"""Exportacion a GeoJSON, KML suelto y CSV/XLSX.

Formatos que el notebook no producia: solo generaba KMZ y un Excel de resultados.
GeoJSON es el que sirve para meter los puntos en QGIS o en cualquier visor web
sin conversion intermedia.
"""

from __future__ import annotations

import io
import json

import pandas as pd

from ...chemistry import facies as facies_mod
from ...constants import ALL_IONS, IONS
from . import kml as kml_mod

LON_COL = "lon_wgs84"
LAT_COL = "lat_wgs84"

#: Columnas que se llevan como atributos, con su nombre legible. El orden
#: importa: es el que veran en la tabla de atributos de QGIS.
ATTRIBUTES: list[tuple[str, str]] = [
    ("station_code", "estacion"),
    ("group", "grupo"),
    ("sampled_at", "fecha"),
    (facies_mod.FACIES_COL, "facies_codigo"),
    (facies_mod.FACIES_LABEL_COL, "facies"),
    ("ph", "pH"),
    ("temp_c", "temp_C"),
    ("do_mgl", "OD_mgL"),
    ("tds_mgl", "TDS_mgL"),
    ("Alkalinity_mgCaCO3", "alcalinidad_mgCaCO3"),
    ("sum_cat", "suma_cationes_meqL"),
    ("sum_an", "suma_aniones_meqL"),
    ("CBE_pct", "balance_carga_pct"),
    ("CBE_flag", "balance_estado"),
]


