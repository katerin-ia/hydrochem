"""Lectura de valores censurados. Regresion del riesgo R9."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hydrochem.io.detection_limits import (
    apply_to_frame,
    parse_series,
    parse_value,
)


def test_plain_numbers():
    for raw, expected in [(45.0, 45.0), (45, 45.0), ("45", 45.0), ("45.5", 45.5), (" 0.9 ", 0.9)]:
        p = parse_value(raw)
        assert p.value == expected
        assert p.analysed
        assert not p.is_censored


def test_comma_decimal_separator():
    """Habitual en hojas de calculo en espanol; el manual del libro PiperStiff
    documenta un bug historico por este mismo motivo."""
    assert parse_value("0,9").value == 0.9
    assert parse_value("1.234,5").value == 1234.5
    assert parse_value("1,234.5").value == 1234.5


def test_scientific_notation():
    assert parse_value("1.2e3").value == 1200.0


def test_below_detection_limit_keeps_the_threshold():
    p = parse_value("<0.05")
    assert math.isnan(p.value), "no hay un valor medido"
    assert p.detection_limit == 0.05
    assert p.qualifier == "<"
    assert p.analysed, "si se analizo: eso es lo que el notebook perdia"
    assert p.is_censored


def test_below_detection_limit_variants():
    for raw in ("<0.05", "< 0.05", "<=0.05", "<0,05"):
        p = parse_value(raw)
        assert p.detection_limit == 0.05, raw
        assert p.analysed, raw


def test_above_range():
    p = parse_value(">1000")
    assert p.detection_limit == 1000.0
    assert p.qualifier == ">"
    assert p.analysed


def test_not_detected_without_threshold():
    for raw in ("ND", "nd", "n.d.", "no detectado", "BDL"):
        p = parse_value(raw)
        assert p.qualifier == "nd", raw
        assert p.analysed, raw
        assert math.isnan(p.detection_limit), raw


def test_not_analysed_is_distinct_from_not_detected():
    """La distincion que da sentido a todo el modulo."""
    for raw in ("", "-", "NA", "n/a", "s/d", None, float("nan"), np.nan):
        p = parse_value(raw)
        assert not p.analysed, repr(raw)
        assert p.qualifier is None, repr(raw)


def test_garbage_is_treated_as_not_analysed():
    for raw in ("pendiente", "ver nota 3", "???"):
        assert not parse_value(raw).analysed, raw


def test_parse_series_shape():
    s = pd.Series(["1.5", "<0.05", "ND", "", 2.0])
    out = parse_series(s)
    assert list(out.columns) == ["value", "detection_limit", "qualifier", "analysed"]
    assert out["value"].tolist()[0] == 1.5
    assert out["detection_limit"].iloc[1] == 0.05
    assert out["analysed"].tolist() == [True, True, True, False, True]


def test_apply_to_frame_adds_detection_limit_column_only_when_needed():
    df = pd.DataFrame({"F_mgL": ["<0.05", "1.2", "ND"], "Ca_mgL": ["40", "41", "42"]})
    data, report = apply_to_frame(df, ["F_mgL", "Ca_mgL"])
    assert "F_mgL__detection_limit" in data.columns
    assert "Ca_mgL__detection_limit" not in data.columns, "Ca no trae censura"
    assert data["F_mgL"].tolist()[1] == 1.2
    assert data["Ca_mgL"].tolist() == [40.0, 41.0, 42.0]


def test_apply_to_frame_report_counts():
    df = pd.DataFrame({"F_mgL": ["<0.05", "1.2", "ND", "", "0.9"]})
    _, report = apply_to_frame(df, ["F_mgL"])
    row = report.iloc[0]
    assert row["n_censored"] == 1
    assert row["n_not_detected"] == 1
    assert row["n_not_analysed"] == 1
    assert row["n_numeric"] == 2


def test_censored_values_can_feed_half_detection_limit_imputation():
    """Encadenado con la capa de imputacion: es el flujo completo que el
    notebook describia en su celda 11 pero no implementaba."""
    from hydrochem.imputation.strategies import impute

    df = pd.DataFrame({"F_mgL": ["<0.05", "1.2"]})
    data, _ = apply_to_frame(df, ["F_mgL"])
    res = impute(data, ["F_mgL"], "half_detection_limit")
    assert res.data["F_mgL"].iloc[0] == 0.025
    assert res.flags["F_mgL"].iloc[0]


def test_missing_column_is_ignored():
    df = pd.DataFrame({"Ca_mgL": [1.0]})
    data, report = apply_to_frame(df, ["Ca_mgL", "NO3_mgL"])
    assert len(report) == 1
    assert data.shape == df.shape
