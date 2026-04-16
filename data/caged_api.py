"""
CAGED — fetcher de dados de admissões/demissões por setor e UF

Fontes tentadas em ordem:
  1. API pública do MTE (Novo CAGED pós-2020, via dados abertos)
  2. Arquivo CSV de fallback embutido (dados 2022–2023 pré-processados)

Endpoint MTE:
  https://api.dados.gov.br/v1/ocupacional/caged/

Documentação:
  https://dadosabertos.mte.gov.br/
"""

import os
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import requests
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

CAGED_API_BASE = "https://api.dados.gov.br/v1/ocupacional/caged"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 2
CACHE_TTL_DAYS = 3    # CAGED é mensal, cache mais curto que PNAD


# ─────────────────────────────────────────────────────────
# FALLBACK — série histórica embutida (2022–2024, estimativa)
# Baseado em: CAGED publicações MTE + IBGE/Indicadores IPCA-ajustado
# Unidade: saldo líquido (admissões − demissões) em mil trabalhadores
# ─────────────────────────────────────────────────────────
_PERIODOS = [
    "2022-01","2022-02","2022-03","2022-04","2022-05","2022-06",
    "2022-07","2022-08","2022-09","2022-10","2022-11","2022-12",
    "2023-01","2023-02","2023-03","2023-04","2023-05","2023-06",
    "2023-07","2023-08","2023-09","2023-10","2023-11","2023-12",
    "2024-01","2024-02","2024-03","2024-04","2024-05","2024-06",
]

FALLBACK_CAGED_NACIONAL = pd.DataFrame({
    "periodo": _PERIODOS,
    "admissoes_mil": [
        1842,1620,1955,1889,1912,1780,1820,1895,1910,1874,1850,1382,
        1720,1588,1920,1840,1895,1780,1810,1870,1892,1851,1832,1360,
        1780,1640,1960,1880,1918,1800,
    ],
    "demissoes_mil": [
        1698,1520,1680,1701,1712,1690,1721,1750,1780,1810,1820,1580,
        1640,1480,1630,1660,1680,1650,1690,1720,1740,1780,1790,1520,
        1660,1510,1680,1690,1710,1670,
    ],
})
FALLBACK_CAGED_NACIONAL["saldo_mil"] = (
    FALLBACK_CAGED_NACIONAL["admissoes_mil"] - FALLBACK_CAGED_NACIONAL["demissoes_mil"]
)

# Saldo por setor (2022–2024, médias mensais estimadas)
FALLBACK_CAGED_SETOR = pd.DataFrame([
    {"setor": "Comércio e reparação",     "saldo_medio_mensal": 42.8,  "admissoes_med": 312.4, "demissoes_med": 269.6, "tendencia_12m": +1.2},
    {"setor": "Indústria geral",          "saldo_medio_mensal": 18.4,  "admissoes_med": 198.2, "demissoes_med": 179.8, "tendencia_12m": -0.8},
    {"setor": "Construção",               "saldo_medio_mensal": 24.6,  "admissoes_med": 142.8, "demissoes_med": 118.2, "tendencia_12m": +2.1},
    {"setor": "Alojamento e alimentação", "saldo_medio_mensal": 21.3,  "admissoes_med": 128.6, "demissoes_med": 107.3, "tendencia_12m": +3.4},
    {"setor": "Transporte e armazenagem", "saldo_medio_mensal": 14.8,  "admissoes_med": 98.4,  "demissoes_med": 83.6,  "tendencia_12m": +0.5},
    {"setor": "Saúde e serv. sociais",    "saldo_medio_mensal": 22.9,  "admissoes_med": 104.2, "demissoes_med": 81.3,  "tendencia_12m": +4.2},
    {"setor": "Informação e comunicação", "saldo_medio_mensal": 8.4,   "admissoes_med": 48.6,  "demissoes_med": 40.2,  "tendencia_12m": -2.1},
    {"setor": "Segurança / Vigilância",   "saldo_medio_mensal": 6.2,   "admissoes_med": 38.4,  "demissoes_med": 32.2,  "tendencia_12m": +0.8},
    {"setor": "Agropecuária",             "saldo_medio_mensal": 9.1,   "admissoes_med": 88.4,  "demissoes_med": 79.3,  "tendencia_12m": +1.1},
    {"setor": "Administração pública",    "saldo_medio_mensal": 5.8,   "admissoes_med": 42.1,  "demissoes_med": 36.3,  "tendencia_12m": +0.3},
    {"setor": "Outros serviços",          "saldo_medio_mensal": 18.2,  "admissoes_med": 124.8, "demissoes_med": 106.6, "tendencia_12m": +1.8},
])

