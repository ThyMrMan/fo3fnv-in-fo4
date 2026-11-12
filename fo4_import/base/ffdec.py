"""JPEXS FFDec's script import: compile AS3 sources over the classes of an existing SWF.

FFDec's `-importScript` replaces the script of every class it finds a source
for (it cannot add classes), so our movies import over a skeleton of empty
shells (base.swf_skeleton).

See: docs/fork/fo4_casino_plan.md#toolchain-found
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS

REPO = Path(__file__).resolve().parents[2]
#: JPEXS FFDec's jar: F3NV_FFDEC, else the tools_ext checkout beside the repo.
FFDEC = Path(os.environ.get('F3NV_FFDEC', REPO.parent / 'tools_ext' / 'FFDec' / 'ffdec.jar'))


def source_digest(sources: Path, seed: bytes) -> str:
    """A 16-digit hash over `seed`, then every .as under `sources`: its path and bytes."""
    digest = hashlib.sha1(seed)
    for path in sorted(sources.rglob('*.as')):
        digest.update(path.relative_to(sources).as_posix().encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()[:16]


def import_scripts(movie: bytes, sources: Path, out: Path, ffdec: Path = FFDEC) -> Path:
    """Write `movie` with the classes in `sources` (.as files by package path) compiled over its own to `out`;
    raises RuntimeError with FFDec's output if it fails."""
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        shutil.copytree(sources, work / 'src' / 'scripts')
        (work / 'in.swf').write_bytes(movie)
        result = subprocess.run(['java', '-jar', str(ffdec), '-importScript', str(work / 'in.swf'),
                                 str(work / 'out.swf'), str(work / 'src')], capture_output=True, text=True,
                                **POPEN_FLAGS)
        built, log = work / 'out.swf', result.stdout + result.stderr
        if result.returncode or 'SEVERE' in log or not built.is_file():
            raise RuntimeError(f'FFDec failed to compile {sources}:\n{log}')
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(built, out)
    return out
