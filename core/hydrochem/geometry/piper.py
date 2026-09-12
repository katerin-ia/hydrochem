"""Diagrama de Piper: geometria, proyeccion y convenciones.

Corrige el riesgo **R2** de la auditoria. El notebook original dimensionaba el
rombo con ``hw = SH/2`` y ``hh = hw*sqrt(3)`` centrado en ``y = sqrt(3)/2``, lo
que situaba su vertice inferior en ``y = -0,52`` --por debajo de la base de los
triangulos-- y hacia que el rombo invadiese ambos ternarios.

Geometria correcta, con triangulos de lado 1 y un hueco ``g`` entre ellos:

==========================  ==================================
Elemento                    Valor
==========================  ==================================
Triangulo cationico         x en [0, 1]
Triangulo anionico          x en [1+g, 2+g]
Semianchura del rombo       hw = 0,5
Semialtura del rombo        hh = sqrt(3)/2
Centro del rombo            (1 + g/2, (sqrt(3)/2)*(1+g))
Vertice inferior            (1 + g/2, (sqrt(3)/2)*g)
==========================  ==================================

Verificado contra la hoja ``CONTROL`` del libro PiperStiff-QW-2019.v9.xlsm, que
con ``Offset = 0,3`` define los vertices (1,15 . 0,2598), (0,65 . 1,1258),
(1,15 . 1,9919) y (1,65 . 1,1258).

Convenciones
------------
Se ofrecen las **dos** orientaciones, seleccionables:

``classic``
    Convencion de Piper (1944) y de la literatura estandar: Mg en el apice
    cationico y SO4 en el anionico. El punto del rombo es la **proyeccion
    geometrica** real: interseccion de la recta que parte del punto cationico
    con pendiente +sqrt(3) y de la que parte del punto anionico con pendiente
    -sqrt(3). Sus ejes son %(Na+K) y %(SO4+Cl), y sus vertices son por tanto
    Ca-HCO3 (izquierda), Na-Cl (derecha), Ca-Cl (arriba) y Na-HCO3 (abajo).
    Es la unica sobre la que pueden superponerse las plantillas clasicas de
    clasificacion de facies.

``notebook``
    Orientacion del notebook original: Na+K en el apice cationico y Cl+F+NO3 en
    el anionico. Su rombo es una **parameterizacion afin** por %(Na+K) y
    %(Cl+F+NO3): los vertices se corresponden con los del rombo, pero no es la
    proyeccion geometrica de Piper para esa disposicion de vertices. Se conserva
    para reproducir los graficos ya publicados con el notebook.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from ..constants import IONS
from .ternary import (
    DEFAULT_LEVELS,
    TRIANGLE_HEIGHT,
    Label,
    Segment,
    normalise,
    tri_xy,
    triangle_gridlines,
    triangle_outline,
    triangle_tick_labels,
)


# --------------------------------------------------------------------------
# Convenciones
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class VertexGroup:
    """Grupo de iones asignado a un vertice de un triangulo ternario."""

    ions: tuple[str, ...]
    label: str

    @classmethod
    def of(cls, *ions: str) -> "VertexGroup":
        return cls(ions, " + ".join(IONS[i].label for i in ions))


@dataclass(frozen=True)
class PiperConvention:
    """Asignacion de iones a vertices y regla de proyeccion al rombo."""

    key: str
    name_es: str
    note_es: str
    cation_left: VertexGroup
    cation_right: VertexGroup
    cation_apex: VertexGroup
    anion_left: VertexGroup
    anion_right: VertexGroup
    anion_apex: VertexGroup
    #: ``geometric`` = proyeccion de Piper; ``affine`` = parameterizacion directa.
    diamond_rule: Literal["geometric", "affine"]
    diamond_x_label: str
    diamond_y_label: str

    @property
    def cation_groups(self) -> tuple[VertexGroup, VertexGroup, VertexGroup]:
        return self.cation_left, self.cation_right, self.cation_apex

    @property
    def anion_groups(self) -> tuple[VertexGroup, VertexGroup, VertexGroup]:
        return self.anion_left, self.anion_right, self.anion_apex

    @property
    def ions_used(self) -> tuple[str, ...]:
        seen: list[str] = []
        for grp in self.cation_groups + self.anion_groups:
            for ion in grp.ions:
                if ion not in seen:
                    seen.append(ion)
        return tuple(seen)


CLASSIC = PiperConvention(
    key="classic",
    name_es="Clasica (Piper 1944)",
    note_es=(
        "Mg y SO4 en los apices. El rombo es la proyeccion geometrica real; "
        "sobre el pueden superponerse las plantillas de clasificacion de facies."
    ),
    cation_left=VertexGroup.of("Ca"),
    cation_right=VertexGroup.of("Na", "K"),
    cation_apex=VertexGroup.of("Mg"),
    anion_left=VertexGroup.of("HCO3", "CO3"),
    anion_right=VertexGroup.of("Cl", "F", "NO3"),
    anion_apex=VertexGroup.of("SO4"),
    diamond_rule="geometric",
    diamond_x_label="Ca-HCO3  ->  Na-Cl",
    diamond_y_label="Na-HCO3  ->  Ca-Cl",
)

NOTEBOOK = PiperConvention(
    key="notebook",
    name_es="Notebook (Na+K y Cl en los apices)",
    note_es=(
        "Orientacion del notebook original. El rombo es una parameterizacion "
        "afin por %(Na+K) y %(Cl+F+NO3), no la proyeccion geometrica de Piper; "
        "las plantillas clasicas de facies no son aplicables."
    ),
    cation_left=VertexGroup.of("Ca"),
    cation_right=VertexGroup.of("Mg"),
    cation_apex=VertexGroup.of("Na", "K"),
    anion_left=VertexGroup.of("HCO3", "CO3"),
    anion_right=VertexGroup.of("SO4"),
    anion_apex=VertexGroup.of("Cl", "F", "NO3"),
    diamond_rule="affine",
    diamond_x_label="%(Na+K) + %(Cl+F+NO3)",
    diamond_y_label="%(Cl+F+NO3)  ->  %(Na+K)",
)

CONVENTIONS: dict[str, PiperConvention] = {c.key: c for c in (CLASSIC, NOTEBOOK)}
DEFAULT_CONVENTION = "classic"


def get_convention(convention: str | PiperConvention = DEFAULT_CONVENTION) -> PiperConvention:
    """Resuelve una convencion por su clave, o la devuelve tal cual si ya lo es."""
    if isinstance(convention, PiperConvention):
        return convention
    try:
        return CONVENTIONS[convention]
    except KeyError:
        raise KeyError(
            "Convencion de Piper desconocida: {!r}. Disponibles: {}".format(
                convention, sorted(CONVENTIONS)
            )
        ) from None


# --------------------------------------------------------------------------
# Disposicion geometrica
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PiperLayout:
    """Disposicion del diagrama. ``gap`` es el hueco entre los dos triangulos."""

    gap: float = 0.6
    levels: tuple[float, ...] = field(default=DEFAULT_LEVELS)

    @property
    def anion_origin(self) -> float:
        """Abscisa del vertice inferior izquierdo del triangulo anionico."""
        return 1.0 + self.gap

    @property
    def diamond_half_width(self) -> float:
        return 0.5

    @property
    def diamond_half_height(self) -> float:
        return TRIANGLE_HEIGHT

    @property
    def diamond_center(self) -> tuple[float, float]:
        return (1.0 + self.gap / 2.0, TRIANGLE_HEIGHT * (1.0 + self.gap))

    @property
    def diamond_vertices(self) -> dict[str, tuple[float, float]]:
        cx, cy = self.diamond_center
        hw, hh = self.diamond_half_width, self.diamond_half_height
        return {
            "bottom": (cx, cy - hh),
            "left": (cx - hw, cy),
            "top": (cx, cy + hh),
            "right": (cx + hw, cy),
        }

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """``(xmin, ymin, xmax, ymax)``, con margen para las etiquetas exteriores."""
        pad = 0.22
        return (
            -pad,
            -pad,
            self.anion_origin + 1.0 + pad,
            self.diamond_vertices["top"][1] + pad,
        )


# --------------------------------------------------------------------------
# Proyeccion de muestras
# --------------------------------------------------------------------------


def _group_sum(df: pd.DataFrame, group: VertexGroup, suffix: str = "_meq") -> np.ndarray:
    """Suma las columnas meq/L de un grupo de vertice.

    Los iones sin columna se omiten: un dataset sin NO3 no debe verlo aparecer
    como cero (riesgo R4).
    """
    cols = [ion + suffix for ion in group.ions if ion + suffix in df.columns]
    if not cols:
        return np.zeros(len(df), dtype=float)
    numeric = df[cols].apply(pd.to_numeric, errors="coerce")
    return numeric.sum(axis=1, min_count=1).to_numpy(dtype=float)


def _diamond_geometric(x_c, y_c, x_a, y_a):
    """Interseccion de la recta de pendiente +sqrt(3) desde el punto cationico
    con la de pendiente -sqrt(3) desde el anionico: construccion de Piper."""
    root3 = np.sqrt(3.0)
    x = (x_c + x_a) / 2.0 + (y_a - y_c) / (2.0 * root3)
    y = y_c + root3 * (x - x_c)
    return x, y


def project(
    df: pd.DataFrame,
    convention: str | PiperConvention = DEFAULT_CONVENTION,
    layout: PiperLayout | None = None,
    suffix: str = "_meq",
) -> pd.DataFrame:
    """Proyecta cada muestra en los dos ternarios y en el rombo.

    Espera columnas ``<ion>_meq``. Devuelve un DataFrame con el mismo indice y
    las columnas ``x_cat``, ``y_cat``, ``x_an``, ``y_an``, ``x_diamond``,
    ``y_diamond`` y los seis porcentajes de vertice ``pct_*`` (fracciones 0-1).
    """
    conv = get_convention(convention)
    lay = layout or PiperLayout()

    cl, cr, ca = (_group_sum(df, g, suffix) for g in conv.cation_groups)
    al, ar, aa = (_group_sum(df, g, suffix) for g in conv.anion_groups)

    f_cl, f_cr, f_ca = normalise(cl, cr, ca)
    f_al, f_ar, f_aa = normalise(al, ar, aa)

    x_cat, y_cat = tri_xy(cl, cr, ca, origin=0.0)
    x_an, y_an = tri_xy(al, ar, aa, origin=lay.anion_origin)

    cx, cy = lay.diamond_center
    hw, hh = lay.diamond_half_width, lay.diamond_half_height

    if conv.diamond_rule == "geometric":
        x_d, y_d = _diamond_geometric(x_cat, y_cat, x_an, y_an)
    else:
        u, w = f_ca, f_aa
        x_d = cx + hw * (u + w - 1.0)
        y_d = cy + hh * (u - w)

    return pd.DataFrame(
        {
            "x_cat": x_cat,
            "y_cat": y_cat,
            "x_an": x_an,
            "y_an": y_an,
            "x_diamond": x_d,
            "y_diamond": y_d,
            "pct_cat_left": f_cl,
            "pct_cat_right": f_cr,
            "pct_cat_apex": f_ca,
            "pct_an_left": f_al,
            "pct_an_right": f_ar,
            "pct_an_apex": f_aa,
        },
        index=df.index,
    )


# --------------------------------------------------------------------------
# Fondo estatico del diagrama
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PiperBackground:
    """Todo lo que no depende de los datos: se calcula una vez y se cachea."""

    outlines: list[list[tuple[float, float]]]
    gridlines: list[Segment]
    tick_labels: list[Label]
    axis_labels: list[Label]
    bounds: tuple[float, float, float, float]


def _diamond_outline(lay: PiperLayout) -> list[tuple[float, float]]:
    v = lay.diamond_vertices
    return [v["bottom"], v["left"], v["top"], v["right"], v["bottom"]]


def _diamond_gridlines(lay: PiperLayout) -> list[Segment]:
    """Isolineas del rombo, paralelas a sus dos pares de lados."""
    cx, cy = lay.diamond_center
    hw, hh = lay.diamond_half_width, lay.diamond_half_height
    out: list[Segment] = []
    for p in lay.levels:
        out.append(
            Segment(cx + hw * (p - 1.0), cy + hh * p, cx + hw * p, cy + hh * (p - 1.0))
        )
        out.append(
            Segment(cx + hw * (p - 1.0), cy - hh * p, cx + hw * p, cy - hh * (p - 1.0))
        )
    return out


def background(
    convention: str | PiperConvention = DEFAULT_CONVENTION,
    layout: PiperLayout | None = None,
) -> PiperBackground:
    """Construye el fondo estatico del diagrama para una convencion dada."""
    conv = get_convention(convention)
    lay = layout or PiperLayout()
    ao = lay.anion_origin
    off = 0.09
    # El rotulo izquierdo del triangulo anionico se baja una linea: comparte el
    # hueco central con el rotulo derecho del cationico y, con huecos estrechos,
    # ambos textos se solapaban al ir a la misma altura.
    inner = -off * 2.6

    axis_labels = [
        Label(-off, -off, conv.cation_left.label, ha="right", va="top"),
        Label(1 + off, -off, conv.cation_right.label, ha="left", va="top"),
        Label(0.5, TRIANGLE_HEIGHT + off * 0.7, conv.cation_apex.label, ha="center", va="bottom"),
        Label(ao - off, inner, conv.anion_left.label, ha="right", va="top"),
        Label(ao + 1 + off, -off, conv.anion_right.label, ha="left", va="top"),
        Label(
            ao + 0.5,
            TRIANGLE_HEIGHT + off * 0.7,
            conv.anion_apex.label,
            ha="center",
            va="bottom",
        ),
    ]

    outlines = [triangle_outline(0.0), triangle_outline(ao), _diamond_outline(lay)]
    ticks = triangle_tick_labels(0.0, lay.levels) + triangle_tick_labels(ao, lay.levels)

    return PiperBackground(
        outlines=outlines,
        gridlines=(
            triangle_gridlines(0.0, lay.levels)
            + triangle_gridlines(ao, lay.levels)
            + _diamond_gridlines(lay)
        ),
        tick_labels=ticks,
        axis_labels=axis_labels,
        bounds=_content_bounds(outlines, ticks + axis_labels),
    )


def _content_bounds(
    outlines: list[list[tuple[float, float]]], labels: list[Label], pad: float = 0.08
) -> tuple[float, float, float, float]:
    """Encuadre que contiene todo lo dibujado, rotulos incluidos.

    Se calcula a partir del contenido y no de un margen fijo: con un margen
    constante, bajar un rotulo para evitar un solape lo dejaba fuera del
    encuadre y desaparecia del grafico.
    """
    xs = [p[0] for poly in outlines for p in poly] + [l.x for l in labels]
    ys = [p[1] for poly in outlines for p in poly] + [l.y for l in labels]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
