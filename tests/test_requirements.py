"""Las dependencias declaradas bastan para arrancar la aplicacion.

Existe por un fallo real: el primer despliegue en Render murio con

    RuntimeError: Form data requires "python-multipart" to be installed.

``python-multipart`` no aparece en ningun ``import`` del proyecto -lo exige
FastAPI por dentro cuando un endpoint recibe ``UploadFile``- asi que un repaso
de los imports no lo encuentra. En local estaba instalado por otra via y todo
funcionaba. Estas pruebas comprueban lo que de verdad hace falta en marcha, no
solo lo que se escribe con ``import``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIREMENTS = ROOT / "requirements.txt"

#: Equivalencias entre el nombre del paquete y el nombre con el que se importa.
ALIAS = {"scikit-learn": "sklearn", "python-multipart": "multipart"}

#: Paquetes que la aplicacion puede no tener. No deben estar en requirements.
OPCIONALES = {"scikit-learn"}


def declared() -> set[str]:
    """Paquetes declarados en requirements.txt, sin los comentados."""
    out: set[str] = set()
    for linea in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        nombre = linea.split(">=")[0].split("==")[0].split("[")[0].strip()
        out.add(nombre.lower())
    return out


def imported() -> set[str]:
    """Modulos de terceros que el codigo importa explicitamente."""
    propios = {"hydrochem", "app", "core"}
    fuera = set(sys.stdlib_module_names) | propios
    encontrados: set[str] = set()
    for carpeta in ("core", "app"):
        for f in (ROOT / carpeta).rglob("*.py"):
            arbol = ast.parse(f.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    for a in nodo.names:
                        encontrados.add(a.name.split(".")[0])
                elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                    encontrados.add(nodo.module.split(".")[0])
    return encontrados - fuera


# -- el fallo concreto que rompio el despliegue -----------------------------


def test_python_multipart_is_declared():
    """Sin el, la aplicacion arranca y se cae al subir un archivo."""
    assert "python-multipart" in declared(), (
        "FastAPI necesita python-multipart para los endpoints que reciben "
        "archivos. No aparece en ningun import, asi que hay que declararlo a mano."
    )


def test_the_upload_endpoint_still_uses_form_data():
    """Si algun dia deja de recibir formularios, la dependencia sobraria.

    Esta prueba ata la una a la otra: mientras haya un UploadFile, el requisito
    tiene que seguir declarado.
    """
    fuente = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "UploadFile" in fuente and "File(" in fuente
    assert "python-multipart" in declared()


def test_uploading_a_file_works_with_what_is_declared():
    """Comprobacion de extremo a extremo del camino que fallo en Render."""
    from fastapi.testclient import TestClient

    from app.main import app

    csv = "Estacion,Calcio (mg/L),Cloruros (mg/L)\nP-01,45.0,35.0\n"
    r = TestClient(app).post(
        "/api/upload", files={"file": ("prueba.csv", csv, "text/csv")}
    )
    assert r.status_code == 200, r.text
    assert r.json()["n_samples"] == 1


# -- coherencia general -----------------------------------------------------


def test_every_imported_package_is_declared_or_optional():
    faltan = set()
    inverso = {v: k for k, v in ALIAS.items()}
    for modulo in imported():
        paquete = inverso.get(modulo, modulo)
        if paquete in OPCIONALES:
            continue
        if paquete.lower() not in declared():
            faltan.add(paquete)
    assert not faltan, f"sin declarar en requirements.txt: {sorted(faltan)}"


def test_optional_packages_are_not_declared():
    """scikit-learn son mas de 100 MB para una sola estrategia de imputacion.
    Si alguien lo anade, que sea a proposito."""
    for paquete in OPCIONALES:
        assert paquete not in declared(), (
            f"{paquete} es opcional: pesa demasiado para instalarlo siempre."
        )


def test_optional_import_fails_with_a_helpful_message():
    """Sin scikit-learn, elegir KNN tiene que explicar que pasa."""
    from hydrochem.imputation.strategies import ImputationMethod, impute
    import pandas as pd

    try:
        import sklearn  # noqa: F401
    except ImportError:
        df = pd.DataFrame({"Ca_mgL": [1.0, None, 3.0]})
        try:
            impute(df, ["Ca_mgL"], ImputationMethod.KNN)
        except ImportError as exc:
            assert "scikit-learn" in str(exc)
        else:
            raise AssertionError("deberia haber avisado")


def test_the_interface_hides_knn_when_it_is_not_installed():
    from fastapi.testclient import TestClient

    from app.main import app

    metodos = TestClient(app).get("/api/options").json()["imputation_methods"]
    knn = [m for m in metodos if m["key"] == "knn"][0]
    try:
        import sklearn  # noqa: F401
        esperado = True
    except ImportError:
        esperado = False
    assert knn["available"] is esperado
    # las demas siempre estan
    for m in metodos:
        if m["key"] != "knn":
            assert m["available"] is True, m["key"]


def test_requirements_pin_a_minimum_version():
    """Sin version minima, un alojamiento puede instalar algo demasiado viejo."""
    for linea in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        assert ">=" in linea or "==" in linea, f"sin version minima: {linea}"


def test_no_heavy_dependency_sneaked_in():
    """El plan gratuito tiene 512 MB: estas no caben y ademas no hacen falta,
    porque su funcion esta implementada en el propio proyecto."""
    prohibidas = {"pyproj", "simplekml", "geopandas", "fiona", "gdal", "shapely"}
    coladas = prohibidas & declared()
    assert not coladas, (
        f"{sorted(coladas)} no deberian hacer falta: su funcion esta en core/hydrochem"
    )
