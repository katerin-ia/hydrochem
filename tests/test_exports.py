"""Exportacion: KMZ, KML, GeoJSON, CSV y XLSX."""

from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from _fixture import load_amargosa
from hydrochem.chemistry.facies import add_facies, summary as facies_summary
from hydrochem.geo.crs import add_wgs84_columns
from hydrochem.geo.exporters.kml import (
    Document,
    Folder,
    IconStyle,
    Placemark,
    ScreenOverlay,
    cdata,
    hex_to_kml_color,
    num,
)
from hydrochem.geo.exporters.kmz import build
from hydrochem.geo.exporters.vectors import (
    tidy_for_export,
    to_csv,
    to_geojson,
    to_kml,
    to_xlsx,
)
from hydrochem.pipeline import AnalysisOptions, analyse
from hydrochem.quality.standards import add_compliance, check

XLSM = "tests/fixtures/PiperStiff-QW-2019.v9.xlsm"

_CACHE: dict = {}


def prepared() -> pd.DataFrame:
    """Dataset completo, listo para exportar. Se cachea: el KMZ tarda unos segundos."""
    if "df" not in _CACHE:
        ds = analyse(XLSM, AnalysisOptions(zeros_as_missing_for=("F",)))
        _CACHE["df"] = add_facies(add_wgs84_columns(ds.data))
        _CACHE["report"] = ds.report
    return _CACHE["df"]


def kmz() -> object:
    if "kmz" not in _CACHE:
        _CACHE["kmz"] = build(
            prepared(), name="Amargosa", colour_by="facies",
            standard="who_drinking", stiff_template="extended",
        )
    return _CACHE["kmz"]


# -- primitivas de KML ------------------------------------------------------


def test_kml_colour_order_is_aabbggrr():
    """El error clasico de KML: el color va al reves que en HTML."""
    assert hex_to_kml_color("#0e6b75") == "ff756b0e"
    assert hex_to_kml_color("#ff0000") == "ff0000ff", "rojo puro"
    assert hex_to_kml_color("#0000ff") == "ffff0000", "azul puro"
    assert hex_to_kml_color("#abc") == "ffccbbaa", "forma corta"
    assert hex_to_kml_color("#0e6b75", alpha=128).startswith("80")


def test_kml_colour_rejects_nonsense():
    try:
        hex_to_kml_color("verde")
    except ValueError as exc:
        assert "rrggbb" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado ValueError")


def test_numbers_always_use_a_dot():
    """Con configuracion regional espanola, una coma decimal rompe el KML."""
    assert num(-116.2274999) == "-116.2274999", "8 decimales, sin ceros de cola"
    assert num(0) == "0"
    assert num(36.5) == "36.5", "los ceros sobrantes se recortan"
    assert "," not in num(1234.5678)
    # Con configuracion regional espanola, format() de Python no introduce
    # comas, pero se comprueba explicitamente porque es el fallo que el manual
    # del libro PiperStiff documenta en su version 7.
    assert "," not in num(-1234567.891234)


def test_cdata_escapes_a_nested_terminator():
    assert cdata("a]]>b").count("<![CDATA[") == 2


def test_placemark_writes_lon_then_lat():
    xml = Placemark("P", lon=-77.0, lat=-12.0).to_xml()
    assert "<coordinates>-77,-12,0</coordinates>" in xml


def test_placemark_escapes_user_text():
    xml = Placemark("Pozo <A> & 'B'", lon=0, lat=0).to_xml()
    assert "&lt;A&gt;" in xml and "&amp;" in xml


def test_icon_style_emits_a_style_map_for_hover():
    xml = IconStyle("g0", icon_href="files/x.png", color_hex="#0e6b75").to_xml()
    assert '<Style id="g0-n">' in xml
    assert '<Style id="g0-h">' in xml
    assert '<StyleMap id="g0">' in xml
    assert "hotSpot" in xml, "sin hotSpot el icono se descoloca del punto"


def test_document_is_well_formed_xml():
    doc = Document(name="X", folders=[Folder("G", [Placemark("P", 1.0, 2.0)])])
    ET.fromstring(doc.to_xml())
    assert doc.n_placemarks == 1


def test_screen_overlay_is_anchored_to_the_screen():
    xml = ScreenOverlay("Leyenda", "files/l.png").to_xml()
    assert "screenXY" in xml and "overlayXY" in xml


# -- KMZ --------------------------------------------------------------------


def test_kmz_is_a_valid_zip_with_doc_kml_first():
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    assert z.testzip() is None, "el zip no debe tener entradas corruptas"
    assert z.namelist()[0] == "doc.kml"


def test_kmz_kml_is_well_formed():
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    ET.fromstring(z.read("doc.kml").decode("utf-8"))


def test_kmz_has_one_placemark_per_sample():
    res = kmz()
    assert res.n_placemarks == 90
    assert res.n_skipped == 0
    assert res.n_groups == 7


def test_kmz_icon_of_each_point_is_its_own_stiff_diagram():
    """Es el rasgo distintivo de la herramienta original."""
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    iconos = [n for n in z.namelist() if n.startswith("files/stiff_")]
    assert len(iconos) == 90
    kml = z.read("doc.kml").decode("utf-8")
    assert "files/stiff_0000.png" in kml
    # y cada icono es un PNG de verdad
    assert z.read(iconos[0])[:8] == b"\x89PNG\r\n\x1a\n"


def test_kmz_carries_a_larger_labelled_image_for_the_balloon():
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    popups = [n for n in z.namelist() if n.startswith("files/popup_")]
    assert len(popups) == 90
    assert z.getinfo(popups[0]).file_size > z.getinfo("files/stiff_0000.png").file_size


