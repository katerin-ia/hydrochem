"""Las figuras del analisis, en PNG de calidad de impresion.

Por que existe, si la aplicacion ya dibuja todo en el navegador: lo de pantalla
es interactivo y esta pensado para explorar; lo que se pega en un informe tiene
que ser un archivo, a 200 ppp, con fondo blanco, leyenda y titulo. Son dos
trabajos distintos y por eso hay dos dibujantes.

La geometria NO se duplica. Estas figuras consumen exactamente las mismas
coordenadas que consume el navegador (``hydrochem.geometry`` y
``hydrochem.temporal``), asi que un punto que aqui cae en un sitio cae en el
mismo sitio en pantalla. Lo unico propio de este modulo es el estilo.

Cada figura declara si puede dibujarse con los datos que hay
(``FigureSpec.requires``); las que no, se omiten del ZIP y se explican en el
LEEME que va dentro, en vez de salir en blanco.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from .. import temporal as temporal_mod
from ..chemistry import facies as facies_mod
from ..geometry import durov as durov_mod
from ..geometry import piper as piper_mod
from ..geometry import stiff as stiff_mod
from ..quality import standards as std_mod

# --------------------------------------------------------------------- estilo

#: Paleta categorica de la aplicacion, validada con scripts/validate_palette.js.
#: Se asigna en orden fijo y no se recicla: a partir del noveno grupo se pliega
#: en un neutro etiquetado "Otros", igual que en pantalla, para que dos grupos
#: distintos nunca compartan color.
PALETTE = ["#0f7d52", "#c24a1f", "#3b56c4", "#a8267a",
           "#8a6a00", "#0e7f9e", "#9b2226", "#6b3fa0"]
NEUTRO = "#566e60"
OTROS = "Otros"

PAPEL = "#ffffff"
INK = "#16241d"
INK_2 = "#3d5548"
INK_3 = "#566e60"
GRID = "#dbe9e1"
GRID_STRONG = "#c3d9cc"
ERR = "#a32020"

DPI = 200


def group_colors(groups: list[str]) -> dict[str, str]:
    """Color por grupo, en orden fijo y sin ciclar."""
    return {
        g: (PALETTE[i] if i < len(PALETTE) else NEUTRO)
        for i, g in enumerate(groups)
    }


def _frame(ax) -> None:
    """Rejilla y ejes en segundo plano: el dato manda, el marco acompana."""
    ax.set_facecolor(PAPEL)
    ax.grid(True, color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRID_STRONG)
    ax.tick_params(colors=INK_3, labelsize=8)


def _title(fig, texto: str, subtexto: str = "") -> None:
    fig.suptitle(texto, fontsize=13, fontweight="bold", color=INK, y=0.99)
    if subtexto:
        fig.text(0.5, 0.945, subtexto, ha="center", fontsize=9, color=INK_3)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight",
                facecolor=PAPEL, pad_inches=0.25)
    plt.close(fig)
    return buf.getvalue()


def _sin_datos(mensaje: str) -> bytes:
    """Una figura que dice por que esta vacia. Mejor que un PNG en blanco."""
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.axis("off")
    ax.text(0.5, 0.5, mensaje, ha="center", va="center", fontsize=11,
            color=INK_2, wrap=True)
    return _png(fig)


# -------------------------------------------------------------------- figuras


def _fig_piper(ds, convention: str | None = None) -> bytes:
    conv = piper_mod.get_convention(convention or ds.options.piper_convention)
    layout = piper_mod.PiperLayout(gap=0.6)
    bg = piper_mod.background(conv, layout)
    p = piper_mod.project(ds.data, conv, layout)

    grupos = ds.groups or ["Todas"]
    colores = group_colors(grupos)
    serie = (ds.data["group"].astype(str) if "group" in ds.data.columns
             else pd.Series(["Todas"] * len(ds.data), index=ds.data.index))

    fig, ax = plt.subplots(figsize=(9.5, 8.6))
    for seg in bg.gridlines:
        ax.plot([seg.x0, seg.x1], [seg.y0, seg.y1], color=GRID, lw=0.55, zorder=1)
    for poly in bg.outlines:
        ax.plot(*zip(*poly), color=INK_2, lw=1.3, zorder=3)
    for lb in bg.tick_labels:
        ax.text(lb.x, lb.y, lb.text, ha=lb.ha,
                va="center" if lb.va == "middle" else lb.va,
                fontsize=6, color=INK_3, zorder=4)
    for lb in bg.axis_labels:
        ax.text(lb.x, lb.y, lb.text, ha=lb.ha,
                va="center" if lb.va == "middle" else lb.va,
                fontsize=9.5, fontweight="bold", color=INK, zorder=4)

    for grupo in grupos:
        m = (serie == grupo).to_numpy()
        if not m.any():
            continue
        # Anillo blanco alrededor de cada marca: con 90 puntos hay solapes, y
        # sin el borde dos muestras vecinas se leen como una sola mancha.
        kw = dict(s=30, color=colores[grupo], edgecolors=PAPEL,
                  linewidths=0.9, zorder=6, alpha=0.92)
        ax.scatter(p["x_cat"][m], p["y_cat"][m], label=grupo, **kw)
        ax.scatter(p["x_an"][m], p["y_an"][m], **kw)
        ax.scatter(p["x_diamond"][m], p["y_diamond"][m], marker="D", **kw)

    xmin, ymin, xmax, ymax = bg.bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")
    if len(grupos) > 1:
        ax.legend(title="Grupo", loc="upper left", fontsize=8, title_fontsize=8.5,
                  framealpha=0.95, edgecolor=GRID_STRONG)
    _title(fig, "Diagrama de Piper",
           f"{ds.n_samples} muestras · convencion {conv.name_es}")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _png(fig)


def _fig_piper_alterno(ds) -> bytes:
    """El mismo Piper en la otra convencion.

    Va aparte a proposito: las dos convenciones intercambian que ion ocupa cada
    vertice, y quien lea el informe tiene que poder comprobar que la lectura no
    depende de esa eleccion.
    """
    actual = ds.options.piper_convention
    otra = next((k for k in piper_mod.CONVENTIONS if k != actual), actual)
    return _fig_piper(ds, otra)


def _fig_stiff_grupos(ds) -> bytes:
    tpl = stiff_mod.get_template(ds.options.stiff_template)
    etiquetas = stiff_mod.row_labels(tpl)
    n_rows = tpl.n_rows
    filas = stiff_mod.row_values(ds.data, tpl)
    limite = stiff_mod.axis_limit(ds.data, tpl)

    grupos = ds.groups or ["Todas"]
    colores = group_colors(grupos)
    serie = (ds.data["group"].astype(str) if "group" in ds.data.columns
             else pd.Series(["Todas"] * len(ds.data), index=ds.data.index))

    ancho = max(3.0 * len(grupos), 5.0)
    fig, axes = plt.subplots(1, len(grupos), figsize=(ancho, 4.8), sharey=True)
    axes = [axes] if len(grupos) == 1 else list(axes)

    for ax, grupo in zip(axes, grupos):
        m = (serie == grupo).to_numpy()
        color = colores[grupo]
        for _, r in filas[m].iterrows():
            poly = stiff_mod.polygon(r, tpl)
            xs = [q[0] for q in poly]
            ys = [q[1] for q in poly]
            # Relleno muy transparente y linea opaca: al superponer decenas de
            # muestras el relleno solo ensucia, la silueta es lo que informa.
            ax.fill(xs, ys, color=color, alpha=0.13, zorder=2)
            ax.plot(xs, ys, color=color, lw=1.1, alpha=0.85, zorder=3)

        for y in range(n_rows):
            ax.axhline(y, color=GRID, lw=0.6, zorder=1)
        ax.axvline(0, color=INK_3, lw=0.9, ls="--", alpha=0.6, zorder=1)
        ax.set_xlim(-limite, limite)
        ax.set_ylim(-0.55, n_rows - 0.45)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(
            [etiquetas[n_rows - 1 - i][0] or "" for i in range(n_rows)], fontsize=8)
        ax.tick_params(axis="x", labelsize=7.5, colors=INK_3)
        ax.set_xlabel("meq/L", fontsize=8, color=INK_3)
        ax.set_title(f"{grupo}\n({int(m.sum())} muestras)", fontsize=9,
                     color=INK, pad=6)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color(GRID_STRONG)
        for i in range(n_rows):
            derecha = etiquetas[n_rows - 1 - i][1]
            if derecha:
                ax.text(limite * 0.97, i, derecha, ha="right", va="bottom",
                        fontsize=7, color=INK_3)

    _title(fig, "Diagramas de Stiff superpuestos por grupo",
           f"plantilla {tpl.name_es} · escala comun 0 a {limite:.1f} meq/L")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return _png(fig)


def _fig_durov(ds) -> bytes:
    layout = durov_mod.DurovLayout()
    proj = durov_mod.project(ds.data, layout)
    paneles = durov_mod.panel_positions(ds.data, proj, layout)
    bg = durov_mod.background(layout, paneles)

    grupos = ds.groups or ["Todas"]
    colores = group_colors(grupos)
    serie = (ds.data["group"].astype(str) if "group" in ds.data.columns
             else pd.Series(["Todas"] * len(ds.data), index=ds.data.index))

    fig, ax = plt.subplots(figsize=(8.6, 8.6))
    for seg in bg.gridlines:
        ax.plot([seg.x0, seg.x1], [seg.y0, seg.y1], color=GRID, lw=0.5, zorder=1)
    for poly in bg.outlines:
        ax.plot(*zip(*poly), color=INK_2, lw=1.2, zorder=3)
    for lb in bg.tick_labels:
        ax.text(lb.x, lb.y, lb.text, ha=lb.ha,
                va="center" if lb.va == "middle" else lb.va,
                fontsize=6, color=INK_3, zorder=4)
    for lb in bg.axis_labels:
        ax.text(lb.x, lb.y, lb.text, ha=lb.ha,
                va="center" if lb.va == "middle" else lb.va,
                fontsize=9, fontweight="bold", color=INK, zorder=4)

    for grupo in grupos:
        m = (serie == grupo).to_numpy()
        if not m.any():
            continue
        kw = dict(s=28, color=colores[grupo], edgecolors=PAPEL,
                  linewidths=0.9, zorder=6, alpha=0.92)
        ax.scatter(proj[durov_mod.X_COL][m], proj[durov_mod.Y_COL][m],
                   label=grupo, **kw)
        ax.scatter(proj["cat_x"][m], proj["cat_y"][m], **kw)
        ax.scatter(proj["an_x"][m], proj["an_y"][m], **kw)
        for clave in ("ph", "tds"):
            panel = paneles.get(clave) or {}
            if panel.get("available"):
                ax.scatter(np.asarray(panel["x"])[m], np.asarray(panel["y"])[m],
                           **{**kw, "s": 20})

    xmin, ymin, xmax, ymax = bg.bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")
    if len(grupos) > 1:
        ax.legend(title="Grupo", loc="lower right", fontsize=8, title_fontsize=8.5,
                  framealpha=0.95, edgecolor=GRID_STRONG)
    faltan = [n for n, c in (("pH", "ph"), ("TDS", "tds"))
              if not (paneles.get(c) or {}).get("available")]
    nota = "sin panel de " + " ni ".join(faltan) if faltan else "con paneles de pH y TDS"
    _title(fig, "Diagrama de Durov ampliado", f"{ds.n_samples} muestras · {nota}")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _png(fig)


def _fig_facies(ds) -> bytes:
    resumen = facies_mod.summary(ds.data["facies"].dropna())
    etiquetas = [facies_mod.label_of(c, ds.options.facies_scheme)
                 for c in resumen["facies"]]
    # Se dibujan de menos a mas para que la barra larga quede arriba al leer.
    orden = resumen.iloc[::-1]
    etiquetas = etiquetas[::-1]
    colores = [PALETTE[i % len(PALETTE)] for i in range(len(orden))][::-1]

    alto = max(3.0, 0.42 * len(orden) + 1.6)
    fig, ax = plt.subplots(figsize=(9.5, alto))
    y = np.arange(len(orden))
    ax.barh(y, orden["n"], color=colores, height=0.62, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(etiquetas, fontsize=9, color=INK_2)
    ax.set_xlabel("Muestras", fontsize=9, color=INK_3)
    _frame(ax)
    ax.grid(axis="y", visible=False)
    for yi, (n, pct) in enumerate(zip(orden["n"], orden["pct"])):
        ax.text(n + max(orden["n"]) * 0.012, yi, f"{int(n)}  ({pct:.1f} %)",
                va="center", fontsize=8.5, color=INK_2)
    ax.set_xlim(0, max(orden["n"]) * 1.18)
    _title(fig, "Facies hidroquimicas",
           f"{int(orden['n'].sum())} muestras clasificadas · esquema "
           f"{ds.options.facies_scheme}")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _png(fig)


def _fig_normas(ds) -> bytes:
    tabla = std_mod.check(ds.data, ds.options.standard)
    tabla = tabla[tabla["n_measured"] > 0]
    if tabla.empty:
        return _sin_datos("Ninguno de los parametros con limite normativo esta "
                          "medido en estos datos.")
    tabla = tabla.sort_values("pct")

    fig, ax = plt.subplots(figsize=(9.5, max(3.0, 0.46 * len(tabla) + 1.8)))
    y = np.arange(len(tabla))
    # Semaforo, no paleta categorica: aqui el color codifica estado, no
    # identidad, y por eso usa los colores reservados de estado.
    colores = ["#a32020" if p >= 25 else "#8a5300" if p > 0 else "#1c6b47"
               for p in tabla["pct"]]
    ax.barh(y, tabla["pct"], color=colores, height=0.6, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{r.label} ({r.range_text})" for r in tabla.itertuples()],
        fontsize=8.5, color=INK_2)
    ax.set_xlabel("% de las muestras medidas que superan el limite",
                  fontsize=9, color=INK_3)
    _frame(ax)
    ax.grid(axis="y", visible=False)
    for yi, r in enumerate(tabla.itertuples()):
        ax.text(r.pct + 1.4, yi, f"{r.n_exceeding} de {r.n_measured}",
                va="center", fontsize=8.5, color=INK_2)
    ax.set_xlim(0, max(float(tabla["pct"].max()) * 1.25, 12))

    std = std_mod.get_standard(ds.options.standard)
    _title(fig, f"Incumplimientos segun {std.name_es}",
           "el denominador son las muestras MEDIDAS de cada parametro, "
           "no el total")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _png(fig)


def _fig_fluoruro(ds) -> bytes:
    df = ds.data
    f = pd.to_numeric(df.get("F_mgL"), errors="coerce")
    medidas = f.notna()
    if not medidas.any():
        return _sin_datos("Estos datos no traen fluoruro medido.")

    std = std_mod.get_standard(ds.options.standard)
    lim = std.limit_for("F_mgL")
    limite = lim.maximum if lim and lim.maximum is not None else 1.5

    grupos = [g for g in (ds.groups or ["Todas"])]
    colores = group_colors(grupos)
    serie = (df["group"].astype(str) if "group" in df.columns
             else pd.Series(["Todas"] * len(df), index=df.index))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.2))

    # -- panel 1: caja por grupo, con los puntos encima ----------------------
    # La caja sola miente cuando un grupo tiene tres muestras; los puntos
    # dejan ver cuantas hay detras de cada resumen.
    datos, presentes = [], []
    for g in grupos:
        v = f[(serie == g) & medidas].dropna()
        if len(v):
            datos.append(v.to_numpy())
            presentes.append(g)
    cajas = ax1.boxplot(datos, patch_artist=True, widths=0.55,
                        medianprops=dict(color=INK, lw=1.4),
                        whiskerprops=dict(color=INK_3, lw=1),
                        capprops=dict(color=INK_3, lw=1),
                        flierprops=dict(marker="", markersize=0))
    for caja, g in zip(cajas["boxes"], presentes):
        caja.set_facecolor(colores[g])
        caja.set_alpha(0.18)
        caja.set_edgecolor(colores[g])
        caja.set_linewidth(1.4)
    rng = np.random.default_rng(0)  # semilla fija: la figura no cambia al repetir
    for i, (v, g) in enumerate(zip(datos, presentes), start=1):
        x = i + rng.uniform(-0.16, 0.16, size=len(v))
        ax1.scatter(x, v, s=22, color=colores[g], alpha=0.85, zorder=4,
                    edgecolors=PAPEL, linewidths=0.8)
    ax1.set_xticks(range(1, len(presentes) + 1))
    ax1.set_xticklabels(presentes, rotation=20, ha="right", fontsize=8.5)
    ax1.set_ylabel("F⁻ (mg/L)", fontsize=9.5, color=INK_2)
    ax1.axhline(limite, color=ERR, lw=1.5, ls="--", zorder=5)
    ax1.text(len(presentes) + 0.45, limite, f"limite {limite:g}", ha="right",
             va="bottom", fontsize=8, color=ERR)
    ax1.set_title("Distribucion por grupo", fontsize=10, color=INK, pad=8)
    _frame(ax1)

    # -- panel 2: fluoruro frente a calcio -----------------------------------
    # Indicador de saturacion en fluorita: al subir el calcio, el fluoruro
    # tiende a bajar porque precipita como CaF2.
    ca = pd.to_numeric(df.get("Ca_mgL"), errors="coerce")
    con_ca = medidas & ca.notna()
    if con_ca.any():
        for g in grupos:
            m = ((serie == g) & con_ca).to_numpy()
            if not m.any():
                continue
            ax2.scatter(ca[m], f[m], s=30, color=colores[g], label=g,
                        alpha=0.9, edgecolors=PAPEL, linewidths=0.9, zorder=4)
        ax2.set_xlabel("Ca²⁺ (mg/L)", fontsize=9.5, color=INK_2)
        ax2.set_ylabel("F⁻ (mg/L)", fontsize=9.5, color=INK_2)
        ax2.axhline(limite, color=ERR, lw=1.5, ls="--", zorder=5)
        if len(grupos) > 1:
            ax2.legend(fontsize=8, framealpha=0.95, edgecolor=GRID_STRONG)
        ax2.set_title("Fluoruro frente a calcio", fontsize=10, color=INK, pad=8)
        _frame(ax2)
    else:
        ax2.axis("off")
        ax2.text(0.5, 0.5, "Sin calcio medido para cruzarlo con el fluoruro.",
                 ha="center", va="center", fontsize=10, color=INK_2)

    n_med = int(medidas.sum())
    n_exc = int((f > limite).sum())
    sin_medir = len(df) - n_med
    sub = (f"{n_exc} de {n_med} muestras medidas ({n_exc / n_med * 100:.1f} %) "
           f"superan {limite:g} mg/L")
    if sin_medir:
        sub += f" · {sin_medir} sin medir, excluidas del porcentaje"
    _title(fig, "Fluoruro", sub)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return _png(fig)


def _estilo_series(ds, estaciones: list[str]):
    """Como colorear una linea por estacion cuando hay mas estaciones que colores.

    Con doce estaciones y ocho tonos, repartir "el que toque" deja cuatro lineas
    del mismo gris: el lector no puede saber cual es cual, y la leyenda mentiria
    si dijera lo contrario. Asi que la figura baja de ambicion en vez de fingir:

    1. Hasta ocho estaciones -> un color por estacion y leyenda de estaciones.
    2. Mas estaciones, pero pocos grupos -> se colorea por GRUPO. La identidad
       de cada estacion se pierde, pero la leyenda solo promete lo que cumple, y
       el grupo es justo la agregacion que usa el resto de la aplicacion.
    3. Ni siquiera eso -> todas las lineas en un neutro fino y, encima, la
       mediana entre estaciones en trazo grueso, que es lo unico legible.

    :returns: ``(color_de, manijas, nota, con_mediana)``.
    """
    if len(estaciones) <= len(PALETTE):
        colores = group_colors(estaciones)
        manijas = [Line2D([], [], color=colores[e], lw=2.2, marker="o", ms=5,
                          label=e) for e in estaciones]
        return (lambda est: colores[est]), manijas, "", False

    por_estacion: dict[str, str] = {}
    if "group" in ds.data.columns and "station_code" in ds.data.columns:
        for est, grp in zip(ds.data["station_code"].astype(str),
                            ds.data["group"].astype(str)):
            por_estacion.setdefault(est, grp)
    grupos = list(dict.fromkeys(por_estacion.values()))

    if grupos and len(grupos) <= len(PALETTE):
        colores = group_colors(grupos)
        manijas = [Line2D([], [], color=colores[g], lw=2.2, marker="o", ms=5,
                          label=g) for g in grupos]
        nota = (f"{len(estaciones)} estaciones coloreadas por grupo: hay mas "
                "estaciones que colores distinguibles")
        return ((lambda est: colores.get(por_estacion.get(est, ""), NEUTRO)),
                manijas, nota, False)

    manijas = [
        Line2D([], [], color=NEUTRO, lw=1, alpha=0.5, label="cada estacion"),
        Line2D([], [], color=PALETTE[0], lw=2.6, label="mediana de todas"),
    ]
    nota = (f"{len(estaciones)} estaciones: demasiadas para distinguirlas por "
            "color, se dibujan en gris con la mediana encima")
    return (lambda est: NEUTRO), manijas, nota, True


def _mediana_por_fecha(sub: pd.DataFrame, valor: str) -> pd.DataFrame:
    """Mediana entre estaciones en cada campana. Resistente a un valor raro."""
    return (sub.groupby("sampled_at", as_index=False)[valor]
            .median()
            .sort_values("sampled_at"))


def _fig_temporal_vertices(ds) -> bytes:
    serie = temporal_mod.vertex_series(
        ds.data, convention=ds.options.piper_convention)
    if serie.empty:
        return _sin_datos("Estos datos no tienen fechas, asi que no hay "
                          "evolucion que dibujar.")

    vertices = list(dict.fromkeys(serie["vertex"]))
    estaciones = list(dict.fromkeys(serie["station_code"]))
    color_de, manijas, nota, con_mediana = _estilo_series(ds, estaciones)
    tenue = 0.45 if con_mediana else 1.0

    fig, axes = plt.subplots(2, 3, figsize=(14, 7.6), sharex=True)
    for ax, vertice in zip(axes.ravel(), vertices):
        sub = serie[serie["vertex"] == vertice]
        for est in estaciones:
            linea = sub[sub["station_code"] == est].sort_values("sampled_at")
            if len(linea) < 2:
                # Con una sola campana no hay linea que trazar: se marca el
                # punto y ya, para no insinuar una tendencia inexistente.
                ax.scatter(linea["sampled_at"], linea["pct"], s=26,
                           color=color_de(est), edgecolors=PAPEL,
                           linewidths=0.8, alpha=tenue, zorder=4)
                continue
            ax.plot(linea["sampled_at"], linea["pct"], color=color_de(est),
                    lw=1.0 if con_mediana else 1.8,
                    marker="" if con_mediana else "o", ms=5, mec=PAPEL,
                    mew=0.9, alpha=tenue, zorder=4)
        if con_mediana:
            med = _mediana_por_fecha(sub, "pct")
            ax.plot(med["sampled_at"], med["pct"], color=PALETTE[0], lw=2.6,
                    marker="o", ms=5, mec=PAPEL, mew=1.0, zorder=6)
        ax.set_title(sub["label"].iloc[0], fontsize=9.5, color=INK, pad=6)
        ax.set_ylim(0, 100)
        ax.set_ylabel("% meq", fontsize=8.5, color=INK_3)
        _frame(ax)
        ax.tick_params(axis="x", labelrotation=30, labelsize=7.5)
    for ax in axes.ravel()[len(vertices):]:
        ax.axis("off")

    if len(estaciones) > 1:
        fig.legend(handles=manijas, loc="lower center",
                   ncol=min(len(manijas), 6), fontsize=8.5, frameon=False,
                   bbox_to_anchor=(0.5, -0.02))

    n_camp = serie["sampled_at"].nunique()
    conv = piper_mod.get_convention(ds.options.piper_convention)
    sub_titulo = (f"{len(estaciones)} estaciones - {n_camp} campanas - "
                  f"convencion {conv.name_es}")
    if nota:
        sub_titulo += f" - {nota}"
    _title(fig, "Evolucion de los vertices del Piper", sub_titulo)
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    return _png(fig)


def _fig_temporal_stiff(ds) -> bytes:
    serie = temporal_mod.stiff_series(ds.data)
    if serie.empty:
        return _sin_datos("Estos datos no tienen fechas, asi que no hay "
                          "evolucion que dibujar.")

    etiquetas = list(dict.fromkeys(serie["label"]))
    estaciones = list(dict.fromkeys(serie["station_code"]))
    color_de, manijas, nota, con_mediana = _estilo_series(ds, estaciones)
    tenue = 0.45 if con_mediana else 1.0

    n = len(etiquetas)
    filas = (n + 2) // 3
    fig, axes = plt.subplots(filas, 3, figsize=(14, 2.6 * filas + 1.4),
                             sharex=True, squeeze=False)
    planos = axes.ravel()
    for ax, etiqueta in zip(planos, etiquetas):
        sub = serie[serie["label"] == etiqueta]
        for est in estaciones:
            linea = sub[sub["station_code"] == est].sort_values("sampled_at")
            if len(linea) < 2:
                ax.scatter(linea["sampled_at"], linea["meq"], s=24,
                           color=color_de(est), edgecolors=PAPEL,
                           linewidths=0.8, alpha=tenue, zorder=4)
                continue
            ax.plot(linea["sampled_at"], linea["meq"], color=color_de(est),
                    lw=1.0 if con_mediana else 1.7,
                    marker="" if con_mediana else "o", ms=4.5, mec=PAPEL,
                    mew=0.9, alpha=tenue, zorder=4)
        if con_mediana:
            med = _mediana_por_fecha(sub, "meq")
            ax.plot(med["sampled_at"], med["meq"], color=PALETTE[0], lw=2.6,
                    marker="o", ms=4.5, mec=PAPEL, mew=1.0, zorder=6)
        ax.set_title(etiqueta, fontsize=9.5, color=INK, pad=6)
        ax.set_ylabel("meq/L", fontsize=8.5, color=INK_3)
        _frame(ax)
        ax.tick_params(axis="x", labelrotation=30, labelsize=7.5)
    for ax in planos[n:]:
        ax.axis("off")

    if len(estaciones) > 1:
        fig.legend(handles=manijas, loc="lower center",
                   ncol=min(len(manijas), 6), fontsize=8.5, frameon=False,
                   bbox_to_anchor=(0.5, -0.01))

    sub_titulo = ("complementa a los vertices: los porcentajes pueden no "
                  "moverse mientras la concentracion total cambia")
    if nota:
        sub_titulo += f" - {nota}"
    _title(fig, "Evolucion de las concentraciones del Stiff", sub_titulo)
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    return _png(fig)


def _fig_balance(ds) -> bytes:
    cbe = pd.to_numeric(ds.data.get("CBE_pct"), errors="coerce").dropna()
    if cbe.empty:
        return _sin_datos("No se pudo calcular el balance ionico.")

    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    tope = float(max(abs(cbe.min()), abs(cbe.max()), ds.options.cbe_marginal_pct)) * 1.1
    ax.hist(cbe, bins=24, range=(-tope, tope), color=PALETTE[0], alpha=0.85,
            zorder=3, edgecolor=PAPEL, linewidth=0.8)
    for umbral, color, texto in (
        (ds.options.cbe_acceptable_pct, "#1c6b47", "aceptable"),
        (ds.options.cbe_marginal_pct, "#8a5300", "marginal"),
    ):
        for signo in (-1, 1):
            ax.axvline(signo * umbral, color=color, lw=1.3, ls="--", zorder=5)
        ax.text(umbral, ax.get_ylim()[1] * 0.96, f"±{umbral:g} % {texto}",
                ha="left", va="top", fontsize=8, color=color)
    ax.set_xlabel("Error de balance ionico (%)", fontsize=9.5, color=INK_2)
    ax.set_ylabel("Muestras", fontsize=9.5, color=INK_2)
    _frame(ax)

    n_ok = int((cbe.abs() <= ds.options.cbe_acceptable_pct).sum())
    _title(fig, "Calidad analitica: balance ionico",
           f"{n_ok} de {len(cbe)} muestras dentro de "
           f"±{ds.options.cbe_acceptable_pct:g} %")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _png(fig)


# ---------------------------------------------------------------- el catalogo


@dataclass(frozen=True)
class FigureSpec:
    key: str
    filename: str
    title: str
    build: Callable[[object], bytes]
    #: Devuelve ``None`` si se puede dibujar, o el motivo por el que no.
    blocked_by: Callable[[object], str | None] = lambda ds: None


def _necesita_fechas(ds) -> str | None:
    if not ds.has_dates:
        return ("no hay fechas en los datos: cada punto esta medido una sola "
                "vez, asi que no hay evolucion que representar")
    idx = temporal_mod.build_index(ds.data)
    if idx.n_campaigns < 2:
        return (f"solo hay {idx.n_campaigns} campana; hacen falta al menos dos "
                "fechas distintas para ver un cambio")
    return None


def _necesita_fluoruro(ds) -> str | None:
    f = pd.to_numeric(ds.data.get("F_mgL"), errors="coerce")
    if f is None or not f.notna().any():
        return "el fluoruro no esta medido en estos datos"
    return None


def _necesita_facies(ds) -> str | None:
    if "facies" not in ds.data.columns or ds.data["facies"].dropna().empty:
        return "no se pudieron clasificar las facies"
    return None


#: Orden del catalogo = orden de lectura de un informe: primero que agua es,
#: luego con que detalle, luego si cumple, luego como cambia.
FIGURES: list[FigureSpec] = [
    FigureSpec("piper", "01_piper.png", "Diagrama de Piper", _fig_piper),
    FigureSpec("piper_alterno", "02_piper_convencion_alterna.png",
               "Piper en la otra convencion", _fig_piper_alterno),
    FigureSpec("stiff", "03_stiff_por_grupo.png",
               "Stiff superpuestos por grupo", _fig_stiff_grupos),
    FigureSpec("durov", "04_durov.png", "Diagrama de Durov ampliado", _fig_durov),
    FigureSpec("facies", "05_facies.png", "Facies hidroquimicas",
               _fig_facies, _necesita_facies),
    FigureSpec("normas", "06_normas.png", "Incumplimientos normativos", _fig_normas),
    FigureSpec("fluoruro", "07_fluoruro.png", "Fluoruro",
               _fig_fluoruro, _necesita_fluoruro),
    FigureSpec("balance", "08_balance_ionico.png", "Balance ionico", _fig_balance),
    FigureSpec("temporal_vertices", "09_evolucion_vertices_piper.png",
               "Evolucion de los vertices del Piper",
               _fig_temporal_vertices, _necesita_fechas),
    FigureSpec("temporal_stiff", "10_evolucion_stiff.png",
               "Evolucion de las concentraciones del Stiff",
               _fig_temporal_stiff, _necesita_fechas),
]

BY_KEY = {spec.key: spec for spec in FIGURES}


def available(ds) -> list[dict]:
    """Que figuras salen y cuales no, con el motivo. Lo consume la interfaz."""
    out = []
    for spec in FIGURES:
        motivo = spec.blocked_by(ds)
        out.append({
            "key": spec.key,
            "title": spec.title,
            "filename": spec.filename,
            "available": motivo is None,
            "reason": motivo,
        })
    return out


def render(ds, key: str) -> bytes:
    """Una figura suelta, en PNG."""
    spec = BY_KEY.get(key)
    if spec is None:
        raise ValueError(
            f"Figura desconocida: {key!r}. Las disponibles son "
            f"{', '.join(BY_KEY)}."
        )
    motivo = spec.blocked_by(ds)
    if motivo is not None:
        raise ValueError(f"{spec.title}: {motivo}.")
    return spec.build(ds)


def _leeme(ds, hechas: list[FigureSpec], omitidas: list[tuple[FigureSpec, str]]) -> str:
    lineas = [
        "FIGURAS DEL ANALISIS - HydroChem",
        "=" * 60,
        "",
        f"Origen de los datos : {ds.source or 'sin nombre'}",
        f"Muestras            : {ds.n_samples}",
        f"Grupos              : {', '.join(ds.groups) or 'sin agrupar'}",
        f"Convencion de Piper : "
        f"{piper_mod.get_convention(ds.options.piper_convention).name_es}",
        f"Plantilla de Stiff  : "
        f"{stiff_mod.get_template(ds.options.stiff_template).name_es}",
        f"Norma comparada     : "
        f"{std_mod.get_standard(ds.options.standard).name_es}",
        "",
        "Los PNG estan a 200 ppp con fondo blanco: se pueden pegar en un",
        "informe sin reescalar.",
        "",
        "INCLUIDAS",
        "-" * 60,
    ]
    for spec in hechas:
        lineas.append(f"  {spec.filename:<38} {spec.title}")
    if omitidas:
        lineas += ["", "NO INCLUIDAS, Y POR QUE", "-" * 60]
        for spec, motivo in omitidas:
            lineas.append(f"  {spec.title}")
            lineas.append(f"      {motivo}.")
    lineas += [
        "",
        "AVISO SOBRE LAS FECHAS",
        "-" * 60,
        "Las figuras de evolucion solo aparecen si los datos traen varias",
        "fechas por estacion. HydroChem nunca inventa campanas ni interpola",
        "entre ellas: si solo hay un dia de medicion, no hay serie temporal,",
        "y decirlo es mas util que dibujar una linea que no existe.",
        "",
    ]
    return "\n".join(lineas)


def render_all(ds, progress=None) -> bytes:
    """Todas las figuras que se puedan dibujar, en un ZIP con su LEEME.

    :param progress: ``callable(hechas, total)``; con muchas muestras esto
        tarda varios segundos y la interfaz tiene que poder decirlo.
    """
    hechas: list[FigureSpec] = []
    omitidas: list[tuple[FigureSpec, str]] = []
    imagenes: list[tuple[str, bytes]] = []

    total = len(FIGURES)
    for i, spec in enumerate(FIGURES, start=1):
        motivo = spec.blocked_by(ds)
        if motivo is not None:
            omitidas.append((spec, motivo))
        else:
            try:
                imagenes.append((spec.filename, spec.build(ds)))
                hechas.append(spec)
            except Exception as exc:  # una figura rota no tira el paquete entero
                omitidas.append((spec, f"fallo al dibujarla ({exc})"))
        if progress:
            progress(i, total)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LEEME.txt", _leeme(ds, hechas, omitidas))
        for nombre, datos in imagenes:
            z.writestr(nombre, datos)
    return buf.getvalue()
