"""Carga del patrón de oro extraído de PiperStiff-QW-2019.v9.xlsm."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

FIXTURE = Path(__file__).parent / "fixtures" / "amargosa_90.csv"

#: Iones realmente medidos en el dataset de referencia. NO₃ no se midió y por
#: tanto no aparece: el núcleo debe funcionar sin inventarlo (riesgo R4).
FIXTURE_IONS = ("Ca", "Mg", "Na", "K", "HCO3", "CO3", "SO4", "Cl", "F")


def load_amargosa() -> pd.DataFrame:
    """Los 90 sitios del Death Valley Regional Flow System, tal como están
    en la hoja ``DATA`` del libro Excel — incluidas las columnas ``xl_*`` que
    contienen los valores calculados por Excel y sirven de testigo."""
    return pd.read_csv(FIXTURE)
