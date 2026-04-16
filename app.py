"""
Simulador de Impacto — Reforma da Escala 6×1 no Brasil
Desenvolvido com Streamlit + Plotly
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from data.dados import (
    CENARIOS, SETORES, REGIOES, PORTES, ESTADOS_VULN,
    MATRIZ_IMPACTO, INTL, QA_ITEMS,
    monte_carlo, estimar_custo_pme,
)

# ── Configuração da página
st.set_page_config(
    page_title="Simulador Reforma 6×1 · Brasil",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS customizado
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

    .metric-container {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 14px 16px;
        border-left: 3px solid #185FA5;
        margin-bottom: 8px;
    }
    .metric-label { font-size: 11px; color: #666; letter-spacing: .05em; text-transform: uppercase; }
    .metric-value { font-size: 22px; font-weight: 600; margin: 4px 0 2px; }
    .metric-range { font-size: 11px; color: #999; }
    .tag-high   { background:#FAECE7; color:#712B13; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
    .tag-med    { background:#FAEEDA; color:#633806; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
    .tag-low    { background:#EAF3DE; color:#27500A; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
    .intl-card  { background:#f8f9fa; border-radius:8px; padding:14px; margin-bottom:8px; border-top:2px solid #185FA5; }
    .qa-answer  { background:#f0f4ff; border-left:3px solid #185FA5; padding:12px 16px; border-radius:0 8px 8px 0; margin-top:4px; font-size:14px; line-height:1.7; }
    div[data-testid="stExpander"] > div { border: none !important; }
    .stTabs [data-baseweb="tab"] { font-size: 14px; font-weight: 500; }
    .scenario-cons { border-left: 4px solid #185FA5 !important; }
    .scenario-mod  { border-left: 4px solid #3B6D11 !important; }
    .scenario-trans{ border-left: 4px solid #993C1D !important; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# SIDEBAR — filtros principais
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚖️ Simulador 6×1")
    st.caption("Análise econométrica da reforma da jornada de trabalho no Brasil")
    st.divider()

    cenario_sel = st.selectbox(
        "**Cenário de transição**",
        options=list(CENARIOS.keys()),
        help="Define o modelo e o ritmo da transição"
    )
    scn = CENARIOS[cenario_sel]
    cor_scn = scn["cor"]

    st.markdown(f"""
    <div style="background:#f8f9fa;border-radius:8px;padding:10px;border-left:3px solid {cor_scn};margin:8px 0">
    <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.05em">Modelo</div>
    <div style="font-weight:600;margin:2px 0">{scn['modelo']}</div>
    <div style="font-size:12px;color:#555">{scn['descricao']}</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    setor_sel = st.selectbox("**Setor econômico**", options=list(SETORES.keys()))
    regiao_sel = st.selectbox("**Região**", options=list(REGIOES.keys()))
    porte_sel = st.selectbox("**Porte da empresa**", options=list(PORTES.keys()))

    st.divider()
    n_sim = st.slider("Iterações Monte Carlo", 1_000, 50_000, 10_000, step=1_000,
                      help="Mais iterações = maior precisão dos intervalos de confiança")

    st.divider()
    st.caption("Dados: PNAD Contínua, RAIS/MTE, IBGE (2015–2023)")
    st.caption("Evidências internacionais: França, Islândia, Japão, Dinamarca, Alemanha")


# ── Executar Monte Carlo com os parâmetros selecionados
@st.cache_data(show_spinner=False)
def rodar_mc(cenario, setor, regiao, porte, n):
    return monte_carlo(cenario, setor, regiao, porte, n)

with st.spinner("Simulando cenário..."):
    resultados = rodar_mc(cenario_sel, setor_sel, regiao_sel, porte_sel, n_sim)

sec = SETORES[setor_sel]
reg = REGIOES[regiao_sel]


