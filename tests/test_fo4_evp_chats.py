"""FO3/FNV EvaluatePackage on Fallout 4 ends an NPC chat when it moves an actor in it to another package.

See: docs/fork/fo4_pipeline.md#evp-ends-npc-chats
"""

import pytest

from script_convert import helpers_fallout4 as H
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from tests.test_script_converter import conv_lines


def _convert(monkeypatch, source: str, target: str, extends: str = 'Quest') -> str:
    """`source` converted for Papyrus `target` from an FO3/FNV script extending `extends`."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', target)
    xref = CrossRefGraph()
    xref._is_fallout = True
    return conv_lines(ScriptConverter(xref), source, extends)


@pytest.mark.parametrize('source, extends, out', [
    ('CG04AmataREF.evp', 'Quest', 'TES4Polyfill.EvaluatePackage(CG04AmataREF)'),
    ('CG04OverseerREF.EvaluatePackage', 'Quest', 'TES4Polyfill.EvaluatePackage(CG04OverseerREF)'),
    ('evp', 'Actor', 'TES4Polyfill.EvaluatePackage(Self)'),
])
def test_evp_calls_the_polyfill_on_fallout4(monkeypatch, source, extends, out):
    """Both spellings, on a named actor or Self, call the polyfill."""
    assert _convert(monkeypatch, source, 'fallout4', extends) == out


def test_evp_stays_native_on_skyrim(monkeypatch):
    """The Skyrim target keeps the native call."""
    assert _convert(monkeypatch, 'CG04AmataREF.evp', 'skyrim') == 'CG04AmataREF.EvaluatePackage()'


def test_the_fallout4_polyfill_replaces_the_shared_wrapper():
    """The Fallout 4 polyfill has one EvaluatePackage, the one that hands an NPC chat to EndChatOnNewPackage."""
    with open('script_convert/static_scripts/TES4Polyfill.psc', encoding='utf-8') as src:
        out = H.fallout4_helper('TES4Polyfill', src.read())
    assert out.count('Function EvaluatePackage(Actor akActor) Global') == 1
    body = out.split('Function EvaluatePackage(Actor akActor) Global', 1)[1].split('EndFunction', 1)[0]
    assert body.index('NpcChat(akActor)') < body.index('akActor.EvaluatePackage()') < body.index('"EndChatOnNewPackage"')
    assert 'Scene Function NpcChat(Actor akActor) Global' in out
