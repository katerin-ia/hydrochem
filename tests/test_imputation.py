"""Imputacion y registro de procedencia. Regresion de los riesgos R3 y R4."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.imputation.strategies import (
    ImputationMethod,
    count_exact_zeros,
    impute,
    zeros_as_missing,
)

ION_COLS = [f"{i}_mgL" for i in FIXTURE_IONS]


def _with_empty_no3() -> pd.DataFrame:
    """El caso real: el notebook anadia NO3 vacio y lo acababa imputando a 0."""
    df = load_amargosa()
    df["NO3_mgL"] = np.nan
    return df


# -- R4: columna vacia al 100 % ---------------------------------------------


def test_fully_empty_column_is_never_imputed():
    df = _with_empty_no3()
    res = impute(df, ION_COLS + ["NO3_mgL"], "group_median", group_col="Group")
    assert res.data["NO3_mgL"].isna().all(), "NO3 no se midio: debe seguir ausente"
    assert "NO3_mgL" in res.skipped_columns
    assert not res.flags["NO3_mgL"].any()


def test_fully_empty_column_is_explained_not_silently_dropped():
    res = impute(_with_empty_no3(), ION_COLS + ["NO3_mgL"], "group_median", group_col="Group")
    msg = [m for m in res.messages_es() if m.startswith("NO3_mgL")]
    assert len(msg) == 1
    assert "no se midio" in msg[0]


def test_never_falls_back_to_zero():
    """El notebook terminaba la cascada en 0.0. Aqui, sin base estadistica, el
    valor sigue ausente."""
    df = pd.DataFrame({"Group": ["A", "A"], "Ca_mgL": [np.nan, np.nan]})
    res = impute(df, ["Ca_mgL"], "group_median", group_col="Group")
    assert res.data["Ca_mgL"].isna().all()
    assert (res.data["Ca_mgL"] != 0).all() or res.data["Ca_mgL"].isna().all()


def test_knn_also_skips_fully_empty_columns():
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return  # entorno sin scikit-learn: nada que comprobar
    res = impute(_with_empty_no3(), ION_COLS + ["NO3_mgL"], "knn")
    assert "NO3_mgL" in res.skipped_columns
    assert res.data["NO3_mgL"].isna().all()


# -- estrategias ------------------------------------------------------------


def test_none_is_the_default_and_changes_nothing():
    df = _with_empty_no3()
    res = impute(df, ION_COLS, ImputationMethod.NONE)
    assert res.n_imputed == 0
    assert res.data[ION_COLS].equals(df[ION_COLS])


def test_group_median_fills_from_the_same_group():
    df = pd.DataFrame({
        "Group": ["A", "A", "A", "B", "B", "B"],
        "Ca_mgL": [10.0, 20.0, np.nan, 100.0, 200.0, 300.0],
    })
    res = impute(df, ["Ca_mgL"], "group_median", group_col="Group", min_group_size=2)
    assert res.data["Ca_mgL"].iloc[2] == 15.0, "mediana de A, no la global"
    assert res.flags["Ca_mgL"].tolist() == [False, False, True, False, False, False]


def test_group_median_refuses_tiny_groups():
    """Con 2 o 3 muestras la mediana de grupo no es robusta (riesgo R14).
    El dataset real tiene grupos de 2 y 3 sitios."""
    df = pd.DataFrame({"Group": ["Furnace Creek"] * 3, "Ca_mgL": [43.0, np.nan, 39.0]})
    res = impute(df, ["Ca_mgL"], "group_median", group_col="Group", min_group_size=5)
    assert res.data["Ca_mgL"].isna().iloc[1], "grupo demasiado pequeno: no se imputa"
    res_ok = impute(df, ["Ca_mgL"], "group_median", group_col="Group", min_group_size=2)
    assert res_ok.data["Ca_mgL"].iloc[1] == 41.0


def test_global_median_ignores_groups():
    df = pd.DataFrame({
        "Group": ["A", "A", "B", "B"],
        "Ca_mgL": [10.0, 20.0, 100.0, np.nan],
    })
    res = impute(df, ["Ca_mgL"], "global_median")
    assert res.data["Ca_mgL"].iloc[3] == 20.0


def test_half_detection_limit_uses_the_declared_limit():
    df = pd.DataFrame({
        "F_mgL": [np.nan, 1.2],
        "F_mgL__detection_limit": [0.05, np.nan],
    })
    res = impute(df, ["F_mgL"], "half_detection_limit")
    assert res.data["F_mgL"].iloc[0] == 0.025
    assert res.flags["F_mgL"].tolist() == [True, False]


# -- procedencia ------------------------------------------------------------


def test_flags_mark_exactly_the_imputed_cells():
    df = _with_empty_no3()
    df.loc[0, "Ca_mgL"] = np.nan
    df.loc[5, "Mg_mgL"] = np.nan
    res = impute(df, ION_COLS, "group_median", group_col="Group", min_group_size=2)
    assert res.n_imputed == 2
    assert res.flags.loc[0, "Ca_mgL"]
    assert res.flags.loc[5, "Mg_mgL"]
    assert not res.flags.loc[1, "Ca_mgL"]


def test_amargosa_needs_no_imputation_at_all():
    """Los 90 sitios tienen los nueve iones medidos; no debe estimarse nada."""
    res = impute(load_amargosa(), ION_COLS, "group_median", group_col="Group")
    assert res.n_imputed == 0
    assert res.imputed_columns == []


def test_reliability_uses_the_original_data_not_the_imputed_one():
    df = pd.DataFrame({
        "Group": ["A"] * 4,
        "Ca_mgL": [10.0, np.nan, 12.0, 11.0],
        "Mg_mgL": [1.0, np.nan, 2.0, 1.5],
        "Na_mgL": [5.0, np.nan, 6.0, 5.5],
        "K_mgL": [1.0, np.nan, 1.2, 1.1],
        "HCO3_mgL": [100.0, 110.0, 120.0, 115.0],
        "SO4_mgL": [20.0, 21.0, 22.0, 23.0],
        "Cl_mgL": [5.0, 6.0, 7.0, 8.0],
    })
    cols = [c for c in df.columns if c.endswith("_mgL")]
    res = impute(df, cols, "group_median", group_col="Group", min_group_size=2)
    assert res.reliability is not None
    assert not bool(res.reliability.iloc[1]), "le faltaban 4 iones mayoritarios"
    assert bool(res.reliability.iloc[0])


# -- R3: ceros que significan "no medido" -----------------------------------


def test_amargosa_has_thirty_two_fluoride_zeros():
    zeros = count_exact_zeros(load_amargosa(), ION_COLS)
    assert zeros["F_mgL"] == 32
    assert zeros["CO3_mgL"] == 87


def test_zeros_as_missing_is_opt_in_and_reversible():
    df = load_amargosa()
    assert (df["F_mgL"] == 0).sum() == 32
    converted = zeros_as_missing(df, ["F_mgL"])
    assert converted["F_mgL"].isna().sum() == 32
    assert df["F_mgL"].isna().sum() == 0, "el original no se toca"


def test_zeros_as_missing_only_touches_the_named_columns():
    df = load_amargosa()
    converted = zeros_as_missing(df, ["F_mgL"])
    assert (converted["CO3_mgL"] == 0).sum() == 87, "CO3 no estaba en la lista"


def test_fluoride_after_conversion_can_then_be_imputed_or_left_missing():
    df = zeros_as_missing(load_amargosa(), ["F_mgL"])
    res = impute(df, ION_COLS, "group_median", group_col="Group", min_group_size=3)
    assert res.flags["F_mgL"].sum() > 0, "ahora si hay que decidir que hacer con ellos"
    assert res.data["F_mgL"].notna().sum() > 58
