"""Equilibrio quimico e indices de saturacion mineral (SI).

Calcula la fuerza ionica (I), los coeficientes de actividad de Davies
y los indices de saturacion para las fases minerales clave:
- Calcita (CaCO3)
- Yeso (CaSO4 . 2H2O)
- Fluorita (CaF2)
- Halita (NaCl)

Ademas, genera el archivo de entrada por lotes (.pqi) para simulacion
avanzada y transporte reactivo con el software oficial USGS PHREEQC.
"""

from __future__ import annotations

from math import log10, sqrt
from typing import Any

import numpy as np
import pandas as pd

from ..constants import IONS

# Masas molares g/mol
MM = {k: ion.molar_mass for k, ion in IONS.items()}

# Constantes de solubilidad termodinamicas log10(Ksp) a 25 °C (Ball & Nordstrom, 1991; Parkhurst & Appelo, 2013)
LOG_KSP = {
    "Calcite": -8.48,
    "Gypsum": -4.58,
    "Fluorite": -10.60,
    "Halite": 1.57,
}


def davies_gamma(charge: int, ionic_strength: float, temp_c: float = 25.0) -> float:
    """Calcula el coeficiente de actividad gamma segun la ecuacion de Davies.

    Valida para fuerzas ionicas hasta ~0.5 M.
    log10(gamma) = -A * z^2 * (sqrt(I) / (1 + sqrt(I)) - 0.3 * I)
    """
    if ionic_strength <= 0:
        return 1.0
    z = abs(charge)
    # Parametro A de Debye-Huckel a ~25 °C es aprox 0.5092
    A = 0.5092
    sqrt_i = sqrt(ionic_strength)
    log_gamma = -A * (z ** 2) * (sqrt_i / (1.0 + sqrt_i) - 0.3 * ionic_strength)
    return 10.0 ** log_gamma


def compute_ionic_strength(row: pd.Series) -> float:
    """Calcula la fuerza ionica I = 0.5 * sum(m_i * z_i^2) en mol/L."""
    I = 0.0
    for ion_key, ion in IONS.items():
        val_mg = row.get(f"{ion_key}_mgL")
        if val_mg is not None and not np.isnan(val_mg) and val_mg > 0:
            m_mol_l = (val_mg / 1000.0) / MM[ion_key]
            I += 0.5 * m_mol_l * (ion.charge ** 2)
    return float(I)


def compute_saturation_indices(row: pd.Series) -> dict[str, float | None]:
    """Calcula los indices de saturacion (SI = log10(IAP / Ksp)) para una muestra."""
    I = compute_ionic_strength(row)
    if I <= 0:
        return {"Calcite": None, "Gypsum": None, "Fluorite": None, "Halite": None}

    # Coeficientes de actividad
    g_ca = davies_gamma(2, I)
    g_mg = davies_gamma(2, I)
    g_na = davies_gamma(1, I)
    g_k = davies_gamma(1, I)
    g_so4 = davies_gamma(-2, I)
    g_cl = davies_gamma(-1, I)
    g_f = davies_gamma(-1, I)
    g_hco3 = davies_gamma(-1, I)
    g_co3 = davies_gamma(-2, I)

    # Molalidades (mol/L)
    m_ca = ((row.get("Ca_mgL") or 0.0) / 1000.0) / MM["Ca"]
    m_so4 = ((row.get("SO4_mgL") or 0.0) / 1000.0) / MM["SO4"]
    m_na = ((row.get("Na_mgL") or 0.0) / 1000.0) / MM["Na"]
    m_cl = ((row.get("Cl_mgL") or 0.0) / 1000.0) / MM["Cl"]
    m_f = ((row.get("F_mgL") or 0.0) / 1000.0) / MM["F"]
    m_hco3 = ((row.get("HCO3_mgL") or 0.0) / 1000.0) / MM["HCO3"]
    m_co3 = ((row.get("CO3_mgL") or 0.0) / 1000.0) / MM["CO3"]
    ph = row.get("ph")

    a_ca = m_ca * g_ca
    a_so4 = m_so4 * g_so4
    a_na = m_na * g_na
    a_cl = m_cl * g_cl
    a_f = m_f * g_f

    # Actividad de CO3 2-: si hay medicion directa se usa; si no, se estima
    # mediante equilibrio con HCO3- a partir del pH: log(a_CO3) = log(a_HCO3) + pH - pK2 (pK2 ~ 10.33)
    if m_co3 > 0:
        a_co3 = m_co3 * g_co3
    elif m_hco3 > 0 and ph is not None and not np.isnan(ph) and ph > 0:
        a_hco3 = m_hco3 * g_hco3
        log_a_co3 = log10(max(a_hco3, 1e-12)) + ph - 10.33
        a_co3 = 10.0 ** log_a_co3
    else:
        a_co3 = 0.0

    si = {}

    # Calcita: Ca2+ + CO3(2-) <=> CaCO3
    if a_ca > 0 and a_co3 > 0:
        iap_calcite = a_ca * a_co3
        si["Calcite"] = round(log10(iap_calcite) - LOG_KSP["Calcite"], 2)
    else:
        si["Calcite"] = None

    # Yeso: Ca2+ + SO4(2-) + 2H2O <=> CaSO4.2H2O
    if a_ca > 0 and a_so4 > 0:
        iap_gypsum = a_ca * a_so4
        si["Gypsum"] = round(log10(iap_gypsum) - LOG_KSP["Gypsum"], 2)
    else:
        si["Gypsum"] = None

    # Fluorita: Ca2+ + 2 F- <=> CaF2
    if a_ca > 0 and a_f > 0:
        iap_fluorite = a_ca * (a_f ** 2)
        si["Fluorite"] = round(log10(iap_fluorite) - LOG_KSP["Fluorite"], 2)
    else:
        si["Fluorite"] = None

    # Halita: Na+ + Cl- <=> NaCl
    if a_na > 0 and a_cl > 0:
        iap_halite = a_na * a_cl
        si["Halite"] = round(log10(iap_halite) - LOG_KSP["Halite"], 2)
    else:
        si["Halite"] = None

    return si


