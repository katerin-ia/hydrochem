"""Lectura de archivos. Regresion del riesgo R1: ninguna fila se pierde."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from _fixture import FIXTURE
from hydrochem.io.column_mapping import ColumnMapping
from hydrochem.io.readers import (
    find_header_row,
    looks_like_description_row,
    read_table,
)

XLSM = Path(__file__).parent / "fixtures" / "PiperStiff-QW-2019.v9.xlsm"

#: Cabeceras de la plantilla que genera el notebook (celda 4).
TEMPLATE_HEADERS = [
    "Group", "Sample_ID", "Sample_Name", "Latitude", "Longitude",
    "pH", "Temp_C", "DO_mgL", "TDS_mgL",
    "Ca_mgL", "Mg_mgL", "Na_mgL", "K_mgL",
    "HCO3_mgL", "CO3_mgL", "SO4_mgL", "Cl_mgL", "F_mgL", "NO3_mgL",
]
TEMPLATE_DESCRIPTIONS = [
    "Group / site name", "Numeric sample ID", "Sample label / name",
    "Latitude - decimal degrees", "Longitude - decimal degrees",
    "pH (s.u.)", "Temperature (C)", "Dissolved Oxygen (mg/L)", "TDS (mg/L)",
    "Calcium (mg/L)", "Magnesium (mg/L)", "Sodium (mg/L)", "Potassium (mg/L)",
    "Bicarbonate (mg/L)", "Carbonate (mg/L)", "Sulfate (mg/L)",
    "Chloride (mg/L)", "Fluoride (mg/L)", "Nitrate (mg/L)",
]


def _template_rows(n: int) -> list[list]:
    """n filas de datos plausibles, la primera claramente identificable."""
    return [
        ["Grupo A", i + 1, f"Muestra {i + 1}", 36.5 + i * 0.01, -117.2 - i * 0.01,
         7.8, 18.5, 8.2, 320, 45.0, 8.5, 55.0, 4.2, 152.0, 0.0, 28.0, 35.0, 0.35, 2.1]
        for i in range(n)
    ]


def _write_template(path: Path, n_data_rows: int, with_description: bool) -> None:
    rows = [TEMPLATE_HEADERS]
    if with_description:
        rows.append(TEMPLATE_DESCRIPTIONS)
    rows.extend(_template_rows(n_data_rows))
    pd.DataFrame(rows).to_excel(path, index=False, header=False)


# -- R1: la regresion principal ---------------------------------------------


def test_template_with_description_row_keeps_every_data_row(tmp_path=None):
    """El notebook hacia skiprows=[1,2] y se comia la primera fila de datos."""
    tmp = Path(tmp_path or Path(__file__).parent / "_tmp")
    tmp.mkdir(exist_ok=True)
    path = tmp / "plantilla_con_descripcion.xlsx"
    _write_template(path, n_data_rows=5, with_description=True)

    res = read_table(path)
    assert res.description_row_dropped, "la fila de descripciones si debe descartarse"
    assert res.n_rows == 5, f"se perdieron filas: {res.n_rows} de 5"
    names = res.data[res.mapping.mapping["station_code"]].tolist()
    assert names[0] == "Muestra 1", "la PRIMERA fila de datos debe sobrevivir"
    assert names[-1] == "Muestra 5"
    path.unlink()


def test_template_without_description_row_is_read_whole(tmp_path=None):
    tmp = Path(tmp_path or Path(__file__).parent / "_tmp")
    tmp.mkdir(exist_ok=True)
    path = tmp / "plantilla_plana.xlsx"
    _write_template(path, n_data_rows=5, with_description=False)

    res = read_table(path)
    assert not res.description_row_dropped
    assert res.n_rows == 5
    assert res.data[res.mapping.mapping["station_code"]].iloc[0] == "Muestra 1"
    path.unlink()


def test_single_data_row_is_not_swallowed(tmp_path=None):
    """Caso extremo: con una sola muestra, el bug del notebook la borraba entera."""
    tmp = Path(tmp_path or Path(__file__).parent / "_tmp")
    tmp.mkdir(exist_ok=True)
    path = tmp / "una_muestra.xlsx"
    _write_template(path, n_data_rows=1, with_description=True)

    res = read_table(path)
    assert res.n_rows == 1
    path.unlink()


# -- el libro Excel original, sin trasvase manual ---------------------------


def test_original_workbook_loads_all_ninety_sites():
    """El objetivo declarado: abrir el .xlsm tal cual y que no falte nada."""
    res = read_table(XLSM)
    assert res.n_rows == 90, f"se leyeron {res.n_rows} sitios, deberian ser 90"
    codes = res.data[res.mapping.mapping["station_code"]].tolist()
    assert codes[0] == "Amargosa Tracer Well 2", "el sitio que el notebook perdia"
    assert codes[-1] == "WW-C-1"
    assert len(set(codes)) == 90


def test_original_workbook_picks_the_data_sheet_among_three():
    res = read_table(XLSM)
    assert res.sheet == "DATA"
    assert res.header_row == 13, "fila 14 del Excel, base 0"


def test_original_workbook_maps_nine_ions_automatically():
    """Las cabeceras vienen con subindices Unicode: Ca2+, HCO3-, SO42-..."""
    res = read_table(XLSM)
    assert set(res.mapping.mapped_ions) == {
        "Ca_mgL", "Mg_mgL", "Na_mgL", "K_mgL",
        "HCO3_mgL", "CO3_mgL", "SO4_mgL", "Cl_mgL", "F_mgL",
    }
    assert "NO3_mgL" not in res.mapping.mapped_ions, "NO3 no se midio; no debe aparecer"
    assert res.mapping.missing_required == []


def test_original_workbook_has_no_date_column():
    """Comprobacion explicita: el material de partida no tiene dimension temporal."""
    res = read_table(XLSM)
    assert not res.mapping.has_temporal
    assert "campaign" not in res.mapping.mapping


def test_duplicate_headers_are_disambiguated():
    """La hoja DATA repite los nombres de ion en mg/L y en meq/L."""
    res = read_table(XLSM)
    assert len(set(res.data.columns)) == len(res.data.columns)
    assert any("__2" in c for c in res.data.columns)
    # El mapeo se queda con la PRIMERA aparicion, que es la de mg/L.
    ca_col = res.mapping.mapping["Ca_mgL"]
    assert "__2" not in ca_col
    assert float(res.data[ca_col].iloc[0]) == 44.0, "mg/L, no meq/L"


def test_reader_explains_what_it_did():
    res = read_table(XLSM)
    joined = " ".join(res.notes)
    assert "DATA" in joined
    assert "14" in joined


# -- deteccion de cabecera y de fila de descripciones -----------------------


def test_find_header_row_on_a_plain_table():
    raw = pd.DataFrame([TEMPLATE_HEADERS] + _template_rows(3))
    assert find_header_row(raw) == 0


def test_find_header_row_skips_leading_junk():
    junk = [["Informe de calidad de agua"] + [None] * 18, [None] * 19]
    raw = pd.DataFrame(junk + [TEMPLATE_HEADERS] + _template_rows(3))
    assert find_header_row(raw) == 2


def test_description_row_is_recognised_by_content():
    row = pd.Series(dict(zip(TEMPLATE_HEADERS, TEMPLATE_DESCRIPTIONS)))
    numeric = ["Ca_mgL", "Mg_mgL", "TDS_mgL"]
    assert looks_like_description_row(row, numeric)


def test_real_data_row_is_never_mistaken_for_a_description():
    row = pd.Series(dict(zip(TEMPLATE_HEADERS, _template_rows(1)[0])))
    numeric = ["Ca_mgL", "Mg_mgL", "TDS_mgL"]
    assert not looks_like_description_row(row, numeric)


def test_censored_values_do_not_look_like_a_description():
    """Una fila cuyo unico dato sea '<0,05' sigue siendo datos, no descripcion."""
    values = dict(zip(TEMPLATE_HEADERS, _template_rows(1)[0]))
    values["Ca_mgL"] = "<0,05"
    values["Mg_mgL"] = "<0.1"
    row = pd.Series(values)
    assert not looks_like_description_row(row, ["Ca_mgL", "Mg_mgL"])


# -- CSV --------------------------------------------------------------------


def test_reads_the_csv_fixture():
    res = read_table(FIXTURE)
    assert res.n_rows == 90
    assert res.mapping.missing_required == []


def test_reads_semicolon_csv(tmp_path=None):
    tmp = Path(tmp_path or Path(__file__).parent / "_tmp")
    tmp.mkdir(exist_ok=True)
    path = tmp / "punto_y_coma.csv"
    path.write_text(
        "Estacion;Calcio (mg/L);Cloruros (mg/L)\nP-01;45,5;12,0\nP-02;38,2;9,5\n",
        encoding="utf-8",
    )
    res = read_table(path)
    assert res.n_rows == 2
    assert "Ca_mgL" in res.mapping.mapping
    path.unlink()


def test_unsupported_format_is_rejected_clearly():
    try:
        read_table(Path("datos.docx"))
    except ValueError as exc:
        assert "no soportado" in str(exc).lower()
    else:
        raise AssertionError("deberia haber lanzado ValueError")


# -- mapeo manual -----------------------------------------------------------


def test_caller_can_override_the_mapping():
    manual = ColumnMapping.suggest(pd.read_csv(FIXTURE, nrows=0).columns)
    manual.set("group", None)
    res = read_table(FIXTURE, mapping=manual)
    assert "group" not in res.mapping.mapping
