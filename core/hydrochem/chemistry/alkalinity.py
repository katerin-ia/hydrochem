"""Alcalinidad expresada como CaCO₃.

Portado de la celda 18 del notebook (clasificado **A** en la auditoría).

    Alcalinidad (mg/L como CaCO₃) = (HCO₃⁻ + CO₃²⁻) [meq/L] × 50,04

El factor 50,04 g/eq es el peso equivalente del CaCO₃ (100,087 / 2).

Limitación conocida y heredada del método: esta expresión es la alcalinidad
*carbonatada* y omite las contribuciones de OH⁻, boratos, silicatos y ácidos
orgánicos. Es la aproximación estándar para aguas naturales con pH < 9, que es
el caso del dataset de referencia.
"""

from __future__ import annotations

import pandas as pd

from ..constants import CACO3_EQUIVALENT_WEIGHT
from .units import meq_column

ALKALINITY_COL = "Alkalinity_mgCaCO3"


def alkalinity_as_caco3(
    hco3_meq: pd.Series,
    co3_meq: pd.Series | None = None,
    factor: float = CACO3_EQUIVALENT_WEIGHT,
) -> pd.Series:
    """Alcalinidad en mg/L como CaCO₃ a partir de meq/L de HCO₃⁻ y CO₃²⁻."""
    total = pd.to_numeric(hco3_meq, errors="coerce")
    if co3_meq is not None:
        total = total.add(pd.to_numeric(co3_meq, errors="coerce"), fill_value=0.0)
    return total * factor


def add_alkalinity(df: pd.DataFrame, factor: float = CACO3_EQUIVALENT_WEIGHT) -> pd.DataFrame:
    """Añade la columna ``Alkalinity_mgCaCO3``.

    Requiere ``HCO3_meq``; ``CO3_meq`` es opcional y se suma si está presente.
    """
    hco3 = meq_column("HCO3")
    if hco3 not in df.columns:
        raise KeyError(
            f"Falta la columna {hco3!r}. Llama antes a add_meq_columns()."
        )
    co3 = meq_column("CO3")
    out = df.copy()
    out[ALKALINITY_COL] = alkalinity_as_caco3(
        out[hco3], out[co3] if co3 in out.columns else None, factor
    )
    return out
