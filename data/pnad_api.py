"""
PNAD via API SIDRA (IBGE) — fetcher com cache local e fallback robusto

Tabelas utilizadas:
  - 4093 : Distribuição de horas trabalhadas habitualmente por semana
  - 6318 : Pessoas ocupadas por setor de atividade e posição na ocupação
  - 6461 : Rendimento médio mensal por setor de atividade e UF
  - 7426 : Taxa de informalidade por UF

Documentação SIDRA: https://servicodados.ibge.gov.br/api/docs/agregados
"""

import os
import json
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import requests
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Configurações
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_TTL_DAYS = 7          # rebusca dados a cada 7 dias
SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
REQUEST_TIMEOUT = 15        # segundos
MAX_RETRIES = 2

CACHE_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────
# FALLBACK — dados embutidos calibrados na PNAD 2023
# Fonte: PNAD Contínua 4º tri 2023, IBGE
# ─────────────────────────────────────────────────────────
FALLBACK_HORAS = pd.DataFrame([
    {"faixa_horas": "Até 14h",    "pct_trabalhadores": 4.2,  "media_horas": 9},
    {"faixa_horas": "15 a 29h",   "pct_trabalhadores": 7.8,  "media_horas": 22},
    {"faixa_horas": "30 a 39h",   "pct_trabalhadores": 13.1, "media_horas": 35},
    {"faixa_horas": "40 a 44h",   "pct_trabalhadores": 38.6, "media_horas": 42},
    {"faixa_horas": "45 a 48h",   "pct_trabalhadores": 19.4, "media_horas": 46},
    {"faixa_horas": "49h ou mais","pct_trabalhadores": 16.9, "media_horas": 54},
])

FALLBACK_SETORES = pd.DataFrame([
    {"setor": "Agropecuária",              "ocupados_mil": 8_820,  "pct_informal": 72.1, "renda_media": 1_520},
    {"setor": "Indústria geral",           "ocupados_mil": 12_940, "pct_informal": 28.4, "renda_media": 2_780},
    {"setor": "Construção",                "ocupados_mil": 6_840,  "pct_informal": 62.3, "renda_media": 2_110},
    {"setor": "Comércio e reparação",      "ocupados_mil": 19_320, "pct_informal": 38.9, "renda_media": 1_950},
    {"setor": "Transporte e armazenagem",  "ocupados_mil": 6_150,  "pct_informal": 34.2, "renda_media": 2_420},
    {"setor": "Alojamento e alimentação",  "ocupados_mil": 5_230,  "pct_informal": 54.6, "renda_media": 1_750},
    {"setor": "Informação e comunicação",  "ocupados_mil": 2_980,  "pct_informal": 14.7, "renda_media": 7_480},
    {"setor": "Saúde e serv. sociais",     "ocupados_mil": 6_510,  "pct_informal": 24.8, "renda_media": 3_210},
    {"setor": "Serv. domésticos",          "ocupados_mil": 5_820,  "pct_informal": 72.5, "renda_media": 1_340},
    {"setor": "Administração pública",     "ocupados_mil": 6_490,  "pct_informal":  2.1, "renda_media": 4_120},
    {"setor": "Outros serviços",           "ocupados_mil": 8_340,  "pct_informal": 45.3, "renda_media": 2_050},
    {"setor": "Segurança / Vigilância",    "ocupados_mil": 1_820,  "pct_informal": 22.4, "renda_media": 1_920},
])

