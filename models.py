"""
Modelos Pydantic do CoreExtract.
Versão enriquecida com todos os campos que o Gemini pode extrair
e campos de metadados de processamento.
"""
from typing import Literal, Optional
from pydantic import BaseModel, field_validator, model_validator


# =========================================================================== #
#  SUBMODELOS — blocos reutilizáveis                                            #
# =========================================================================== #

class Contato(BaseModel):
    email:    Optional[str] = None
    telefone: Optional[str] = None
    linkedin: Optional[str] = None
    github:   Optional[str] = None
    portfolio: Optional[str] = None
    cidade:   Optional[str] = None
    estado:   Optional[str] = None
    pais:     Optional[str] = "Brasil"


class Habilidades(BaseModel):
    """Skills categorizadas para facilitar triagem por tipo."""
    tecnicas:       list[str] = []   # linguagens, frameworks, ferramentas
    comportamentais: list[str] = []  # soft skills
    ferramentas:    list[str] = []   # IDEs, plataformas, SaaS
    idiomas:        list[str] = []   # idiomas com proficiência (ex: "Inglês — Avançado")


class Experiencia(BaseModel):
    cargo:        Optional[str] = None
    empresa:      Optional[str] = None
    periodo:      Optional[str] = None   # ex: "Jan/2022 – Atual"
    descricao:    Optional[str] = None   # resumo das responsabilidades
    conquistas:   list[str] = []         # realizações quantificadas


class Formacao(BaseModel):
    curso:        Optional[str] = None
    instituicao:  Optional[str] = None
    nivel:        Optional[str] = None   # Graduação, MBA, Pós-Graduação, Técnico...
    ano_conclusao: Optional[str] = None
    em_andamento: bool = False


class Certificacao(BaseModel):
    nome:         Optional[str] = None
    emissor:      Optional[str] = None   # ex: AWS, Google, Microsoft
    ano:          Optional[str] = None
    credencial_id: Optional[str] = None


class ScoreAnalise(BaseModel):
    """
    Scores estimados pelo Gemini (0–100).
    Útil para ranqueamento automático de candidatos.
    """
    experiencia_relevante: int = 0    # profundidade e relevância das exp.
    formacao_academica:    int = 0    # nível e qualidade da formação
    habilidades_tecnicas:  int = 0    # densidade e modernidade das skills
    clareza_comunicacao:   int = 0    # quão bem redigido está o currículo
    score_geral:           int = 0    # média ponderada

    @field_validator(
        "experiencia_relevante", "formacao_academica",
        "habilidades_tecnicas", "clareza_comunicacao", "score_geral",
        mode="before",
    )
    @classmethod
    def clamp_score(cls, v) -> int:
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0


class FitAnalise(BaseModel):
    """
    Análise de aderência quando uma descrição de vaga é fornecida.
    Só é preenchida se o campo job_description for enviado na requisição.
    """
    score_fit:        int = 0          # 0–100
    pontos_fortes:    list[str] = []   # por que o candidato se encaixa
    lacunas:          list[str] = []   # o que está faltando
    recomendacao:     Optional[Literal["Avançar", "Em análise", "Não recomendado"]] = None


# =========================================================================== #
#  MODELO PRINCIPAL DE SAÍDA                                                    #
# =========================================================================== #

class ResumeOutput(BaseModel):
    # Dados pessoais
    nome:                       Optional[str] = None
    contato:                    Optional[Contato] = None

    # Perfil profissional
    resumo_profissional:        Optional[str] = None
    nivel_senioridade:          Optional[str] = "Indefinido"
    anos_experiencia_estimados: Optional[float] = None   # aceita float do modelo (ex: 0.75, 1.5)
    area_atuacao:               Optional[str] = None   # ex: "Engenharia de Software"

    # Competências
    habilidades:                Habilidades = Habilidades()

    # Histórico
    experiencias:               list[Experiencia] = []   # mais recente primeiro
    formacoes:                  list[Formacao] = []
    certificacoes:              list[Certificacao] = []

    # Análise de qualidade
    scores:                     ScoreAnalise = ScoreAnalise()
    fit:                        Optional[FitAnalise] = None  # só se job_description enviado

    # Metadados de extração
    confianca_extracao:         Optional[str] = None  # "Alta" | "Média" | "Baixa"
    observacoes_ia:             Optional[str] = None  # alertas do modelo (ex: "currículo incompleto")

    @field_validator("nivel_senioridade")
    @classmethod
    def validate_senioridade(cls, v: Optional[str]) -> str:
        allowed = {"Júnior", "Pleno", "Sênior", "Especialista", "Indefinido"}
        return v if v in allowed else "Indefinido"

    @model_validator(mode="after")
    def compute_score_geral(self) -> "ResumeOutput":
        s = self.scores
        # Ponderação: experiência (40%) + técnicas (30%) + formação (20%) + clareza (10%)
        if s.score_geral == 0:
            s.score_geral = int(
                s.experiencia_relevante * 0.40
                + s.habilidades_tecnicas  * 0.30
                + s.formacao_academica    * 0.20
                + s.clareza_comunicacao   * 0.10
            )
        return self


# =========================================================================== #
#  MODELOS DE REQUISIÇÃO                                                        #
# =========================================================================== #

class EmailRequest(BaseModel):
    destinatario:        str
    tema:                Optional[str] = "Triagem Geral"
    job_description:     Optional[str] = None   # JD para análise de fit
    contexto_adicional:  Optional[str] = None
    nome_recrutador:     Optional[str] = None
    empresa_recrutadora: Optional[str] = None


# =========================================================================== #
#  MODELO DE RESULTADO POR ARQUIVO                                              #
# =========================================================================== #

class ProcessingResult(BaseModel):
    filename:      str
    status:        Literal["ok", "error"]
    resume:        Optional[ResumeOutput] = None
    error:         Optional[str] = None
    meta:          Optional[dict] = None   # RequestContext.to_response_meta()
