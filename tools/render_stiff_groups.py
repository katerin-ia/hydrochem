"""Reproduce la figura "Superposed Stiff Diagrams by Group" del notebook.

Herramienta de desarrollo y documentacion: en la aplicacion estos paneles se
dibujan en el navegador con Plotly, a partir de las mismas coordenadas que
devuelve ``hydrochem.geometry.stiff``. Este script existe para poder comparar el
resultado con la figura original del notebook y para ilustrar la documentacion.

Uso:
    python tools/render_stiff_groups.py [plantilla]     # standard | extended
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

from hydrochem.geometry import stiff as stiff_mod
from hydrochem.pipeline import AnalysisOptions, analyse

PALETTE = ["#0e6b75", "#b5651d", "#3f6386", "#8a2f43", "#4c7a3f", "#6b5b95", "#a2322c"]
GRID = "#d5dfe2"
INK = "#12232a"
INK2 = "#53686f"


def main(template: str = "standard") -> int:
    ds = analyse(
        ROOT / "tests" / "fixtures" / "PiperStiff-QW-2019.v9.xlsm",
        AnalysisOptions(stiff_template=template),
    )
    df = ds.data
    tpl = stiff_mod.get_template(template)
    labels = stiff_mod.row_labels(tpl)
    n_rows = tpl.n_rows
    rows = stiff_mod.row_values(df, tpl)
    limit = stiff_mod.axis_limit(df, tpl)

    groups = ds.groups
    colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}

    fig, axes = plt.subplots(
        1, len(groups), figsize=(3.0 * len(groups), 4.4), sharey=True
    )
    axes = [axes] if len(groups) == 1 else list(axes)

    for ax, group in zip(axes, groups):
        mask = (df["group"] == group).to_numpy()
        subset = rows[mask]
        color = colors[group]

        for _, r in subset.iterrows():
            poly = stiff_mod.polygon(r, tpl)
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            ax.fill(xs, ys, color=color, alpha=0.22, zorder=2)
            ax.plot(xs, ys, color=color, lw=1.1, alpha=0.85, zorder=3)

        for y in range(n_rows):
            ax.axhline(y, color=GRID, lw=0.6, zorder=1)
        ax.axvline(0, color=INK2, lw=0.9, ls="--", alpha=0.6, zorder=1)

        ax.set_xlim(-limit, limit)
        ax.set_ylim(-0.55, n_rows - 0.45)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels([labels[n_rows - 1 - i][0] or "" for i in range(n_rows)], fontsize=8)
        ax.tick_params(axis="x", labelsize=7.5, colors=INK2)
        ax.set_xlabel("meq/L", fontsize=8, color=INK2)
        ax.set_title(f"{group}\n({int(mask.sum())} muestras)", fontsize=9, color=INK, pad=6)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

        # Etiquetas de los aniones al borde derecho
        for i in range(n_rows):
            right = labels[n_rows - 1 - i][1]
            if right:
                ax.text(limit * 0.97, i, right, ha="right", va="bottom",
                        fontsize=7, color=INK2)

    fig.suptitle(
        f"Diagramas de Stiff superpuestos por grupo  —  plantilla {tpl.name_es}  —  "
        f"escala comun 0 a {limit:.1f} meq/L",
        fontsize=11, fontweight="bold", color=INK, y=1.0,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))

    out = ROOT / "docs" / "figures" / f"stiff_grupos_{template}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"escrito: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "standard"))
