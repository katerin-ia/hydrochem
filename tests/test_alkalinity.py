"""Alcalinidad como CaCO₃."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.alkalinity import ALKALINITY_COL, add_alkalinity
from hydrochem.chemistry.units import add_meq_columns


def test_alkalinity_matches_manual_formula():
    df = add_meq_columns(load_amargosa(), ions=FIXTURE_IONS, ew_table="PiperStiff-v9")
    out = add_alkalinity(df)
    expected = (out["HCO3_meq"] + out["CO3_meq"]) * 50.04
    assert np.allclose(out[ALKALINITY_COL], expected)


def test_known_value():
    """1 meq/L de HCO₃ equivale a 50,04 mg/L de CaCO₃."""
    out = add_alkalinity(pd.DataFrame({"HCO3_meq": [1.0]}))
    assert out[ALKALINITY_COL].iloc[0] == 50.04


def test_carbonate_is_optional():
    """Un dataset sin CO₃ debe calcular alcalinidad, no fallar."""
    out = add_alkalinity(pd.DataFrame({"HCO3_meq": [2.0]}))
    assert out[ALKALINITY_COL].iloc[0] == 100.08


def test_requires_bicarbonate():
    try:
        add_alkalinity(pd.DataFrame({"CO3_meq": [1.0]}))
    except KeyError as exc:
        assert "HCO3_meq" in str(exc)
    else:
        raise AssertionError("debería haber lanzado KeyError")


def test_amargosa_range_is_plausible():
    """Extremos conocidos: UE-29a 2 HTH (HCO₃ 107, CO₃ 0) y Death Valley
    Junction Well (HCO₃ 525, CO₃ 45), las únicas muestras con CO₃ apreciable."""
    df = add_meq_columns(load_amargosa(), ions=FIXTURE_IONS)
    out = add_alkalinity(df)
    assert round(float(out[ALKALINITY_COL].min()), 2) == 87.75
    assert round(float(out[ALKALINITY_COL].max()), 2) == 505.61
    assert out.loc[out[ALKALINITY_COL].idxmax(), "Site"] == "Death Valley Junction Well"