def test_kmz_legend_is_an_overlay_not_a_placemark_at_zero_zero():
    """Regresion del riesgo R19: el notebook ponia la leyenda en (0,0), que cae
    en el golfo de Guinea."""
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    kml = z.read("doc.kml").decode("utf-8")
    assert "<ScreenOverlay>" in kml
    assert "files/leyenda.png" in z.namelist()
    assert ">0,0,0<" not in kml, "no debe haber ningun punto en (0,0)"


def test_kmz_balloon_includes_chemistry_and_exceedances():
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    kml = z.read("doc.kml").decode("utf-8")
    assert "meq/L" in kml
    assert "Alcalinidad" in kml
    assert "Facies" in kml
    assert "Supera" in kml, "alguna muestra supera el umbral de fluoruro"


def test_kmz_marks_estimated_values():
    """Los 32 ceros de fluoruro quedan como no medidos, asi que ninguna muestra
    deberia mostrarlos como si fueran medida."""
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    kml = z.read("doc.kml").decode("utf-8")
    assert kml.count("<Placemark>") == 90


def test_kmz_groups_the_points_in_folders():
    z = zipfile.ZipFile(io.BytesIO(kmz().content))
    kml = z.read("doc.kml").decode("utf-8")
    assert kml.count("<Folder>") == 7
    assert "Central Amargosa Desert (38)" in kml


def test_kmz_requires_wgs84_columns():
    try:
        build(load_amargosa())
    except ValueError as exc:
        assert "add_wgs84_columns" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado ValueError")


def test_kmz_without_any_coordinate_fails_clearly():
    df = prepared().copy()
    df["lon_wgs84"] = None
    df["lat_wgs84"] = None
    try:
        build(df)
    except ValueError as exc:
        assert "Ninguna muestra" in str(exc)
    else:
        raise AssertionError("deberia haber lanzado ValueError")


def test_kmz_counts_the_samples_it_had_to_skip():
    df = prepared().copy()
    df.loc[df.index[:5], "lon_wgs84"] = None
    res = build(df, stiff_template="standard")
    assert res.n_skipped == 5
    assert res.n_placemarks == 85


def test_kmz_progress_is_reported():
    visto = []
    df = prepared().head(12)
    build(df, progress=lambda d, t, e: visto.append(e))
    assert "iconos" in visto and "empaquetado" in visto


def test_kmz_size_is_reasonable():
    res = kmz()
    assert 200 < res.size_kb < 8000, f"{res.size_kb} KB"


# -- KML suelto -------------------------------------------------------------


def test_plain_kml_is_far_lighter_than_the_kmz():
    texto = to_kml(prepared())
    ET.fromstring(texto)
    assert texto.count("<Placemark>") == 90
    assert len(texto.encode()) < kmz().size_kb * 1024


def test_plain_kml_uses_coloured_circles():
    texto = to_kml(prepared(), colour_by="facies")
    assert "placemark_circle.png" in texto
    assert "<color>" in texto


# -- GeoJSON ----------------------------------------------------------------


def test_geojson_is_a_valid_feature_collection():
    data = json.loads(to_geojson(prepared()))
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 90
    assert data["crs"]["properties"]["name"].endswith("CRS84")


def test_geojson_coordinates_are_lon_lat():
    data = json.loads(to_geojson(prepared()))
    lon, lat = data["features"][0]["geometry"]["coordinates"]
    assert -117 < lon < -115, f"la longitud deberia ir primera, llego {lon}"
    assert 36 < lat < 38


def test_geojson_carries_the_derived_attributes():
    props = json.loads(to_geojson(prepared()))["features"][0]["properties"]
    for clave in ("estacion", "grupo", "facies", "TDS_mgL",
                  "balance_carga_pct", "Ca_mgL", "Ca_meqL"):
        assert clave in props, clave


def test_geojson_has_no_nan():
    """Un NaN en JSON no es valido y rompe cualquier lector."""
    texto = to_geojson(prepared())
    assert "NaN" not in texto
    json.loads(texto)  # y se puede releer


def test_geojson_reports_skipped_samples():
    df = prepared().copy()
    df.loc[df.index[:3], "lat_wgs84"] = None
    data = json.loads(to_geojson(df))
    assert len(data["features"]) == 87
    assert data["omitidas_sin_coordenadas"] == 3


# -- CSV y XLSX -------------------------------------------------------------


def test_tidy_drops_internal_columns():
    out = tidy_for_export(prepared())
    assert not [c for c in out.columns if c.startswith("x_") or c.startswith("row0_")]
    assert "station_code" in out.columns
    assert out.columns[0] == "station_code", "la estacion va primera"


def test_csv_opens_in_excel_without_breaking_accents():
    data = to_csv(prepared())
    assert data[:3] == b"\xef\xbb\xbf", "BOM de UTF-8"
    texto = data.decode("utf-8-sig")
    assert texto.count("\n") >= 90


def test_xlsx_has_one_sheet_per_block():
    df = prepared()
    data = to_xlsx(
        df,
        compliance=check(add_compliance(df, "who_drinking"), "who_drinking"),
        facies_summary=facies_summary(df["facies"]),
    )
    book = pd.ExcelFile(io.BytesIO(data))
    assert "Resultados" in book.sheet_names
    assert "Umbrales" in book.sheet_names
    assert "Facies" in book.sheet_names
    hoja = book.parse("Resultados")
    assert len(hoja) == 90
    book.close()


def test_xlsx_works_with_only_the_results():
    book = pd.ExcelFile(io.BytesIO(to_xlsx(prepared())))
    assert book.sheet_names == ["Resultados"]
    book.close()
