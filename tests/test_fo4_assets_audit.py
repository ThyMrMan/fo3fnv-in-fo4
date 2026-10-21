"""The FO4 asset audit fixes: materials and maps named by their contents, Elric one file at a time, the cache
tags, cache pruning, texture staging, weapon mesh names, Elric keyed without reading a NIF back, and a current
mesh written from its kept files.

See: docs/fork/fo4_tool_audit.md#meshes
"""

import os
import pathlib
import time
from types import SimpleNamespace

import pytest

from fo4_import.base import ba2_pack as BP
from fo4_import.nif import convert_static as C
from fo4_import.nif import elric as E
from fo4_import.nif import file as F
from fo4_import.nif.blocks import NONE
from fo4_import.nif.file import NifFile
from fo4_import.pipeline import code_tag as CT
from fo4_import.pipeline import elric_cache as EC
from fo4_import.pipeline import mesh_cache as MC
from fo4_import.pipeline import work_cache as WC
from fo4_import.spike import statics as ST

DAY = 86400


def _lit(diffuse='fnv/a.dds', normal='fnv/a_n.dds', decal=False, spec='') -> dict:
    """A BGSM dict with the given diffuse, normal, decal flag and specular map."""
    mat = dict(C.MATERIAL, decal=decal, textures=dict.fromkeys(C.BGSM_TEXTURES, ''))
    mat['textures'].update(diffuse=diffuse, normal=normal, smooth_spec=spec)
    return mat


def test_a_material_path_names_every_field_its_plain_name_leaves_out():
    """The usual normal map (x_n beside x or x_d) adds nothing; another normal, none, a decal or a glossiness each
    give a different path, as lit_material writes it."""
    assert C.lit_tags(_lit()) == '' and C.lit_tags(_lit('fnv/a_d.dds', 'fnv/a_n.dds')) == ''
    tags = [C.lit_tags(m) for m in (_lit(normal='fnv/b_n.dds'), _lit(normal=''), _lit(decal=True),
                                    _lit(spec='fnv/a_s_g60.dds'))]
    assert len(set(tags)) == 4 and '' not in tags
    plain, decal = (C.lit_material(['a.dds', 'a_n.dds'], {}, None, False, d, None).path for d in (False, True))
    assert plain == 'materials\\fnv\\a.bgsm' and decal == 'materials\\fnv\\a_decal.bgsm'


def test_a_spec_map_is_named_for_its_glossiness_and_the_name_reads_back():
    """FNV's default glossiness keeps x_s.dds; any other is in the name and spec_glossiness() returns it exactly."""
    assert C.spec_map_path('textures\\x\\Foo_n.dds') == 'fnv\\x\\foo_s.dds'
    for glossiness in (60.0, 12.5, 0.0, 10.000000149011612):
        path = C.spec_map_path('textures\\x\\foo_n.dds', glossiness)
        assert path != 'fnv\\x\\foo_s.dds' and C.spec_glossiness(path) == glossiness
    assert C.spec_glossiness('fnv\\a_s_gb_s.dds') == C.GLOSSINESS


def test_an_effect_material_names_its_blend_normal_and_env_map():
    """Glass at the usual blend with its own normal map adds nothing; another alpha test or an env map is named."""
    base = dict(C.GLASS_EFFECT, alpha_blend=True, src_blend=6, dst_blend=7, alpha_test=False, alpha_test_ref=0,
                textures={'base': 'fnv/g.dds', 'grayscale': '', 'envmap': '', 'normal': 'fnv/g_n.dds', 'env_mask': ''})
    assert C.effect_tags(base) == ''
    tags = {C.effect_tags(v) for v in (dict(base, alpha_test_ref=60), dict(base, alpha_test=True),
                                       dict(base, textures=dict(base['textures'], envmap='fnv/e.dds')))}
    assert len(tags) == 3 and '' not in tags


