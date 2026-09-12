"""Clasificacion hidroquimica (facies).

Es lo que convierte un diagrama en un analisis: en lugar de mirar una nube de
puntos, cada muestra recibe un nombre -"bicarbonatada calcica", "clorurada
sodica"- que se puede contar, filtrar, cartografiar y comparar entre campanas.
El notebook original no clasificaba nada.

Se ofrecen dos esquemas, porque responden a preguntas distintas:

``dominant``
    Nomenclatura por ion dominante (Custodio y Llamas, 1983, *Hidrologia
    Subterranea*, cap. 10). Se nombra el agua por su anion y su cation
    mayoritarios en porcentaje de meq/L. Regla: si un ion supera el 50 % de su
    grupo, nombra solo el agua; si ninguno llega al 50 %, se nombran los dos
    mayores en orden decreciente unidos por guion. Es el esquema por defecto
    porque funciona con cualquier orientacion del diagrama y se lee sin
    consultar una plantilla.

``piper_zone``
    Los cinco tipos clasicos del rombo de Piper (Piper, 1944; Back, 1966),
    definidos por si los alcalinoterreos superan a los alcalinos y los acidos
    debiles a los fuertes. Son las zonas 5 a 9 de la subdivision habitual del
    rombo. Solo tiene sentido leerlo sobre la convencion clasica del diagrama.

Ambos esquemas trabajan sobre **porcentajes de meq/L**, nunca sobre mg/L: en
mg/L el sodio y el calcio no son comparables.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..constants import IONS
from .units import meq_column

FACIES_COL = "facies"
FACIES_LABEL_COL = "facies_label"

#: Grupos que definen el nombre del agua. El potasio va con el sodio y el
#: carbonato con el bicarbonato: es la practica habitual, porque en aguas
#: naturales el segundo de cada par es casi siempre minoritario.
CATION_GROUPS: dict[str, tuple[str, ...]] = {
    "Ca": ("Ca",),
    "Mg": ("Mg",),
    "Na": ("Na", "K"),
}
ANION_GROUPS: dict[str, tuple[str, ...]] = {
    "HCO3": ("HCO3", "CO3"),
    "SO4": ("SO4",),
    "Cl": ("Cl", "F", "NO3"),
}

#: Adjetivos en espanol. El anion da el sustantivo y el cation el adjetivo:
#: "agua bicarbonatada calcica".
ANION_NOUN = {"HCO3": "bicarbonatada", "SO4": "sulfatada", "Cl": "clorurada"}
CATION_ADJ = {"Ca": "calcica", "Mg": "magnesica", "Na": "sodica"}

#: Umbral por encima del cual un solo ion nombra el agua.
DOMINANCE_THRESHOLD = 50.0

#: Paleta estable por facies, para que el mismo tipo de agua tenga el mismo
#: color en el mapa, en el Piper y en la tabla.
FACIES_COLORS: dict[str, str] = {
    "HCO3-Ca": "#0e6b75",
    "HCO3-Mg": "#3f8f7a",
    "HCO3-Na": "#4c7a3f",
    "SO4-Ca": "#b5651d",
    "SO4-Mg": "#c98a3c",
    "SO4-Na": "#8a6a2f",
    "Cl-Ca": "#8a2f43",
    "Cl-Mg": "#a2506b",
    "Cl-Na": "#a2322c",
    "mixta": "#6b5b95",
    "sin_datos": "#7f9299",
}

ZONE_COLORS: dict[str, str] = {
    "z5_dura_carbonatada": "#0e6b75",
    "z6_dura_no_carbonatada": "#b5651d",
    "z7_alcalina_no_carbonatada": "#a2322c",
    "z8_alcalina_carbonatada": "#4c7a3f",
    "z9_mixta": "#6b5b95",
    "sin_datos": "#7f9299",
}

ZONE_LABELS: dict[str, str] = {
    "z5_dura_carbonatada": "Dureza carbonatada (Ca-Mg / HCO3)",
    "z6_dura_no_carbonatada": "Dureza no carbonatada (Ca-Mg / SO4-Cl)",
    "z7_alcalina_no_carbonatada": "Alcalina no carbonatada (Na-K / SO4-Cl)",
    "z8_alcalina_carbonatada": "Alcalina carbonatada (Na-K / HCO3)",
    "z9_mixta": "Mixta (ningun par supera el 50 %)",
    "sin_datos": "Sin datos suficientes",
}


@dataclass(frozen=True)
class Scheme:
    key: str
    name_es: str
    note_es: str


SCHEMES: dict[str, Scheme] = {
    "dominant": Scheme(
        "dominant",
        "Ion dominante (Custodio)",
        "Se nombra el agua por su anion y su cation mayoritarios en % de meq/L. "
        "Si ninguno supera el 50 %, se nombran los dos mayores.",
    ),
    "piper_zone": Scheme(
        "piper_zone",
        "Zonas del rombo de Piper",
        "Los cinco tipos clasicos, segun si los alcalinoterreos superan a los "
        "alcalinos y los acidos debiles a los fuertes. Lee sobre la convencion clasica.",
    ),
}
DEFAULT_SCHEME = "dominant"


def get_scheme(scheme: str = DEFAULT_SCHEME) -> Scheme:
    try:
        return SCHEMES[scheme]
    except KeyError:
        raise KeyError(
            "Esquema de facies desconocido: {!r}. Disponibles: {}".format(
                scheme, sorted(SCHEMES)
            )
        ) from None


def _group_percentages(
    df: pd.DataFrame, groups: dict[str, tuple[str, ...]], suffix: str = "_meq"
) -> pd.DataFrame:
    """Porcentaje de cada grupo sobre el total del lado (cationes o aniones).

    Los iones sin medir se omiten: no se cuentan como cero, porque un cero
    inventado desplaza todos los porcentajes del resto.
    """
    sums: dict[str, pd.Series] = {}
    for name, ions in groups.items():
        cols = [f"{i}{suffix}" for i in ions if f"{i}{suffix}" in df.columns]
        if cols:
            sums[name] = df[cols].apply(pd.to_numeric, errors="coerce").sum(
                axis=1, min_count=1
            )
    if not sums:
        return pd.DataFrame(index=df.index)

    block = pd.DataFrame(sums, index=df.index)
    total = block.sum(axis=1, min_count=1)
    total = total.where(total > 0)
    return block.div(total, axis=0) * 100.0


def percentages(df: pd.DataFrame, suffix: str = "_meq") -> pd.DataFrame:
    """Los seis porcentajes que usa la clasificacion, en un solo DataFrame."""
    cat = _group_percentages(df, CATION_GROUPS, suffix).add_prefix("pct_")
    an = _group_percentages(df, ANION_GROUPS, suffix).add_prefix("pct_")
    return pd.concat([cat, an], axis=1)


def _dominant_name(shares: pd.Series, order: list[str]) -> str | None:
    """Nombre del lado: un ion si pasa del 50 %, los dos mayores si no."""
    valid = shares.dropna()
    if valid.empty:
        return None
    ranked = valid.sort_values(ascending=False)
    if float(ranked.iloc[0]) >= DOMINANCE_THRESHOLD:
        return str(ranked.index[0])
    top = [str(i) for i in ranked.index[:2]]
    return "-".join(top)


def classify_dominant(df: pd.DataFrame, suffix: str = "_meq") -> pd.DataFrame:
    """Clasificacion por ion dominante.

    :returns: DataFrame con ``facies`` (codigo ``anion-cation``) y
        ``facies_label`` (nombre en espanol).
    """
    pct = percentages(df, suffix)
    cat_cols = [f"pct_{k}" for k in CATION_GROUPS if f"pct_{k}" in pct.columns]
    an_cols = [f"pct_{k}" for k in ANION_GROUPS if f"pct_{k}" in pct.columns]

    codes: list[str] = []
    labels: list[str] = []
    for idx in df.index:
        cat = pct.loc[idx, cat_cols].rename(lambda c: c[4:]) if cat_cols else pd.Series(dtype=float)
        an = pct.loc[idx, an_cols].rename(lambda c: c[4:]) if an_cols else pd.Series(dtype=float)
        cat_name = _dominant_name(cat, list(CATION_GROUPS))
        an_name = _dominant_name(an, list(ANION_GROUPS))
        if cat_name is None or an_name is None:
            codes.append("sin_datos")
            labels.append("Sin datos suficientes")
            continue
        codes.append(f"{an_name}-{cat_name}")
        labels.append(_spanish_label(an_name, cat_name))

    return pd.DataFrame({FACIES_COL: codes, FACIES_LABEL_COL: labels}, index=df.index)


def _spanish_label(anion_name: str, cation_name: str) -> str:
    """"HCO3-Ca" -> "Bicarbonatada calcica"; "Cl-SO4-Na" -> nombres compuestos."""
    nouns = [ANION_NOUN.get(p, p) for p in anion_name.split("-")]
    adjs = [CATION_ADJ.get(p, p) for p in cation_name.split("-")]
    noun = "-".join(nouns)
    adj = "-".join(adjs)
    return f"{noun.capitalize()} {adj}"


def classify_piper_zone(df: pd.DataFrame, suffix: str = "_meq") -> pd.DataFrame:
    """Los cinco tipos clasicos del rombo de Piper (zonas 5 a 9)."""
    pct = percentages(df, suffix)

    def col(name: str) -> pd.Series:
        return pct[f"pct_{name}"] if f"pct_{name}" in pct.columns else pd.Series(
            np.nan, index=df.index
        )

    alkaline_earth = col("Ca").fillna(0) + col("Mg").fillna(0)  # Ca + Mg
    alkali = col("Na")  # Na + K
    weak_acid = col("HCO3")  # HCO3 + CO3
    strong_acid = col("SO4").fillna(0) + col("Cl").fillna(0)

    have = col("Ca").notna() | col("Mg").notna()
    have &= col("HCO3").notna() | col("SO4").notna() | col("Cl").notna()

    codes = pd.Series("z9_mixta", index=df.index, dtype=object)
    codes[alkaline_earth.gt(50) & weak_acid.gt(50)] = "z5_dura_carbonatada"
    codes[alkaline_earth.gt(50) & strong_acid.gt(50)] = "z6_dura_no_carbonatada"
    codes[alkali.gt(50) & strong_acid.gt(50)] = "z7_alcalina_no_carbonatada"
    codes[alkali.gt(50) & weak_acid.gt(50)] = "z8_alcalina_carbonatada"
    codes[~have] = "sin_datos"

    return pd.DataFrame(
        {
            FACIES_COL: codes,
            FACIES_LABEL_COL: codes.map(ZONE_LABELS).fillna("Sin datos suficientes"),
        },
        index=df.index,
    )


def classify(
    df: pd.DataFrame, scheme: str = DEFAULT_SCHEME, suffix: str = "_meq"
) -> pd.DataFrame:
    """Clasifica segun el esquema indicado."""
    get_scheme(scheme)
    if scheme == "piper_zone":
        return classify_piper_zone(df, suffix)
    return classify_dominant(df, suffix)


def add_facies(
    df: pd.DataFrame, scheme: str = DEFAULT_SCHEME, suffix: str = "_meq"
) -> pd.DataFrame:
    """Anade ``facies`` y ``facies_label`` mas los seis porcentajes de grupo."""
    out = df.copy()
    pct = percentages(df, suffix)
    for c in pct.columns:
        out[c] = pct[c]
    result = classify(df, scheme, suffix)
    out[FACIES_COL] = result[FACIES_COL]
    out[FACIES_LABEL_COL] = result[FACIES_LABEL_COL]
    return out


def colors_for(scheme: str = DEFAULT_SCHEME) -> dict[str, str]:
    return dict(ZONE_COLORS) if scheme == "piper_zone" else dict(FACIES_COLORS)


def color_of(code: str, scheme: str = DEFAULT_SCHEME) -> str:
    """Color de una facies. Los codigos compuestos heredan el del anion."""
    table = colors_for(scheme)
    if code in table:
        return table[code]
    head = code.split("-")[0]
    for key, value in table.items():
        if key.startswith(head):
            return value
    return table.get("sin_datos", "#7f9299")


def summary(facies: pd.Series) -> pd.DataFrame:
    """Recuento por facies, de mas a menos frecuente."""
    counts = facies.value_counts()
    total = int(counts.sum()) or 1
    return pd.DataFrame(
        {
            "facies": counts.index,
            "n": counts.to_numpy(),
            "pct": (counts.to_numpy() / total * 100.0).round(1),
        }
    ).reset_index(drop=True)


def label_of(code: str, scheme: str = DEFAULT_SCHEME) -> str:
    """Nombre legible de un codigo de facies."""
    if scheme == "piper_zone":
        return ZONE_LABELS.get(code, code)
    if code == "sin_datos":
        return "Sin datos suficientes"
    parts = code.split("-")
    # El ultimo grupo es el cation; el resto, aniones.
    cations = [p for p in parts if p in CATION_ADJ]
    anions = [p for p in parts if p in ANION_NOUN]
    if not cations or not anions:
        return code
    return _spanish_label("-".join(anions), "-".join(cations))


def ion_label(group: str) -> str:
    """Etiqueta con formato del ion que representa un grupo."""
    ions = CATION_GROUPS.get(group) or ANION_GROUPS.get(group) or (group,)
    return " + ".join(IONS[i].label for i in ions if i in IONS) or group


__all__ = [
    "FACIES_COL", "FACIES_LABEL_COL", "SCHEMES", "DEFAULT_SCHEME",
    "CATION_GROUPS", "ANION_GROUPS", "DOMINANCE_THRESHOLD",
    "add_facies", "classify", "classify_dominant", "classify_piper_zone",
    "colors_for", "color_of", "get_scheme", "ion_label", "label_of",
    "percentages", "summary",
]
