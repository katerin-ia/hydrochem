"""Error de balance de carga (CBE) y clasificación de aceptabilidad.

Portado de la celda 16 del notebook (clasificado **A** en la auditoría).

    CBE (%) = (Σcationes − Σaniones) / (Σcationes + Σaniones) × 100

con las sumas en meq/L. Umbrales convencionales: |CBE| ≤ 5 % calidad analítica,
≤ 10 % tolerable en muestras de campo (Custodio y Llamas, 1983; Appelo y
Postma, 2005, §1.3).

Nota sobre la convención: el libro PiperStiff-QW-2019 expresa el mismo valor
como **fracción** (−0,0236) en lugar de porcentaje (−2,36 %). Aquí se trabaja
siempre en porcentaje; ``as_fraction=True`` reproduce la salida del libro.
"""

from __future__ import annotations

from enum import Enum

import pandas as pd

from ..constants import CBE_ACCEPTABLE_PCT, CBE_MARGINAL_PCT
from .units import SUM_ANIONS_COL, SUM_CATIONS_COL

CBE_COL = "CBE_pct"
CBE_FLAG_COL = "CBE_flag"


class ChargeBalanceFlag(str, Enum):
    """Resultado de la comprobación del balance de carga."""

    ACCEPTABLE = "acceptable"
    MARGINAL = "marginal"
    REJECTED = "rejected"
    UNKNOWN = "unknown"

    @property
    def label_es(self) -> str:
        return {
            "acceptable": "Aceptable (≤ 5 %)",
            "marginal": "Marginal (5–10 %)",
            "rejected": "Rechazado (> 10 %)",
            "unknown": "Sin datos suficientes",
        }[self.value]


def charge_balance_error(
    sum_cations: pd.Series,
    sum_anions: pd.Series,
    as_fraction: bool = False,
) -> pd.Series:
    """Calcula el CBE a partir de las sumas catiónica y aniónica en meq/L.

    Devuelve ``NaN`` cuando falta alguna suma o cuando el total es cero, en
    lugar de propagar una división por cero.
    """
    cat = pd.to_numeric(sum_cations, errors="coerce")
    an = pd.to_numeric(sum_anions, errors="coerce")
    total = cat + an
    cbe = (cat - an) / total.where(total != 0)
    return cbe if as_fraction else cbe * 100.0


def classify_charge_balance(
    cbe_pct: pd.Series,
    acceptable: float = CBE_ACCEPTABLE_PCT,
    marginal: float = CBE_MARGINAL_PCT,
) -> pd.Series:
    """Clasifica cada CBE (%) según los umbrales convencionales."""
    magnitude = pd.to_numeric(cbe_pct, errors="coerce").abs()
    flags = pd.Series(ChargeBalanceFlag.UNKNOWN.value, index=magnitude.index, dtype=object)
    flags[magnitude > marginal] = ChargeBalanceFlag.REJECTED.value
    flags[(magnitude > acceptable) & (magnitude <= marginal)] = ChargeBalanceFlag.MARGINAL.value
    flags[magnitude <= acceptable] = ChargeBalanceFlag.ACCEPTABLE.value
    flags[magnitude.isna()] = ChargeBalanceFlag.UNKNOWN.value
    return flags


def add_charge_balance(
    df: pd.DataFrame,
    acceptable: float = CBE_ACCEPTABLE_PCT,
    marginal: float = CBE_MARGINAL_PCT,
    unreliable_mask: pd.Series | None = None,
) -> pd.DataFrame:
    """Añade ``CBE_pct`` y ``CBE_flag`` a partir de ``sum_cat`` y ``sum_an``.

    :param unreliable_mask: filas que deben marcarse ``unknown`` con
        independencia de su CBE, por ejemplo por tener demasiados iones
        mayoritarios ausentes. Un CBE excelente calculado sobre datos imputados
        no significa nada, así que no debe presentarse como aceptable.
    :returns: una copia del DataFrame; el original no se modifica.
    """
    missing = {SUM_CATIONS_COL, SUM_ANIONS_COL} - set(df.columns)
    if missing:
        raise KeyError(
            f"Faltan columnas requeridas {sorted(missing)}. "
            "Llama antes a add_meq_columns()."
        )

    out = df.copy()
    out[CBE_COL] = charge_balance_error(out[SUM_CATIONS_COL], out[SUM_ANIONS_COL])
    out[CBE_FLAG_COL] = classify_charge_balance(out[CBE_COL], acceptable, marginal)

    if unreliable_mask is not None:
        mask = unreliable_mask.reindex(out.index, fill_value=False).astype(bool)
        out.loc[mask, CBE_FLAG_COL] = ChargeBalanceFlag.UNKNOWN.value

    return out


def summary(cbe_flags: pd.Series) -> dict[str, int]:
    """Recuento de muestras por categoría de balance de carga."""
    counts = cbe_flags.value_counts().to_dict()
    return {flag.value: int(counts.get(flag.value, 0)) for flag in ChargeBalanceFlag}
