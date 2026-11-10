"""Plugins sharing one `scripts/` folder must not wipe each other's scripts.

See: docs/commentary/script_convert.md#wipe-output-dir
"""
import os

from script_convert import pipeline
from script_convert.context_setup import prepare_output_dir
from script_convert.ownership import read_owned, sibling_owned, write_owned


def _scripts(tmp_path, names):
    """A `scripts/source` tree holding `names` as .psc with matching .pex."""
    src = tmp_path / 'scripts' / 'source'
    src.mkdir(parents=True)
    for n in names:
        (src / f'{n}.psc').write_text('x', encoding='utf-8')
        (src.parent / f'{n}.pex').write_bytes(b'x')
    return src


def test_a_shared_folder_keeps_the_siblings_scripts(tmp_path):
    """Converting the ESP after the ESM deleted every one of the ESM's scripts. The ESP's own old .pex goes at
    once; its old source stays for write_psc to compare and goes at the run's end, unless written again."""
    src = _scripts(tmp_path, ['EsmOnly', 'EspOld', 'EspKept', 'Both'])
    write_owned(src, 'Mod.esm', ['EsmOnly', 'Both'])
    write_owned(src, 'Mod.esp', ['EspOld', 'EspKept', 'Both'])

    shared = prepare_output_dir(str(src), 'Mod.esp')

    assert shared == {'EsmOnly', 'Both'}
    assert sorted(p.stem for p in src.glob('*.psc')) == ['Both', 'EsmOnly', 'EspKept', 'EspOld']
    assert sorted(p.stem for p in src.parent.glob('*.pex')) == ['Both', 'EsmOnly']
    pipeline._record_ownership(str(src), {'owner': 'Mod.esp', 'shared': shared}, ['espkept', 'EspNew'])
    assert sorted(p.stem for p in src.glob('*.psc')) == ['Both', 'EsmOnly', 'EspKept']
    assert read_owned(src, 'Mod.esp') == {'espkept', 'EspNew'}


def test_an_unchanged_script_is_not_written_again(tmp_path):
    """write_psc leaves a file already holding the script's bytes (its time stays) and replaces one that
    differs; both writes are noted as written."""
    path = tmp_path / 'A.psc'
    pipeline._drain_written(), pipeline._drain_origins()
    pipeline.write_psc(str(tmp_path), 'A', 'ScriptName A\nInt x\n')
    first = path.read_bytes()
    os.utime(path, ns=(10 ** 18, 10 ** 18))
    pipeline.write_psc(str(tmp_path), 'A', 'ScriptName A\nInt x\n')
    assert path.read_bytes() == first and path.stat().st_mtime_ns == 10 ** 18
    pipeline.write_psc(str(tmp_path), 'A', 'ScriptName A\nInt y\n')
    assert path.read_bytes() == first.replace(b'Int x', b'Int y') and path.stat().st_mtime_ns != 10 ** 18
    assert pipeline._drain_written() == ['A', 'A', 'A'] and len(pipeline._drain_origins()) == 3


def test_an_unshared_folder_is_still_wiped_whole(tmp_path):
    """Stale scripts a plugin stopped generating must not survive."""
    src = _scripts(tmp_path, ['Stale', 'Unlisted'])
    write_owned(src, 'Oblivion.esm', ['Stale'])

    assert prepare_output_dir(str(src), 'Oblivion.esm') == set()
    assert not list(src.glob('*.psc'))
    assert not list(src.parent.glob('*.pex'))


def test_owned_lists_round_trip(tmp_path):
    """A written list reads back, and a sibling sees it."""
    src = _scripts(tmp_path, [])
    write_owned(src, 'A.esm', ['X', 'Y', 'X'])
    assert read_owned(src, 'A.esm') == {'X', 'Y'}
    assert sibling_owned(src, 'B.esp') == {'X', 'Y'}
    assert sibling_owned(src, 'A.esm') == set()
