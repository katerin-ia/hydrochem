"""Umbrales normativos y comprobacion de excedencias.

Generaliza el bloque de fluoruro del notebook, que llevaba el limite de la OMS
escrito dos veces en el codigo (``WHO_F = 1.5``) y solo servia para ese ion.
Aqui un estandar es **dato**, no codigo: se puede leer, editar y anadir sin
tocar la aplicacion.

Aviso importante sobre los valores
----------------------------------
Los umbrales de la OMS que se incluyen estan tomados de las *Guidelines for
Drinking-water Quality* (4.ª edicion, 2011, con el apendice de 2017) y son los
que se citan de forma habitual en la literatura.

El conjunto marcado como ``peru_*`` es una **plantilla de partida, no una fuente
normativa**. Antes de usarlo para cualquier informe hay que cotejarlo con el
texto oficial publicado (D.S. 031-2010-SA para agua de consumo humano y
D.S. 004-2017-MINAM para los ECA de agua), porque estos valores se revisan y una
cifra equivocada en un informe de calidad de agua tiene consecuencias. La
aplicacion marca estos conjuntos con ``verified=False`` y lo advierte en
pantalla.

Cada umbral lleva ademas su naturaleza: un limite **sanitario** protege la salud
y uno **organoleptico** solo afecta al sabor, el olor o el aspecto. Mezclarlos en
un mismo recuento de "incumplimientos" no dice nada util.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

import pandas as pd

from ..constants import IONS


class LimitKind(str, Enum):
    HEALTH = "health"
    AESTHETIC = "aesthetic"
    OPERATIONAL = "operational"

    @property
    def label_es(self) -> str:
        return {
            "health": "sanitario",
            "aesthetic": "organoleptico",
            "operational": "operativo",
        }[self.value]


@dataclass(frozen=True)
class Limit:
    """Un umbral para un parametro."""

    parameter: str  # columna canonica, p. ej. "F_mgL" o "ph"
    label: str  # como mostrarlo
    unit: str
    kind: LimitKind
    maximum: float | None = None
    minimum: float | None = None
    note: str = ""
    source_url: str = ""

    def exceeds(self, values: pd.Series) -> pd.Series:
        """Serie booleana de incumplimientos. Los ausentes no incumplen."""
        v = pd.to_numeric(values, errors="coerce")
        bad = pd.Series(False, index=v.index)
        if self.maximum is not None:
            bad |= v > self.maximum
        if self.minimum is not None:
            bad |= v < self.minimum
        return bad & v.notna()

    @property
    def range_text(self) -> str:
        if self.minimum is not None and self.maximum is not None:
            return f"{self.minimum:g} – {self.maximum:g} {self.unit}"
        if self.maximum is not None:
            return f"≤ {self.maximum:g} {self.unit}"
        if self.minimum is not None:
            return f"≥ {self.minimum:g} {self.unit}"
        return "—"

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter, "label": self.label, "unit": self.unit,
            "kind": self.kind.value, "kind_label": self.kind.label_es,
            "maximum": self.maximum, "minimum": self.minimum,
            "range_text": self.range_text, "note": self.note,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class Standard:
    """Un conjunto de umbrales con su procedencia."""

    key: str
    name_es: str
    source: str
    #: ``False`` = plantilla sin cotejar con el texto oficial. La interfaz avisa.
    verified: bool
    limits: tuple[Limit, ...] = field(default_factory=tuple)
    source_url: str = ""

    def limit_for(self, parameter: str) -> Limit | None:
        for lim in self.limits:
            if lim.parameter == parameter:
                return lim
        return None

    @property
    def parameters(self) -> tuple[str, ...]:
        return tuple(lim.parameter for lim in self.limits)

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name_es, "source": self.source,
            "verified": self.verified,
            "limits": [lim.to_dict() for lim in self.limits],
            "source_url": self.source_url,
        }


def _ion(ion: str) -> str:
    return f"{ion}_mgL"


def _label(ion: str) -> str:
    return IONS[ion].label if ion in IONS else ion


WHO_BASE = "https://cdn.who.int/media/docs/default-source/wash-documents/water-safety-and-quality/chemical-fact-sheets-2022/"
PERU_SOURCE = "https://www.digesa.minsa.gob.pe/norma_consulta/Reglamento_Calidad_Agua%20D.S%20N%C2%B0031-2010-SA.pdf"

WHO_DRINKING = Standard(
    key="who_drinking",
    name_es="OMS — guías y referencias de calidad",
    source=(
        "World Health Organization, Guidelines for Drinking-water Quality, "
        "4.ª ed. con adendas de 2022. F y NO3: valores guía sanitarios. "
        "Los demás son referencias de aceptabilidad u operación, no límites sanitarios."
    ),
    verified=True,
    limits=(
        Limit(_ion("F"), _label("F"), "mg/L", LimitKind.HEALTH, maximum=1.5,
              note="Valor guía sanitario para fluoruro.", source_url=WHO_BASE + "fluoride-fact-sheet-2022.pdf"),
        Limit(_ion("NO3"), _label("NO3"), "mg/L", LimitKind.HEALTH, maximum=50.0,
              note="Expresado como ion NO3, no como nitrógeno. La evaluación conjunta con nitrito no está incluida.", source_url=WHO_BASE + "nitrate-and-nitrite-fact-sheet-2022.pdf"),
        Limit(_ion("Cl"), _label("Cl"), "mg/L", LimitKind.AESTHETIC, maximum=250.0,
              note="Referencia de sabor; no hay valor guía sanitario.", source_url=WHO_BASE + "chloride-fact-sheet-2022.pdf"),
        Limit(_ion("SO4"), _label("SO4"), "mg/L", LimitKind.AESTHETIC, maximum=250.0,
              note="Referencia de comparación de la aplicación (250 mg/L), no límite sanitario ni umbral de efecto laxante. La OMS recomienda notificar a la autoridad por encima de 500 mg/L.", source_url=WHO_BASE + "sulfate-fact-sheet-2022.pdf"),
        Limit(_ion("Na"), _label("Na"), "mg/L", LimitKind.AESTHETIC, maximum=200.0,
              note="Referencia de sabor; no hay valor guía sanitario.", source_url=WHO_BASE + "sodium-fact-sheet-2022.pdf"),
        Limit("tds_mgl", "TDS", "mg/L", LimitKind.AESTHETIC, maximum=1000.0,
              note="Referencia de comparación de la aplicación (1000 mg/L). La OMS no fija un valor guía sanitario para TDS.", source_url=WHO_BASE + "total-dissolved-solids-fact-sheet-2022.pdf"),
        Limit("ph", "pH", "u. de pH", LimitKind.OPERATIONAL, minimum=6.5, maximum=8.5,
              note="Intervalo operativo de comparación de la aplicación; la OMS no fija un valor guía sanitario ni un intervalo universal de pH.", source_url=WHO_BASE + "ph-fact-sheet-2022.pdf"),
    ),
)

PERU_DRINKING = Standard(
    key="peru_drinking",
    name_es="Perú — D.S. 031-2010-SA (parámetros disponibles)",
    source="MINSA / DIGESA, D.S. 031-2010-SA, anexos II y III, pp. 39–40. Valores cotejados con la publicación de 2011. Evalúa solo los parámetros medidos incluidos; no certifica potabilidad.",
    verified=True,
    source_url=PERU_SOURCE,
    limits=(
        Limit("F_mgL", _label("F"), "mg/L", LimitKind.HEALTH, maximum=1.0, note="Anexo III: flúor expresado como F−.", source_url=PERU_SOURCE + "#page=41"),
        Limit("NO3_mgL", _label("NO3"), "mg/L", LimitKind.HEALTH, maximum=50.0, note="Anexo III: nitratos expresados como NO3, no como N.", source_url=PERU_SOURCE + "#page=41"),
        Limit("Cl_mgL", _label("Cl"), "mg/L", LimitKind.AESTHETIC, maximum=250, note="Anexo II.", source_url=PERU_SOURCE + "#page=40"),
        Limit("SO4_mgL", _label("SO4"), "mg/L", LimitKind.AESTHETIC, maximum=250, note="Anexo II.", source_url=PERU_SOURCE + "#page=40"),
        Limit("Na_mgL", _label("Na"), "mg/L", LimitKind.AESTHETIC, maximum=200, note="Anexo II.", source_url=PERU_SOURCE + "#page=40"),
        Limit("tds_mgl", "TDS", "mg/L", LimitKind.AESTHETIC, maximum=1000, note="Anexo II: sólidos totales disueltos.", source_url=PERU_SOURCE + "#page=40"),
        Limit("ph", "pH", "u. de pH", LimitKind.AESTHETIC, minimum=6.5, maximum=8.5, note="Anexo II: parámetro de calidad organoléptica.", source_url=PERU_SOURCE + "#page=40"),
    ),
)

PERU_DRINKING_TEMPLATE = Standard(
    key="peru_drinking_template",
    name_es="Perú — consumo humano (PLANTILLA SIN COTEJAR)",
    source=(
        "Plantilla de partida inspirada en el D.S. 031-2010-SA (Reglamento de la "
        "Calidad del Agua para Consumo Humano). NO cotejada con el texto oficial: "
        "verifica cada cifra antes de usarla en un informe."
    ),
    verified=False,
    limits=(
        Limit(_ion("F"), _label("F"), "mg/L", LimitKind.HEALTH, maximum=1.0),
        Limit(_ion("NO3"), _label("NO3"), "mg/L", LimitKind.HEALTH, maximum=50.0),
        Limit(_ion("Cl"), _label("Cl"), "mg/L", LimitKind.AESTHETIC, maximum=250.0),
        Limit(_ion("SO4"), _label("SO4"), "mg/L", LimitKind.AESTHETIC, maximum=250.0),
        Limit(_ion("Na"), _label("Na"), "mg/L", LimitKind.AESTHETIC, maximum=200.0),
        Limit("tds_mgl", "TDS", "mg/L", LimitKind.AESTHETIC, maximum=1000.0),
        Limit("ph", "pH", "u. de pH", LimitKind.OPERATIONAL, minimum=6.5, maximum=8.5),
    ),
)

STANDARDS: dict[str, Standard] = {
    s.key: s for s in (WHO_DRINKING, PERU_DRINKING, PERU_DRINKING_TEMPLATE)
}
DEFAULT_STANDARD = "who_drinking"


def get_standard(standard: str | Standard = DEFAULT_STANDARD) -> Standard:
    if isinstance(standard, Standard):
        return standard
    try:
        return STANDARDS[standard]
    except KeyError:
        raise KeyError(
            "Estandar desconocido: {!r}. Disponibles: {}".format(
                standard, sorted(STANDARDS)
            )
        ) from None


def custom_standard(name: str, limits: list[dict]) -> Standard:
    """Construye un estandar propio desde datos sueltos.

    Pensado para que el usuario pueda cargar sus umbrales sin tocar el codigo.
    """
    if not isinstance(limits, list) or not 1 <= len(limits) <= 30:
        raise ValueError("Incluye entre 1 y 30 parámetros con límites.")
    name = str(name).strip()
    if not name or len(name) > 120:
        raise ValueError("El nombre debe tener entre 1 y 120 caracteres.")
    allowed = {f"{ion}_mgL" for ion in IONS} | {"tds_mgl", "ph", "temp_c", "do_mgl"}
    built: list[Limit] = []
    seen = set()
    for raw in limits:
        param = str(raw["parameter"])
        if param not in allowed or param in seen:
            raise ValueError(f"Parámetro no admitido o repetido: {param}.")
        seen.add(param)
        bounds = {}
        for key in ("minimum", "maximum"):
            value = raw.get(key)
            if value is None or value == "":
                bounds[key] = None
                continue
            if isinstance(value, bool):
                raise ValueError("Los límites deben ser números.")
            value = float(value)
            if not math.isfinite(value) or (param != "temp_c" and value < 0):
                raise ValueError("Los límites deben ser finitos y las concentraciones no negativas.")
            if param == "ph" and value > 14:
                raise ValueError("El intervalo de pH admitido es de 0 a 14.")
            bounds[key] = value
        lo, hi = bounds["minimum"], bounds["maximum"]
        if lo is None and hi is None:
            raise ValueError(f"Indica al menos un límite para {param}.")
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"El mínimo de {param} no puede superar el máximo.")
        built.append(
            Limit(
                parameter=param,
                label=str(raw.get("label") or param),
                unit=str(raw.get("unit") or "mg/L"),
                kind=LimitKind(raw.get("kind") or "health"),
                maximum=hi,
                minimum=lo,
                note=str(raw.get("note") or ""),
            )
        )
    return Standard("custom", name, "Criterios definidos por el usuario; no constituyen una norma oficial.", False, tuple(built))


# --------------------------------------------------------------------------
# Comprobacion
# --------------------------------------------------------------------------


def check(
    df: pd.DataFrame,
    standard: str | Standard = DEFAULT_STANDARD,
    measured_only: bool = True,
) -> pd.DataFrame:
    """Excedencias por parametro.

    :param measured_only: el denominador son las muestras **con medida**, no el
        total. Es la diferencia entre "32 de 90 superan el limite" y "32 de 58
        medidas lo superan": con el fluoruro del dataset de referencia, 36 % o
        55 %. Contar las no medidas como cumplidoras es el error mas comun.
    :returns: una fila por parametro con ``n_measured``, ``n_exceeding``, ``pct``
        y los extremos observados.
    """
    std = get_standard(standard)
    rows: list[dict] = []
    for lim in std.limits:
        if lim.parameter not in df.columns:
            continue
        values = pd.to_numeric(df[lim.parameter], errors="coerce")
        n_measured = int(values.notna().sum())
        if measured_only and n_measured == 0:
            continue
        bad = lim.exceeds(values)
        denom = n_measured if measured_only else len(df)
        rows.append(
            {
                "parameter": lim.parameter,
                "label": lim.label,
                "unit": lim.unit,
                "kind": lim.kind.value,
                "kind_label": lim.kind.label_es,
                "range_text": lim.range_text,
                "maximum": lim.maximum,
                "minimum": lim.minimum,
                "n_total": int(len(df)),
                "n_measured": n_measured,
                "n_missing": int(len(df) - n_measured),
                "n_exceeding": int(bad.sum()),
                "pct": round(float(bad.sum()) / denom * 100.0, 1) if denom else 0.0,
                "min_observed": None if not n_measured else float(values.min()),
                "max_observed": None if not n_measured else float(values.max()),
                "note": lim.note,
                "source_url": lim.source_url,
            }
        )
    return pd.DataFrame(rows)


def exceeding_mask(
    df: pd.DataFrame, parameter: str, standard: str | Standard = DEFAULT_STANDARD
) -> pd.Series:
    """Muestras que incumplen un parametro concreto."""
    std = get_standard(standard)
    lim = std.limit_for(parameter)
    if lim is None or parameter not in df.columns:
        return pd.Series(False, index=df.index)
    return lim.exceeds(df[parameter])


def add_compliance(
    df: pd.DataFrame, standard: str | Standard = DEFAULT_STANDARD
) -> pd.DataFrame:
    """Anade una columna booleana por parametro y un resumen por muestra."""
    std = get_standard(standard)
    out = df.copy()
    cols: list[str] = []
    measured: list[pd.Series] = []
    for lim in std.limits:
        if lim.parameter not in out.columns:
            continue
        col = f"{lim.parameter}__exceeds"
        out[col] = lim.exceeds(out[lim.parameter])
        cols.append(col)
        measured.append(pd.to_numeric(out[lim.parameter], errors="coerce").notna())
    out["n_evaluated"] = pd.concat(measured, axis=1).sum(axis=1).astype(int) if measured else 0
    if cols:
        out["n_exceedances"] = out[cols].sum(axis=1).astype(int)
        health = [
            f"{lim.parameter}__exceeds"
            for lim in std.limits
            if lim.kind is LimitKind.HEALTH and f"{lim.parameter}__exceeds" in out.columns
        ]
        out["exceeds_health"] = out[health].any(axis=1) if health else False
    else:
        out["n_exceedances"] = 0
        out["exceeds_health"] = False
    return out


def available() -> list[dict]:
    return [s.to_dict() for s in STANDARDS.values()]
