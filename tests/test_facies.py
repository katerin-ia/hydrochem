"""Clasificacion hidroquimica."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.facies import (
    DOMINANCE_THRESHOLD,
    FACIES_COL,
    FACIES_LABEL_COL,
    add_facies,
    classify,
    classify_dominant,
    classify_piper_zone,
    color_of,
    get_scheme,
    label_of,
    percentages,
    summary,
)
from hydrochem.chemistry.units import add_meq_columns


def _prepared() -> pd.DataFrame:
    return add_meq_columns(load_amargosa(), ions=FIXTURE_IONS)


def _water(**meq) -> pd.DataFrame:
    base = {f"{i}_meq": 0.0 for i in FIXTURE_IONS}
    base.update({f"{k}_meq": v for k, v in meq.items()})
    return pd.DataFrame([base])


# -- porcentajes ------------------------------------------------------------


def test_percentages_sum_to_one_hundred_per_side():
    pct = percentages(_prepared())
    cat = pct[["pct_Ca", "pct_Mg", "pct_Na"]].sum(axis=1)
    an = pct[["pct_HCO3", "pct_SO4", "pct_Cl"]].sum(axis=1)
    assert np.allclose(cat, 100.0)
    assert np.allclose(an, 100.0)


def test_potassium_counts_with_sodium():
    """Es la practica habitual: en aguas naturales el K es minoritario."""
    pct = percentages(_water(Na=1.0, K=1.0, Ca=2.0, HCO3=1.0))
    assert np.isclose(pct["pct_Na"].iloc[0], 50.0)


def test_carbonate_counts_with_bicarbonate():
    pct = percentages(_water(Ca=1.0, HCO3=1.0, CO3=1.0, SO4=2.0))
    assert np.isclose(pct["pct_HCO3"].iloc[0], 50.0)


def test_unmeasured_ion_is_not_counted_as_zero():
    """Sin columna de NO3, el grupo del cloruro solo suma Cl y F."""
    df = _water(Ca=1.0, Cl=1.0).drop(columns=["NO3_meq"], errors="ignore")
    pct = percentages(df)
    assert np.isclose(pct["pct_Cl"].iloc[0], 100.0)


# -- ion dominante ----------------------------------------------------------


def test_pure_calcium_bicarbonate_water():
    r = classify_dominant(_water(Ca=5.0, HCO3=5.0)).iloc[0]
    assert r[FACIES_COL] == "HCO3-Ca"
    assert r[FACIES_LABEL_COL] == "Bicarbonatada calcica"


def test_pure_sodium_chloride_water():
    r = classify_dominant(_water(Na=5.0, Cl=5.0)).iloc[0]
    assert r[FACIES_COL] == "Cl-Na"
    assert r[FACIES_LABEL_COL] == "Clorurada sodica"


def test_magnesium_sulfate_water():
    r = classify_dominant(_water(Mg=5.0, SO4=5.0)).iloc[0]
    assert r[FACIES_COL] == "SO4-Mg"
    assert r[FACIES_LABEL_COL] == "Sulfatada magnesica"


def test_one_ion_above_fifty_percent_names_the_water_alone():
    # Ca 60 %, Na 40 % -> solo calcica
    r = classify_dominant(_water(Ca=6.0, Na=4.0, HCO3=10.0)).iloc[0]
    assert r[FACIES_COL] == "HCO3-Ca"


def test_below_fifty_percent_the_two_largest_are_named():
    # Ca 40 %, Na 35 %, Mg 25 % -> calcico-sodica
    r = classify_dominant(_water(Ca=4.0, Na=3.5, Mg=2.5, HCO3=10.0)).iloc[0]
    assert r[FACIES_COL] == "HCO3-Ca-Na"
    assert r[FACIES_LABEL_COL] == "Bicarbonatada calcica-sodica"


def test_dominance_threshold_is_fifty():
    assert DOMINANCE_THRESHOLD == 50.0
    # Exactamente 50 % ya nombra sola (>= 50)
    r = classify_dominant(_water(Ca=5.0, Na=3.0, Mg=2.0, HCO3=10.0)).iloc[0]
    assert r[FACIES_COL] == "HCO3-Ca"


def test_sample_without_data_is_marked_not_guessed():
    df = pd.DataFrame([{f"{i}_meq": np.nan for i in FIXTURE_IONS}])
    r = classify_dominant(df).iloc[0]
    assert r[FACIES_COL] == "sin_datos"


# -- zonas del rombo de Piper ----------------------------------------------


def test_zone_five_is_carbonate_hardness():
    r = classify_piper_zone(_water(Ca=8.0, Na=2.0, HCO3=8.0, Cl=2.0)).iloc[0]
    assert r[FACIES_COL] == "z5_dura_carbonatada"
    assert "carbonatada" in r[FACIES_LABEL_COL].lower()


def test_zone_six_is_non_carbonate_hardness():
    r = classify_piper_zone(_water(Ca=8.0, Na=2.0, SO4=8.0, HCO3=2.0)).iloc[0]
    assert r[FACIES_COL] == "z6_dura_no_carbonatada"


def test_zone_seven_is_non_carbonate_alkali():
    r = classify_piper_zone(_water(Na=8.0, Ca=2.0, Cl=8.0, HCO3=2.0)).iloc[0]
    assert r[FACIES_COL] == "z7_alcalina_no_carbonatada"


def test_zone_eight_is_carbonate_alkali():
    r = classify_piper_zone(_water(Na=8.0, Ca=2.0, HCO3=8.0, Cl=2.0)).iloc[0]
    assert r[FACIES_COL] == "z8_alcalina_carbonatada"


def test_zone_nine_when_no_pair_dominates():
    r = classify_piper_zone(_water(Ca=5.0, Na=5.0, HCO3=5.0, SO4=5.0)).iloc[0]
    assert r[FACIES_COL] == "z9_mixta"


# -- sobre el dataset real --------------------------------------------------


def test_amargosa_is_classified_without_gaps():
    out = add_facies(_prepared())
    assert out[FACIES_COL].notna().all()
    assert (out[FACIES_COL] != "sin_datos").all()


def test_amargosa_is_mostly_bicarbonate_water():
    """Control de realidad: el Death Valley Regional Flow System son aguas
    bicarbonatadas. Si saliera otra cosa, la clasificacion estaria mal."""
    out = add_facies(_prepared())
    res = summary(out[FACIES_COL])
    dominante = res.iloc[0]["facies"]
    assert dominante.startswith("HCO3"), f"la facies mas frecuente es {dominante}"
    bicarbonatadas = out[FACIES_COL].str.startswith("HCO3").sum()
    assert bicarbonatadas / len(out) > 0.75


def test_amargosa_zones_are_plausible():
    out = add_facies(_prepared(), scheme="piper_zone")
    res = summary(out[FACIES_COL])
    assert set(res["facies"]) <= {
        "z5_dura_carbonatada", "z6_dura_no_carbonatada",
        "z7_alcalina_no_carbonatada", "z8_alcalina_carbonatada", "z9_mixta",
    }
    assert res["n"].sum() == 90


def test_add_facies_keeps_the_original_columns():
    df = _prepared()
    out = add_facies(df)
    assert set(df.columns) <= set(out.columns)
    assert len(out) == len(df)


# -- presentacion -----------------------------------------------------------


def test_summary_counts_and_percentages():
    out = add_facies(_prepared())
    res = summary(out[FACIES_COL])
    assert res["n"].sum() == 90
    assert abs(res["pct"].sum() - 100.0) < 0.5
    assert res["n"].is_monotonic_decreasing


def test_every_facies_has_a_colour():
    out = add_facies(_prepared())
    for code in out[FACIES_COL].unique():
        color = color_of(code)
        assert color.startswith("#") and len(color) == 7, code


def test_compound_codes_inherit_the_anion_colour():
    assert color_of("HCO3-Ca-Na") == color_of("HCO3-Ca")


def test_label_of_round_trips():
    assert label_of("HCO3-Ca") == "Bicarbonatada calcica"
    assert label_of("Cl-Na") == "Clorurada sodica"
    assert label_of("z5_dura_carbonatada", "piper_zone").startswith("Dureza carbonatada")


def test_schemes_are_registered_and_documented():
    for key in ("dominant", "piper_zone"):
        s = get_scheme(key)
        assert s.name_es and s.note_es


def test_unknown_scheme_raises():
    try:
        get_scheme("no-existe")
    except KeyError as exc:
        assert "dominant" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado KeyError")


def test_classify_dispatches_on_scheme():
    df = _water(Ca=8.0, HCO3=8.0, Na=2.0, Cl=2.0)
    assert classify(df, "dominant").iloc[0][FACIES_COL] == "HCO3-Ca"
    assert classify(df, "piper_zone").iloc[0][FACIES_COL] == "z5_dura_carbonatada"
