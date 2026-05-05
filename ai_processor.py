"""
Integração com Google AI Studio — Gemini API gratuita.
Modelo padrão: gemini-2.5-flash (rápido, sem custo).
"""
import json
from typing import Optional

import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError, ResourceExhausted

import config
from models import ResumeOutput
from utils.logger import get_logger
from utils.retry import with_retry
from utils.text_cleaner import clean_extracted_text, truncate_for_model
from utils.request_context import RequestContext
from utils.json_utils import extract_json

logger = get_logger("ai_processor")

# Configura o cliente uma única vez
genai.configure(api_key=config.GEMINI_API_KEY)
_model = genai.GenerativeModel(config.GEMINI_MODEL)


# =========================================================================== #
#  PROMPTS                                                                      #
# =========================================================================== #

def _build_system_prompt(job_description: Optional[str] = None) -> str:
    """Monta o prompt de sistema com ou sem análise de fit."""

    fit_schema = ""
    fit_rule   = ""
    fit_jd     = ""

    if job_description and job_description.strip():
        fit_schema = """
  "fit": {
    "score_fit": 0,
    "score_experiencia": 0,
    "score_formacao": 0,
    "score_tecnico": 0,
    "pontos_fortes": [],
    "lacunas": [],
    "recomendacao": "Avançar|Em análise|Não recomendado"
  },"""
        fit_rule = (
            '- fit.score_fit: 0-100, aderência geral candidato × vaga.\n'
            '- fit.score_experiencia: 0-100, quanto a experiência do candidato corresponde à vaga.\n'
            '- fit.score_formacao: 0-100, quanto a formação acadêmica corresponde ao requisito da vaga.\n'
            '- fit.score_tecnico: 0-100, quanto as habilidades técnicas correspondem ao exigido pela vaga.\n'
            '- fit.recomendacao: "Avançar" (score_fit>=70), "Em análise" (40-69), '
            '"Não recomendado" (<40).\n'
        )
        fit_jd = f"\n\nDESCRIÇÃO DA VAGA (use para preencher o campo fit):\n{job_description.strip()[:3_000]}"

    return f"""Você é um assistente de RH sênior com 20 anos de experiência em recrutamento técnico.
Analisa currículos com precisão e retorna dados estruturados em JSON.

REGRAS ABSOLUTAS:
- Retorne APENAS um objeto JSON válido. Nenhum texto, markdown ou explicação fora do JSON.
- Se uma informação não está no texto, use null. Nunca invente dados.
- resumo_profissional: máximo 3 frases objetivas.
- habilidades.tecnicas: máximo 12 itens.
- habilidades.comportamentais: máximo 6 itens.
- experiencias: as 3 mais recentes, da mais recente para a mais antiga.
- scores.experiencia_relevante: 0-100, profundidade e volume de experiência profissional do currículo.
- scores.formacao_academica: 0-100, nível e qualidade da formação acadêmica apresentada no currículo.
- scores.score_geral: deixe 0 (será calculado automaticamente).
- confianca_extracao: "Alta" se claro e completo, "Média" se parcial, "Baixa" se difícil.
{fit_rule}
FORMATO JSON DE SAÍDA (siga rigorosamente — inclua TODOS os campos, mesmo que null):
{{
  "nome": "string|null",
  "contato": {{
    "email": "string|null",
    "telefone": "string|null",
    "linkedin": "string|null",
    "github": "string|null",
    "portfolio": "string|null",
    "cidade": "string|null",
    "estado": "string|null",
    "pais": "string|null"
  }},
  "resumo_profissional": "string|null",
  "nivel_senioridade": "Júnior|Pleno|Sênior|Especialista|Indefinido",
  "anos_experiencia_estimados": null,
  "area_atuacao": "string|null",
  "habilidades": {{
    "tecnicas": [],
    "comportamentais": [],
    "ferramentas": [],
    "idiomas": []
  }},
  "experiencias": [
    {{
      "cargo": "string|null",
      "empresa": "string|null",
      "periodo": "string|null",
      "descricao": "string|null",
      "conquistas": []
    }}
  ],
  "formacoes": [
    {{
      "curso": "string|null",
      "instituicao": "string|null",
      "nivel": "string|null",
      "ano_conclusao": "string|null",
      "em_andamento": false
    }}
  ],
  "certificacoes": [
    {{
      "nome": "string|null",
      "emissor": "string|null",
      "ano": "string|null",
      "credencial_id": "string|null"
    }}
  ],
  "scores": {{
    "experiencia_relevante": 0,
    "formacao_academica": 0,
    "score_geral": 0
  }},{fit_schema}
  "confianca_extracao": "Alta|Média|Baixa",
  "observacoes_ia": "string|null"
}}{fit_jd}"""


