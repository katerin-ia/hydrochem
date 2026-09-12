"""Regresión del balance de carga contra la columna Q del libro Excel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.balance import (
    CBE_COL,
    CBE_FLAG_COL,
    ChargeBalanceFlag,
    add_charge_balance,
    charge_balance_error,
    classify_charge_balance,
    summary,
)
from hydrochem.chemistry.units import add_meq_columns


def _prepared(ew_table: str = "PiperStiff-v9") -> pd.DataFrame:
    return add_meq_columns(load_amargosa(), ions=FIXTURE_IONS, ew_table=ew_table)


def test_cbe_reproduces_excel_column_q():
    """El libro expresa el CBE como fracción; aquí como porcentaje."""
    df = add_charge_balance(_prepared())
    got = df[CBE_COL].to_numpy()
    expected = df["xl_charge_balance"].to_numpy() * 100.0
    assert np.allclose(got, expected, rtol=1e-10, atol=1e-10), (
        f"desviación máxima {np.nanmax(np.abs(got - expected)):.3e} puntos porcentuales"
    )


def test_cbe_as_fraction_matches_excel_convention():
    df = _prepared()
    frac = charge_balance_error(df["sum_cat"], df["sum_an"], as_fraction=True)
    assert np.allclose(frac, df["xl_charge_balance"], rtol=1e-10, atol=1e-12)


def test_all_amargosa_samples_are_acceptable():
    """Ninguno de los 90 sitios supera el ±5 % — coincide con el libro, que
    resalta las filas que exceden el umbral y no resalta ninguna."""
    df = add_charge_balance(_prepared())
    counts = summary(df[CBE_FLAG_COL])
    assert counts["acceptable"] == 90
    assert counts["marginal"] == 0
    assert counts["rejected"] == 0


def test_twenty_samples_exceed_two_percent():
    """Contraste independiente: el umbral de 2 % separa 20 de las 90 muestras."""
    df = add_charge_balance(_prepared())
    assert int((df[CBE_COL].abs() > 2.0).sum()) == 20


def test_classification_thresholds():
    cbe = pd.Series([0.0, 4.9, -5.0, 5.1, -9.9, 10.0, 10.1, -30.0, np.nan])
    flags = classify_charge_balance(cbe).tolist()
    assert flags == [
        "acceptable", "acceptable", "acceptable",
        "marginal", "marginal", "marginal",
        "rejected", "rejected",
        "unknown",
    ]


def test_zero_total_gives_nan_not_division_error():
    cbe = charge_balance_error(pd.Series([0.0]), pd.Series([0.0]))
    assert pd.isna(cbe.iloc[0])


def test_missing_sums_give_nan():
    cbe = charge_balance_error(pd.Series([np.nan]), pd.Series([3.0]))
    assert pd.isna(cbe.iloc[0])


def test_unreliable_mask_overrides_a_good_looking_cbe():
    """Un CBE excelente sobre datos imputados no debe presentarse como aceptable."""
    df = _prepared().head(3)
    mask = pd.Series([True, False, False], index=df.index)
    out = add_charge_balance(df, unreliable_mask=mask)
    assert out[CBE_FLAG_COL].iloc[0] == ChargeBalanceFlag.UNKNOWN.value
    assert out[CBE_FLAG_COL].iloc[1] == ChargeBalanceFlag.ACCEPTABLE.value


def test_add_charge_balance_requires_sums():
    try:
        add_charge_balance(pd.DataFrame({"Ca_meq": [1.0]}))
    except KeyError as exc:
        assert "add_meq_columns" in str(exc)
    else:
        raise AssertionError("debería haber lanzado KeyError")


def test_flag_labels_are_human_readable():
    assert ChargeBalanceFlag.ACCEPTABLE.label_es.startswith("Aceptable")
    assert "%" in ChargeBalanceFlag.REJECTED.label_es
