"""Constantes químicas y catálogo de iones.

Resuelve el riesgo R13 de la auditoría (pesos equivalentes inconsistentes entre
el notebook y el libro `PiperStiff-QW-2019.v9.xlsm`) fijando tablas **nombradas y
con fuente citada** en lugar de un único diccionario sin procedencia.

Se distribuyen dos tablas:

``IUPAC2021``
    Valor canónico y por defecto. Peso equivalente = masa molar / |carga|, con
    masas molares de la tabla de pesos atómicos estándar IUPAC 2021
    (Prohaska et al., 2022, *Pure Appl. Chem.* 94(5), 573-600). Para elementos
    con intervalo se usa el valor abreviado convencional.

``PIPERSTIFF_V9``
    Reproduce **exactamente** los pesos codificados en la hoja ``CONTROL`` del
    libro PiperStiff-QW-2019.v9.xlsm (Keith Halford, USGS). Existe para poder
    validar el núcleo contra ese libro bit a bit; no es el valor recomendado.

Las diferencias entre ambas tablas son inferiores al 0,1 % y carecen de
relevancia práctica, pero hacen que los resultados no sean reproducibles entre
herramientas si no se declara cuál se usa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# --------------------------------------------------------------------------
# Catálogo de iones
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ion:
    """Un ion mayoritario del análisis hidroquímico."""

    key: str  # identificador interno, p. ej. "HCO3"
    label: str  # etiqueta para mostrar, p. ej. "HCO₃⁻"
    name_es: str  # nombre en español
    charge: int  # carga con signo: +2, +1, -1, -2
    molar_mass: float  # g/mol, IUPAC 2021

    @property
    def is_cation(self) -> bool:
        return self.charge > 0

    @property
    def is_anion(self) -> bool:
        return self.charge < 0


IONS: dict[str, Ion] = {
    "Ca": Ion("Ca", "Ca²⁺", "calcio", 2, 40.078),
    "Mg": Ion("Mg", "Mg²⁺", "magnesio", 2, 24.305),
    "Na": Ion("Na", "Na⁺", "sodio", 1, 22.98976928),
    "K": Ion("K", "K⁺", "potasio", 1, 39.0983),
    "HCO3": Ion("HCO3", "HCO₃⁻", "bicarbonato", -1, 61.016),
    "CO3": Ion("CO3", "CO₃²⁻", "carbonato", -2, 60.008),
    "SO4": Ion("SO4", "SO₄²⁻", "sulfato", -2, 96.056),
    "Cl": Ion("Cl", "Cl⁻", "cloruro", -1, 35.45),
    "F": Ion("F", "F⁻", "fluoruro", -1, 18.998403),
    "NO3": Ion("NO3", "NO₃⁻", "nitrato", -1, 62.004),
}

CATIONS: tuple[str, ...] = tuple(k for k, i in IONS.items() if i.is_cation)
ANIONS: tuple[str, ...] = tuple(k for k, i in IONS.items() if i.is_anion)
ALL_IONS: tuple[str, ...] = tuple(IONS)

#: Los siete iones mayoritarios que definen la fiabilidad de un análisis.
MAJOR_IONS: tuple[str, ...] = ("Ca", "Mg", "Na", "K", "HCO3", "SO4", "Cl")

# --------------------------------------------------------------------------
# Tablas de pesos equivalentes (g/eq)
# --------------------------------------------------------------------------

IUPAC2021: dict[str, float] = {
    key: round(ion.molar_mass / abs(ion.charge), 6) for key, ion in IONS.items()
}

#: Valores literales de la hoja CONTROL del libro PiperStiff-QW-2019.v9.xlsm.
PIPERSTIFF_V9: dict[str, float] = {
    "Ca": 20.04,
    "Mg": 12.156,
    "Na": 22.98983,
    "K": 39.102,
    "HCO3": 61.0,
    "CO3": 30.0,
    "Cl": 35.453,
    "SO4": 48.0308,
    "F": 18.9984,
    "NO3": 62.004,
}

EW_TABLES: dict[str, Mapping[str, float]] = {
    "IUPAC2021": IUPAC2021,
    "PiperStiff-v9": PIPERSTIFF_V9,
}

DEFAULT_EW_TABLE = "IUPAC2021"


def equivalent_weights(table: str = DEFAULT_EW_TABLE) -> Mapping[str, float]:
    """Devuelve la tabla de pesos equivalentes indicada.

    :raises KeyError: si el nombre no corresponde a ninguna tabla conocida.
    """
    try:
        return EW_TABLES[table]
    except KeyError:
        raise KeyError(
            f"Tabla de pesos equivalentes desconocida: {table!r}. "
            f"Disponibles: {sorted(EW_TABLES)}"
        ) from None


# --------------------------------------------------------------------------
# Otras constantes del análisis
# --------------------------------------------------------------------------

#: Factor de conversión a alcalinidad expresada como CaCO₃.
#: Peso equivalente del CaCO₃ = 100,087 / 2 = 50,04 g/eq.
CACO3_EQUIVALENT_WEIGHT = 50.04

#: Umbrales convencionales del error de balance de carga, en valor absoluto (%).
CBE_ACCEPTABLE_PCT = 5.0  # calidad analítica
CBE_MARGINAL_PCT = 10.0  # tolerable en muestras de campo

#: Nº máximo de iones mayoritarios ausentes antes de marcar la muestra no fiable.
MAX_MISSING_MAJOR_IONS = 2