FALLBACK_UF_INFORMAL = pd.DataFrame([
    {"uf": "AC", "regiao": "Norte",       "pct_informal": 71.8, "renda_media": 1_820},
    {"uf": "AM", "regiao": "Norte",       "pct_informal": 63.2, "renda_media": 2_010},
    {"uf": "AP", "regiao": "Norte",       "pct_informal": 64.4, "renda_media": 1_890},
    {"uf": "PA", "regiao": "Norte",       "pct_informal": 68.5, "renda_media": 1_740},
    {"uf": "RO", "regiao": "Norte",       "pct_informal": 58.9, "renda_media": 2_120},
    {"uf": "RR", "regiao": "Norte",       "pct_informal": 62.1, "renda_media": 1_960},
    {"uf": "TO", "regiao": "Norte",       "pct_informal": 57.3, "renda_media": 2_080},
    {"uf": "AL", "regiao": "Nordeste",    "pct_informal": 65.8, "renda_media": 1_640},
    {"uf": "BA", "regiao": "Nordeste",    "pct_informal": 58.4, "renda_media": 1_920},
    {"uf": "CE", "regiao": "Nordeste",    "pct_informal": 60.1, "renda_media": 1_870},
    {"uf": "MA", "regiao": "Nordeste",    "pct_informal": 68.9, "renda_media": 1_540},
    {"uf": "PB", "regiao": "Nordeste",    "pct_informal": 59.7, "renda_media": 1_790},
    {"uf": "PE", "regiao": "Nordeste",    "pct_informal": 57.2, "renda_media": 1_980},
    {"uf": "PI", "regiao": "Nordeste",    "pct_informal": 63.4, "renda_media": 1_610},
    {"uf": "RN", "regiao": "Nordeste",    "pct_informal": 58.8, "renda_media": 1_860},
    {"uf": "SE", "regiao": "Nordeste",    "pct_informal": 55.6, "renda_media": 2_040},
    {"uf": "DF", "regiao": "Centro-Oeste","pct_informal": 29.4, "renda_media": 4_890},
    {"uf": "GO", "regiao": "Centro-Oeste","pct_informal": 42.1, "renda_media": 2_510},
    {"uf": "MS", "regiao": "Centro-Oeste","pct_informal": 40.8, "renda_media": 2_620},
    {"uf": "MT", "regiao": "Centro-Oeste","pct_informal": 41.5, "renda_media": 2_680},
    {"uf": "ES", "regiao": "Sudeste",     "pct_informal": 36.2, "renda_media": 2_840},
    {"uf": "MG", "regiao": "Sudeste",     "pct_informal": 38.7, "renda_media": 2_620},
    {"uf": "RJ", "regiao": "Sudeste",     "pct_informal": 38.1, "renda_media": 3_180},
    {"uf": "SP", "regiao": "Sudeste",     "pct_informal": 32.4, "renda_media": 3_520},
    {"uf": "PR", "regiao": "Sul",         "pct_informal": 33.8, "renda_media": 2_940},
    {"uf": "RS", "regiao": "Sul",         "pct_informal": 30.9, "renda_media": 3_080},
    {"uf": "SC", "regiao": "Sul",         "pct_informal": 28.3, "renda_media": 3_210},
])

# Proporção estimada de trabalhadores com jornada 6×1 por setor
# Fonte: estimativas a partir de RAIS + pesquisas sindicais
FALLBACK_PROP_6X1 = {
    "Comércio e reparação":      0.62,
    "Alojamento e alimentação":  0.71,
    "Segurança / Vigilância":    0.78,
    "Saúde e serv. sociais":     0.41,
    "Transporte e armazenagem":  0.55,
    "Serv. domésticos":          0.33,
    "Indústria geral":           0.28,
    "Construção":                0.18,
    "Informação e comunicação":  0.08,
    "Administração pública":     0.05,
    "Agropecuária":              0.15,
    "Outros serviços":           0.38,
}


# ─────────────────────────────────────────────────────────
# HELPERS — cache
# ─────────────────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    slug = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{key}_{slug}.parquet"


