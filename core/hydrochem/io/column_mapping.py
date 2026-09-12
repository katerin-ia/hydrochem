"""Esquema canonico y mapeo configurable de columnas de entrada.

Resuelve el riesgo **R8**. El notebook exigia 17 nombres de columna exactos, de
modo que el usuario tuvo que trasvasar a mano la hoja ``DATA`` del libro
PiperStiff a la plantilla del notebook, perdiendo por el camino pH, temperatura,
oxigeno disuelto y NO3 (que no existian en el origen) y una fila entera por el
riesgo R1.

Aqui la entrada se describe una sola vez, en el esquema canonico, y cada archivo
se conecta a el mediante un mapeo que se puede proponer automaticamente y
corregir a mano. La hoja ``DATA`` del libro Excel se reconoce sin intervencion.

Dimension temporal
------------------
``sampled_at`` y ``campaign`` forman parte del esquema desde el primer dia y son
**opcionales**. Hoy ningun dato los trae —la auditoria verifico que no hay una
sola celda de fecha en el material de partida— pero su presencia en el esquema
es lo que permite que la aplicacion admita varias campanas mas adelante sin
rehacer el modelo. No se inventan fechas: si no vienen, quedan nulas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from ..constants import ALL_IONS, IONS


class FieldKind(str, Enum):
    IDENTITY = "identity"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    PHYSCHEM = "physchem"
    ION = "ion"

    @property
    def label_es(self) -> str:
        return {
            "identity": "Identificacion",
            "temporal": "Tiempo",
            "spatial": "Ubicacion",
            "physchem": "Fisico-quimica",
            "ion": "Iones mayoritarios",
        }[self.value]


@dataclass(frozen=True)
class FieldSpec:
    """Un campo del esquema canonico."""

    key: str
    label_es: str
    kind: FieldKind
    unit: str | None = None
    required: bool = False
    aliases: tuple[str, ...] = ()

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.key, self.label_es) + self.aliases


def _ion_field(ion: str, *aliases: str) -> FieldSpec:
    spec = IONS[ion]
    return FieldSpec(
        key=f"{ion}_mgL",
        label_es=spec.name_es.capitalize(),
        kind=FieldKind.ION,
        unit="mg/L",
        # El plural castellano es habitual en informes de laboratorio
        # ("Bicarbonatos", "Sulfatos"), asi que se genera siempre.
        aliases=(
            ion, spec.label, f"{ion}_mg_l", f"{ion} mg/l",
            spec.name_es, f"{spec.name_es}s",
        ) + aliases,
    )


SCHEMA: tuple[FieldSpec, ...] = (
    # -- identificacion -----------------------------------------------------
    FieldSpec(
        "station_code", "Codigo de estacion", FieldKind.IDENTITY, required=True,
        aliases=("site", "sitio", "site_id", "station", "estacion", "punto",
                 "sample_name", "nombre", "codigo", "id", "well", "pozo"),
    ),
    FieldSpec(
        "sample_id", "Identificador de muestra", FieldKind.IDENTITY,
        aliases=("sample", "muestra", "lab_id", "id_muestra"),
    ),
    FieldSpec(
        "group", "Grupo", FieldKind.IDENTITY,
        aliases=("grupo", "data group", "unidad", "acuifero", "aquifer", "zona", "sector"),
    ),
    # -- tiempo (opcional; hoy ningun dato lo trae) -------------------------
    FieldSpec(
        "sampled_at", "Fecha de muestreo", FieldKind.TEMPORAL,
        aliases=("fecha", "date", "sample_date", "sampled_date", "fecha_muestreo",
                 "sampling_date", "datetime", "fecha y hora"),
    ),
    FieldSpec(
        "campaign", "Campana", FieldKind.TEMPORAL,
        aliases=("campana", "campaign", "monitoreo", "survey", "periodo", "evento"),
    ),
    # -- ubicacion ----------------------------------------------------------
    FieldSpec(
        "longitude", "Longitud", FieldKind.SPATIAL, unit="grados o m",
        aliases=("lon", "long", "longitud", "x", "este", "easting", "utm_e", "coord_x"),
    ),
    FieldSpec(
        "latitude", "Latitud", FieldKind.SPATIAL, unit="grados o m",
        aliases=("lat", "latitud", "y", "norte", "northing", "utm_n", "coord_y"),
    ),
    FieldSpec(
        "elevation", "Cota", FieldKind.SPATIAL, unit="m s. n. m.",
        aliases=("elev", "altitud", "altitude", "z", "msnm", "cota"),
    ),
    # -- fisico-quimica -----------------------------------------------------
    FieldSpec("ph", "pH", FieldKind.PHYSCHEM, unit="u. de pH", aliases=("ph_campo", "ph_lab")),
    FieldSpec(
        "temp_c", "Temperatura", FieldKind.PHYSCHEM, unit="C",
        aliases=("temp", "temperatura", "t", "temp_c", "temperature", "t_c"),
    ),
    FieldSpec(
        "do_mgl", "Oxigeno disuelto", FieldKind.PHYSCHEM, unit="mg/L",
        aliases=("do", "od", "oxigeno", "oxigeno disuelto", "dissolved oxygen", "do_mgl"),
    ),
    FieldSpec(
        "tds_mgl", "Solidos disueltos totales", FieldKind.PHYSCHEM, unit="mg/L",
        aliases=("tds", "std", "sdt", "solidos disueltos", "tds, mg/l", "tds_mgl"),
    ),
    FieldSpec(
        "ec_uscm", "Conductividad electrica", FieldKind.PHYSCHEM, unit="uS/cm",
        aliases=("ce", "ec", "conductividad", "conductivity", "cond", "spc"),
    ),
    # -- iones --------------------------------------------------------------
    _ion_field("Ca", "calcium"),
    _ion_field("Mg", "magnesium"),
    _ion_field("Na", "sodium"),
    _ion_field("K", "potassium"),
    _ion_field("HCO3", "bicarbonate", "alcalinidad", "hco3-"),
    _ion_field("CO3", "carbonate", "co3-", "co3--"),
    _ion_field("SO4", "sulfate", "sulphate", "so4--", "sulfatos"),
    _ion_field("Cl", "chloride", "cloruros", "cl-"),
    _ion_field("F", "fluoride", "fluoruros", "f-"),
    _ion_field("NO3", "nitrate", "nitratos", "no3-"),
)

BY_KEY: dict[str, FieldSpec] = {f.key: f for f in SCHEMA}
REQUIRED_KEYS: tuple[str, ...] = tuple(f.key for f in SCHEMA if f.required)
ION_KEYS: tuple[str, ...] = tuple(f"{i}_mgL" for i in ALL_IONS)


# --------------------------------------------------------------------------
# Normalizacion y deteccion
# --------------------------------------------------------------------------

#: Subindices y superindices Unicode que traen las cabeceras del libro Excel
#: (``Ca²⁺``, ``HCO₃⁻``, ``SO₄²⁻``...). Sin esto, esas cabeceras no se reconocen.
_SUPERSUB = str.maketrans(
    {
        "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
        "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
        "⁰": "", "¹": "", "²": "", "³": "", "⁴": "",
        "⁺": "", "⁻": "", "±": "",
    }
)


def normalise_name(name: str) -> str:
    """Reduce una cabecera a una forma comparable.

    Quita acentos, traduce subindices Unicode a digitos, elimina cargas y
    unidades entre parentesis, y colapsa separadores.
    """
    text = str(name).strip().translate(_SUPERSUB)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"\((?:[^()]*)\)", " ", text)  # "(mg/L)", "(Ca2+)"
    text = re.sub(r"\b(mg/?l|mgl|ug/?l|meq/?l|us/?cm|ppm|s\.?u\.?)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for spec in SCHEMA:
        for name in spec.all_names:
            key = normalise_name(name)
            # El primer campo que reclama un alias se lo queda: el esquema esta
            # ordenado de mas especifico a menos.
            index.setdefault(key, spec.key)
    return index


ALIAS_INDEX: dict[str, str] = _alias_index()


def suggest_mapping(columns) -> tuple[dict[str, str], list[str]]:
    """Propone un mapeo ``campo_canonico -> columna_original``.

    :returns: ``(mapeo, sin_reconocer)``. Nunca asigna dos columnas al mismo
        campo: gana la primera, y la segunda se devuelve como no reconocida para
        que el usuario decida.
    """
    mapping: dict[str, str] = {}
    unmatched: list[str] = []
    for col in columns:
        key = ALIAS_INDEX.get(normalise_name(col))
        if key is not None and key not in mapping:
            mapping[key] = col
        else:
            unmatched.append(str(col))
    return mapping, unmatched


@dataclass
class ColumnMapping:
    """Mapeo entre las columnas de un archivo y el esquema canonico."""

    mapping: dict[str, str] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)

    @classmethod
    def suggest(cls, columns) -> "ColumnMapping":
        mapping, unmatched = suggest_mapping(columns)
        return cls(mapping, unmatched)

    @property
    def missing_required(self) -> list[str]:
        return [k for k in REQUIRED_KEYS if k not in self.mapping]

    @property
    def mapped_ions(self) -> list[str]:
        return [k for k in ION_KEYS if k in self.mapping]

    @property
    def has_temporal(self) -> bool:
        return "sampled_at" in self.mapping

    def set(self, canonical: str, source: str | None) -> "ColumnMapping":
        """Fija o borra manualmente una correspondencia."""
        if canonical not in BY_KEY:
            raise KeyError(
                "Campo canonico desconocido: {!r}. Disponibles: {}".format(
                    canonical, sorted(BY_KEY)
                )
            )
        if source is None:
            self.mapping.pop(canonical, None)
        else:
            self.mapping[canonical] = source
        return self

    def apply(self, df: pd.DataFrame, keep_extra: bool = False) -> pd.DataFrame:
        """Renombra el DataFrame al esquema canonico.

        Las columnas no mapeadas se descartan salvo que ``keep_extra`` las pida:
        arrastrarlas sin declarar es como se cuelan errores de unidades.
        """
        rename = {src: key for key, src in self.mapping.items() if src in df.columns}
        cols = list(rename)
        if keep_extra:
            cols += [c for c in df.columns if c not in rename]
        return df[cols].rename(columns=rename)

    def describe(self) -> pd.DataFrame:
        """Tabla del mapeo, para mostrarla y dejar que el usuario la corrija."""
        rows = []
        for spec in SCHEMA:
            rows.append(
                {
                    "campo": spec.key,
                    "etiqueta": spec.label_es,
                    "tipo": spec.kind.label_es,
                    "unidad": spec.unit or "",
                    "obligatorio": spec.required,
                    "columna_origen": self.mapping.get(spec.key, ""),
                }
            )
        return pd.DataFrame(rows)
