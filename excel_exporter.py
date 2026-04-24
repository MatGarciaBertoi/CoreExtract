"""
Gerador de relatório Excel completo para o CoreExtract.

Produz um .xlsx com 3 abas:
  1. Candidatos   — tabela formatada com todas as colunas, cores por score
  2. Dashboard    — KPIs + gráficos (score geral, breakdown, nível, fit)
  3. Fit & Notas  — apenas quando job_description foi fornecido

Retorna bytes prontos para stream HTTP ou anexo de e-mail.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.series import SeriesLabel
from openpyxl.styles import (
    Alignment, Border, Font, GradientFill, PatternFill, Side,
)
from openpyxl.utils import get_column_letter

# ── Brand palette ────────────────────────────────────────────────────────────
_NAVY    = "0D1B2A"
_BLUE    = "1A6BFF"
_CYAN    = "00C8FF"
_EMERALD = "00D68F"
_AMBER   = "FFB830"
_CORAL   = "FF5757"
_SLATE   = "F0F4FF"
_WHITE   = "FFFFFF"
_GRAY    = "6B7A99"
_LIGHTBG = "EEF3FF"


# ── Style helpers ────────────────────────────────────────────────────────────

def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)

def _font(bold=False, size=11, color=_NAVY, italic=False) -> Font:
    return Font(bold=bold, size=size, color=color, italic=italic, name="Calibri")

def _center() -> Alignment:
    return Alignment(horizontal="center", vertical="center", wrap_text=True)

def _left() -> Alignment:
    return Alignment(horizontal="left", vertical="center", wrap_text=True)

def _thin_border() -> Border:
    s = Side(style="thin", color="D0D8F0")
    return Border(left=s, right=s, top=s, bottom=s)

def _score_fill(v: int) -> PatternFill:
    if v >= 70: return _fill("D6FAE8")
    if v >= 40: return _fill("FFF8E1")
    return _fill("FFE8E8")

def _score_font(v: int) -> Font:
    if v >= 70: return _font(bold=True, color="007A4C")
    if v >= 40: return _font(bold=True, color="7A4F00")
    return _font(bold=True, color="CC2200")


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_excel_report(
    results: list[dict],
    tema: str = "Triagem Geral",
    nome_recrutador: Optional[str] = None,
    empresa_recrutadora: Optional[str] = None,
) -> bytes:
    """
    Gera o relatório Excel e retorna bytes.

    `results` é a lista de ProcessingResult.model_dump() já filtrada/ordenada.
    """
    wb = Workbook()
    wb.remove(wb.active)           # remove default sheet

    ok_results = [r for r in results if r.get("status") == "ok"]

    _build_candidates_sheet(wb, ok_results)
    _build_dashboard_sheet(wb, ok_results, tema, nome_recrutador, empresa_recrutadora)

    has_fit = any(r.get("resume", {}).get("fit") for r in ok_results)
    if has_fit:
        _build_fit_sheet(wb, ok_results)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Sheet 1: Candidatos ───────────────────────────────────────────────────────

def _build_candidates_sheet(wb: Workbook, ok_results: list[dict]) -> None:
    ws = wb.create_sheet("Candidatos")
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    headers = [
        "Rank", "Nome", "E-mail", "Telefone", "LinkedIn", "GitHub",
        "Cidade", "Nível", "Área", "Exp. (anos)",
        "Score Geral", "Score Exp.", "Score Técnico", "Score Formação", "Score Comunic.",
        "Fit Score", "Fit Recomendação",
        "Habilidades Técnicas", "Idiomas",
        "Empresa Atual", "Cargo Atual",
        "Confiança IA", "Obs. IA", "Arquivo",
    ]
    col_widths = [
        6, 28, 30, 16, 36, 28,
        16, 12, 22, 12,
        12, 12, 14, 14, 14,
        10, 18,
        42, 24,
        24, 26,
        12, 34, 34,
    ]

    # Header row
    for col_idx, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = _fill(_NAVY)
        cell.font = _font(bold=True, size=10, color=_WHITE)
        cell.alignment = _center()
        cell.border = _thin_border()
        ws.column_dimensions[get_column_letter(col_idx)].width = w
    ws.row_dimensions[1].height = 28

    score_cols = {11, 12, 13, 14, 15, 16}   # 1-based col indices

    for rank, r in enumerate(ok_results, 1):
        resume  = r.get("resume") or {}
        contato = resume.get("contato") or {}
        scores  = resume.get("scores") or {}
        fit     = resume.get("fit") or {}
        exps    = resume.get("experiencias") or []
        habs    = resume.get("habilidades") or {}
        row = rank + 1

        row_data = [
            rank,
            resume.get("nome", ""),
            contato.get("email", ""),
            contato.get("telefone", ""),
            contato.get("linkedin", ""),
            contato.get("github", ""),
            contato.get("cidade", ""),
            resume.get("nivel_senioridade", ""),
            resume.get("area_atuacao", ""),
            resume.get("anos_experiencia_estimados", ""),
            scores.get("score_geral", 0),
            scores.get("experiencia_relevante", 0),
            scores.get("habilidades_tecnicas", 0),
            scores.get("formacao_academica", 0),
            scores.get("clareza_comunicacao", 0),
            fit.get("score_fit", "") if fit else "",
            fit.get("recomendacao", "") if fit else "",
            ", ".join(habs.get("tecnicas", [])),
            ", ".join(habs.get("idiomas", [])),
            exps[0].get("empresa", "") if exps else "",
            exps[0].get("cargo", "") if exps else "",
            resume.get("confianca_extracao", ""),
            resume.get("observacoes_ia", ""),
            r.get("filename", ""),
        ]

        row_fill = _fill(_LIGHTBG) if rank % 2 == 0 else _fill(_WHITE)
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row, column=col_idx, value=value)
            cell.border = _thin_border()
            cell.alignment = _center() if col_idx in score_cols | {1, 8, 10, 16} else _left()
            if col_idx in score_cols and isinstance(value, (int, float)) and value != "":
                cell.fill  = _score_fill(int(value))
                cell.font  = _score_font(int(value))
            else:
                cell.fill = row_fill
                cell.font = _font(size=10)
                if col_idx == 2:                          # Nome — bold
                    cell.font = _font(bold=True, size=10)
                if col_idx == 8:                          # Nível
                    nivel_colors = {
                        "Sênior":      ("D6FAE8", "007A4C"),
                        "Especialista":("E0F8FF", "005580"),
                        "Pleno":       ("EEF4FF", "1A3A8B"),
                        "Júnior":      ("FFF8E1", "7A4F00"),
                    }
                    if value in nivel_colors:
                        bg, fg = nivel_colors[value]
                        cell.fill = _fill(bg)
                        cell.font = _font(bold=True, size=10, color=fg)
                if col_idx == 17:                         # Fit recomendação
                    rec_colors = {
                        "Avançar":         ("D6FAE8", "007A4C"),
                        "Em análise":      ("FFF8E1", "7A4F00"),
                        "Não recomendado": ("FFE8E8", "CC2200"),
                    }
                    if value in rec_colors:
                        bg, fg = rec_colors[value]
                        cell.fill = _fill(bg)
                        cell.font = _font(bold=True, size=10, color=fg)
        ws.row_dimensions[row].height = 20

    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(ok_results)+1}"


# ── Sheet 2: Dashboard ────────────────────────────────────────────────────────

def _build_dashboard_sheet(
    wb: Workbook,
    ok_results: list[dict],
    tema: str,
    nome_recrutador: Optional[str],
    empresa_recrutadora: Optional[str],
) -> None:
    ws = wb.create_sheet("Dashboard")
    ws.sheet_view.showGridLines = False

    # Column widths
    for i, w in enumerate([2, 18, 18, 18, 18, 18, 18, 2], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ── Title block ──
    ws.merge_cells("B2:G2")
    title = ws["B2"]
    title.value = "CoreExtract — Relatório de Triagem"
    title.font  = _font(bold=True, size=20, color=_WHITE)
    title.fill  = _fill(_NAVY)
    title.alignment = _center()
    ws.row_dimensions[2].height = 40

    ws.merge_cells("B3:G3")
    sub = ws["B3"]
    sub.value = f"Tema: {tema}  ·  Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    sub.font  = _font(size=11, color="A0B4CC", italic=True)
    sub.fill  = _fill("0A1628")
    sub.alignment = _center()
    ws.row_dimensions[3].height = 22

    if nome_recrutador or empresa_recrutadora:
        ws.merge_cells("B4:G4")
        meta = ws["B4"]
        meta_parts = []
        if nome_recrutador:    meta_parts.append(f"Recrutador: {nome_recrutador}")
        if empresa_recrutadora: meta_parts.append(f"Empresa: {empresa_recrutadora}")
        meta.value = "  ·  ".join(meta_parts)
        meta.font  = _font(size=10, color=_GRAY)
        meta.fill  = _fill(_SLATE)
        meta.alignment = _center()
        ws.row_dimensions[4].height = 18

    # ── KPI cards ──
    scores_all = [r.get("resume", {}).get("scores", {}).get("score_geral", 0) for r in ok_results]
    top_name   = ok_results[0].get("resume", {}).get("nome", "—") if ok_results else "—"
    avg_score  = round(sum(scores_all) / len(scores_all)) if scores_all else 0
    top_score  = max(scores_all) if scores_all else 0

    kpi_start_row = 6
    kpis = [
        ("Total de Candidatos", len(ok_results), _BLUE,    _WHITE),
        ("Melhor Score",         top_score,       _EMERALD, "002B1C"),
        ("Score Médio",          avg_score,        _AMBER,   "3D2900"),
        ("Top Candidato",        top_name,         "1A3A6B", _WHITE),
    ]
    kpi_cols = [2, 3, 5, 6]        # skip col 4 (gap between pairs)

    for (label, value, bg, fg), col in zip(kpis, kpi_cols):
        label_cell = ws.cell(row=kpi_start_row, column=col, value=label)
        label_cell.fill = _fill(bg)
        label_cell.font = _font(size=9, color=fg, bold=False)
        label_cell.alignment = _center()
        label_cell.border = _thin_border()
        ws.row_dimensions[kpi_start_row].height = 18

        value_cell = ws.cell(row=kpi_start_row + 1, column=col, value=value)
        value_cell.fill = _fill(bg)
        value_cell.font = _font(bold=True, size=16, color=fg)
        value_cell.alignment = _center()
        value_cell.border = _thin_border()
        ws.row_dimensions[kpi_start_row + 1].height = 36

    # ── Hidden data for charts ── (rows 10+)
    data_row_start = 10

    # Section header
    ws.merge_cells(f"B{data_row_start}:G{data_row_start}")
    sec = ws[f"B{data_row_start}"]
    sec.value = "Dados para gráficos (não edite)"
    sec.font  = _font(size=8, color="C0CCE0", italic=True)
    sec.alignment = _left()
    data_row_start += 1

    # Score table: col B=Nome, C=ScoreGeral, D=Exp, E=Tec, F=Form, G=Comun
    ws.cell(row=data_row_start, column=2, value="Candidato")
    ws.cell(row=data_row_start, column=3, value="Score Geral")
    ws.cell(row=data_row_start, column=4, value="Experiência")
    ws.cell(row=data_row_start, column=5, value="Técnico")
    ws.cell(row=data_row_start, column=6, value="Formação")
    ws.cell(row=data_row_start, column=7, value="Comunicação")
    for c in range(2, 8):
        ws.cell(row=data_row_start, column=c).font = _font(bold=True, size=9, color=_GRAY)

    chart_rows = []
    for i, r in enumerate(ok_results[:12]):        # max 12 on chart
        resume = r.get("resume") or {}
        scores = resume.get("scores") or {}
        nome   = (resume.get("nome") or r.get("filename", ""))[:20]
        row = data_row_start + 1 + i
        ws.cell(row=row, column=2, value=nome)
        ws.cell(row=row, column=3, value=scores.get("score_geral", 0))
        ws.cell(row=row, column=4, value=scores.get("experiencia_relevante", 0))
        ws.cell(row=row, column=5, value=scores.get("habilidades_tecnicas", 0))
        ws.cell(row=row, column=6, value=scores.get("formacao_academica", 0))
        ws.cell(row=row, column=7, value=scores.get("clareza_comunicacao", 0))
        for c in range(2, 8):
            ws.cell(row=row, column=c).font = _font(size=9)
        chart_rows.append(row)

    n_chart = len(chart_rows)
    if n_chart == 0:
        return

    r0  = data_row_start + 1
    r1  = data_row_start + n_chart

    # Palette por candidato (Chart 1 e Chart 2 usam as mesmas cores para consistência)
    _CANDIDATE_PALETTE = [
        _BLUE, _EMERALD, _AMBER, _CYAN, _CORAL,
        "9B59B6", "E67E22", "1ABC9C", "E74C3C", "2ECC71", "F1C40F", "3498DB",
    ]

    # ── Chart 1: Score Geral — uma série por candidato, cor distinta ──
    chart1 = BarChart()
    chart1.type        = "col"
    chart1.grouping    = "clustered"
    chart1.title       = "Score Geral por Candidato"
    chart1.y_axis.title = "Score"
    chart1.x_axis.title = "Candidato"
    chart1.style       = 10
    chart1.width       = 18
    chart1.height      = 10
    chart1.varyColors  = True   # cor diferente por barra dentro de uma única série

    data_ref1 = Reference(ws, min_col=3, max_col=3, min_row=data_row_start, max_row=r1)
    cats1     = Reference(ws, min_col=2, max_col=2, min_row=r0, max_row=r1)
    chart1.add_data(data_ref1, titles_from_data=True)
    chart1.set_categories(cats1)
    # Não definir solidFill: deixa varyColors escolher as cores automaticamente
    ws.add_chart(chart1, "B14")

    # ── Chart 2: Breakdown — transposto (série por candidato, eixo X = métricas) ──
    # Bloco transposto: col B = Métrica, col C+ = candidatos
    _METRIC_KEYS   = ["experiencia_relevante", "habilidades_tecnicas",
                      "formacao_academica", "clareza_comunicacao"]
    _METRIC_LABELS = ["Experiência", "Técnico", "Formação", "Comunicação"]
    n_cands   = min(n_chart, 8)          # máx. 8 candidatos no breakdown
    trans_row = r1 + 2                   # começa após os dados horizontais

    # Cabeçalho: "Métrica" + nomes dos candidatos
    ws.cell(row=trans_row, column=2, value="Métrica").font = _font(bold=True, size=9, color=_GRAY)
    for j in range(n_cands):
        resume = ok_results[j].get("resume") or {}
        nome   = (resume.get("nome") or ok_results[j].get("filename", ""))[:18]
        ws.cell(row=trans_row, column=3 + j, value=nome).font = _font(bold=True, size=9, color=_GRAY)

    # Linhas de dados: uma por métrica
    for i, (key, label) in enumerate(zip(_METRIC_KEYS, _METRIC_LABELS)):
        row_t = trans_row + 1 + i
        ws.cell(row=row_t, column=2, value=label).font = _font(size=9)
        for j in range(n_cands):
            scores = (ok_results[j].get("resume") or {}).get("scores") or {}
            ws.cell(row=row_t, column=3 + j, value=scores.get(key, 0)).font = _font(size=9)

    chart2 = BarChart()
    chart2.type        = "col"
    chart2.grouping    = "clustered"
    chart2.title       = "Breakdown de Scores por Candidato"
    chart2.y_axis.title = "Score"
    chart2.style       = 10
    chart2.width       = 18
    chart2.height      = 10

    # Uma série por candidato (colunas C até C+n_cands), categorias = 4 métricas
    data_ref2 = Reference(ws, min_col=3, max_col=3 + n_cands - 1,
                          min_row=trans_row, max_row=trans_row + 4)
    cats2     = Reference(ws, min_col=2, max_col=2,
                          min_row=trans_row + 1, max_row=trans_row + 4)
    chart2.add_data(data_ref2, titles_from_data=True)
    chart2.set_categories(cats2)

    for s, c in zip(chart2.series, _CANDIDATE_PALETTE[:n_cands]):
        s.graphicalProperties.solidFill      = c
        s.graphicalProperties.line.solidFill = c
    ws.add_chart(chart2, "J14")

    # ── Chart 3: Pie — distribuição por nível ──
    nivel_counts: dict[str, int] = {}
    for r in ok_results:
        n = r.get("resume", {}).get("nivel_senioridade", "Indefinido") or "Indefinido"
        nivel_counts[n] = nivel_counts.get(n, 0) + 1

    pie_row_start = trans_row + 6     # após bloco transposto (1 header + 4 dados + 1 gap)
    ws.cell(row=pie_row_start,     column=2, value="Nível")
    ws.cell(row=pie_row_start,     column=3, value="Qtd")
    ws.cell(row=pie_row_start,     column=2).font = _font(bold=True, size=9, color=_GRAY)
    ws.cell(row=pie_row_start,     column=3).font = _font(bold=True, size=9, color=_GRAY)
    for i, (nivel, count) in enumerate(nivel_counts.items()):
        ws.cell(row=pie_row_start + 1 + i, column=2, value=nivel)
        ws.cell(row=pie_row_start + 1 + i, column=3, value=count)

    n_niveis = len(nivel_counts)
    chart3 = PieChart()
    chart3.title  = "Distribuição por Nível"
    chart3.style  = 10
    chart3.width  = 12
    chart3.height = 10

    data_ref3 = Reference(ws, min_col=3, max_col=3,
                          min_row=pie_row_start, max_row=pie_row_start + n_niveis)
    cats3     = Reference(ws, min_col=2, max_col=2,
                          min_row=pie_row_start + 1, max_row=pie_row_start + n_niveis)
    chart3.add_data(data_ref3, titles_from_data=True)
    chart3.set_categories(cats3)
    ws.add_chart(chart3, "B30")

    # ── Chart 4: Fit scores (if available) ──
    has_fit = any(r.get("resume", {}).get("fit") for r in ok_results)
    if has_fit:
        fit_row_start = pie_row_start + n_niveis + 2
        ws.cell(row=fit_row_start, column=2, value="Candidato")
        ws.cell(row=fit_row_start, column=3, value="Fit Score")
        ws.cell(row=fit_row_start, column=2).font = _font(bold=True, size=9, color=_GRAY)
        ws.cell(row=fit_row_start, column=3).font = _font(bold=True, size=9, color=_GRAY)
        fit_rows = 0
        for r in ok_results:
            resume = r.get("resume") or {}
            fit    = resume.get("fit")
            if fit and fit.get("score_fit") is not None:
                nome = (resume.get("nome") or "")[:20]
                ws.cell(row=fit_row_start + 1 + fit_rows, column=2, value=nome)
                ws.cell(row=fit_row_start + 1 + fit_rows, column=3, value=fit.get("score_fit", 0))
                fit_rows += 1

        if fit_rows > 0:
            chart4 = BarChart()
            chart4.type        = "bar"
            chart4.grouping    = "clustered"
            chart4.title       = "Score de Fit por Candidato"
            chart4.x_axis.title = "Score Fit"
            chart4.style       = 10
            chart4.width       = 12
            chart4.height      = 10
            chart4.varyColors  = True   # cor distinta por candidato
            data_ref4 = Reference(ws, min_col=3, max_col=3,
                                  min_row=fit_row_start, max_row=fit_row_start + fit_rows)
            cats4     = Reference(ws, min_col=2, max_col=2,
                                  min_row=fit_row_start + 1, max_row=fit_row_start + fit_rows)
            chart4.add_data(data_ref4, titles_from_data=True)
            chart4.set_categories(cats4)
            # Não força solidFill — varyColors escolhe paleta automática
            ws.add_chart(chart4, "J30")


# ── Sheet 3: Fit & Notas ──────────────────────────────────────────────────────

def _build_fit_sheet(wb: Workbook, ok_results: list[dict]) -> None:
    ws = wb.create_sheet("Fit & Notas")
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    headers = [
        "Rank", "Nome", "Fit Score", "Recomendação",
        "Pontos Fortes", "Lacunas", "Score Geral", "Nível", "Arquivo",
    ]
    col_widths = [6, 28, 10, 18, 50, 50, 12, 12, 30]

    for col_idx, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = _fill(_NAVY)
        cell.font = _font(bold=True, size=10, color=_WHITE)
        cell.alignment = _center()
        cell.border = _thin_border()
        ws.column_dimensions[get_column_letter(col_idx)].width = w
    ws.row_dimensions[1].height = 28

    fit_results = [(i+1, r) for i, r in enumerate(ok_results) if r.get("resume", {}).get("fit")]
    for rank, (orig_rank, r) in enumerate(fit_results, 1):
        resume = r.get("resume") or {}
        fit    = resume.get("fit") or {}
        scores = resume.get("scores") or {}
        row    = rank + 1

        fit_score = fit.get("score_fit", 0) or 0
        rec       = fit.get("recomendacao", "")
        fortes    = " | ".join(fit.get("pontos_fortes", []))
        lacunas   = " | ".join(fit.get("lacunas", []))

        row_data = [
            orig_rank,
            resume.get("nome", ""),
            fit_score,
            rec,
            fortes,
            lacunas,
            scores.get("score_geral", 0),
            resume.get("nivel_senioridade", ""),
            r.get("filename", ""),
        ]

        rec_fills = {
            "Avançar":         ("D6FAE8", "007A4C"),
            "Em análise":      ("FFF8E1", "7A4F00"),
            "Não recomendado": ("FFE8E8", "CC2200"),
        }
        row_fill = _fill(_LIGHTBG) if rank % 2 == 0 else _fill(_WHITE)

        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row, column=col_idx, value=value)
            cell.border = _thin_border()
            cell.font   = _font(size=10)
            if col_idx == 3:
                cell.fill = _score_fill(int(fit_score))
                cell.font = _score_font(int(fit_score))
                cell.alignment = _center()
            elif col_idx == 4 and rec in rec_fills:
                bg, fg = rec_fills[rec]
                cell.fill = _fill(bg)
                cell.font = _font(bold=True, size=10, color=fg)
                cell.alignment = _center()
            elif col_idx == 7:
                cell.fill = _score_fill(int(value) if isinstance(value, (int, float)) else 0)
                cell.font = _score_font(int(value) if isinstance(value, (int, float)) else 0)
                cell.alignment = _center()
            elif col_idx == 2:
                cell.fill = row_fill
                cell.font = _font(bold=True, size=10)
                cell.alignment = _left()
            else:
                cell.fill = row_fill
                cell.alignment = _left()
        ws.row_dimensions[row].height = 24

    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(fit_results)+1}"
