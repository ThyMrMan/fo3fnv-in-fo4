"""FNV's level-up art (PERK and AVIF ICON images) staged as our textures for our own level-up menu.

See: docs/fork/swf_framework.md#level-up
"""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from fo4_import.spike import level_up_icons as L

EXPORTS = Path(__file__).resolve().parents[1] / 'export'


def test_icons_are_the_distinct_perk_and_skill_images_as_texture_paths(monkeypatch):
    """Each PERK and AVIF ICON once, as a lowercase textures\\ path; records without one are left out."""
    records = {'PERK': [{'ICON': 'Interface\\Icons\\Perk_A.dds'}, {'ICON': 'interface\\icons\\perk_a.dds'}, {}],
               'AVIF': [{'ICON': 'Interface\\Icons\\Stats\\Skills_Unarmed.dds'}, {'FULL': 'Karma'}]}
    monkeypatch.setattr(L, 'export_records', lambda _export, sig: records[sig])
    assert L.icons(Path('x')) == ['textures\\interface\\icons\\perk_a.dds',
                                  'textures\\interface\\icons\\stats\\skills_unarmed.dds']


def test_stage_copies_the_images_the_export_has_and_counts_the_rest(monkeypatch, tmp_path):
    """Found images go through copy_texture; one the export lacks is counted, not copied."""
    monkeypatch.setattr(L, 'icons', lambda _export: ['textures\\a.dds', 'textures\\b.dds', 'textures\\gone.dds'])
    monkeypatch.setattr(L, 'export_file', lambda _export, rel: tmp_path / rel)
    for name in ('a.dds', 'b.dds'):
        (tmp_path / 'textures').mkdir(exist_ok=True)
        (tmp_path / 'textures' / name).write_bytes(b'DDS ')
    copied = []
    monkeypatch.setattr(L, 'copy_texture', lambda _export, _data, path: copied.append(path) or True)
    builder = SimpleNamespace(counts=Counter())
    L.stage(builder, Path('x'), tmp_path / 'data')
    assert copied == ['textures\\a.dds', 'textures\\b.dds']
    assert builder.counts == {'level-up icons staged': 2, 'level-up icon missing from the export': 1}


@pytest.mark.parametrize('game, count', [('FalloutNV.esm', 156), ('Fallout3.esm', 91)])
def test_every_image_of_the_games_is_in_their_export(game, count):
    """FNV's 156 and FO3's 91 distinct perk, skill and SPECIAL images, all in the export."""
    export = EXPORTS / game
    if not (export / 'PERK.txt').is_file():
        pytest.skip(f'no {game} export')
    paths = L.icons(export)
    assert len(paths) == count and any('s.p.e.c.i.a.l' in p for p in paths)
    assert all(L.export_file(export, p.replace('\\', '/')).is_file() for p in paths)