def add_saturation_indices(df: pd.DataFrame) -> pd.DataFrame:
    """Anade columnas SI_Calcite, SI_Gypsum, SI_Fluorite, SI_Halite al DataFrame."""
    out = df.copy()
    calcite_list = []
    gypsum_list = []
    fluorite_list = []
    halite_list = []
    ionic_strength_list = []

    for _, row in out.iterrows():
        I = compute_ionic_strength(row)
        ionic_strength_list.append(round(I, 4))
        si = compute_saturation_indices(row)
        calcite_list.append(si["Calcite"])
        gypsum_list.append(si["Gypsum"])
        fluorite_list.append(si["Fluorite"])
        halite_list.append(si["Halite"])

    out["ionic_strength"] = ionic_strength_list
    out["SI_Calcite"] = calcite_list
    out["SI_Gypsum"] = gypsum_list
    out["SI_Fluorite"] = fluorite_list
    out["SI_Halite"] = halite_list
    return out


def generate_phreeqc_pqi(df: pd.DataFrame, title: str = "HydroChem Batch Simulation") -> str:
    """Genera un archivo de script .pqi completo para USGS PHREEQC.

    Permite calcular especiacion, saturacion exacta y modelado de mezcla/equilibrio
    usando la base de datos termodinamica oficial de PHREEQC (phreeqc.dat / wateq4f.dat).
    """
    lines = [
        f"TITLE {title}",
        "# Generado automaticamente por HydroChem para USGS PHREEQC",
        "# Compatible con phreeqc.dat, wateq4f.dat y llnl.dat",
        "",
        "SELECTED_OUTPUT",
        "    -file hydrochem_output.sel",
        "    -selected_out true",
        "    -user_punch true",
        "    -high_precision false",
        "    -reset false",
        "    -solution true",
        "    -distance false",
        "    -time false",
        "    -step false",
        "    -pH true",
        "    -pe false",
        "    -temperature true",
        "    -alkalinity true",
        "    -ionic_strength true",
        "    -water true",
        "    -charge_balance true",
        "    -totals Ca Mg Na K Cl S(6) F C(4)",
        "    -si Calcite Gypsum Fluorite Halite Dolomite Aragonite Anhydrite",
        "",
    ]

    for idx, (pos, row) in enumerate(df.iterrows(), 1):
        station = str(row.get("station_code") or f"Muestra_{idx}")
        temp = row.get("temp_c") if row.get("temp_c") and not np.isnan(row.get("temp_c")) else 25.0
        ph = row.get("ph") if row.get("ph") and not np.isnan(row.get("ph")) else 7.0

        lines.append(f"SOLUTION {idx} {station}")
        lines.append(f"    temp {temp}")
        lines.append(f"    pH {ph}")
        lines.append("    units mg/l")

        if row.get("Ca_mgL") is not None and not np.isnan(row.get("Ca_mgL")):
            lines.append(f"    Ca {row['Ca_mgL']}")
        if row.get("Mg_mgL") is not None and not np.isnan(row.get("Mg_mgL")):
            lines.append(f"    Mg {row['Mg_mgL']}")
        if row.get("Na_mgL") is not None and not np.isnan(row.get("Na_mgL")):
            lines.append(f"    Na {row['Na_mgL']}")
        if row.get("K_mgL") is not None and not np.isnan(row.get("K_mgL")):
            lines.append(f"    K {row['K_mgL']}")
        if row.get("Cl_mgL") is not None and not np.isnan(row.get("Cl_mgL")):
            lines.append(f"    Cl {row['Cl_mgL']}")
        if row.get("SO4_mgL") is not None and not np.isnan(row.get("SO4_mgL")):
            lines.append(f"    S(6) {row['SO4_mgL']} as SO4")
        if row.get("HCO3_mgL") is not None and not np.isnan(row.get("HCO3_mgL")):
            lines.append(f"    Alkalinity {row['HCO3_mgL']} as HCO3")
        if row.get("F_mgL") is not None and not np.isnan(row.get("F_mgL")):
            lines.append(f"    F {row['F_mgL']}")
        if row.get("NO3_mgL") is not None and not np.isnan(row.get("NO3_mgL")):
            lines.append(f"    N(5) {row['NO3_mgL']} as NO3")

        lines.append("")

    lines.append("END")
    lines.append("")
    return "\n".join(lines)
