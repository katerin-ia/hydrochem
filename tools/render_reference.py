"""Renderizador de referencia con matplotlib. Herramienta de desarrollo.

NO forma parte del nucleo ni del producto: en la aplicacion web los diagramas se
dibujan en el navegador a partir de las coordenadas que devuelve
``hydrochem.geometry``. Este script existe para (a) inspeccionar visualmente la
geometria durante el desarrollo y (b) generar las figuras de la documentacion.

Uso:
    python tools/render_reference.py [directorio_salida]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "tests"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from _fixture import FIXTURE_IONS, load_amargosa
from hydrochem.chemistry.units import add_meq_columns
from hydrochem.geometry.piper import CONVENTIONS, PiperLayout, background, get_convention, project

GRID_COLOR = "#c3ccd0"
EDGE_COLOR = "#12232a"
PALETTE = [
    "#0e6b75", "#b5651d", "#3f6386", "#8a2f43",
    "#4c7a3f", "#6b5b95", "#a2322c",
]


def draw_piper(ax, df: pd.DataFrame, convention: str, layout: PiperLayout) -> None:
    conv = get_convention(convention)
    bg = background(conv, layout)

    for seg in bg.gridlines:
        ax.plot([seg.x0, seg.x1], [seg.y0, seg.y1], color=GRID_COLOR, lw=0.55, zorder=1)
    for poly in bg.outlines:
        ax.plot(*zip(*poly), color=EDGE_COLOR, lw=1.3, zorder=3)
    for lb in bg.tick_labels:
        ax.text(lb.x, lb.y, lb.text, ha=lb.ha, va="center" if lb.va == "middle" else lb.va,
                fontsize=6, color="#66777d", zorder=4)
    for lb in bg.axis_labels:
        ax.text(lb.x, lb.y, lb.text, ha=lb.ha, va="center" if lb.va == "middle" else lb.va,
                fontsize=9, fontweight="bold", color=EDGE_COLOR, zorder=4)

    groups = list(dict.fromkeys(df["Group"]))
    colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}
    p = project(df, conv, layout)

    for grp in groups:
        m = (df["Group"] == grp).to_numpy()
        kw = dict(s=26, color=colors[grp], edgecolors="white", linewidths=0.4, zorder=6)
        ax.scatter(p["x_cat"][m], p["y_cat"][m], label=grp, **kw)
        ax.scatter(p["x_an"][m], p["y_an"][m], **kw)
        ax.scatter(p["x_diamond"][m], p["y_diamond"][m], marker="D", **kw)

    xmin, ymin, xmax, ymax = bg.bounds
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Convencion: {conv.name_es}", fontsize=11, fontweight="bold", pad=8)


def main(out_dir: str = "docs/figures") -> int:
    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)

    df = add_meq_columns(load_amargosa(), ions=FIXTURE_IONS)
    layout = PiperLayout(gap=0.6)

    fig, axes = plt.subplots(1, 2, figsize=(17, 8.2))
    for ax, key in zip(axes, CONVENTIONS):
        draw_piper(ax, df, key, layout)
    axes[0].legend(title="Grupo", loc="upper left", fontsize=7.5, title_fontsize=8, framealpha=0.9)
    fig.suptitle(
        "Diagrama de Piper con la geometria corregida - 90 sitios, Death Valley Regional Flow System",
        fontsize=13, fontweight="bold", y=0.97,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    path = out / "piper_conventions.png"
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"escrito: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/figures"))