# =========================================================================== #
#  CHAMADA AO GEMINI (com retry)                                                #
# =========================================================================== #

@with_retry(
    max_attempts=3,
    base_delay=2.0,
    max_delay=20.0,
    retryable_exceptions=(GoogleAPIError, ResourceExhausted),
    non_retryable_exceptions=(ValueError,),
)
def _call_gemini(prompt: str) -> tuple[str, int, int]:
    """Chama o Gemini e retorna (texto, tokens_entrada, tokens_saída)."""
    response = _model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.05,
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )
    text        = response.text.strip()
    tokens_in   = response.usage_metadata.prompt_token_count     or 0
    tokens_out  = response.usage_metadata.candidates_token_count or 0
    return text, tokens_in, tokens_out


# =========================================================================== #
#  FUNÇÃO PRINCIPAL                                                             #
# =========================================================================== #

def analyze_resume(
    raw_text: str,
    ctx: RequestContext,
    job_description: Optional[str] = None,
) -> ResumeOutput:
    """
    Pipeline: limpa texto → monta prompt → chama Gemini → valida Pydantic.
    """
    ctx.step("text_clean")
    cleaned, was_truncated = truncate_for_model(
        clean_extracted_text(raw_text),
        max_chars=25_000,   # Gemini 1.5 Flash suporta 1M tokens
    )
    ctx.chars_extracted = len(cleaned)
    ctx.was_truncated   = was_truncated

    if not cleaned:
        raise ValueError(
            "Texto extraído está vazio. O arquivo pode estar corrompido, "
            "protegido por senha ou sem conteúdo textual."
        )

    ctx.step("prompt_build")
    system = _build_system_prompt(job_description)
    aviso = "\n\n[AVISO: Texto truncado por ser muito longo.]" if was_truncated else ""
    full_prompt = f"{system}\n\nTEXTO DO CURRÍCULO:{aviso}\n\n{cleaned}"

    logger.info(
        "Enviando ao Gemini | modelo=%s chars=%d truncado=%s fit=%s",
        config.GEMINI_MODEL, len(cleaned), was_truncated, bool(job_description),
        extra=ctx.to_log_extras(),
    )

    ctx.step("gemini_call")
    raw_response, tokens_in, tokens_out = _call_gemini(full_prompt)
    ctx.gemini_input_tokens  = tokens_in
    ctx.gemini_output_tokens = tokens_out

    logger.info(
        "Resposta recebida | tokens_in=%d tokens_out=%d",
        tokens_in, tokens_out, extra=ctx.to_log_extras(),
    )

    ctx.step("json_parse")
    try:
        data = extract_json(raw_response)
    except ValueError as exc:
        logger.error("JSON inválido: %.300s | erro: %s", raw_response, exc,
                     extra=ctx.to_log_extras())
        raise

    ctx.step("pydantic_validate")
    result = ResumeOutput(**data)

    logger.info(
        "Extração concluída | candidato='%s' nivel='%s' score=%d confiança='%s'",
        result.nome or "N/A", result.nivel_senioridade,
        result.scores.score_geral, result.confianca_extracao or "N/A",
        extra=ctx.to_log_extras(),
    )
    return result
