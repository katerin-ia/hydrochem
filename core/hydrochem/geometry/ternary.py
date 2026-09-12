"""Geometría de diagramas ternarios equiláteros.

Portado de la celda 24 del notebook (``tri_xy`` y ``draw_tri_grid``), clasificado
**A — reutilizable** en la auditoría: las tres familias de isolíneas se
verificaron analíticamente y son exactas. Los cambios son: separación entre
cálculo y dibujo, y corrección del doble etiquetado de porcentajes (riesgo R17).

Convenio de vértices para un triángulo de lado 1 con origen en ``ox``:

    A = (ox, 0)            vértice inferior izquierdo
    B = (ox + 1, 0)        vértice inferior derecho
    C = (ox + 0.5, √3/2)   ápice superior
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Altura de un triángulo equilátero de lado 1.
TRIANGLE_HEIGHT = math.sqrt(3) / 2

#: Niveles de isolínea por defecto, como fracción.
DEFAULT_LEVELS: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8)


def normalise(a, b, c):
    """Normaliza tres componentes a fracciones que suman 1.

    Las filas cuyo total sea 0 o no finito devuelven ``NaN`` en lugar de una
    división por cero silenciosa. El notebook original sustituía el total por 1,
    lo que colocaba esas muestras en el vértice A sin avisar.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    c = np.asarray(c, dtype=float)
    total = a + b + c
    valid = np.isfinite(total) & (total > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        safe = np.where(valid, total, np.nan)
        return a / safe, b / safe, c / safe


def tri_xy(a, b, c, origin: float = 0.0):
    """Convierte componentes ternarias en coordenadas cartesianas.

    :returns: ``(x, y)`` como arrays de numpy.
    """
    fa, fb, fc = normalise(a, b, c)
    x = origin + 0.5 * (2.0 * fb + fc)
    y = TRIANGLE_HEIGHT * fc
    return x, y


@dataclass(frozen=True)
class Segment:
    """Un segmento recto, listo para dibujar."""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class Label:
    """Una etiqueta posicionada, con anclaje tipográfico."""

    x: float
    y: float
    text: str
    ha: str = "center"  # left | center | right
    va: str = "middle"  # top | middle | bottom


def triangle_outline(origin: float = 0.0) -> list[tuple[float, float]]:
    """Polígono cerrado del triángulo."""
    return [
        (origin, 0.0),
        (origin + 1.0, 0.0),
        (origin + 0.5, TRIANGLE_HEIGHT),
        (origin, 0.0),
    ]


def triangle_gridlines(
    origin: float = 0.0, levels: tuple[float, ...] = DEFAULT_LEVELS
) -> list[Segment]:
    """Isolíneas de porcentaje constante para cada uno de los tres componentes."""
    out: list[Segment] = []
    for p in levels:
        q = 1.0 - p
        # A constante = p  (componente del vértice inferior izquierdo)
        out.append(Segment(origin + q, 0.0, origin + q / 2, TRIANGLE_HEIGHT * q))
        # B constante = p  (componente del vértice inferior derecho)
        out.append(Segment(origin + p, 0.0, origin + 0.5 * (1 + p), TRIANGLE_HEIGHT * q))
        # C constante = p  (componente del ápice) — horizontal
        out.append(
            Segment(origin + p / 2, TRIANGLE_HEIGHT * p, origin + 1 - p / 2, TRIANGLE_HEIGHT * p)
        )
    return out


def triangle_tick_labels(
    origin: float = 0.0,
    levels: tuple[float, ...] = DEFAULT_LEVELS,
    offset: float = 0.045,
) -> list[Label]:
    """Etiquetas de porcentaje, **una por nivel y por lado**.

    Corrige el riesgo R17: el notebook escribía en el borde inferior tanto ``p``
    como ``1−p``, de modo que cada nivel aparecía dos veces y era imposible
    saber a qué componente se refería.

    Cada lado del triángulo se etiqueta con el componente que crece a lo largo
    de él, siguiendo el sentido antihorario habitual en los diagramas de Piper.
    """
    out: list[Label] = []
    for p in levels:
        pct = f"{round(p * 100)}"
        q = 1.0 - p
        # Borde inferior (A → B): crece B, de izquierda a derecha.
        out.append(Label(origin + p, -offset, pct, ha="center", va="top"))
        # Borde izquierdo (A → C): crece C, de abajo arriba.
        out.append(
            Label(origin + p / 2 - offset * 0.8, TRIANGLE_HEIGHT * p, pct, ha="right", va="middle")
        )
        # Borde derecho (C → B): crece A, de arriba abajo.
        out.append(
            Label(
                origin + 0.5 * (1 + q) + offset * 0.8,
                TRIANGLE_HEIGHT * q,
                pct,
                ha="left",
                va="middle",
            )
        )
    return out
