"""Sistemas de coordenadas y conversion UTM <-> WGS84.

Por que esta implementado aqui y no con ``pyproj``: en el equipo de destino la
instalacion de paquetes falla por verificacion de certificado, y sin
reproyeccion los datos en UTM -que es como vienen casi todos los levantamientos
en Peru- no se pueden situar en un mapa. La proyeccion transversa de Mercator
esta completamente especificada y su implementacion cabe en un archivo, asi que
la dependencia no compensa.

Las formulas son las series de Snyder (1987), *Map Projections: A Working
Manual*, USGS Professional Paper 1395, paginas 60-64, sobre el elipsoide WGS84.
Su error dentro de una zona UTM es milimetrico, muy por debajo de la precision
con la que se toma un punto de muestreo con GPS.

La verificacion no se apoya en valores recordados: el arco de meridiano de la
serie se compara contra su integral numerica, la ida y vuelta debe cerrar por
debajo del milimetro, y se comprueban las propiedades exactas de la proyeccion
(en el meridiano central el este vale 500 000 m justos, y el factor de escala
es 0,9996).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --- Elipsoide WGS84 (EPSG:7030) -------------------------------------------
A = 6378137.0  # semieje mayor, m
F = 1.0 / 298.257223563  # achatamiento
E2 = 2.0 * F - F * F  # primera excentricidad al cuadrado
E = math.sqrt(E2)
EP2 = E2 / (1.0 - E2)  # segunda excentricidad al cuadrado

# --- Parametros UTM --------------------------------------------------------
K0 = 0.9996
FALSE_EASTING = 500_000.0
FALSE_NORTHING_SOUTH = 10_000_000.0

WGS84_EPSG = 4326


@dataclass(frozen=True)
class CRS:
    """Un sistema de coordenadas de los que esta aplicacion maneja."""

    epsg: int
    name: str
    kind: str  # "geographic" | "utm"
    zone: int | None = None
    hemisphere: str | None = None  # "N" | "S"

    @property
    def is_geographic(self) -> bool:
        return self.kind == "geographic"

    @property
    def central_meridian(self) -> float:
        if self.zone is None:
            return 0.0
        return (self.zone - 1) * 6.0 - 180.0 + 3.0

    @property
    def units(self) -> str:
        return "grados" if self.is_geographic else "m"

    def to_dict(self) -> dict:
        return {
            "epsg": self.epsg, "name": self.name, "kind": self.kind,
            "zone": self.zone, "hemisphere": self.hemisphere, "units": self.units,
        }


WGS84 = CRS(WGS84_EPSG, "WGS 84 (grados decimales)", "geographic")


def utm_crs(zone: int, hemisphere: str) -> CRS:
    """CRS de una zona UTM sobre WGS84. Norte 326xx, sur 327xx."""
    if not 1 <= int(zone) <= 60:
        raise ValueError(f"Zona UTM fuera de rango: {zone!r}. Debe estar entre 1 y 60.")
    hemi = str(hemisphere).strip().upper()[:1]
    if hemi not in ("N", "S"):
        raise ValueError(f"Hemisferio no valido: {hemisphere!r}. Usa 'N' o 'S'.")
    base = 32600 if hemi == "N" else 32700
    return CRS(base + int(zone), f"WGS 84 / UTM zona {int(zone)}{hemi}", "utm",
               int(zone), hemi)


def parse_crs(spec) -> CRS:
    """Acepta ``4326``, ``"EPSG:32718"``, ``"UTM 18S"``, ``"18S"`` o un ``CRS``."""
    if isinstance(spec, CRS):
        return spec
    if spec is None:
        return WGS84
    if isinstance(spec, (int, float)):
        return _crs_from_epsg(int(spec))

    text = str(spec).strip().upper().replace("_", " ")
    if not text:
        return WGS84
    if text.startswith("EPSG:"):
        return _crs_from_epsg(int(text.split(":", 1)[1]))
    # El desplegable de la interfaz manda el codigo EPSG como texto ("32718"),
    # que es la forma en la que llega desde un <option value="...">.
    if text.isdigit():
        return _crs_from_epsg(int(text))
    if text in ("WGS84", "WGS 84", "GEOGRAFICAS", "GRADOS", "DD"):
        return WGS84
    text = text.replace("UTM", "").replace("ZONA", "").replace("ZONE", "").strip()
    if text and text[-1] in "NS":
        return utm_crs(int(text[:-1].strip()), text[-1])
    raise ValueError(
        f"No se reconoce el sistema de coordenadas {spec!r}. "
        "Usa por ejemplo 'EPSG:32718', 'UTM 18S' o 4326."
    )


def _crs_from_epsg(code: int) -> CRS:
    if code == WGS84_EPSG:
        return WGS84
    if 32601 <= code <= 32660:
        return utm_crs(code - 32600, "N")
    if 32701 <= code <= 32760:
        return utm_crs(code - 32700, "S")
    raise ValueError(
        f"EPSG:{code} no soportado. Se admiten 4326 y las zonas UTM WGS84 "
        "(EPSG 32601-32660 norte, 32701-32760 sur)."
    )


def utm_zone_from_lon(lon: float) -> int:
    """Zona UTM que le corresponde a una longitud."""
    return int(math.floor((float(lon) + 180.0) / 6.0) % 60) + 1


def suggest_crs(x, y) -> CRS:
    """Propone un sistema mirando el rango de los valores.

    Es una **sugerencia**, no una deteccion: solo el usuario sabe en que
    sistema tomo sus coordenadas. El notebook original decidia por su cuenta y
    ademas llevaba la zona escrita a mano en el codigo.
    """
    xs = pd.to_numeric(pd.Series(x), errors="coerce").dropna()
    ys = pd.to_numeric(pd.Series(y), errors="coerce").dropna()
    if xs.empty or ys.empty:
        return WGS84

    looks_geographic = xs.abs().max() <= 180.0 and ys.abs().max() <= 90.0
    if looks_geographic:
        return WGS84

    # Coordenadas proyectadas: el este de una zona UTM cae entre 100 km y 900 km
    # y el norte es positivo; por encima de 5 000 km suele ser hemisferio sur.
    hemi = "S" if ys.median() > 5_000_000 else "N"
    return utm_crs(18, hemi)  # zona por defecto; el usuario debe confirmarla


# --- Arco de meridiano ------------------------------------------------------


def meridian_arc(lat_rad):
    """Distancia sobre el meridiano desde el ecuador, en metros.

    Serie de Snyder (1987), ecuacion 3-21.
    """
    phi = np.asarray(lat_rad, dtype=float)
    return A * (
        (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256) * phi
        - (3 * E2 / 8 + 3 * E2**2 / 32 + 45 * E2**3 / 1024) * np.sin(2 * phi)
        + (15 * E2**2 / 256 + 45 * E2**3 / 1024) * np.sin(4 * phi)
        - (35 * E2**3 / 3072) * np.sin(6 * phi)
    )


def meridian_arc_numeric(lat_rad: float, n: int = 200_001) -> float:
    """El mismo arco por integracion numerica, para poder contrastar la serie.

    No se usa en produccion: existe para que las pruebas no tengan que confiar
    en la serie ni en ningun valor recordado.
    """
    phi = float(lat_rad)
    if phi == 0.0:
        return 0.0
    b = np.linspace(0.0, phi, n if n % 2 else n + 1)
    integrand = A * (1 - E2) / np.power(1 - E2 * np.sin(b) ** 2, 1.5)
    # Simpson
    h = (b[-1] - b[0]) / (len(b) - 1)
    return float(h / 3 * (integrand[0] + integrand[-1]
                          + 4 * integrand[1:-1:2].sum() + 2 * integrand[2:-1:2].sum()))


# --- Proyeccion -------------------------------------------------------------


def geographic_to_utm(lon, lat, crs: CRS):
    """WGS84 en grados -> este/norte en metros. Snyder, ecuaciones 8-9 a 8-11."""
    if crs.is_geographic:
        raise ValueError("El CRS de destino debe ser una zona UTM.")
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)

    phi = np.radians(lat)
    lam = np.radians(lon)
    lam0 = math.radians(crs.central_meridian)

    sin_phi, cos_phi, tan_phi = np.sin(phi), np.cos(phi), np.tan(phi)
    n = A / np.sqrt(1 - E2 * sin_phi**2)
    t = tan_phi**2
    c = EP2 * cos_phi**2
    a_ = (lam - lam0) * cos_phi
    m = meridian_arc(phi)

    east = FALSE_EASTING + K0 * n * (
        a_
        + (1 - t + c) * a_**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * EP2) * a_**5 / 120
    )
    north = K0 * (
        m
        + n * tan_phi * (
            a_**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * a_**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * EP2) * a_**6 / 720
        )
    )
    if crs.hemisphere == "S":
        north = north + FALSE_NORTHING_SOUTH
    return east, north


def utm_to_geographic(east, north, crs: CRS):
    """Este/norte en metros -> WGS84 en grados. Snyder, ecuaciones 8-17 a 8-25."""
    if crs.is_geographic:
        raise ValueError("El CRS de origen debe ser una zona UTM.")
    east = np.asarray(east, dtype=float)
    north = np.asarray(north, dtype=float)

    y = north - (FALSE_NORTHING_SOUTH if crs.hemisphere == "S" else 0.0)
    x = east - FALSE_EASTING

    m = y / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))

    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
        + (151 * e1**3 / 96) * np.sin(6 * mu)
        + (1097 * e1**4 / 512) * np.sin(8 * mu)
    )

    sin1, cos1, tan1 = np.sin(phi1), np.cos(phi1), np.tan(phi1)
    c1 = EP2 * cos1**2
    t1 = tan1**2
    n1 = A / np.sqrt(1 - E2 * sin1**2)
    r1 = A * (1 - E2) / np.power(1 - E2 * sin1**2, 1.5)
    d = x / (n1 * K0)

    phi = phi1 - (n1 * tan1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * EP2 - 3 * c1**2) * d**6 / 720
    )
    lam = math.radians(crs.central_meridian) + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * EP2 + 24 * t1**2) * d**5 / 120
    ) / cos1

    return np.degrees(lam), np.degrees(phi)


# --- Uso desde la tubería ---------------------------------------------------

LON_WGS84 = "lon_wgs84"
LAT_WGS84 = "lat_wgs84"


def add_wgs84_columns(
    df: pd.DataFrame,
    crs=None,
    x_col: str = "longitude",
    y_col: str = "latitude",
) -> pd.DataFrame:
    """Anade ``lon_wgs84`` / ``lat_wgs84`` a partir de las coordenadas de entrada.

    Todo lo que dibuja un mapa o exporta a Google Earth usa **solo** estas dos
    columnas. El notebook original mezclaba las crudas y las reproyectadas segun
    la celda, de modo que con entrada UTM el mapa y el KMZ no coincidian.
    """
    out = df.copy()
    if x_col not in out.columns or y_col not in out.columns:
        out[LON_WGS84] = np.nan
        out[LAT_WGS84] = np.nan
        return out

    x = pd.to_numeric(out[x_col], errors="coerce")
    y = pd.to_numeric(out[y_col], errors="coerce")
    resolved = parse_crs(crs) if crs is not None else suggest_crs(x, y)

    if resolved.is_geographic:
        out[LON_WGS84] = x
        out[LAT_WGS84] = y
        return out

    valid = x.notna() & y.notna()
    lon = pd.Series(np.nan, index=out.index, dtype=float)
    lat = pd.Series(np.nan, index=out.index, dtype=float)
    if valid.any():
        lo, la = utm_to_geographic(x[valid].to_numpy(), y[valid].to_numpy(), resolved)
        lon.loc[valid] = lo
        lat.loc[valid] = la
    out[LON_WGS84] = lon
    out[LAT_WGS84] = lat
    return out


def available_crs() -> list[dict]:
    """Lista para el desplegable de la interfaz: WGS84 y las zonas UTM utiles.

    Se incluyen todas las zonas, pero las de Peru (17S a 19S) van primero
    porque es donde se va a usar la herramienta.
    """
    out = [WGS84.to_dict()]
    for zone, hemi in ((18, "S"), (19, "S"), (17, "S")):
        out.append(utm_crs(zone, hemi).to_dict())
    for hemi in ("S", "N"):
        for zone in range(1, 61):
            crs = utm_crs(zone, hemi)
            if crs.epsg not in {c["epsg"] for c in out}:
                out.append(crs.to_dict())
    return out
