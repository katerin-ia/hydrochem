"""Las dependencias declaradas bastan para arrancar la aplicacion.

Existe por un fallo real: el primer despliegue en Render murio con

    RuntimeError: Form data requires "python-multipart" to be installed.

``python-multipart`` no aparece en ningun ``import`` del proyecto -lo exige
FastAPI por dentro cuando un endpoint recibe ``UploadFile``- asi que un repaso
de los imports no lo encuentra. En local estaba instalado por otra via y todo
funcionaba.

Y por un segundo fallo, el simetrico. El despliegue siguiente murio con

    ModuleNotFoundError: No module named 'sklearn'

Esta vez el paquete SI aparecia en un import: ``chemistry/multivariate.py`` lo
ponia arriba del todo. Pero scikit-learn es opcional a proposito -pesa mas de
100 MB- y no esta en ``requirements.txt``. Un import de un paquete opcional en
la cabecera de un modulo no degrada esa pantalla: tumba la aplicacion entera al
arrancar, porque ``app/main.py`` importa ese modulo.

La leccion es la misma las dos veces: en esta maquina estaba instalado y por eso
no se noto. Estas pruebas comprueban lo que de verdad hace falta en marcha, no
solo lo que se escribe con ``import``; y la de abajo lo hace **fingiendo que los
paquetes opcionales no existen**, que es la unica forma de verlo sin desplegar.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
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


# -- el segundo fallo: un paquete opcional importado en la cabecera ---------


def _imports_de_cabecera(ruta: Path) -> set[str]:
    """Paquetes que el modulo importa al cargarse, no dentro de una funcion.

    Solo cuentan los del cuerpo del modulo: un import dentro de ``def`` se
    ejecuta cuando alguien llama, y ese si se puede capturar y explicar.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    fuera: set[str] = set()
    for nodo in arbol.body:                     # <- solo el primer nivel
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                fuera.add(a.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
            fuera.add(nodo.module.split(".")[0])
        elif isinstance(nodo, ast.Try):
            # Un try/except ImportError en la cabecera si vale: es la forma
            # correcta de ofrecer algo opcional con respaldo.
            continue
    return fuera


def test_no_optional_package_is_imported_at_module_level():
    """El fallo de Render, convertido en prueba.

    Un paquete opcional importado en la cabecera de cualquier modulo de
    ``core/`` o ``app/`` impide arrancar en un servidor donde no este. Tiene que
    ir dentro de la funcion que lo usa, o envuelto en try/except ImportError.
    """
    culpables: list[str] = []
    opcionales_modulo = {ALIAS.get(p, p) for p in OPCIONALES}
    for carpeta in ("core", "app"):
        for f in (ROOT / carpeta).rglob("*.py"):
            colados = _imports_de_cabecera(f) & opcionales_modulo
            for modulo in sorted(colados):
                culpables.append(f"{f.relative_to(ROOT)} importa {modulo}")
    assert not culpables, (
        "paquetes opcionales importados al cargar el modulo:\n  "
        + "\n  ".join(culpables)
        + "\nMuevelos dentro de la funcion que los usa."
    )


def test_the_app_starts_with_only_the_declared_packages():
    """Arranca la aplicacion fingiendo que los opcionales no estan instalados.

    Es la comprobacion de extremo a extremo del fallo: se importan todos los
    modulos del nucleo y ``app.main`` en un proceso aparte donde importar
    scikit-learn lanza ImportError, igual que en Render.
    """
    opcionales = sorted({ALIAS.get(p, p) for p in OPCIONALES})
    guion = textwrap.dedent(f"""
        import importlib, pkgutil, sys
        from pathlib import Path

        RAIZ = Path({str(ROOT)!r})
        sys.path.insert(0, str(RAIZ))
        sys.path.insert(0, str(RAIZ / "core"))

        BLOQUEADOS = {opcionales!r}

        # Hace desaparecer los paquetes opcionales de este proceso.
        class Veto:
            def find_module(self, nombre, ruta=None):
                return self.find_spec(nombre, ruta)
            def find_spec(self, nombre, ruta=None, destino=None):
                if nombre.split(".")[0] in BLOQUEADOS:
                    raise ImportError(f"sin {{nombre}} (simulado)")
                return None

        for nombre in list(sys.modules):
            if nombre.split(".")[0] in BLOQUEADOS:
                del sys.modules[nombre]
        sys.meta_path.insert(0, Veto())

        import hydrochem
        for info in pkgutil.walk_packages(hydrochem.__path__, "hydrochem."):
            importlib.import_module(info.name)
        import app.main

        # Y la pantalla que usa el paquete que falta responde, sin reventar.
        from hydrochem.chemistry import multivariate
        import pandas as pd
        r = multivariate.run_pca_and_clustering(
            pd.DataFrame({{"Ca_mgL": [1.0, 2.0, 3.0, 4.0],
                          "Mg_mgL": [0.5, 1.5, 2.5, 3.5],
                          "Na_mgL": [2.0, 1.0, 4.0, 3.0]}}))
        assert r["status"] == "unavailable", r
        assert "scikit-learn" in r["message"]
        assert multivariate.available() is False
        print("OK")
    """)
    proceso = subprocess.run(
        [sys.executable, "-c", guion], capture_output=True, text=True, cwd=str(ROOT)
    )
    assert proceso.returncode == 0, (
        "la aplicacion no arranca sin los paquetes opcionales:\n"
        + proceso.stdout + proceso.stderr
    )
    assert "OK" in proceso.stdout


def test_multivariate_says_so_instead_of_crashing():
    """Con o sin scikit-learn, esta funcion devuelve siempre la misma forma."""
    import pandas as pd

    from hydrochem.chemistry import multivariate

    r = multivariate.run_pca_and_clustering(
        pd.DataFrame({"Ca_mgL": [1.0, 2.0, 3.0, 4.0],
                      "Mg_mgL": [0.5, 1.5, 2.5, 3.5],
                      "Na_mgL": [2.0, 1.0, 4.0, 3.0]}))
    for clave in ("status", "message", "samples", "loadings", "explained_variance"):
        assert clave in r or r["status"] == "ok", clave
    assert r["status"] in ("ok", "unavailable", "insufficient")


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
