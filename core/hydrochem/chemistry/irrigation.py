"""Indices de calidad del agua para riego agricola.

Calcula los principales parametros hidroquimicos para evaluar riesgos de
salinizacion y sodificacion del suelo:
- SAR (Sodium Adsorption Ratio / Relacion de Adsorcion de Sodio)
- RSC (Residual Sodium Carbonate / Carbonato de Sodio Residual)
- %Na (Porcentaje de sodio soluble)
- KR (Kelley's Ratio / Relacion de Kelley)
- MR (Magnesium Hazard / Relacion de Magnesio)
- Clasificacion combinada de Wilcox (Conductividad/TDS vs %Na)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_sar(na_meq: pd.Series, ca_meq: pd.Series, mg_meq: pd.Series) -> pd.Series:
    """Calcula el SAR (Sodium Adsorption Ratio).

    SAR = Na / sqrt((Ca + Mg) / 2) con concentraciones en meq/L.
    """
    denom = np.sqrt(np.maximum((ca_meq + mg_meq) / 2.0, 1e-9))
    sar = na_meq / denom
    sar[ca_meq.isna() | mg_meq.isna() | na_meq.isna()] = np.nan
    return sar


def classify_sar(sar: float | None) -> dict[str, str]:
    """Clasifica el SAR segun la norma del Laboratorio de Salinidad de EE.UU. (USSL)."""
    if sar is None or np.isnan(sar):
        return {"class": "Desconocido", "hazard": "Sin datos", "description": "Faltan cationes"}
    if sar < 10.0:
        return {"class": "S1", "hazard": "Bajo", "description": "Agua excelente para casi cualquier cultivo y suelo."}
    if sar < 18.0:
        return {"class": "S2", "hazard": "Medio", "description": "Apta en suelos de textura gruesa o con buena permeabilidad."}
    if sar < 26.0:
        return {"class": "S3", "hazard": "Alto", "description": "Riesgo apreciable de dispersion de arcillas. Requiere enmiendas de yeso."}
    return {"class": "S4", "hazard": "Muy Alto", "description": "Inadecuada en condiciones ordinarias; peligro severo de sodificacion."}


def compute_rsc(hco3_meq: pd.Series, co3_meq: pd.Series, ca_meq: pd.Series, mg_meq: pd.Series) -> pd.Series:
    """Calcula el Carbonato de Sodio Residual (RSC).

    RSC = (HCO3 + CO3) - (Ca + Mg) en meq/L (Eaton, 1950).
    """
    co3 = co3_meq.fillna(0.0)
    rsc = (hco3_meq + co3) - (ca_meq + mg_meq)
    rsc[hco3_meq.isna() | ca_meq.isna() | mg_meq.isna()] = np.nan
    return rsc


def classify_rsc(rsc: float | None) -> dict[str, str]:
    """Clasifica el RSC segun Eaton (1950) y Richards (1954)."""
    if rsc is None or np.isnan(rsc):
        return {"class": "Desconocido", "hazard": "Sin datos", "description": "Faltan iones"}
    if rsc < 1.25:
        return {"class": "Seguro", "hazard": "Bajo", "description": "Buena calidad; no hay riesgo de precipitacion de Ca y Mg."}
    if rsc <= 2.50:
        return {"class": "Marginal", "hazard": "Moderado", "description": "Uso con precaucion y buen drenaje."}
    return {"class": "Inadecuado", "hazard": "Severo", "description": "Peligro severo: precipita Ca y Mg elevando el sodio relativo."}


def compute_na_pct(na_meq: pd.Series, k_meq: pd.Series, ca_meq: pd.Series, mg_meq: pd.Series) -> pd.Series:
    """Porcentaje de Sodio Soluble (%Na).

    %Na = ((Na + K) / (Ca + Mg + Na + K)) * 100 en meq/L.
    """
    k = k_meq.fillna(0.0)
    total_cat = ca_meq + mg_meq + na_meq + k
    pct = ((na_meq + k) / np.maximum(total_cat, 1e-9)) * 100.0
    pct[(total_cat <= 0) | na_meq.isna() | ca_meq.isna() | mg_meq.isna()] = np.nan
    return pct


def compute_kelley_ratio(na_meq: pd.Series, ca_meq: pd.Series, mg_meq: pd.Series) -> pd.Series:
    """Relacion de Kelley (KR).

    KR = Na / (Ca + Mg). Valores > 1 indican exceso de sodio (Kelley, 1940).
    """
    kr = na_meq / np.maximum(ca_meq + mg_meq, 1e-9)
    kr[ca_meq.isna() | mg_meq.isna() | na_meq.isna()] = np.nan
    return kr


def compute_magnesium_ratio(mg_meq: pd.Series, ca_meq: pd.Series) -> pd.Series:
    """Riesgo de Magnesio / Magnesium Hazard (MR).

    MR = (Mg / (Ca + Mg)) * 100. Valores > 50 % indican deterioro del suelo (Szabolcs, 1964).
    """
    mr = (mg_meq / np.maximum(ca_meq + mg_meq, 1e-9)) * 100.0
    mr[ca_meq.isna() | mg_meq.isna()] = np.nan
    return mr


def classify_wilcox(na_pct: float | None, ec_or_tds: float | None) -> dict[str, str]:
    """Clasificacion combinada segun el diagrama de Wilcox (1955)."""
    if na_pct is None or np.isnan(na_pct) or ec_or_tds is None or np.isnan(ec_or_tds):
        return {"class": "Sin datos", "category": "Desconocido"}
    ec = ec_or_tds if ec_or_tds > 10000 or ec_or_tds < 50 else ec_or_tds / 0.64
    if na_pct < 20.0 and ec < 250.0:
        return {"class": "Excelente", "category": "Excelente a Buena"}
    if na_pct < 40.0 and ec < 750.0:
        return {"class": "Buena", "category": "Buena a Permisible"}
    if na_pct < 60.0 and ec < 2000.0:
        return {"class": "Permisible", "category": "Permisible a Dudosa"}
    if na_pct < 80.0 and ec < 3000.0:
        return {"class": "Dudosa", "category": "Dudosa a Inadecuada"}
    return {"class": "Inadecuada", "category": "Inadecuada para riego"}


def add_irrigation_indices(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula todos los indices de riego e incorpora columnas estandarizadas al DataFrame."""
    out = df.copy()
    req = ["Na_meq", "Ca_meq", "Mg_meq"]
    if not all(c in out.columns for c in req):
        return out

    k_meq = out["K_meq"] if "K_meq" in out.columns else pd.Series(0.0, index=out.index)
    co3_meq = out["CO3_meq"] if "CO3_meq" in out.columns else pd.Series(0.0, index=out.index)
    hco3_meq = out["HCO3_meq"] if "HCO3_meq" in out.columns else pd.Series(np.nan, index=out.index)

    out["SAR"] = compute_sar(out["Na_meq"], out["Ca_meq"], out["Mg_meq"])
    out["SAR_class"] = [classify_sar(v)["class"] for v in out["SAR"]]

    out["RSC"] = compute_rsc(hco3_meq, co3_meq, out["Ca_meq"], out["Mg_meq"])
    out["RSC_class"] = [classify_rsc(v)["class"] for v in out["RSC"]]

    out["Na_pct"] = compute_na_pct(out["Na_meq"], k_meq, out["Ca_meq"], out["Mg_meq"])
    out["Kelley_ratio"] = compute_kelley_ratio(out["Na_meq"], out["Ca_meq"], out["Mg_meq"])
    out["Magnesium_ratio"] = compute_magnesium_ratio(out["Mg_meq"], out["Ca_meq"])

    tds_col = "tds_mgl" if "tds_mgl" in out.columns else None
    wilcox_classes = []
    for idx, row in out.iterrows():
        tds_val = row.get(tds_col) if tds_col else None
        wilcox_classes.append(classify_wilcox(row["Na_pct"], tds_val)["category"])
    out["Wilcox_class"] = wilcox_classes

    return out
