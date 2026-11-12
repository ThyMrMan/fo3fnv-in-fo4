"""Our own Flash movies, compiled by Apache Flex's `mxmlc` from a menu's AS3 sources plus our f3ui library.

mxmlc is a real compiler (type errors and missing members fail the build).
It writes a build date into tags 41 (ProductInfo) and 77 (Metadata); both
are dropped and the movie is written uncompressed, so the same sources give the same bytes. The Flex SDK and
Adobe's playerglobal.swc are build-time tools, never shipped or committed.

See: docs/fork/swf_framework.md#toolchain
"""

import hashlib
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from asset_convert.ui.swf import Swf
from core.subprocess_flags import POPEN_FLAGS

REPO = Path(__file__).resolve().parents[2]
#: The Flex SDK 4.16.1 with playerglobal 11.2 (docs/fork/swf_framework.md#mxmlc-setup): F3NV_FLEX, else tools_ext.
FLEX = Path(os.environ.get('F3NV_FLEX', REPO.parent / 'tools_ext' / 'FlexSDK'))
#: Our shared AS3 library (package f3ui), on every movie's source path.
LIBRARY = Path(__file__).resolve().parent / 'as3'
#: Stage, frame rate, background, player and SWF version.
OPTIONS = ('-target-player=11.2', '-swf-version=15', '-static-link-runtime-shared-libraries=true', '-debug=false',
           '-default-size', '1280', '720', '-default-frame-rate', '30', '-default-background-color=0x000000')
#: The tags that carry the build date (ProductInfo, Metadata); FileAttributes' HasMetadata flag.
DATED, FILE_ATTRIBUTES, HAS_METADATA = (41, 77), 69, 0x10


def source_digest(sources: Path, seed: bytes) -> str:
    """A 16-digit hash over `seed`, then every .as under `sources`: its path and bytes."""
    digest = hashlib.sha1(seed)
    for path in sorted(sources.rglob('*.as')):
        digest.update(path.relative_to(sources).as_posix().encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()[:16]


def available(flex: Path = FLEX) -> bool:
    """Whether the Flex SDK's compiler is installed."""
    return (flex / 'lib' / 'mxmlc.jar').is_file()


def undated(raw: bytes) -> bytes:
    """`raw` without its build-date tags, the metadata flag cleared, uncompressed (zlib builds differ in output).
    See: docs/fork/swf_framework.md#mxmlc-setup
    """
    movie = Swf.parse(raw)
    movie.tags = [tag for tag in movie.tags if tag.code not in DATED]
    for tag in movie.tags:
        if tag.code == FILE_ATTRIBUTES:
            flags = struct.unpack_from('<I', tag.data)[0] & ~HAS_METADATA
            tag.data = struct.pack('<I', flags) + tag.data[4:]
    return movie.serialize(compress=False)


def compile_movie(out: Path, sources: Path, document: str, flex: Path = FLEX) -> Path:
    """Compile <sources>/<document>.as (document class `document`) with the library to `out`; raises
    RuntimeError with the compiler's output on any error or warning."""
    with tempfile.TemporaryDirectory() as work:
        built = Path(work) / 'out.swf'
        command = ['java', '-Xmx1024m', '-jar', str(flex / 'lib' / 'mxmlc.jar'), f'+flexlib={flex / "frameworks"}',
                   *OPTIONS, f'-source-path={sources}', f'-source-path+={LIBRARY}', f'-output={built}',
                   str(Path(sources) / f'{document}.as')]
        result = subprocess.run(command, capture_output=True, text=True, **POPEN_FLAGS)
        log = result.stdout + result.stderr
        if result.returncode or 'Warning:' in log or 'Error:' in log or not built.is_file():
            raise RuntimeError(f'mxmlc failed to compile {sources}:\n{log}')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(undated(built.read_bytes()))
    return out


def source_hash(sources: Path) -> str:
    """A hash of the menu's sources, the library, the options and output format."""
    seed = ' '.join(OPTIONS) + ' FWS' + source_digest(LIBRARY, b'f3ui')
    return source_digest(sources, seed.encode())


def built_movie(sources: Path, document: str, cache: Path, name: str) -> 'Path | None':
    """The movie of `sources`, cached as <cache>/<source_hash>/<name>, compiled when the Flex SDK is there; None
    when it is neither cached nor buildable."""
    cached = Path(cache) / source_hash(sources) / name
    if not cached.is_file() and available():
        compile_movie(cached, sources, document)
    return cached if cached.is_file() else None
