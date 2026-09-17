"""Iconos de Stiff en PNG para usarlos como marcador en Google Earth.

Por que PNG y no SVG: Google Earth **no admite SVG** como icono de un
``Placemark``. El SVG seria mas ligero y nitido a cualquier escala, pero no se
veria. Para la propia aplicacion web si se usa SVG dibujado en el navegador;
esto es solo para el KMZ.

El rendimiento importa: el notebook creaba una figura de matplotlib por muestra
con ``plt.subplots()``, lo que tarda decenas de segundos con 90 puntos. Aqui se
reutiliza una unica figura para todas las muestras y solo se redibuja su
contenido, que es entre cinco y diez veces mas rapido.

Estilo: se sigue el del diagrama de Stiff impreso —rejilla de filas, eje
simetrico con marcas a intervalos redondos, y el valor de cada vertice escrito
al lado en la version grande—, para que lo que se ve en Google Earth sea
reconocible como el mismo grafico que produce la aplicacion.
"""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ...geometry import stiff as stiff_mod

#: Tamano del icono en pulgadas y resolucion. Un icono de mapa no necesita mas:
#: a 100 ppp sale de unos 250x190 px, que pesa poco y se ve bien.
ICON_SIZE = (2.5, 1.9)
ICON_DPI = 100

#: Tamano de la version grande que va dentro del globo de informacion.
POPUP_SIZE = (4.0, 3.0)
POPUP_DPI = 120

# Paleta de la aplicacion, para que el KMZ no desentone de la pantalla.
INK = "#16241d"
INK_2 = "#3d5548"
INK_3 = "#566e60"
GRID = "#dbe9e1"
GRID_STRONG = "#c3d9cc"


def _nice_ticks(limit: float, objetivo: int = 3) -> list[float]:
    """Marcas a intervalos redondos entre 0 y ``limit``.

    Un eje rotulado solo con 0 y el maximo no deja estimar valores intermedios;
    con marcas en 5, 10 y 15 se lee de un vistazo cuanto vale cada vertice.

    Se elige, entre los intervalos "redondos" habituales, el que deja un numero
    de marcas mas cercano al objetivo. Quedarse con el primero que supera el
    ancho ideal dejaba ejes con una sola marca.
    """
    if limit <= 0:
        return [0.0]
    ideal = limit / max(objetivo, 1)
    magnitud = 10.0 ** math.floor(math.log10(ideal))
    candidatos = [p * magnitud for p in (1, 2, 2.5, 5, 10)]
    candidatos += [p * magnitud / 10 for p in (1, 2, 5)]

    def marcas_de(intervalo: float) -> list[float]:
        salida, v = [], intervalo
        while v < limit * 0.98:
            salida.append(round(v, 6))
            v += intervalo
        return salida

    mejor, mejor_coste = [], None
    for intervalo in sorted(set(candidatos)):
        if intervalo <= 0:
            continue
        m = marcas_de(intervalo)
        if not m or len(m) > 8:
            continue
        coste = abs(len(m) - objetivo)
        if mejor_coste is None or coste < mejor_coste:
            mejor, mejor_coste = m, coste
    return mejor


def _draw(ax, poly, values, color: str, limit: float, n_rows: int,
          labels: list[tuple[str, str]] | None, title: str | None,
          annotate: bool) -> None:
    ax.clear()
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]

    marcas = _nice_ticks(limit)
    for m in marcas:
        for signo in (-1, 1):
            ax.axvline(signo * m, color=GRID, lw=0.6, zorder=1)
    for y in range(n_rows):
        ax.axhline(y, color=GRID_STRONG, lw=0.7, zorder=1)
    ax.axvline(0, color=INK_3, lw=1.0, zorder=2)

    ax.fill(xs, ys, color=color, alpha=0.45, zorder=3)
    ax.plot(xs, ys, color=color, lw=1.8, zorder=4,
            solid_joinstyle="round", solid_capstyle="round")
    # Vertices marcados: dejan ver donde esta el dato y no solo la silueta.
    ax.plot(xs, ys, "o", color=color, ms=2.6, zorder=5,
            markeredgecolor="white", markeredgewidth=0.5)

    ax.set_xlim(-limit, limit)
    ax.set_ylim(-0.55, n_rows - 0.45)
    ax.set_yticks([])
    posiciones = sorted({-m for m in marcas} | {0.0} | set(marcas))
    ax.set_xticks(posiciones)
    ax.set_xticklabels([f"{abs(v):g}" for v in posiciones], fontsize=6.5, color=INK_3)
    ax.tick_params(axis="x", length=2.5, pad=1.5, colors=INK_3)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID_STRONG)

    if labels:
        for i, (left, right) in enumerate(labels):
            y = n_rows - 1 - i
            if left:
                ax.text(-limit * 0.98, y + 0.12, left, ha="left", va="bottom",
                        fontsize=6, color=INK_2)
            if right:
                ax.text(limit * 0.98, y + 0.12, right, ha="right", va="bottom",
                        fontsize=6, color=INK_2)

    if annotate and values is not None:
        # El valor de cada vertice, al lado del punto. Es lo que convierte el
        # dibujo en algo que se puede leer sin abrir la tabla.
        for i in range(n_rows):
            y = n_rows - 1 - i
            izq = values.get(f"row{i}_left")
            der = values.get(f"row{i}_right")
            if izq is not None and pd.notna(izq) and izq > 0:
                ax.text(-float(izq) - limit * 0.02, y, f"{float(izq):.2f}",
                        ha="right", va="center", fontsize=5.8, color=INK)
            if der is not None and pd.notna(der) and der > 0:
                ax.text(float(der) + limit * 0.02, y, f"{float(der):.2f}",
                        ha="left", va="center", fontsize=5.8, color=INK)

    ax.set_xlabel("meq/L", fontsize=6.5, color=INK_3, labelpad=1)
    if title:
        ax.set_title(title, fontsize=8, color=INK, pad=4, fontweight="bold")


def render_icons(
    df: pd.DataFrame,
    colors: dict[str, str] | None = None,
    group_col: str = "group",
    template: str = "standard",
    with_labels: bool = False,
    size: tuple[float, float] = ICON_SIZE,
    dpi: int = ICON_DPI,
    titles: list[str] | None = None,
    annotate: bool = False,
    progress=None,
) -> list[bytes]:
    """Un PNG por muestra, en el mismo orden que el DataFrame.

    :param colors: color por grupo. Sin el, todos salen en el color de acento.
    :param titles: titulo opcional por muestra (para la version del globo).
    :param annotate: escribe el valor de cada vertice junto al punto.
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
            color = (colors or {}).get(group, "#0f7d52")
            title = titles[pos] if titles else None
            _draw(ax, stiff_mod.polygon(r, tpl), r, color, limit, n_rows,
                  labels, title, annotate)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                        transparent=True, pad_inches=0.05)
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
    """Version grande, rotulada y con los valores escritos, para el globo."""
    return render_icons(
        df, colors, group_col, template, with_labels=True,
        size=POPUP_SIZE, dpi=POPUP_DPI, titles=titles,
        annotate=True, progress=progress,
    )
