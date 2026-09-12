"""Aislamiento entre visitantes y control de la subida de archivos.

Es lo que hace que la aplicacion se pueda publicar. La primera version guardaba
el dataset en un diccionario del proceso: en local funcionaba, pero publicada el
segundo visitante sobrescribia los datos del primero.
"""

from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app
from app.session import (
    ALLOWED_SUFFIXES,
    COOKIE_NAME,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_MB,
    SessionStore,
    UploadRejected,
    safe_filename,
)

XLSM = ROOT / "tests" / "fixtures" / "PiperStiff-QW-2019.v9.xlsm"
DEMO = ROOT / "data" / "samples" / "DEMO-SINTETICO-campanas.csv"


def _client() -> TestClient:
    """Cliente con su propio tarro de cookies: simula un navegador distinto."""
    return TestClient(app)


# -- aislamiento entre visitantes -------------------------------------------


def test_two_visitors_do_not_overwrite_each_other():
    """El fallo que impedia publicarla."""
    ana, luis = _client(), _client()

    a = ana.post("/api/load-example", json={}).json()
    l = luis.post("/api/demo-campaigns", json={}).json()

    assert a["source"] == XLSM.name
    assert l["source"] == DEMO.name

    # y cada uno sigue viendo lo suyo despues de que el otro cargue
    assert ana.get("/api/state").json()["source"] == XLSM.name
    assert luis.get("/api/state").json()["source"] == DEMO.name
    assert ana.get("/api/state").json()["n_samples"] == 90
    assert luis.get("/api/state").json()["n_samples"] == 96


def test_each_visitor_gets_a_cookie():
    ana, luis = _client(), _client()
    ana.get("/")
    luis.get("/")
    sid_a = ana.cookies.get(COOKIE_NAME)
    sid_l = luis.cookies.get(COOKIE_NAME)
    assert sid_a and sid_l
    assert sid_a != sid_l


def test_reanalyse_uses_the_visitors_own_file():
    ana, luis = _client(), _client()
    ana.post("/api/load-example", json={})
    luis.post("/api/demo-campaigns", json={})
    r = ana.post("/api/reanalyse", json={"piper_convention": "notebook"}).json()
    assert r["source"] == XLSM.name
    assert r["piper"]["convention"] == "notebook"
    # el de Luis no se ha tocado
    assert luis.get("/api/state").json()["piper"]["convention"] == "classic"


def test_exports_belong_to_the_visitor_who_asks():
    ana, luis = _client(), _client()
    ana.post("/api/load-example", json={})
    luis.post("/api/demo-campaigns", json={})
    csv_ana = ana.get("/api/export/csv").content.decode("utf-8-sig")
    csv_luis = luis.get("/api/export/csv").content.decode("utf-8-sig")
    assert "Amargosa Tracer Well 2" in csv_ana
    assert csv_ana != csv_luis
    assert csv_luis.count("\n") > csv_ana.count("\n"), "la demo tiene 96 filas"


def test_a_visitor_without_data_gets_a_clear_error():
    nuevo = _client()
    assert nuevo.get("/api/state").json() == {"loaded": False}
    for ruta in ("/api/export/csv", "/api/export/xlsx", "/api/mapping"):
        r = nuevo.get(ruta)
        assert r.status_code == 400, ruta
        assert "No hay datos" in r.json()["detail"]


def test_reset_only_clears_the_asking_visitor():
    ana, luis = _client(), _client()
    ana.post("/api/load-example", json={})
    luis.post("/api/load-example", json={})
    ana.post("/api/reset")
    assert ana.get("/api/state").json()["loaded"] is False
    assert luis.get("/api/state").json()["loaded"] is True


