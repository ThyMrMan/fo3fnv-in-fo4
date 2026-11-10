"""The F4SE plugin (F3NV.dll) installed into the game's output: the committed build in tes_runtime/dist copied to
F4SE/Plugins, so the output folder is a complete MO2 mod.

    py -3.14 -m fo4_import.app.runtime_dll --out <the game's output folder>

See: docs/fork/fo4_gui.md#extra-stages
"""

import argparse
import shutil
from pathlib import Path

from tools.validate.fo4_install_check import PLUGINS, RUNTIME_DLL

DIST = Path(__file__).resolve().parents[2] / 'tes_runtime' / 'dist' / RUNTIME_DLL


def install(out: Path, dll: Path = DIST) -> Path:
    """Copy `dll` into `out`/F4SE/Plugins; the copy."""
    target = Path(out) / PLUGINS / dll.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dll, target)
    return target


def main() -> None:
    """Install the DLL into --out and say where."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True, type=Path, help="The game's output folder")
    print(f'installed {install(ap.parse_args().out)}')


if __name__ == '__main__':
    main()
