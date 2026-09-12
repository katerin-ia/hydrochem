"""Regresion de la geometria del Piper (riesgo R2 de la auditoria).

El testigo es la hoja ``CONTROL`` del libro PiperStiff-QW-2019.v9.xlsm, que con
``Offset = 0,3`` define los cuatro vertices del rombo.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.units import add_meq_columns
from hydrochem.geometry.piper import (
    CLASSIC,
    CONVENTIONS,
    NOTEBOOK,
    PiperLayout,
    background,
    get_convention,
    project,
)
from hydrochem.geometry.ternary import TRIANGLE_HEIGHT

#: Vertices del rombo tal como los define la hoja CONTROL del libro Excel.
EXCEL_DIAMOND = {
    "bottom": (1.15, 0.2598076211353316),
    "left": (0.65, 1.1258330249197702),
    "top": (1.15, 1.9918584287042087),
    "right": (1.65, 1.1258330249197702),
}
EXCEL_GAP = 0.3


def _prepared() -> pd.DataFrame:
    return add_meq_columns(load_amargosa(), ions=FIXTURE_IONS, ew_table="PiperStiff-v9")


# -- geometria del rombo ----------------------------------------------------


def test_diamond_matches_excel_control_sheet():
    got = PiperLayout(gap=EXCEL_GAP).diamond_vertices
    for name, (ex, ey) in EXCEL_DIAMOND.items():
        gx, gy = got[name]
        assert math.isclose(gx, ex, abs_tol=1e-9), f"{name}.x: {gx} != {ex}"
        assert math.isclose(gy, ey, abs_tol=1e-9), f"{name}.y: {gy} != {ey}"


def test_diamond_sits_above_the_triangles():
    """Regresion directa de R2: el vertice inferior debe quedar POR ENCIMA de la
    base de los triangulos. El notebook lo situaba en y = -0,52."""
    for gap in (0.2, 0.3, 0.6, 1.0):
        lay = PiperLayout(gap=gap)
        bottom_y = lay.diamond_vertices["bottom"][1]
        assert bottom_y > 0, f"hueco {gap}: vertice inferior en y={bottom_y}"
        assert math.isclose(bottom_y, TRIANGLE_HEIGHT * gap, abs_tol=1e-12)


def test_diamond_does_not_overlap_triangles():
    """Los lados del rombo no pueden cruzar los triangulos: el vertice izquierdo
    queda a la derecha del apice cationico y por encima de el."""
    lay = PiperLayout(gap=0.6)
    lx, ly = lay.diamond_vertices["left"]
    rx, ry = lay.diamond_vertices["right"]
    assert lx > 0.5 and ly > TRIANGLE_HEIGHT
    assert rx < lay.anion_origin + 0.5 and ry > TRIANGLE_HEIGHT


def test_diamond_is_a_rhombus_with_sixty_degree_sides():
    lay = PiperLayout(gap=0.6)
    v = lay.diamond_vertices
    side = math.hypot(v["left"][0] - v["bottom"][0], v["left"][1] - v["bottom"][1])
    assert math.isclose(side, 1.0, abs_tol=1e-12), "el lado del rombo iguala al del triangulo"
    slope = (v["left"][1] - v["bottom"][1]) / (v["left"][0] - v["bottom"][0])
    assert math.isclose(abs(slope), math.sqrt(3), abs_tol=1e-12), "lados a 60 grados"


def test_diamond_half_dimensions_are_fixed_not_derived_from_gap():
    """hw y hh NO dependen del hueco; ese era el error del notebook."""
    for gap in (0.1, 0.6, 2.0):
        lay = PiperLayout(gap=gap)
        assert lay.diamond_half_width == 0.5
        assert math.isclose(lay.diamond_half_height, TRIANGLE_HEIGHT, abs_tol=1e-15)


# -- convencion clasica -----------------------------------------------------


def _pure(**meq) -> pd.DataFrame:
    base = {f"{i}_meq": 0.0 for i in FIXTURE_IONS}
    base.update({f"{k}_meq": v for k, v in meq.items()})
    return pd.DataFrame([base])


def test_classic_pure_waters_land_on_diamond_vertices():
    """Los cuatro extremos puros deben caer exactamente en los cuatro vertices.
    Es la comprobacion mas fuerte de que la proyeccion es la de Piper."""
    lay = PiperLayout(gap=0.6)
    v = lay.diamond_vertices
    cases = [
        (_pure(Ca=1, HCO3=1), v["left"], "Ca-HCO3"),
        (_pure(Na=1, Cl=1), v["right"], "Na-Cl"),
        (_pure(Ca=1, Cl=1), v["top"], "Ca-Cl"),
        (_pure(Na=1, HCO3=1), v["bottom"], "Na-HCO3"),
    ]
    for df, (ex, ey), name in cases:
        p = project(df, "classic", lay).iloc[0]
        assert math.isclose(p.x_diamond, ex, abs_tol=1e-12), name
        assert math.isclose(p.y_diamond, ey, abs_tol=1e-12), name


def test_classic_diamond_ignores_ca_vs_mg_and_so4_vs_cl():
    """El rombo clasico solo separa alcalinos de alcalinoterreos y acidos
    fuertes de debiles: Ca/Cl y Mg/SO4 son el mismo punto."""
    lay = PiperLayout(gap=0.6)
    a = project(_pure(Ca=1, Cl=1), "classic", lay).iloc[0]
    b = project(_pure(Mg=1, SO4=1), "classic", lay).iloc[0]
    assert math.isclose(a.x_diamond, b.x_diamond, abs_tol=1e-12)
    assert math.isclose(a.y_diamond, b.y_diamond, abs_tol=1e-12)


def test_classic_closed_form_matches_ray_intersection():
    """x = (S + u + w)/2 ; y = (sqrt(3)/2)(S + w - u), con u = %(Na+K) y
    w = %(SO4+Cl). Contraste independiente del calculo por interseccion."""
    lay = PiperLayout(gap=0.6)
    df = _prepared()
    p = project(df, "classic", lay)
    cat = df[["Ca_meq", "Mg_meq", "Na_meq", "K_meq"]].sum(axis=1)
    an = df[["HCO3_meq", "CO3_meq", "SO4_meq", "Cl_meq", "F_meq"]].sum(axis=1)
    u = (df["Na_meq"] + df["K_meq"]) / cat
    w = (df["SO4_meq"] + df["Cl_meq"] + df["F_meq"]) / an
    s = lay.anion_origin
    assert np.allclose(p["x_diamond"], (s + u + w) / 2, atol=1e-12)
    assert np.allclose(p["y_diamond"], TRIANGLE_HEIGHT * (s + w - u), atol=1e-12)


# -- convencion del notebook ------------------------------------------------


def test_notebook_pure_waters_land_on_diamond_vertices():
    lay = PiperLayout(gap=0.6)
    v = lay.diamond_vertices
    cases = [
        (_pure(Na=1, HCO3=1), v["top"], "Na+K apice / HCO3"),
        (_pure(Ca=1, Cl=1), v["bottom"], "Ca / Cl apice"),
        (_pure(Ca=1, HCO3=1), v["left"], "Ca / HCO3"),
        (_pure(Na=1, Cl=1), v["right"], "Na+K / Cl"),
    ]
    for df, (ex, ey), name in cases:
        p = project(df, "notebook", lay).iloc[0]
        assert math.isclose(p.x_diamond, ex, abs_tol=1e-12), name
        assert math.isclose(p.y_diamond, ey, abs_tol=1e-12), name


def test_the_two_conventions_really_differ():
    """Si ambas dieran lo mismo, ofrecer las dos no tendria sentido."""
    df = _prepared()
    a = project(df, "classic")
    b = project(df, "notebook")
    assert not np.allclose(a["y_diamond"], b["y_diamond"])
    assert not np.allclose(a["x_cat"], b["x_cat"])


def test_conventions_are_registered_and_documented():
    assert set(CONVENTIONS) == {"classic", "notebook"}
    for conv in CONVENTIONS.values():
        assert conv.name_es and conv.note_es
        assert len(conv.ions_used) >= 8
    assert CLASSIC.cation_apex.ions == ("Mg",)
    assert CLASSIC.anion_apex.ions == ("SO4",)
    assert NOTEBOOK.cation_apex.ions == ("Na", "K")
    assert NOTEBOOK.anion_apex.ions == ("Cl", "F", "NO3")


def test_unknown_convention_raises():
    try:
        get_convention("no-existe")
    except KeyError as exc:
        assert "classic" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado KeyError")


# -- proyeccion sobre el dataset real ---------------------------------------


def test_all_amargosa_points_fall_inside_the_figure():
    lay = PiperLayout(gap=0.6)
    v = lay.diamond_vertices
    for convention in ("classic", "notebook"):
        p = project(_prepared(), convention, lay)
        assert p.notna().all().all(), f"{convention}: hay NaN"
        # dentro de los triangulos
        assert (p["y_cat"] >= -1e-9).all() and (p["y_cat"] <= TRIANGLE_HEIGHT + 1e-9).all()
        assert (p["x_cat"] >= -1e-9).all() and (p["x_cat"] <= 1 + 1e-9).all()
        # dentro del rombo: |dx|/hw + |dy|/hh <= 1
        cx, cy = lay.diamond_center
        norm = (p["x_diamond"] - cx).abs() / lay.diamond_half_width + (
            p["y_diamond"] - cy
        ).abs() / lay.diamond_half_height
        assert (norm <= 1 + 1e-9).all(), f"{convention}: maximo {norm.max()}"
        assert p["y_diamond"].min() > v["bottom"][1] - 1e-9


def test_percentages_sum_to_one():
    p = project(_prepared(), "classic")
    assert np.allclose(p[["pct_cat_left", "pct_cat_right", "pct_cat_apex"]].sum(axis=1), 1.0)
    assert np.allclose(p[["pct_an_left", "pct_an_right", "pct_an_apex"]].sum(axis=1), 1.0)


def test_sample_with_no_data_gives_nan_not_a_corner():
    """El notebook sustituia el total 0 por 1 y colocaba la muestra en un
    vertice sin avisar. Ahora da NaN."""
    df = pd.DataFrame([{f"{i}_meq": 0.0 for i in FIXTURE_IONS}])
    p = project(df, "classic").iloc[0]
    assert np.isnan(p.x_cat) and np.isnan(p.x_diamond)


def test_missing_no3_column_does_not_break_projection():
    """El dataset real no tiene NO3; la proyeccion debe funcionar igualmente."""
    p = project(_prepared(), "classic")
    assert p["x_an"].notna().all()


# -- fondo estatico ---------------------------------------------------------


def test_background_is_complete_and_within_bounds():
    for convention in ("classic", "notebook"):
        bg = background(convention, PiperLayout(gap=0.6))
        assert len(bg.outlines) == 3, "dos triangulos y un rombo"
        assert len(bg.gridlines) == 12 + 12 + 8
        assert len(bg.axis_labels) == 6
        xmin, ymin, xmax, ymax = bg.bounds
        for poly in bg.outlines:
            for x, y in poly:
                assert xmin <= x <= xmax and ymin <= y <= ymax


def test_background_tick_labels_are_not_duplicated():
    """Regresion de R17: el notebook escribia p y 1-p en el mismo borde, de modo
    que cada nivel aparecia dos veces en la base de cada triangulo."""
    bg = background("classic", PiperLayout(gap=0.6))
    bottom = [lb for lb in bg.tick_labels if abs(lb.y + 0.045) < 1e-9 and lb.x <= 1.0]
    positions = sorted(round(lb.x, 6) for lb in bottom)
    assert positions == sorted(set(positions)), f"posiciones repetidas: {positions}"
    assert len(positions) == 4, "un rotulo por nivel en el borde inferior"


def test_axis_labels_follow_the_convention():
    """Ambas convenciones rotulan los mismos seis grupos de iones; lo que cambia
    es QUE grupo ocupa cada apice."""

    def apices(convention: str) -> tuple[str, str]:
        labels = background(convention).axis_labels
        tops = sorted((lb for lb in labels if lb.va == "bottom"), key=lambda lb: lb.x)
        return tops[0].text, tops[1].text

    assert apices("classic") == ("Mg²⁺", "SO₄²⁻")
    assert apices("notebook") == ("Na⁺ + K⁺", "Cl⁻ + F⁻ + NO₃⁻")


def test_bounds_contain_every_label():
    """Regresion: bajar un rotulo para evitar un solape lo dejaba fuera del
    encuadre y desaparecia del grafico."""
    for convention in ("classic", "notebook"):
        for gap in (0.2, 0.6, 1.2):
            bg = background(convention, PiperLayout(gap=gap))
            xmin, ymin, xmax, ymax = bg.bounds
            for lb in bg.axis_labels + bg.tick_labels:
                assert xmin <= lb.x <= xmax, f"{convention}/{gap}: {lb.text} fuera en x"
                assert ymin <= lb.y <= ymax, f"{convention}/{gap}: {lb.text} fuera en y"


def test_bounds_adapt_to_the_gap():
    narrow = background("classic", PiperLayout(gap=0.2)).bounds
    wide = background("classic", PiperLayout(gap=1.2)).bounds
    assert wide[2] > narrow[2], "un hueco mayor ensancha el encuadre"
