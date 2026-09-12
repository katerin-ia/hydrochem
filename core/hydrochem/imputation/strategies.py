"""Imputacion de iones no medidos, con registro de procedencia.

Reescribe la celda 12 del notebook. Cambios de fondo respecto al original:

1. **Una columna vacia al 100 % no se imputa** (riesgo R4). El notebook
   encadenaba mediana de grupo -> mediana global -> ``0.0``, de modo que el NO3,
   que no se habia medido en ninguna muestra, acababa valiendo 0 en las 89 y
   entrando en la suma anionica, en el CBE y en el Piper. Aqui la columna se
   excluye y se informa.
2. **Nunca se cae a cero.** Si no hay base estadistica, el valor sigue ausente.
3. La estrategia es seleccionable y queda registrada por celda, de modo que la
   interfaz puede mostrar que valor es medido y cual estimado.
4. Vectorizado: el original recorria columna x grupo con bucles anidados.

Metodos disponibles
-------------------
``none``
    No imputa nada. Es el valor por defecto: estimar debe ser una decision
    explicita del usuario.
``group_median``
    Mediana dentro del mismo grupo. Preserva la geoquimica de grupo y resiste
    los valores extremos. Requiere un minimo de muestras por grupo.
``global_median``
    Mediana de todo el conjunto. Enmascara la estructura de grupo.
``knn``
    Media ponderada de las k muestras quimicamente mas parecidas. Preserva la
    covariacion multivariante. Requiere scikit-learn.
``half_detection_limit``
    Sustituye los valores por debajo del limite de deteccion por LD/2. Solo es
    aplicable a celdas que llegaron con un limite declarado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from ..constants import MAJOR_IONS, MAX_MISSING_MAJOR_IONS


class ImputationMethod(str, Enum):
    NONE = "none"
    GROUP_MEDIAN = "group_median"
    GLOBAL_MEDIAN = "global_median"
    KNN = "knn"
    HALF_DETECTION_LIMIT = "half_detection_limit"

    @property
    def label_es(self) -> str:
        return {
            "none": "Sin imputacion",
            "group_median": "Mediana del grupo",
            "global_median": "Mediana global",
            "knn": "KNN (k vecinos mas parecidos)",
            "half_detection_limit": "Mitad del limite de deteccion",
        }[self.value]


@dataclass
class ColumnOutcome:
    """Que ocurrio con una columna concreta."""

    column: str
    n_missing_before: int
    n_imputed: int
    n_missing_after: int
    method: str
    skipped_reason: str | None = None

    @property
    def was_skipped(self) -> bool:
        return self.skipped_reason is not None


@dataclass
class ImputationResult:
    """Resultado completo: datos, banderas por celda y explicacion."""

    data: pd.DataFrame
    flags: pd.DataFrame
    method: ImputationMethod
    columns: list[ColumnOutcome] = field(default_factory=list)
    reliability: pd.Series | None = None

    @property
    def n_imputed(self) -> int:
        return int(self.flags.to_numpy().sum())

    @property
    def skipped_columns(self) -> list[str]:
        return [c.column for c in self.columns if c.was_skipped]

    @property
    def imputed_columns(self) -> list[str]:
        return [c.column for c in self.columns if c.n_imputed > 0]

    def messages_es(self) -> list[str]:
        """Frases listas para mostrar en el informe de validacion."""
        out: list[str] = []
        for c in self.columns:
            if c.was_skipped:
                out.append(f"{c.column}: no imputada - {c.skipped_reason}")
            elif c.n_imputed:
                txt = f"{c.column}: {c.n_imputed} valor(es) estimado(s) por {self.method.label_es.lower()}"
                if c.n_missing_after:
                    txt += f"; {c.n_missing_after} siguen ausentes"
                out.append(txt)
        return out


def _empty_flags(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(False, index=df.index, dtype=bool, columns=columns)


def impute(
    df: pd.DataFrame,
    columns: list[str],
    method: ImputationMethod | str = ImputationMethod.NONE,
    group_col: str | None = None,
    min_group_size: int = 3,
    knn_neighbours: int = 5,
) -> ImputationResult:
    """Imputa los valores ausentes de ``columns`` y devuelve datos y procedencia.

    :param min_group_size: numero minimo de valores observados en un grupo para
        que su mediana se considere utilizable. Con grupos de 2 o 3 muestras
        (los hay en el dataset de referencia) la mediana es poco robusta, asi
        que por debajo de este umbral se informa y no se imputa.
    """
    method = ImputationMethod(method)
    present = [c for c in columns if c in df.columns]
    out = df.copy()
    flags = _empty_flags(df, present)
    outcomes: list[ColumnOutcome] = []

    if method is ImputationMethod.NONE:
        for col in present:
            n_missing = int(out[col].isna().sum())
            outcomes.append(ColumnOutcome(col, n_missing, 0, n_missing, method.value))
        return ImputationResult(out, flags, method, outcomes, _reliability(df, columns))

    if method is ImputationMethod.KNN:
        return _impute_knn(out, present, knn_neighbours, columns)

    for col in present:
        series = pd.to_numeric(out[col], errors="coerce")
        missing = series.isna()
        n_missing = int(missing.sum())

        if n_missing == 0:
            outcomes.append(ColumnOutcome(col, 0, 0, 0, method.value))
            continue

        # --- R4: una columna sin ningun valor observado no se inventa ---
        if missing.all():
            outcomes.append(
                ColumnOutcome(
                    col, n_missing, 0, n_missing, method.value,
                    skipped_reason=(
                        "no hay ningun valor observado; el parametro no se midio "
                        "y queda excluido del analisis"
                    ),
                )
            )
            continue

        filled = series.copy()
        if method is ImputationMethod.GROUP_MEDIAN and group_col and group_col in out.columns:
            grouped = series.groupby(out[group_col])
            medians = grouped.median()
            counts = grouped.count()
            usable = medians.where(counts >= min_group_size)
            filled = series.fillna(out[group_col].map(usable))
        elif method is ImputationMethod.GLOBAL_MEDIAN:
            filled = series.fillna(series.median())
        elif method is ImputationMethod.HALF_DETECTION_LIMIT:
            dl_col = f"{col}__detection_limit"
            if dl_col in out.columns:
                filled = series.fillna(pd.to_numeric(out[dl_col], errors="coerce") / 2.0)

        imputed_here = missing & filled.notna()
        out[col] = filled
        flags[col] = imputed_here
        outcomes.append(
            ColumnOutcome(
                col,
                n_missing,
                int(imputed_here.sum()),
                int(filled.isna().sum()),
                method.value,
            )
        )

    return ImputationResult(out, flags, method, outcomes, _reliability(df, columns))


def _impute_knn(
    df: pd.DataFrame, present: list[str], neighbours: int, requested: list[str]
) -> ImputationResult:
    try:
        from sklearn.impute import KNNImputer
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ImportError(
            "La imputacion KNN requiere scikit-learn. Instalalo o elige otro metodo."
        ) from exc

    method = ImputationMethod.KNN
    out = df.copy()
    flags = _empty_flags(df, present)
    outcomes: list[ColumnOutcome] = []

    numeric = out[present].apply(pd.to_numeric, errors="coerce")
    missing = numeric.isna()
    # Las columnas sin ningun valor observado se excluyen del ajuste (R4).
    usable = [c for c in present if not missing[c].all()]
    for col in present:
        if col not in usable:
            n = int(missing[col].sum())
            outcomes.append(
                ColumnOutcome(
                    col, n, 0, n, method.value,
                    skipped_reason=(
                        "no hay ningun valor observado; el parametro no se midio "
                        "y queda excluido del analisis"
                    ),
                )
            )

    if usable:
        imputer = KNNImputer(n_neighbors=neighbours, weights="distance")
        filled = pd.DataFrame(
            imputer.fit_transform(numeric[usable].to_numpy()),
            index=out.index,
            columns=usable,
        )
        for col in usable:
            imputed_here = missing[col] & filled[col].notna()
            out[col] = filled[col]
            flags[col] = imputed_here
            outcomes.append(
                ColumnOutcome(
                    col,
                    int(missing[col].sum()),
                    int(imputed_here.sum()),
                    int(filled[col].isna().sum()),
                    method.value,
                )
            )

    outcomes.sort(key=lambda o: present.index(o.column))
    return ImputationResult(out, flags, method, outcomes, _reliability(df, requested))


def _reliability(
    df: pd.DataFrame, columns: list[str], max_missing: int = MAX_MISSING_MAJOR_IONS
) -> pd.Series:
    """Marca como no fiable la muestra a la que le faltan demasiados iones
    mayoritarios **antes** de imputar. Se evalua sobre el dato original: una
    muestra reconstruida a base de medianas no es fiable por mucho que su
    balance de carga salga perfecto."""
    major_cols = [c for c in columns if c.split("_")[0] in MAJOR_IONS and c in df.columns]
    if not major_cols:
        return pd.Series(True, index=df.index, dtype=bool)
    n_missing = df[major_cols].apply(pd.to_numeric, errors="coerce").isna().sum(axis=1)
    return n_missing <= max_missing


def zeros_as_missing(
    df: pd.DataFrame, columns: list[str], threshold: float = 0.0
) -> pd.DataFrame:
    """Convierte en ausentes los ceros exactos de las columnas indicadas.

    Herramienta para el riesgo **R3**. En el dataset de referencia 32 de 90
    muestras traen ``F = 0``, y el manual del libro PiperStiff documenta que las
    celdas vacias se escriben como 0: ese cero significa *no medido*, no
    *ausente en el agua*. La decision es del usuario y por eso esto es una
    funcion aparte que hay que invocar a proposito, no un comportamiento
    implicito.
    """
    out = df.copy()
    for col in columns:
        if col in out.columns:
            series = pd.to_numeric(out[col], errors="coerce")
            out[col] = series.mask(series <= threshold)
    return out


def count_exact_zeros(df: pd.DataFrame, columns: list[str]) -> dict[str, int]:
    """Ceros exactos por columna: alimenta el aviso del informe de validacion."""
    out: dict[str, int] = {}
    for col in columns:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            n = int((series == 0).sum())
            if n:
                out[col] = n
    return out
