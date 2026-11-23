"""fo4_import.base.papyrus.unpack_headers on a fake install's Data/Scripts/Source.

See: docs/fork/fo4_spikes.md#spike-3-gate
"""

import zipfile
from pathlib import Path

from fo4_import.base.papyrus import FLAGS_FILE, unpack_headers


def zip_of(path: Path, files: dict) -> None:
    """A zip at `path` holding {name: text}."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        for name, text in files.items():
            z.writestr(name, text)


def test_unpacks_zips_and_f4se_once(tmp_path):
    """Every Creation Kit zip lands in Base, F4SE's .psc in F4SE; a second call reads nothing."""
    source, out = tmp_path / 'Source', tmp_path / 'headers'
    zip_of(source / 'Base' / 'Base.zip', {FLAGS_FILE: '', 'Actor.psc': 'base', 'Hardcore/HC.psc': ''})
    zip_of(source / 'DLC01' / 'DLC01.zip', {'DLC01Script.psc': ''})
    (source / 'F4SE.psc').write_text('f4se', encoding='utf-8')
    assert unpack_headers(source, out)
    assert {p.relative_to(out).as_posix() for p in out.rglob('*.psc')} == {
        'Base/Actor.psc', 'Base/Hardcore/HC.psc', 'Base/DLC01Script.psc', 'F4SE/F4SE.psc'}
    (source / 'F4SE.psc').unlink()
    assert unpack_headers(source, out)


def test_no_creation_kit_is_not_unpacked(tmp_path):
    """Without the Creation Kit's zips the headers are not there, and a later call tries again."""
    source = tmp_path / 'Source'
    source.mkdir()
    (source / 'F4SE.psc').write_text('', encoding='utf-8')
    assert not unpack_headers(source, tmp_path / 'headers')
    assert not (tmp_path / 'headers' / '.done').exists()
