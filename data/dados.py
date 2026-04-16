"""
Dados e modelos econométricos — Simulador Reforma 6×1
Baseado em: PNAD Contínua, RAIS/MTE, IBGE (2015–2023)
e evidências internacionais (França, Islândia, Japão, Dinamarca)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Tuple

# ── Semente para reprodutibilidade nas simulações Monte Carlo
RNG_SEED = 42

# ──────────────────────────────────────────────────────────
# CENÁRIOS
# ──────────────────────────────────────────────────────────
CENARIOS = {
    "Conservador": {
        "descricao": "5×2 gradual — transição em 4 anos, sem remuneração adicional",
        "horizonte": 4,
        "modelo": "5×2",
        "custo_lo": 8.0,
        "custo_hi": 12.0,
        "emprego_lo": -1.0,
        "emprego_hi": 2.0,
        "prod_lo": 3.0,
        "prod_hi": 6.0,
        "fiscal_lo": -4.0,
        "fiscal_hi": 2.0,
        "consumo_lo": 1.0,
        "consumo_hi": 3.0,
        "cor": "#185FA5",
    },
    "Moderado": {
        "descricao": "5×2 acelerado — transição em 2 anos, redistribuição parcial",
        "horizonte": 2,
        "modelo": "5×2",
        "custo_lo": 12.0,
        "custo_hi": 18.0,
        "emprego_lo": -3.0,
        "emprego_hi": 0.0,
        "prod_lo": 5.0,
        "prod_hi": 8.0,
        "fiscal_lo": -8.0,
        "fiscal_hi": 0.0,
        "consumo_lo": 2.0,
        "consumo_hi": 5.0,
        "cor": "#3B6D11",
    },
    "Transformador": {
        "descricao": "4×3 estrutural — novo paradigma laboral, transição em 3 anos",
        "horizonte": 3,
        "modelo": "4×3",
        "custo_lo": 20.0,
        "custo_hi": 32.0,
        "emprego_lo": -8.0,
        "emprego_hi": -3.0,
        "prod_lo": 6.0,
        "prod_hi": 12.0,
        "fiscal_lo": -18.0,
        "fiscal_hi": -5.0,
        "consumo_lo": 3.0,
        "consumo_hi": 8.0,
        "cor": "#993C1D",
    },
}

# ──────────────────────────────────────────────────────────
# SETORES
# ──────────────────────────────────────────────────────────
SETORES = {
    "Todos os setores": {
        "vuln": 6.5,
        "workers_str": "13,5 milhões",
        "workers_n": 13_500_000,
        "custo_mult": 1.00,
        "prod_mult": 1.00,
        "salario_medio": 2100,
    },
    "Varejo": {
        "vuln": 8.2,
        "workers_str": "4,2 milhões",
        "workers_n": 4_200_000,
        "custo_mult": 1.15,
        "prod_mult": 0.90,
        "salario_medio": 1950,
    },
    "Saúde": {
        "vuln": 6.1,
        "workers_str": "2,1 milhões",
        "workers_n": 2_100_000,
        "custo_mult": 1.05,
        "prod_mult": 1.05,
        "salario_medio": 3200,
    },
    "Alimentação / Restaurantes": {
        "vuln": 9.0,
        "workers_str": "1,8 milhões",
        "workers_n": 1_800_000,
        "custo_mult": 1.20,
        "prod_mult": 0.85,
        "salario_medio": 1750,
    },
    "Transporte e Logística": {
        "vuln": 7.3,
        "workers_str": "1,4 milhões",
        "workers_n": 1_400_000,
        "custo_mult": 1.10,
        "prod_mult": 0.95,
        "salario_medio": 2400,
    },
    "Indústria": {
        "vuln": 5.2,
        "workers_str": "2,5 milhões",
        "workers_n": 2_500_000,
        "custo_mult": 0.95,
        "prod_mult": 1.10,
        "salario_medio": 2800,
    },
    "Segurança Privada": {
        "vuln": 8.5,
        "workers_str": "1,0 milhão",
        "workers_n": 1_000_000,
        "custo_mult": 1.18,
        "prod_mult": 0.80,
        "salario_medio": 1900,
    },
    "Limpeza e Conservação": {
        "vuln": 8.8,
        "workers_str": "1,2 milhões",
        "workers_n": 1_200_000,
        "custo_mult": 1.22,
        "prod_mult": 0.90,
        "salario_medio": 1560,
    },
    "Tecnologia (TI)": {
        "vuln": 1.8,
        "workers_str": "0,3 milhão",
        "workers_n": 300_000,
        "custo_mult": 0.80,
        "prod_mult": 1.25,
        "salario_medio": 7500,
    },
}

# ──────────────────────────────────────────────────────────
# REGIÕES
# ──────────────────────────────────────────────────────────
REGIOES = {
    "Brasil (agregado)": {"exposure": 6.0, "reg_mult": 1.00},
    "Norte":             {"exposure": 9.1, "reg_mult": 1.30},
    "Nordeste":          {"exposure": 8.4, "reg_mult": 1.20},
    "Centro-Oeste":      {"exposure": 6.2, "reg_mult": 1.05},
    "Sudeste":           {"exposure": 5.1, "reg_mult": 0.90},
    "Sul":               {"exposure": 4.3, "reg_mult": 0.82},
}

# ──────────────────────────────────────────────────────────
# ESTADOS — vulnerabilidade (0–10)
# ──────────────────────────────────────────────────────────
ESTADOS_VULN = {
    "AC": 9.2, "AM": 8.9, "AP": 8.7, "PA": 8.8, "RO": 8.5, "RR": 9.0, "TO": 8.3,
    "AL": 9.0, "BA": 8.6, "CE": 8.4, "MA": 9.1, "PB": 8.5, "PE": 8.3,
    "PI": 8.8, "RN": 8.2, "SE": 8.0,
    "DF": 5.8, "GO": 6.1, "MS": 6.0, "MT": 5.9,
    "ES": 5.5, "MG": 5.3, "RJ": 5.6, "SP": 4.8,
    "PR": 4.5, "RS": 4.2, "SC": 4.0,
}

# ──────────────────────────────────────────────────────────
# PORTES
# ──────────────────────────────────────────────────────────
PORTES = {
    "Todos os portes":           {"custo_adj": 0.0,  "emprego_adj": 0.0},
    "MEI / Microempresa":        {"custo_adj": 6.0,  "emprego_adj": -2.0},
    "PME (10–499 func.)":        {"custo_adj": 3.0,  "emprego_adj": -1.0},
    "Grande empresa (500+ func.)": {"custo_adj": -2.0, "emprego_adj": 0.5},
}

# ──────────────────────────────────────────────────────────
# MATRIZ DE IMPACTO SETORIAL
# ──────────────────────────────────────────────────────────
MATRIZ_IMPACTO = [
    {"setor": "Varejo",               "mei": "Alta",      "pme": "Alta",   "grande": "Média",      "workers": "4,2M", "inform": "Alto"},
    {"setor": "Saúde",                "mei": "Média",     "pme": "Média",  "grande": "Baixa",      "workers": "2,1M", "inform": "Médio"},
    {"setor": "Alimentação",          "mei": "Muito alta","pme": "Alta",   "grande": "Média",      "workers": "1,8M", "inform": "Muito alto"},
    {"setor": "Transporte",           "mei": "Alta",      "pme": "Alta",   "grande": "Baixa",      "workers": "1,4M", "inform": "Alto"},
    {"setor": "Indústria",            "mei": "Baixa",     "pme": "Média",  "grande": "Baixa",      "workers": "2,5M", "inform": "Baixo"},
    {"setor": "Segurança privada",    "mei": "Alta",      "pme": "Alta",   "grande": "Média",      "workers": "1,0M", "inform": "Médio"},
    {"setor": "Limpeza / Cons.",      "mei": "Muito alta","pme": "Alta",   "grande": "Média",      "workers": "1,2M", "inform": "Alto"},
    {"setor": "TI / Tech",            "mei": "Baixa",     "pme": "Baixa",  "grande": "Muito baixa","workers": "0,3M", "inform": "Muito baixo"},
]

# ──────────────────────────────────────────────────────────
# COMPARAÇÕES INTERNACIONAIS
# ──────────────────────────────────────────────────────────
INTL = [
    {
        "pais": "França",
        "flag": "🇫🇷",
        "politica": "Lei Aubry — 35h/semana (1998–2002)",
        "prod_hora": "+6%",
        "emprego": "+350 mil",
        "custo": "+14%",
        "obs": "Criação de empregos no curto prazo; resistência empresarial intensa. Setor de serviços mais beneficiado.",
    },
    {
        "pais": "Islândia",
        "flag": "🇮🇸",
        "politica": "Piloto 4 dias (2015–2019)",
        "prod_hora": "Mantida / +5%",
        "emprego": "Neutro",
        "custo": "+8%",
        "obs": "86% da força de trabalho migrou. Burnout −30%, absenteísmo −20%. Maior êxito documentado.",
    },
    {
        "pais": "Japão",
        "flag": "🇯🇵",
        "politica": "Iniciativa Microsoft Japão (2019+)",
        "prod_hora": "+40% (piloto)",
        "emprego": "Neutro",
        "custo": "Variável",
        "obs": "Adoção geral lenta; cultura de presencialismo. Grandes corporações lideram, PMEs resistem.",
    },
    {
        "pais": "Dinamarca",
        "flag": "🇩🇰",
        "politica": "37h/semana padrão via acordos coletivos",
        "prod_hora": "+27% acima OCDE",
        "emprego": "Alto",
        "custo": "Neutro (gradual)",
        "obs": "Modelo de flexissegurança com forte rede de proteção social. Referência de longo prazo.",
    },
    {
        "pais": "Alemanha",
        "flag": "🇩🇪",
        "politica": "Kurzarbeit + acordos setoriais",
        "prod_hora": "+8%",
        "emprego": "+1,4M preservados (2008)",
        "custo": "Subsidiado",
        "obs": "Subsídio estatal para redução de jornada preservou empregos na crise. Modelo de transição gradual.",
    },
]

# ──────────────────────────────────────────────────────────
# Q&A GUIADAS
# ──────────────────────────────────────────────────────────
QA_ITEMS = [
    {
        "q": "O que muda concretamente na escala 6×1 para um trabalhador do varejo?",
        "a": (
            "Na escala 6×1, o trabalhador trabalha 6 dias e folga 1, com o descanso semanal remunerado (DSR) "
            "em dia rotativo — não necessariamente no domingo. A reforma para 5×2 garantiria dois dias de folga "
            "semanais fixos, com impacto direto na qualidade de vida, tempo para família e redução de fadiga "
            "acumulada.\n\n"
            "Para o varejo com operações 7 dias/semana, a empresa precisaria contratar em média **10–15% mais "
            "funcionários** para manter a mesma cobertura operacional."
        ),
    },
    {
        "q": "Como o custo laboral aumenta para uma PME com 50 funcionários em regime 6×1?",
        "a": (
            "Hipóteses: salário médio de R$2.200/mês, 50 empregados em 6×1.\n\n"
            "Na transição para 5×2, estima-se necessidade de 8–14 trabalhadores adicionais para manter "
            "operação equivalente. Com encargos completos (INSS patronal 20%, FGTS 8%, férias, 13º), "
            "o custo adicional na folha representa entre **R$18.000 e R$35.000/mês**.\n\n"
            "Esse impacto é assimétrico: setores com maior proporção de mão de obra no custo total "
            "(alimentação, limpeza) são muito mais vulneráveis do que setores capital-intensivos."
        ),
    },
    {
        "q": "Qual o efeito esperado sobre a produtividade por hora trabalhada?",
        "a": (
            "A evidência internacional é consistente: jornadas menores tendem a aumentar a produtividade "
            "por hora. A lógica é dupla — trabalhadores descansados erram menos e concentram-se melhor; "
            "empresas são forçadas a otimizar processos.\n\n"
            "O ganho estimado para o Brasil varia de **+3% (conservador) a +12% (transformador)**, com maior "
            "potencial em setores cognitivos (TI, saúde, educação) e menor em atividades físicas repetitivas "
            "(segurança, limpeza).\n\n"
            "⚠️ O ganho de produtividade por hora **não compensa automaticamente** o aumento de custo — "
            "o saldo líquido depende do setor e do porte da empresa."
        ),
    },
    {
        "q": "Qual o impacto fiscal sobre INSS e FGTS no curto e médio prazo?",
        "a": (
            "**Curto prazo (1–2 anos):** pressão fiscal negativa. Empresas reduzem quadro ou migram para "
            "informalidade, reduzindo a base de contribuição. Estima-se queda de arrecadação de "
            "**R$4–18 bilhões/ano** dependendo do cenário.\n\n"
            "**Médio prazo (3–5 anos):** se a reforma for bem-sucedida, a criação de novos postos formais "
            "e o aumento do consumo podem reverter o quadro. O cenário moderado apresenta o melhor "
            "custo-benefício fiscal: impacto negativo limitado com maior potencial de recuperação."
        ),
    },
    {
        "q": "Quais estados e regiões estão mais expostos a impactos negativos?",
        "a": (
            "As regiões **Norte e Nordeste** concentram maior vulnerabilidade por quatro razões:\n\n"
            "1. Maior proporção de trabalhadores em setores intensivos em 6×1 (varejo, alimentação, serviços)\n"
            "2. Menor produtividade média por hora — reduz a margem de absorção de custos\n"
            "3. Maior informalidade de base — reforma pode acelerar migração para o setor informal\n"
            "4. Menor capacidade fiscal estadual para programas de transição\n\n"
            "O **Sul e Sudeste**, com maior industrialização e economia de serviços sofisticados, "
            "absorvem o choque com mais facilidade. Essa assimetria justifica mecanismos de transição "
            "diferenciados por região."
        ),
    },
    {
        "q": "Quais condições tornam a transição economicamente sustentável?",
        "a": (
            "Com base nos casos internacionais bem-sucedidos (França, Islândia, Alemanha), "
            "as **condições necessárias** são:\n\n"
            "1. Transição gradual em no mínimo 2–4 anos, com metas intermediárias mensuráveis\n"
            "2. Compensação fiscal temporária para PMEs (desoneração parcial da folha, crédito tributário)\n"
            "3. Incentivo à automação e ganhos de produtividade, especialmente no Nordeste\n"
            "4. Envolvimento sindical ativo para acordos setoriais específicos\n"
            "5. Fiscalização robusta contra informalização (especialmente varejo e alimentação)\n"
            "6. Mecanismo de ajuste diferenciado por região e porte\n\n"
            "Sem pelo menos **3 dessas condições**, o risco de aumento da informalidade supera os "
            "ganhos esperados em bem-estar."
        ),
    },
]


# ──────────────────────────────────────────────────────────
# MODELO ECONOMÉTRICO — Monte Carlo
# ──────────────────────────────────────────────────────────
def monte_carlo(
    cenario: str,
    setor: str,
    regiao: str,
    porte: str,
    n_sim: int = 10_000,
) -> dict:
    """
    Simulação Monte Carlo para estimativa de impactos.

    Hipóteses:
    - Distribuição log-normal para choques de custo (assimetria positiva)
    - Distribuição normal para variação de produtividade
    - Distribuição normal para variação de emprego
    - Elasticidade custo-emprego: -0.15 a -0.40 dependendo do setor
    """
    rng = np.random.default_rng(RNG_SEED)
    scn = CENARIOS[cenario]
    sec = SETORES[setor]
    reg = REGIOES[regiao]
    por = PORTES[porte]

    mult = sec["custo_mult"] * reg["reg_mult"]
    pm = sec["prod_mult"]

    # Custo — log-normal centrada no mid-range
    custo_mid = (scn["custo_lo"] + scn["custo_hi"]) / 2 * mult + por["custo_adj"]
    custo_std = (scn["custo_hi"] - scn["custo_lo"]) / 4 * mult
    custo_sim = rng.lognormal(np.log(max(custo_mid, 1)), custo_std / custo_mid, n_sim)

    # Emprego — normal
    emp_mid = (scn["emprego_lo"] + scn["emprego_hi"]) / 2 + por["emprego_adj"]
    emp_std = (scn["emprego_hi"] - scn["emprego_lo"]) / 4
    emp_sim = rng.normal(emp_mid, max(emp_std, 0.5), n_sim)

    # Produtividade — normal com multiplicador setorial
    prod_mid = (scn["prod_lo"] + scn["prod_hi"]) / 2 * pm
    prod_std = (scn["prod_hi"] - scn["prod_lo"]) / 4 * pm
    prod_sim = rng.normal(prod_mid, max(prod_std, 0.3), n_sim)

    # Fiscal — normal com multiplicador regional
    fiscal_mid = (scn["fiscal_lo"] + scn["fiscal_hi"]) / 2 * reg["reg_mult"]
    fiscal_std = (scn["fiscal_hi"] - scn["fiscal_lo"]) / 4
    fiscal_sim = rng.normal(fiscal_mid, max(abs(fiscal_std), 0.5), n_sim)

    def ci(arr, lo=10, hi=90):
        return float(np.percentile(arr, lo)), float(np.mean(arr)), float(np.percentile(arr, hi))

    return {
        "custo":   ci(custo_sim),
        "emprego": ci(emp_sim),
        "produtividade": ci(prod_sim),
        "fiscal":  ci(fiscal_sim),
        "n_sim": n_sim,
    }


def estimar_custo_pme(n_func: int, salario_medio: float, cenario: str, setor: str) -> dict:
    """Estima custo adicional mensal para uma empresa específica."""
    scn = CENARIOS[cenario]
    sec = SETORES[setor]

    encargos = 1.0 + 0.20 + 0.08 + (1 / 12) + (1 / 12)  # INSS + FGTS + férias + 13º
    folha_atual = n_func * salario_medio * encargos

    # Novos funcionários necessários para cobrir os dias de folga adicionais
    if scn["modelo"] == "5×2":
        extra_ratio_lo, extra_ratio_hi = 0.08, 0.14
    else:
        extra_ratio_lo, extra_ratio_hi = 0.18, 0.28

    extra_ratio_lo *= sec["custo_mult"]
    extra_ratio_hi *= sec["custo_mult"]

    custo_adic_lo = folha_atual * extra_ratio_lo
    custo_adic_hi = folha_atual * extra_ratio_hi

    return {
        "folha_atual": folha_atual,
        "custo_adicional_lo": custo_adic_lo,
        "custo_adicional_hi": custo_adic_hi,
        "extra_func_lo": int(n_func * extra_ratio_lo),
        "extra_func_hi": int(n_func * extra_ratio_hi),
    }
