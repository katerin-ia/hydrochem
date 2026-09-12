"""Lectura de archivos de entrada: Excel (.xlsx/.xlsm) y CSV.

Corrige el riesgo **R1** de la auditoria, que es el mas grave de los detectados.
El notebook leia con::

    pd.read_excel(fname, header=0, skiprows=[1, 2])

Eso descarta la fila de descripciones **y la siguiente**, de modo que si el
usuario sustituia la fila de ejemplo de la plantilla por datos reales, esa
muestra desaparecia sin aviso. Ocurrio: la hoja ``DATA`` del libro Excel tiene
90 sitios y el notebook informo ``Loaded 89 samples``; el sitio perdido fue
*Amargosa Tracer Well 2*, con F = 1,7 mg/L, lo que ademas desplazo el recuento
de excedencias de fluoruro de 32 a 31.

Aqui la fila de descripciones se detecta **por su contenido** y se descarta solo
ella. Ninguna fila de datos se pierde nunca.

El lector tambien localiza por su cuenta la fila de cabeceras, que no siempre es
la primera: en la hoja ``DATA`` del libro PiperStiff esta en la fila 14, con
trece filas de configuracion por encima.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .column_mapping import ColumnMapping, normalise_name

#: Extensiones reconocidas.
EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm", ".xltx", ".xltm"})
CSV_SUFFIXES = frozenset({".csv", ".txt", ".tsv"})

#: Cuantas filas se inspeccionan al buscar la cabecera.
HEADER_SEARCH_ROWS = 30


@dataclass
class ReadResult:
    """Lo leido y como se leyo, para poder explicarselo al usuario."""

    data: pd.DataFrame
    mapping: ColumnMapping
    source: str
    sheet: str | None = None
    header_row: int = 0
    description_row_dropped: bool = False
    n_rows_read: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.data)


def _is_numeric_like(value) -> bool:
    """Un valor que podria ser una medida. Las descripciones no lo son."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip().replace(",", ".")
    if not text:
        return False
    try:
        float(text)
        return True
    except ValueError:
        # "<0,05" tambien es una medida, no una descripcion.
        return text[0] in "<>" and _is_numeric_like(text[1:])


def _score_header_row(values) -> int:
    """Cuantas celdas de una fila se reconocen como nombres de campo."""
    from .column_mapping import ALIAS_INDEX

    return sum(
        1
        for v in values
        if v is not None and not pd.isna(v) and normalise_name(v) in ALIAS_INDEX
    )


def find_header_row(raw: pd.DataFrame, max_rows: int = HEADER_SEARCH_ROWS) -> int:
    """Indice (base 0) de la fila que mejor funciona como cabecera.

    Puntua cada fila por cuantas de sus celdas coinciden con un nombre de campo
    conocido. Asi se encuentra la fila 14 de la hoja ``DATA`` sin que el usuario
    tenga que indicarlo.
    """
    best_row, best_score = 0, -1
    for i in range(min(max_rows, len(raw))):
        score = _score_header_row(raw.iloc[i].tolist())
        if score > best_score:
            best_row, best_score = i, score
    return best_row if best_score > 0 else 0


def looks_like_description_row(row: pd.Series, numeric_candidates: list[str]) -> bool:
    """Decide si una fila es de descripciones y no de datos.

    Criterio: en las columnas que deberian contener numeros no hay ni uno. La
    fila de la plantilla del notebook dice "Calcium (mg/L)" donde deberia haber
    45,0; una fila de datos real siempre trae algun numero.
    """
    cells = [row[c] for c in numeric_candidates if c in row.index]
    if not cells:
        return False
    non_empty = [c for c in cells if c is not None and not pd.isna(c) and str(c).strip()]
    if not non_empty:
        return False
    return not any(_is_numeric_like(c) for c in non_empty)