# ═══════════════════════════════════════════════════════════
# CABEÇALHO
# ═══════════════════════════════════════════════════════════
st.markdown(f"""
<h1 style="font-size:26px;font-weight:600;margin-bottom:4px">
  Reforma da Escala 6×1 — Simulador de Impacto Econômico
</h1>
<p style="color:#666;font-size:14px;margin-bottom:0">
  Cenário: <strong style="color:{cor_scn}">{cenario_sel}</strong> ·
  {setor_sel} · {regiao_sel} · {porte_sel} ·
  <span style="font-family:monospace">{n_sim:,} simulações Monte Carlo</span>
</p>
""", unsafe_allow_html=True)
st.divider()


# ═══════════════════════════════════════════════════════════
# TABS PRINCIPAIS
# ═══════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Indicadores",
    "🗺️ Análise Setorial e Regional",
    "🌍 Comparações Internacionais",
    "🏢 Calculadora PME",
    "❓ Perguntas Guiadas",
])


# ─────────────────────────────────────────────────────────
# TAB 1 — INDICADORES PRINCIPAIS
# ─────────────────────────────────────────────────────────
with tab1:
    st.markdown("#### Estimativas com intervalo de confiança 80% (Monte Carlo)")

    c1, c2, c3, c4 = st.columns(4)

    def fmt_range(lo, mid, hi, suffix="%", prefix=""):
        return f"{prefix}{lo:.1f}{suffix} — {prefix}{hi:.1f}{suffix}"

    custo_lo, custo_mid, custo_hi = resultados["custo"]
    emp_lo, emp_mid, emp_hi = resultados["emprego"]
    prod_lo, prod_mid, prod_hi = resultados["produtividade"]
    fiscal_lo, fiscal_mid, fiscal_hi = resultados["fiscal"]

    with c1:
        delta_color = "inverse" if custo_mid > 15 else "normal"
        st.metric(
            "Custo laboral adicional",
            f"+{custo_mid:.1f}%",
            f"IC 80%: +{custo_lo:.1f}% a +{custo_hi:.1f}%",
            delta_color="inverse",
        )
    with c2:
        st.metric(
            "Variação emprego formal",
            f"{emp_mid:+.1f}%",
            f"IC 80%: {emp_lo:+.1f}% a {emp_hi:+.1f}%",
            delta_color="normal" if emp_mid > 0 else "inverse",
        )
    with c3:
        st.metric(
            "Produtividade por hora",
            f"+{prod_mid:.1f}%",
            f"IC 80%: +{prod_lo:.1f}% a +{prod_hi:.1f}%",
            delta_color="normal",
        )
    with c4:
        sinal = "+" if fiscal_mid > 0 else ""
        st.metric(
            "Impacto fiscal (INSS+FGTS)",
            f"R$ {fiscal_mid:.1f} bi/ano",
            f"IC 80%: R$ {fiscal_lo:.1f}bi a R$ {fiscal_hi:.1f}bi",
            delta_color="normal" if fiscal_mid > 0 else "inverse",
        )

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("##### Distribuição — custo laboral adicional")
        rng_obj = np.random.default_rng(42)
        custo_sim_plot = rng_obj.lognormal(
            np.log(max(custo_mid, 1)), max((custo_hi - custo_lo) / (4 * custo_mid), 0.05), n_sim
        )
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=custo_sim_plot,
            nbinsx=60,
            marker_color=cor_scn,
            opacity=0.75,
            name="Simulações",
        ))
        fig_hist.add_vline(x=custo_mid, line_dash="dash", line_color="#333",
                           annotation_text=f"Mediana {custo_mid:.1f}%")
        fig_hist.add_vrect(x0=custo_lo, x1=custo_hi, fillcolor=cor_scn, opacity=0.08,
                           annotation_text="IC 80%", annotation_position="top left")
        fig_hist.update_layout(
            xaxis_title="Variação % no custo laboral",
            yaxis_title="Frequência",
            showlegend=False,
            height=280,
            margin=dict(l=0, r=0, t=20, b=40),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_hist.update_xaxes(showgrid=True, gridcolor="#eee")
        fig_hist.update_yaxes(showgrid=True, gridcolor="#eee")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_b:
        st.markdown("##### Comparativo entre cenários — indicadores-chave")
        cenarios_nomes = list(CENARIOS.keys())
        indicadores = ["Custo laboral", "Produtividade/hora", "Consumo interno"]
        dados_comp = {
            "Conservador": [10, 4.5, 2.0],
            "Moderado":     [15, 6.5, 3.5],
            "Transformador":[26, 9.0, 5.5],
        }
        fig_radar = go.Figure()
        cores = ["#185FA5", "#3B6D11", "#993C1D"]
        for i, (nome, vals) in enumerate(dados_comp.items()):
            fig_radar.add_trace(go.Bar(
                name=nome,
                x=indicadores,
                y=vals,
                marker_color=cores[i],
                opacity=0.8,
            ))
        fig_radar.update_layout(
            barmode="group",
            height=280,
            margin=dict(l=0, r=0, t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="Variação estimada (%)",
        )
        fig_radar.update_xaxes(showgrid=False)
        fig_radar.update_yaxes(showgrid=True, gridcolor="#eee")
        st.plotly_chart(fig_radar, use_container_width=True)

    st.divider()
    st.markdown("##### Trade-offs centrais para formuladores de política")
    col_pro, col_con = st.columns(2)
    with col_pro:
        st.success("""
**Argumentos pró-reforma**
- Bem-estar e saúde dos trabalhadores
- Produtividade por hora (evidência internacional)
- Redução de acidentes e afastamentos
- Consumo interno (mais tempo livre)
- Alinhamento com padrões OCDE
- Redistribuição do tempo social
        """)
    with col_con:
        st.error("""
**Riscos e custos**
- Aumento do custo do trabalho formal
- Pressão sobre MEI e PMEs intensivas em mão de obra
- Risco de migração para informalidade
- Impacto fiscal no curto prazo (INSS/FGTS)
- Assimetria regional: Norte/NE mais expostos
- Resistência setorial (varejo, alimentos, segurança)
        """)


# ─────────────────────────────────────────────────────────
# TAB 2 — ANÁLISE SETORIAL E REGIONAL
# ─────────────────────────────────────────────────────────
with tab2:
    col_set, col_reg = st.columns(2)

    with col_set:
        st.markdown("#### Vulnerabilidade setorial (índice 0–10)")
        setores_plot = {k: v for k, v in SETORES.items() if k != "Todos os setores"}
        df_set = pd.DataFrame([
            {"Setor": k, "Vulnerabilidade": v["vuln"], "Trabalhadores": v["workers_n"] / 1e6}
            for k, v in setores_plot.items()
        ]).sort_values("Vulnerabilidade", ascending=True)

        cores_set = {
            "Varejo": "#D85A30", "Saúde": "#185FA5",
            "Alimentação / Restaurantes": "#993C1D",
            "Transporte e Logística": "#BA7517",
            "Indústria": "#3B6D11", "Segurança Privada": "#712B13",
            "Limpeza e Conservação": "#854F0B", "Tecnologia (TI)": "#0F6E56",
        }
        fig_set = go.Figure(go.Bar(
            x=df_set["Vulnerabilidade"],
            y=df_set["Setor"],
            orientation="h",
            marker_color=[cores_set.get(s, "#888") for s in df_set["Setor"]],
            text=df_set["Vulnerabilidade"].apply(lambda x: f"{x:.1f}"),
            textposition="outside",
            customdata=df_set["Trabalhadores"],
            hovertemplate="%{y}<br>Vulnerabilidade: %{x:.1f}<br>Trabalhadores: %{customdata:.1f}M<extra></extra>",
        ))
        fig_set.update_layout(
            xaxis=dict(range=[0, 11], title="Índice de vulnerabilidade"),
            height=340,
            margin=dict(l=0, r=60, t=10, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_set.update_xaxes(showgrid=True, gridcolor="#eee")
        fig_set.update_yaxes(showgrid=False)
        st.plotly_chart(fig_set, use_container_width=True)

    with col_reg:
        st.markdown("#### Exposição regional ao impacto")
        df_reg = pd.DataFrame([
            {"Região": k, "Exposição": v["exposure"]}
            for k, v in REGIOES.items() if k != "Brasil (agregado)"
        ]).sort_values("Exposição", ascending=True)

        cores_reg = {
            "Norte": "#D85A30", "Nordeste": "#BA7517",
            "Centro-Oeste": "#185FA5", "Sudeste": "#3B6D11", "Sul": "#1D9E75",
        }
        fig_reg = go.Figure(go.Bar(
            x=df_reg["Exposição"],
            y=df_reg["Região"],
            orientation="h",
            marker_color=[cores_reg.get(r, "#888") for r in df_reg["Região"]],
            text=df_reg["Exposição"].apply(lambda x: f"{x:.1f}"),
            textposition="outside",
        ))
        fig_reg.update_layout(
            xaxis=dict(range=[0, 11], title="Índice de exposição"),
            height=240,
            margin=dict(l=0, r=60, t=10, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_reg.update_xaxes(showgrid=True, gridcolor="#eee")
        fig_reg.update_yaxes(showgrid=False)
        st.plotly_chart(fig_reg, use_container_width=True)

    st.divider()
    st.markdown("#### Mapa de vulnerabilidade por estado")
    df_estados = pd.DataFrame([
        {"Estado": k, "Vulnerabilidade": v, "Sigla": k}
        for k, v in ESTADOS_VULN.items()
    ])
    fig_map = px.choropleth(
        df_estados,
        geojson="https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson",
        locations="Sigla",
        featureidkey="properties.sigla",
        color="Vulnerabilidade",
        color_continuous_scale=["#EAF3DE", "#FAEEDA", "#FAECE7", "#D85A30", "#712B13"],
        range_color=[3, 10],
        hover_name="Estado",
        labels={"Vulnerabilidade": "Índice"},
    )
    fig_map.update_geos(
        fitbounds="locations", visible=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig_map.update_layout(
        height=420,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(title="Vuln.", len=0.6),
    )
    st.plotly_chart(fig_map, use_container_width=True)
    st.caption("Fonte: estimativas baseadas em PNAD Contínua, RAIS e IBGE 2015–2023. Vulnerabilidade = composição setorial + informalidade + produtividade média estadual.")

    st.divider()
    st.markdown("#### Matriz de impacto setorial × porte da empresa")
    df_matriz = pd.DataFrame(MATRIZ_IMPACTO)

    def colorir_cel(val):
        if val in ("Muito alta", "Muito alto"):
            return "background-color: #FAECE7; color: #712B13; font-weight: 600"
        elif val in ("Alta", "Alto", "Médio"):
            return "background-color: #FAEEDA; color: #633806; font-weight: 600"
        elif val in ("Baixa", "Baixo"):
            return "background-color: #EAF3DE; color: #27500A; font-weight: 600"
        elif val == "Muito baixa" or val == "Muito baixo":
            return "background-color: #E6F1FB; color: #0C447C; font-weight: 600"
        return ""

    styled = df_matriz.rename(columns={
        "setor": "Setor", "mei": "MEI / Micro", "pme": "PME",
        "grande": "Grande empresa", "workers": "Trabalhadores 6×1", "inform": "Risco informalização"
    }).style.applymap(colorir_cel, subset=["MEI / Micro", "PME", "Grande empresa", "Risco informalização"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────
# TAB 3 — COMPARAÇÕES INTERNACIONAIS
# ─────────────────────────────────────────────────────────
with tab3:
    st.markdown("#### Experiências internacionais com redução de jornada")
    st.caption("Países que realizaram transições similares e seus resultados documentados")

    for item in INTL:
        with st.container():
            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 1.2])
            with c1:
                st.markdown(f"**{item['flag']} {item['pais']}** — {item['politica']}")
                st.caption(item["obs"])
            with c2:
                st.metric("Produtividade/hora", item["prod_hora"])
            with c3:
                st.metric("Emprego", item["emprego"])
            with c4:
                st.metric("Custo laboral", item["custo"])
            st.divider()

    st.markdown("#### Posicionamento do Brasil vs. OCDE")
    dados_ocde = {
        "País": ["Islândia", "Dinamarca", "Alemanha", "França", "Japão", "Brasil (atual)", "Brasil (5×2)", "Brasil (4×3)"],
        "Horas/semana (média)": [36, 37, 34, 35, 38, 44, 40, 36],
        "Produtividade PIB/hora (USD)": [82, 79, 65, 67, 45, 18, 21, 24],
        "Tipo": ["Referência","Referência","Referência","Referência","Referência","Atual","Projeção","Projeção"],
    }
    df_ocde = pd.DataFrame(dados_ocde)
    cores_tipo = {"Referência": "#185FA5", "Atual": "#D85A30", "Projeção": "#3B6D11"}
    fig_ocde = px.scatter(
        df_ocde,
        x="Horas/semana (média)",
        y="Produtividade PIB/hora (USD)",
        text="País",
        color="Tipo",
        color_discrete_map=cores_tipo,
        size_max=14,
    )
    fig_ocde.update_traces(textposition="top center", marker_size=12)
    fig_ocde.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title="",
    )
    fig_ocde.update_xaxes(showgrid=True, gridcolor="#eee", range=[32, 47])
    fig_ocde.update_yaxes(showgrid=True, gridcolor="#eee")
    st.plotly_chart(fig_ocde, use_container_width=True)
    st.caption("Projeções Brasil baseadas em ganhos médios de produtividade observados nos países de referência, ajustados ao contexto econômico brasileiro. Fonte: OCDE, ILO, estimativas próprias.")


# ─────────────────────────────────────────────────────────
# TAB 4 — CALCULADORA PME
# ─────────────────────────────────────────────────────────
with tab4:
    st.markdown("#### Calculadora de impacto para sua empresa")
    st.caption("Estime o custo adicional mensal da transição para um perfil específico de empresa.")

    col_i1, col_i2, col_i3 = st.columns(3)
    with col_i1:
        n_func = st.number_input("Número de funcionários em 6×1", min_value=1, max_value=10000, value=50, step=1)
    with col_i2:
        setor_calc = st.selectbox("Setor da empresa", options=[s for s in SETORES if s != "Todos os setores"], key="setor_calc")
    with col_i3:
        cenario_calc = st.selectbox("Cenário", options=list(CENARIOS.keys()), key="cenario_calc")

    sal_medio = SETORES[setor_calc]["salario_medio"]
    salario_input = st.slider(
        f"Salário médio (R$/mês) — referência setorial: R${sal_medio:,.0f}",
        min_value=1320, max_value=15000, value=sal_medio, step=100,
    )

    resultado_pme = estimar_custo_pme(n_func, salario_input, cenario_calc, setor_calc)

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Folha atual (c/ encargos)",
            f"R$ {resultado_pme['folha_atual']:,.0f}/mês",
        )
    with c2:
        st.metric(
            "Custo adicional estimado",
            f"R$ {resultado_pme['custo_adicional_lo']:,.0f} — R$ {resultado_pme['custo_adicional_hi']:,.0f}/mês",
            delta=f"+{resultado_pme['custo_adicional_hi']/resultado_pme['folha_atual']*100:.1f}% (máx.)",
            delta_color="inverse",
        )
    with c3:
        st.metric(
            "Contratações adicionais necessárias",
            f"{resultado_pme['extra_func_lo']} — {resultado_pme['extra_func_hi']} funcionários",
            help="Para manter a mesma cobertura operacional",
        )

    st.divider()
    st.markdown("##### Impacto acumulado ao longo da transição")
    anos = list(range(1, CENARIOS[cenario_calc]["horizonte"] + 3))
    custo_anual_lo = resultado_pme["custo_adicional_lo"] * 12
    custo_anual_hi = resultado_pme["custo_adicional_hi"] * 12
    horizonte = CENARIOS[cenario_calc]["horizonte"]

    custo_acum_lo = [custo_anual_lo * min(a, horizonte) / horizonte * a for a in anos]
    custo_acum_hi = [custo_anual_hi * min(a, horizonte) / horizonte * a for a in anos]

    fig_acum = go.Figure()
    fig_acum.add_trace(go.Scatter(
        x=anos, y=custo_acum_hi,
        fill=None, line_color=cor_scn, name="Limite superior",
    ))
    fig_acum.add_trace(go.Scatter(
        x=anos, y=custo_acum_lo,
        fill="tonexty", line_color=cor_scn, opacity=0.3,
        fillcolor=cor_scn + "33", name="Limite inferior",
    ))
    fig_acum.update_layout(
        xaxis_title="Ano de transição",
        yaxis_title="Custo acumulado (R$)",
        height=260,
        margin=dict(l=0, r=0, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h"),
        yaxis_tickformat=",.0f",
    )
    fig_acum.update_xaxes(showgrid=True, gridcolor="#eee", dtick=1)
    fig_acum.update_yaxes(showgrid=True, gridcolor="#eee")
    st.plotly_chart(fig_acum, use_container_width=True)
    st.caption("Hipóteses: encargos totais = INSS patronal 20% + FGTS 8% + férias 1/12 + 13º 1/12. Transição linear ao longo do horizonte do cenário.")


# ─────────────────────────────────────────────────────────
# TAB 5 — PERGUNTAS GUIADAS
# ─────────────────────────────────────────────────────────
with tab5:
    st.markdown("#### Framework de perguntas guiadas")
    st.caption("Explore as principais variáveis e seus efeitos esperados com base nos modelos.")

    for i, item in enumerate(QA_ITEMS):
        with st.expander(f"**{item['q']}**", expanded=(i == 0)):
            st.markdown(item["a"])

    st.divider()
    st.markdown("#### Hipóteses e limitações do modelo")
    with st.expander("Ver hipóteses declaradas e limitações"):
        st.markdown("""
**Hipóteses do modelo Monte Carlo:**
- Distribuição log-normal para choques de custo (captura assimetria positiva dos custos)
- Distribuição normal para variação de produtividade e emprego
- Elasticidade custo-emprego: -0,15 a -0,40 dependendo do setor (baseado em literatura empírica brasileira)
- Ganhos de produtividade levam 18–36 meses para se materializar
- Resposta da informalidade ao diferencial de custo: defasagem de 2–4 trimestres

**Limitações:**
- O modelo não captura choques macroeconômicos exógenos (recessão, inflação de salários)
- A resposta da política fiscal (eventuais desonerações compensatórias) altera substancialmente os resultados
- Dados de produtividade setorial desagregada para o Brasil têm qualidade variável
- Efeitos de equilíbrio geral (feedback entre setores) não são modelados explicitamente
- Diferenças intra-estaduais (capital vs. interior) não são capturadas no nível regional

**Fontes de dados:**
- PNAD Contínua (IBGE) 2015–2023
- RAIS / CAGED (MTE) 2015–2023
- Evidências internacionais: OCDE, ILO, estudos publicados sobre França, Islândia, Japão, Alemanha e Dinamarca
        """)


# ─────────────────────────────────────────────────────────
# RODAPÉ
# ─────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style="font-size:12px;color:#999;text-align:center;padding:8px 0">
  Simulador Reforma 6×1 · Fins analíticos e educacionais ·
  Dados: PNAD Contínua, RAIS/MTE, IBGE · Evidências: OCDE, ILO
</div>
""", unsafe_allow_html=True)
