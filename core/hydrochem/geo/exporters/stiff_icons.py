"""Iconos de Stiff en PNG para usarlos como marcador en Google Earth.

Por que PNG y no SVG: Google Earth **no admite SVG** como icono de un
``Placemark``. El SVG seria mas ligero y nitido a cualquier escala, pero no se
veria. Para la propia aplicacion web si se usa SVG dibujado en el navegador;
esto es solo para el KMZ.

El rendimiento importa: el notebook creaba una figura de matplotlib por muestra
con ``plt.subplots()``, lo que tarda decenas de segundos con 90 puntos. Aqui se
reutiliza una unica figura para todas las muestras y solo se redibuja su
contenido, que es entre cinco y diez veces mas rapido.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ...geometry import stiff as stiff_mod

#: Tamano del icono en pulgadas y resolucion. Un icono de mapa no necesita mas:
#: a 90 ppp sale de unos 200x150 px, que pesa poco y se ve bien.
ICON_SIZE = (2.2, 1.7)
ICON_DPI = 90

#: Tamano de la version grande que va dentro del globo de informacion.
POPUP_SIZE = (3.4, 2.6)
POPUP_DPI = 110


def _draw(ax, poly, color: str, limit: float, n_rows: int,
          labels: list[tuple[str, str]] | None, title: str | None) -> None:
    ax.clear()
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    ax.fill(xs, ys, color=color, alpha=0.55, zorder=3)
    ax.plot(xs, ys, color=color, lw=1.6, zorder=4)
    for y in range(n_rows):
        ax.axhline(y, color="#d5dfe2", lw=0.6, zorder=1)
    ax.axvline(0, color="#7f9299", lw=0.9, ls="--", alpha=0.7, zorder=2)

    ax.set_xlim(-limit, limit)
    ax.set_ylim(-0.55, n_rows - 0.45)
    ax.set_yticks([])
    ax.set_xticks([-limit, 0, limit])
    ax.set_xticklabels([f"{limit:.0f}", "0", f"{limit:.0f}"], fontsize=6, color="#53686f")
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#d5dfe2")

    if labels:
        for i, (left, right) in enumerate(labels):
            y = n_rows - 1 - i
            if left:
                ax.text(-limit * 0.97, y, left, ha="left", va="bottom",
                        fontsize=5.5, color="#53686f")
            if right:
                ax.text(limit * 0.97, y, right, ha="right", va="bottom",
                        fontsize=5.5, color="#53686f")
    if title:
        ax.set_title(title, fontsize=7, color="#12232a", pad=3)


def render_icons(
    df: pd.DataFrame,
    colors: dict[str, str] | None = None,
    group_col: str = "group",
    template: str = "standard",
    with_labels: bool = False,
    size: tuple[float, float] = ICON_SIZE,
    dpi: int = ICON_DPI,
    titles: list[str] | None = None,
    progress=None,
) -> list[bytes]:
    """Un PNG por muestra, en el mismo orden que el DataFrame.

    :param colors: color por grupo. Sin el, todos salen en el color de acento.
    :param titles: titulo opcional por muestra (para la version del globo).
    :param progress: ``callable(hechos, total)`` para poder informar del avance;
        con miles de muestras esto tarda y la interfaz debe poder decirlo.
    """
    tpl = stiff_mod.get_template(template)
    rows = stiff_mod.row_values(df, tpl)
    limit = stiff_mod.axis_limit(df, tpl)
    labels = stiff_mod.row_labels(tpl) if with_labels else None
    n_rows = tpl.n_rows
    groups = df[group_col].astype(str) if group_col in df.columns else None

    fig, ax = plt.subplots(figsize=size)
    fig.patch.set_alpha(0.0)  # fondo transparente: se integra con el mapa
    out: list[bytes] = []
    total = len(rows)
    try:
        for pos, (_, r) in enumerate(rows.iterrows()):
            group = groups.iloc[pos] if groups is not None else ""
            color = (colors or {}).get(group, "#0e6b75")
            title = titles[pos] if titles else None
            _draw(ax, stiff_mod.polygon(r, tpl), color, limit, n_rows, labels, title)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                        transparent=True, pad_inches=0.04)
            out.append(buf.getvalue())
            if progress and (pos + 1) % 10 == 0:
                progress(pos + 1, total)
    finally:
        plt.close(fig)

    if progress:
        progress(total, total)
    return out


def render_popup_images(
    df: pd.DataFrame,
    colors: dict[str, str] | None = None,
    group_col: str = "group",
    template: str = "standard",
    titles: list[str] | None = None,
    progress=None,
) -> list[bytes]:
    """Version grande y rotulada, para el globo de informacion."""
    return render_icons(
        df, colors, group_col, template, with_labels=True,
        size=POPUP_SIZE, dpi=POPUP_DPI, titles=titles, progress=progress,
    )
