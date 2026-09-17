"""Plantillas de Excel para que el usuario prepare sus datos.

Hay dos, porque son dos situaciones distintas:

``simple``
    Una fila por punto de muestreo. Es lo que basta para el Piper, el Stiff, el
    Durov, las facies y el mapa.

``campaigns``
    La misma estacion repetida en varias fechas. Es la unica forma de que el
    modulo temporal tenga algo que dibujar, y la estructura no es evidente: la
    gente tiende a poner una columna por campana (``Ca marzo``, ``Ca setiembre``)
    en vez de repetir la fila. Con ese formato en ancho no se puede analizar, asi
    que la plantilla trae el ejemplo ya montado en largo y una hoja que lo
    explica.

Las dos llevan las cabeceras que el mapeo automatico reconoce sin ajustes, una
fila de ayuda debajo y un ejemplo que se borra.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Paleta de la aplicacion, para que la plantilla se reconozca como suya.
VERDE = "237551"
VERDE_SUAVE = "DCF0E5"
PAPEL = "FFFFFF"
TINTA = "16241D"
LINEA = "CFE0D6"


@dataclass(frozen=True)
class Columna:
    titulo: str
    ayuda: str
    obligatoria: bool = False


#: Columnas comunes a las dos plantillas, en el orden en que conviene leerlas.
IDENTIDAD = [
    Columna("Codigo de estacion", "Identificador del punto. Se repite en cada campana.", True),
    Columna("Grupo", "Zona, acuifero o unidad. Agrupa y colorea los diagramas."),
]

TEMPORAL = [
    Columna("Fecha de muestreo", "AAAA-MM-DD. Sin ella no hay analisis temporal.", True),
    Columna("Campana", "Nombre corto de la salida de campo: C1, Estiaje 2026..."),
]

UBICACION = [
    Columna("Latitud", "Grados WGS84 (-12.0464) o Norte UTM (8670000)."),
    Columna("Longitud", "Grados WGS84 (-77.0428) o Este UTM (277000)."),
]

FISICO = [
    Columna("pH", "Unidades de pH. Necesario para el diagrama de Durov."),
    Columna("Temperatura (C)", "Opcional."),
    Columna("Conductividad (uS/cm)", "Opcional."),
    Columna("TDS (mg/L)", "Solidos disueltos totales. Opcional."),
]

IONES = [
    Columna("Calcio (mg/L)", "Ion mayoritario.", True),
    Columna("Magnesio (mg/L)", "Ion mayoritario.", True),
    Columna("Sodio (mg/L)", "Ion mayoritario.", True),
    Columna("Potasio (mg/L)", "Ion mayoritario.", True),
    Columna("Bicarbonatos (mg/L)", "Ion mayoritario.", True),
    Columna("Carbonatos (mg/L)", "Deja 0 si el pH es menor que 8,3."),
    Columna("Sulfatos (mg/L)", "Ion mayoritario.", True),
    Columna("Cloruros (mg/L)", "Ion mayoritario.", True),
    Columna("Fluoruros (mg/L)", "Se compara con el limite normativo. Admite <0,05."),
    Columna("Nitratos (mg/L)", "Se compara con el limite normativo. Admite ND."),
]

AYUDA_COMUN = [
    ("Como rellenarla", True),
    ("", False),
    ("1. Una fila = una muestra. No combines celdas ni pongas titulos encima de la fila 1.", False),
    ("2. Borra la fila 2 (la de ayuda) y la fila de ejemplo antes de subir el archivo.", False),
    ("3. Las concentraciones van en mg/L. Si las tienes en meq/L, conviertelas antes.", False),
    ("4. Deja la celda VACIA si no midieron el parametro. No pongas 0:", False),
    ("   un cero significa 'medido y ausente', y cambia el balance ionico y los", False),
    ("   porcentajes de incumplimiento.", False),
    ("5. Si el laboratorio informo por debajo del limite de deteccion, escribe", False),
    ("   el limite tal cual: <0,05. La aplicacion lo entiende.", False),
    ("", False),
    ("Columnas obligatorias", True),
    ("   Codigo de estacion, y los siete iones mayoritarios:", False),
    ("   Ca, Mg, Na, K, HCO3, SO4 y Cl.", False),
    ("", False),
    ("Lo demas es opcional, pero cada cosa habilita algo:", True),
    ("   Latitud y Longitud -> mapa y exportacion a Google Earth", False),
    ("   pH -> diagrama de Durov completo", False),
    ("   Fecha de muestreo -> evolucion entre campanas", False),
    ("   Grupo -> color y agrupacion en todos los diagramas", False),
    ("", False),
    ("Si alguna columna no se reconoce, la puedes asignar a mano en", False),
    ("Datos -> Columnas, sin volver a editar el Excel.", False),
]

AYUDA_CAMPANAS = [
    ("", False),
    ("Esta plantilla es la de varias campanas", True),
    ("", False),
    ("La misma estacion se repite una vez por fecha. Fijate en el ejemplo:", False),
    ("PZ-01 aparece tres veces, con tres fechas distintas.", False),
    ("", False),
    ("NO pongas una columna por campana (Ca marzo, Ca setiembre...).", False),
    ("Ese formato no se puede analizar: la aplicacion no sabria que", False),
    ("'Ca marzo' y 'Ca setiembre' son el mismo parametro en dos momentos.", False),
    ("", False),
    ("Con dos campanas ya se ve la evolucion. Para hablar de tendencia", False),
    ("hacen falta al menos tres, y la aplicacion lo advierte si no las hay.", False),
]


def _columnas(kind: str) -> list[Columna]:
    if kind == "campaigns":
        return IDENTIDAD + TEMPORAL + UBICACION + FISICO + IONES
    return IDENTIDAD + [TEMPORAL[0]] + UBICACION + FISICO + IONES


def _ejemplos(kind: str) -> list[list]:
    """Filas de ejemplo. Valores plausibles y con el balance ionico cerrado,
    para que quien las deje por error no vea la aplicacion llena de avisos."""
    base_simple = {
        "Codigo de estacion": "PZ-01", "Grupo": "Sector norte",
        "Fecha de muestreo": "2026-01-15",
        "Latitud": -12.0464, "Longitud": -77.0428,
        "pH": 7.3, "Temperatura (C)": 21.4, "Conductividad (uS/cm)": 650,
        "TDS (mg/L)": 420,
        "Calcio (mg/L)": 68.2, "Magnesio (mg/L)": 14.5, "Sodio (mg/L)": 52.1,
        "Potasio (mg/L)": 3.8, "Bicarbonatos (mg/L)": 268.0,
        "Carbonatos (mg/L)": 0.0, "Sulfatos (mg/L)": 48.0,
        "Cloruros (mg/L)": 37.0, "Fluoruros (mg/L)": 0.7, "Nitratos (mg/L)": 4.2,
    }
    if kind != "campaigns":
        return [[base_simple.get(c.titulo, "") for c in _columnas(kind)]]

    # Dos estaciones x tres campanas: el minimo que ensena la estructura.
    filas = []
    for estacion, grupo, lat, lon, factor in (
        ("PZ-01", "Sector norte", -12.0464, -77.0428, 1.00),
        ("PZ-02", "Sector sur", -12.0731, -77.0155, 1.35),
    ):
        for fecha, campana, deriva in (
            ("2026-01-15", "C1", 1.00),
            ("2026-07-20", "C2", 1.06),
            ("2027-01-18", "C3", 1.13),
        ):
            escala = factor * deriva
            fila = dict(base_simple)
            fila.update({
                "Codigo de estacion": estacion, "Grupo": grupo,
                "Fecha de muestreo": fecha, "Campana": campana,
                "Latitud": lat, "Longitud": lon,
                "pH": round(7.3 - (deriva - 1) * 1.2, 2),
                "Conductividad (uS/cm)": round(650 * escala),
                "TDS (mg/L)": round(420 * escala),
            })
            for ion in ("Calcio (mg/L)", "Magnesio (mg/L)", "Sodio (mg/L)",
                        "Potasio (mg/L)", "Bicarbonatos (mg/L)", "Sulfatos (mg/L)",
                        "Cloruros (mg/L)"):
                fila[ion] = round(base_simple[ion] * escala, 2)
            filas.append([fila.get(c.titulo, "") for c in _columnas(kind)])
    return filas


def _hoja_ayuda(wb: Workbook, kind: str) -> None:
    ws = wb.create_sheet("LEEME", 0)
    lineas = list(AYUDA_COMUN)
    if kind == "campaigns":
        lineas = AYUDA_CAMPANAS + [("", False)] + lineas
    for i, (texto, destacado) in enumerate(lineas, start=1):
        celda = ws.cell(i, 1, texto)
        if destacado:
            celda.font = Font(bold=True, size=12, color=VERDE)
    ws.column_dimensions["A"].width = 84
    ws.sheet_view.showGridLines = False


def build_template(kind: str = "simple") -> bytes:
    """Devuelve el .xlsx de la plantilla pedida.

    :param kind: ``simple`` (una fila por punto) o ``campaigns`` (varias fechas).
    """
    if kind not in ("simple", "campaigns"):
        raise ValueError(
            f"Plantilla desconocida: {kind!r}. Usa 'simple' o 'campaigns'."
        )

    columnas = _columnas(kind)
    wb = Workbook()
    ws = wb.active
    ws.title = "Datos"

    cabecera = PatternFill("solid", fgColor=VERDE)
    ayuda = PatternFill("solid", fgColor=VERDE_SUAVE)
    borde = Border(*[Side(style="thin", color=LINEA)] * 4)

    for col, columna in enumerate(columnas, start=1):
        titulo = columna.titulo + (" *" if columna.obligatoria else "")
        c = ws.cell(1, col, titulo)
        c.fill = cabecera
        c.font = Font(color=PAPEL, bold=True, size=10)
        c.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        c.border = borde

        a = ws.cell(2, col, columna.ayuda)
        a.fill = ayuda
        a.font = Font(size=9, color=TINTA)
        a.alignment = Alignment(wrap_text=True, vertical="top")
        a.border = borde

        ws.column_dimensions[get_column_letter(col)].width = max(
            14, min(26, len(columna.titulo) + 3)
        )

    for fila_idx, valores in enumerate(_ejemplos(kind), start=3):
        for col, valor in enumerate(valores, start=1):
            celda = ws.cell(fila_idx, col, valor)
            celda.border = borde
            celda.font = Font(size=10, italic=True, color="5F7A6B")

    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 42
    ws.freeze_panes = "C3"

    _hoja_ayuda(wb, kind)
    wb.active = 1  # se abre en Datos, con LEEME a un clic

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def filename(kind: str = "simple") -> str:
    return (
        "plantilla_hydrochem_campanas.xlsx" if kind == "campaigns"
        else "plantilla_hydrochem.xlsx"
    )
