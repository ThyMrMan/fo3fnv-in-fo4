"""The pinned zlib: the same compressed bytes on every Python, readable by Python's own zlib and gzip.

See: docs/fork/fo4_pipeline.md#pinned-zlib
"""

import gzip
import hashlib
import zlib

import pytest

from fo4_import.base import pinned_zlib as P

#: Inputs whose compressed bytes are pinned: text-like, mostly flat with noise, a short and an empty one.
SAMPLES = (b'the quick brown fox ' * 900 + bytes(range(256)) * 9, bytes(i * i % 7 for i in range(40000)), b'x', b'')


def digest() -> str:
    """SHA-256 over every SAMPLES entry compressed at levels 1, 6 and 9 and gzipped."""
    h = hashlib.sha256()
    for blob in SAMPLES:
        for level in (1, 6, 9):
            h.update(P.compress(blob, level))
        h.update(P.gzip(blob))
    return h.hexdigest()


def test_the_compressed_bytes_are_the_pinned_ones():
    """The library gives the recorded bytes, whatever this Python's own zlib is."""
    assert digest() == 'f97ba4f1648bf69e8666a4e75388c172f891d62ba72fefd43a1ce5e69bb93dcf'


@pytest.mark.parametrize('level', [1, 6, 9])
def test_python_reads_back_what_was_compressed(level):
    """zlib.decompress and gzip.decompress return every sample unchanged."""
    for blob in SAMPLES:
        assert zlib.decompress(P.compress(blob, level)) == blob
        assert gzip.decompress(P.gzip(blob, level)) == blob


@pytest.mark.skipif('ng' in zlib.ZLIB_RUNTIME_VERSION, reason='this Python is built on zlib-ng')
def test_the_bytes_match_stock_zlib():
    """On stock zlib, compress() and gzip() match zlib.compress, gzip.compress."""
    for blob in SAMPLES:
        assert P.compress(blob, 9) == zlib.compress(blob, 9)
        assert P.gzip(blob) == gzip.compress(blob, mtime=0)


def test_a_missing_library_names_how_to_build_it(monkeypatch, tmp_path):
    """Without the library the first call raises, naming the generator; nothing falls back to Python's zlib."""
    monkeypatch.setattr(P, 'LIBRARY', tmp_path / 'f3_zlib.dll')
    P.library.cache_clear()
    try:
        with pytest.raises(RuntimeError, match='gen_f3_zlib'):
            P.compress(b'data', 9)
    finally:
        P.library.cache_clear()
