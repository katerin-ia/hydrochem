"""Diagrama de Durov ampliado.

Rehecho desde cero. El de la celda 26 del notebook tenia tres problemas: los
triangulos marginales se dibujaban sin contorno (quedaban nubes de puntos
flotando), el eje vertical estaba rotulado ``← Ca   Mg →`` pero lo que se
graficaba era ``1 − %(Na+K)``, y el panel de pH salia vacio porque el dataset no
trae pH y esa columna nunca se imputa.

Construccion
------------
Un cuadrado central de lado 1, con un triangulo ternario apoyado en dos de sus
lados:

- **Triangulo anionico** encima, con base en el lado superior del cuadrado:
  HCO₃⁻+CO₃²⁻ en (0,1), Cl⁻ en (1,1) y SO₄²⁻ en el apice.
- **Triangulo cationico** a la izquierda, con base en el lado izquierdo:
  Ca²⁺ en (0,0), Na⁺+K⁺ en (0,1) y Mg²⁺ en el apice.

Cada punto se proyecta **perpendicularmente** sobre el lado que comparte su
triangulo con el cuadrado. Para un triangulo equilatero esa proyeccion es una
funcion lineal exacta de las fracciones:

===========  ==================================
Eje          Formula
===========  ==================================
x            %Cl⁻ + ½·%SO₄²⁻
y            %(Na⁺+K⁺) + ½·%Mg²⁺
===========  ==================================

De ahi salen los limites exactos que verifican las pruebas: un agua de calcio
puro cae en y = 0, una de sodio puro en y = 1 y una de magnesio puro en y = 0,5,
justo el centro del lado.

Dos paneles laterales completan el diagrama ampliado (Lloyd, 1965): **pH** debajo
y **TDS** a la derecha, cada uno alineado con el eje del cuadrado que le
corresponde. Si el dato no existe, el panel **no se dibuja** y se dice por que,
en lugar de mostrar unos ejes vacios.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..constants import IONS
from .ternary import TRIANGLE_HEIGHT, DEFAULT_LEVELS, Label, Segment, normalise

#: Grupos de iones de cada vertice. Fijos: el Durov no admite variantes de
#: orientacion como el Piper.
CATION_BASE_LOW = ("Ca",)  # (0,0)
CATION_BASE_HIGH = ("Na", "K")  # (0,1)
CATION_APEX = ("Mg",)  # apice, hacia la izquierda

ANION_BASE_LOW = ("HCO3", "CO3")  # (0,1)
ANION_BASE_HIGH = ("Cl", "F", "NO3")  # (1,1)
ANION_APEX = ("SO4",)  # apice, hacia arriba

X_COL = "durov_x"
Y_COL = "durov_y"


def _label(ions: tuple[str, ...]) -> str:
    return " + ".join(IONS[i].label for i in ions if i in IONS)


@dataclass(frozen=True)
class DurovLayout:
    """Disposicion. ``side`` es el lado del cuadrado; los triangulos tienen la
    misma base, asi que su altura es ``√3/2``."""

    side: float = 1.0
    #: Anchura de los paneles de pH y TDS, en unidades del cuadrado.
    panel: float = 0.55
    #: Separacion entre el cuadrado y los paneles laterales.
    gap: float = 0.12
    levels: tuple[float, ...] = field(default=DEFAULT_LEVELS)

    @property
    def height(self) -> float:
        return TRIANGLE_HEIGHT * self.side

    @property
    def square(self) -> list[tuple[float, float]]:
        s = self.side
        return [(0, 0), (s, 0), (s, s), (0, s), (0, 0)]

    @property
    def anion_triangle(self) -> list[tuple[float, float]]:
        s = self.side
        return [(0, s), (s, s), (s / 2, s + self.height), (0, s)]

    @property
    def cation_triangle(self) -> list[tuple[float, float]]:
        s = self.side
        return [(0, 0), (0, s), (-self.height, s / 2), (0, 0)]

    @property
    def tds_panel(self) -> list[tuple[float, float]]:
        """Rectangulo del panel de TDS, a la derecha del cuadrado."""
        x0 = self.side + self.gap
        x1 = x0 + self.panel
        return [(x0, 0), (x1, 0), (x1, self.side), (x0, self.side), (x0, 0)]

    @property
    def ph_panel(self) -> list[tuple[float, float]]:
        """Rectangulo del panel de pH, debajo del cuadrado."""
        y0 = -self.gap - self.panel
        y1 = -self.gap
        return [(0, y0), (self.side, y0), (self.side, y1), (0, y1), (0, y0)]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        pad = 0.22
        return (
            -self.height - pad,
            -self.gap - self.panel - pad,
            self.side + self.gap + self.panel + pad,
            self.side + self.height + pad,
        )


def _group_sum(df: pd.DataFrame, ions: tuple[str, ...], suffix: str) -> np.ndarray:
    cols = [i + suffix for i in ions if i + suffix in df.columns]
    if not cols:
        return np.zeros(len(df), dtype=float)
    return (
        df[cols].apply(pd.to_numeric, errors="coerce")
        .sum(axis=1, min_count=1)
        .to_numpy(dtype=float)
    )


def project(
    df: pd.DataFrame, layout: DurovLayout | None = None, suffix: str = "_meq"
) -> pd.DataFrame:
    """Proyecta cada muestra en el cuadrado central y en los dos triangulos.

    :returns: ``durov_x``, ``durov_y`` (cuadrado), ``cat_x``/``cat_y`` y
        ``an_x``/``an_y`` (posicion dentro de cada triangulo marginal) y los seis
        porcentajes.
    """
    lay = layout or DurovLayout()
    s = lay.side
    h = lay.height

    ca = _group_sum(df, CATION_BASE_LOW, suffix)
    nak = _group_sum(df, CATION_BASE_HIGH, suffix)
    mg = _group_sum(df, CATION_APEX, suffix)
    hco3 = _group_sum(df, ANION_BASE_LOW, suffix)
    cl = _group_sum(df, ANION_BASE_HIGH, suffix)
    so4 = _group_sum(df, ANION_APEX, suffix)

    f_ca, f_nak, f_mg = normalise(ca, nak, mg)
    f_hco3, f_cl, f_so4 = normalise(hco3, cl, so4)

    # Proyeccion perpendicular sobre el lado compartido
    y_sq = (f_nak + 0.5 * f_mg) * s
    x_sq = (f_cl + 0.5 * f_so4) * s

    # Posicion dentro de cada triangulo marginal
    cat_x = -h * f_mg
    cat_y = y_sq
    an_x = x_sq
    an_y = s + h * f_so4

    return pd.DataFrame(
        {
            X_COL: x_sq,
            Y_COL: y_sq,
            "cat_x": cat_x,
            "cat_y": cat_y,
            "an_x": an_x,
            "an_y": an_y,
            "pct_Ca": f_ca * 100,
            "pct_NaK": f_nak * 100,
            "pct_Mg": f_mg * 100,
            "pct_HCO3": f_hco3 * 100,
            "pct_Cl": f_cl * 100,
            "pct_SO4": f_so4 * 100,
        },
        index=df.index,
    )


def panel_positions(
    df: pd.DataFrame,
    projected: pd.DataFrame,
    layout: DurovLayout | None = None,
    ph_col: str = "ph",
    tds_col: str = "tds_mgl",
) -> dict:
    """Coordenadas de los puntos en los paneles de pH y TDS.

    Devuelve ``available: False`` para el panel cuyo dato no exista, con el
    motivo escrito: es lo que el notebook no hacia y por eso dibujaba unos ejes
    vacios sin explicacion.
    """
    lay = layout or DurovLayout()
    out: dict = {}

    for key, col, axis in (("ph", ph_col, "x"), ("tds", tds_col, "y")):
        if col not in df.columns:
            out[key] = {
                "available": False,
                "reason": f"El archivo no trae la columna de {key.upper()}.",
            }
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        n = int(values.notna().sum())
        if n == 0:
            out[key] = {
                "available": False,
                "reason": (
                    f"La columna de {key.upper()} existe pero no tiene ni un valor. "
                    "No se imputa: un pH inventado no significa nada."
                ),
            }
            continue

        lo, hi = float(values.min()), float(values.max())
        if hi == lo:
            lo, hi = lo - 0.5, hi + 0.5
        norm = (values - lo) / (hi - lo)

        if axis == "x":  # pH debajo: x del cuadrado, y dentro del panel
            y0 = -lay.gap - lay.panel
            out[key] = {
                "available": True, "n": n, "min": lo, "max": hi,
                "x": projected[X_COL].to_numpy(),
                "y": (y0 + norm * lay.panel).to_numpy(),
            }
        else:  # TDS a la derecha: y del cuadrado, x dentro del panel
            x0 = lay.side + lay.gap
            out[key] = {
                "available": True, "n": n, "min": lo, "max": hi,
                "x": (x0 + norm * lay.panel).to_numpy(),
                "y": projected[Y_COL].to_numpy(),
            }
    return out


@dataclass(frozen=True)
class DurovBackground:
    outlines: list[list[tuple[float, float]]]
    gridlines: list[Segment]
    axis_labels: list[Label]
    tick_labels: list[Label]
    bounds: tuple[float, float, float, float]


def background(layout: DurovLayout | None = None, panels: dict | None = None) -> DurovBackground:
    """Fondo estatico: cuadrado, los dos triangulos con contorno, rejilla y
    rotulos. Los paneles laterales solo se dibujan si hay dato."""
    lay = layout or DurovLayout()
    s, h = lay.side, lay.height
    panels = panels or {}

    outlines = [lay.square, lay.anion_triangle, lay.cation_triangle]
    if panels.get("tds", {}).get("available"):
        outlines.append(lay.tds_panel)
    if panels.get("ph", {}).get("available"):
        outlines.append(lay.ph_panel)

    grid: list[Segment] = []
    for p in lay.levels:
        grid.append(Segment(p * s, 0, p * s, s))  # verticales del cuadrado
        grid.append(Segment(0, p * s, s, p * s))  # horizontales del cuadrado
    # Rejilla de los triangulos: isolineas del apice
    for p in lay.levels:
        q = 1 - p
        grid.append(Segment(p * s / 2, s + h * p, s - p * s / 2, s + h * p))
        grid.append(Segment(-h * p, s * p / 2, -h * p, s - s * p / 2))

    off = 0.05
    axis_labels = [
        Label(-h - off, s / 2, _label(CATION_APEX), ha="right", va="middle"),
        Label(-off, -off, _label(CATION_BASE_LOW), ha="right", va="top"),
        Label(-off, s + off, _label(CATION_BASE_HIGH), ha="right", va="bottom"),
        Label(s / 2, s + h + off, _label(ANION_APEX), ha="center", va="bottom"),
        Label(-off * 0.5, s + off * 1.4, "", ha="right", va="bottom"),
        Label(s + off, s + off, _label(ANION_BASE_HIGH), ha="left", va="bottom"),
    ]
    # El rotulo del bicarbonato va sobre la esquina superior izquierda
    axis_labels[4] = Label(
        -off, s + off * 2.6, _label(ANION_BASE_LOW), ha="left", va="bottom"
    )

    tick_labels: list[Label] = []
    for p in lay.levels:
        tick_labels.append(Label(p * s, -off * 0.5, f"{round(p * 100)}",
                                 ha="center", va="top"))
        tick_labels.append(Label(s + off * 0.4, p * s, f"{round(p * 100)}",
                                 ha="left", va="middle"))

    if panels.get("ph", {}).get("available"):
        ph = panels["ph"]
        y0 = -lay.gap - lay.panel
        axis_labels.append(Label(s / 2, y0 - off, "pH", ha="center", va="top"))
        tick_labels.append(Label(-off * 0.5, y0, f"{ph['min']:.1f}", ha="right", va="middle"))
        tick_labels.append(Label(-off * 0.5, y0 + lay.panel, f"{ph['max']:.1f}",
                                 ha="right", va="middle"))
    if panels.get("tds", {}).get("available"):
        tds = panels["tds"]
        x0 = lay.side + lay.gap
        axis_labels.append(Label(x0 + lay.panel / 2, s + off, "TDS (mg/L)",
                                 ha="center", va="bottom"))
        tick_labels.append(Label(x0, -off * 0.5, f"{tds['min']:.0f}", ha="center", va="top"))
        tick_labels.append(Label(x0 + lay.panel, -off * 0.5, f"{tds['max']:.0f}",
                                 ha="center", va="top"))

    return DurovBackground(outlines, grid, axis_labels, tick_labels, lay.bounds)


def axis_titles() -> dict[str, str]:
    """Rotulos correctos de los ejes del cuadrado.

    El notebook ponia ``← Ca   Mg →`` en el eje vertical cuando lo que graficaba
    era ``1 − %(Na+K)``. Estos son los que corresponden a la proyeccion.
    """
    return {
        "x": f"%{_label(ANION_BASE_HIGH)} + ½·%{_label(ANION_APEX)}",
        "y": f"%{_label(CATION_BASE_HIGH)} + ½·%{_label(CATION_APEX)}",
    }
