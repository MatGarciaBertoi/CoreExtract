"""
Constrói o e-mail de triagem com textos gerados localmente (sem chamada extra ao Gemini)
e montagem direta dos cards HTML pelo código.

Removida a chamada Gemini para textos do e-mail: a extração do currículo já consome
a cota diária do free tier; os textos de boilerplate do e-mail não precisam de IA.
"""
from pathlib import Path
from typing import Optional

import config
from brand import EMERALD, AMBER, CORAL
from models import ProcessingResult, ResumeOutput, FitAnalise
from utils.logger import get_logger

logger = get_logger("email_builder")

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "email_base.html"


# =========================================================================== #
#  GERAÇÃO DE TEXTOS DO E-MAIL — LOCAL, SEM IA                                 #
# =========================================================================== #

def _build_email_texts(
    tema: str,
    destinatario_nome: str,
    total_candidatos: int,
    nome_recrutador: Optional[str],
    empresa_recrutadora: Optional[str],
    contexto_adicional: Optional[str],
    ok_results: list,
) -> dict:
    """Gera os textos do e-mail localmente, sem chamar o Gemini."""
    assinatura  = nome_recrutador or "Equipe de Recrutamento"
    empresa_str = f" — {empresa_recrutadora}" if empresa_recrutadora else ""

    # Assunto
    subject = f"[CoreExtract] Triagem de Currículos — {tema}"
    if len(subject) > 80:
        subject = f"[CoreExtract] Triagem — {tema[:50]}"

    # Título e subtítulo
    email_title    = f"Triagem — {tema}"
    n_str = f"{total_candidatos} candidato{'s' if total_candidatos != 1 else ''} analisado{'s' if total_candidatos != 1 else ''}"
    email_subtitle = n_str

    # Saudação
    scores = [r.resume.scores.score_geral for r in ok_results if r.resume]
    top    = max(scores) if scores else 0
    avg    = int(sum(scores) / len(scores)) if scores else 0

    # Parágrafo de observação adicional — linha separada quando preenchido
    obs_extra = (
        f"<p><b>Observação adicional:</b> {contexto_adicional}</p>"
        if contexto_adicional else ""
    )

    greeting_html = (
        f"<p>Olá, <b>{destinatario_nome}</b>!</p>"
        f"<p>Segue abaixo o relatório de triagem inteligente para a vaga <b>{tema}</b>. "
        f"Foram analisados <b>{total_candidatos}</b> currículo{'s' if total_candidatos != 1 else ''}, "
        f"com score médio de <b>{avg}/100</b> e melhor score de <b>{top}/100</b>.</p>"
        f"{obs_extra}"
        f"<p>Em anexo você encontra a <b>planilha Excel completa</b> com a análise detalhada "
        f"de cada candidato, incluindo scores individuais, gráficos comparativos e "
        f"distribuição por nível de senioridade.</p>"
    )

    closing_html = (
        f"<p>Esta análise foi gerada automaticamente pelo <b>CoreExtract · RH Inteligente</b> "
        f"com base nos dados extraídos dos currículos. Recomendamos revisão humana antes de "
        f"tomar decisões finais de contratação.</p>"
        f"<p>Atenciosamente,<br><b>{assinatura}{empresa_str}</b></p>"
    )

    return {
        "subject":        subject,
        "email_title":    email_title,
        "email_subtitle": email_subtitle,
        "greeting_html":  greeting_html,
        "closing_html":   closing_html,
    }


# =========================================================================== #
#  MONTAGEM DOS CARDS HTML                                                      #
# =========================================================================== #

def _badge_class(nivel: Optional[str]) -> str:
    return {
        "Júnior":       "badge-junior",
        "Pleno":        "badge-pleno",
        "Sênior":       "badge-senior",
        "Especialista": "badge-especialista",
    }.get(nivel or "", "badge-indefinido")