def test_series_endpoint_is_per_session():
    ana, luis = _client(), _client()
    ana.post("/api/load-example", json={})       # sin fechas
    luis.post("/api/demo-campaigns", json={})    # con 8 campanas
    estacion = luis.get("/api/state").json()["temporal"]["repeated_stations"][0]
    r_luis = luis.post("/api/series", json={"stations": [estacion]})
    assert r_luis.status_code == 200
    assert len(r_luis.json()["vertices"]) > 0
    r_ana = ana.post("/api/series", json={"stations": [estacion]})
    assert r_ana.json()["vertices"] == [], "Ana no tiene fechas"


# -- caducidad y cupo -------------------------------------------------------


def test_idle_sessions_are_forgotten(tmp_path=None):
    raiz = Path(tmp_path or ROOT / "tests" / "_tmp_sessions")
    store = SessionStore(raiz, ttl_min=0)
    s = store.get(None)
    assert len(store) == 1
    time.sleep(0.01)
    store.get(None)  # cualquier acceso limpia las caducadas
    assert s.sid not in {x for x in store._sessions}


def test_session_quota_drops_the_oldest(tmp_path=None):
    raiz = Path(tmp_path or ROOT / "tests" / "_tmp_sessions2")
    store = SessionStore(raiz, max_sessions=3)
    ids = []
    for _ in range(5):
        ids.append(store.get(None).sid)
        time.sleep(0.005)
    assert len(store) <= 3, "la memoria no puede crecer sin tope"
    assert ids[-1] in store._sessions, "la mas reciente sobrevive"


def test_disposing_a_session_deletes_its_files(tmp_path=None):
    raiz = Path(tmp_path or ROOT / "tests" / "_tmp_sessions3")
    store = SessionStore(raiz)
    s = store.get(None)
    store.store_upload(s, "datos.csv", b"Estacion,Ca_mgL\nP1,40\n")
    assert s.source_path.exists()
    carpeta = s.workdir
    store.drop(s.sid)
    assert not carpeta.exists(), "lo que subio el usuario no se queda en el disco"


def test_a_returning_visitor_keeps_their_session():
    ana = _client()
    ana.post("/api/load-example", json={})
    sid = ana.cookies.get(COOKIE_NAME)
    # nueva peticion con la misma cookie
    assert ana.get("/api/state").json()["loaded"] is True
    assert ana.cookies.get(COOKIE_NAME) == sid


# -- control de la subida ---------------------------------------------------


def _store(nombre: str):
    raiz = ROOT / "tests" / "_tmp_uploads"
    store = SessionStore(raiz)
    return store, store.get(None), nombre


def test_filename_cannot_escape_the_session_folder():
    """Un nombre con rutas se queda solo con el nombre base."""
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("..\\\\..\\\\windows\\\\system32\\\\x.xlsx") == "x.xlsx"
    assert "/" not in safe_filename("a/b/c.csv")
    assert "\\\\" not in safe_filename("a\\\\b.csv")


def test_filename_strips_odd_characters():
    assert safe_filename("datos<>:|?.xlsx") == "datos_.xlsx"
    assert safe_filename("") == "datos.xlsx"
    assert safe_filename(None) == "datos.xlsx"
    assert len(safe_filename("x" * 400 + ".csv")) <= 120


def test_only_spreadsheet_extensions_are_accepted():
    store, s, _ = _store("x")
    for malo in ("virus.exe", "script.sh", "pagina.html", "sin_extension"):
        try:
            store.store_upload(s, malo, b"PK\x03\x04algo")
        except UploadRejected as exc:
            assert "No se admite" in str(exc), malo
        else:
            raise AssertionError(f"deberia haber rechazado {malo}")
    store.drop(s.sid)


def test_extension_must_match_the_content():
    """Renombrar un binario a .xlsx no debe colar: un xlsx es un ZIP."""
    store, s, _ = _store("x")
    try:
        store.store_upload(s, "trampa.xlsx", b"\x7fELF\x02\x01\x01\x00 binario")
    except UploadRejected as exc:
        assert "no corresponde" in str(exc)
    else:
        raise AssertionError("deberia haber rechazado el archivo")
    store.drop(s.sid)


