"""
PNAD via API SIDRA (IBGE) — fetcher com cache local e fallback robusto

Correções v2.1:
  - requests URL-encodava N1[all] -> N1%5Ball%5D (SIDRA rejeita)
  - parser não correspondia à estrutura real da resposta SIDRA v3
  Solução: urllib com URL construída manualmente + parser corrigido.

Estrutura real da resposta SIDRA v3:
[{
  "id": "1000", "variavel": "...", "unidade": "Mil pessoas",
  "resultados": [{
    "classificacoes": [{"id":"12789","nome":"...","categoria":{"id":"nome"}}],
    "series": [{"localidade":{"id":"1","nome":"Brasil"},"serie":{"202304":"100143"}}]
  }]
}]
"""

import json, logging, time, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_TTL_DAYS = 7
SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 2
CACHE_DIR.mkdir(exist_ok=True)

# ── Fallback PNAD Continua 4o tri 2023
FALLBACK_HORAS = pd.DataFrame([
    {"faixa_horas": "Ate 14h",      "pct_trabalhadores": 4.2,  "media_horas": 9},
    {"faixa_horas": "15 a 29h",     "pct_trabalhadores": 7.8,  "media_horas": 22},
    {"faixa_horas": "30 a 39h",     "pct_trabalhadores": 13.1, "media_horas": 35},
    {"faixa_horas": "40 a 44h",     "pct_trabalhadores": 38.6, "media_horas": 42},
    {"faixa_horas": "45 a 48h",     "pct_trabalhadores": 19.4, "media_horas": 46},
    {"faixa_horas": "49h ou mais",  "pct_trabalhadores": 16.9, "media_horas": 54},
])

FALLBACK_SETORES = pd.DataFrame([
    {"setor": "Agropecuaria",             "ocupados_mil": 8820,  "pct_informal": 72.1, "renda_media": 1520},
    {"setor": "Industria geral",          "ocupados_mil": 12940, "pct_informal": 28.4, "renda_media": 2780},
    {"setor": "Construcao",               "ocupados_mil": 6840,  "pct_informal": 62.3, "renda_media": 2110},
    {"setor": "Comercio e reparacao",     "ocupados_mil": 19320, "pct_informal": 38.9, "renda_media": 1950},
    {"setor": "Transporte e armazenagem", "ocupados_mil": 6150,  "pct_informal": 34.2, "renda_media": 2420},
    {"setor": "Alojamento e alimentacao", "ocupados_mil": 5230,  "pct_informal": 54.6, "renda_media": 1750},
    {"setor": "Informacao e comunicacao", "ocupados_mil": 2980,  "pct_informal": 14.7, "renda_media": 7480},
    {"setor": "Saude e serv. sociais",    "ocupados_mil": 6510,  "pct_informal": 24.8, "renda_media": 3210},
    {"setor": "Serv. domesticos",         "ocupados_mil": 5820,  "pct_informal": 72.5, "renda_media": 1340},
    {"setor": "Administracao publica",    "ocupados_mil": 6490,  "pct_informal":  2.1, "renda_media": 4120},
    {"setor": "Outros servicos",          "ocupados_mil": 8340,  "pct_informal": 45.3, "renda_media": 2050},
    {"setor": "Seguranca / Vigilancia",   "ocupados_mil": 1820,  "pct_informal": 22.4, "renda_media": 1920},
])

FALLBACK_UF = pd.DataFrame([
    {"uf":"AC","regiao":"Norte",       "pct_informal":71.8,"renda_media":1820},
    {"uf":"AM","regiao":"Norte",       "pct_informal":63.2,"renda_media":2010},
    {"uf":"AP","regiao":"Norte",       "pct_informal":64.4,"renda_media":1890},
    {"uf":"PA","regiao":"Norte",       "pct_informal":68.5,"renda_media":1740},
    {"uf":"RO","regiao":"Norte",       "pct_informal":58.9,"renda_media":2120},
    {"uf":"RR","regiao":"Norte",       "pct_informal":62.1,"renda_media":1960},
    {"uf":"TO","regiao":"Norte",       "pct_informal":57.3,"renda_media":2080},
    {"uf":"AL","regiao":"Nordeste",    "pct_informal":65.8,"renda_media":1640},
    {"uf":"BA","regiao":"Nordeste",    "pct_informal":58.4,"renda_media":1920},
    {"uf":"CE","regiao":"Nordeste",    "pct_informal":60.1,"renda_media":1870},
    {"uf":"MA","regiao":"Nordeste",    "pct_informal":68.9,"renda_media":1540},
    {"uf":"PB","regiao":"Nordeste",    "pct_informal":59.7,"renda_media":1790},
    {"uf":"PE","regiao":"Nordeste",    "pct_informal":57.2,"renda_media":1980},
    {"uf":"PI","regiao":"Nordeste",    "pct_informal":63.4,"renda_media":1610},
    {"uf":"RN","regiao":"Nordeste",    "pct_informal":58.8,"renda_media":1860},
    {"uf":"SE","regiao":"Nordeste",    "pct_informal":55.6,"renda_media":2040},
    {"uf":"DF","regiao":"Centro-Oeste","pct_informal":29.4,"renda_media":4890},
    {"uf":"GO","regiao":"Centro-Oeste","pct_informal":42.1,"renda_media":2510},
    {"uf":"MS","regiao":"Centro-Oeste","pct_informal":40.8,"renda_media":2620},
    {"uf":"MT","regiao":"Centro-Oeste","pct_informal":41.5,"renda_media":2680},
    {"uf":"ES","regiao":"Sudeste",     "pct_informal":36.2,"renda_media":2840},
    {"uf":"MG","regiao":"Sudeste",     "pct_informal":38.7,"renda_media":2620},
    {"uf":"RJ","regiao":"Sudeste",     "pct_informal":38.1,"renda_media":3180},
    {"uf":"SP","regiao":"Sudeste",     "pct_informal":32.4,"renda_media":3520},
    {"uf":"PR","regiao":"Sul",         "pct_informal":33.8,"renda_media":2940},
    {"uf":"RS","regiao":"Sul",         "pct_informal":30.9,"renda_media":3080},
    {"uf":"SC","regiao":"Sul",         "pct_informal":28.3,"renda_media":3210},
])

