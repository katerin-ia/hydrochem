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
        }


def _ion(ion: str) -> str:
    return f"{ion}_mgL"


def _label(ion: str) -> str:
    return IONS[ion].label if ion in IONS else ion


WHO_DRINKING = Standard(
    key="who_drinking",
    name_es="OMS — agua de consumo humano",
    source=(
        "World Health Organization, Guidelines for Drinking-water Quality, "
        "4.ª ed. (2011) con el apendice de 2017."
    ),
    verified=True,
    limits=(
        Limit(_ion("F"), _label("F"), "mg/L", LimitKind.HEALTH, maximum=1.5,
              note="Por encima, fluorosis dental y, a dosis altas, esqueletica."),
        Limit(_ion("NO3"), _label("NO3"), "mg/L", LimitKind.HEALTH, maximum=50.0,
              note="Expresado como NO3. Riesgo de metahemoglobinemia en lactantes."),
        Limit(_ion("Cl"), _label("Cl"), "mg/L", LimitKind.AESTHETIC, maximum=250.0,
              note="Umbral de sabor; no hay valor guia sanitario."),
        Limit(_ion("SO4"), _label("SO4"), "mg/L", LimitKind.AESTHETIC, maximum=250.0,
              note="Umbral de sabor y efecto laxante."),
        Limit(_ion("Na"), _label("Na"), "mg/L", LimitKind.AESTHETIC, maximum=200.0,
              note="Umbral de sabor."),
        Limit("tds_mgl", "TDS", "mg/L", LimitKind.AESTHETIC, maximum=1000.0,
              note="Palatabilidad; por encima de 1200 mg/L se considera desagradable."),
        Limit("ph", "pH", "u. de pH", LimitKind.OPERATIONAL, minimum=6.5, maximum=8.5,
              note="Intervalo operativo recomendado; no es un valor guia sanitario."),
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
    s.key: s for s in (WHO_DRINKING, PERU_DRINKING_TEMPLATE)
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
    built: list[Limit] = []
    for raw in limits:
        param = str(raw["parameter"])
        built.append(
            Limit(
                parameter=param,
                label=str(raw.get("label") or param),
                unit=str(raw.get("unit") or "mg/L"),
                kind=LimitKind(raw.get("kind") or "health"),
                maximum=None if raw.get("maximum") is None else float(raw["maximum"]),
                minimum=None if raw.get("minimum") is None else float(raw["minimum"]),
                note=str(raw.get("note") or ""),
            )
        )
    return Standard("custom", name, "Definido por el usuario", False, tuple(built))


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
    for lim in std.limits:
        if lim.parameter not in out.columns:
            continue
        col = f"{lim.parameter}__exceeds"
        out[col] = lim.exceeds(out[lim.parameter])
        cols.append(col)
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
