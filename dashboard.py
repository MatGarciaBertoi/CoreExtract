"""
BTExtract — Dashboard Streamlit (Cloud Edition)
══════════════════════════════════════════════════════════════════════════════
Versão cloud: autentica via API FastAPI e lê dados por HTTP.
Configuração local  → .streamlit/secrets.toml
Configuração cloud  → Streamlit Cloud > App Settings > Secrets

Secrets necessários:
    API_BASE_URL = "https://SEU-APP.fly.dev"
══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import time
from collections import Counter

import plotly.graph_objects as go
import requests
import streamlit as st

# ── Config página ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BTExtract · Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Cores semânticas ──────────────────────────────────────────────────────────
C_GREEN  = "#00C07A"
C_AMBER  = "#FFB830"
C_RED    = "#FF5757"
C_BLUE   = "#1A6BFF"
C_NAVY   = "#0D1B2A"
C_GRAY   = "#6B7A99"

REC_COLORS = {"Avançar": C_GREEN, "Em análise": C_AMBER, "Não recomendado": C_RED}
REC_ORDER  = ["Avançar", "Em análise", "Não recomendado"]

# ── CSS global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0D1B2A; }
  [data-testid="stHeader"]           { background: transparent; }
  .kpi-card {
    background: #162032; border-radius: 12px; padding: 18px 24px;
    border: 1px solid #1e3050; text-align: center;
  }
  .kpi-label { font-size:12px; color:#6B7A99; text-transform:uppercase;
               letter-spacing:1px; margin-bottom:6px; }
  .kpi-value { font-size:36px; font-weight:800; }
  .section-title {
    font-size:13px; font-weight:700; color:#6B7A99;
    text-transform:uppercase; letter-spacing:2px;
    margin:32px 0 12px; border-bottom:1px solid #1e3050; padding-bottom:8px;
  }
  /* Login card */
  .login-wrap {
    max-width: 400px; margin: 80px auto 0;
    background: #162032; border: 1px solid #1e3050;
    border-radius: 16px; padding: 36px 32px;
  }
  .login-title { font-size:22px; font-weight:800; color:#fff; margin-bottom:4px; }
  .login-sub   { font-size:13px; color:#6B7A99; margin-bottom:28px; }
</style>
""", unsafe_allow_html=True)

# ── API Base URL ───────────────────────────────────────────────────────────────
try:
    API_BASE = st.secrets["API_BASE_URL"].rstrip("/")
except Exception:
    API_BASE = "http://localhost:8080"          # fallback para desenvolvimento local

# ── Session state ──────────────────────────────────────────────────────────────
for _k, _v in [("token", None), ("nome", ""), ("role", ""), ("sessao_id", None)]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Helpers de autenticação ────────────────────────────────────────────────────
def _headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state['token']}"}


def do_login(email: str, senha: str) -> tuple[bool, str]:
    """Autentica na API e armazena o token. Retorna (sucesso, mensagem)."""
    try:
        r = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": email, "senha": senha},
            timeout=12,
        )
        if r.status_code == 200:
            data = r.json()
            st.session_state["token"] = data.get("access_token")
            st.session_state["nome"]  = data.get("nome", "Usuário")
            st.session_state["role"]  = data.get("role", "user")
            return True, ""
        detail = r.json().get("detail", "Credenciais inválidas.")
        return False, detail
    except requests.exceptions.ConnectionError:
        return False, f"Não foi possível conectar à API ({API_BASE}). Verifique a configuração."
    except Exception as exc:
        return False, str(exc)


