"""Geometria del diagrama de Stiff."""

from __future__ import annotations

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.units import add_meq_columns
from hydrochem.geometry.stiff import (
    EXTENDED,
    STANDARD,
    TEMPLATES,
    axis_limit,
    get_template,
    polygon,
    polygons,
    row_labels,
    row_values,
)


def _prepared() -> pd.DataFrame:
    return add_meq_columns(load_amargosa(), ions=FIXTURE_IONS, ew_table="PiperStiff-v9")


def test_templates_registered():
    assert set(TEMPLATES) == {"standard", "extended"}
    assert STANDARD.n_rows == 3
    assert EXTENDED.n_rows == 4


def test_standard_pairs_follow_stiff_1951():
    pairs = [(r.left.ions, r.right.ions) for r in STANDARD.rows]
    assert pairs == [
        (("Na", "K"), ("Cl",)),
        (("Ca",), ("HCO3", "CO3")),
        (("Mg",), ("SO4",)),
    ]


def test_extended_adds_a_fourth_anion_only_row():
    last = EXTENDED.rows[-1]
    assert last.left.is_empty
    assert last.right.ions == ("F", "NO3")


def test_row_values_match_manual_sums():
    df = _prepared()
    v = row_values(df, "standard")
    assert np.allclose(v["row0_left"], df["Na_meq"] + df["K_meq"])
    assert np.allclose(v["row0_right"], df["Cl_meq"])
    assert np.allclose(v["row1_left"], df["Ca_meq"])
    assert np.allclose(v["row1_right"], df["HCO3_meq"] + df["CO3_meq"])
    assert np.allclose(v["row2_left"], df["Mg_meq"])
    assert np.allclose(v["row2_right"], df["SO4_meq"])


def test_empty_side_is_zero_but_unmeasured_side_is_nan():
    """Distincion importante: la cuarta fila no tiene cation (0 por definicion),
    pero si NO3 no se midio el lado anionico no puede valer 0."""
    df = _prepared()  # sin columna NO3_meq
    v = row_values(df, "extended")
    assert (v["row3_left"] == 0).all(), "lado sin cation homologo: 0 por definicion"
    assert v["row3_right"].notna().all(), "F si esta medido, asi que hay valor"
    sin_f = df.drop(columns=["F_meq"])
    v2 = row_values(sin_f, "extended")
    assert v2["row3_right"].isna().all(), "sin F ni NO3 medidos: NaN, no 0"


def test_polygon_is_closed_and_ordered_bottom_up():
    df = _prepared().head(1)
    poly = polygons(df, "standard")[0]
    assert poly[0] == poly[-1], "el poligono se cierra"
    assert len(poly) == 2 * STANDARD.n_rows + 1
    ys = [p[1] for p in poly[: STANDARD.n_rows]]
    assert ys == [0.0, 1.0, 2.0], "lado cationico de abajo arriba"


def test_cations_are_negative_anions_positive():
    df = _prepared().head(5)
    for poly in polygons(df, "standard"):
        cations = poly[: STANDARD.n_rows]
        anions = poly[STANDARD.n_rows : 2 * STANDARD.n_rows]
        assert all(x <= 0 for x, _ in cations)
        assert all(x >= 0 for x, _ in anions)


def test_row_zero_is_the_top_row():
    vals = {"row0_left": 1.0, "row0_right": 2.0,
            "row1_left": 3.0, "row1_right": 4.0,
            "row2_left": 5.0, "row2_right": 6.0}
    poly = polygon(vals, "standard")
    top_left = [p for p in poly if p[1] == 2.0 and p[0] < 0][0]
    assert top_left[0] == -1.0, "row0 debe dibujarse arriba"


def test_axis_limit_is_symmetric_and_covers_all_samples():
    df = _prepared()
    lim = axis_limit(df, "standard")
    vals = row_values(df, "standard").to_numpy(dtype=float)
    assert lim >= np.nanmax(vals)
    assert lim == max(float(np.nanmax(vals)) * 1.20, 0.5)


def test_axis_limit_has_a_floor_for_very_dilute_water():
    tiny = pd.DataFrame({f"{i}_meq": [0.001] for i in FIXTURE_IONS})
    assert axis_limit(tiny, "standard") == 0.5


def test_axis_limit_of_empty_frame_does_not_crash():
    empty = pd.DataFrame({f"{i}_meq": [] for i in FIXTURE_IONS})
    assert axis_limit(empty, "standard") == 0.5


def test_row_labels_are_human_readable():
    labels = row_labels("standard")
    assert labels[0] == ("Na⁺ + K⁺", "Cl⁻")
    assert labels[2] == ("Mg²⁺", "SO₄²⁻")
    assert row_labels("extended")[3][0] == "", "la cuarta fila no tiene cation"


def test_amargosa_polygons_are_all_finite():
    polys = polygons(_prepared(), "standard")
    assert len(polys) == 90
    for poly in polys:
        assert all(np.isfinite(x) and np.isfinite(y) for x, y in poly)


def test_unknown_template_raises():
    try:
        get_template("no-existe")
    except KeyError as exc:
        assert "standard" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado KeyError")