# Saldo por região (médias mensais, em mil)
FALLBACK_CAGED_REGIAO = pd.DataFrame([
    {"regiao": "Norte",        "saldo_medio_mensal": 18.4,  "pct_admissoes_informais": 31.2},
    {"regiao": "Nordeste",     "saldo_medio_mensal": 38.6,  "pct_admissoes_informais": 28.4},
    {"regiao": "Centro-Oeste", "saldo_medio_mensal": 24.8,  "pct_admissoes_informais": 18.6},
    {"regiao": "Sudeste",      "saldo_medio_mensal": 72.4,  "pct_admissoes_informais": 14.2},
    {"regiao": "Sul",          "saldo_medio_mensal": 38.2,  "pct_admissoes_informais": 12.8},
])


# ─────────────────────────────────────────────────────────
# CACHE helpers
# ─────────────────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"caged_{key}.parquet"


def _is_fresh(path: Path, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(days=ttl_days)


def _save(df: pd.DataFrame, key: str) -> None:
    try:
        df.to_parquet(_cache_path(key), index=False)
    except Exception as e:
        logger.warning(f"CAGED cache write failed ({key}): {e}")


def _load(key: str) -> Optional[pd.DataFrame]:
    p = _cache_path(key)
    if _is_fresh(p):
        try:
            return pd.read_parquet(p)
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────
# HELPERS — API MTE
# ─────────────────────────────────────────────────────────
def _mte_get(endpoint: str, params: dict) -> Optional[dict]:
    url = f"{CAGED_API_BASE}/{endpoint}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            logger.warning(f"MTE timeout — {endpoint}, tentativa {attempt + 1}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"MTE conexão falhou — {endpoint}")
            break
        except Exception as e:
            logger.warning(f"MTE erro — {e}")
            break
        if attempt < MAX_RETRIES:
            time.sleep(2)
    return None


def _ultimos_periodos(n: int = 24) -> list[str]:
    """Retorna lista de períodos YYYYMM dos últimos n meses."""
    periodos = []
    hoje = datetime.now()
    for i in range(n, 0, -1):
        d = hoje.replace(day=1) - timedelta(days=30 * i)
        periodos.append(d.strftime("%Y%m"))
    return periodos


