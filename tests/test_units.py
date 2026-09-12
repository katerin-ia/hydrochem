"""Regresión de la conversión mg/L → meq/L contra las columnas R–Z del libro Excel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.units import (
    SUM_ANIONS_COL,
    SUM_CATIONS_COL,
    add_meq_columns,
    add_mmol_columns,
    equivalent_weight_table,
    meq_column,
    mgl_to_meq,
)
from hydrochem.constants import IUPAC2021, PIPERSTIFF_V9, equivalent_weights


def test_fixture_shape():
    df = load_amargosa()
    assert len(df) == 90, "el libro Excel tiene 90 sitios en las filas 15-104"
    assert df["Site"].nunique() == 90, "los nombres de sitio son únicos"
    assert df[[f"{i}_mgL" for i in FIXTURE_IONS]].isna().sum().sum() == 0


def test_meq_reproduces_excel_exactly_with_piperstiff_table():
    """Con la tabla del propio libro, los meq/L deben coincidir bit a bit."""
    df = add_meq_columns(load_amargosa(), ions=FIXTURE_IONS, ew_table="PiperStiff-v9")
    for ion in FIXTURE_IONS:
        got = df[meq_column(ion)].to_numpy()
        expected = df[f"xl_{ion}_meq"].to_numpy()
        assert np.allclose(got, expected, rtol=1e-12, atol=1e-12), (
            f"{ion}: desviación máxima {np.nanmax(np.abs(got - expected)):.3e}"
        )


def test_meq_with_iupac_table_stays_within_0_1_percent():
    """La tabla canónica IUPAC difiere de la del libro en menos del 0,1 %."""
    df = add_meq_columns(load_amargosa(), ions=FIXTURE_IONS, ew_table="IUPAC2021")
    for ion in FIXTURE_IONS:
        expected = df[f"xl_{ion}_meq"].to_numpy()
        got = df[meq_column(ion)].to_numpy()
        nonzero = expected != 0
        rel = np.abs(got[nonzero] - expected[nonzero]) / expected[nonzero]
        assert rel.max() < 1e-3, f"{ion}: desviación relativa {rel.max():.2e}"


def test_sums_only_count_present_ions():
    """NO₃ no está medido: no debe aparecer ni contarse como cero."""
    df = add_meq_columns(load_amargosa(), ions=FIXTURE_IONS)
    assert meq_column("NO3") not in df.columns
    expected_cat = df[[meq_column(i) for i in ("Ca", "Mg", "Na", "K")]].sum(axis=1)
    expected_an = df[[meq_column(i) for i in ("HCO3", "CO3", "SO4", "Cl", "F")]].sum(axis=1)
    assert np.allclose(df[SUM_CATIONS_COL], expected_cat)
    assert np.allclose(df[SUM_ANIONS_COL], expected_an)


def test_missing_ion_column_is_skipped_not_invented():
    df = pd.DataFrame({"Ca_mgL": [40.0], "Cl_mgL": [35.45]})
    out = add_meq_columns(df, ions=("Ca", "Cl", "NO3"))
    assert meq_column("NO3") not in out.columns
    assert len(out) == 1


def test_all_nan_row_does_not_become_zero():
    """min_count=1: una fila sin ninguna medida da NaN, no un falso 0."""
    df = pd.DataFrame({"Ca_mgL": [np.nan], "Mg_mgL": [np.nan]})
    out = add_meq_columns(df, ions=("Ca", "Mg"))
    assert pd.isna(out[SUM_CATIONS_COL].iloc[0])


def test_scalar_conversion():
    assert mgl_to_meq(40.078, "Ca", "IUPAC2021") == 40.078 / IUPAC2021["Ca"]
    assert mgl_to_meq(61.0, "HCO3", "PiperStiff-v9") == 1.0


def test_mmol_columns():
    out = add_mmol_columns(load_amargosa(), ions=("Ca",))
    assert np.allclose(out["Ca_mmol"], out["Ca_mgL"] / 40.078)


def test_unknown_ew_table_raises():
    try:
        equivalent_weights("no-existe")
    except KeyError as exc:
        assert "IUPAC2021" in str(exc)
    else:
        raise AssertionError("debería haber lanzado KeyError")


def test_equivalent_weight_table_is_presentable():
    tbl = equivalent_weight_table("IUPAC2021")
    assert len(tbl) == len(IUPAC2021)
    assert set(tbl.columns) >= {"ion", "peso_equivalente_g_eq", "tipo"}
    assert (tbl["tipo"] == "catión").sum() == 4


def test_two_tables_are_distinct_and_documented():
    assert IUPAC2021 != PIPERSTIFF_V9
    assert set(IUPAC2021) == set(PIPERSTIFF_V9)
