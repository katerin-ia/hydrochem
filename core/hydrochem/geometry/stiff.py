"""Diagrama de Stiff: plantillas de filas y construccion del poligono.

Unifica las celdas 20 y 22 del notebook, que repetian la misma construccion de
vertices (riesgo R11: codigo duplicado). Aqui solo se calculan coordenadas en
meq/L; el dibujo corresponde al cliente, ya sea el navegador o el exportador SVG
para el KMZ.

Un diagrama de Stiff apila filas horizontales. En cada fila, los cationes se
representan hacia la izquierda (valores negativos) y los aniones hacia la
derecha. El poligono se cierra recorriendo el lado cationico de abajo arriba y
el anionico de arriba abajo.

Plantillas incluidas
--------------------
``standard``
    Las tres filas clasicas (Stiff, 1951), de arriba abajo:
    Na+K / Cl, Ca / HCO3+CO3, Mg / SO4.

``extended``
    La del notebook: las tres clasicas mas una cuarta fila inferior solo
    anionica con F+NO3, cuyo vertice izquierdo se fija en 0 para cerrar la
    figura. Util cuando el fluoruro es el objeto del estudio.

El orden de iones es configurable, igual que en el libro PiperStiff-QW-2019,
que lo expone mediante menus desplegables.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..constants import IONS


@dataclass(frozen=True)
class StiffSide:
    """Un lado (cationico o anionico) de una fila del diagrama."""

    ions: tuple[str, ...]
    label: str

    @classmethod
    def of(cls, *ions: str) -> "StiffSide":
        if not ions:
            return cls((), "")
        return cls(ions, " + ".join(IONS[i].label for i in ions))

    @property
    def is_empty(self) -> bool:
        return not self.ions


@dataclass(frozen=True)
class StiffRow:
    """Una fila: un grupo de cationes a la izquierda y otro de aniones a la derecha."""

    left: StiffSide
    right: StiffSide


@dataclass(frozen=True)
class StiffTemplate:
    """Conjunto ordenado de filas. ``rows[0]`` es la fila **superior**."""

    key: str
    name_es: str
    note_es: str
    rows: tuple[StiffRow, ...]

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def ions_used(self) -> tuple[str, ...]:
        seen: list[str] = []
        for row in self.rows:
            for side in (row.left, row.right):
                for ion in side.ions:
                    if ion not in seen:
                        seen.append(ion)
        return tuple(seen)


STANDARD = StiffTemplate(
    key="standard",
    name_es="Estandar (3 filas)",
    note_es="Emparejamiento clasico de Stiff (1951): Na+K/Cl, Ca/HCO3, Mg/SO4.",
    rows=(
        StiffRow(StiffSide.of("Na", "K"), StiffSide.of("Cl")),
        StiffRow(StiffSide.of("Ca"), StiffSide.of("HCO3", "CO3")),
        StiffRow(StiffSide.of("Mg"), StiffSide.of("SO4")),
    ),
)

EXTENDED = StiffTemplate(
    key="extended",
    name_es="Extendida (4 filas, con F y NO3)",
    note_es=(
        "Las tres filas clasicas mas una cuarta solo anionica con F+NO3. Su "
        "vertice izquierdo se fija en 0 porque no tiene cation homologo."
    ),
    rows=STANDARD.rows + (StiffRow(StiffSide.of(), StiffSide.of("F", "NO3")),),
)

TEMPLATES: dict[str, StiffTemplate] = {t.key: t for t in (STANDARD, EXTENDED)}
DEFAULT_TEMPLATE = "standard"


def get_template(template: str | StiffTemplate = DEFAULT_TEMPLATE) -> StiffTemplate:
    if isinstance(template, StiffTemplate):
        return template
    try:
        return TEMPLATES[template]
    except KeyError:
        raise KeyError(
            "Plantilla de Stiff desconocida: {!r}. Disponibles: {}".format(
                template, sorted(TEMPLATES)
            )
        ) from None


def _side_sum(df: pd.DataFrame, side: StiffSide, suffix: str) -> np.ndarray:
    """Suma en meq/L de un lado. Un lado vacio vale 0 por definicion; un lado
    cuyos iones no se midieron devuelve NaN, para no fingir una medida."""
    if side.is_empty:
        return np.zeros(len(df), dtype=float)
    cols = [ion + suffix for ion in side.ions if ion + suffix in df.columns]
    if not cols:
        return np.full(len(df), np.nan)
    return df[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1).to_numpy(float)


def row_values(
    df: pd.DataFrame,
    template: str | StiffTemplate = DEFAULT_TEMPLATE,
    suffix: str = "_meq",
) -> pd.DataFrame:
    """Valores en meq/L de cada lado de cada fila, una fila por muestra.

    Columnas ``row0_left``, ``row0_right``, ``row1_left``, ... con ``row0``
    arriba.
    """
    tpl = get_template(template)
    data: dict[str, np.ndarray] = {}
    for i, row in enumerate(tpl.rows):
        data[f"row{i}_left"] = _side_sum(df, row.left, suffix)
        data[f"row{i}_right"] = _side_sum(df, row.right, suffix)
    return pd.DataFrame(data, index=df.index)


def polygon(values: "pd.Series | dict", template: str | StiffTemplate = DEFAULT_TEMPLATE):
    """Poligono cerrado de una muestra, en coordenadas (meq/L, indice de fila).

    ``y`` va de 0 en la fila inferior a ``n_rows - 1`` en la superior, de modo
    que el eje vertical se lee de abajo arriba como en el diagrama impreso.
    Los cationes salen con signo negativo.
    """
    tpl = get_template(template)
    n = tpl.n_rows
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for i in range(n):
        y = float(n - 1 - i)  # row0 es la superior
        left.append((-float(values[f"row{i}_left"]), y))
        right.append((float(values[f"row{i}_right"]), y))
    # cationes de abajo arriba, aniones de arriba abajo, y cierre
    ordered = left[::-1] + right + [left[-1]]
    return ordered


def polygons(
    df: pd.DataFrame,
    template: str | StiffTemplate = DEFAULT_TEMPLATE,
    suffix: str = "_meq",
) -> list[list[tuple[float, float]]]:
    """Poligono de cada muestra del DataFrame, en el mismo orden."""
    tpl = get_template(template)
    vals = row_values(df, tpl, suffix)
    return [polygon(row, tpl) for _, row in vals.iterrows()]


def axis_limit(
    df: pd.DataFrame,
    template: str | StiffTemplate = DEFAULT_TEMPLATE,
    suffix: str = "_meq",
    margin: float = 1.20,
    minimum: float = 0.5,
) -> float:
    """Semiamplitud simetrica del eje X, comun a todas las muestras.

    Una escala compartida es lo que permite comparar formas entre muestras; el
    precio es que los grupos poco mineralizados se ven pequenos. Para escalar
    por grupo, llamar con el subconjunto correspondiente.
    """
    vals = row_values(df, template, suffix)
    top = np.nanmax(vals.to_numpy(dtype=float)) if len(vals) else np.nan
    if not np.isfinite(top):
        return minimum
    return max(float(top) * margin, minimum)


def row_labels(template: str | StiffTemplate = DEFAULT_TEMPLATE) -> list[tuple[str, str]]:
    """Etiquetas ``(izquierda, derecha)`` de cada fila, de arriba abajo."""
    tpl = get_template(template)
    return [(r.left.label, r.right.label) for r in tpl.rows]
