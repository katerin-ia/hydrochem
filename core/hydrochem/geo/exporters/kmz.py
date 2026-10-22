"""Construccion del KMZ para Google Earth.

Un KMZ es un ZIP que contiene ``doc.kml`` y los recursos que este referencia.
Se empaqueta con ``zipfile`` de la libreria estandar, sin dependencias.

Que trae el archivo resultante, y por que:

- **El icono de cada punto es su propio diagrama de Stiff.** Es el rasgo
  distintivo de la herramienta original de Halford y lo que hace util el mapa:
  se ve la forma del agua sin abrir nada.
- Una carpeta por grupo, plegable desde el panel de Google Earth.
- Globo de informacion con la ficha completa: fisico-quimica, iones en mg/L y
  meq/L, balance de carga, alcalinidad, facies y las excedencias normativas.
- Leyenda como ``ScreenOverlay``. El notebook la hacia con marcadores en la
  coordenada (0, 0), que caen en el golfo de Guinea.
- Los valores estimados se marcan con un asterisco y se explican al pie, para
  que nadie confunda un dato medido con uno imputado.
"""

from __future__ import annotations

import io
import json
import textwrap
import math
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ...chemistry import facies as facies_mod
from ...constants import ALL_IONS, IONS
from ...quality import standards as std_mod
from . import kml as kml_mod
from .stiff_icons import render_map_icons, render_popup_images
from ...geometry import stiff as stiff_mod
from ...report.plotting import serialized

LON_COL = "lon_wgs84"
LAT_COL = "lat_wgs84"

PALETTE = ["#0f7d52", "#c24a1f", "#3b56c4", "#a8267a",
           "#8a6a00", "#0e7f9e", "#9b2226", "#6b3fa0"]


@dataclass
class KmzResult:
    """El archivo y un resumen de lo que quedo dentro."""

    content: bytes
    n_placemarks: int
    n_groups: int
    n_skipped: int
    filename: str = "hydrochem.kmz"

    @property
    def size_kb(self) -> int:
        return len(self.content) // 1024

    def to_dict(self) -> dict:
        return {
            "filename": self.filename, "size_kb": self.size_kb,
            "n_placemarks": self.n_placemarks, "n_groups": self.n_groups,
            "n_skipped": self.n_skipped,
        }


def _fmt(value, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):,.{decimals}f}".replace(",", " ")
    except (TypeError, ValueError):
        return escape(str(value))


