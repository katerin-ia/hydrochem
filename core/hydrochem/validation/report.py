"""Informe de validacion estructurado.

Sustituye los ``print`` con emojis del notebook por un objeto que la interfaz
puede pintar y el usuario puede leer. Cada hallazgo lleva severidad, el campo
afectado y, cuando procede, las filas implicadas, de modo que la pantalla puede
llevar al usuario directamente al dato problematico.

Principio de fondo: **decir lo que pasa, no arreglarlo por detras**. La
aplicacion informa de que 32 muestras traen fluoruro exactamente 0 y explica por
que eso probablemente significa "no medido", pero no lo cambia sin permiso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"  # impide continuar
    WARNING = "warning"  # se puede continuar, pero afecta a los resultados
    INFO = "info"  # conviene saberlo

    @property
    def label_es(self) -> str:
        return {"error": "Error", "warning": "Aviso", "info": "Informacion"}[self.value]

    @property
    def order(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


@dataclass
class Issue:
    """Un hallazgo concreto."""

    severity: Severity
    code: str
    message: str
    # Nombre deliberadamente distinto de "field": un atributo llamado asi
    # sustituye a dataclasses.field dentro del cuerpo de la clase y rompe los
    # default_factory declarados despues de el.
    field_name: str | None = None
    rows: list[int] = field(default_factory=list)
    hint: str | None = None

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "field": self.field_name,
            "rows": self.rows,
            "n_rows": self.n_rows,
            "hint": self.hint,
        }


@dataclass
class ValidationReport:
    """Resultado completo de validar un conjunto de datos."""

    n_rows: int = 0
    n_columns_mapped: int = 0
    issues: list[Issue] = field(default_factory=list)
    column_stats: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(
        self,
        severity: Severity | str,
        code: str,
        message: str,
        field_name: str | None = None,
        rows: list[int] | None = None,
        hint: str | None = None,
    ) -> "ValidationReport":
        self.issues.append(
            Issue(Severity(severity), code, message, field_name, list(rows or []), hint)
        )
        return self

    def of(self, severity: Severity | str) -> list[Issue]:
        sev = Severity(severity)
        return [i for i in self.issues if i.severity is sev]

    @property
    def errors(self) -> list[Issue]:
        return self.of(Severity.ERROR)

    @property
    def warnings(self) -> list[Issue]:
        return self.of(Severity.WARNING)

    @property
    def ok(self) -> bool:
        """Se puede seguir adelante con el analisis."""
        return not self.errors

    @property
    def counts(self) -> dict[str, int]:
        return {s.value: len(self.of(s)) for s in Severity}

    def sorted_issues(self) -> list[Issue]:
        return sorted(self.issues, key=lambda i: (i.severity.order, i.code))

    def to_dict(self) -> dict:
        return {
            "n_rows": self.n_rows,
            "n_columns_mapped": self.n_columns_mapped,
            "ok": self.ok,
            "counts": self.counts,
            "issues": [i.to_dict() for i in self.sorted_issues()],
            "column_stats": self.column_stats,
            "notes": self.notes,
        }

    def summary_es(self) -> str:
        c = self.counts
        estado = "listo para analizar" if self.ok else "no se puede continuar"
        return (
            f"{self.n_rows} muestras, {self.n_columns_mapped} campos reconocidos - "
            f"{estado}. {c['error']} error(es), {c['warning']} aviso(s), "
            f"{c['info']} nota(s)."
        )
