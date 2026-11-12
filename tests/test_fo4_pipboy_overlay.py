"""Our movie inside the Pip-Boy: built by mxmlc, loaded by F3NV.dll under the name the build installs.

See: docs/fork/swf_framework.md#pipboy
"""

import re
from pathlib import Path

import pytest

from asset_convert.ui.swf import Swf
from fo4_import import pipboy_overlay as P
from fo4_import.base import mxmlc
from fo4_import.spike import condition as C

PIPBOY_CPP = Path(__file__).parents[1] / 'tes_runtime' / 'fo4_condition' / 'pipboy.cpp'


def test_the_dll_loads_the_movie_the_build_installs():
    """pipboy.cpp loads OVERLAY, the name install() writes under Interface."""
    source = PIPBOY_CPP.read_text(encoding='utf-8')
    assert re.search(r'OVERLAY = "([^"]+)"', source).group(1) == Path(P.MOVIE).name
    assert P.MOVIE.startswith('Interface/') and 'LoadOverlay(movie, root);' in source


def test_the_movie_calls_every_native_the_dll_registers_for_it():
    """Each native pipboy.cpp registers for the movie is called by it; the DLL no longer writes on the card."""
    source = PIPBOY_CPP.read_text(encoding='utf-8')
    movie = (P.SOURCES / 'F3NV_Pipboy.as').read_text(encoding='utf-8')
    natives = re.findall(r'RegisterFunction<\w+>\(plugin, movie, "(\w+)"\);', source)
    assert sorted(natives) == ['PipboyCardLines', 'PipboyList']
    assert all(f'dll.{name}()' in movie for name in natives)
    assert '"InfoObj", &lines' not in source and 'ShowLine(movie, card, g_health' not in source


def test_the_item_card_api_script_declares_the_native_card_cpp_registers():
    """F3NV_ItemCard.psc declares SetLine as card.cpp registers it, and the condition build ships the script."""
    card = (PIPBOY_CPP.parent / 'card.cpp').read_text(encoding='utf-8')
    script = (Path(__file__).parents[1] / 'script_convert' / 'static_scripts' / 'fallout4' /
              f'{C.CARD_SCRIPT}.psc').read_text(encoding='utf-8')
    assert f'SCRIPT = "{C.CARD_SCRIPT}"' in card and '"SetLine", SCRIPT, SetLine' in card
    assert 'Function SetLine(Form akItem, String asLabel, String asValue) Global Native' in script
    assert 'card.cpp' in (PIPBOY_CPP.parent / 'build.bat').read_text(encoding='utf-8')


@pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
def test_the_movie_builds_the_same_twice_and_fills_the_item_card(tmp_path):
    """Two uncompressed, undated builds are identical; the movie fills the item card's InfoObj and redraws it."""
    raw = P.compile_movie(tmp_path / 'a.swf').read_bytes()
    assert raw == P.compile_movie(tmp_path / 'b.swf').read_bytes() and raw[:3] == b'FWS'
    assert not {t.code for t in Swf.parse(raw).tags} & set(mxmlc.DATED)
    for name in (b'F3NV_Pipboy', b'CurrentPage', b'ItemCard_mc', b'InfoObj', b'onDataChange', b'PipboyCardLines', b'PipboyList', b'ListPanel', b'f3ui'):
        assert name in raw


@pytest.mark.skipif(not mxmlc.available(), reason='the Flex SDK is not installed')
def test_install_writes_the_movie_under_interface(tmp_path):
    """install() copies the built movie to <data>/Interface/F3NV_Pipboy.swf."""
    assert P.install(tmp_path) == 1 and (tmp_path / P.MOVIE).read_bytes()[:3] == b'FWS'
