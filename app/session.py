"""Estado por sesion, para que la aplicacion admita varios usuarios a la vez.

Por que hacia falta: la primera version guardaba el dataset en un unico
diccionario del proceso. En el ordenador de un solo usuario eso no se nota, pero
publicada en internet **el segundo visitante sobrescribia los datos del
primero** y ambos veian una mezcla. Este modulo aisla cada visitante.

Como funciona: una cookie con un identificador aleatorio. No hay cuentas ni
contrasenas -la herramienta no las necesita- pero cada sesion ve solo lo suyo.

Tres limites que en local sobran y publicada no:

- **Caducidad**: una sesion sin actividad se olvida, y con ella sus archivos.
- **Cupo de sesiones**: por encima del maximo se descarta la mas antigua, para
  que la memoria no crezca sin tope.
- **Tamano y tipo de archivo**: se rechaza lo que no sea una hoja de calculo y
  lo que pase del limite, antes de leerlo entero en memoria.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

COOKIE_NAME = "hc_session"

#: Minutos sin actividad tras los que una sesion se olvida.
SESSION_TTL_MIN = int(os.environ.get("HC_SESSION_TTL_MIN", "90"))

#: Sesiones simultaneas como maximo. Cada una guarda un DataFrame en memoria.
MAX_SESSIONS = int(os.environ.get("HC_MAX_SESSIONS", "40"))

#: Tamano maximo de un archivo subido, en MB.
MAX_UPLOAD_MB = int(os.environ.get("HC_MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

#: Extensiones aceptadas. Cualquier otra se rechaza sin abrirla.
ALLOWED_SUFFIXES = frozenset({".xlsx", ".xlsm", ".xltx", ".xltm", ".csv", ".txt", ".tsv"})

#: Caracteres admitidos en el nombre de un archivo subido.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ ()-]+")


class UploadRejected(Exception):
    """El archivo no se acepta. El mensaje va directo al usuario."""


@dataclass
class Session:
    """Lo que sabe la aplicacion de un visitante."""

    sid: str
    workdir: Path
    dataset: Any = None
    source_path: Path | None = None
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_seen = time.time()

    @property
    def idle_minutes(self) -> float:
        return (time.time() - self.last_seen) / 60.0

    def clear(self) -> None:
        self.dataset = None
        self.source_path = None

    def dispose(self) -> None:
        """Borra los archivos de la sesion. Lo que subio el usuario no se queda."""
        self.clear()
        shutil.rmtree(self.workdir, ignore_errors=True)


class SessionStore:
    """Registro de sesiones con caducidad y cupo."""

    def __init__(self, root: Path, ttl_min: int = SESSION_TTL_MIN,
                 max_sessions: int = MAX_SESSIONS) -> None:
        self.root = Path(root)
        self.ttl_min = ttl_min
        self.max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}
        self.root.mkdir(parents=True, exist_ok=True)

    # -- ciclo de vida -----------------------------------------------------

    def new_id(self) -> str:
        return secrets.token_urlsafe(18)

    def get(self, sid: str | None, create: bool = True) -> Session | None:
        self._evict()
        if sid and sid in self._sessions:
            s = self._sessions[sid]
            s.touch()
            return s
        if not create:
            return None
        return self._create(sid if _valid_id(sid) else self.new_id())

    def _create(self, sid: str) -> Session:
        if len(self._sessions) >= self.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.last_seen)
            self.drop(oldest.sid)
        workdir = self.root / sid
        workdir.mkdir(parents=True, exist_ok=True)
        s = Session(sid=sid, workdir=workdir)
        self._sessions[sid] = s
        return s

    def drop(self, sid: str) -> None:
        s = self._sessions.pop(sid, None)
        if s is not None:
            s.dispose()

    def _evict(self) -> None:
        caducadas = [
            sid for sid, s in self._sessions.items() if s.idle_minutes > self.ttl_min
        ]
        for sid in caducadas:
            self.drop(sid)

    # -- informacion -------------------------------------------------------

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def stats(self) -> dict:
        return {
            "sessions": len(self._sessions),
            "with_data": sum(1 for s in self._sessions.values() if s.dataset is not None),
            "ttl_min": self.ttl_min,
            "max_sessions": self.max_sessions,
            "max_upload_mb": MAX_UPLOAD_MB,
        }

    # -- subida de archivos -------------------------------------------------

    def store_upload(self, session: Session, filename: str | None, data: bytes) -> Path:
        """Guarda un archivo subido tras comprobarlo.

        :raises UploadRejected: si el tipo, el tamano o el contenido no cuadran.
        """
        if not data:
            raise UploadRejected("El archivo esta vacio.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise UploadRejected(
                f"El archivo pesa {len(data) / 1024 / 1024:.1f} MB y el limite son "
                f"{MAX_UPLOAD_MB} MB."
            )
        nombre = safe_filename(filename)
        suffix = Path(nombre).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise UploadRejected(
                f"No se admite el formato {suffix or '(sin extension)'}. "
                f"Usa {', '.join(sorted(ALLOWED_SUFFIXES))}."
            )
        if not _looks_like_spreadsheet(data, suffix):
            raise UploadRejected(
                "El contenido del archivo no corresponde a su extension. "
                "Comprueba que sea una hoja de calculo de verdad."
            )

        # Un archivo por sesion: subir otro reemplaza el anterior.
        for viejo in session.workdir.glob("*"):
            if viejo.is_file():
                viejo.unlink(missing_ok=True)
        destino = session.workdir / nombre
        destino.write_bytes(data)
        session.source_path = destino
        return destino


def safe_filename(filename: str | None) -> str:
    """Nombre de archivo inofensivo.

    Se queda solo con el nombre base -asi ``../../etc/passwd`` se convierte en
    ``passwd``-, recorta los caracteres raros y limita la longitud.
    """
    base = Path(str(filename or "datos.xlsx")).name
    base = base.replace("\\", "/").split("/")[-1]
    base = _SAFE_NAME.sub("_", base).strip(" ._") or "datos.xlsx"
    if len(base) > 120:
        stem, _, suffix = base.rpartition(".")
        base = f"{stem[:100]}.{suffix}" if suffix else base[:120]
    return base


def _looks_like_spreadsheet(data: bytes, suffix: str) -> bool:
    """Comprueba la firma del archivo, no solo su extension.

    Un ``.xlsx`` es un ZIP y empieza por ``PK``. Renombrar un ejecutable a
    ``.xlsx`` no deberia colar.
    """
    if suffix in {".csv", ".txt", ".tsv"}:
        muestra = data[:4096]
        if b"\x00" in muestra:
            return False  # un binario disfrazado de texto
        for encoding in ("utf-8", "latin-1"):
            try:
                muestra.decode(encoding)
                return True
            except UnicodeDecodeError:
                continue
        return False
    return data[:2] == b"PK"


def _valid_id(sid: str | None) -> bool:
    return bool(sid) and bool(re.fullmatch(r"[A-Za-z0-9_-]{16,64}", sid or ""))