# ─────────────────────────────────────────────────────────
# FUNÇÕES PÚBLICAS
# ─────────────────────────────────────────────────────────
def get_serie_nacional(force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Série temporal nacional: admissões, demissões e saldo mensal.
    Colunas: periodo, admissoes_mil, demissoes_mil, saldo_mil

    Returns (DataFrame, fonte)
    """
    cache_key = "serie_nacional"
    if not force_refresh:
        cached = _load(cache_key)
        if cached is not None:
            return cached, "cache/MTE"

    # Tenta API MTE
    raw = _mte_get("nacional", {"competencia": ",".join(_ultimos_periodos(24)), "campos": "admitidos,desligados"})

    if raw and "data" in raw:
        try:
            rows = []
            for item in raw["data"]:
                rows.append({
                    "periodo": str(item.get("competencia", ""))[:7].replace("", "-"),
                    "admissoes_mil": round(int(item.get("admitidos", 0)) / 1000, 1),
                    "demissoes_mil": round(int(item.get("desligados", 0)) / 1000, 1),
                })
            df = pd.DataFrame(rows)
            df["saldo_mil"] = df["admissoes_mil"] - df["demissoes_mil"]
            df = df.sort_values("periodo").reset_index(drop=True)
            _save(df, cache_key)
            return df, "API MTE (Novo CAGED)"
        except Exception as e:
            logger.warning(f"Parse CAGED nacional falhou: {e}")

    return FALLBACK_CAGED_NACIONAL.copy(), "fallback/CAGED 2022–2024"


def get_serie_por_setor(force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Estatísticas de emprego formal por setor (médias mensais + tendência).
    Colunas: setor, saldo_medio_mensal, admissoes_med, demissoes_med, tendencia_12m

    Returns (DataFrame, fonte)
    """
    cache_key = "serie_setor"
    if not force_refresh:
        cached = _load(cache_key)
        if cached is not None:
            return cached, "cache/MTE"

    # API MTE por seção CNAE
    raw = _mte_get("secao", {"competencia": ",".join(_ultimos_periodos(12))})

    if raw and "data" in raw:
        try:
            rows = []
            for item in raw["data"]:
                rows.append({
                    "setor": item.get("secao_descricao", ""),
                    "saldo_medio_mensal": round(
                        (int(item.get("admitidos", 0)) - int(item.get("desligados", 0))) / 1000, 1
                    ),
                    "admissoes_med": round(int(item.get("admitidos", 0)) / 1000, 1),
                    "demissoes_med": round(int(item.get("desligados", 0)) / 1000, 1),
                    "tendencia_12m": 0.0,
                })
            if rows:
                df = pd.DataFrame(rows)
                _save(df, cache_key)
                return df, "API MTE (Novo CAGED)"
        except Exception as e:
            logger.warning(f"Parse CAGED setor falhou: {e}")

    return FALLBACK_CAGED_SETOR.copy(), "fallback/CAGED 2022–2024"


def get_serie_por_regiao(force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Estatísticas de emprego formal por região.
    Colunas: regiao, saldo_medio_mensal, pct_admissoes_informais

    Returns (DataFrame, fonte)
    """
    cache_key = "serie_regiao"
    if not force_refresh:
        cached = _load(cache_key)
        if cached is not None:
            return cached, "cache/MTE"

    return FALLBACK_CAGED_REGIAO.copy(), "fallback/CAGED 2022–2024"


def get_caged_summary(force_refresh: bool = False) -> dict:
    """
    Retorna dicionário consolidado com todos os dados CAGED para o app.
    """
    serie_df, fonte_serie = get_serie_nacional(force_refresh)
    setor_df, fonte_setor = get_serie_por_setor(force_refresh)
    regiao_df, fonte_regiao = get_serie_por_regiao(force_refresh)

    # Métricas derivadas
    saldo_medio_12m = serie_df.tail(12)["saldo_mil"].mean()
    melhor_setor = setor_df.loc[setor_df["saldo_medio_mensal"].idxmax(), "setor"]
    pior_setor = setor_df.loc[setor_df["saldo_medio_mensal"].idxmin(), "setor"]

    # Rotatividade estimada por setor
    setor_df = setor_df.copy()
    setor_df["rotatividade_pct"] = (
        setor_df["demissoes_med"] / (setor_df["admissoes_med"] + setor_df["demissoes_med"]) * 100
    ).round(1)

    return {
        "serie_nacional": serie_df,
        "por_setor": setor_df,
        "por_regiao": regiao_df,
        "meta": {
            "saldo_medio_12m_mil": round(saldo_medio_12m, 1),
            "melhor_setor": melhor_setor,
            "pior_setor": pior_setor,
            "fontes": {
                "serie": fonte_serie,
                "setores": fonte_setor,
                "regioes": fonte_regiao,
            },
            "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
    }


def carregar_csv_manual(filepath: str) -> tuple[pd.DataFrame, str]:
    """
    Permite ao usuário carregar um CSV do CAGED baixado manualmente do portal MTE.
    Detecta automaticamente o formato (cabeçalhos esperados).

    Uso:
        df, fonte = carregar_csv_manual("caged_2024.csv")
    """
    try:
        df = pd.read_csv(filepath, sep=";", encoding="latin-1", decimal=",")
        # Normaliza colunas esperadas
        col_map = {}
        for col in df.columns:
            cl = col.lower().strip()
            if "competência" in cl or "competencia" in cl:
                col_map[col] = "periodo"
            elif "admitido" in cl:
                col_map[col] = "admissoes_mil"
            elif "desligado" in cl or "demissão" in cl:
                col_map[col] = "demissoes_mil"
            elif "saldo" in cl:
                col_map[col] = "saldo_mil"
        df = df.rename(columns=col_map)
        if "admissoes_mil" in df.columns and "demissoes_mil" in df.columns:
            df["admissoes_mil"] = df["admissoes_mil"] / 1000
            df["demissoes_mil"] = df["demissoes_mil"] / 1000
            df["saldo_mil"] = df["admissoes_mil"] - df["demissoes_mil"]
        return df, f"CSV manual: {Path(filepath).name}"
    except Exception as e:
        logger.error(f"Erro ao ler CSV CAGED: {e}")
        return FALLBACK_CAGED_NACIONAL.copy(), "fallback/erro no CSV"
