"""Diagrama de Durov ampliado."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.units import add_meq_columns
from hydrochem.geometry.durov import (
    X_COL,
    Y_COL,
    DurovLayout,
    axis_titles,
    background,
    panel_positions,
    project,
)
from hydrochem.geometry.ternary import TRIANGLE_HEIGHT


def _prepared() -> pd.DataFrame:
    return add_meq_columns(load_amargosa(), ions=FIXTURE_IONS)


def _water(**meq) -> pd.DataFrame:
    base = {f"{i}_meq": 0.0 for i in FIXTURE_IONS}
    base.update({f"{k}_meq": v for k, v in meq.items()})
    return pd.DataFrame([base])


# -- proyeccion: los limites exactos ---------------------------------------


def test_pure_calcium_sits_at_the_bottom_of_the_square():
    p = project(_water(Ca=5.0, HCO3=5.0)).iloc[0]
    assert abs(p[Y_COL] - 0.0) < 1e-12


def test_pure_sodium_sits_at_the_top_of_the_square():
    p = project(_water(Na=5.0, HCO3=5.0)).iloc[0]
    assert abs(p[Y_COL] - 1.0) < 1e-12


def test_pure_magnesium_sits_at_the_middle_of_the_left_edge():
    """La proyeccion perpendicular del apice cae en el centro de la base."""
    p = project(_water(Mg=5.0, HCO3=5.0)).iloc[0]
    assert abs(p[Y_COL] - 0.5) < 1e-12


def test_pure_bicarbonate_sits_at_the_left_of_the_square():
    p = project(_water(Ca=5.0, HCO3=5.0)).iloc[0]
    assert abs(p[X_COL] - 0.0) < 1e-12


def test_pure_chloride_sits_at_the_right_of_the_square():
    p = project(_water(Ca=5.0, Cl=5.0)).iloc[0]
    assert abs(p[X_COL] - 1.0) < 1e-12


def test_pure_sulfate_sits_at_the_middle_of_the_top_edge():
    p = project(_water(Ca=5.0, SO4=5.0)).iloc[0]
    assert abs(p[X_COL] - 0.5) < 1e-12


def test_projection_matches_the_documented_formula():
    """x = %Cl + ½%SO4 ; y = %(Na+K) + ½%Mg, en fracciones."""
    df = _prepared()
    p = project(df)
    cat = df[["Ca_meq", "Mg_meq", "Na_meq", "K_meq"]].sum(axis=1)
    an = df[["HCO3_meq", "CO3_meq", "SO4_meq", "Cl_meq", "F_meq"]].sum(axis=1)
    nak = (df["Na_meq"] + df["K_meq"]) / cat
    mg = df["Mg_meq"] / cat
    cl = (df["Cl_meq"] + df["F_meq"]) / an
    so4 = df["SO4_meq"] / an
    assert np.allclose(p[Y_COL], nak + 0.5 * mg, atol=1e-12)
    assert np.allclose(p[X_COL], cl + 0.5 * so4, atol=1e-12)


def test_every_point_falls_inside_the_square():
    p = project(_prepared())
    assert (p[X_COL] >= -1e-12).all() and (p[X_COL] <= 1 + 1e-12).all()
    assert (p[Y_COL] >= -1e-12).all() and (p[Y_COL] <= 1 + 1e-12).all()


def test_percentages_sum_to_one_hundred():
    p = project(_prepared())
    assert np.allclose(p[["pct_Ca", "pct_NaK", "pct_Mg"]].sum(axis=1), 100.0)
    assert np.allclose(p[["pct_HCO3", "pct_Cl", "pct_SO4"]].sum(axis=1), 100.0)


def test_marginal_triangle_points_stay_inside_their_triangle():
    lay = DurovLayout()
    p = project(_prepared(), lay)
    assert (p["cat_x"] <= 1e-12).all(), "el triangulo cationico esta a la izquierda"
    assert (p["cat_x"] >= -lay.height - 1e-12).all()
    assert (p["an_y"] >= lay.side - 1e-12).all(), "el anionico esta encima"
    assert (p["an_y"] <= lay.side + lay.height + 1e-12).all()


def test_sample_without_data_gives_nan_not_a_corner():
    df = pd.DataFrame([{f"{i}_meq": np.nan for i in FIXTURE_IONS}])
    p = project(df).iloc[0]
    assert np.isnan(p[X_COL]) and np.isnan(p[Y_COL])


# -- geometria --------------------------------------------------------------


def test_triangles_share_an_edge_with_the_square():
    lay = DurovLayout()
    assert (0, lay.side) in lay.anion_triangle and (lay.side, lay.side) in lay.anion_triangle
    assert (0, 0) in lay.cation_triangle and (0, lay.side) in lay.cation_triangle


def test_triangles_are_equilateral():
    lay = DurovLayout()
    assert abs(lay.height - TRIANGLE_HEIGHT) < 1e-12
    v = lay.anion_triangle
    lado = math.hypot(v[2][0] - v[0][0], v[2][1] - v[0][1])
    assert abs(lado - lay.side) < 1e-12


def test_bounds_contain_the_whole_figure():
    lay = DurovLayout()
    xmin, ymin, xmax, ymax = lay.bounds
    for poly in (lay.square, lay.anion_triangle, lay.cation_triangle,
                 lay.tds_panel, lay.ph_panel):
        for x, y in poly:
            assert xmin <= x <= xmax and ymin <= y <= ymax


def test_axis_titles_describe_what_is_plotted():
    """El notebook rotulaba el eje Y con Ca y Mg y graficaba 1-%(Na+K)."""
    t = axis_titles()
    assert "Na" in t["y"] and "Mg" in t["y"]
    assert "Cl" in t["x"] and "SO" in t["x"]
    assert "½" in t["x"] and "½" in t["y"]


# -- paneles de pH y TDS ----------------------------------------------------


def test_ph_panel_is_absent_for_the_real_data_and_says_why():
    """El caso que dejaba el panel vacio en el notebook: el dataset no trae pH."""
    df = _prepared()
    p = project(df)
    panels = panel_positions(df, p)
    assert not panels["ph"]["available"]
    assert "no trae" in panels["ph"]["reason"] or "ni un valor" in panels["ph"]["reason"]


def test_tds_panel_is_available_for_the_real_data():
    df = _prepared().rename(columns={"TDS_mgL": "tds_mgl"})
    panels = panel_positions(df, project(df))
    assert panels["tds"]["available"]
    assert panels["tds"]["n"] == 90
    assert abs(panels["tds"]["min"] - 194) < 1 and abs(panels["tds"]["max"] - 1121) < 1


def test_empty_column_is_reported_not_imputed():
    df = _prepared()
    df["ph"] = np.nan
    panels = panel_positions(df, project(df))
    assert not panels["ph"]["available"]
    assert "no se imputa" in panels["ph"]["reason"].lower()


def test_panels_align_with_the_square_axes():
    df = _prepared().rename(columns={"TDS_mgL": "tds_mgl"})
    df["ph"] = 7.5 + np.linspace(-0.5, 0.5, len(df))
    p = project(df)
    panels = panel_positions(df, p)
    # el pH va debajo: comparte la x del cuadrado
    assert np.allclose(panels["ph"]["x"], p[X_COL])
    # el TDS va a la derecha: comparte la y
    assert np.allclose(panels["tds"]["y"], p[Y_COL])


def test_panel_points_stay_inside_their_rectangle():
    lay = DurovLayout()
    df = _prepared().rename(columns={"TDS_mgL": "tds_mgl"})
    df["ph"] = 7.5 + np.linspace(-0.5, 0.5, len(df))
    panels = panel_positions(df, project(df, lay), lay)
    y0 = -lay.gap - lay.panel
    assert (panels["ph"]["y"] >= y0 - 1e-9).all()
    assert (panels["ph"]["y"] <= y0 + lay.panel + 1e-9).all()
    x0 = lay.side + lay.gap
    assert (panels["tds"]["x"] >= x0 - 1e-9).all()
    assert (panels["tds"]["x"] <= x0 + lay.panel + 1e-9).all()


def test_constant_column_does_not_divide_by_zero():
    df = _prepared()
    df["ph"] = 7.2
    panels = panel_positions(df, project(df))
    assert panels["ph"]["available"]
    assert np.isfinite(panels["ph"]["y"]).all()


# -- fondo ------------------------------------------------------------------


def test_background_draws_the_square_and_both_triangles_with_outline():
    """El notebook no dibujaba el contorno de los triangulos marginales."""
    bg = background()
    assert len(bg.outlines) == 3, "sin paneles: cuadrado y dos triangulos"
    for poly in bg.outlines:
        assert poly[0] == poly[-1], "cada contorno debe cerrarse"


def test_background_adds_the_panels_only_when_available():
    lay = DurovLayout()
    solo_tds = background(lay, {"tds": {"available": True, "min": 0, "max": 1},
                                "ph": {"available": False}})
    assert len(solo_tds.outlines) == 4
    ambos = background(lay, {"tds": {"available": True, "min": 0, "max": 1},
                             "ph": {"available": True, "min": 6, "max": 8}})
    assert len(ambos.outlines) == 5


def test_background_labels_every_vertex():
    textos = {lb.text for lb in background().axis_labels if lb.text}
    assert "Mg²⁺" in textos
    assert "SO₄²⁻" in textos
    assert "Ca²⁺" in textos
    assert "Na⁺ + K⁺" in textos
    assert any("HCO₃" in t for t in textos)
    assert any("Cl⁻" in t for t in textos)


def test_background_gridlines_are_inside_the_figure():
    bg = background()
    xmin, ymin, xmax, ymax = bg.bounds
    for seg in bg.gridlines:
        for x, y in ((seg.x0, seg.y0), (seg.x1, seg.y1)):
            assert xmin <= x <= xmax and ymin <= y <= ymax