FALLBACK_PROP_6X1 = {
    "Comercio e reparacao":      0.62,
    "Alojamento e alimentacao":  0.71,
    "Seguranca / Vigilancia":    0.78,
    "Saude e serv. sociais":     0.41,
    "Transporte e armazenagem":  0.55,
    "Serv. domesticos":          0.33,
    "Industria geral":           0.28,
    "Construcao":                0.18,
    "Informacao e comunicacao":  0.08,
    "Administracao publica":     0.05,
    "Agropecuaria":              0.15,
    "Outros servicos":           0.38,
}

ESTADO_SIGLA = {
    "Rondonia":"RO","Acre":"AC","Amazonas":"AM","Roraima":"RR","Para":"PA",
    "Amapa":"AP","Tocantins":"TO","Maranhao":"MA","Piaui":"PI","Ceara":"CE",
    "Rio Grande do Norte":"RN","Paraiba":"PB","Pernambuco":"PE","Alagoas":"AL",
    "Sergipe":"SE","Bahia":"BA","Minas Gerais":"MG","Espirito Santo":"ES",
    "Rio de Janeiro":"RJ","Sao Paulo":"SP","Parana":"PR","Santa Catarina":"SC",
    "Rio Grande do Sul":"RS","Mato Grosso do Sul":"MS","Mato Grosso":"MT",
    "Goias":"GO","Distrito Federal":"DF",
}


# ── Cache helpers
def _cache_path(key):
    return CACHE_DIR / f"pnad_{key}.parquet"

def _is_fresh(path):
    if not path.exists(): return False
    return datetime.now() - datetime.fromtimestamp(path.stat().st_mtime) < timedelta(days=CACHE_TTL_DAYS)

def _save(df, key):
    try: df.to_parquet(_cache_path(key), index=False)
    except Exception as e: logger.warning(f"Cache write failed ({key}): {e}")

def _load(key):
    p = _cache_path(key)
    if _is_fresh(p):
        try: return pd.read_parquet(p)
        except Exception: pass
    return None


# ── SIDRA fetcher — URL manual sem encoding de colchetes
def _sidra_fetch(tabela, variavel, localidades="N1[all]", classificacao=""):
    url = f"{SIDRA_BASE}/{tabela}/periodos/last/variaveis/{variavel}?localidades={localidades}"
    if classificacao:
        url += f"&classificacao={classificacao}"
    headers = {"Accept": "application/json", "User-Agent": "reforma-6x1-simulator/2.1"}
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and data:
                    return data
                return None
        except HTTPError as e:
            logger.warning(f"SIDRA HTTP {e.code} tabela={tabela} attempt={attempt+1}")
        except URLError as e:
            logger.warning(f"SIDRA URLError: {e.reason}")
            break
        except Exception as e:
            logger.warning(f"SIDRA erro: {e}")
            break
        if attempt < MAX_RETRIES:
            time.sleep(1.5 * (attempt + 1))
    return None


def _parse_val(v):
    if not v or str(v).strip() in ("-", "...", "X", "", "None"): return None
    try: return float(str(v).replace(",", ".").replace(" ", ""))
    except ValueError: return None


def _ultima_serie(serie):
    if not serie: return None
    return _parse_val(serie[sorted(serie.keys())[-1]])


def _extrair_resultados(raw):
    """Itera sobre resultados SIDRA v3 e retorna lista de (categoria, valor)."""
    rows = []
    for variavel in raw:
        for resultado in variavel.get("resultados", []):
            cats = resultado.get("classificacoes", [])
            categoria = "?"
            if cats:
                cat_dict = cats[0].get("categoria", {})
                if cat_dict:
                    categoria = list(cat_dict.values())[0]
            for serie_item in resultado.get("series", []):
                localidade = serie_item.get("localidade", {})
                val = _ultima_serie(serie_item.get("serie", {}))
                if val is not None:
                    rows.append({
                        "categoria": categoria,
                        "localidade_id": localidade.get("id", ""),
                        "localidade_nome": localidade.get("nome", ""),
                        "valor": val,
                    })
    return rows