def do_logout():
    for k in ("token", "nome", "role", "sessao_id"):
        st.session_state[k] = None if k == "token" else ""
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TELA DE LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state["token"]:
    st.markdown("""
    <div style='text-align:center;margin-top:60px;margin-bottom:32px'>
      <div style='font-size:48px'>🧠</div>
      <h1 style='color:#fff;font-size:28px;margin:8px 0 4px'>
        BTExtract <span style='color:#1A6BFF'>Dashboard</span>
      </h1>
      <p style='color:#6B7A99;font-size:14px'>Entre com sua conta BTExtract para ver os resultados</p>
    </div>
    """, unsafe_allow_html=True)

    col_c, col_f, col_c2 = st.columns([1, 2, 1])
    with col_f:
        with st.form("login_form"):
            email = st.text_input("E-mail", placeholder="seu@email.com.br")
            senha = st.text_input("Senha", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Entrar", use_container_width=True)

        if submitted:
            if not email or not senha:
                st.error("Preencha e-mail e senha.")
            else:
                with st.spinner("Autenticando..."):
                    ok, msg = do_login(email.strip(), senha)
                if ok:
                    st.rerun()
                else:
                    st.error(msg or "Credenciais inválidas.")

        st.markdown(
            f"<p style='text-align:center;color:#6B7A99;font-size:12px;margin-top:20px'>"
            f"Acesse o sistema em <a href='{API_BASE}' target='_blank' style='color:#1A6BFF'>"
            f"{API_BASE}</a></p>",
            unsafe_allow_html=True,
        )
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE DADOS
# ══════════════════════════════════════════════════════════════════════════════
def _fit(r):   return (r.get("resume") or {}).get("fit") or {}
def _res(r):   return r.get("resume") or {}
def _habs(r):  return (_res(r).get("habilidades") or {})
def _score(r): return int((_res(r).get("scores") or {}).get("score_geral", 0) or 0)
def _name(r, i): return ((_res(r).get("nome") or r.get("filename", f"C{i+1}"))[:30])

def _agg(ok_list, field, top=12):
    c = Counter()
    for r in ok_list:
        for item in _fit(r).get(field, []):
            item = item.strip()
            if item:
                c[item] += 1
    return c.most_common(top)

def _agg_by_cand(ok_list, field, top=10):
    cand_names = [_name(r, i) for i, r in enumerate(ok_list)]
    skill_counter = Counter()
    for r in ok_list:
        for item in _fit(r).get(field, []):
            item = item.strip()
            if item:
                skill_counter[item] += 1
    top_skills = [s for s, _ in skill_counter.most_common(top)]
    matrix = {}
    for i, r in enumerate(ok_list):
        cand_set = {f.strip() for f in _fit(r).get(field, [])}
        matrix[cand_names[i]] = [1 if s in cand_set else 0 for s in top_skills]
    return top_skills, cand_names, matrix

POOL_STACKED_MAX = 10
CAND_PALETTE = [
    "#1A6BFF", "#00C07A", "#FFB830", "#FF5757",
    "#9B59B6", "#00BCD4", "#FF9800", "#E91E63",
    "#F06292", "#4DB6AC",
]

def plotly_layout(fig, height=340, show_legend=True):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(22,32,50,1)",
        font=dict(color="#A0B4CC", family="Inter, sans-serif", size=12),
        margin=dict(l=10, r=10, t=36, b=10), height=height,
        showlegend=show_legend,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#A0B4CC", size=11)),
        xaxis=dict(gridcolor="#1e3050", zerolinecolor="#1e3050"),
        yaxis=dict(gridcolor="#1e3050", zerolinecolor="#1e3050"),
    )
    return fig