def test_a_retextured_material_takes_the_new_diffuse_and_its_tags():
    """A swap keeps the rest of the name; the old normal map, not b's, is named."""
    old, new = _lit(), _lit(diffuse='fnv/b.dds')
    assert C.retextured('materials\\fnv\\a_2s.bgsm', old, new) == f'materials\\fnv\\b_2s{C.lit_tags(new)}.bgsm'
    assert C.lit_tags(new)


def _node(nif: NifFile, collision: int = NONE) -> dict:
    """A root NiNode dict with collision object `collision`."""
    return {'name': nif.string('root'), 'extra': [], 'controller': NONE, 'flags': 0, 'translation': (0.0,) * 3,
            'rotation': E.IDENTITY, 'scale': 1.0, 'collision': collision, 'children': []}


def test_without_havok_renumbers_a_block_after_the_havok_and_refuses_one_it_cannot():
    """A parsed static block after the Havok input moves up with its references; an animation block there raises."""
    nif = NifFile()
    nif.blocks = [('NiNode', _node(nif, 1)), ('bhkCollisionObject', b'raw'), ('BSShaderTextureSet', {'textures': []})]
    nif.blocks[0][1]['extra'] = [2]
    E.without_havok(nif)
    assert [k for k, _ in nif.blocks] == ['NiNode', 'BSShaderTextureSet']
    assert nif.blocks[0][1]['extra'] == [1] and nif.blocks[0][1]['collision'] == NONE
    bad = NifFile()
    bad.blocks = [('NiNode', _node(bad, 1)), ('bhkCollisionObject', b'raw'), ('NiFloatData', {'keys': []})]
    with pytest.raises(ValueError):
        E.without_havok(bad)


def test_finish_gives_elric_each_file_rewritten_and_writes_a_failed_one_without_havok(tmp_path):
    """Elric gets every Havok NIF's bytes as written again; one it returns nothing for loses its Havok and fails."""
    nif = NifFile()
    nif.blocks = [('NiNode', _node(nif, 1)), ('bhkCollisionObject', b'raw')]
    path, plain = tmp_path / 'a.nif', tmp_path / 'b.nif'
    path.write_bytes(F.write(nif))
    plain.write_bytes(F.write(NifFile(blocks=[('NiNode', _node(NifFile()))])))
    seen = []
    assert E.finish([path, plain], lambda sources: seen.append(dict(sources)) or {}) == [path]
    assert list(seen[0].values()) == [F.write(F.read(F.write(nif)))]
    assert [k for k, _ in F.read(path.read_bytes()).blocks] == ['NiNode']


def test_code_tag_hashes_a_named_native_extension_and_reads_crlf_as_lf(tmp_path, monkeypatch):
    """A source naming native/dist/<name><suffix> is tagged with its bytes; a CRLF copy of a source keeps the tag;
    an IGNORED edge is not followed."""
    monkeypatch.setattr(CT, 'ROOT', tmp_path)
    monkeypatch.setattr(CT, 'NATIVE', tmp_path / 'native')
    (tmp_path / 'native').mkdir()
    (tmp_path / 'pkg').mkdir()
    extension = tmp_path / 'native' / f'_fake_native{CT.EXT_SUFFIX}'
    extension.write_bytes(b'one')
    (tmp_path / 'pkg' / '__init__.py').write_bytes(b'')
    (tmp_path / 'pkg' / 'other.py').write_bytes(b'X = 1\n')
    source = tmp_path / 'pkg' / 'mod.py'
    source.write_bytes(b"import pkg.other\nNAME = '_fake_native'\n")
    tags = []
    for change in (lambda: None, lambda: source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n')),
                   lambda: extension.write_bytes(b'two')):
        change()
        CT.code_tag.cache_clear()
        tags.append(CT.code_tag('pkg.mod'))
    CT.code_tag.cache_clear()
    assert tags[0] == tags[1] != tags[2]
    monkeypatch.setattr(CT, 'IGNORED', {('pkg.mod', 'pkg.other'): 'nothing'})
    assert 'pkg.other' not in CT.tagged_files('pkg.mod') and extension.name in CT.tagged_files('pkg.mod')


