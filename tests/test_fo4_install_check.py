"""tools.validate.fo4_install_check on a fake machine: everything ready, then one requirement broken at a time.

See: docs/fork/fo4_plan_release.md#install-check
"""

import json
from pathlib import Path

import pytest

from tools.validate import fo4_install_check as IC

READY_VERSION = (*IC.GAME_VERSION, 0)
PLAY = 'Play'
BASE_MOD, DLC_MOD = 'F3NV - Fallout New Vegas', 'F3NV - Dead Money'


def touch(path: Path, text: str = '') -> Path:
    """Write `text` to `path`, its folders made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def stamp(folder: Path, plugin: str, status: str = 'finished') -> None:
    """A converted `plugin` in `folder` with its build stamp."""
    touch(folder / plugin)
    touch(folder / (plugin + IC.STAMP_SUFFIX), json.dumps({'status': status}))


def fake_mo2(root: Path, fallout4: Path) -> Path:
    """An MO2 instance managing `fallout4`, its profile enabling the README mods and two converted plugins."""
    mo2 = root / 'mo2'
    game = str(fallout4).replace('\\', '\\\\')
    touch(mo2 / 'ModOrganizer.ini', '\n'.join([
        '[General]', f'selected_profile=@ByteArray({PLAY})', f'gamePath=@ByteArray({game})', '[customExecutables]',
        '1\\title=F4SE', f'1\\binary={(fallout4 / IC.F4SE_LOADER).as_posix()}',
        '2\\title=Creation Kit', f'2\\binary={(fallout4 / "CreationKit.exe").as_posix()}']))
    mods = [name for name, _, _ in IC.REQUIRED_MODS] + [BASE_MOD, DLC_MOD]
    touch(mo2 / 'profiles' / PLAY / 'modlist.txt', '\n'.join(f'+{m}' for m in mods))
    touch(mo2 / 'profiles' / PLAY / 'plugins.txt', '*FalloutNV.esm\n*DeadMoney.esm\n')
    for name, file, _ in IC.REQUIRED_MODS:
        touch(mo2 / 'mods' / name / file.format(version='-'.join(map(str, READY_VERSION))))
    stamp(mo2 / 'mods' / BASE_MOD, IC.BASE_PLUGIN)
    for dll in IC.RUNTIME_DLLS:
        touch(mo2 / 'mods' / BASE_MOD / IC.PLUGINS / dll)
    stamp(mo2 / 'mods' / DLC_MOD, 'DeadMoney.esm')
    (mo2 / 'overwrite').mkdir()
    return mo2


@pytest.fixture
def machine(tmp_path: Path) -> IC.Machine:
    """A machine with everything the README lists, converted and in place."""
    fallout4, fnv = tmp_path / 'Fallout 4', tmp_path / 'Fallout New Vegas'
    for name in ('Fallout4.exe', 'CreationKit.exe', IC.F4SE_LOADER, 'f4se_1_11_240.dll'):
        touch(fallout4 / name)
    (fallout4 / 'Data').mkdir()
    touch(fnv / 'Data' / IC.BASE_PLUGIN)
    touch(fnv / 'Data' / 'DeadMoney.esm')
    return IC.Machine(fallout4, fnv, READY_VERSION, fake_mo2(tmp_path, fallout4), '', tmp_path, 32 * IC.GB)


def report(m: IC.Machine, free: int = 200 * IC.GB) -> dict:
    """{check name: (status, detail)} for `m`."""
    return {c.name: (c.status, c.detail) for c in IC.checks(m, free)}


def status(m: IC.Machine, name: str, free: int = 200 * IC.GB) -> str:
    """The status of check `name` for `m`."""
    return report(m, free)[name][0]


def test_ready_machine_passes(machine):
    """Every check is OK on the fake machine, the DLC counted."""
    got = report(machine)
    assert {s for s, _ in got.values()} == {'OK'}, got
    assert got['New Vegas DLC'][1].startswith('1 of 9')
    assert set(got) >= {name for name, _, _ in IC.REQUIRED_MODS} | {IC.BASE_PLUGIN, 'DeadMoney.esm', *IC.RUNTIME_DLLS}


@pytest.mark.parametrize('name, file', [('Creation Kit', 'CreationKit.exe'), ('F4SE', IC.F4SE_LOADER)])
def test_missing_game_file(machine, name, file):
    """A missing Creation Kit or F4SE loader is MISSING."""
    (machine.fallout4 / file).unlink()
    assert status(machine, name) == 'MISSING'


def test_wrong_versions(machine):
    """Another Fallout 4 version is WRONG VERSION, and so is F4SE built for this one."""
    old = IC.Machine(**{**machine.__dict__, 'version': (1, 10, 984, 0)})
    assert status(old, 'Fallout 4 version') == 'WRONG VERSION'
    assert status(old, 'F4SE') == 'WRONG VERSION'
    assert status(old, 'Address Library for F4SE Plugins') == 'MISSING'


@pytest.mark.parametrize('mod', [name for name, _, _ in IC.REQUIRED_MODS])
def test_required_mod_missing_or_off(machine, mod):
    """A README mod left out of the profile is NOT ENABLED; with its folder gone it is MISSING."""
    modlist = machine.mo2 / 'profiles' / PLAY / 'modlist.txt'
    modlist.write_text(modlist.read_text().replace(f'+{mod}\n', f'-{mod}\n'), encoding='utf-8')
    assert status(machine, mod) == 'NOT ENABLED'
    for path in sorted((machine.mo2 / 'mods' / mod).rglob('*'), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    assert status(machine, mod) == 'MISSING'


def test_enabled_xdi_conflicts(machine):
    """XDI.dll in an enabled mod is a CONFLICT (F3NV.dll's menu replaces it); disabled, it is not reported."""
    name, rel = IC.CONFLICTING_MODS[0]
    touch(machine.mo2 / 'mods' / 'XDI' / rel)
    modlist = machine.mo2 / 'profiles' / PLAY / 'modlist.txt'
    modlist.write_text(modlist.read_text() + '\n+XDI', encoding='utf-8')
    assert status(machine, name) == 'CONFLICT'
    modlist.write_text(modlist.read_text().replace('+XDI', '-XDI'), encoding='utf-8')
    assert name not in report(machine)


def test_mo2_problems(machine):
    """No instance is MISSING; a lost executable or profile is MISSING too."""
    ini = machine.mo2 / 'ModOrganizer.ini'
    ini.write_text(ini.read_text().replace('Creation Kit', 'CK'), encoding='utf-8')
    assert status(machine, 'MO2 "Creation Kit" executable') == 'MISSING'
    assert status(IC.Machine(**{**machine.__dict__, 'profile': 'Nope'}), 'MO2 profile') == 'MISSING'
    assert status(IC.Machine(**{**machine.__dict__, 'mo2': machine.work / 'none'}), 'Mod Organizer 2') == 'MISSING'


def test_fnv_missing(machine):
    """No FalloutNV.esm is MISSING."""
    (machine.falloutnv / 'Data' / IC.BASE_PLUGIN).unlink()
    assert status(machine, 'Fallout: New Vegas') == 'MISSING'


def test_low_disk_and_ram(machine):
    """Under 100 GB free or 32 GB of RAM is LOW."""
    assert status(machine, 'Free disk', free=40 * IC.GB) == 'LOW'
    assert status(IC.Machine(**{**machine.__dict__, 'ram': 16 * IC.GB}), 'RAM') == 'LOW'


def test_plugins_share_a_mod(machine):
    """A DLC built into the base game's mod folder is WRONG PLACE."""
    stamp(machine.mo2 / 'mods' / BASE_MOD, 'HonestHearts.esm')
    assert status(machine, 'HonestHearts.esm') == 'WRONG PLACE'


def test_plugin_in_overwrite_unfinished_or_unticked(machine):
    """A plugin in overwrite is WRONG PLACE, a running stamp UNFINISHED, an unticked plugin NOT ENABLED."""
    stamp(machine.mo2 / 'overwrite', 'LonesomeRoad.esm')
    stamp(machine.mo2 / 'mods' / DLC_MOD, 'DeadMoney.esm', status='running')
    plugins = machine.mo2 / 'profiles' / PLAY / 'plugins.txt'
    plugins.write_text('*DeadMoney.esm\n', encoding='utf-8')
    got = report(machine)
    assert (got['LonesomeRoad.esm'][0], got['DeadMoney.esm'][0], got[IC.BASE_PLUGIN][0]) == \
        ('WRONG PLACE', 'UNFINISHED', 'NOT ENABLED')


def test_dll_missing_and_nothing_converted(machine):
    """A DLL not there is MISSING; with no converted plugin the output check is NOT YET and passes."""
    for dll in IC.RUNTIME_DLLS:
        (machine.mo2 / 'mods' / BASE_MOD / IC.PLUGINS / dll).unlink()
        assert status(machine, dll) == 'MISSING'
    for mod in (BASE_MOD, DLC_MOD):
        for path in IC.all_moved_in(machine.mo2 / 'mods' / mod, '*' + IC.STAMP_SUFFIX):
            path.unlink()
    assert status(machine, 'Converted plugins') == 'NOT YET'
