"""
Pipeline de integração — dados reais (PNAD + CAGED) × modelo econométrico

Responsabilidades:
  1. Busca dados via pnad_api e caged_api (com fallback automático)
  2. Recalibra os multiplicadores do modelo (dados.py) com valores reais
  3. Exporta parâmetros prontos para uso no app.py
  4. Expõe indicadores derivados para as novas abas de dados reais
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
import pandas as pd
import numpy as np

from .pnad_api import get_pnad_summary
from .caged_api import get_caged_summary
from .dados import CENARIOS, SETORES, REGIOES, monte_carlo

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# DATACLASS de resultado consolidado
# ─────────────────────────────────────────────────────────
@dataclass
class DadosConsolidados:
    # Dados brutos
    pnad: dict = field(default_factory=dict)
    caged: dict = field(default_factory=dict)

    # Parâmetros recalibrados
    setores_calibrados: dict = field(default_factory=dict)
    regioes_calibradas: dict = field(default_factory=dict)

    # Metadados de fonte
    fontes: dict = field(default_factory=dict)
    usando_dados_reais: bool = False
    atualizado_em: str = ""

    def banner_fonte(self) -> tuple[str, str]:
        """
        Retorna (mensagem, tipo) para exibição no app.
        Snapshot PNAD 2023 = dado real calibrado, nao estimativa.
        SEMPRE verde — amarelo so se erro critico.
        """
        fontes_vals = set(self.fontes.values())
        tem_api = any("SIDRA" in f or "MTE" in f for f in fontes_vals)
        tem_cache = any("cache" in f for f in fontes_vals)

        if tem_api:
            return (
                f"Dados via API — PNAD/SIDRA (IBGE) + CAGED (MTE) · "
                f"Atualizado: {self.atualizado_em}",
                "success",
            )
        elif tem_cache:
            return (
                f"Dados em cache local · PNAD Continua 2023 + CAGED 2023 · "
                f"Atualizado: {self.atualizado_em}",
                "success",
            )
        else:
            return (
                f"Dados: PNAD Continua 2023 (snapshot) + CAGED 2023 (snapshot) · "
                f"{self.atualizado_em} · "
                "Clique em 'Atualizar dados' para buscar via API ao vivo.",
                "success",
            )


# ─────────────────────────────────────────────────────────
# CALIBRAÇÃO — atualiza multiplicadores com dados reais
# ─────────────────────────────────────────────────────────
_MAPA_SETOR_PNAD_PARA_APP = {
    "Comércio e reparação":      "Varejo",
    "Alojamento e alimentação":  "Alimentação / Restaurantes",
    "Saúde e serv. sociais":     "Saúde",
    "Transporte e armazenagem":  "Transporte e Logística",
    "Indústria geral":           "Indústria",
    "Segurança / Vigilância":    "Segurança Privada",
    "Serv. domésticos":          "Limpeza e Conservação",
    "Informação e comunicação":  "Tecnologia (TI)",
}

_MAPA_REGIAO_PNAD_PARA_APP = {
    "Norte":        "Norte",
    "Nordeste":     "Nordeste",
    "Centro-Oeste": "Centro-Oeste",
    "Sudeste":      "Sudeste",
    "Sul":          "Sul",
}


def _calibrar_setores(pnad_setores: pd.DataFrame) -> dict:
    """
    Recalibra custo_mult e prod_mult dos setores usando informalidade real
    e renda média da PNAD.

    Lógica:
    - custo_mult ∝ (pct_informal_setor / pct_informal_nacional) × (renda_media_nacional / renda_media_setor)
      Setores com mais informais e menor renda são mais vulneráveis ao aumento de custo formal.
    - prod_mult ∝ (renda_media_setor / renda_media_nacional)
      Proxy: setores de maior renda tendem a ter maior potencial de ganho de produtividade.
    """
    setores_cal = {}
    informal_med = pnad_setores["pct_informal"].mean()
    renda_med = pnad_setores["renda_media"].mean()

    for _, row in pnad_setores.iterrows():
        nome_app = _MAPA_SETOR_PNAD_PARA_APP.get(row["setor"])
        if not nome_app:
            continue
        base = SETORES.get(nome_app, {})
        if not base:
            continue

        informal_ratio = row["pct_informal"] / max(informal_med, 1)
        renda_ratio = renda_med / max(row["renda_media"], 1)

        # Escala moderada — não deixamos o multiplicador sair muito do padrão
        custo_mult = 1.0 + 0.3 * (informal_ratio - 1) + 0.2 * (renda_ratio - 1)
        custo_mult = float(np.clip(custo_mult, 0.70, 1.50))

        prod_mult = 1.0 + 0.2 * (row["renda_media"] / max(renda_med, 1) - 1)
        prod_mult = float(np.clip(prod_mult, 0.70, 1.40))

        setores_cal[nome_app] = {
            **base,
            "custo_mult": round(custo_mult, 3),
            "prod_mult": round(prod_mult, 3),
            "pct_informal_real": round(row["pct_informal"], 1),
            "renda_media_real": int(row["renda_media"]),
            "trabalhadores_6x1_mil": int(row.get("trabalhadores_6x1_mil", base.get("workers_n", 0) / 1000)),
            "workers_str": f"{row.get('trabalhadores_6x1_mil', base.get('workers_n', 0) / 1000):,.0f} mil (PNAD)",
        }

    # Setores não cobertos pela PNAD mantêm valores originais
    for nome, dados in SETORES.items():
        if nome not in setores_cal:
            setores_cal[nome] = dados

    return setores_cal


def _calibrar_regioes(pnad_ufs: pd.DataFrame) -> dict:
    """
    Recalibra reg_mult das regiões usando informalidade real por UF.

    Lógica:
    - reg_mult ∝ (pct_informal_regiao / pct_informal_nacional)
    """
    regioes_cal = {}
    df_reg = pnad_ufs.groupby("regiao", as_index=False).agg(
        pct_informal=("pct_informal", "mean"),
        renda_media=("renda_media", "mean"),
    )
    informal_nacional = pnad_ufs["pct_informal"].mean()

    for _, row in df_reg.iterrows():
        nome_app = _MAPA_REGIAO_PNAD_PARA_APP.get(row["regiao"])
        if not nome_app:
            continue
        base = REGIOES.get(nome_app, {})
        if not base:
            continue

        reg_mult = 1.0 + 0.4 * (row["pct_informal"] / max(informal_nacional, 1) - 1)
        reg_mult = float(np.clip(reg_mult, 0.65, 1.50))

        # Recalcula exposure index baseado em informalidade real
        exposure = min(10.0, row["pct_informal"] / 10)

        regioes_cal[nome_app] = {
            **base,
            "reg_mult": round(reg_mult, 3),
            "exposure": round(exposure, 1),
            "pct_informal_real": round(row["pct_informal"], 1),
            "renda_media_real": int(row["renda_media"]),
        }

    for nome, dados in REGIOES.items():
        if nome not in regioes_cal:
            regioes_cal[nome] = dados

    return regioes_cal


# ─────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────
def carregar_dados(force_refresh: bool = False) -> DadosConsolidados:
    """
    Carrega e consolida todos os dados (PNAD + CAGED).
    Retorna DadosConsolidados com parâmetros recalibrados.
    """
    pnad = get_pnad_summary(force_refresh)
    caged = get_caged_summary(force_refresh)

    fontes = {**pnad["meta"]["fontes"], **caged["meta"]["fontes"]}
    usando_reais = any("SIDRA" in str(v) or "MTE" in str(v) for v in fontes.values())

    try:
        setores_cal = _calibrar_setores(pnad["setores"])
    except Exception as e:
        logger.warning(f"Calibração de setores falhou: {e}")
        setores_cal = dict(SETORES)

    try:
        regioes_cal = _calibrar_regioes(pnad["ufs"])
    except Exception as e:
        logger.warning(f"Calibração de regiões falhou: {e}")
        regioes_cal = dict(REGIOES)

    return DadosConsolidados(
        pnad=pnad,
        caged=caged,
        setores_calibrados=setores_cal,
        regioes_calibradas=regioes_cal,
        fontes=fontes,
        usando_dados_reais=usando_reais,
        atualizado_em=pnad["meta"]["atualizado_em"],
    )


# ─────────────────────────────────────────────────────────
# HELPERS — indicadores derivados para o app
# ─────────────────────────────────────────────────────────
def distribuicao_horas_chart(dados: DadosConsolidados) -> pd.DataFrame:
    """DataFrame formatado para o gráfico de distribuição de horas."""
    df = dados.pnad["horas"].copy()
    df["em_6x1_estimado"] = df["media_horas"].apply(lambda h: h >= 45)
    df["cor"] = df["em_6x1_estimado"].map({True: "#D85A30", False: "#185FA5"})
    return df


def serie_emprego_chart(dados: DadosConsolidados) -> pd.DataFrame:
    """Série temporal CAGED formatada para gráfico de linha."""
    df = dados.caged["serie_nacional"].copy()
    df["periodo_dt"] = pd.to_datetime(df["periodo"] + "-01", errors="coerce")
    df = df.dropna(subset=["periodo_dt"]).sort_values("periodo_dt")
    df["saldo_acumulado_mil"] = df["saldo_mil"].cumsum()
    df["media_movel_3m"] = df["saldo_mil"].rolling(3, min_periods=1).mean().round(1)
    return df


def rotatividade_por_setor(dados: DadosConsolidados) -> pd.DataFrame:
    """Ranking de setores por rotatividade para contextualizar impacto da reforma."""
    return (
        dados.caged["por_setor"]
        .sort_values("rotatividade_pct", ascending=False)
        .reset_index(drop=True)
    )


def vulnerabilidade_recalibrada(dados: DadosConsolidados) -> pd.DataFrame:
    """
    Índice de vulnerabilidade recalibrado com dados reais.
    Combina informalidade real + rotatividade CAGED + proporção 6×1.
    """
    rows = []
    caged_rot = {
        row["setor"]: row["rotatividade_pct"]
        for _, row in dados.caged["por_setor"].iterrows()
    }

    for nome_app, params in dados.setores_calibrados.items():
        if nome_app == "Todos os setores":
            continue
        informal = params.get("pct_informal_real", 40.0)
        rot = caged_rot.get(nome_app, 40.0)
        prop_6x1 = params.get("pct_6x1", 0.30) if "pct_6x1" in params else 0.30

        # Índice composto (0–10)
        vuln = (
            (informal / 10) * 0.40 +
            (rot / 10) * 0.25 +
            (prop_6x1 * 10) * 0.35
        )
        vuln = round(min(vuln, 10.0), 1)

        rows.append({
            "setor": nome_app,
            "vulnerabilidade": vuln,
            "pct_informal": informal,
            "rotatividade_pct": rot,
            "prop_6x1": round(prop_6x1, 2),
        })

    return pd.DataFrame(rows).sort_values("vulnerabilidade", ascending=False).reset_index(drop=True)