def _value(v):
    """Valor apto para JSON: los NaN pasan a null y los Timestamp a ISO."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, (bool, int, float, str)):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _properties(row: pd.Series) -> dict:
    props: dict = {}
    for col, label in ATTRIBUTES:
        if col in row.index:
            val = _value(row[col])
            if val is not None:
                props[label] = val
    for ion in ALL_IONS:
        for suffix, unit in (("_mgL", "mgL"), ("_meq", "meqL")):
            col = f"{ion}{suffix}"
            if col in row.index:
                val = _value(row[col])
                if val is not None:
                    props[f"{ion}_{unit}"] = val
    imputed = [
        IONS[i].label for i in ALL_IONS
        if f"{i}_mgL__imputed" in row.index and bool(row.get(f"{i}_mgL__imputed"))
    ]
    if imputed:
        props["valores_estimados"] = ", ".join(imputed)
    return props


def _with_coordinates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if LON_COL not in df.columns or LAT_COL not in df.columns:
        raise ValueError(
            "Faltan las columnas de coordenadas WGS84. Llama antes a "
            "geo.crs.add_wgs84_columns()."
        )
    lon = pd.to_numeric(df[LON_COL], errors="coerce")
    lat = pd.to_numeric(df[LAT_COL], errors="coerce")
    ok = lon.notna() & lat.notna()
    return df.loc[ok], int((~ok).sum())


def to_geojson(df: pd.DataFrame, name: str = "HydroChem", indent: int = 1) -> str:
    """``FeatureCollection`` de puntos con todos los atributos calculados."""
    work, skipped = _with_coordinates(df)
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row[LON_COL]), float(row[LAT_COL])],
            },
            "properties": _properties(row),
        }
        for _, row in work.iterrows()
    ]
    payload = {
        "type": "FeatureCollection",
        "name": name,
        # CRS84 es el que asume GeoJSON (RFC 7946); se declara para que no haya duda.
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    if skipped:
        payload["omitidas_sin_coordenadas"] = skipped
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def to_kml(
    df: pd.DataFrame, name: str = "HydroChem", group_col: str = "group",
    colour_by: str = "facies",
) -> str:
    """KML suelto, sin imagenes: marcadores de color con la ficha en el globo.

    Pesa mil veces menos que el KMZ y se abre igual en Google Earth. El KMZ solo
    hace falta si se quieren los diagramas de Stiff como icono.
    """
    from .kmz import PALETTE, _popup_html

    work, _ = _with_coordinates(df)
    if colour_by == "facies" and facies_mod.FACIES_COL in work.columns:
        keys = work[facies_mod.FACIES_COL].astype(str)
        unique = list(dict.fromkeys(keys))
        colours = {k: facies_mod.color_of(k) for k in unique}
    else:
        keys = (work[group_col].astype(str) if group_col in work.columns
                else pd.Series("Sin grupo", index=work.index))
        unique = list(dict.fromkeys(keys))
        colours = {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(unique)}

    doc = kml_mod.Document(name=name, description=f"{len(work)} muestras")
    circle = "http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"
    for i, key in enumerate(unique):
        doc.styles.append(
            kml_mod.IconStyle(f"c{i}", icon_href=circle, color_hex=colours[key], scale=1.1)
        )
    style_of = {key: f"c{i}" for i, key in enumerate(unique)}

    grouping = (work[group_col].astype(str) if group_col in work.columns
                else pd.Series("Sin grupo", index=work.index))
    for group in dict.fromkeys(grouping):
        sub = work.loc[grouping == group]
        folder = kml_mod.Folder(name=f"{group} ({len(sub)})")
        for idx, row in sub.iterrows():
            folder.placemarks.append(
                kml_mod.Placemark(
                    name=str(row.get("station_code", "")),
                    lon=float(row[LON_COL]),
                    lat=float(row[LAT_COL]),
                    description_html=_popup_html(row, None, None, ""),
                    style_id=style_of[str(keys.loc[idx])],
                )
            )
        doc.folders.append(folder)
    return doc.to_xml()


#: Columnas internas que no aportan nada al usuario final.
_INTERNAL_PREFIXES = ("__", "row0_", "row1_", "row2_", "row3_", "x_", "y_", "pct_")


def tidy_for_export(df: pd.DataFrame, keep_geometry: bool = True) -> pd.DataFrame:
    """Quita las columnas de uso interno y ordena el resto de forma legible."""
    drop = [
        c for c in df.columns
        if c.startswith(_INTERNAL_PREFIXES) or c.endswith("__detection_limit")
    ]
    out = df.drop(columns=drop, errors="ignore")

    orden: list[str] = []
    for col, _ in ATTRIBUTES:
        if col in out.columns:
            orden.append(col)
    if keep_geometry:
        for col in (LON_COL, LAT_COL, "longitude", "latitude"):
            if col in out.columns:
                orden.append(col)
    for ion in ALL_IONS:
        for suffix in ("_mgL", "_meq"):
            if f"{ion}{suffix}" in out.columns:
                orden.append(f"{ion}{suffix}")
    resto = [c for c in out.columns if c not in orden]
    return out[orden + resto]


def to_csv(df: pd.DataFrame) -> bytes:
    """CSV en UTF-8 con BOM, que es lo que Excel abre sin estropear los acentos."""
    buf = io.StringIO()
    tidy_for_export(df).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(
    df: pd.DataFrame,
    validation: pd.DataFrame | None = None,
    compliance: pd.DataFrame | None = None,
    facies_summary: pd.DataFrame | None = None,
    equivalent_weights: pd.DataFrame | None = None,
) -> bytes:
    """Libro de Excel con una hoja por bloque de informacion.

    El notebook producia una sola hoja con 30 columnas. Aqui se separan los
    resultados de los metadatos, para que el Excel se pueda leer.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        tidy_for_export(df).to_excel(writer, sheet_name="Resultados", index=False)
        if facies_summary is not None and not facies_summary.empty:
            facies_summary.to_excel(writer, sheet_name="Facies", index=False)
        if compliance is not None and not compliance.empty:
            compliance.to_excel(writer, sheet_name="Umbrales", index=False)
        if validation is not None and not validation.empty:
            validation.to_excel(writer, sheet_name="Validacion", index=False)
        if equivalent_weights is not None and not equivalent_weights.empty:
            equivalent_weights.to_excel(writer, sheet_name="Pesos equivalentes",
                                        index=False)

        # Anchos legibles y cabecera fijada
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            for column in sheet.columns:
                largo = max((len(str(c.value)) for c in column[:60] if c.value), default=8)
                sheet.column_dimensions[column[0].column_letter].width = min(
                    max(largo + 2, 10), 34
                )
    return buf.getvalue()