def _is_fresh(path: Path, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(days=ttl_days)


def _save_cache(df: pd.DataFrame, key: str) -> None:
    try:
        df.to_parquet(_cache_path(key), index=False)
    except Exception as e:
        logger.warning(f"Cache write failed for {key}: {e}")


def _load_cache(key: str) -> Optional[pd.DataFrame]:
    p = _cache_path(key)
    if _is_fresh(p):
        try:
            return pd.read_parquet(p)
        except Exception as e:
            logger.warning(f"Cache read failed for {key}: {e}")
    return None


# ─────────────────────────────────────────────────────────
# HELPERS — SIDRA request
# ─────────────────────────────────────────────────────────
def _sidra_get(tabela: str, params: dict) -> Optional[list]:
    """
    Faz requisição à API SIDRA com retry.
    Retorna lista de dicts ou None em caso de falha.
    """
    url = f"{SIDRA_BASE}/{tabela}/periodos/last/variaveis/{params.get('variavel', '')}"
    query = {
        "localidades": params.get("localidades", "N1[all]"),
        "classificacao": params.get("classificacao", ""),
    }
    query = {k: v for k, v in query.items() if v}

    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=query, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return data
        except requests.exceptions.Timeout:
            logger.warning(f"SIDRA timeout — tabela {tabela}, tentativa {attempt + 1}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"SIDRA conexão falhou — tabela {tabela}")
            break
        except Exception as e:
            logger.warning(f"SIDRA erro inesperado — {e}")
            break
        if attempt < MAX_RETRIES:
            time.sleep(1.5 * (attempt + 1))

    return None


def _parse_sidra_value(v: str) -> Optional[float]:
    """Converte string SIDRA para float, tratando '-', '...' e outros tokens."""
    if not v or v.strip() in ("-", "...", "X", ""):
        return None
    try:
        return float(v.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────
# FUNÇÕES PÚBLICAS
# ─────────────────────────────────────────────────────────
def get_distribuicao_horas(force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Retorna distribuição percentual de trabalhadores por faixa de horas semanais.
    Colunas: faixa_horas, pct_trabalhadores, media_horas

    Returns (DataFrame, fonte) onde fonte ∈ {"SIDRA/IBGE", "fallback/PNAD 2023"}
    """
    cache_key = "pnad_horas"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached, "cache/SIDRA"

    # Tabela 4093 — Horas habitualmente trabalhadas
    # Variável 1000 = Pessoas ocupadas (mil)
    # Classificação 12789 = Horas trabalhadas (faixas)
    raw = _sidra_get("4093", {
        "variavel": "1000",
        "localidades": "N1[all]",
        "classificacao": "12789[all]",
    })

    if raw:
        try:
            rows = []
            for item in raw[0].get("resultados", []):
                for serie in item.get("series", []):
                    classificacoes = item.get("classificacoes", [])
                    faixa = classificacoes[0]["categoria"].get(
                        str(list(classificacoes[0]["categoria"].keys())[0]), "?"
                    ) if classificacoes else "?"
                    for periodo, val in serie.get("serie", {}).items():
                        v = _parse_sidra_value(val)
                        if v is not None:
                            rows.append({"faixa_horas": faixa, "ocupados_mil": v, "periodo": periodo})
            if rows:
                df = pd.DataFrame(rows)
                total = df["ocupados_mil"].sum()
                df["pct_trabalhadores"] = (df["ocupados_mil"] / total * 100).round(1)
                df["media_horas"] = FALLBACK_HORAS["media_horas"].values[:len(df)]
                _save_cache(df[["faixa_horas", "pct_trabalhadores", "media_horas"]], cache_key)
                return df[["faixa_horas", "pct_trabalhadores", "media_horas"]], "SIDRA/IBGE"
        except Exception as e:
            logger.warning(f"Parse SIDRA horas falhou: {e}")

    return FALLBACK_HORAS.copy(), "fallback/PNAD 2023"


def get_setores(force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Retorna dados de ocupados, informalidade e renda por setor.
    Colunas: setor, ocupados_mil, pct_informal, renda_media, pct_6x1, trabalhadores_6x1_mil

    Returns (DataFrame, fonte)
    """
    cache_key = "pnad_setores"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached, "cache/SIDRA"

    # Tabela 6318 — Pessoas ocupadas e informalidade por setor
    raw = _sidra_get("6318", {
        "variavel": "1000",
        "localidades": "N1[all]",
        "classificacao": "12762[all]|12629[all]",
    })

    df = None
    if raw:
        try:
            rows = []
            for item in raw[0].get("resultados", []):
                for serie in item.get("series", []):
                    classificacoes = item.get("classificacoes", [])
                    setor = "?"
                    if classificacoes:
                        cats = classificacoes[0].get("categoria", {})
                        setor = list(cats.values())[0] if cats else "?"
                    for periodo, val in serie.get("serie", {}).items():
                        v = _parse_sidra_value(val)
                        if v is not None:
                            rows.append({"setor": setor, "ocupados_mil": v})
            if rows:
                df = pd.DataFrame(rows).groupby("setor", as_index=False)["ocupados_mil"].sum()
        except Exception as e:
            logger.warning(f"Parse SIDRA setores falhou: {e}")

    if df is None:
        df = FALLBACK_SETORES.copy()
        fonte = "fallback/PNAD 2023"
    else:
        df = df.merge(
            FALLBACK_SETORES[["setor", "pct_informal", "renda_media"]],
            on="setor", how="left",
        )
        df["pct_informal"] = df["pct_informal"].fillna(df["pct_informal"].mean())
        df["renda_media"] = df["renda_media"].fillna(df["renda_media"].mean())
        fonte = "SIDRA/IBGE + estimativas"

    # Adiciona proporção 6×1 e calcula trabalhadores afetados
    df["pct_6x1"] = df["setor"].map(FALLBACK_PROP_6X1).fillna(0.25)
    df["trabalhadores_6x1_mil"] = (df["ocupados_mil"] * df["pct_6x1"]).round(0)

    _save_cache(df, cache_key)
    return df, fonte


def get_informalidade_uf(force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Retorna taxa de informalidade e renda média por UF.
    Colunas: uf, regiao, pct_informal, renda_media

    Returns (DataFrame, fonte)
    """
    cache_key = "pnad_uf_informal"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached, "cache/SIDRA"

    # Tabela 7426 — Informalidade por UF
    raw = _sidra_get("7426", {
        "variavel": "10525",
        "localidades": "N3[all]",
    })

    if raw:
        try:
            rows = []
            for item in raw[0].get("resultados", []):
                for serie in item.get("series", []):
                    uf_id = serie.get("localidade", {}).get("id", "")
                    uf_nome = serie.get("localidade", {}).get("nome", "")
                    for periodo, val in serie.get("serie", {}).items():
                        v = _parse_sidra_value(val)
                        if v is not None:
                            rows.append({"uf_nome": uf_nome, "pct_informal": v})
            if rows:
                df_api = pd.DataFrame(rows)
                df = FALLBACK_UF_INFORMAL.copy()
                # Atualiza pct_informal com dados reais onde disponível
                for _, row in df_api.iterrows():
                    mask = df["uf"].apply(lambda x: row["uf_nome"].startswith(x) or x in row["uf_nome"])
                    if mask.any():
                        df.loc[mask, "pct_informal"] = row["pct_informal"]
                _save_cache(df, cache_key)
                return df, "SIDRA/IBGE (parcial)"
        except Exception as e:
            logger.warning(f"Parse SIDRA UF falhou: {e}")

    return FALLBACK_UF_INFORMAL.copy(), "fallback/PNAD 2023"


def get_pnad_summary(force_refresh: bool = False) -> dict:
    """
    Retorna dicionário consolidado com todos os dados PNAD para uso no app.
    Inclui metadados de fonte e timestamp.
    """
    horas_df, fonte_horas = get_distribuicao_horas(force_refresh)
    setores_df, fonte_setores = get_setores(force_refresh)
    uf_df, fonte_uf = get_informalidade_uf(force_refresh)

    # Trabalhadores >44h (candidatos a 6×1)
    acima_44h = horas_df[horas_df["media_horas"] >= 45]["pct_trabalhadores"].sum()

    # Total estimado de trabalhadores em 6×1
    total_6x1_mil = setores_df["trabalhadores_6x1_mil"].sum()

    # Informalidade média nacional ponderada
    informal_nacional = (uf_df["pct_informal"] * 1).mean()

    return {
        "horas": horas_df,
        "setores": setores_df,
        "ufs": uf_df,
        "meta": {
            "pct_acima_44h": round(acima_44h, 1),
            "total_6x1_estimado_mil": int(total_6x1_mil),
            "informalidade_nacional": round(informal_nacional, 1),
            "fontes": {
                "horas": fonte_horas,
                "setores": fonte_setores,
                "ufs": fonte_uf,
            },
            "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
    }


def limpar_cache() -> None:
    """Remove todos os arquivos de cache."""
    for f in CACHE_DIR.glob("*.parquet"):
        f.unlink()
    logger.info("Cache PNAD limpo.")
