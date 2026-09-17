"""Pruebas para indices de riego (SAR, RSC, %Na, Wilcox)."""

import numpy as np
import pandas as pd
from hydrochem.chemistry.irrigation import (
    compute_sar,
    classify_sar,
    compute_rsc,
    classify_rsc,
    compute_na_pct,
    compute_kelley_ratio,
    compute_magnesium_ratio,
    classify_wilcox,
    add_irrigation_indices,
)


def test_sar_calculation():
    # Na = 5 meq/L, Ca = 4 meq/L, Mg = 2 meq/L
    # SAR = 5 / sqrt((4 + 2) / 2) = 5 / sqrt(3) ~= 2.8867
    na = pd.Series([5.0])
    ca = pd.Series([4.0])
    mg = pd.Series([2.0])
    sar = compute_sar(na, ca, mg)
    assert np.isclose(sar.iloc[0], 5.0 / np.sqrt(3.0))
    cls = classify_sar(sar.iloc[0])
    assert cls["class"] == "S1"


def test_rsc_calculation():
    # HCO3 = 4, CO3 = 0, Ca = 2, Mg = 1 -> RSC = 4 - 3 = 1.0 (Seguro)
    hco3 = pd.Series([4.0])
    co3 = pd.Series([0.0])
    ca = pd.Series([2.0])
    mg = pd.Series([1.0])
    rsc = compute_rsc(hco3, co3, ca, mg)
    assert np.isclose(rsc.iloc[0], 1.0)
    cls = classify_rsc(rsc.iloc[0])
    assert cls["class"] == "Seguro"


def test_add_irrigation_indices():
    df = pd.DataFrame({
        "station_code": ["PZ-01"],
        "Na_meq": [4.0],
        "Ca_meq": [3.0],
        "Mg_meq": [2.0],
        "K_meq": [0.5],
        "HCO3_meq": [3.5],
        "tds_mgl": [450.0],
    })
    res = add_irrigation_indices(df)
    assert "SAR" in res.columns
    assert "RSC" in res.columns
    assert "Na_pct" in res.columns
    assert "Kelley_ratio" in res.columns
    assert "Magnesium_ratio" in res.columns
    assert "Wilcox_class" in res.columns
