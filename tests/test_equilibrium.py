"""Pruebas para equilibrio quimico y PHREEQC."""

import pandas as pd
from hydrochem.chemistry.equilibrium import (
    compute_ionic_strength,
    compute_saturation_indices,
    add_saturation_indices,
    generate_phreeqc_pqi,
)


def test_equilibrium_and_saturation():
    sample = pd.Series({
        "station_code": "PZ-01",
        "Ca_mgL": 80.0,
        "Mg_mgL": 20.0,
        "Na_mgL": 30.0,
        "K_mgL": 5.0,
        "HCO3_mgL": 250.0,
        "SO4_mgL": 90.0,
        "Cl_mgL": 40.0,
        "F_mgL": 1.2,
        "ph": 7.5,
    })
    I = compute_ionic_strength(sample)
    assert I > 0
    si = compute_saturation_indices(sample)
    assert "Calcite" in si
    assert "Gypsum" in si
    assert "Fluorite" in si
    assert "Halite" in si
    assert si["Halite"] is not None and si["Halite"] < 0  # halita siempre subsaturada en agua dulce


def test_generate_phreeqc_pqi():
    df = pd.DataFrame([{
        "station_code": "PZ-01",
        "Ca_mgL": 80.0,
        "Mg_mgL": 20.0,
        "Na_mgL": 30.0,
        "K_mgL": 5.0,
        "HCO3_mgL": 250.0,
        "SO4_mgL": 90.0,
        "Cl_mgL": 40.0,
        "F_mgL": 1.2,
        "ph": 7.5,
    }])
    pqi = generate_phreeqc_pqi(df)
    assert "SOLUTION 1 PZ-01" in pqi
    assert "Ca 80.0" in pqi
    assert "END" in pqi