def test_the_mesh_key_covers_the_addon_mapping(tmp_path, monkeypatch):
    """The same NIF with another ADDN mapping converts again; a hit marks its entry used."""
    calls = []
    monkeypatch.setattr(MC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(MC, 'convert', lambda *a: calls.append(a) or C.Converted(NifFile()))
    nif = tmp_path / 'a.nif'
    nif.write_bytes(b'nif bytes')
    MC.cached_convert(nif, addons={14: 4})
    entry = next(p for p in (tmp_path / 'cache').rglob('*.pkl'))
    os.utime(entry, (time.time() - 30 * DAY,) * 2)
    MC.cached_convert(nif, addons={14: 4})
    MC.cached_convert(nif, addons={14: 5})
    assert len(calls) == 2 and calls[0][4] == {14: 4} and entry.stat().st_mtime > time.time() - DAY


def test_a_used_entry_is_touched_and_prune_drops_only_long_unused_files(tmp_path, monkeypatch):
    """lookup() marks an entry used; prune() deletes files unused for 14 days and keeps the rest."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'work')
    WC.store('site', 'fo4_import.pipeline.work_cache', (b'a',), 1)
    used = next(p for p in (tmp_path / 'work').rglob('*') if p.is_file())
    stale, recent = tmp_path / 'work' / 'site' / 'zz' / 'stale', tmp_path / 'elric' / 'recent'
    for path, age in ((used, 30), (stale, 15), (recent, 13)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.read_bytes() if path.exists() else b'x')
        os.utime(path, (time.time() - age * DAY,) * 2)
    assert WC.lookup('site', 'fo4_import.pipeline.work_cache', (b'a',)) == 1
    assert WC.prune((tmp_path / 'work', tmp_path / 'elric', tmp_path / 'missing')) == 1
    assert used.exists() and recent.exists() and not stale.exists()


def test_a_texture_is_staged_once_per_run_and_not_rewritten_or_repacked_while_current(tmp_path, monkeypatch):
    """A second call this run is skipped; the next run skips a current staged copy and Archive2; a staged own
    texture no build wrote is pruned, FaceGen kept; a changed source is written and repacked."""
    packs = []
    monkeypatch.setattr(BP.subprocess, 'run', lambda cmd, **_: packs.append(cmd) or pathlib.Path(cmd[2][3:]).write_bytes(
        str(len(packs)).encode()))
    data, source = tmp_path / 'data', tmp_path / 'src.dds'
    source.write_bytes(b'dds')
    plan = lambda: (f'copy {source.read_bytes()}', lambda target: target.write_bytes(source.read_bytes()))
    face = data / 'Textures' / 'Actors' / 'Character' / 'FaceCustomization' / 'P.esp' / 'x_d.dds'
    stale = data / BP.STAGING / 'Textures' / 'fnv' / 'old.dds'
    for path in (face, stale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    assert BP.stage_texture(data, 'fnv\\a.dds', plan) and not BP.stage_texture(data, 'fnv\\a.dds', plan)
    assert BP.pack_textures(data, 'P.esp') == 2 and not stale.exists() and len(packs) == 1
    assert not BP.stage_texture(data, 'fnv\\a.dds', plan)
    assert BP.pack_textures(data, 'P.esp') == 2 and len(packs) == 1
    source.write_bytes(b'new dds')
    assert BP.stage_texture(data, 'fnv\\a.dds', plan) and BP.pack_textures(data, 'P.esp') == 2 and len(packs) == 2
    assert (data / BP.STAGING / 'Textures' / 'fnv' / 'a.dds').read_bytes() == b'new dds'


def test_write_assets_names_a_weapon_mesh_apart_and_keeps_load_doors(tmp_path, monkeypatch):
    """`suffix` names the mesh `<name><suffix>.nif`; a load door is still `<name>load.nif`."""
    names = []
    monkeypatch.setattr(ST, 'cached_files', lambda *a: SimpleNamespace(animatable=True))
    monkeypatch.setattr(ST, 'write_files', lambda root, files, rel, data: names.append(rel) or (rel, None))
    ST.write_assets(tmp_path, 'Weapons\\Knife.nif', tmp_path, {}, animated=False, suffix='_weapon')
    ST.write_assets(tmp_path, 'Doors\\Door.nif', tmp_path, load=True)
    ST.write_assets(tmp_path, 'Clutter\\Cup.nif', tmp_path)
    assert names == ['weapons\\knife_weapon.nif', 'doors\\doorload.nif', 'clutter\\cup.nif']


def _cup() -> C.Converted:
    """A converted mesh: one root node, one BGSM, the FNV texture textures\\a.dds."""
    nif = NifFile()
    nif.blocks = [('NiNode', _node(nif))]
    return C.Converted(nif, materials={'materials\\fnv\\a.bgsm': dict(_lit(), root_material='')},
                       textures={'textures\\a.dds'})


def test_a_current_mesh_is_written_from_its_kept_files_and_a_file_holding_its_bytes_is_left_alone(tmp_path,
                                                                                                     monkeypatch):
    """Writing an unchanged mesh again neither converts, unpickles nor serializes it, and skips a material that
    already holds its bytes; a NIF Elric rewrote is written again; a changed texture or a pose converts again."""
    for module in (MC, WC):
        monkeypatch.setattr(module, 'CACHE', tmp_path / module.__name__)
    calls, real = [], (F.write, MC.cached_convert)
    monkeypatch.setattr(MC, 'convert', lambda *a: calls.append(a) or _cup())
    export, data = tmp_path / 'export', tmp_path / 'data'
    for rel, payload in (('meshes/clutter/cup.nif', b'fnv nif'), ('textures/a.dds', b'dds')):
        (export / rel).parent.mkdir(parents=True, exist_ok=True)
        (export / rel).write_bytes(payload)
    first = ST.write_assets(export, 'Clutter\\Cup.nif', data)
    nif, material = data / 'Meshes' / first[0], data / 'Materials' / 'fnv' / 'a.bgsm'
    raw = nif.read_bytes()
    nif.write_bytes(b'finished by Elric')
    os.utime(material, (time.time() - 30 * DAY,) * 2)
    monkeypatch.setattr(F, 'write', lambda *a: pytest.fail('serialized again'))
    monkeypatch.setattr(MC, 'cached_convert', lambda *a: pytest.fail('Converted read again'))
    assert ST.write_assets(export, 'Clutter\\Cup.nif', data) == first and nif.read_bytes() == raw
    assert material.stat().st_mtime < time.time() - DAY and len(calls) == 1
    monkeypatch.setattr(F, 'write', real[0])
    monkeypatch.setattr(MC, 'cached_convert', real[1])
    (export / 'textures' / 'a.dds').write_bytes(b'new dds')
    ST.write_assets(export, 'Clutter\\Cup.nif', data)
    ST.write_assets(export, 'Clutter\\Cup.nif', data, {'Cup': ((0.0, 0.0, 1.0), None)}, False, suffix='_weapon')
    assert len(calls) == 3


def test_a_havok_nif_reaches_disk_only_finished_and_an_unchanged_one_is_not_rewritten(tmp_path, monkeypatch):
    """write_mesh() holds a Havok NIF (mesh_bytes() gives it back) and writes nothing; finish() writes it finished;
    a rebuild of the same NIF leaves the file untouched; a NIF without Havok is written at once."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(EC, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(EC.elric, 'has_havok', lambda data: data != b'plain')
    monkeypatch.setattr(EC.elric, 'finish', lambda paths, run: [p.write_bytes(p.read_bytes() + b'+') for p in paths]
                        and [])
    path, plain = tmp_path / 'a.nif', tmp_path / 'b.nif'
    EC.write_mesh(path, b'one')
    assert not path.exists() and EC.mesh_bytes(path) == b'one'
    assert EC.finish([path]) == [] and path.read_bytes() == b'one+'
    os.utime(path, (1, 1))
    EC.write_mesh(path, b'one')
    assert path.read_bytes() == b'one+' and EC.finish([path]) == [] and path.stat().st_mtime == 1
    EC.write_mesh(plain, b'plain')
    assert plain.read_bytes() == b'plain'
