"""Renueva la version de los assets en index.html.

El navegador cachea app.js y app.css con fuerza. Sin cambiar la cadena de
consulta, una correccion no llega al usuario aunque el servidor ya la sirva.

Quita cualquier version anterior antes de poner la nueva: concatenarlas deja
``?v=123?v=abc``, que el navegador trata como una sola consulta rara y hace
imposible saber que version se esta sirviendo.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
ASSETS = ("app.js", "app.css")


def main(version: str | None = None) -> int:
    version = version or str(int(time.time()))
    texto = HTML.read_text(encoding="utf-8")
    for asset in ASSETS:
        # Se consume la consulta completa que hubiera, no solo la numerica.
        patron = re.compile(r"(/static/" + re.escape(asset) + r")(\?[^\"']*)?")
        texto = patron.sub(lambda m: f"{m.group(1)}?v={version}", texto)
    HTML.write_text(texto, encoding="utf-8")
    for linea in texto.splitlines():
        if any(a in linea for a in ASSETS):
            print("  " + linea.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
