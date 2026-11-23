"""Filesystem anchors for asset_convert, independent of package depth.

Every module resolves the repo root and the bundled data directory from here,
so moving a module into a subpackage cannot silently repoint it: deriving them
per-module from `__file__` breaks the moment the module's depth changes, and
one `generated/` site created an empty directory rather than raising.
"""

import os
from pathlib import Path

#: Repository root: the directory holding `convert.py` and `external/`.
REPO = Path(__file__).resolve().parent.parent

#: Bundled data shipped inside the package (skeleton bones, body-wrap caches).
GENERATED = Path(__file__).resolve().parent / 'generated'

#: Names the folder holding the export, output and logs (the Fallout 4 app's work folder).
DATA_ENV = 'F3NV_DATA'


def data_root() -> Path:
    """The folder holding export/, output/ and logs/: $F3NV_DATA, else this checkout.
    See: docs/fork/fo4_gui.md#work-folder
    """
    return Path(os.environ.get(DATA_ENV) or REPO)


#: Default export, output and log trees (data_root() at import), overridden by an explicit root.
DATA = data_root()
EXPORT = DATA / 'export'
OUTPUT = DATA / 'output'
LOGS = DATA / 'logs'
#: The Fallout 4 build's caches.
FO4_CACHE = OUTPUT / 'fo4_cache'

#: Third-party executables committed under `external/`.
EXTERNAL = REPO / 'external'
HKXCMD = REPO / 'external' / 'hkxcmd' / 'hkxcmd.exe'
HKXCONV = REPO / 'external' / 'hkxconv' / 'hkxconv.exe'
BSARCH = REPO / 'external' / 'bsarch' / 'BSArch.exe'
LODGEN = REPO / 'external' / 'lodgen' / 'LODGenx64.exe'
MOPP_BRIDGE = REPO / 'external' / 'mopp_bridge' / 'dovah_hkp_mesh_mopp_bridge.exe'

#: Native helper programs built by `python native/build.py --programs`.
SPT_ENGINE_DUMP = REPO / 'native' / 'dist' / 'spt_engine_dump.exe'

#: Compiled native extension modules built by `python native/build.py`.
NATIVE_DIST = REPO / 'native' / 'dist'
