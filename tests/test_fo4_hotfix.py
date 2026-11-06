"""The script hotfix: which scripts differ from a plugin's last build, and the hotfix mod's files shipped, kept while
newer than a build and cleared by a deploy of a later one.

See: docs/fork/fo4_hotfix.md#how-it-works
"""

import json

from tools.release import fo4_deploy, fo4_hotfix


def test_the_build_options_come_from_the_stamps_command(tmp_path):
    """--export, --data, --scripts and --plugin-dirs are read from the command the build stamp records."""
    plugin = tmp_path / 'DeadMoney.esm'
    command = ('fo4_import.pipeline.run --export export/DeadMoney.esm --out x --data temp/profile_data_dm '
               '--scripts temp/fo4_scripts/DeadMoney.esm --plugin-dirs temp/profile_data --world A B --whole')
    (tmp_path / 'DeadMoney.esm.build.json').write_text(json.dumps({'command': command}))
    options = fo4_hotfix.build_options(plugin)
    assert options == {'--export': ['export/DeadMoney.esm'], '--data': ['temp/profile_data_dm'],
                       '--scripts': ['temp/fo4_scripts/DeadMoney.esm'], '--plugin-dirs': ['temp/profile_data']}


def test_changed_scripts_and_new_helpers_ship_but_not_unused_conversions(tmp_path):
    """A script unlike its staged copy ships, an unchanged one does not; a helper the build never had ships (a
    changed helper may call it), a converted script the build never compiled does not (nothing runs it)."""
    scripts, stage = tmp_path / 'scripts', tmp_path / 'stage'
    scripts.mkdir()
    stage.mkdir()
    for name, now, then in (('TES4Polyfill', 'b', 'a'), ('F3NV_Greeting', 'a', 'a'),
                            ('F3NV_ReputationTab', 'new', None), ('FALLOUTNV_Unused', 'x', None)):
        (scripts / f'{name}.psc').write_text(now)
        if then is not None:
            (stage / f'{name}.psc').write_text(then)
    changed = fo4_hotfix.changed_sources(scripts, stage, 'FALLOUTNV_')
    assert [p.stem for p in changed] == ['F3NV_ReputationTab', 'TES4Polyfill']


def test_a_hotfix_replaces_its_last_and_a_later_build_clears_it(tmp_path):
    """Installing replaces the plugin's earlier files; a build begun before the hotfix keeps it, one begun after
    clears it and its manifest entry."""
    mod, built = tmp_path / 'F3NV - Hotfix', tmp_path / 'out'
    built.mkdir()
    for name in ('A', 'B'):
        (built / f'{name}.pex').write_bytes(name.encode())
    fo4_deploy.install_hotfix(mod, 'FalloutNV.esm', [built / 'A.pex'], 100.0)
    assert fo4_deploy.install_hotfix(mod, 'FalloutNV.esm', [built / 'B.pex'], 200.0) == 1
    assert sorted(p.name for p in (mod / 'Scripts').iterdir()) == ['B.pex']
    assert fo4_deploy.clear_hotfix(mod, 'FalloutNV.esm', 150.0) == 0
    assert fo4_deploy.clear_hotfix(mod, 'FalloutNV.esm', 250.0) == 1
    assert not (mod / 'Scripts' / 'B.pex').exists() and fo4_deploy.read_manifest(mod) == {}
