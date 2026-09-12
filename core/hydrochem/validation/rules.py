"""Reglas de validacion sobre los datos ya mapeados al esquema canonico.

Comprueba lo que el notebook no comprobaba: rangos plausibles por parametro,
duplicados, coordenadas, ceros sospechosos, columnas sin ninguna medida y
balance de carga. Nada se corrige automaticamente: se informa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..constants import ALL_IONS, IONS, MAJOR_IONS
from ..imputation.strategies import count_exact_zeros
from .report import Severity, ValidationReport

#: Rangos plausibles en aguas naturales continentales, en mg/L salvo indicacion.
#: Fuera de ellos el dato no es imposible, pero casi siempre indica un error de
#: unidades o de transcripcion, asi que se avisa.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "Ca_mgL": (0.0, 2000.0),
    "Mg_mgL": (0.0, 2000.0),
    "Na_mgL": (0.0, 20000.0),
    "K_mgL": (0.0, 1000.0),
    "HCO3_mgL": (0.0, 2000.0),
    "CO3_mgL": (0.0, 1000.0),
    "SO4_mgL": (0.0, 5000.0),
    "Cl_mgL": (0.0, 30000.0),
    "F_mgL": (0.0, 50.0),
    "NO3_mgL": (0.0, 1000.0),
    "ph": (0.0, 14.0),
    "temp_c": (-5.0, 100.0),
    "do_mgl": (0.0, 25.0),
    "tds_mgl": (0.0, 100000.0),
    "ec_uscm": (0.0, 200000.0),
}

ION_COLUMNS = tuple(f"{i}_mgL" for i in ALL_IONS)
MAJOR_COLUMNS = tuple(f"{i}_mgL" for i in MAJOR_IONS)


def validate(df: pd.DataFrame, report: ValidationReport | None = None) -> ValidationReport:
    """Aplica todas las reglas y devuelve el informe."""
    rep = report or ValidationReport()
    rep.n_rows = len(df)
    rep.n_columns_mapped = len(df.columns)

    if df.empty:
        rep.add(Severity.ERROR, "sin_datos", "El archivo no contiene ninguna muestra.")
        return rep

    _check_identity(df, rep)
    _check_ions_present(df, rep)
    _check_ranges(df, rep)
    _check_suspicious_zeros(df, rep)
    _check_coordinates(df, rep)
    _check_temporal(df, rep)
    _column_stats(df, rep)
    return rep


# --------------------------------------------------------------------------


def _check_identity(df: pd.DataFrame, rep: ValidationReport) -> None:
    if "station_code" not in df.columns:
        rep.add(
            Severity.ERROR, "sin_estacion",
            "No se ha reconocido ninguna columna con el codigo o nombre de la estacion.",
            hint="Indica cual es en el mapeo de columnas.",
        )
        return

    codes = df["station_code"].astype(str).str.strip()
    blank = codes[codes.isin(["", "nan", "None"])]
    if len(blank):
        rep.add(
            Severity.ERROR, "estacion_vacia",
            f"{len(blank)} muestra(s) sin codigo de estacion.",
            "station_code", blank.index.tolist(),
        )

    has_date = "sampled_at" in df.columns and df["sampled_at"].notna().any()
    duplicated = codes[codes.duplicated(keep=False) & ~codes.isin(["", "nan", "None"])]
    if len(duplicated) and not has_date:
        rep.add(
            Severity.WARNING, "estacion_duplicada",
            f"{duplicated.nunique()} codigo(s) de estacion se repiten en "
            f"{len(duplicated)} filas, y no hay fecha que las distinga.",
            "station_code", duplicated.index.tolist(),
            hint=(
                "Sin fecha, dos muestras de la misma estacion son indistinguibles. "
                "Anade una columna de fecha o diferencia los codigos."
            ),
        )


def _check_ions_present(df: pd.DataFrame, rep: ValidationReport) -> None:
    present = [c for c in ION_COLUMNS if c in df.columns]
    if not present:
        rep.add(
            Severity.ERROR, "sin_iones",
            "No se ha reconocido ninguna columna de iones mayoritarios.",
            hint="El analisis hidroquimico necesita al menos Ca, Mg, Na, HCO3, SO4 y Cl.",
        )
        return

    missing_major = [c for c in MAJOR_COLUMNS if c not in df.columns]
    if missing_major:
        nombres = ", ".join(IONS[c.replace("_mgL", "")].label for c in missing_major)
        rep.add(
            Severity.WARNING, "falta_ion_mayoritario",
            f"No se midieron {len(missing_major)} ion(es) mayoritario(s): {nombres}.",
            hint=(
                "El balance de carga y el diagrama de Piper se calcularan sin ellos, "
                "lo que sesga el resultado."
            ),
        )

    # Columnas presentes pero sin una sola medida: el caso del NO3 (riesgo R4).
    for col in present:
        series = pd.to_numeric(df[col], errors="coerce")
        if series.isna().all():
            rep.add(
                Severity.WARNING, "columna_sin_medidas",
                f"La columna {col} existe pero no tiene ni un valor.",
                col,
                hint=(
                    "Se excluye del analisis. No se rellenara con ceros ni con "
                    "medianas: eso falsearia el balance de carga y el Piper."
                ),
            )


def _check_ranges(df: pd.DataFrame, rep: ValidationReport) -> None:
    for col, (low, high) in PLAUSIBLE_RANGES.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        out = series[(series < low) | (series > high)]
        if len(out):
            rep.add(
                Severity.WARNING, "fuera_de_rango",
                f"{len(out)} valor(es) de {col} fuera del rango plausible "
                f"({low:g} a {high:g}).",
                col, out.index.tolist(),
                hint="Suele indicar un error de unidades o de transcripcion.",
            )
        negative = series[series < 0]
        if len(negative):
            rep.add(
                Severity.ERROR, "valor_negativo",
                f"{len(negative)} valor(es) negativo(s) en {col}.",
                col, negative.index.tolist(),
            )


def _check_suspicious_zeros(df: pd.DataFrame, rep: ValidationReport) -> None:
    """Riesgo R3: un 0 exacto en un ion traza casi nunca es una medida."""
    zeros = count_exact_zeros(df, [c for c in ION_COLUMNS if c in df.columns])
    for col, n in zeros.items():
        ion = col.replace("_mgL", "")
        # CO3 = 0 es quimicamente normal a pH < 8,3; los demas no.
        if ion == "CO3":
            continue
        share = n / len(df)
        if share >= 0.10:
            rep.add(
                Severity.WARNING, "ceros_sospechosos",
                f"{n} de {len(df)} muestras ({share:.0%}) tienen {col} "
                f"exactamente 0.",
                col,
                df.index[pd.to_numeric(df[col], errors="coerce") == 0].tolist(),
                hint=(
                    "Un cero exacto suele significar 'no medido', no 'ausente'. "
                    "El manual del libro PiperStiff documenta que las celdas vacias "
                    "se escriben como 0. Si es tu caso, marcalos como ausentes antes "
                    "de analizar."
                ),
            )


def _check_coordinates(df: pd.DataFrame, rep: ValidationReport) -> None:
    if "longitude" not in df.columns or "latitude" not in df.columns:
        rep.add(
            Severity.INFO, "sin_coordenadas",
            "No hay coordenadas: el mapa y la exportacion a Google Earth no estaran disponibles.",
        )
        return

    lon = pd.to_numeric(df["longitude"], errors="coerce")
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    missing = df.index[lon.isna() | lat.isna()]
    if len(missing):
        rep.add(
            Severity.WARNING, "coordenada_incompleta",
            f"{len(missing)} muestra(s) sin coordenadas completas.",
            "longitude", missing.tolist(),
            hint="No apareceran en el mapa ni en el KMZ.",
        )

    looks_projected = (lat.abs() > 90).any() or (lon.abs() > 180).any()
    if looks_projected:
        rep.add(
            Severity.INFO, "coordenadas_proyectadas",
            "Las coordenadas no estan en grados decimales; parecen UTM u otra proyeccion.",
            hint="Indica el sistema de coordenadas para poder situarlas en el mapa.",
        )
    elif lon.notna().any():
        swapped = (lat.abs().max() or 0) <= 90 and (lon.abs().max() or 0) <= 90
        if swapped and (lon.abs().max() or 0) > (lat.abs().max() or 0):
            rep.add(
                Severity.INFO, "posible_intercambio",
                "Comprueba que longitud y latitud no esten intercambiadas.",
            )


def _check_temporal(df: pd.DataFrame, rep: ValidationReport) -> None:
    """La dimension temporal es opcional. Se informa de su ausencia sin
    presentarla como un problema: los datos de una sola campana son validos."""
    if "sampled_at" not in df.columns or df["sampled_at"].isna().all():
        rep.add(
            Severity.INFO, "sin_fecha",
            "Los datos no traen fecha de muestreo: se tratan como una unica campana.",
            hint=(
                "El analisis temporal se activara solo cuando cargues datos con "
                "fecha. No se inventan fechas."
            ),
        )
        return

    from ..temporal import parse_dates

    dates = parse_dates(df["sampled_at"])
    n_bad = int(dates.isna().sum())
    if n_bad:
        rep.add(
            Severity.WARNING, "fecha_ilegible",
            f"{n_bad} fecha(s) no se pudieron interpretar.",
            "sampled_at", df.index[dates.isna()].tolist(),
        )
    n_dates = int(dates.dropna().dt.normalize().nunique())
    rep.add(
        Severity.INFO, "campanas_detectadas",
        f"Se detectaron {n_dates} fecha(s) de muestreo distintas.",
        "sampled_at",
        hint=("El analisis temporal requiere al menos 2 campanas." if n_dates < 2 else None),
    )


def _column_stats(df: pd.DataFrame, rep: ValidationReport) -> None:
    """Resumen numerico por columna, para la pantalla de datos."""
    stats: list[dict] = []
    for col in df.columns:
        series = pd.to_numeric(df[col], errors="coerce")
        numeric = series.notna().sum()
        row = {
            "column": col,
            "n_present": int(df[col].notna().sum()),
            "n_missing": int(df[col].isna().sum()),
            "n_numeric": int(numeric),
        }
        if numeric:
            row.update(
                {
                    "min": float(np.nanmin(series)),
                    "max": float(np.nanmax(series)),
                    "mean": float(np.nanmean(series)),
                    "median": float(np.nanmedian(series)),
                }
            )
        stats.append(row)
    rep.column_stats = stats
