"""Aplicacion local de HydroChem.

Sirve la interfaz y expone el nucleo cientifico. Corre en el ordenador del
usuario: no hay servidor que alojar ni cuenta que crear.

Arranque:
    python -m app.main
o, en Windows, doble clic en "Abrir HydroChem.bat".
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))

import pandas as pd
from fastapi import Cookie, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from hydrochem.chemistry import facies as facies_mod
from hydrochem.chemistry.units import equivalent_weight_table
from hydrochem.constants import ALL_IONS, IONS
from hydrochem.geo import crs as crs_mod
from hydrochem.geo.exporters import kmz as kmz_mod
from hydrochem.geo.exporters import vectors as vec_mod
from hydrochem.geometry import durov as durov_mod
from hydrochem.quality import standards as std_mod

# Import tolerante: la aplicacion se arranca tanto con "python app/main.py"
# (que es lo que hace el lanzador de Windows y no crea contexto de paquete)
# como con "python -m app.main" o desde un servidor ASGI.
try:
    from .session import (
        COOKIE_NAME,
        MAX_UPLOAD_MB,
        SESSION_TTL_MIN,
        Session,
        SessionStore,
        UploadRejected,
    )
except ImportError:  # ejecutado como script suelto
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.session import (  # type: ignore[no-redef]
        COOKIE_NAME,
        MAX_UPLOAD_MB,
        SESSION_TTL_MIN,
        Session,
        SessionStore,
        UploadRejected,
    )
from hydrochem.geometry import piper as piper_mod
from hydrochem.geometry import stiff as stiff_mod
from hydrochem.imputation.strategies import ImputationMethod
from hydrochem.io.template import build_template, filename as template_filename
from hydrochem.io.column_mapping import BY_KEY, SCHEMA, ColumnMapping
from hydrochem.pipeline import AnalysisOptions, Dataset, analyse
from hydrochem.report import figures as fig_mod
from hydrochem import temporal as temporal_mod
from hydrochem.chemistry import multivariate as multi_mod
from hydrochem.chemistry import equilibrium as eq_mod

STATIC = Path(__file__).parent / "static"
VENDOR = Path(__file__).parent / "vendor"
EXAMPLE = ROOT / "tests" / "fixtures" / "PiperStiff-QW-2019.v9.xlsm"
DEMO_CAMPAIGNS = ROOT / "data" / "samples" / "DEMO-SINTETICO-campanas.csv"

app = FastAPI(title="HydroChem", docs_url=None, redoc_url=None)

#: Cada visitante tiene su propio dataset. Sin esto, dos personas usando la
#: aplicacion a la vez se sobrescriben los datos (ver app/session.py).
SESSIONS = SessionStore(Path(os.environ.get("HC_WORKDIR", ROOT / "data" / "sessions")))


def _session(request: Request) -> Session:
    """Sesion del visitante, creandola si es su primera peticion."""
    return SESSIONS.get(request.cookies.get(COOKIE_NAME))


def _set_cookie(response: Response, session: Session) -> Response:
    response.set_cookie(
        COOKIE_NAME, session.sid,
        max_age=SESSION_TTL_MIN * 60, httponly=True, samesite="lax",
    )
    return response


# --------------------------------------------------------------------------
# Serializacion
# --------------------------------------------------------------------------


def _clean(value):
    """Convierte a algo que JSON admita; NaN pasa a None.

    Los escalares de numpy (``numpy.bool_``, ``numpy.int64``, ``numpy.float64``)
    no son serializables aunque se parezcan a los tipos de Python, asi que se
    desenvuelven con ``.item()`` antes de nada.
    """
    if value is None:
        return None
    if hasattr(value, "item") and getattr(value, "ndim", 0) == 0:
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return None if pd.isna(value) else float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def samples_payload(ds: Dataset) -> list[dict]:
    """Un objeto por muestra, compartido por el Piper, el mapa y la tabla.

    Es la estructura de datos que hace posible la seleccion cruzada: todas las
    vistas leen el mismo array y la seleccion es un id.
    """
    df = ds.data
    out: list[dict] = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        mgl = {
            ion: _clean(row.get(f"{ion}_mgL"))
            for ion in ALL_IONS
            if f"{ion}_mgL" in df.columns
        }
        meq = {
            ion: _clean(row.get(f"{ion}_meq"))
            for ion in ALL_IONS
            if f"{ion}_meq" in df.columns
        }
        imputed = [
            ion for ion in ALL_IONS
            if f"{ion}_mgL__imputed" in df.columns and bool(row.get(f"{ion}_mgL__imputed"))
        ]
        stiff_rows = [
            [_clean(row.get(f"row{i}_left")), _clean(row.get(f"row{i}_right"))]
            for i in range(stiff_mod.get_template(ds.options.stiff_template).n_rows)
            if f"row{i}_left" in df.columns
        ]
        out.append(
            {
                "id": f"s{pos}",
                "row": int(pos),
                "station": _clean(row.get("station_code")) or f"Muestra {pos + 1}",
                "group": _clean(row.get("group")) or "Sin grupo",
                "sampled_at": _clean(row.get("sampled_at")),
                "lon": _clean(row.get(crs_mod.LON_WGS84)),
                "lat": _clean(row.get(crs_mod.LAT_WGS84)),
                "lon_raw": _clean(row.get("longitude")),
                "lat_raw": _clean(row.get("latitude")),
                "mgl": mgl,
                "meq": meq,
                "tds": _clean(row.get("tds_mgl")),
                "ph": _clean(row.get("ph")),
                "temp": _clean(row.get("temp_c")),
                "sum_cat": _clean(row.get("sum_cat")),
                "sum_an": _clean(row.get("sum_an")),
                "cbe": _clean(row.get("CBE_pct")),
                "cbe_flag": _clean(row.get("CBE_flag")),
                "alkalinity": _clean(row.get("Alkalinity_mgCaCO3")),
                "piper": {
                    "cat": [_clean(row.get("x_cat")), _clean(row.get("y_cat"))],
                    "an": [_clean(row.get("x_an")), _clean(row.get("y_an"))],
                    "diamond": [_clean(row.get("x_diamond")), _clean(row.get("y_diamond"))],
                },
                "stiff": stiff_rows,
                "imputed": imputed,
                "facies": _clean(row.get(facies_mod.FACIES_COL)),
                "facies_label": _clean(row.get(facies_mod.FACIES_LABEL_COL)),
                "n_exceedances": int(row.get("n_exceedances") or 0),
                "exceeds_health": bool(row.get("exceeds_health") or False),
                "durov": [_clean(row.get("durov_x")), _clean(row.get("durov_y"))],
                "irrigation": {
                    "sar": _clean(row.get("SAR")),
                    "sar_class": _clean(row.get("SAR_class")),
                    "rsc": _clean(row.get("RSC")),
                    "rsc_class": _clean(row.get("RSC_class")),
                    "na_pct": _clean(row.get("Na_pct")),
                    "kelley": _clean(row.get("Kelley_ratio")),
                    "mr": _clean(row.get("Magnesium_ratio")),
                    "wilcox": _clean(row.get("Wilcox_class")),
                },
                "saturation": {
                    "calcite": _clean(row.get("SI_Calcite")),
                    "gypsum": _clean(row.get("SI_Gypsum")),
                    "fluorite": _clean(row.get("SI_Fluorite")),
                    "halite": _clean(row.get("SI_Halite")),
                    "ionic_strength": _clean(row.get("ionic_strength")),
                },
            }
        )
    return out


def background_payload(convention: str) -> dict:
    """Fondo estatico del Piper: se calcula una vez y el navegador lo cachea."""
    bg = piper_mod.background(convention)
    return {
        "outlines": [[list(p) for p in poly] for poly in bg.outlines],
        "gridlines": [[s.x0, s.y0, s.x1, s.y1] for s in bg.gridlines],
        "ticks": [
            {"x": l.x, "y": l.y, "text": l.text, "ha": l.ha, "va": l.va}
            for l in bg.tick_labels
        ],
        "axis_labels": [
            {"x": l.x, "y": l.y, "text": l.text, "ha": l.ha, "va": l.va}
            for l in bg.axis_labels
        ],
        "bounds": list(bg.bounds),
    }


def suspicious_zero_ions(ds: Dataset) -> list[str]:
    """Iones cuyos ceros exactos el validador considera sospechosos.

    Un 0,00 clavado en un ion traza casi nunca es una medida: el manual del
    libro PiperStiff documenta que las celdas vacias se escriben como 0.
    """
    out: list[str] = []
    for issue in ds.report.issues:
        if issue.code == "ceros_sospechosos" and issue.field_name:
            ion = issue.field_name.replace("_mgL", "")
            if ion not in out:
                out.append(ion)
    return out


def temporal_payload(ds: Dataset) -> dict:
    """Lo que la pantalla temporal necesita para decidir que puede dibujar.

    Las series en si se piden aparte: solo tienen sentido para una estacion
    concreta y no hay por que mandarlas todas de golpe.
    """
    idx = ds.temporal
    out = idx.to_dict()
    out["message"] = idx.message_es()
    out["vertex_labels"] = temporal_mod.vertex_labels(ds.options.piper_convention)
    return out


def series_payload(ds: Dataset, stations: list[str]) -> dict:
    """Series temporales de las estaciones pedidas."""
    conv = ds.options.piper_convention
    vertices = temporal_mod.vertex_series(ds.data, stations, conv)
    cambios = temporal_mod.change_summary(ds.data, stations, conv)
    rutas = temporal_mod.trajectories(ds.data, stations)

    params = [c for c in ("tds_mgl", "ph", "temp_c", "CBE_pct",
                          "Alkalinity_mgCaCO3", "sum_cat", "sum_an")
              if c in ds.data.columns]
    series = temporal_mod.parameter_series(ds.data, params, stations)
    trends = temporal_mod.trend_summary(ds.data, params, stations)

    def rows(frame: pd.DataFrame) -> list[dict]:
        if frame.empty:
            return []
        f = frame.copy()
        if "sampled_at" in f.columns:
            f["sampled_at"] = pd.to_datetime(f["sampled_at"]).dt.strftime("%Y-%m-%d")
        return json.loads(f.to_json(orient="records", date_format="iso"))

    stiff = temporal_mod.stiff_series(
        ds.data, stations, labels=stiff_mod.row_labels(ds.options.stiff_template)
    )

    return {
        "stations": stations,
        "vertices": rows(vertices),
        "changes": rows(cambios),
        "parameters": rows(series),
        "trends": rows(trends),
        "stiff": rows(stiff),
        "trajectories": rutas,
        "parameter_labels": {
            "tds_mgl": "TDS (mg/L)", "ph": "pH", "temp_c": "Temperatura (C)",
            "CBE_pct": "Balance de carga (%)",
            "Alkalinity_mgCaCO3": "Alcalinidad (mg/L CaCO3)",
            "sum_cat": "Suma de cationes (meq/L)", "sum_an": "Suma de aniones (meq/L)",
        },
    }


def _standard_payload(ds: Dataset) -> dict:
    if not ds.options.standard:
        return {"key": None, "name": "Sin comprobar", "verified": True, "rows": []}
    std = std_mod.get_standard(ds.options.standard)
    tabla = ds.compliance
    return {
        "key": std.key, "name": std.name_es, "source": std.source,
        "verified": std.verified,
        "rows": json.loads(tabla.to_json(orient="records")) if not tabla.empty else [],
    }


def _durov_payload(ds: Dataset) -> dict:
    """Fondo del Durov y estado de sus dos paneles laterales."""
    lay = durov_mod.DurovLayout()
    projected = durov_mod.project(ds.data, lay)
    panels = durov_mod.panel_positions(ds.data, projected, lay)
    bg = durov_mod.background(lay, panels)

    def points(key):
        panel = panels.get(key, {})
        if not panel.get("available"):
            return {"available": False, "reason": panel.get("reason", "")}
        return {
            "available": True, "n": panel["n"],
            "min": panel["min"], "max": panel["max"],
            "x": [None if pd.isna(v) else float(v) for v in panel["x"]],
            "y": [None if pd.isna(v) else float(v) for v in panel["y"]],
        }

    return {
        "outlines": [[list(pt) for pt in poly] for poly in bg.outlines],
        "gridlines": [[g.x0, g.y0, g.x1, g.y1] for g in bg.gridlines],
        "axis_labels": [
            {"x": l.x, "y": l.y, "text": l.text, "ha": l.ha, "va": l.va}
            for l in bg.axis_labels if l.text
        ],
        "tick_labels": [
            {"x": l.x, "y": l.y, "text": l.text, "ha": l.ha, "va": l.va}
            for l in bg.tick_labels
        ],
        "bounds": list(bg.bounds),
        "axis_titles": durov_mod.axis_titles(),
        "square": [
            [None if pd.isna(a) else float(a), None if pd.isna(b) else float(b)]
            for a, b in zip(projected[durov_mod.X_COL], projected[durov_mod.Y_COL])
        ],
        "cation": [
            [None if pd.isna(a) else float(a), None if pd.isna(b) else float(b)]
            for a, b in zip(projected["cat_x"], projected["cat_y"])
        ],
        "anion": [
            [None if pd.isna(a) else float(a), None if pd.isna(b) else float(b)]
            for a, b in zip(projected["an_x"], projected["an_y"])
        ],
        "ph": points("ph"),
        "tds": points("tds"),
    }


def _fluoride_summary(ds: Dataset) -> dict:
    df = ds.data
    if "F_mgL" not in df.columns:
        return {"has_fluoride": False, "n_measured": 0}
    vals = pd.to_numeric(df["F_mgL"], errors="coerce").dropna()
    if vals.empty:
        return {"has_fluoride": False, "n_measured": 0}
    n_measured = len(vals)
    n_exceed = int((vals > 1.5).sum())
    n_severe = int((vals > 4.0).sum())
    n_low = int((vals < 0.5).sum())
    n_optimal = int(((vals >= 0.5) & (vals <= 1.5)).sum())
    return {
        "has_fluoride": True,
        "n_measured": n_measured,
        "n_exceed_who": n_exceed,
        "pct_exceed_who": round(n_exceed / n_measured * 100.0, 1),
        "n_severe": n_severe,
        "n_low_caries": n_low,
        "pct_low_caries": round(n_low / n_measured * 100.0, 1),
        "n_optimal": n_optimal,
        "pct_optimal": round(n_optimal / n_measured * 100.0, 1),
        "min": round(float(vals.min()), 2),
        "median": round(float(vals.median()), 2),
        "max": round(float(vals.max()), 2),
    }


def dataset_payload(ds: Dataset, detected_zero_ions: list[str] | None = None) -> dict:
    """:param detected_zero_ions: iones con ceros sospechosos detectados **antes**
        de convertirlos. Hay que arrastrarlo: una vez convertidos ya no hay ceros
        que detectar, y la interfaz perderia el ajuste que debe poder revertir."""
    conv = piper_mod.get_convention(ds.options.piper_convention)
    tpl = stiff_mod.get_template(ds.options.stiff_template)
    return {
        "source": ds.source,
        "n_samples": ds.n_samples,
        "groups": ds.groups,
        "measured_ions": ds.measured_ions,
        "ion_labels": {i: IONS[i].label for i in ALL_IONS},
        "has_coordinates": ds.has_coordinates,
        "has_dates": ds.has_dates,
        "campaigns": ds.campaigns,
        "temporal": temporal_payload(ds),
        "fluoride": _fluoride_summary(ds),
        "multivariate": multi_mod.run_pca_and_clustering(ds.data),
        "is_synthetic_demo": ds.source == DEMO_CAMPAIGNS.name,
        "options": ds.options.to_dict(),
        "suspicious_zero_ions": detected_zero_ions if detected_zero_ions is not None
                                else suspicious_zero_ions(ds),
        "zeros_as_missing_for": list(ds.options.zeros_as_missing_for),
        "report": ds.report.to_dict(),
        "summary": ds.report.summary_es(),
        "piper": {
            "convention": conv.key,
            "name": conv.name_es,
            "note": conv.note_es,
            "background": background_payload(conv.key),
        },
        "facies": {
            "scheme": ds.options.facies_scheme,
            "name": facies_mod.get_scheme(ds.options.facies_scheme).name_es,
            "note": facies_mod.get_scheme(ds.options.facies_scheme).note_es,
            "counts": json.loads(ds.facies_counts.to_json(orient="records")),
            "colors": {
                code: facies_mod.color_of(code, ds.options.facies_scheme)
                for code in ds.data[facies_mod.FACIES_COL].unique()
            } if facies_mod.FACIES_COL in ds.data.columns else {},
            "labels": {
                code: facies_mod.label_of(code, ds.options.facies_scheme)
                for code in ds.data[facies_mod.FACIES_COL].unique()
            } if facies_mod.FACIES_COL in ds.data.columns else {},
        },
        "standard": _standard_payload(ds),
        "crs": ds.crs.to_dict(),
        "crs_declared": ds.options.crs is not None,
        "durov": _durov_payload(ds),
        "stiff": {
            "template": tpl.key,
            "name": tpl.name_es,
            "note": tpl.note_es,
            "labels": stiff_mod.row_labels(tpl),
        },
        "samples": samples_payload(ds),
    }


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    session = _session(request)
    return _set_cookie(
        HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8")), session
    )


@app.get("/api/options")
def options() -> dict:
    """Todo lo que el usuario puede elegir, para construir los controles."""
    return {
        "piper_conventions": [
            {"key": c.key, "name": c.name_es, "note": c.note_es}
            for c in piper_mod.CONVENTIONS.values()
        ],
        "stiff_templates": [
            {"key": t.key, "name": t.name_es, "note": t.note_es}
            for t in stiff_mod.TEMPLATES.values()
        ],
        "imputation_methods": [
            {"key": m.value, "name": m.label_es, "available": _method_available(m)}
            for m in ImputationMethod
        ],
        "facies_schemes": [
            {"key": s.key, "name": s.name_es, "note": s.note_es}
            for s in facies_mod.SCHEMES.values()
        ],
        "standards": std_mod.available(),
        "crs_options": crs_mod.available_crs(),
        "schema": [
            {
                "key": f.key, "label": f.label_es, "kind": f.kind.value,
                "kind_label": f.kind.label_es, "unit": f.unit or "",
                "required": f.required,
            }
            for f in SCHEMA
        ],
        "ions": [{"key": i, "label": IONS[i].label, "name": IONS[i].name_es} for i in ALL_IONS],
        "limits": {
            "max_upload_mb": MAX_UPLOAD_MB,
            "session_ttl_min": SESSION_TTL_MIN,
        },
        "example_available": EXAMPLE.exists(),
        "example_name": EXAMPLE.name,
        "demo_campaigns_available": DEMO_CAMPAIGNS.exists(),
    }


def _method_available(method: ImputationMethod) -> bool:
    """KNN necesita scikit-learn, que es opcional.

    Si no esta instalado, la interfaz marca la opcion como no disponible en vez
    de ofrecerla y fallar al elegirla.
    """
    if method is not ImputationMethod.KNN:
        return True
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return False
    return True


def _options_from(payload: dict) -> AnalysisOptions:
    opts = AnalysisOptions()
    for key in (
        "ew_table", "piper_convention", "stiff_template", "imputation",
        "min_group_size", "cbe_acceptable_pct", "cbe_marginal_pct",
        "facies_scheme", "standard", "crs",
    ):
        if payload.get(key) is not None:
            setattr(opts, key, payload[key])
    zeros = payload.get("zeros_as_missing_for")
    if zeros is not None:
        opts.zeros_as_missing_for = tuple(zeros)
    return opts


def _run(session: Session, source, opts: AnalysisOptions, sheet=None,
         zeros_decided: bool = False, mapping: ColumnMapping | None = None,
         display_name: str | None = None) -> JSONResponse:
    """Analiza y devuelve el resultado.

    Si el usuario no ha decidido nada sobre los ceros sospechosos, se aplica la
    lectura mas defendible —tratarlos como no medidos— y se deja constancia en
    el informe. La interfaz lo muestra como un ajuste activo y reversible: no se
    altera un dato en silencio, pero tampoco se deja el valor por omision en la
    opcion que sesga el resultado.
    """
    try:
        ds = analyse(source, opts, sheet=sheet, mapping=mapping)
        detected = suspicious_zero_ions(ds)
        if not zeros_decided and detected:
            opts.zeros_as_missing_for = tuple(detected)
            ds = analyse(source, opts, sheet=sheet, mapping=mapping)
        elif zeros_decided:
            # La deteccion se hace sobre el dato ya convertido, asi que no
            # encuentra nada; se recuerda lo que el usuario tiene en juego.
            detected = sorted(set(detected) | set(opts.zeros_as_missing_for))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}")
    if display_name:
        ds.source = display_name
    session.dataset = ds
    if isinstance(source, pd.DataFrame):
        session.source_frame = source.copy()
        session.source_path = None
        session.source_mapping = mapping
    else:
        session.source_frame = None
        session.source_path = Path(source)
        session.source_mapping = mapping
    payload = dataset_payload(ds, detected_zero_ions=detected)
    return _set_cookie(
        JSONResponse(json.loads(json.dumps(payload, allow_nan=False))), session
    )


@app.post("/api/load-example")
def load_example(request: Request, payload: dict | None = None) -> JSONResponse:
    if not EXAMPLE.exists():
        raise HTTPException(status_code=404, detail="El archivo de ejemplo no esta disponible.")
    payload = payload or {}
    session = _session(request)
    session.source_path = EXAMPLE
    return _run(session, EXAMPLE, _options_from(payload),
                zeros_decided="zeros_as_missing_for" in payload)


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """Recibe un archivo del usuario, comprobandolo antes de guardarlo."""
    session = _session(request)
    # Se lee con tope: asi un archivo enorme no llena la memoria del servidor
    # antes de que se rechace.
    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        dest = SESSIONS.store_upload(session, file.filename, data)
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _run(session, dest, AnalysisOptions())


@app.post("/api/reanalyse")
def reanalyse(request: Request, payload: dict) -> JSONResponse:
    """Vuelve a calcular con otras opciones, sin volver a subir el archivo."""
    session = _session(request)
    source = session.source_frame if session.source_frame is not None else session.source_path
    if source is None:
        raise HTTPException(status_code=400, detail="Carga antes un archivo.")
    payload = payload or {}
    return _run(session, source, _options_from(payload),
                zeros_decided="zeros_as_missing_for" in payload,
                mapping=session.source_mapping)


@app.post("/api/demo-campaigns")
def load_demo_campaigns(request: Request, payload: dict | None = None) -> JSONResponse:
    """Archivo SINTETICO con 8 campanas, solo para ver funcionando lo temporal."""
    if not DEMO_CAMPAIGNS.exists():
        raise HTTPException(
            status_code=404,
            detail="Falta el archivo de demostracion. Generalo con "
                   "python tools/make_demo_campaigns.py",
        )
    payload = payload or {}
    session = _session(request)
    session.source_path = DEMO_CAMPAIGNS
    return _run(session, DEMO_CAMPAIGNS, _options_from(payload),
                zeros_decided="zeros_as_missing_for" in payload)


@app.post("/api/series")
def series(request: Request, payload: dict) -> JSONResponse:
    """Series temporales de una o varias estaciones."""
    ds = _require_dataset(request)
    stations = payload.get("stations") or []
    if not stations:
        raise HTTPException(status_code=400, detail="Indica al menos una estacion.")
    body = series_payload(ds, list(stations))
    return JSONResponse(json.loads(json.dumps(body, allow_nan=False)))


@app.get("/api/state")
def state(request: Request) -> JSONResponse:
    """Dataset que el servidor tiene en memoria, si hay alguno.

    La aplicacion guarda el estado en el proceso, asi que al recargar la pagina
    el navegador se queda sin datos mientras el servidor sigue teniendolos. Sin
    esto, un "reanalizar" despues de una recarga trabajaria en silencio sobre el
    archivo anterior, que es como aparecio este fallo.
    """
    session = _session(request)
    if session.dataset is None:
        return _set_cookie(JSONResponse({"loaded": False}), session)
    payload = dataset_payload(
        session.dataset, detected_zero_ions=suspicious_zero_ions(session.dataset)
    )
    payload["loaded"] = True
    return _set_cookie(
        JSONResponse(json.loads(json.dumps(payload, allow_nan=False))), session
    )


@app.post("/api/reset")
def reset(request: Request) -> JSONResponse:
    """Olvida el dataset de esta sesion y borra sus archivos."""
    sid = request.cookies.get(COOKIE_NAME)
    if sid:
        SESSIONS.drop(sid)
    return JSONResponse({"loaded": False})


@app.get("/api/health")
def health() -> JSONResponse:
    """Comprobacion de vida y cifras del servidor, para el alojamiento."""
    return JSONResponse({"ok": True, **SESSIONS.stats})


@app.get("/api/mapping")
def mapping(request: Request) -> JSONResponse:
    """Mapeo actual de columnas, para poder corregirlo a mano."""
    ds = _require_dataset(request)
    origen = (ds.read_result.data.columns.tolist()
              if ds.read_result is not None else [])
    return JSONResponse({
        "mapping": dict(ds.mapping.mapping),
        "unmatched": list(ds.mapping.unmatched),
        "source_columns": [str(c) for c in origen],
        "missing_required": list(ds.mapping.missing_required),
        "rows": json.loads(ds.mapping.describe().to_json(orient="records")),
    })


@app.post("/api/mapping")
def set_mapping(request: Request, payload: dict) -> JSONResponse:
    """Reanaliza con un mapeo corregido por el usuario."""
    session = _session(request)
    source = session.source_frame if session.source_frame is not None else session.source_path
    if source is None:
        raise HTTPException(status_code=400, detail="Carga antes un archivo.")
    nuevo = ColumnMapping(mapping=dict(payload.get("mapping") or {}))
    if nuevo.missing_required:
        raise HTTPException(
            status_code=400,
            detail="Falta asignar: " + ", ".join(nuevo.missing_required),
        )
    opts = _options_from(payload)
    try:
        ds = analyse(source, opts, mapping=nuevo)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo reanalizar: {exc}")
    session.dataset = ds
    session.source_mapping = nuevo
    payload_out = dataset_payload(ds, detected_zero_ions=suspicious_zero_ions(ds))
    return _set_cookie(
        JSONResponse(json.loads(json.dumps(payload_out, allow_nan=False))), session
    )


def _require_dataset(request: Request) -> Dataset:
    session = _session(request)
    if session.dataset is None:
        raise HTTPException(status_code=400, detail="No hay datos cargados.")
    return session.dataset


def _stem(ds: Dataset) -> str:
    return (ds.source.rsplit(".", 1)[0] or "hydrochem").replace(" ", "_")


def _project_document(ds: Dataset) -> dict:
    """Formato portable de HydroChem: datos de entrada, mapeo y opciones.

    No guarda los resultados calculados: al abrirlo se calculan de nuevo para
    que nunca sobrevivan resultados incompatibles con una version futura.
    """
    if ds.read_result is not None:
        frame = ds.read_result.data.copy()
        mapping = dict(ds.mapping.mapping)
    else:
        cols = [field.key for field in SCHEMA if field.key in ds.data.columns]
        frame = ds.data.loc[:, cols].copy()
        mapping = {column: column for column in cols}
    records = json.loads(frame.to_json(orient="records", date_format="iso"))
    return {
        "format": "hydrochem-project",
        "version": 1,
        "source": ds.source,
        "options": ds.options.to_dict(),
        "mapping": mapping,
        "records": records,
    }


@app.get("/api/template")
def template(kind: str = "simple") -> Response:
    """Plantilla Excel con cabeceras que la deteccion reconoce sin ajustes.

    :param kind: ``simple`` (una fila por punto) o ``campaigns`` (varias fechas
        por punto, que es lo que necesita el analisis temporal).
    """
    try:
        book = build_template(kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        book,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                f'attachment; filename="{template_filename(kind)}"'
        },
    )


@app.get("/api/project")
def export_project(request: Request) -> Response:
    ds = _require_dataset(request)
    text = json.dumps(_project_document(ds), ensure_ascii=False, separators=(",", ":"))
    return Response(
        text.encode("utf-8"), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{_stem(ds)}.hydrochem.json"'},
    )


@app.post("/api/project")
async def import_project(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """Reabre un proyecto guardado por HydroChem, sin ejecutar archivos."""
    raw = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El proyecto supera el limite de tamano.")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="No es un proyecto HydroChem JSON valido.") from exc
    if document.get("format") != "hydrochem-project" or document.get("version") != 1:
        raise HTTPException(status_code=400, detail="El archivo no corresponde a un proyecto HydroChem compatible.")
    records = document.get("records")
    if not isinstance(records, list) or not records:
        raise HTTPException(status_code=400, detail="El proyecto no contiene muestras para analizar.")
    frame = pd.DataFrame(records)
    mapping_data = document.get("mapping") or {}
    if not isinstance(mapping_data, dict):
        raise HTTPException(status_code=400, detail="El mapeo del proyecto no es valido.")
    mapping = ColumnMapping(
        mapping={str(k): str(v) for k, v in mapping_data.items()
                 if str(k) in BY_KEY and str(v) in frame.columns}
    )
    if mapping.missing_required:
        raise HTTPException(status_code=400, detail="El proyecto no trae: " + ", ".join(mapping.missing_required))
    session = _session(request)
    name = str(document.get("source") or "proyecto_hydrochem")
    return _run(session, frame, _options_from(document.get("options") or {}),
                mapping=mapping, display_name=name)


@app.get("/api/figures")
def figures_index(request: Request) -> dict:
    """Que figuras se pueden dibujar con estos datos, y por que no las demas.

    La interfaz lo usa para no ofrecer un boton que solo puede fallar: si no
    hay fechas, la evolucion aparece explicada y desactivada, no rota.
    """
    ds = _require_dataset(request)
    return {"figures": fig_mod.available(ds), "stem": _stem(ds)}


@app.get("/api/figure/{key}.png")
def figure_png(request: Request, key: str) -> Response:
    """Una figura suelta, en PNG a 200 ppp con fondo blanco."""
    ds = _require_dataset(request)
    try:
        data = fig_mod.render(ds, key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    nombre = f"{_stem(ds)}_{fig_mod.BY_KEY[key].filename}"
    return Response(
        data,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@app.get("/api/export/figures.zip")
def export_figures(request: Request) -> Response:
    """Todas las figuras que se puedan dibujar, con un LEEME que las explica.

    Se generan en el servidor con matplotlib y no en el navegador: asi salen a
    200 ppp, con fondo blanco y el mismo aspecto que las del notebook, en vez de
    una captura del lienzo a la resolucion que tenga la pantalla de turno.
    """
    ds = _require_dataset(request)
    data = fig_mod.render_all(ds)
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition":
                f'attachment; filename="{_stem(ds)}_figuras.zip"'
        },
    )


@app.get("/api/export/phreeqc")
def export_phreeqc(request: Request) -> Response:
    """Genera un archivo de script por lotes .pqi para USGS PHREEQC."""
    ds = _require_dataset(request)
    pqi_text = eq_mod.generate_phreeqc_pqi(ds.data, title=f"HydroChem - {_stem(ds)}")
    return Response(
        pqi_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_stem(ds)}.pqi"'},
    )


@app.get("/api/export/kmz")
def export_kmz(request: Request, colour_by: str = "facies",
               template: str | None = None) -> Response:
    """KMZ para Google Earth, con el diagrama de Stiff como icono de cada punto."""
    ds = _require_dataset(request)
    try:
        res = kmz_mod.build(
            ds.data, name=_stem(ds), colour_by=colour_by,
            stiff_template=template or ds.options.stiff_template,
            standard=ds.options.standard,
            filename=f"{_stem(ds)}.kmz",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        res.content,
        media_type="application/vnd.google-earth.kmz",
        headers={
            "Content-Disposition": f'attachment; filename="{res.filename}"',
            "X-Placemarks": str(res.n_placemarks),
            "X-Skipped": str(res.n_skipped),
        },
    )


@app.get("/api/export/kml")
def export_kml(request: Request, colour_by: str = "facies") -> Response:
    ds = _require_dataset(request)
    try:
        texto = vec_mod.to_kml(ds.data, name=_stem(ds), colour_by=colour_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        texto.encode("utf-8"),
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": f'attachment; filename="{_stem(ds)}.kml"'},
    )


@app.get("/api/export/xlsx")
def export_xlsx(request: Request) -> Response:
    ds = _require_dataset(request)
    data = vec_mod.to_xlsx(
        ds.data,
        validation=pd.DataFrame(ds.report.column_stats),
        compliance=ds.compliance,
        facies_summary=ds.facies_counts,
        equivalent_weights=equivalent_weight_table(ds.options.ew_table),
    )
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_stem(ds)}.xlsx"'},
    )


@app.get("/api/export/csv")
def export_csv(request: Request) -> Response:
    ds = _require_dataset(request)
    return Response(
        vec_mod.to_csv(ds.data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_stem(ds)}.csv"'},
    )


@app.get("/api/export/geojson")
def export_geojson(request: Request) -> Response:
    ds = _require_dataset(request)
    try:
        texto = vec_mod.to_geojson(ds.data, name=_stem(ds))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        texto.encode("utf-8"),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{_stem(ds)}.geojson"'},
    )


app.mount("/vendor", StaticFiles(directory=VENDOR), name="vendor")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main(port: int | None = None, host: str | None = None,
         open_browser: bool | None = None) -> None:
    """Arranca el servidor.

    En local escucha solo en 127.0.0.1 y abre el navegador. Publicada (variable
    ``HC_SERVE_PUBLIC``, o ``PORT`` definido por el alojamiento) escucha en todas
    las interfaces y no intenta abrir ningun navegador.
    """
    import uvicorn

    publico = bool(os.environ.get("HC_SERVE_PUBLIC") or os.environ.get("PORT"))
    port = port or int(os.environ.get("PORT", "8000"))
    host = host or ("0.0.0.0" if publico else "127.0.0.1")
    if open_browser is None:
        open_browser = not publico

    if publico:
        print(f"\n  HydroChem escuchando en {host}:{port}")
        print(f"  Sesiones simultaneas: {SESSIONS.max_sessions} | "
              f"caducidad: {SESSION_TTL_MIN} min | subida maxima: {MAX_UPLOAD_MB} MB\n")
    else:
        url = f"http://127.0.0.1:{port}"
        print("\n  HydroChem esta arrancando...")
        print(f"  Abre esta direccion en tu navegador:  {url}")
        print("  Para cerrar la aplicacion, cierra esta ventana.\n")
        if open_browser:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
