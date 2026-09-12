"""Lectura de valores censurados y limites de deteccion.

Resuelve el riesgo **R9**. El notebook aplicaba ``pd.to_numeric(errors='coerce')``,
que convierte ``"<0.05"``, ``"ND"`` o ``"n.d."`` en ``NaN``: se perdia la
informacion de que el parametro **si se midio** y quedo por debajo del limite de
deteccion, y esas celdas acababan mezcladas con las que nunca se analizaron.

Aqui cada celda se descompone en tres piezas:

``value``
    El numero, cuando la celda trae uno sin calificar.
``detection_limit``
    El umbral declarado, cuando la celda viene censurada (``<0,05`` -> 0,05).
``qualifier``
    ``"<"``, ``">"``, ``"nd"`` (no detectado sin umbral) o ``None``.

Con eso, la capa de imputacion puede aplicar LD/2 a las censuradas y dejar
ausentes las que de verdad no se midieron, que son cosas distintas.

Se acepta la coma como separador decimal: es lo habitual en hojas de calculo en
espanol y castellano, y el propio manual del libro PiperStiff documenta un bug
historico por este motivo.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Textos que significan "analizado y no detectado", sin umbral explicito.
NOT_DETECTED_TOKENS = frozenset(
    {"nd", "n.d.", "n.d", "no detectado", "not detected", "bdl", "bld", "<ld", "<dl", "ud"}
)

#: Textos que significan "no analizado". Se distinguen de los anteriores.
NOT_ANALYSED_TOKENS = frozenset({"", "-", "--", "na", "n/a", "n.a.", "s/d", "sin dato", "nan"})

_CENSORED = re.compile(r"^\s*(?P<op><=?|>=?)\s*(?P<num>[-+]?[\d.,]+(?:[eE][-+]?\d+)?)\s*$")
_PLAIN = re.compile(r"^\s*(?P<num>[-+]?[\d.,]+(?:[eE][-+]?\d+)?)\s*$")


@dataclass(frozen=True)
class ParsedValue:
    """Una celda descompuesta."""

    value: float
    detection_limit: float
    qualifier: str | None
    analysed: bool

    @property
    def is_censored(self) -> bool:
        return self.qualifier in {"<", "<=", ">", ">=", "nd"}


NOT_ANALYSED = ParsedValue(math.nan, math.nan, None, analysed=False)


def _to_float(text: str) -> float:
    """Convierte a float admitiendo coma decimal y separadores de millar."""
    t = text.strip()
    if "," in t and "." in t:
        # El ultimo separador que aparece es el decimal.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return math.nan


def parse_value(raw) -> ParsedValue:
    """Descompone una celda en valor, limite de deteccion y calificador."""
    if raw is None:
        return NOT_ANALYSED
    if isinstance(raw, (int, float, np.integer, np.floating)):
        v = float(raw)
        return NOT_ANALYSED if math.isnan(v) else ParsedValue(v, math.nan, None, True)

    text = str(raw).strip()
    low = text.lower()

    if low in NOT_ANALYSED_TOKENS:
        return NOT_ANALYSED
    if low in NOT_DETECTED_TOKENS:
        return ParsedValue(math.nan, math.nan, "nd", analysed=True)

    m = _CENSORED.match(text)
    if m:
        num = _to_float(m.group("num"))
        op = m.group("op")
        if math.isnan(num):
            return NOT_ANALYSED
        if op.startswith("<"):
            return ParsedValue(math.nan, num, op, analysed=True)
        return ParsedValue(math.nan, num, op, analysed=True)

    m = _PLAIN.match(text)
    if m:
        num = _to_float(m.group("num"))
        return NOT_ANALYSED if math.isnan(num) else ParsedValue(num, math.nan, None, True)

    return NOT_ANALYSED


def parse_series(series: pd.Series) -> pd.DataFrame:
    """Descompone una columna entera.

    :returns: DataFrame con las columnas ``value``, ``detection_limit``,
        ``qualifier`` y ``analysed``, con el mismo indice que la entrada.
    """
    parsed = [parse_value(v) for v in series]
    return pd.DataFrame(
        {
            "value": [p.value for p in parsed],
            "detection_limit": [p.detection_limit for p in parsed],
            "qualifier": [p.qualifier for p in parsed],
            "analysed": [p.analysed for p in parsed],
        },
        index=series.index,
    )


def apply_to_frame(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica el parseo a varias columnas de un DataFrame.

    :returns: ``(datos, censura)``. ``datos`` lleva las columnas originales ya
        numericas mas una ``<col>__detection_limit`` por cada columna que traiga
        algun valor censurado. ``censura`` resume, por columna, cuantas celdas
        vienen censuradas y cuantas no se analizaron.
    """
    out = df.copy()
    rows = []
    for col in columns:
        if col not in out.columns:
            continue
        parsed = parse_series(out[col])
        out[col] = parsed["value"]
        n_censored = int(parsed["detection_limit"].notna().sum())
        n_nd = int((parsed["qualifier"] == "nd").sum())
        if n_censored:
            out[f"{col}__detection_limit"] = parsed["detection_limit"]
        rows.append(
            {
                "column": col,
                "n_censored": n_censored,
                "n_not_detected": n_nd,
                "n_not_analysed": int((~parsed["analysed"]).sum()),
                "n_numeric": int(parsed["value"].notna().sum()),
            }
        )
    return out, pd.DataFrame(rows)
