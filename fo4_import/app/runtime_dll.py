"""The F4SE plugins installed into the game's output: the committed builds in tes_runtime/dist (F3NV.dll and Cleanroom
UI's CleanroomDialogue.dll and CleanroomUI.dll) copied to F4SE/Plugins, so the output folder is a complete MO2 mod.

    py -3.14 -m fo4_import.app.runtime_dll --out <the game's output folder>

See: docs/fork/fo4_gui.md#extra-stages
"""

import argparse
import shutil
from pathlib import Path

from fo4_import.cleanroom import DIST
from tools.validate.fo4_install_check import PLUGINS, RUNTIME_DLLS

#: The committed DLLs the output gets.
DLLS = tuple(DIST / name for name in RUNTIME_DLLS)


def install(out: Path, dlls: tuple = DLLS) -> list:
    """Copy `dlls` into `out`/F4SE/Plugins; the copies."""
    folder = Path(out) / PLUGINS
    folder.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copy2(dll, folder / dll.name)) for dll in dlls]


def main() -> None:
    """Install the DLLs into --out and say where."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True, type=Path, help="The game's output folder")
    for copy in install(ap.parse_args().out):
        print(f'installed {copy}')


if __name__ == '__main__':
    main()
