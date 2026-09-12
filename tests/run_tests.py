"""Runner mínimo sin dependencias, para entornos sin pytest instalado.

Los tests están escritos en estilo pytest (funciones ``test_*`` con ``assert``
plano), así que ``pytest tests/`` funciona igual cuando esté disponible.

Uso:  python tests/run_tests.py [patrón]
"""

from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "core"))


def main(pattern: str = "") -> int:
    modules = sorted(p.stem for p in HERE.glob("test_*.py") if pattern in p.stem)
    passed = failed = 0
    failures: list[tuple[str, str]] = []

    for mod_name in modules:
        module = importlib.import_module(mod_name)
        names = [n for n in dir(module) if n.startswith("test_")]
        print(f"\n{mod_name}  ({len(names)} tests)")
        for name in names:
            try:
                getattr(module, name)()
            except Exception:
                failed += 1
                failures.append((f"{mod_name}::{name}", traceback.format_exc()))
                print(f"  FALLO  {name}")
            else:
                passed += 1
                print(f"  ok     {name}")

    for where, tb in failures:
        print(f"\n{'=' * 70}\n{where}\n{'=' * 70}\n{tb}")

    print(f"\n{passed} pasados, {failed} fallidos")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
