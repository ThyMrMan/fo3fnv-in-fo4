"""Compress with our own copy of zlib (1.4, native/src/f3_zlib), so the same input gives the same bytes everywhere.

Python's zlib module is whatever the interpreter was built with (stock zlib, zlib-ng, the system's), and those
compress the same input to different bytes. Everything the FO4 build writes compressed goes through here.
Decompress with Python's zlib: inflating gives the same bytes from any of them.

See: docs/fork/fo4_pipeline.md#pinned-zlib
"""

import ctypes
import functools
import struct
import sys
import zlib
from pathlib import Path

#: The library tools/generators/gen_f3_zlib.py builds, committed in native/dist.
LIBRARY = Path(__file__).resolve().parents[2] / 'native' / 'dist' / {
    'win32': 'f3_zlib.dll', 'darwin': 'libf3_zlib.dylib'}.get(sys.platform, 'libf3_zlib.so')
#: Window bits: a zlib stream, and raw deflate (gzip() writes its own header and trailer).
ZLIB, RAW = 15, -15
#: The zlib version the library must report.
VERSION = b'1.4'
#: A gzip member's header with mtime 0 and OS 255 (unknown), as Python's gzip.compress(mtime=0) writes it.
GZIP_HEAD = struct.Struct('<4sIBB')


@functools.cache
def library() -> ctypes.CDLL:
    """The pinned zlib, loaded and typed once; RuntimeError when it is missing or another version."""
    if not LIBRARY.is_file():
        raise RuntimeError(f'{LIBRARY} is missing: build it with python -m tools.generators.gen_f3_zlib')
    lib = ctypes.CDLL(str(LIBRARY))
    lib.f3_deflate.argtypes = (ctypes.c_char_p, ctypes.POINTER(ctypes.c_ulong), ctypes.c_char_p, ctypes.c_ulong,
                               ctypes.c_int, ctypes.c_int)
    lib.f3_version.restype = ctypes.c_char_p
    if lib.f3_version() != VERSION:
        raise RuntimeError(f'{LIBRARY} is zlib {lib.f3_version()!r}, not {VERSION!r}: rebuild it')
    return lib


def deflate(data: bytes, level: int, bits: int) -> bytes:
    """`data` deflated at `level` with window bits `bits` (ZLIB or RAW); RuntimeError on a zlib error."""
    data = bytes(data)
    size = len(data)
    out = ctypes.create_string_buffer(size + (size >> 12) + (size >> 14) + (size >> 25) + 64)
    written = ctypes.c_ulong(len(out))
    error = library().f3_deflate(out, ctypes.byref(written), data, size, level, bits)
    if error:
        raise RuntimeError(f'pinned zlib failed with error {error} on {size} bytes')
    return ctypes.string_at(out, written.value)


def compress(data: bytes, level: int) -> bytes:
    """`data` as a zlib stream at `level`, like zlib.compress(data, level)."""
    return deflate(data, level, ZLIB)


def gzip(data: bytes, level: int = 9) -> bytes:
    """`data` as one gzip member, laid out as gzip.compress(data, level, mtime=0) writes it."""
    data = bytes(data)
    flags = 2 if level == 9 else 4 if level == 1 else 0
    head = GZIP_HEAD.pack(b'\x1f\x8b\x08\x00', 0, flags, 255)
    return head + deflate(data, level, RAW) + struct.pack('<II', zlib.crc32(data), len(data) & 0xFFFFFFFF)