def _popup_html(
    row: pd.Series,
    image_name: str | None,
    compliance: pd.DataFrame | None,
    standard_name: str,
    scale_note: str = "",
) -> str:
    """Ficha completa de la muestra, en HTML para el globo de Google Earth."""
    style = (
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#12232a}"
        "table{border-collapse:collapse;width:100%;margin:4px 0}"
        "td,th{border:1px solid #d5dfe2;padding:3px 7px;text-align:left}"
        "th{background:#0e6b75;color:#fff;font-weight:600}"
        "td.n{text-align:right;font-variant-numeric:tabular-nums}"
        "h3{margin:0 0 2px;font-size:15px}"
        ".sub{color:#53686f;font-size:11px;margin-bottom:6px}"
        ".warn{color:#a2322c;font-weight:600}"
        ".foot{color:#7f9299;font-size:10px;margin-top:6px}"
        "</style>"
    )

    img = ""
    if image_name:
        img = (
            f'<div style="text-align:center;margin:6px 0">'
            f'<img src="{kml_mod.FILES_DIR}/{escape(image_name)}" width="{160 if image_name.startswith("stiff_") else 360}"/></div>'
        )

    imputed = [
        ion for ion in ALL_IONS
        if f"{ion}_mgL__imputed" in row.index and bool(row.get(f"{ion}_mgL__imputed"))
    ]

    fisico = [
        ("pH", _fmt(row.get("ph"), 2)),
        ("Temperatura (°C)", _fmt(row.get("temp_c"), 1)),
        ("Oxígeno disuelto (mg/L)", _fmt(row.get("do_mgl"), 2)),
        ("TDS (mg/L)", _fmt(row.get("tds_mgl"), 0)),
        ("Alcalinidad (mg/L CaCO₃)", _fmt(row.get("Alkalinity_mgCaCO3"), 1)),
        ("Balance de carga (%)", _fmt(row.get("CBE_pct"), 2)),
    ]
    if facies_mod.FACIES_LABEL_COL in row.index and pd.notna(
        row.get(facies_mod.FACIES_LABEL_COL)
    ):
        fisico.insert(0, ("Facies", escape(str(row[facies_mod.FACIES_LABEL_COL]))))

    fisico_html = "".join(
        f'<tr><td>{k}</td><td class="n">{v}</td></tr>'
        for k, v in fisico if v != "—"
    )

    iones_html = ""
    for ion in ALL_IONS:
        mgl, meq = f"{ion}_mgL", f"{ion}_meq"
        if mgl not in row.index or pd.isna(row.get(mgl)):
            continue
        marca = " *" if ion in imputed else ""
        iones_html += (
            f"<tr><td>{IONS[ion].label}</td>"
            f'<td class="n">{_fmt(row.get(mgl), 2)}{marca}</td>'
            f'<td class="n">{_fmt(row.get(meq), 3)}</td></tr>'
        )

    excede = ""
    if compliance is not None and not compliance.empty:
        fallos = []
        for _, lim in compliance.iterrows():
            col = f"{lim['parameter']}__exceeds"
            if col in row.index and bool(row.get(col)):
                fallos.append(
                    f"{lim['label']} {_fmt(row.get(lim['parameter']), 2)} "
                    f"{lim['unit']} (límite {lim['range_text']}, {lim['kind_label']})"
                )
        if fallos:
            excede = (
                f'<p class="warn">Supera {len(fallos)} umbral(es) de {escape(standard_name)}:</p>'
                "<ul>" + "".join(f"<li>{escape(f)}</li>" for f in fallos) + "</ul>"
            )

    pie = ""
    if imputed:
        pie = (
            '<p class="foot">* valor estimado, no medido: '
            + ", ".join(IONS[i].label for i in imputed)
            + "</p>"
        )
    pie += (
        f'<p class="foot">Lat {_fmt(row.get(LAT_COL), 5)}°  '
        f"Lon {_fmt(row.get(LON_COL), 5)}°</p>"
    )

    return (
        style
        + f"<h3>{escape(str(row.get('station_code', '?')))}</h3>"
        + f'<div class="sub">{escape(str(row.get("group", "")))}'
        + (f" · {escape(str(row.get('sampled_at')))[:10]}"
           if pd.notna(row.get("sampled_at")) else "")
        + "</div>"
        + img
        + (f'<p class="sub">{escape(scale_note)}</p>' if scale_note else "")
        + (f'<p class="sub">Criterios: {escape(standard_name)}. Comparación parcial de parámetros medidos.</p>' if standard_name else "")
        + excede
        + (f"<table><tr><th>Parámetro</th><th>Valor</th></tr>{fisico_html}</table>"
           if fisico_html else "")
        + (f"<table><tr><th>Ion</th><th>mg/L</th><th>meq/L</th></tr>{iones_html}</table>"
           if iones_html else "")
        + pie
    )


def _legend_png(labels: list[str], colors: list[str], title: str, scale_note: str = "") -> bytes:
    """Leyenda como imagen, para el ScreenOverlay."""
    wrapped = [textwrap.fill(str(label), 34) for label in labels]
    heights = [max(1, text.count("\n") + 1) for text in wrapped]
    n = max(sum(heights), 1)
    fig, ax = plt.subplots(figsize=(3.4, 0.27 * n + 1.15))
    fig.patch.set_facecolor("white")
    fig.patch.set_alpha(0.92)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(-1.3, n + 1)
    ax.text(0.03, n + 0.45, title, fontsize=9, fontweight="bold", color="#12232a",
            va="center")
    y = n - 0.2
    for label, color, height in zip(wrapped, colors, heights):
        ax.plot([0.08], [y], marker="o", ms=6, color=color)
        ax.text(0.2, y, label, fontsize=8, color="#12232a", va="center")
        y -= height
    if scale_note:
        ax.text(0.03, -0.65, textwrap.fill(scale_note, 43), fontsize=7, color="#53686f", va="center")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


