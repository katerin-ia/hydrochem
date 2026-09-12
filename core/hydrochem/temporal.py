"""Analisis temporal: evolucion de cada estacion a lo largo de varias campanas.

Este modulo **no inventa fechas**. Si los datos no traen ``sampled_at``, todas
sus funciones devuelven estructuras vacias y ``TemporalIndex.has_dates`` es
falso, para que la interfaz pueda explicar que falta en lugar de dibujar una
serie ficticia. Los datos de referencia del proyecto (90 sitios del Death Valley
Regional Flow System) son una sola campana sin fechar, y asi se presentan.

Lo que si hace es estar listo: en cuanto un archivo traiga una columna de fecha,
estas funciones producen

``vertex_series``
    La evolucion de cada **vertice del diagrama de Piper** —los seis extremos de
    los dos triangulos— expresada en porcentaje sobre el total de cationes o de
    aniones. Es la lectura mas directa de si un agua se esta "moviendo" hacia el
    sodio, hacia el cloruro, etc.

``stiff_series``
    Lo mismo para las filas del diagrama de Stiff, en meq/L: util cuando importa
    la concentracion absoluta y no solo la proporcion.

``trajectories``
    El recorrido de cada estacion dentro del Piper, ordenado por fecha. Dibujado
    sobre el diagrama, muestra de un vistazo si la facies cambia.

``parameter_series``
    Serie temporal de cualquier parametro medido (TDS, un ion, el balance...).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .geometry import piper as piper_mod

DATE_COL = "sampled_at"
STATION_COL = "station_code"

#: Nombre de las seis columnas de porcentaje que produce ``piper.project``.
VERTEX_COLUMNS: tuple[str, ...] = (
    "pct_cat_left",
    "pct_cat_right",
    "pct_cat_apex",
    "pct_an_left",
    "pct_an_right",
    "pct_an_apex",
)

#: Numero minimo de campanas para que una tendencia signifique algo. Por debajo
#: se pueden dibujar los puntos, pero no hablar de tendencia.
MIN_CAMPAIGNS_FOR_TREND = 3


@dataclass
class TemporalIndex:
    """Que hay disponible en el eje del tiempo."""

    has_dates: bool = False
    campaigns: list[str] = field(default_factory=list)
    stations: list[str] = field(default_factory=list)
    #: Estaciones con mas de una campana: las unicas que admiten una serie.
    repeated_stations: list[str] = field(default_factory=list)
    n_undated: int = 0

    @property
    def n_campaigns(self) -> int:
        return len(self.campaigns)

    @property
    def can_plot_series(self) -> bool:
        return bool(self.repeated_stations)

    @property
    def can_discuss_trend(self) -> bool:
        return self.n_campaigns >= MIN_CAMPAIGNS_FOR_TREND

    def to_dict(self) -> dict:
        return {
            "has_dates": self.has_dates,
            "campaigns": self.campaigns,
            "n_campaigns": self.n_campaigns,
            "stations": self.stations,
            "repeated_stations": self.repeated_stations,
            "n_undated": self.n_undated,
            "can_plot_series": self.can_plot_series,
            "can_discuss_trend": self.can_discuss_trend,
            "min_campaigns_for_trend": MIN_CAMPAIGNS_FOR_TREND,
        }

    def message_es(self) -> str:
        """Explicacion para la pantalla, en el estado en que este."""
        if not self.has_dates:
            return (
                "Estos datos no traen fecha de muestreo, asi que se tratan como una "
                "unica campana. El analisis temporal se activara solo cuando cargues "
                "un archivo con una columna de fecha; no se inventan fechas."
            )
        if not self.repeated_stations:
            return (
                f"Hay {self.n_campaigns} fecha(s), pero ninguna estacion se repite en "
                "mas de una. Para ver una evolucion hace falta medir el mismo punto "
                "en campanas distintas."
            )
        if not self.can_discuss_trend:
            return (
                f"{self.n_campaigns} campanas y {len(self.repeated_stations)} estacion(es) "
                f"repetida(s). Se puede ver la evolucion, pero con menos de "
                f"{MIN_CAMPAIGNS_FOR_TREND} campanas no conviene hablar de tendencia."
            )
        return (
            f"{self.n_campaigns} campanas y {len(self.repeated_stations)} estacion(es) "
            "con seguimiento."
        )


def parse_dates(values) -> pd.Series:
    """Interpreta una columna de fechas sin exigir un formato concreto.

    Se intenta primero ISO (``2024-03-18``), que es lo que produce cualquier
    exportacion sensata, y solo si eso no cuaja se recurre a la deteccion
    elemento a elemento. Hacerlo al reves funciona igual pero llena la consola
    de avisos de pandas.
    """
    series = pd.Series(values)
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    try:
        parsed = pd.to_datetime(series, errors="coerce", format="ISO8601")
        if parsed.notna().any():
            return parsed
    except (ValueError, TypeError):
        pass
    return pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)


def normalise_dates(df: pd.DataFrame, column: str = DATE_COL) -> pd.DataFrame:
    """Convierte la columna de fecha a ``datetime``. Sin columna, no hace nada."""
    if column not in df.columns:
        return df
    out = df.copy()
    out[column] = parse_dates(out[column])
    return out


def build_index(df: pd.DataFrame) -> TemporalIndex:
    """Inventario de lo que hay en el eje del tiempo."""
    if DATE_COL not in df.columns or STATION_COL not in df.columns:
        return TemporalIndex(has_dates=False, n_undated=len(df))

    dates = parse_dates(df[DATE_COL])
    if dates.notna().sum() == 0:
        return TemporalIndex(has_dates=False, n_undated=len(df))

    dated = df.loc[dates.notna()].copy()
    dated["__date"] = dates[dates.notna()].dt.normalize()

    campaigns = sorted({d.strftime("%Y-%m-%d") for d in dated["__date"]})
    stations = sorted(dated[STATION_COL].astype(str).unique())
    counts = dated.groupby(dated[STATION_COL].astype(str))["__date"].nunique()

    return TemporalIndex(
        has_dates=True,
        campaigns=campaigns,
        stations=stations,
        repeated_stations=sorted(counts[counts > 1].index.tolist()),
        n_undated=int(dates.isna().sum()),
    )


def _dated(df: pd.DataFrame, stations: list[str] | None = None) -> pd.DataFrame:
    """Filas con fecha valida, ordenadas por estacion y fecha."""
    if DATE_COL not in df.columns or STATION_COL not in df.columns:
        return df.iloc[0:0]
    out = df.copy()
    out[DATE_COL] = parse_dates(out[DATE_COL])
    out = out.loc[out[DATE_COL].notna()]
    if stations:
        out = out.loc[out[STATION_COL].astype(str).isin(stations)]
    return out.sort_values([STATION_COL, DATE_COL])


def vertex_labels(convention: str | piper_mod.PiperConvention = "classic") -> dict[str, str]:
    """Etiqueta de cada vertice segun la convencion elegida.

    Importa: al cambiar de convencion cambia que ion ocupa cada vertice, y una
    serie temporal mal rotulada es peor que no tenerla.
    """
    conv = piper_mod.get_convention(convention)
    return {
        "pct_cat_left": conv.cation_left.label,
        "pct_cat_right": conv.cation_right.label,
        "pct_cat_apex": conv.cation_apex.label,
        "pct_an_left": conv.anion_left.label,
        "pct_an_right": conv.anion_right.label,
        "pct_an_apex": conv.anion_apex.label,
    }


def vertex_series(
    df: pd.DataFrame,
    stations: list[str] | None = None,
    convention: str | piper_mod.PiperConvention = "classic",
) -> pd.DataFrame:
    """Evolucion de los seis vertices del Piper, en porcentaje.

    :returns: formato largo con ``station_code``, ``sampled_at``, ``vertex``,
        ``label``, ``side`` (``cation``/``anion``) y ``pct`` (0-100).
        DataFrame vacio si no hay fechas o faltan las columnas del Piper.
    """
    dated = _dated(df, stations)
    present = [c for c in VERTEX_COLUMNS if c in dated.columns]
    if dated.empty or not present:
        return pd.DataFrame(
            columns=["station_code", "sampled_at", "vertex", "label", "side", "pct"]
        )

    labels = vertex_labels(convention)
    rows = []
    for vertex in present:
        rows.append(
            pd.DataFrame(
                {
                    "station_code": dated[STATION_COL].astype(str).to_numpy(),
                    "sampled_at": dated[DATE_COL].to_numpy(),
                    "vertex": vertex,
                    "label": labels.get(vertex, vertex),
                    "side": "cation" if "cat" in vertex else "anion",
                    "pct": pd.to_numeric(dated[vertex], errors="coerce").to_numpy() * 100.0,
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["station_code", "vertex", "sampled_at"]).reset_index(drop=True)


def stiff_series(
    df: pd.DataFrame,
    stations: list[str] | None = None,
    labels: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """Evolucion de cada lado de cada fila del Stiff, en meq/L.

    Complementa a ``vertex_series``: los porcentajes pueden quedarse quietos
    mientras la concentracion total se dispara, y al reves.
    """
    dated = _dated(df, stations)
    cols = [c for c in dated.columns if c.startswith("row") and c.endswith(("_left", "_right"))]
    if dated.empty or not cols:
        return pd.DataFrame(
            columns=["station_code", "sampled_at", "row", "side", "label", "meq"]
        )

    rows = []
    for col in sorted(cols):
        index = int(col[3 : col.index("_")])
        side = "left" if col.endswith("_left") else "right"
        label = ""
        if labels and index < len(labels):
            label = labels[index][0 if side == "left" else 1]
        rows.append(
            pd.DataFrame(
                {
                    "station_code": dated[STATION_COL].astype(str).to_numpy(),
                    "sampled_at": dated[DATE_COL].to_numpy(),
                    "row": index,
                    "side": side,
                    "label": label,
                    "meq": pd.to_numeric(dated[col], errors="coerce").to_numpy(),
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["station_code", "row", "side", "sampled_at"]).reset_index(drop=True)


def parameter_series(
    df: pd.DataFrame,
    parameters: list[str],
    stations: list[str] | None = None,
) -> pd.DataFrame:
    """Serie temporal de los parametros indicados (TDS, un ion, el CBE...)."""
    dated = _dated(df, stations)
    present = [p for p in parameters if p in dated.columns]
    if dated.empty or not present:
        return pd.DataFrame(columns=["station_code", "sampled_at", "parameter", "value"])

    rows = []
    for param in present:
        rows.append(
            pd.DataFrame(
                {
                    "station_code": dated[STATION_COL].astype(str).to_numpy(),
                    "sampled_at": dated[DATE_COL].to_numpy(),
                    "parameter": param,
                    "value": pd.to_numeric(dated[param], errors="coerce").to_numpy(),
                }
            )
        )
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["station_code", "parameter", "sampled_at"]).reset_index(drop=True)


def trajectories(
    df: pd.DataFrame, stations: list[str] | None = None
) -> dict[str, list[dict]]:
    """Recorrido de cada estacion dentro del Piper, ordenado por fecha.

    :returns: ``{estacion: [{fecha, cat:[x,y], an:[x,y], diamond:[x,y]}, ...]}``,
        solo para estaciones con mas de una campana: con un unico punto no hay
        trayectoria que dibujar.
    """
    dated = _dated(df, stations)
    needed = {"x_cat", "y_cat", "x_an", "y_an", "x_diamond", "y_diamond"}
    if dated.empty or not needed.issubset(dated.columns):
        return {}

    out: dict[str, list[dict]] = {}
    for station, block in dated.groupby(dated[STATION_COL].astype(str)):
        if len(block) < 2:
            continue
        out[str(station)] = [
            {
                "date": row[DATE_COL].strftime("%Y-%m-%d"),
                "cat": [float(row["x_cat"]), float(row["y_cat"])],
                "an": [float(row["x_an"]), float(row["y_an"])],
                "diamond": [float(row["x_diamond"]), float(row["y_diamond"])],
            }
            for _, row in block.iterrows()
            if pd.notna(row["x_cat"]) and pd.notna(row["x_diamond"])
        ]
    return {k: v for k, v in out.items() if len(v) >= 2}


def change_summary(
    df: pd.DataFrame,
    stations: list[str] | None = None,
    convention: str | piper_mod.PiperConvention = "classic",
) -> pd.DataFrame:
    """Cuanto ha cambiado cada vertice entre la primera y la ultima campana.

    Deliberadamente no es una regresion: con pocas campanas una pendiente da una
    falsa sensacion de precision. Esto es lo que se puede afirmar sin modelo,
    una diferencia entre dos medidas.
    """
    series = vertex_series(df, stations, convention)
    if series.empty:
        return pd.DataFrame(
            columns=["station_code", "vertex", "label", "first", "last",
                     "delta_pp", "n_campaigns"]
        )

    rows = []
    for (station, vertex), block in series.groupby(["station_code", "vertex"], sort=False):
        valid = block.dropna(subset=["pct"])
        if len(valid) < 2:
            continue
        first, last = float(valid["pct"].iloc[0]), float(valid["pct"].iloc[-1])
        rows.append(
            {
                "station_code": station,
                "vertex": vertex,
                "label": valid["label"].iloc[0],
                "first": first,
                "last": last,
                "delta_pp": last - first,  # puntos porcentuales
                "n_campaigns": int(valid["sampled_at"].nunique()),
            }
        )
    return pd.DataFrame(rows)