def _uniquify(names: list[str]) -> tuple[list[str], int]:
    """Hace unicos los nombres repetidos anadiendo ``__2``, ``__3``...

    Sin esto, ``df[nombre]`` devuelve un DataFrame en vez de una columna y todo
    lo que venga despues falla de forma poco clara. La hoja ``DATA`` del libro
    PiperStiff repite los nombres de los iones: una vez en mg/L (columnas E-M) y
    otra en meq/L (columnas R-Z).
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    repeats = 0
    for name in names:
        if name in seen:
            seen[name] += 1
            repeats += 1
            out.append(f"{name}__{seen[name]}")
        else:
            seen[name] = 1
            out.append(name)
    return out, repeats


def _numeric_candidate_columns(df: pd.DataFrame, mapping: ColumnMapping) -> list[str]:
    """Columnas del archivo que, segun el mapeo, deberian ser numericas."""
    numeric_keys = set(mapping.mapped_ions) | {
        "longitude", "latitude", "elevation", "ph", "temp_c", "do_mgl", "tds_mgl", "ec_uscm"
    }
    return [src for key, src in mapping.mapping.items() if key in numeric_keys]


def read_table(
    path: str | Path,
    sheet: str | int | None = None,
    header_row: int | None = None,
    mapping: ColumnMapping | None = None,
) -> ReadResult:
    """Lee un archivo de datos hidroquimicos y lo devuelve con su mapeo.

    :param sheet: hoja de Excel. Si se omite, se elige la que mas nombres de
        campo reconocidos tenga en su cabecera.
    :param header_row: fila de cabeceras (base 0). Si se omite, se detecta.
    :param mapping: mapeo a usar. Si se omite, se propone automaticamente.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    notes: list[str] = []

    if suffix in EXCEL_SUFFIXES:
        raw, sheet_name = _read_excel_raw(path, sheet, notes)
    elif suffix in CSV_SUFFIXES:
        raw, sheet_name = _read_csv_raw(path, notes), None
    else:
        raise ValueError(
            f"Formato no soportado: {suffix!r}. "
            f"Se aceptan {sorted(EXCEL_SUFFIXES | CSV_SUFFIXES)}"
        )

    if raw.empty:
        raise ValueError(f"El archivo {path.name!r} no contiene datos.")

    hrow = find_header_row(raw) if header_row is None else header_row
    if hrow > 0:
        notes.append(
            f"Cabeceras detectadas en la fila {hrow + 1} del archivo; "
            f"las {hrow} filas anteriores se ignoran."
        )

    header = [
        str(v).strip() if v is not None and not pd.isna(v) else f"columna_{i + 1}"
        for i, v in enumerate(raw.iloc[hrow].tolist())
    ]
    header, n_duplicates = _uniquify(header)
    if n_duplicates:
        notes.append(
            f"{n_duplicates} cabecera(s) repetida(s) en el archivo; se les anadio "
            f"un sufijo para distinguirlas. La hoja DATA del libro PiperStiff "
            f"repite los nombres de los iones en mg/L y en meq/L."
        )

    body = raw.iloc[hrow + 1 :].copy()
    body.columns = header
    body = body.reset_index(drop=True)

    # Columnas y filas enteramente vacias: no aportan nada.
    body = body.dropna(axis=1, how="all").dropna(axis=0, how="all").reset_index(drop=True)

    mapping = mapping or ColumnMapping.suggest(body.columns)

    # --- R1: se descarta la fila de descripciones, y SOLO esa ---------------
    dropped = False
    candidates = _numeric_candidate_columns(body, mapping)
    if len(body) and looks_like_description_row(body.iloc[0], candidates):
        body = body.iloc[1:].reset_index(drop=True)
        dropped = True
        notes.append(
            "Se descarto la fila de descripciones. A diferencia del notebook "
            "original, la fila siguiente SI se conserva como dato."
        )

    return ReadResult(
        data=body,
        mapping=mapping,
        source=path.name,
        sheet=sheet_name,
        header_row=hrow,
        description_row_dropped=dropped,
        n_rows_read=len(body),
        notes=notes,
    )


def _read_excel_raw(path: Path, sheet, notes: list[str]) -> tuple[pd.DataFrame, str]:
    """Lee una hoja sin interpretar cabeceras, eligiendola si hace falta.

    El libro se cierra siempre: en Windows, dejarlo abierto bloquea el archivo y
    el usuario no puede ni moverlo ni sobrescribirlo mientras la aplicacion
    siga en marcha.
    """
    with pd.ExcelFile(path) as book:
        if sheet is None:
            sheet = _best_sheet(book, notes)
        raw = book.parse(sheet, header=None, dtype=object)
        name = book.sheet_names[sheet] if isinstance(sheet, int) else str(sheet)
    return raw, name


def _best_sheet(book: pd.ExcelFile, notes: list[str]):
    """La hoja cuya mejor fila de cabecera reconoce mas campos."""
    if len(book.sheet_names) == 1:
        return book.sheet_names[0]
    best, best_score = book.sheet_names[0], -1
    for name in book.sheet_names:
        sample = book.parse(name, header=None, nrows=HEADER_SEARCH_ROWS, dtype=object)
        if sample.empty:
            continue
        score = max(
            (_score_header_row(sample.iloc[i].tolist()) for i in range(len(sample))),
            default=0,
        )
        if score > best_score:
            best, best_score = name, score
    if len(book.sheet_names) > 1:
        notes.append(
            f"El archivo tiene {len(book.sheet_names)} hojas; se eligio {best!r} "
            f"por ser la que contiene los datos."
        )
    return best


def _read_csv_raw(path: Path, notes: list[str]) -> pd.DataFrame:
    """Lee un CSV probando separadores y codificaciones habituales."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "latin-1"):
        for sep in (None, ";", ",", "\t"):
            try:
                raw = pd.read_csv(
                    path, header=None, dtype=object, sep=sep,
                    engine="python", encoding=encoding, skip_blank_lines=False,
                )
            except Exception as exc:  # separador o codificacion equivocados
                last_error = exc
                continue
            if raw.shape[1] > 1:
                if sep not in (None, ","):
                    notes.append(f"CSV leido con separador {sep!r} y codificacion {encoding!r}.")
                return raw
    if last_error is not None:
        raise ValueError(f"No se pudo leer {path.name!r} como CSV: {last_error}")
    raise ValueError(f"No se pudo reconocer la estructura de {path.name!r}.")
