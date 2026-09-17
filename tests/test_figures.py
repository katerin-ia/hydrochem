"""El paquete de figuras.

Lo que se comprueba no es que las figuras sean bonitas -eso se mira- sino que:

* una figura que no se puede dibujar se declara como tal ANTES de intentarlo,
  con el motivo escrito, en vez de salir en blanco o reventar;
* el ZIP incluye exactamente lo declarado y un LEEME que nombra lo omitido;
* una figura rota no se lleva por delante a las demas.

El aviso sobre las fechas es el que mas importa: estos datos no tienen ninguna,
y la aplicacion no debe inventarlas nunca.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from _fixture import load_amargosa
from hydrochem.pipeline import AnalysisOptions, analyse
from hydrochem.report import figures as fig_mod

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "samples" / "DEMO-SINTETICO-campanas.csv"

_SIN_FECHAS = None
_CON_FECHAS = None


def sin_fechas():
    """Los 90 sitios de referencia: una sola medida por punto."""
    global _SIN_FECHAS
    if _SIN_FECHAS is None:
        _SIN_FECHAS = analyse(load_amargosa(), AnalysisOptions())
    return _SIN_FECHAS


def con_fechas():
    global _CON_FECHAS
    if _CON_FECHAS is None:
        _CON_FECHAS = analyse(DEMO, AnalysisOptions())
    return _CON_FECHAS


def test_el_catalogo_no_tiene_claves_ni_archivos_repetidos():
    claves = [f.key for f in fig_mod.FIGURES]
    nombres = [f.filename for f in fig_mod.FIGURES]
    assert len(claves) == len(set(claves))
    assert len(nombres) == len(set(nombres))


def test_sin_fechas_la_evolucion_se_declara_imposible_con_motivo():
    disponibles = {f["key"]: f for f in fig_mod.available(sin_fechas())}
    for clave in ("temporal_vertices", "temporal_stiff"):
        assert disponibles[clave]["available"] is False
        assert "fecha" in disponibles[clave]["reason"]


def test_sin_fechas_las_demas_si_salen():
    disponibles = {f["key"]: f["available"] for f in fig_mod.available(sin_fechas())}
    for clave in ("piper", "piper_alterno", "stiff", "durov", "facies",
                  "normas", "fluoruro", "balance"):
        assert disponibles[clave] is True, clave


def test_pedir_una_figura_imposible_explica_por_que():
    try:
        fig_mod.render(sin_fechas(), "temporal_vertices")
    except ValueError as exc:
        assert "fecha" in str(exc)
    else:
        raise AssertionError("deberia negarse a dibujar una serie sin fechas")


def test_una_clave_inventada_no_pasa_por_figura():
    try:
        fig_mod.render(sin_fechas(), "piper3d")
    except ValueError as exc:
        assert "piper" in str(exc)
    else:
        raise AssertionError("deberia rechazar una figura que no existe")


def test_cada_figura_disponible_produce_un_png():
    ds = sin_fechas()
    for info in fig_mod.available(ds):
        if not info["available"]:
            continue
        data = fig_mod.render(ds, info["key"])
        # Firma PNG: sin esto un HTML de error pasaria por imagen.
        assert data[:8] == b"\x89PNG\r\n\x1a\n", info["key"]
        assert len(data) > 5_000, info["key"]


def test_con_fechas_aparecen_las_dos_de_evolucion():
    disponibles = {f["key"]: f["available"] for f in fig_mod.available(con_fechas())}
    assert disponibles["temporal_vertices"] is True
    assert disponibles["temporal_stiff"] is True


def test_el_zip_trae_lo_declarado_y_nada_mas():
    ds = sin_fechas()
    esperadas = {f["filename"] for f in fig_mod.available(ds) if f["available"]}
    dentro = set(zipfile.ZipFile(io.BytesIO(fig_mod.render_all(ds))).namelist())
    assert dentro == esperadas | {"LEEME.txt"}


def test_el_leeme_nombra_lo_que_falta_y_por_que():
    z = zipfile.ZipFile(io.BytesIO(fig_mod.render_all(sin_fechas())))
    texto = z.read("LEEME.txt").decode("utf-8")
    assert "NO INCLUIDAS" in texto
    assert "Evolucion de los vertices del Piper" in texto
    # El compromiso explicito de no fabricar campanas.
    assert "nunca inventa campanas" in texto


def test_una_figura_rota_no_tumba_el_paquete(monkeypatch=None):
    """Si una figura falla, el resto tiene que seguir saliendo.

    Se rompe a proposito la del Piper y se comprueba que el ZIP llega igual,
    sin ella y con el motivo escrito.
    """
    ds = sin_fechas()
    spec = fig_mod.BY_KEY["piper"]
    original = spec.build

    def explota(_ds):
        raise RuntimeError("fallo a proposito")

    object.__setattr__(spec, "build", explota)
    try:
        datos = fig_mod.render_all(ds)
    finally:
        object.__setattr__(spec, "build", original)

    z = zipfile.ZipFile(io.BytesIO(datos))
    assert "01_piper.png" not in z.namelist()
    assert "03_stiff_por_grupo.png" in z.namelist()
    assert "fallo a proposito" in z.read("LEEME.txt").decode("utf-8")


def test_sin_fluoruro_la_figura_se_declara_imposible():
    df = load_amargosa().copy()
    df["F_mgL"] = pd.NA
    ds = analyse(df, AnalysisOptions())
    disponibles = {f["key"]: f for f in fig_mod.available(ds)}
    assert disponibles["fluoruro"]["available"] is False
    assert "fluoruro" in disponibles["fluoruro"]["reason"]


def test_los_colores_no_se_reciclan_entre_grupos():
    """Dos grupos distintos no pueden compartir tono.

    A partir del noveno se pliegan a un neutro comun, que es una perdida
    declarada; lo que no puede pasar es que el grupo 9 reciba el color del 1 y
    parezcan el mismo.
    """
    grupos = [f"G{i}" for i in range(12)]
    colores = fig_mod.group_colors(grupos)
    asignados = [colores[g] for g in grupos[: len(fig_mod.PALETTE)]]
    assert len(set(asignados)) == len(asignados)
    assert all(colores[g] == fig_mod.NEUTRO for g in grupos[len(fig_mod.PALETTE):])
