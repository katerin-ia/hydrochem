"""Conversión de unidades: mg/L ↔ meq/L ↔ mmol/L.

Portado de la celda 14 del notebook original (clasificado **A — reutilizable
prácticamente sin cambios** en la auditoría). Los cambios respecto al original
son: sin variables globales, sin ``print``, tabla de pesos equivalentes
seleccionable y nombres de columna configurables.

    meq/L = (mg/L) / peso_equivalente        peso_equivalente = masa molar / |carga|
    mmol/L = (mg/L) / masa_molar
"""

from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

from ..constants import (
    ALL_IONS,
    ANIONS,
    CATIONS,
    DEFAULT_EW_TABLE,
    IONS,
    equivalent_weights,
)

MGL_SUFFIX = "_mgL"
MEQ_SUFFIX = "_meq"
MMOL_SUFFIX = "_mmol"

SUM_CATIONS_COL = "sum_cat"
SUM_ANIONS_COL = "sum_an"


def mgl_column(ion: str) -> str:
    return f"{ion}{MGL_SUFFIX}"


def meq_column(ion: str) -> str:
    return f"{ion}{MEQ_SUFFIX}"


def mmol_column(ion: str) -> str:
    return f"{ion}{MMOL_SUFFIX}"


def mgl_to_meq(
    values: pd.Series | float,
    ion: str,
    ew_table: str = DEFAULT_EW_TABLE,
) -> pd.Series | float:
    """Convierte mg/L a meq/L para un ion concreto."""
    ew = equivalent_weights(ew_table)
    if ion not in ew:
        raise KeyError(f"Ion desconocido: {ion!r}. Conocidos: {sorted(ew)}")
    return values / ew[ion]


def mgl_to_mmol(values: pd.Series | float, ion: str) -> pd.Series | float:
    """Convierte mg/L a mmol/L para un ion concreto."""
    if ion not in IONS:
        raise KeyError(f"Ion desconocido: {ion!r}. Conocidos: {sorted(IONS)}")
    return values / IONS[ion].molar_mass


def add_meq_columns(
    df: pd.DataFrame,
    ions: Iterable[str] = ALL_IONS,
    ew_table: str = DEFAULT_EW_TABLE,
    add_sums: bool = True,
) -> pd.DataFrame:
    """Añade las columnas ``<ion>_meq`` a partir de las columnas ``<ion>_mgL``.

    Los iones cuya columna en mg/L no exista se omiten en silencio: eso permite
    trabajar con datasets que no midieron NO₃ o F sin inventar valores. Los
    iones omitidos **no** se cuentan en las sumas.

    :param add_sums: añade además ``sum_cat`` y ``sum_an`` (meq/L).
    :returns: una copia del DataFrame; el original no se modifica.
    """
    out = df.copy()
    ew = equivalent_weights(ew_table)

    present: list[str] = []
    for ion in ions:
        src = mgl_column(ion)
        if src not in out.columns:
            continue
        if ion not in ew:
            raise KeyError(f"Ion desconocido: {ion!r}")
        out[meq_column(ion)] = pd.to_numeric(out[src], errors="coerce") / ew[ion]
        present.append(ion)

    if add_sums:
        cat_cols = [meq_column(i) for i in present if i in CATIONS]
        an_cols = [meq_column(i) for i in present if i in ANIONS]
        # min_count=1 evita que una fila enteramente NaN se convierta en 0.
        out[SUM_CATIONS_COL] = out[cat_cols].sum(axis=1, min_count=1) if cat_cols else pd.NA
        out[SUM_ANIONS_COL] = out[an_cols].sum(axis=1, min_count=1) if an_cols else pd.NA

    return out


def add_mmol_columns(
    df: pd.DataFrame, ions: Iterable[str] = ALL_IONS
) -> pd.DataFrame:
    """Añade las columnas ``<ion>_mmol`` a partir de las columnas ``<ion>_mgL``."""
    out = df.copy()
    for ion in ions:
        src = mgl_column(ion)
        if src in out.columns:
            out[mmol_column(ion)] = (
                pd.to_numeric(out[src], errors="coerce") / IONS[ion].molar_mass
            )
    return out


def equivalent_weight_table(ew_table: str = DEFAULT_EW_TABLE) -> pd.DataFrame:
    """Tabla de pesos equivalentes lista para mostrar en la interfaz."""
    ew: Mapping[str, float] = equivalent_weights(ew_table)
    return pd.DataFrame(
        [
            {
                "ion": key,
                "etiqueta": IONS[key].label,
                "nombre": IONS[key].name_es,
                "carga": IONS[key].charge,
                "masa_molar_g_mol": IONS[key].molar_mass,
                "peso_equivalente_g_eq": ew[key],
                "tipo": "catión" if IONS[key].is_cation else "anión",
            }
            for key in IONS
            if key in ew
        ]
    )