def test_binary_disguised_as_csv_is_rejected():
    store, s, _ = _store("x")
    try:
        store.store_upload(s, "trampa.csv", b"col1,col2\n\x00\x00\x00\x00binario")
    except UploadRejected as exc:
        assert "no corresponde" in str(exc)
    else:
        raise AssertionError("deberia haber rechazado el archivo")
    store.drop(s.sid)


def test_oversized_upload_is_rejected():
    store, s, _ = _store("x")
    try:
        store.store_upload(s, "grande.csv", b"a," * (MAX_UPLOAD_BYTES // 2 + 10))
    except UploadRejected as exc:
        assert str(MAX_UPLOAD_MB) in str(exc)
    else:
        raise AssertionError("deberia haber rechazado el archivo")
    store.drop(s.sid)


def test_empty_upload_is_rejected():
    store, s, _ = _store("x")
    try:
        store.store_upload(s, "vacio.csv", b"")
    except UploadRejected as exc:
        assert "vacio" in str(exc)
    else:
        raise AssertionError("deberia haber rechazado el archivo")
    store.drop(s.sid)


def test_a_new_upload_replaces_the_previous_one():
    """Un archivo por sesion: el disco del servidor no se llena."""
    store, s, _ = _store("x")
    store.store_upload(s, "uno.csv", b"Estacion,Ca_mgL\nP1,40\n")
    store.store_upload(s, "dos.csv", b"Estacion,Ca_mgL\nP2,50\n")
    quedan = [f.name for f in s.workdir.glob("*") if f.is_file()]
    assert quedan == ["dos.csv"]
    store.drop(s.sid)


def test_valid_spreadsheets_are_accepted():
    store, s, _ = _store("x")
    store.store_upload(s, "bien.csv", b"Estacion,Ca_mgL\nP1,40\n")
    assert s.source_path.name == "bien.csv"
    store.store_upload(s, "bien.xlsx", XLSM.read_bytes()[:5000])
    assert s.source_path.name == "bien.xlsx"
    store.drop(s.sid)


def test_allowed_suffixes_cover_what_the_reader_supports():
    from hydrochem.io.readers import CSV_SUFFIXES, EXCEL_SUFFIXES

    assert ALLOWED_SUFFIXES == frozenset(EXCEL_SUFFIXES | CSV_SUFFIXES)


# -- subida a traves de la API ----------------------------------------------


def test_upload_through_the_api_and_then_analyse():
    ana = _client()
    csv = (
        "Estacion,Grupo,Longitud,Latitud,Ca (mg/L),Mg (mg/L),Sodio (mg/L),"
        "Potasio (mg/L),Bicarbonatos (mg/L),Sulfatos (mg/L),Cloruros (mg/L)\n"
        "P-01,Zona A,-77.04,-12.05,45.0,8.5,55.0,4.2,152.0,28.0,35.0\n"
        "P-02,Zona A,-77.03,-12.06,38.0,6.1,61.0,3.8,140.0,31.0,40.0\n"
    )
    r = ana.post("/api/upload", files={"file": ("prueba.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["n_samples"] == 2
    assert d["source"] == "prueba.csv"
    assert len(d["measured_ions"]) == 7


def test_upload_rejects_a_bad_file_through_the_api():
    ana = _client()
    r = ana.post("/api/upload", files={"file": ("malo.exe", b"MZ\x90\x00", "application/x-msdownload")})
    assert r.status_code == 400
    assert "No se admite" in r.json()["detail"]


def test_health_endpoint_reports_the_limits():
    h = _client().get("/api/health").json()
    assert h["ok"] is True
    for clave in ("sessions", "ttl_min", "max_sessions", "max_upload_mb"):
        assert clave in h


def test_options_publishes_the_limits():
    o = _client().get("/api/options").json()
    assert o["limits"]["max_upload_mb"] == MAX_UPLOAD_MB
    assert o["limits"]["session_ttl_min"] > 0