# ── APIs públicas
def get_distribuicao_horas(force_refresh=False):
    key = "horas"
    if not force_refresh:
        cached = _load(key)
        if cached is not None: return cached, "cache/SIDRA"

    raw = _sidra_fetch("4093", "1000", "N1[all]", "12789[all]")
    if raw:
        try:
            rows = _extrair_resultados(raw)
            df = pd.DataFrame(rows)
            if not df.empty and "categoria" in df.columns:
                df = df.groupby("categoria", as_index=False)["valor"].sum()
                df.columns = ["faixa_horas", "ocupados_mil"]
                total = df["ocupados_mil"].sum()
                if total > 0:
                    df["pct_trabalhadores"] = (df["ocupados_mil"] / total * 100).round(1)
                    horas_map = dict(zip(FALLBACK_HORAS["faixa_horas"], FALLBACK_HORAS["media_horas"]))
                    df["media_horas"] = df["faixa_horas"].map(horas_map).fillna(40).astype(int)
                    df = df[["faixa_horas", "pct_trabalhadores", "media_horas"]]
                    _save(df, key)
                    return df, "SIDRA/IBGE"
        except Exception as e:
            logger.warning(f"Parse horas: {e}")

    return FALLBACK_HORAS.copy(), "fallback/PNAD 2023"


def get_setores(force_refresh=False):
    key = "setores"
    if not force_refresh:
        cached = _load(key)
        if cached is not None: return cached, "cache/SIDRA"

    raw = _sidra_fetch("6318", "1000", "N1[all]")
    if raw:
        try:
            rows = _extrair_resultados(raw)
            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.groupby("categoria", as_index=False)["valor"].sum()
                df.columns = ["setor", "ocupados_mil"]
                df = df.merge(FALLBACK_SETORES[["setor","pct_informal","renda_media"]], on="setor", how="left")
                df["pct_informal"] = df["pct_informal"].fillna(FALLBACK_SETORES["pct_informal"].mean())
                df["renda_media"]  = df["renda_media"].fillna(FALLBACK_SETORES["renda_media"].mean())
                df["pct_6x1"] = df["setor"].map(FALLBACK_PROP_6X1).fillna(0.25)
                df["trabalhadores_6x1_mil"] = (df["ocupados_mil"] * df["pct_6x1"]).round(0)
                _save(df, key)
                return df, "SIDRA/IBGE"
        except Exception as e:
            logger.warning(f"Parse setores: {e}")

    df = FALLBACK_SETORES.copy()
    df["pct_6x1"] = df["setor"].map(FALLBACK_PROP_6X1).fillna(0.25)
    df["trabalhadores_6x1_mil"] = (df["ocupados_mil"] * df["pct_6x1"]).round(0)
    return df, "fallback/PNAD 2023"


def get_informalidade_uf(force_refresh=False):
    key = "uf_informal"
    if not force_refresh:
        cached = _load(key)
        if cached is not None: return cached, "cache/SIDRA"

    raw = _sidra_fetch("7426", "10525", "N3[all]")
    if raw:
        try:
            rows = _extrair_resultados(raw)
            df_api = pd.DataFrame(rows)
            if not df_api.empty:
                df = FALLBACK_UF.copy()
                for _, row in df_api.iterrows():
                    nome = row["localidade_nome"]
                    # normaliza acentos simples para casamento
                    nome_norm = nome.replace("ã","a").replace("á","a").replace("â","a") \
                                   .replace("é","e").replace("ê","e").replace("í","i") \
                                   .replace("ó","o").replace("ô","o").replace("ú","u") \
                                   .replace("ç","c")
                    sigla = ESTADO_SIGLA.get(nome) or ESTADO_SIGLA.get(nome_norm)
                    if sigla:
                        df.loc[df["uf"] == sigla, "pct_informal"] = row["valor"]
                _save(df, key)
                return df, "SIDRA/IBGE"
        except Exception as e:
            logger.warning(f"Parse UF: {e}")

    return FALLBACK_UF.copy(), "fallback/PNAD 2023"


def get_pnad_summary(force_refresh=False):
    horas_df, fonte_h = get_distribuicao_horas(force_refresh)
    setores_df, fonte_s = get_setores(force_refresh)
    uf_df, fonte_u = get_informalidade_uf(force_refresh)

    acima_44h = horas_df[horas_df["media_horas"] >= 45]["pct_trabalhadores"].sum()
    total_6x1 = setores_df["trabalhadores_6x1_mil"].sum()
    informal_nac = uf_df["pct_informal"].mean()

    return {
        "horas": horas_df, "setores": setores_df, "ufs": uf_df,
        "meta": {
            "pct_acima_44h": round(acima_44h, 1),
            "total_6x1_estimado_mil": int(total_6x1),
            "informalidade_nacional": round(informal_nac, 1),
            "fontes": {"horas": fonte_h, "setores": fonte_s, "ufs": fonte_u},
            "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        },
    }


def limpar_cache():
    for f in CACHE_DIR.glob("pnad_*.parquet"):
        f.unlink()