def _stacked_pool_chart(top_skills, cand_names, matrix, title, title_color):
    skills_rev = list(reversed(top_skills))
    fig = go.Figure()
    for j, cname in enumerate(cand_names):
        color = CAND_PALETTE[j % len(CAND_PALETTE)]
        vals_rev = list(reversed(matrix[cname]))
        fig.add_trace(go.Bar(
            name=cname, x=vals_rev, y=skills_rev, orientation="h",
            marker=dict(color=color, line=dict(color="#0D1B2A", width=1)),
            hovertemplate=f"<b>{cname}</b><br>%{{y}}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        title=dict(text=title, font=dict(color=title_color, size=14)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(22,32,50,1)",
        font=dict(color="#A0B4CC", family="Inter, sans-serif", size=12),
        legend=dict(bgcolor="rgba(13,27,42,0.85)", font=dict(color="#A0B4CC", size=10),
                    bordercolor="#1e3050", borderwidth=1, orientation="v", x=1.01, y=1),
        xaxis=dict(gridcolor="#1e3050", zerolinecolor="#1e3050",
                   title_text="Nº de Candidatos", title_font=dict(color=C_GRAY),
                   tickfont=dict(color=C_GRAY), tickmode="linear", dtick=1),
        yaxis=dict(gridcolor="#1e3050", zerolinecolor="#1e3050", tickfont=dict(color="#A0B4CC")),
        height=max(340, len(top_skills) * 42),
        margin=dict(l=10, r=160, t=44, b=10),
    )
    return fig

def _heatmap_pool_chart(top_skills, cand_names, matrix, title, title_color, cell_color):
    z = [[matrix[c][i] for c in cand_names] for i in range(len(top_skills))]
    hover = [
        [f"<b>{cand_names[j]}</b><br>{top_skills[i]}" if z[i][j] else
         f"<span style='color:#555'>{cand_names[j]}</span><br>—"
         for j in range(len(cand_names))]
        for i in range(len(top_skills))
    ]
    fig = go.Figure(go.Heatmap(
        z=z, x=cand_names, y=top_skills,
        colorscale=[[0, "rgba(30,48,80,0.5)"], [1, cell_color]],
        showscale=False, xgap=3, ygap=3,
        hoverinfo="text", text=hover, hovertemplate="%{text}<extra></extra>",
    ))
    tick_angle  = -45 if len(cand_names) > 15 else 0
    label_height = 80 if len(cand_names) > 15 else 20
    fig.update_layout(
        title=dict(text=title, font=dict(color=title_color, size=14)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(22,32,50,1)",
        font=dict(color="#A0B4CC", family="Inter, sans-serif", size=11),
        xaxis=dict(tickangle=tick_angle, tickfont=dict(color="#A0B4CC", size=10),
                   side="bottom", gridcolor="#1e3050"),
        yaxis=dict(tickfont=dict(color="#A0B4CC", size=11), autorange="reversed",
                   gridcolor="#1e3050"),
        height=max(340, len(top_skills) * 36 + label_height),
        margin=dict(l=10, r=10, t=44, b=label_height),
    )
    return fig

def _render_pool_section(ok_list, field, title_stack, title_heat, title_color, cell_color):
    top_skills, cand_names, matrix = _agg_by_cand(ok_list, field, top=10)
    if not top_skills:
        return False
    if len(cand_names) <= POOL_STACKED_MAX:
        fig = _stacked_pool_chart(top_skills, cand_names, matrix, title_stack, title_color)
    else:
        fig = _heatmap_pool_chart(top_skills, cand_names, matrix, title_heat, title_color, cell_color)
    st.plotly_chart(fig, use_container_width=True)
    return True


# ══════════════════════════════════════════════════════════════════════════════
# CARGA DE DADOS — via API
# ══════════════════════════════════════════════════════════════════════════════
def _load_session(sessao_id: int | None = None) -> dict | None:
    """
    Carrega sessão da API.
    sessao_id=None → última sessão.
    Retorna None em caso de erro ou sessão inexistente.
    """
    try:
        if sessao_id:
            url = f"{API_BASE}/dashboard/sessoes/{sessao_id}"
        else:
            url = f"{API_BASE}/dashboard/ultima-sessao"
        r = requests.get(url, headers=_headers(), timeout=15)
        if r.status_code == 401:
            # Token expirado — força novo login
            st.session_state["token"] = None
            st.rerun()
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def _load_history() -> list[dict]:
    """Lista as sessões recentes para o seletor de histórico."""
    try:
        r = requests.get(f"{API_BASE}/dashboard/sessoes?limit=30",
                         headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — histórico + logout
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"<div style='color:#fff;font-weight:700;font-size:15px'>🧠 BTExtract</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div style='color:#6B7A99;font-size:12px;margin-bottom:16px'>"
                f"Olá, {st.session_state['nome']}</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<div style='color:#6B7A99;font-size:11px;text-transform:uppercase;"
                "letter-spacing:1px;margin-bottom:8px'>Histórico de Triagens</div>",
                unsafe_allow_html=True)

    historico = _load_history()
    if historico:
        opcoes = {
            f"#{h['id']} · {h['tema'][:30]} · {h['timestamp'][:10]}": h["id"]
            for h in historico
        }
        escolha = st.selectbox(
            "Selecione uma triagem",
            options=["Mais recente"] + list(opcoes.keys()),
            label_visibility="collapsed",
        )
        if escolha == "Mais recente":
            st.session_state["sessao_id"] = None
        else:
            st.session_state["sessao_id"] = opcoes[escolha]
    else:
        st.caption("Nenhuma triagem encontrada.")

    st.markdown("---")
    if st.button("🚪 Sair", use_container_width=True):
        do_logout()

    st.markdown(
        f"<div style='color:#2a3a55;font-size:10px;margin-top:16px'>"
        f"API: {API_BASE}</div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# RENDER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
session = _load_session(st.session_state.get("sessao_id"))

# ── Cabeçalho ─────────────────────────────────────────────────────────────────
col_logo, col_title, col_refresh = st.columns([1, 8, 2])
with col_logo:
    st.markdown("<div style='font-size:40px;padding-top:8px'>🧠</div>", unsafe_allow_html=True)
with col_title:
    st.markdown(
        "<h1 style='color:#FFFFFF;margin:0;font-size:28px'>BTExtract "
        "<span style=\"color:#1A6BFF\">Dashboard</span></h1>",
        unsafe_allow_html=True,
    )
    if session:
        ts   = session.get("timestamp", "")
        tema = session.get("tema", "Triagem Geral")
        st.markdown(
            f"<p style='color:#6B7A99;margin:0;font-size:13px'>"
            f"📋 {tema[:80]}  ·  🕐 {ts[:16].replace('T',' ')}</p>",
            unsafe_allow_html=True,
        )
with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄  Atualizar", use_container_width=True):
        st.rerun()

st.markdown("<hr style='border-color:#1e3050;margin:12px 0 20px'>", unsafe_allow_html=True)

# ── Sem dados ─────────────────────────────────────────────────────────────────
if not session:
    st.markdown(f"""
    <div style='text-align:center;padding:80px 0;color:#6B7A99'>
      <div style='font-size:56px'>📂</div>
      <h3 style='color:#A0B4CC;margin:16px 0 8px'>Nenhuma análise encontrada</h3>
      <p>Processe currículos no
        <a href='{API_BASE}' target='_blank' style='color:#1A6BFF'>BTExtract</a>
        e volte aqui para ver o dashboard.
      </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

ok      = [r for r in (session.get("results") or []) if r.get("status") == "ok"]
has_fit = any(_fit(r).get("recomendacao") for r in ok)

if not ok:
    st.warning("Nenhum currículo processado com sucesso nesta sessão.")
    st.stop()

total   = len(ok)
rec_c   = Counter(_fit(r).get("recomendacao", "") for r in ok if has_fit)
avg_sc  = round(sum(_score(r) for r in ok) / total) if total else 0
pct_av  = round(rec_c.get("Avançar", 0) / total * 100) if total else 0
pct_rej = round(rec_c.get("Não recomendado", 0) / total * 100) if total else 0
avg_lac = round(sum(len(_fit(r).get("lacunas", [])) for r in ok) / total, 1) if total else 0

# ── KPI Cards ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)

def kpi(col, label, value, color):
    col.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value" style="color:{color}">{value}</div>
    </div>""", unsafe_allow_html=True)

kpi(k1, "Score Médio",         avg_sc,         C_BLUE)
kpi(k2, "Total Candidatos",    total,           "#FFFFFF")
kpi(k3, "% Avançar",           f"{pct_av}%",    C_GREEN)
kpi(k4, "% Rejeitados",        f"{pct_rej}%",   C_RED)
kpi(k5, "Lacunas / Candidato", avg_lac,         C_AMBER)

# ── Visão Geral: Donut + Ranking ─────────────────────────────────────────────
if has_fit:
    st.markdown("<div class='section-title'>Visão Geral</div>", unsafe_allow_html=True)
    col_pie, col_rank = st.columns([2, 3])

    with col_pie:
        labels = [r for r in REC_ORDER if rec_c.get(r, 0) > 0]
        values = [rec_c[r] for r in labels]
        colors = [REC_COLORS[r] for r in labels]
        fig_pie = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.55,
            marker=dict(colors=colors, line=dict(color="#0D1B2A", width=3)),
            textinfo="label+percent",
            textfont=dict(color="#FFFFFF", size=13),
            hovertemplate="%{label}: %{value} candidato(s)<extra></extra>",
        ))
        fig_pie.update_layout(
            title=dict(text="Distribuição de Recomendação", font=dict(color="#A0B4CC", size=14)),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#A0B4CC"), showlegend=True,
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#A0B4CC")),
            height=300, margin=dict(l=0, r=0, t=40, b=0),
            annotations=[dict(text=f"<b>{total}</b><br>candidatos", x=0.5, y=0.5,
                              font=dict(size=14, color="#FFFFFF"), showarrow=False)],
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_rank:
        sorted_sc = sorted(
            [(_name(r, i), _score(r), _fit(r).get("recomendacao", "")) for i, r in enumerate(ok)],
            key=lambda x: x[1],
        )
        bar_colors = [REC_COLORS.get(rec, C_BLUE) for _, _, rec in sorted_sc]
        names  = [x[0] for x in sorted_sc]
        scores = [x[1] for x in sorted_sc]
        recs   = [x[2] for x in sorted_sc]
        fig_rank = go.Figure(go.Bar(
            x=scores, y=names, orientation="h",
            marker=dict(color=bar_colors, line=dict(color="#0D1B2A", width=1)),
            text=scores, textposition="outside",
            textfont=dict(color="#A0B4CC", size=11),
            hovertemplate="<b>%{y}</b><br>Score: %{x}<br>%{customdata}<extra></extra>",
            customdata=recs,
        ))
        fig_rank.update_xaxes(range=[0, 110], title_text="Score (0–100)",
                               title_font=dict(color=C_GRAY), tickfont=dict(color=C_GRAY))
        fig_rank.update_yaxes(tickfont=dict(color="#A0B4CC"))
        h_rank = max(300, len(ok) * 50)
        plotly_layout(fig_rank, height=h_rank, show_legend=False)
        fig_rank.update_layout(
            title=dict(text="Ranking por Score", font=dict(color="#A0B4CC", size=14)),
            plot_bgcolor="rgba(22,32,50,1)",
        )
        st.plotly_chart(fig_rank, use_container_width=True)

# ── Pontos Fortes + Lacunas ───────────────────────────────────────────────────
st.markdown("<div class='section-title'>Análise do Pool</div>", unsafe_allow_html=True)
col_pf, col_lac = st.columns(2)

with col_pf:
    had = _render_pool_section(
        ok, "pontos_fortes",
        title_stack="✅  Pontos Fortes por Candidato",
        title_heat= "✅  Pontos Fortes — Mapa de Presença",
        title_color=C_GREEN, cell_color=C_GREEN,
    )
    if not had:
        st.info("Sem pontos fortes registrados.")

with col_lac:
    had = _render_pool_section(
        ok, "lacunas",
        title_stack="⚠️  Lacunas por Candidato",
        title_heat= "⚠️  Lacunas — Mapa de Presença",
        title_color=C_RED, cell_color=C_RED,
    )
    if not had:
        st.info("Sem lacunas registradas.")

# ── Senioridade × Recomendação ────────────────────────────────────────────────
if has_fit:
    st.markdown("<div class='section-title'>Senioridade × Recomendação</div>", unsafe_allow_html=True)
    nivel_order = ["Especialista", "Sênior", "Pleno", "Júnior", "Indefinido"]
    xtab = {n: {rec: 0 for rec in REC_ORDER} for n in nivel_order}
    for r in ok:
        nivel = _res(r).get("nivel_senioridade") or "Indefinido"
        if nivel not in xtab:
            nivel = "Indefinido"
        rec = _fit(r).get("recomendacao", "")
        if rec in REC_ORDER:
            xtab[nivel][rec] += 1
    active = [n for n in nivel_order if sum(xtab[n].values()) > 0]
    if active:
        fig_stk = go.Figure()
        for rec, color in [(r, REC_COLORS[r]) for r in REC_ORDER]:
            vals = [xtab[n][rec] for n in active]
            fig_stk.add_trace(go.Bar(
                name=rec, x=active, y=vals, marker_color=color,
                hovertemplate=f"{rec}: %{{y}} candidato(s)<extra></extra>",
                text=vals, textposition="inside",
                textfont=dict(color="#FFFFFF", size=12),
            ))
        fig_stk.update_layout(
            barmode="stack",
            title=dict(text="Distribuição de Recomendação por Nível de Senioridade",
                       font=dict(color="#A0B4CC", size=14)),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(22,32,50,1)",
            font=dict(color="#A0B4CC"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#A0B4CC"),
                        orientation="h", yanchor="bottom", y=1.02),
            xaxis=dict(gridcolor="#1e3050"),
            yaxis=dict(gridcolor="#1e3050", title="Candidatos"),
            height=300, margin=dict(l=10, r=10, t=60, b=10),
        )
        st.plotly_chart(fig_stk, use_container_width=True)

# ── Matriz Candidato × Competências ──────────────────────────────────────────
if has_fit:
    top_skills = [item for item, _ in _agg(ok, "pontos_fortes", top=10)]
    if top_skills:
        st.markdown("<div class='section-title'>Matriz Candidato × Competências</div>",
                    unsafe_allow_html=True)
        import pandas as pd
        sorted_ok = sorted(ok, key=lambda r: (
            REC_ORDER.index(_fit(r).get("recomendacao", "Não recomendado")
                            if _fit(r).get("recomendacao") in REC_ORDER
                            else "Não recomendado"),
            -_score(r),
        ))
        matrix_rows = []
        for i, r in enumerate(sorted_ok):
            cand_set = {f.strip() for f in _fit(r).get("pontos_fortes", [])}
            rec = _fit(r).get("recomendacao", "")
            row = {"Candidato": _name(r, i), "Score": _score(r), "Recomendação": rec}
            for skill in top_skills:
                row[skill] = "✓" if skill in cand_set else ""
            matrix_rows.append(row)

        df = pd.DataFrame(matrix_rows)
        skill_cols = [c for c in df.columns if c not in ("Candidato", "Score", "Recomendação")]

        def style_rec(val):
            return {"Avançar": "background:#1a4a2e;color:#00C07A;font-weight:700",
                    "Em análise": "background:#3d2e00;color:#FFB830;font-weight:700",
                    "Não recomendado": "background:#4a1a1a;color:#FF5757;font-weight:700"}.get(val, "")

        def style_check(val):
            return "color:#00C07A;font-weight:800;font-size:16px" if val == "✓" else "color:#1e3050"

        styled = (df.style
                    .applymap(style_rec, subset=["Recomendação"])
                    .applymap(style_check, subset=skill_cols)
                    .set_properties(**{"background-color": "#162032", "color": "#A0B4CC",
                                       "border": "1px solid #1e3050"})
                    .set_table_styles([
                        {"selector": "th", "props": [
                            ("background-color", "#0D1B2A"), ("color", "#6B7A99"),
                            ("font-weight", "600"), ("font-size", "11px"),
                            ("white-space", "normal"), ("word-break", "break-word"),
                            ("min-width", "140px"), ("text-align", "center")]},
                        {"selector": "td", "props": [
                            ("white-space", "normal"), ("word-break", "break-word"),
                            ("min-width", "140px"), ("text-align", "center")]},
                    ]))
        col_cfg = {
            "Candidato":    st.column_config.TextColumn("Candidato",    width="medium"),
            "Score":        st.column_config.NumberColumn("Score",      width="small"),
            "Recomendação": st.column_config.TextColumn("Recomendação", width="medium"),
        }
        for skill in skill_cols:
            col_cfg[skill] = st.column_config.TextColumn(skill, width="medium")
        st.dataframe(styled, use_container_width=True, hide_index=True, column_config=col_cfg)

# ── Tabela Detalhada ──────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>Tabela de Candidatos</div>", unsafe_allow_html=True)
import pandas as pd

rows = []
for i, r in enumerate(ok):
    res = _res(r); fit = _fit(r); hb = _habs(r)
    rows.append({
        "Nome":          _name(r, i),
        "Score":         _score(r),
        "Recomendação":  fit.get("recomendacao", "—") if has_fit else "—",
        "Nível":         res.get("nivel_senioridade", "—"),
        "Área":          res.get("area_atuacao", "—"),
        "Exp.(anos)":    res.get("anos_experiencia_estimados", "—"),
        "Habilidades":   ", ".join(hb.get("tecnicas", [])[:5]),
        "Pontos Fortes": " · ".join(fit.get("pontos_fortes", [])[:3]) if has_fit else "—",
        "Lacunas":       " · ".join(fit.get("lacunas", [])[:3]) if has_fit else "—",
        "Arquivo":       r.get("filename", ""),
    })

df_cands = pd.DataFrame(rows).sort_values("Score", ascending=False)

def color_rec_row(row):
    pal = {"Avançar": "#1a4a2e", "Em análise": "#3d2e00", "Não recomendado": "#4a1a1a"}
    bg = pal.get(row.get("Recomendação", ""), "#162032")
    return [f"background-color:{bg};color:#A0B4CC"] * len(row)

st.dataframe(
    df_cands.style
        .apply(color_rec_row, axis=1)
        .set_properties(**{"border": "1px solid #1e3050"})
        .set_table_styles([{"selector": "th", "props": [
            ("background-color", "#0D1B2A"), ("color", "#6B7A99")]}]),
    use_container_width=True,
    hide_index=True,
    height=min(600, 80 + len(rows) * 50),
)

# ── Rodapé ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center;color:#2a3a55;font-size:11px;margin-top:40px;
             border-top:1px solid #1e3050;padding-top:16px'>
  BTExtract Dashboard · Bertoi Informática ·
  Dados de: {session.get("timestamp","—")[:16].replace("T"," ")}
</div>
""", unsafe_allow_html=True)
