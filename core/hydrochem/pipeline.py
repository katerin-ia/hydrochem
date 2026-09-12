"""Orquestacion de extremo a extremo: de un archivo a un dataset analizado.

Es el unico punto que la aplicacion necesita conocer. Sustituye a la cadena de
celdas del notebook, que dependia del orden de ejecucion y de una decena de
variables globales (riesgo R11): aqui todo son parametros y valores devueltos.

    archivo -> lectura -> mapeo -> censura -> validacion
            -> imputacion -> meq/L -> balance -> alcalinidad
            -> proyeccion Piper -> filas Stiff
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .chemistry import facies as facies_mod
from .chemistry.alkalinity import ALKALINITY_COL, add_alkalinity
from .chemistry.balance import CBE_COL, CBE_FLAG_COL, add_charge_balance
from .chemistry.units import add_meq_columns, meq_column
from .constants import ALL_IONS, DEFAULT_EW_TABLE
from .geometry import piper as piper_mod
from .geometry import stiff as stiff_mod
from .imputation.strategies import ImputationMethod, ImputationResult, impute, zeros_as_missing
from .io.column_mapping import ColumnMapping
from .io.detection_limits import apply_to_frame
from .geo import crs as crs_mod
from .io.readers import ReadResult, read_table
from .quality import standards as std_mod
from .temporal import normalise_dates
from .validation.report import Severity, ValidationReport
from .validation.rules import validate

ION_COLUMNS = [f"{i}_mgL" for i in ALL_IONS]


@dataclass
class AnalysisOptions:
    """Todo lo que el usuario puede decidir. Los valores por defecto son los
    conservadores: no imputar y no tocar los ceros."""

    ew_table: str = DEFAULT_EW_TABLE
    piper_convention: str = piper_mod.DEFAULT_CONVENTION
    stiff_template: str = stiff_mod.DEFAULT_TEMPLATE
    imputation: str = ImputationMethod.NONE.value
    min_group_size: int = 3
    #: Iones cuyos ceros exactos deben leerse como "no medido" (riesgo R3).
    zeros_as_missing_for: tuple[str, ...] = ()
    cbe_acceptable_pct: float = 5.0
    cbe_marginal_pct: float = 10.0
    #: Esquema de clasificacion hidroquimica.
    facies_scheme: str = facies_mod.DEFAULT_SCHEME
    #: Umbrales normativos con los que comprobar las excedencias.
    standard: str = std_mod.DEFAULT_STANDARD
    #: Sistema de coordenadas de la entrada. ``None`` = deducirlo del rango, que
    #: es solo una sugerencia; el usuario deberia confirmarlo.
    crs: str | None = None

    def to_dict(self) -> dict:
        return {
            "ew_table": self.ew_table,
            "piper_convention": self.piper_convention,
            "stiff_template": self.stiff_template,
            "imputation": self.imputation,
            "min_group_size": self.min_group_size,
            "zeros_as_missing_for": list(self.zeros_as_missing_for),
            "cbe_acceptable_pct": self.cbe_acceptable_pct,
            "cbe_marginal_pct": self.cbe_marginal_pct,
            "facies_scheme": self.facies_scheme,
            "standard": self.standard,
            "crs": self.crs,
        }


@dataclass
class Dataset:
    """Un conjunto de datos leido, validado y analizado."""

    data: pd.DataFrame
    report: ValidationReport
    mapping: ColumnMapping
    options: AnalysisOptions
    source: str = ""
    read_result: ReadResult | None = None
    imputation: ImputationResult | None = None
    censoring: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def n_samples(self) -> int:
        return len(self.data)

    @property
    def groups(self) -> list[str]:
        if "group" not in self.data.columns:
            return []
        return [g for g in dict.fromkeys(self.data["group"].dropna().astype(str))]

    @property
    def measured_ions(self) -> list[str]:
        """Iones con al menos una medida. NO3 no esta aqui en el dataset de
        referencia, y por eso no aparece en ningun calculo."""
        out = []
        for ion in ALL_IONS:
            col = f"{ion}_mgL"
            if col in self.data.columns and pd.to_numeric(self.data[col], errors="coerce").notna().any():
                out.append(ion)
        return out

    @property
    def has_coordinates(self) -> bool:
        # bool() explicito: .any() de pandas devuelve numpy.bool_, que no es
        # serializable a JSON aunque se comporte como un bool.
        return bool(
            "longitude" in self.data.columns
            and "latitude" in self.data.columns
            and pd.to_numeric(self.data["longitude"], errors="coerce").notna().any()
        )

    @property
    def has_dates(self) -> bool:
        return bool(
            "sampled_at" in self.data.columns and self.data["sampled_at"].notna().any()
        )

    @property
    def crs(self):
        """Sistema de coordenadas efectivo, ya resuelto."""
        if self.options.crs is not None:
            return crs_mod.parse_crs(self.options.crs)
        if not {"longitude", "latitude"} <= set(self.data.columns):
            return crs_mod.WGS84
        return crs_mod.suggest_crs(self.data["longitude"], self.data["latitude"])

    @property
    def facies_counts(self) -> pd.DataFrame:
        if facies_mod.FACIES_COL not in self.data.columns:
            return pd.DataFrame(columns=["facies", "n", "pct"])
        return facies_mod.summary(self.data[facies_mod.FACIES_COL])

    @property
    def compliance(self) -> pd.DataFrame:
        """Excedencias por parametro frente al estandar elegido."""
        if not self.options.standard:
            return pd.DataFrame()
        return std_mod.check(self.data, self.options.standard)

    @property
    def temporal(self):
        """Inventario de lo disponible en el eje del tiempo."""
        from .temporal import build_index

        return build_index(self.data)

    @property
    def campaigns(self) -> list[str]:
        """Fechas de muestreo distintas, en orden. Vacio si no hay fechas: la
        aplicacion usa esto para desactivar el modulo temporal y explicarlo."""
        if not self.has_dates:
            return []
        dates = pd.to_datetime(self.data["sampled_at"], errors="coerce").dropna()
        return sorted({d.strftime("%Y-%m-%d") for d in dates})


def analyse(
    source: str | Path | pd.DataFrame,
    options: AnalysisOptions | None = None,
    mapping: ColumnMapping | None = None,
    sheet: str | int | None = None,
) -> Dataset:
    """Lee y analiza un archivo (o un DataFrame ya mapeado) de principio a fin."""
    opts = options or AnalysisOptions()

    # -- 1. lectura y mapeo al esquema canonico ------------------------------
    read_result: ReadResult | None = None
    if isinstance(source, pd.DataFrame):
        canonical = source.copy()
        mapping = mapping or ColumnMapping.suggest(source.columns)
        if set(mapping.mapping.values()) & set(source.columns):
            canonical = mapping.apply(source)
        name = "(DataFrame)"
        notes: list[str] = []
    else:
        read_result = read_table(source, sheet=sheet, mapping=mapping)
        mapping = read_result.mapping
        canonical = mapping.apply(read_result.data)
        name = read_result.source
        notes = list(read_result.notes)

    # -- 1b. fechas -----------------------------------------------------------
    # Se normalizan una sola vez y aqui, para que todo lo que viene despues
    # trabaje con datetime y no con texto. Si no hay columna, no pasa nada.
    canonical = normalise_dates(canonical)

    # -- 2. valores censurados (<0,05, ND) ----------------------------------
    ion_cols = [c for c in ION_COLUMNS if c in canonical.columns]
    physchem = [c for c in ("ph", "temp_c", "do_mgl", "tds_mgl", "ec_uscm") if c in canonical.columns]
    canonical, censoring = apply_to_frame(canonical, ion_cols + physchem)

    # -- 3. ceros que en realidad son "no medido" ---------------------------
    if opts.zeros_as_missing_for:
        cols = [f"{i}_mgL" for i in opts.zeros_as_missing_for if f"{i}_mgL" in canonical.columns]
        canonical = zeros_as_missing(canonical, cols)
        notes.append(
            "Los ceros exactos de " + ", ".join(cols) + " se han marcado como no medidos."
        )

    # -- 4. validacion -------------------------------------------------------
    report = validate(canonical)
    report.notes.extend(notes)
    if read_result is not None:
        report.add(
            Severity.INFO, "filas_leidas",
            f"Se leyeron {read_result.n_rows} muestras de {read_result.source}"
            + (f", hoja {read_result.sheet}" if read_result.sheet else "")
            + ".",
        )

    if not report.ok:
        return Dataset(canonical, report, mapping, opts, name, read_result, None, censoring)

    # -- 5. imputacion (por defecto, ninguna) -------------------------------
    imputation = impute(
        canonical,
        ion_cols,
        opts.imputation,
        group_col="group" if "group" in canonical.columns else None,
        min_group_size=opts.min_group_size,
    )
    work = imputation.data
    for msg in imputation.messages_es():
        report.notes.append(msg)

    # -- 6. quimica ----------------------------------------------------------
    work = add_meq_columns(work, ions=ALL_IONS, ew_table=opts.ew_table)
    unreliable = ~imputation.reliability if imputation.reliability is not None else None
    work = add_charge_balance(
        work,
        acceptable=opts.cbe_acceptable_pct,
        marginal=opts.cbe_marginal_pct,
        unreliable_mask=unreliable,
    )
    if meq_column("HCO3") in work.columns:
        work = add_alkalinity(work)

    # -- 6b. clasificacion hidroquimica -------------------------------------
    work = facies_mod.add_facies(work, opts.facies_scheme)

    # -- 6c. coordenadas en WGS84 -------------------------------------------
    # Una sola pareja de columnas para el mapa y para todas las exportaciones.
    # El notebook mezclaba las crudas con las reproyectadas segun la celda.
    work = crs_mod.add_wgs84_columns(work, opts.crs)

    # -- 6d. umbrales normativos --------------------------------------------
    if opts.standard:
        work = std_mod.add_compliance(work, opts.standard)

    # -- 7. geometria de los diagramas --------------------------------------
    projected = piper_mod.project(work, opts.piper_convention)
    work = work.join(projected)
    work = work.join(stiff_mod.row_values(work, opts.stiff_template))

    # -- 8. procedencia de cada celda ---------------------------------------
    for col in ion_cols:
        work[f"{col}__imputed"] = imputation.flags[col] if col in imputation.flags else False

    _report_charge_balance(work, report)
    _report_compliance(work, opts, report)
    _report_crs(work, opts, report)

    return Dataset(work, report, mapping, opts, name, read_result, imputation, censoring)


def _report_compliance(
    df: pd.DataFrame, opts: AnalysisOptions, report: ValidationReport
) -> None:
    """Resume las excedencias normativas y avisa si el estandar no esta cotejado."""
    if not opts.standard:
        return
    std = std_mod.get_standard(opts.standard)
    if not std.verified:
        report.add(
            Severity.WARNING, "estandar_sin_cotejar",
            f"Los umbrales de {std.name_es} son una plantilla sin cotejar con el "
            "texto oficial.",
            hint="Verifica cada cifra antes de usarla en un informe.",
        )
    tabla = std_mod.check(df, std)
    for _, row in tabla.iterrows():
        if not row["n_exceeding"]:
            continue
        severidad = Severity.WARNING if row["kind"] == "health" else Severity.INFO
        col = f"{row['parameter']}__exceeds"
        filas = df.index[df[col]].tolist() if col in df.columns else []
        report.add(
            severidad, "excede_umbral",
            f"{int(row['n_exceeding'])} de {int(row['n_measured'])} muestras medidas "
            f"({row['pct']:.0f} %) superan el umbral {row['kind_label']} de "
            f"{row['label']} ({row['range_text']}).",
            row["parameter"], filas,
            hint=row["note"] or None,
        )


def _report_crs(
    df: pd.DataFrame, opts: AnalysisOptions, report: ValidationReport
) -> None:
    """Deja constancia del sistema de coordenadas usado, y de si fue supuesto."""
    if not {"longitude", "latitude"} <= set(df.columns):
        return
    if opts.crs is not None:
        crs = crs_mod.parse_crs(opts.crs)
        report.add(
            Severity.INFO, "crs_declarado",
            f"Coordenadas interpretadas como {crs.name} (EPSG:{crs.epsg}).",
        )
        return
    crs = crs_mod.suggest_crs(df["longitude"], df["latitude"])
    if crs.is_geographic:
        report.add(
            Severity.INFO, "crs_supuesto",
            "Las coordenadas parecen grados decimales WGS84 y se han tratado asi.",
        )
    else:
        report.add(
            Severity.WARNING, "crs_sin_declarar",
            f"Las coordenadas parecen proyectadas. Se ha supuesto {crs.name}, "
            "pero la zona es una conjetura.",
            hint="Elige el sistema correcto: si la zona esta mal, los puntos "
                 "apareceran a cientos de kilometros de su sitio.",
        )


def _report_charge_balance(df: pd.DataFrame, report: ValidationReport) -> None:
    if CBE_FLAG_COL not in df.columns:
        return
    rejected = df.index[df[CBE_FLAG_COL] == "rejected"].tolist()
    marginal = df.index[df[CBE_FLAG_COL] == "marginal"].tolist()
    if rejected:
        report.add(
            Severity.WARNING, "balance_rechazado",
            f"{len(rejected)} muestra(s) con error de balance de carga superior al 10 %.",
            CBE_COL, rejected,
            hint="Revisa el analisis: suele faltar un ion o sobrar un cero.",
        )
    if marginal:
        report.add(
            Severity.INFO, "balance_marginal",
            f"{len(marginal)} muestra(s) con error de balance entre el 5 % y el 10 %.",
            CBE_COL, marginal,
        )
