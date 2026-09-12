"""Genera un archivo de DEMOSTRACION con varias campanas.

Por que existe: los datos reales del proyecto no tienen fecha de muestreo, asi
que sin un archivo como este no hay forma de ver funcionando el modulo temporal.

Que NO es: un dato hidroquimico. Las concentraciones se derivan de estaciones
reales aplicandoles una deriva inventada, y ninguna conclusion cientifica puede
salir de aqui. El nombre del archivo y el aviso de la aplicacion lo dicen.

Uso:
    python tools/make_demo_campaigns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import numpy as np
import pandas as pd

DESTINO = ROOT / "data" / "samples" / "DEMO-SINTETICO-campanas.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "amargosa_90.csv"

#: Ocho campanas semestrales: suficientes para que una tendencia se lea.
CAMPANAS = [
    "2021-04-12", "2021-10-18", "2022-04-11", "2022-10-17",
    "2023-04-10", "2023-10-16", "2024-04-15", "2024-10-21",
]

#: Cuantas estaciones se siguen en el tiempo.
N_ESTACIONES = 12


def main() -> int:
    base = pd.read_csv(FIXTURE).head(N_ESTACIONES).reset_index(drop=True)
    rng = np.random.default_rng(20260912)  # semilla fija: el archivo es reproducible

    bloques = []
    for k, fecha in enumerate(CAMPANAS):
        b = base.copy()
        b.insert(0, "Fecha", fecha)
        b.insert(1, "Campana", f"C{k + 1:02d}")

        # Deriva lenta hacia agua sodico-clorurada, mas marcada en unas
        # estaciones que en otras, y ruido analitico del 3 %.
        intensidad = np.linspace(0.05, 0.35, len(b))
        t = k / (len(CAMPANAS) - 1)
        ruido = lambda: rng.normal(1.0, 0.03, len(b))

        b["Na_mgL"] = b["Na_mgL"] * (1 + intensidad * t * 3.0) * ruido()
        b["Cl_mgL"] = b["Cl_mgL"] * (1 + intensidad * t * 3.4) * ruido()
        b["SO4_mgL"] = b["SO4_mgL"] * (1 + intensidad * t * 1.2) * ruido()
        b["Ca_mgL"] = b["Ca_mgL"] * (1 - intensidad * t * 0.6) * ruido()
        b["Mg_mgL"] = b["Mg_mgL"] * (1 - intensidad * t * 0.3) * ruido()
        b["HCO3_mgL"] = b["HCO3_mgL"] * (1 - intensidad * t * 0.25) * ruido()
        b["K_mgL"] = b["K_mgL"] * ruido()
        b["F_mgL"] = b["F_mgL"] * ruido()

        # Fisico-quimica que el dataset real no trae, para que las vistas que
        # dependen de ella tambien se puedan probar.
        b["pH"] = np.round(7.4 + 0.35 * np.sin(k) + rng.normal(0, 0.08, len(b)), 2)
        b["Temp_C"] = np.round(21 + 4 * np.sin(k / 1.3) + rng.normal(0, 0.5, len(b)), 1)

        iones = ["Ca_mgL", "Mg_mgL", "Na_mgL", "K_mgL", "HCO3_mgL",
                 "CO3_mgL", "SO4_mgL", "Cl_mgL", "F_mgL"]
        b[iones] = b[iones].round(2)
        b["TDS_mgL"] = b[iones].sum(axis=1).round(0)
        bloques.append(b)

    salida = pd.concat(bloques, ignore_index=True)
    salida = salida.rename(columns={"Site": "Estacion", "Group": "Grupo"})
    salida = salida[[
        "Fecha", "Campana", "Estacion", "Grupo", "Longitude", "Latitude",
        "pH", "Temp_C", "TDS_mgL",
        "Ca_mgL", "Mg_mgL", "Na_mgL", "K_mgL",
        "HCO3_mgL", "CO3_mgL", "SO4_mgL", "Cl_mgL", "F_mgL",
    ]]

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    salida.to_csv(DESTINO, index=False, encoding="utf-8-sig")
    print(f"escrito: {DESTINO}")
    print(f"  {len(salida)} filas = {N_ESTACIONES} estaciones x {len(CAMPANAS)} campanas")
    print(f"  campanas: {CAMPANAS[0]} a {CAMPANAS[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
