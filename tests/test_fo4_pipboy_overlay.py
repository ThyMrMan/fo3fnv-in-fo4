"""Our movie inside the Pip-Boy (spike 4): built by mxmlc, loaded by F3NV.dll under the name the build installs.

See: docs/fork/swf_framework.md#spikes
"""

import re
from pathlib import Path

import pytest

from asset_convert.ui.swf import Swf
from fo4_import import pipboy_overlay as P
from fo4_import.base import mxmlc

PIPBOY_CPP = Path(__file__).parents[1] / 'tes_runtime' / 'fo4_condition' / 'pipboy.cpp'


def test_the_dll_loads_the_movie_the_build_installs():
    """pipboy.cpp loads OVERLAY, the name install() writes under Interface."""
    source = PIPBOY_CPP.read_text(encoding='utf-8')
    assert re.search(r'OVERLAY = "([^"]+)"', source).group(1) == Path(P.MOVIE).name
    assert P.MOVIE.startswith('Interface/') and 'LoadOverlay(movie, root);' in source


@pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
def test_the_movie_builds_the_same_twice_and_keeps_a_line_on_the_item_card(tmp_path):
    """Two uncompressed, undated builds are identical; the movie fills the item card's InfoObj and redraws it."""
    raw = P.compile_movie(tmp_path / 'a.swf').read_bytes()
    assert raw == P.compile_movie(tmp_path / 'b.swf').read_bytes() and raw[:3] == b'FWS'
    assert not {t.code for t in Swf.parse(raw).tags} & set(mxmlc.DATED)
    for name in (b'F3NV_Pipboy', b'CurrentPage', b'ItemCard_mc', b'InfoObj', b'onDataChange', b'f3ui'):
        assert name in raw


@pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
def test_install_writes_the_movie_under_interface(tmp_path):
    """install() copies the built movie to <data>/Interface/F3NV_Pipboy.swf."""
    assert P.install(tmp_path) == 1 and (tmp_path / P.MOVIE).read_bytes()[:3] == b'FWS'