@serialized
def build(
    df: pd.DataFrame,
    name: str = "HydroChem",
    group_col: str = "group",
    colour_by: str = "group",
    stiff_template: str = "standard",
    standard: str | None = None,
    filename: str = "hydrochem.kmz",
    progress=None,
    detailed_popups: bool = True,
    facies_scheme: str = facies_mod.DEFAULT_SCHEME,
) -> KmzResult:
    """Construye el KMZ completo.

    :param colour_by: ``group`` o ``facies``. Con ``facies``, el color del icono
        es el del tipo de agua, que suele ser mas informativo que el del grupo.
    :param standard: estandar normativo con el que anotar las excedencias en el
        globo. ``None`` para no comprobar nada.
    :param progress: ``callable(hechos, total, etapa)``.
    """
    if LON_COL not in df.columns or LAT_COL not in df.columns:
        raise ValueError(
            "Faltan las columnas de coordenadas WGS84. Llama antes a "
            "geo.crs.add_wgs84_columns()."
        )

    lon = pd.to_numeric(df[LON_COL], errors="coerce")
    lat = pd.to_numeric(df[LAT_COL], errors="coerce")
    ok = lon.between(-180, 180) & lat.between(-90, 90)
    n_skipped = int((~ok).sum())
    work = df.loc[ok].copy().reset_index(drop=True)
    if work.empty:
        raise ValueError("Ninguna muestra tiene coordenadas: no hay nada que exportar.")

    # --- color por grupo o por facies ---------------------------------------
    if colour_by == "facies" and facies_mod.FACIES_COL in work.columns:
        keys = work[facies_mod.FACIES_COL].astype(str)
        unique = list(dict.fromkeys(keys))
        colours = {k: facies_mod.color_of(k, facies_scheme) for k in unique}
        legend_title = "Facies hidroquímica"
        legend_labels = [facies_mod.label_of(k, facies_scheme) for k in unique]
    else:
        keys = (work[group_col].astype(str) if group_col in work.columns
                else pd.Series("Sin grupo", index=work.index))
        unique = list(dict.fromkeys(keys))
        colours = {k: PALETTE[i] if i < len(PALETTE) else "#566e60" for i, k in enumerate(unique)}
        legend_title = "Grupo"
        legend_labels = list(unique)

    # --- comprobacion normativa --------------------------------------------
    compliance = None
    standard_name = ""
    if standard:
        std = std_mod.get_standard(standard)
        standard_name = std.name_es
        compliance = std_mod.check(work, std)
        work = std_mod.add_compliance(work, std)

    # --- iconos -------------------------------------------------------------
    def stage(label):
        def inner(done, total):
            if progress:
                progress(done, total, label)
        return inner

    colour_series = keys.map(colours).fillna(PALETTE[0])
    work["__colour_key"] = keys.to_numpy()
    icon_colours = {k: colours[k] for k in unique}

    limit = stiff_mod.axis_limit(work, stiff_template)
    scale_note = f"Stiff · escala común: 0–{limit:.2f} meq/L por lado. Cationes a la izquierda; aniones a la derecha."
    icons = render_map_icons(
        work, icon_colours, group_col="__colour_key",
        template=stiff_template, progress=stage("iconos"),
    )
    popups = render_popup_images(
        work, icon_colours, group_col="__colour_key",
        template=stiff_template,
        titles=work.get("station_code", pd.Series(dtype=object)).astype(str).tolist(),
        progress=stage("imagenes del globo"),
    ) if detailed_popups else []

    # --- documento KML ------------------------------------------------------
    doc = kml_mod.Document(
        name=name,
        description=(
            f"<b>{escape(name)}</b><br>{len(work)} muestras"
            + (f", {len(unique)} {legend_title.lower()}(s)" if unique else "")
            + (f"<br>Umbrales: {escape(standard_name)}" if standard_name else "")
            + "<br>El icono de cada punto es su diagrama de Stiff."
            + f"<br>{escape(scale_note)}"
            + f"<br>{n_skipped} muestras omitidas por coordenadas ausentes o inválidas."
        ),
    )
    centre_lon = float(work[LON_COL].min() + work[LON_COL].max()) / 2
    centre_lat = float(work[LAT_COL].min() + work[LAT_COL].max()) / 2
    extent = max(float(work[LAT_COL].max() - work[LAT_COL].min()),
                 float(work[LON_COL].max() - work[LON_COL].min()) * math.cos(math.radians(centre_lat)))
    doc.look_at = (centre_lon, centre_lat, max(1500, extent * 111320 * 2.2))

    styles: dict[int, str] = {}
    files: dict[str, bytes] = {}

    for pos in range(len(work)):
        icon_name = f"stiff_{pos:04d}.png"
        popup_name = f"popup_{pos:04d}.png"
        files[icon_name] = icons[pos]
        if detailed_popups:
            files[popup_name] = popups[pos]
        style_id = f"s{pos:04d}"
        styles[pos] = style_id
        doc.styles.append(
            kml_mod.IconStyle(
                style_id=style_id,
                icon_href=f"{kml_mod.FILES_DIR}/{icon_name}",
                scale=0.75,
                highlight_scale=1.25,
                label_scale=0,
            )
        )

    grouping = (work[group_col].astype(str) if group_col in work.columns
                else pd.Series("Sin grupo", index=work.index))
    for group in dict.fromkeys(grouping):
        idx = [i for i in range(len(work)) if grouping.iloc[i] == group]
        folder = kml_mod.Folder(name=f"{group} ({len(idx)})", open=False)
        for pos in idx:
            row = work.iloc[pos]
            folder.placemarks.append(
                kml_mod.Placemark(
                    name=str(row.get("station_code", f"Muestra {pos + 1}")),
                    lon=float(row[LON_COL]),
                    lat=float(row[LAT_COL]),
                    description_html=_popup_html(
                        row, f"popup_{pos:04d}.png" if detailed_popups else f"stiff_{pos:04d}.png",
                        compliance, standard_name, scale_note
                    ),
                    style_id=styles[pos],
                    data={
                        "Grupo": row.get(group_col),
                        "Fecha": str(row["sampled_at"])[:10] if pd.notna(row.get("sampled_at")) else None,
                        "Facies": row.get(facies_mod.FACIES_LABEL_COL),
                        "TDS_mgL": row.get("tds_mgl"),
                        "CBE_pct": None if pd.isna(row.get("CBE_pct"))
                        else round(float(row["CBE_pct"]), 2),
                    },
                )
            )
        doc.folders.append(folder)

    legend_name = "leyenda.png"
    files[legend_name] = _legend_png(
        legend_labels, [colours[k] for k in unique], legend_title, scale_note
    )
    doc.overlays.append(
        kml_mod.ScreenOverlay("Leyenda", f"{kml_mod.FILES_DIR}/{legend_name}")
    )

    # --- empaquetado --------------------------------------------------------
    if progress:
        progress(0, 1, "empaquetado")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # doc.kml primero: algunos lectores esperan encontrarlo al principio.
        zf.writestr("doc.kml", doc.to_xml())
        zf.writestr("metadatos.json", json.dumps({
            "samples": len(work), "skipped_coordinates": n_skipped,
            "stiff_template": stiff_template, "scale_meq_per_side": limit,
            "colour_by": colour_by, "facies_scheme": facies_scheme,
            "standard": std_mod.get_standard(standard).to_dict() if standard else None,
            "detailed_popups": detailed_popups,
        }, ensure_ascii=False, indent=2))
        for fname, content in files.items():
            zf.writestr(f"{kml_mod.FILES_DIR}/{fname}", content)
    if progress:
        progress(1, 1, "empaquetado")

    return KmzResult(
        content=buf.getvalue(),
        n_placemarks=doc.n_placemarks,
        n_groups=len(doc.folders),
        n_skipped=n_skipped,
        filename=filename,
    )
