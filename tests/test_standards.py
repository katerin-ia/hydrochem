"""Umbrales normativos y excedencias."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import load_amargosa
from hydrochem.pipeline import AnalysisOptions, analyse
from hydrochem.quality.standards import (
    DEFAULT_STANDARD,
    STANDARDS,
    LimitKind,
    add_compliance,
    available,
    check,
    custom_standard,
    exceeding_mask,
    get_standard,
)

XLSM = "tests/fixtures/PiperStiff-QW-2019.v9.xlsm"


def _analysed(zeros=()):
    return analyse(XLSM, AnalysisOptions(zeros_as_missing_for=zeros))


# -- catalogo ---------------------------------------------------------------


def test_who_is_the_default_and_is_marked_verified():
    assert DEFAULT_STANDARD == "who_drinking"
    std = get_standard()
    assert std.verified, "los valores de la OMS si estan cotejados"
    assert "World Health Organization" in std.source


def test_peru_template_is_marked_unverified():
    """Un limite normativo equivocado en un informe tiene consecuencias, asi que
    la plantilla peruana se distribuye avisando de que hay que cotejarla."""
    std = get_standard("peru_drinking_template")
    assert not std.verified
    assert "cotejada" in std.source.lower() or "verifica" in std.source.lower()
    assert "PLANTILLA" in std.name_es


def test_who_fluoride_limit_is_one_point_five():
    lim = get_standard("who_drinking").limit_for("F_mgL")
    assert lim is not None
    assert lim.maximum == 1.5
    assert lim.kind is LimitKind.HEALTH


def test_limits_separate_health_from_aesthetic():
    """Contar juntos un limite sanitario y uno de sabor no dice nada util."""
    std = get_standard("who_drinking")
    kinds = {lim.parameter: lim.kind for lim in std.limits}
    assert kinds["F_mgL"] is LimitKind.HEALTH
    assert kinds["NO3_mgL"] is LimitKind.HEALTH
    assert kinds["Cl_mgL"] is LimitKind.AESTHETIC
    assert kinds["SO4_mgL"] is LimitKind.AESTHETIC
    assert kinds["ph"] is LimitKind.OPERATIONAL


def test_ph_has_a_range_not_a_maximum():
    lim = get_standard("who_drinking").limit_for("ph")
    assert lim.minimum == 6.5 and lim.maximum == 8.5
    assert "–" in lim.range_text


def test_unknown_standard_raises():
    try:
        get_standard("no-existe")
    except KeyError as exc:
        assert "who_drinking" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado KeyError")


def test_available_lists_every_standard():
    lista = available()
    assert {s["key"] for s in lista} == set(STANDARDS)
    assert all("verified" in s for s in lista)


# -- comprobacion de umbrales ----------------------------------------------


def test_missing_values_never_count_as_exceeding():
    lim = get_standard("who_drinking").limit_for("F_mgL")
    bad = lim.exceeds(pd.Series([np.nan, 0.5, 2.0]))
    assert bad.tolist() == [False, False, True]


def test_range_limit_flags_both_sides():
    lim = get_standard("who_drinking").limit_for("ph")
    bad = lim.exceeds(pd.Series([6.0, 7.0, 9.0, np.nan]))
    assert bad.tolist() == [True, False, True, False]


def test_exactly_at_the_limit_does_not_exceed():
    lim = get_standard("who_drinking").limit_for("F_mgL")
    assert not bool(lim.exceeds(pd.Series([1.5])).iloc[0])


# -- el caso del fluoruro, que es el que motivo todo esto -------------------


def test_fluoride_denominator_changes_with_the_zero_policy():
    """El nucleo del asunto: 32 incumplimientos sobre 90 o sobre 58 no es lo
    mismo, y la diferencia la decide como se lean los 32 ceros."""
    crudo = check(_analysed(()).data)
    f1 = crudo[crudo.parameter == "F_mgL"].iloc[0]
    assert f1.n_measured == 90
    assert f1.n_exceeding == 32
    assert abs(f1.pct - 35.6) < 0.2

    limpio = check(_analysed(("F",)).data)
    f2 = limpio[limpio.parameter == "F_mgL"].iloc[0]
    assert f2.n_measured == 58, "los 32 ceros dejan de contar como medida"
    assert f2.n_exceeding == 32, "los incumplimientos no cambian"
    assert abs(f2.pct - 55.2) < 0.2


def test_measured_only_false_uses_the_total_as_denominator():
    ds = _analysed(("F",))
    sobre_medidas = check(ds.data, measured_only=True)
    sobre_total = check(ds.data, measured_only=False)
    a = sobre_medidas[sobre_medidas.parameter == "F_mgL"].iloc[0]
    b = sobre_total[sobre_total.parameter == "F_mgL"].iloc[0]
    assert a.pct > b.pct, "el denominador mayor rebaja el porcentaje"


def test_fluoride_maximum_in_the_real_data():
    r = check(_analysed().data)
    f = r[r.parameter == "F_mgL"].iloc[0]
    assert abs(f.max_observed - 7.1) < 0.01, "el maximo del dataset son 7,1 mg/L"


def test_exceeding_mask_identifies_the_samples():
    ds = _analysed()
    mask = exceeding_mask(ds.data, "F_mgL")
    assert int(mask.sum()) == 32
    peores = ds.data.loc[mask, "F_mgL"].sort_values(ascending=False)
    assert peores.iloc[0] == 7.1


def test_parameters_absent_from_the_data_are_skipped():
    """El dataset no mide NO3: no debe aparecer con 0 incumplimientos, que se
    leeria como que cumple."""
    r = check(_analysed().data)
    assert "NO3_mgL" not in set(r.parameter)


def test_sulfate_and_chloride_are_within_the_aesthetic_limits():
    r = check(_analysed().data)
    for param in ("Cl_mgL", "SO4_mgL"):
        row = r[r.parameter == param].iloc[0]
        assert row.n_exceeding == 0, param


def test_three_samples_exceed_the_sodium_taste_threshold():
    r = check(_analysed().data)
    na = r[r.parameter == "Na_mgL"].iloc[0]
    assert na.n_exceeding == 3
    assert na.kind == "aesthetic"


# -- banderas por muestra ---------------------------------------------------


def test_add_compliance_marks_each_parameter_and_counts():
    out = add_compliance(_analysed().data)
    assert "F_mgL__exceeds" in out.columns
    assert out["n_exceedances"].max() >= 1
    assert int(out["F_mgL__exceeds"].sum()) == 32


def test_health_flag_ignores_aesthetic_breaches():
    """Una muestra que solo pasa el umbral de sabor del sodio no es un problema
    sanitario y no debe marcarse como tal."""
    df = pd.DataFrame({"F_mgL": [0.5], "Na_mgL": [300.0], "ph": [7.2]})
    out = add_compliance(df)
    assert out["n_exceedances"].iloc[0] == 1
    assert not bool(out["exceeds_health"].iloc[0])

    df2 = pd.DataFrame({"F_mgL": [3.0], "Na_mgL": [10.0], "ph": [7.2]})
    assert bool(add_compliance(df2)["exceeds_health"].iloc[0])


def test_add_compliance_on_data_without_any_limited_parameter():
    out = add_compliance(pd.DataFrame({"station_code": ["A"]}))
    assert out["n_exceedances"].iloc[0] == 0
    assert not bool(out["exceeds_health"].iloc[0])


# -- estandares propios -----------------------------------------------------


def test_user_can_define_their_own_standard():
    std = custom_standard("Mi proyecto", [
        {"parameter": "F_mgL", "label": "Fluoruro", "maximum": 0.8, "kind": "health"},
        {"parameter": "tds_mgl", "label": "TDS", "maximum": 500, "kind": "aesthetic"},
    ])
    assert not std.verified
    assert std.limit_for("F_mgL").maximum == 0.8
    r = check(_analysed().data, std)
    f = r[r.parameter == "F_mgL"].iloc[0]
    assert f.n_exceeding > 32, "un umbral mas estricto detecta mas incumplimientos"


def test_custom_standard_defaults_to_health_and_mgl():
    std = custom_standard("X", [{"parameter": "Cl_mgL", "maximum": 100}])
    lim = std.limit_for("Cl_mgL")
    assert lim.kind is LimitKind.HEALTH
    assert lim.unit == "mg/L"
    assert lim.label == "Cl_mgL"