def _score_bar(label: str, value: int) -> str:
    pct   = max(0, min(100, value))
    color = EMERALD if pct >= 70 else (AMBER if pct >= 40 else CORAL)
    return f"""
    <div class="score-section">
      <div class="score-label">{label} — <b style="color:{color}">{pct}/100</b></div>
      <div class="score-bar-bg">
        <div class="score-bar-fill" style="width:{pct}%;background:{color}"></div>
      </div>
    </div>"""


def _fit_html(fit: Optional[FitAnalise]) -> str:
    if not fit:
        return ""
    rec_class = {
        "Avançar":         "fit-rec-avancar",
        "Em análise":      "fit-rec-analise",
        "Não recomendado": "fit-rec-nao",
    }.get(fit.recomendacao or "", "fit-rec-analise")
    items = (
        "".join(f"<li>✓ {p}</li>" for p in (fit.pontos_fortes or [])[:3]) +
        "".join(f"<li>✗ {l}</li>" for l in (fit.lacunas or [])[:3])
    )
    return f"""
    <div class="fit-box">
      <div class="fit-title">Análise de Fit com a Vaga</div>
      <div class="fit-score-row">
        <div>
          <div class="fit-score-num">{fit.score_fit}</div>
          <div class="fit-score-label">score de aderência</div>
        </div>
        <div><span class="fit-rec {rec_class}">{fit.recomendacao or 'Em análise'}</span></div>
      </div>
      {'<ul class="fit-list">' + items + '</ul>' if items else ''}
    </div>"""


