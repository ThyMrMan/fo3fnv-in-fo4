"""The converter on Cleanroom UI's framework: its Pip-Boy movie installed, and our scripts calling only natives its
scripts declare and listening for events its DLL sends. The movie and CleanroomUI.dll are tested in Cleanroom UI.

See: docs/fork/spin_offs.md#move
"""

import re
from pathlib import Path

import pytest

from fo4_import import cleanroom
from fo4_import import pipboy_overlay as P
from fo4_import.spike import ammo_switch, condition, pipboy_tabs

STATIC = Path(__file__).parents[1] / 'script_convert' / 'static_scripts' / 'fallout4'
NEEDS_CHECKOUT = pytest.mark.skipif(cleanroom.checkout() is None, reason='no Cleanroom UI checkout')


def test_install_copies_cleanroom_uis_movie_and_drops_ours(tmp_path, monkeypatch):
    """install() copies CRUI_Pipboy.swf from Cleanroom UI's build and deletes an older build's F3NV_Pipboy.swf."""
    built = tmp_path / 'crui'
    (built / 'Interface').mkdir(parents=True)
    (built / P.FILES[0]).write_bytes(b'FWS')
    monkeypatch.setattr(cleanroom, 'build', lambda: built)
    data = tmp_path / 'data'
    (data / P.OLD_MOVIE).parent.mkdir(parents=True)
    (data / P.OLD_MOVIE).write_bytes(b'old')
    assert P.install(data) == 1 and (data / P.FILES[0]).read_bytes() == b'FWS' and not (data / P.OLD_MOVIE).exists()


def test_the_build_names_cleanroom_uis_native_scripts():
    """The scripts each build ships for the natives are Cleanroom UI's; no F3NV_ native script is left."""
    for name in (condition.NATIVES, condition.CARD_SCRIPT, ammo_switch.NATIVES, pipboy_tabs.NATIVES):
        assert name in cleanroom.SCRIPTS, name
    for name in ('Condition', 'ItemCard', 'Pipboy', 'PipboyAmmo', 'Sex'):
        assert not (STATIC / f'F3NV_{name}.psc').exists()


@NEEDS_CHECKOUT
def test_every_crui_call_is_a_native_its_script_declares():
    """Each CRUI_<Script>.<Function>( our scripts call is a function that script of Cleanroom UI's declares."""
    declared = {}
    for name, path in cleanroom.scripts().items():
        declared[name[:-4]] = set(re.findall(r'Function (\w+)\(', path.read_text(encoding='utf-8')))
    call = re.compile(r'(?<!Event )\b(CRUI_\w+)\.(\w+)\(')
    calls = {found for path in STATIC.rglob('*.psc') for found in call.findall(path.read_text(encoding='utf-8'))}
    assert {script for script, _ in calls} >= {'CRUI_Condition', 'CRUI_PipboyAmmo', 'CRUI_Pipboy', 'CRUI_Sex'}
    assert [call for call in calls if call[1] not in declared.get(call[0], ())] == []


@NEEDS_CHECKOUT
def test_our_scripts_listen_for_the_events_cleanroom_ui_sends():
    """F3NV_ConditionPlayer and F3NV_AmmoSwitch register for the external events CleanroomUI.dll sends."""
    dll = '\n'.join(p.read_text(encoding='utf-8') for p in (cleanroom.checkout() / 'dll' / 'framework').glob('*.cpp'))
    registered = {event for path in STATIC.glob('*.psc')
                  for event in re.findall(r'RegisterForExternalEvent\("(\w+)"', path.read_text(encoding='utf-8'))}
    for event in cleanroom.EVENTS:
        assert event in registered and f'"{event}"' in dll, event
