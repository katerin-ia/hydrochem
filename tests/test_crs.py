"""Conversion UTM <-> WGS84.

La verificacion no usa ningun valor recordado. Se apoya en:
  - propiedades exactas de la proyeccion (en el meridiano central el este vale
    500 000 m justos; en el ecuador el norte vale 0);
  - el contraste de la serie del arco de meridiano contra su integral numerica;
  - el cierre de la ida y vuelta por debajo del milimetro.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from _fixture import load_amargosa
from hydrochem.geo.crs import (
    A,
    FALSE_EASTING,
    FALSE_NORTHING_SOUTH,
    K0,
    LAT_WGS84,
    LON_WGS84,
    WGS84,
    add_wgs84_columns,
    available_crs,
    geographic_to_utm,
    meridian_arc,
    meridian_arc_numeric,
    parse_crs,
    suggest_crs,
    utm_crs,
    utm_to_geographic,
    utm_zone_from_lon,
)

# -- identificacion de sistemas ---------------------------------------------


def test_epsg_codes_of_utm_zones():
    assert utm_crs(18, "S").epsg == 32718, "UTM 18S sobre WGS84"
    assert utm_crs(18, "N").epsg == 32618
    assert utm_crs(1, "N").epsg == 32601
    assert utm_crs(60, "S").epsg == 32760


def test_parse_crs_accepts_the_usual_spellings():
    for spec in ("EPSG:32718", "UTM 18S", "18S", "utm zona 18 s".upper().replace(" ", "")):
        crs = parse_crs(spec)
        assert crs.epsg == 32718, spec
    assert parse_crs(4326) == WGS84
    assert parse_crs(None) == WGS84
    assert parse_crs("WGS84") == WGS84


def test_parse_crs_accepts_an_epsg_code_as_text():
    """El desplegable de la interfaz manda el codigo como cadena."""
    assert parse_crs("32718").epsg == 32718
    assert parse_crs("4326") == WGS84
    assert parse_crs("") == WGS84, "el valor vacio significa deteccion automatica"


def test_parse_crs_rejects_nonsense_clearly():
    for spec in ("EPSG:1234", "UTM 99S", "marte"):
        try:
            parse_crs(spec)
        except ValueError as exc:
            assert len(str(exc)) > 20, spec
        else:
            raise AssertionError(f"deberia haber fallado con {spec!r}")


def test_central_meridian_of_each_zone():
    assert utm_crs(18, "S").central_meridian == -75.0, "zona 18: meridiano -75"
    assert utm_crs(19, "S").central_meridian == -69.0
    assert utm_crs(31, "N").central_meridian == 3.0
    assert utm_crs(1, "N").central_meridian == -177.0


def test_zone_from_longitude():
    assert utm_zone_from_lon(-77.0) == 18, "Lima cae en la zona 18"
    assert utm_zone_from_lon(-69.5) == 19
    assert utm_zone_from_lon(-116.0) == 11, "el dataset de Amargosa"
    assert utm_zone_from_lon(0.0) == 31
    assert utm_zone_from_lon(-180.0) == 1
    assert utm_zone_from_lon(179.9) == 60


# -- arco de meridiano ------------------------------------------------------


def test_meridian_series_matches_numeric_integration():
    """Contraste independiente: la serie frente a la integral del propio arco."""
    for grados in (0, 5, 12, 30, 45, 60, 84):
        phi = math.radians(grados)
        serie = float(meridian_arc(phi))
        integral = meridian_arc_numeric(phi)
        assert abs(serie - integral) < 0.001, (
            f"{grados} grados: serie {serie:.4f} vs integral {integral:.4f}"
        )


def test_meridian_arc_is_zero_at_the_equator():
    assert float(meridian_arc(0.0)) == 0.0


def test_quarter_meridian_is_about_ten_thousand_kilometres():
    """El cuadrante del meridiano define el metro historico: 10 000 km."""
    cuadrante = meridian_arc_numeric(math.pi / 2)
    assert 10_001_000 < cuadrante < 10_002_500, cuadrante


# -- propiedades exactas de la proyeccion -----------------------------------


def test_easting_is_exactly_five_hundred_thousand_on_the_central_meridian():
    crs = utm_crs(18, "S")
    e, _ = geographic_to_utm(crs.central_meridian, -12.0, crs)
    assert abs(float(e) - FALSE_EASTING) < 1e-6


def test_northing_at_the_equator_on_the_central_meridian():
    norte = utm_crs(18, "N")
    _, n = geographic_to_utm(norte.central_meridian, 0.0, norte)
    assert abs(float(n)) < 1e-6

    sur = utm_crs(18, "S")
    _, n2 = geographic_to_utm(sur.central_meridian, 0.0, sur)
    assert abs(float(n2) - FALSE_NORTHING_SOUTH) < 1e-6


def test_northing_on_the_central_meridian_equals_k0_times_the_arc():
    """Sobre el meridiano central la proyeccion se reduce al arco por k0."""
    crs = utm_crs(18, "N")
    for lat in (5.0, 20.0, 45.0):
        _, n = geographic_to_utm(crs.central_meridian, lat, crs)
        esperado = K0 * meridian_arc_numeric(math.radians(lat))
        assert abs(float(n) - esperado) < 0.002, lat


def test_south_hemisphere_uses_the_false_northing():
    crs = utm_crs(18, "S")
    _, n = geographic_to_utm(-75.0, -12.0, crs)
    assert 8_000_000 < float(n) < 9_000_000, float(n)


def test_easting_grows_eastwards():
    crs = utm_crs(18, "S")
    e1, _ = geographic_to_utm(-77.0, -12.0, crs)
    e2, _ = geographic_to_utm(-76.0, -12.0, crs)
    assert float(e2) > float(e1)


# -- ida y vuelta -----------------------------------------------------------


#: Metros que mide un grado de latitud, aproximadamente. Sirve para expresar el
#: error de la ida y vuelta en milimetros sobre el terreno, que es la unidad en
#: la que la serie de Snyder declara su precision (del orden del milimetro).
METROS_POR_GRADO = 111_320.0


def _error_mm(delta_grados: float, lat: float = 0.0) -> float:
    """Error angular convertido a milimetros sobre el terreno."""
    return abs(delta_grados) * METROS_POR_GRADO * 1000.0


def test_round_trip_closes_below_a_millimetre():
    casos = [
        (-77.0428, -12.0464, 18, "S"),   # Lima
        (-76.9350, -12.2100, 18, "S"),   # Villa El Salvador
        (-71.5375, -16.4090, 19, "S"),   # Arequipa
        (-116.0373, 36.5898, 11, "N"),   # Amargosa
        (2.3522, 48.8566, 31, "N"),      # Paris
        (-75.0, 0.0, 18, "N"),           # ecuador, meridiano central
        (-70.0, -55.0, 19, "S"),         # latitud alta sur
    ]
    for lon, lat, zona, hemi in casos:
        crs = utm_crs(zona, hemi)
        e, n = geographic_to_utm(lon, lat, crs)
        lon2, lat2 = utm_to_geographic(e, n, crs)
        err_lon = _error_mm(float(lon2) - lon)
        err_lat = _error_mm(float(lat2) - lat)
        assert err_lon < 1.0, f"{lon},{lat}: {err_lon:.3f} mm en longitud"
        assert err_lat < 1.0, f"{lon},{lat}: {err_lat:.3f} mm en latitud"


def test_round_trip_is_vectorised():
    crs = utm_crs(18, "S")
    lon = np.array([-77.0, -76.5, -75.0, -74.2])
    lat = np.array([-12.0, -11.0, -9.5, -8.0])
    e, n = geographic_to_utm(lon, lat, crs)
    lon2, lat2 = utm_to_geographic(e, n, crs)
    tol = 1.0 / (METROS_POR_GRADO * 1000.0)  # 1 mm expresado en grados
    assert np.allclose(lon, lon2, atol=tol)
    assert np.allclose(lat, lat2, atol=tol)


def test_round_trip_over_the_whole_real_dataset():
    df = load_amargosa()
    crs = utm_crs(11, "N")
    e, n = geographic_to_utm(df["Longitude"].to_numpy(), df["Latitude"].to_numpy(), crs)
    lon2, lat2 = utm_to_geographic(e, n, crs)
    tol = 1.0 / (METROS_POR_GRADO * 1000.0)
    assert np.allclose(df["Longitude"].to_numpy(), lon2, atol=tol)
    assert np.allclose(df["Latitude"].to_numpy(), lat2, atol=tol)


def test_scale_factor_on_the_central_meridian_is_k0():
    """Un grado de latitud proyectado sobre el meridiano central mide k0 veces
    el arco real. Es la definicion de la proyeccion UTM."""
    crs = utm_crs(18, "N")
    _, n1 = geographic_to_utm(crs.central_meridian, 10.0, crs)
    _, n2 = geographic_to_utm(crs.central_meridian, 11.0, crs)
    arco = (meridian_arc_numeric(math.radians(11.0))
            - meridian_arc_numeric(math.radians(10.0)))
    assert abs((float(n2) - float(n1)) / arco - K0) < 1e-9


# -- sugerencia -------------------------------------------------------------


def test_suggests_geographic_for_degrees():
    df = load_amargosa()
    assert suggest_crs(df["Longitude"], df["Latitude"]).is_geographic


def test_suggests_utm_for_projected_values():
    crs = suggest_crs([277_000, 280_000], [8_668_000, 8_670_000])
    assert not crs.is_geographic
    assert crs.hemisphere == "S", "un norte de 8,6 millones solo cabe en el sur"


def test_suggests_north_for_small_northings():
    crs = suggest_crs([500_000, 510_000], [2_000_000, 2_100_000])
    assert crs.hemisphere == "N"


def test_suggestion_of_empty_data_falls_back_to_wgs84():
    assert suggest_crs([], []).is_geographic


# -- integracion con la tubería ---------------------------------------------


def test_add_wgs84_columns_copies_geographic_input():
    out = add_wgs84_columns(
        load_amargosa().rename(columns={"Longitude": "longitude", "Latitude": "latitude"})
    )
    assert np.allclose(out[LON_WGS84], out["longitude"])
    assert np.allclose(out[LAT_WGS84], out["latitude"])


def test_add_wgs84_columns_reprojects_utm_input():
    """El caso peruano: un Excel con este/norte en UTM 18S."""
    crs = utm_crs(18, "S")
    lon = np.array([-77.0428, -76.9350, -76.8000])
    lat = np.array([-12.0464, -12.2100, -12.3000])
    e, n = geographic_to_utm(lon, lat, crs)
    df = pd.DataFrame({"longitude": e, "latitude": n})

    out = add_wgs84_columns(df, crs="UTM 18S")
    assert np.allclose(out[LON_WGS84], lon, atol=1e-8)
    assert np.allclose(out[LAT_WGS84], lat, atol=1e-8)


def test_add_wgs84_columns_without_coordinates_gives_nan():
    out = add_wgs84_columns(pd.DataFrame({"station_code": ["A", "B"]}))
    assert out[LON_WGS84].isna().all()
    assert out[LAT_WGS84].isna().all()


def test_rows_without_coordinates_stay_nan():
    df = pd.DataFrame({"longitude": [277_000.0, np.nan], "latitude": [8_668_000.0, np.nan]})
    out = add_wgs84_columns(df, crs="UTM 18S")
    assert out[LON_WGS84].notna().iloc[0]
    assert out[LON_WGS84].isna().iloc[1]


def test_available_crs_puts_peru_first():
    lista = available_crs()
    assert lista[0]["epsg"] == 4326
    primeras = [c["epsg"] for c in lista[1:4]]
    assert 32718 in primeras, "UTM 18S debe estar entre las primeras"
    assert len(lista) == 1 + 120, "WGS84 mas las 60 zonas de cada hemisferio"
    assert len({c["epsg"] for c in lista}) == len(lista), "sin repetidos"


def test_worst_round_trip_error_is_reported_in_millimetres():
    """Deja constancia del error real, no solo de que pase el umbral."""
    casos = [
        (-77.0428, -12.0464, 18, "S"), (2.3522, 48.8566, 31, "N"),
        (-116.0373, 36.5898, 11, "N"), (-70.0, -55.0, 19, "S"),
        (-71.5375, -16.4090, 19, "S"),
    ]
    peor = 0.0
    for lon, lat, zona, hemi in casos:
        crs = utm_crs(zona, hemi)
        e, n = geographic_to_utm(lon, lat, crs)
        lon2, lat2 = utm_to_geographic(e, n, crs)
        peor = max(peor, _error_mm(float(lon2) - lon), _error_mm(float(lat2) - lat))
    assert peor < 1.0, f"peor error de ida y vuelta: {peor:.4f} mm"