def _recruiter_note_html(comment: str) -> str:
    """Bloco de anotação do recrutador — visualmente distinto das obs. da IA."""
    if not comment or not comment.strip():
        return ""
    safe = comment.strip().replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <div style="margin-top:12px;padding:10px 14px;background:#F4EEFF;
                border-left:3px solid #8B5CF6;border-radius:6px;">
      <div style="font-size:10px;font-weight:700;color:#6D28D9;
                  text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px;">
        ✏ Anotação do Recrutador
      </div>
      <div style="font-size:12px;color:#3B1F6E;line-height:1.55;">{safe}</div>
    </div>"""


def _candidate_card(result: ProcessingResult, index: int,
                    recruiter_comment: str = "") -> str:
    r: ResumeOutput = result.resume  # type: ignore
    nome  = r.nome or "Candidato sem nome"
    cargo = ""
    if r.experiencias:
        e = r.experiencias[0]
        cargo = f"{e.cargo or ''}{' @ ' + e.empresa if e.cargo and e.empresa else (e.empresa or '')}"

    chips = "".join(
        f'<span class="skill-chip">{s}</span>'
        for s in ((r.habilidades.tecnicas or [])[:6] + (r.habilidades.ferramentas or [])[:2])[:8]
    )
    scores_html = (
        _score_bar("Score Geral",  r.scores.score_geral)
        + _score_bar("Experiência", r.scores.experiencia_relevante)
        + _score_bar("Técnico",     r.scores.habilidades_tecnicas)
        + _score_bar("Formação",    r.scores.formacao_academica)
    )
    contato_parts = []
    if r.contato:
        if r.contato.email:    contato_parts.append(f'<a href="mailto:{r.contato.email}">{r.contato.email}</a>')
        if r.contato.telefone: contato_parts.append(r.contato.telefone)
        if r.contato.linkedin: contato_parts.append(f'<a href="{r.contato.linkedin}">LinkedIn</a>')
        if r.contato.cidade:
            contato_parts.append(r.contato.cidade + (f", {r.contato.estado}" if r.contato.estado else ""))
    contato_html = '<span class="contact-sep">·</span>'.join(contato_parts)

    certs = ", ".join(
        f"{c.nome}{' (' + c.emissor + ')' if c.emissor else ''}"
        for c in (r.certificacoes or [])[:3]
    )
    return f"""
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-name">{index}. {nome}</div>
          {'<div class="card-role">' + cargo + '</div>' if cargo else ''}
          {'<div class="card-role" style="color:#00C8FF">' + (r.area_atuacao or '') + ('&nbsp;·&nbsp;' + str(r.anos_experiencia_estimados) + ' anos' if r.anos_experiencia_estimados else '') + '</div>' if r.area_atuacao else ''}
          <div class="card-file">📄 {result.filename}</div>
        </div>
        <span class="badge {_badge_class(r.nivel_senioridade)}">{r.nivel_senioridade or 'Indefinido'}</span>
      </div>
      {'<div style="font-size:13px;color:#3A4563;line-height:1.6;margin-bottom:12px">' + r.resumo_profissional + '</div>' if r.resumo_profissional else ''}
      {scores_html}
      {'<div class="skills-section"><div class="skills-label">Principais Habilidades</div><div class="skills-wrap">' + chips + '</div></div>' if chips else ''}
      {'<div style="margin-top:10px;font-size:12px;color:#6B7A99;">🏅 ' + certs + '</div>' if certs else ''}
      {'<div class="contact-row">' + contato_html + '</div>' if contato_html else ''}
      {_fit_html(r.fit)}
      {_recruiter_note_html(recruiter_comment)}
      {'<div style="margin-top:8px;font-size:11px;color:#9AAABF;font-style:italic;">ℹ ' + r.observacoes_ia + '</div>' if r.observacoes_ia else ''}
    </div>"""


def _error_card(result: ProcessingResult, index: int) -> str:
    return f"""
    <div class="card" style="border-color:#FFD0D0;background:#FFF5F5;">
      <div class="card-name" style="color:#CC2200">{index}. {result.filename}</div>
      <div style="font-size:13px;color:#884444;margin-top:8px;">
        ⚠ Não foi possível processar este arquivo.<br>
        <span style="font-size:11px;color:#AA6666">{result.error or 'Erro desconhecido'}</span>
      </div>
    </div>"""


# =========================================================================== #
#  FUNÇÃO PRINCIPAL                                                             #
# =========================================================================== #

def build_email_content(
    results: list[ProcessingResult],
    tema: str,
    destinatario_nome: str,
    nome_recrutador: Optional[str] = None,
    empresa_recrutadora: Optional[str] = None,
    contexto_adicional: Optional[str] = None,
    recruiter_comments: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Retorna {"subject": str, "html_body": str} com o e-mail completo."""
    ok_results    = [r for r in results if r.status == "ok" and r.resume]
    error_results = [r for r in results if r.status == "error"]

    if not ok_results and not error_results:
        raise ValueError("Nenhum resultado disponível para o e-mail.")

    logger.info("Montando e-mail | tema='%s' candidatos=%d", tema, len(ok_results))

    texts = _build_email_texts(
        tema=tema,
        destinatario_nome=destinatario_nome,
        total_candidatos=len(ok_results),
        nome_recrutador=nome_recrutador,
        empresa_recrutadora=empresa_recrutadora,
        contexto_adicional=contexto_adicional,
        ok_results=ok_results,
    )

    comments = recruiter_comments or {}
    cards_html = ""
    for i, r in enumerate(ok_results, start=1):
        comment = comments.get(r.filename, "")
        cards_html += _candidate_card(r, i, recruiter_comment=comment)
    for i, r in enumerate(error_results, start=len(ok_results) + 1):
        cards_html += _error_card(r, i)

    template  = _TEMPLATE_PATH.read_text(encoding="utf-8")
    html_body = (
        template
        .replace("{{EMAIL_SUBJECT}}",        texts["subject"])
        .replace("{{EMAIL_TITLE}}",          texts["email_title"])
        .replace("{{EMAIL_SUBTITLE}}",       texts["email_subtitle"])
        .replace("{{GREETING_HTML}}",        texts["greeting_html"])
        .replace("{{CANDIDATE_CARDS_HTML}}", cards_html)
        .replace("{{CLOSING_HTML}}",         texts["closing_html"])
    )
    return {"subject": texts["subject"], "html_body": html_body}
