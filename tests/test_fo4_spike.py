"""Spike 1b dialogue rules confirmed in game: Random piles, [Leave], walking away.

See: docs/fork/fo4_spikes.md#spike-1b
"""

import struct
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fo4_import.base.ba2 import Archives
from fo4_import.base import strings as ST
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.nif import collision as CO
from fo4_import.nif import file as nf
from fo4_import.spike import conditions as CD
from fo4_import.spike import dialogue as D
from fo4_import.spike import globals as GL
from fo4_import.spike import equipment as E
from fo4_import.spike import factions as FA
from fo4_import.spike import gun_choice as GC
from fo4_import.spike import sounds as SO
from fo4_import.spike import replacements as RP
from fo4_import.spike import imods as I
from fo4_import.spike import imagespace as IM
from fo4_import.spike import lighting_template as LT
from fo4_import.spike import emittance as EM
from fo4_import.spike import weathers as WT
from fo4_import.spike import exterior as EX
from fo4_import.spike import land_layers as LL
from fo4_import.spike import interiors as IN
from fo4_import.spike import navmesh as NM
from fo4_import.spike import placement as PL
from fo4_import.spike import poses as P
from fo4_import.spike import records as R
from fo4_import.spike import script as SC
from fo4_import import helpers_plugin as HP
from fo4_import.spike import skeleton as S
from fo4_import.spike import voice as V
from fo4_import.spike import cell as CB
from fo4_import.spike.cell import CellBuilder
from fo4_import import record_routes as RT
from tools.esm import fo4_record_census as C
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def _flags(value: int) -> dict:
    """An export INFO record with only DATA.Flags."""
    return {'DATA.Flags': str(value)}


def test_random_pile_gets_an_even_chain():
    """Three Random lines: the first two pass with 1/3 and 1/2, the last always."""
    pile = [(_flags(D.RANDOM), []), (_flags(D.RANDOM), []), (_flags(D.RANDOM | D.RANDOM_END), [])]
    extra = D.random_chain(pile)
    assert [g[0][0]['value'] for g in extra[:2]] == [100.0 / 3, 50.0]
    assert extra[2] == []


def test_random_pile_chains_each_condition_set_alone():
    """Sir/madame lines alternate in one pile; each set keeps a last line with no roll."""
    sir, madame = [[{'func': 'GetIsSex', 'p1': 0}]], [[{'func': 'GetIsSex', 'p1': 1}]]
    pile = [(_flags(D.RANDOM), sir), (_flags(D.RANDOM), madame), (_flags(D.RANDOM), sir),
            (_flags(D.RANDOM | D.RANDOM_END), madame)]
    extra = D.random_chain(pile)
    assert [g[0][0]['value'] for g in extra[:2]] == [50.0, 50.0]
    assert extra[2:] == [[], []]


def test_negate_or_group_becomes_and_of_negations():
    """NOT(a OR b) is NOT a AND NOT b; NOT(a AND b) is NOT a OR NOT b."""
    a = {'op_flags': 0x00, 'value': 1.0, 'func': 'GetIsID', 'p1': 1, 'p2': 0, 'run_on': 0, 'ref': 0}
    b = dict(a, func='GetInFaction', p1=2)
    spike = SimpleNamespace(report=[])
    assert D.Spike.negate(spike, [[a, b]], 'x') == [[dict(a, op_flags=0x20)], [dict(b, op_flags=0x20)]]
    assert D.Spike.negate(spike, [[a], [b]], 'x') == [[dict(a, op_flags=0x20), dict(b, op_flags=0x20)]]
    assert not spike.report


def test_menu_scene_ends_when_the_speaker_is_out_of_dialogue_range():
    """The Menu phase's completion condition is GetDistance(Player) > ACTV, run on the alias."""
    scene = R.pack_scen(0x01000800, 'Test', 0x01000801, 0, b'', 0x01000802)
    ctda = scene[scene.index(b'CTDA') + 6:][:32]
    op, value, func, p1, _, run_on, _, alias = struct.unpack('<B3xfH2xIIIIi', ctda)
    assert (op, value, func, p1, run_on, alias) == (R.OP_GREATER, R.DIALOGUE_DISTANCE, R.FUNC_GET_DISTANCE,
                                                    R.PLAYER, R.RUN_QUEST_ALIAS, 0)


def test_voice_job_names_the_fuz_by_plugin_voice_type_and_info(tmp_path):
    """An FNV recording of a line goes to Sound/Voice/<plugin>/<voice type>/<INFO id 00xxxxxx>_<n>.fuz."""
    folder = tmp_path / 'maleuniquedocmitchell'
    folder.mkdir()
    (folder / 'vfreeformg_vfreeformgoodsp_00107495_1.ogg').write_bytes(b'')
    rec = {'FormID': '00107495', 'ResponseCount': '1', 'Response[0].ResponseNumber': '1',
           'Response[0].ResponseText': '[SUCCEEDED] Of course.'}
    jobs = V.jobs([(0x02000869, rec)], [(folder, 'NPCMDocWeathers')], tmp_path / 'Data', 'Spike.esp')
    assert [(j[1].relative_to(tmp_path).as_posix(), j[2]) for j in jobs] == [
        ('Data/Sound/Voice/Spike.esp/NPCMDocWeathers/00000869_1.fuz', ' Of course.')]


def test_imad_moves_fnv_contrast_to_fo4_and_resets_hdr_slots():
    """FNV contrast (pair 18) is FO4's pair 19 with its key count; FNV's skin dimmer (pair 2) becomes FO4's identity."""
    keys = struct.pack('<6f', 0.0, 1.0, 0.5, 2.0, 1.0, 1.0)
    counts = [2] * 42
    counts[18 * 2] = counts[2 * 2] = 3
    dnam = struct.pack('<If42I', 1, 3.0, *counts) + bytes(244 - 176)
    body = pack_subrecord('EDID', b'T\0') + pack_subrecord('DNAM', dnam)
    body += pack_subrecord('\x12IAD', keys) + pack_subrecord('\x02IAD', keys)
    subs = dict(subrecords(I.convert(body)))
    ints = struct.unpack('<63I', subs[b'DNAM'])
    assert subs[b'\x13IAD'] == keys and ints[2 + 19 * 2] == 3
    assert subs[b'\x02IAD'] == I.MULT_KEYS and ints[2 + 2 * 2] == 2
    assert ints[61:] == (2, 2) and subs[b'NAM5'] == I.ZERO_KEYS


def test_seat_moves_from_the_start_marker_onto_docs_bed():
    """VCG01's start marker stands 13 units outside the twin bed; the seat goes 18 inside its mesh edge, facing out."""
    bed = Path('export/FalloutNV.esm/meshes/furniture/nv_bedtwin01.nif')
    if not bed.exists():
        pytest.skip('needs the FalloutNV.esm export')
    marker = ((2257.0427, 2318.2153, 7360.0), (0.0, 0.0, 3.1415987))
    (x, y, z), rot = P.seat_place(marker, [(((2281.6326, 2377.5889, 7392.0), (0.0, 0.0, 1.685404)), str(bed))])
    assert (round(x), round(y), z, rot) == (2257, 2352, 7360.0, marker[1])


def test_skeleton_box_top_lowered_and_bottom_kept():
    """Vanilla skeleton.nif's BSBound (top 128) goes to a top of 115 with z 0 still its bottom; nothing else moves."""
    if not (FALLOUT4_DIR / 'Data' / 'Fallout4 - Meshes.ba2').exists():
        pytest.skip('needs Fallout 4')
    source = chr(92).join(p.lower() for p in S.FOLDER + ('skeleton.nif',))
    raw = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2').read(source)
    out = S.lowered(raw, S.BOX_TOP)
    block = next(b for kind, b in nf.read(out).blocks if kind == 'BSBound')
    cz, hz = struct.unpack_from('<6f', block, len(block) - S.BOX_SIZE)[2::3]
    assert (round(cz + hz, 3), round(cz - hz, 3)) == (S.BOX_TOP, 0.0)
    assert len(out) == len(raw) and sum(a != b for a, b in zip(out, raw)) <= 8


def test_strings_parse_reads_zero_terminated_and_sized_entries():
    """A .STRINGS entry ends at its zero; a .DLSTRINGS one starts with its length."""
    plain = struct.pack('<II', 2, 8) + struct.pack('<IIII', 7, 0, 9, 4) + b'Bat\0Pin\0'
    sized = struct.pack('<II', 1, 8) + struct.pack('<II', 3, 0) + struct.pack('<I', 4) + b'Old\0'
    assert ST.parse(plain, False) == {7: b'Bat', 9: b'Pin'}
    assert ST.parse(sized, True) == {3: b'Old'}


def test_weapon_copy_takes_fnv_stats_and_resolves_template_strings():
    """FNV's name, weight, value and damage go on the FO4 template; its other FULLs and DESC become their text."""
    dnam = bytearray(100)
    dnam[E.DNAM_ANIM] = 1
    template = [(b'EDID', b'BaseballBat\0'), (b'VMAD', b'x'), (b'FULL', struct.pack('<I', 1)),
                (b'DESC', struct.pack('<I', 2)), (b'OBTE', b''), (b'FULL', struct.pack('<I', 3)), (b'DNAM', bytes(dnam))]
    written = []
    builder = SimpleNamespace(counts={'WEAP': 0}, writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x01ABCDEF, add_record=lambda sig, rec: written.append(rec)))
    eq = E.Equipment.__new__(E.Equipment)
    eq.builder, eq.fnv, eq.vanilla = builder, {}, {'BaseballBat': template}
    eq.table = {'WeapBaseballBat': RP.Replacement('Fallout4.esm', 'BaseballBat', 'stats')}
    eq.strings = {1: b'Baseball Bat', 2: b'Swing it', 3: b'Default'}
    rec = {'EditorID': 'WeapBaseballBat', 'FULL': 'Bat', 'DATA.Weight': '3.0', 'DATA.Value': '250', 'DATA.Damage': '22'}
    assert eq.weap(0x1234, rec) == 0x01ABCDEF
    subs = list(subrecords(written[0][24:]))
    assert [s for s, _ in subs] == [b'EDID', b'FULL', b'DESC', b'OBTE', b'FULL', b'DNAM']
    assert [b for s, b in subs if s in (b'EDID', b'FULL', b'DESC')] == [b'FNV_WeapBaseballBat\0', b'Bat\0',
                                                                         b'Swing it\0', b'Default\0']
    assert struct.unpack_from('<fIH', subs[-1][1], E.DNAM_WEIGHT) == (3.0, 250, 22)


def test_melee_weapon_on_fnv_mesh_drops_template_model_and_mods():
    """A melee copy points MODL and MOD4 at FNV's mesh with its bounds; FO4's model data and OBTE...STOP go."""
    dnam = bytearray(100)
    dnam[E.DNAM_ANIM] = 1
    template = [(b'EDID', b'RollingPin\0'), (b'OBND', bytes(12)), (b'FULL', struct.pack('<I', 1)),
                (b'MODL', b'Weapons/RollingPin/RollingPin01.nif\0'), (b'MODT', b'x'), (b'OBTE', bytes(4)),
                (b'OBTF', b''), (b'FULL', struct.pack('<I', 2)), (b'OBTS', b'y'), (b'STOP', b''),
                (b'MOD4', b'Weapons/RollingPin/RollingPin01_1.nif\0'), (b'MO4T', b'z'), (b'DNAM', bytes(dnam))]
    written, ours = [], ('fnv/weapons/rollingpin.nif', (-2, -5, -2, 2, 39, 2))
    builder = SimpleNamespace(counts={"WEAP": 0}, weapon_mesh=lambda model, pose: ours, export_dir=Path("."),
                              writer=SimpleNamespace(derive_formid=lambda site, key: 7,
                                                     add_record=lambda sig, rec: written.append(rec)))
    eq = E.Equipment.__new__(E.Equipment)
    eq.builder, eq.fnv, eq.vanilla, eq.strings = builder, {}, {'RollingPin': template}, {1: b'Rolling Pin'}
    eq.poses = {}
    eq.table = {'WeapRollingPin': RP.Replacement('Fallout4.esm', 'RollingPin', 'fnv')}
    eq.weap(1, {'EditorID': 'WeapRollingPin', 'FULL': 'Rolling Pin', 'Model.MODL': 'Weapons/RollingPin.NIF'})
    subs = list(subrecords(written[0][24:]))
    assert [s for s, _ in subs] == [b'EDID', b'OBND', b'FULL', b'MODL', b'MOD4', b'DNAM']
    assert dict(subs)[b'MODL'] == dict(subs)[b'MOD4'] == b'fnv/weapons/rollingpin.nif\0'
    assert struct.unpack('<6h', dict(subs)[b'OBND']) == ours[1]


def test_fnv_gun_wants_stance_mode_and_spread_from_its_record():
    """FNV's 9mm SMG (type 3, Flags1 2): a one-handed automatic; a two-handed rifle; a shotgun by its pellets."""
    assert GC.fnv_wants({'DNAM.FalloutAnimType': '3', 'DNAM.Flags1': '2', 'DNAM.ProjectileCount': '1'}) == (
        'pistol', True, False)
    assert GC.fnv_wants({'DNAM.FalloutAnimType': '5', 'DNAM.Flags1': '0', 'DNAM.ProjectileCount': '7'}) == (
        'rifle', False, True)
    assert GC.fnv_wants({'DNAM.FalloutAnimType': '8'})[0] is None


def test_omod_properties_end_its_data_and_obts_includes_follow_its_keywords():
    """Two 24-byte properties after an include; an OBTS with one keyword, its includes after two level bytes."""
    prop = struct.pack('<B3xB3xH2x4s4sf', 2, 0, GC.PROP_AUTOMATIC, struct.pack('<I', 1), bytes(4), 0.0)
    data = struct.pack('<II', 1, 2) + bytes(12) + struct.pack('<III', 0, 0, 0) + bytes(7) + prop + prop
    assert GC.properties(data) == [(2, 0, GC.PROP_AUTOMATIC, struct.pack('<I', 1))] * 2
    obts = struct.pack('<IIBBBBhBB', 2, 0, 0, 0, 0, 0, -1, 1, 1) + struct.pack('<I', 77) + bytes(2)
    obts += struct.pack('<IBBB', 0x10, 0, 0, 0) + struct.pack('<IBBB', 0x20, 0, 0, 0)
    assert GC.includes(obts) == [0x10, 0x20]


def test_layout_distance_prefers_the_nearer_magazine_and_muzzle():
    """Offsets count from each gun's trigger; the muzzle weighs MUZZLE_WEIGHT; a missing magazine counts 0."""
    ours = {'trigger': np.array([0.0, 2.0, 2.0]), 'mag': np.array([0.0, 15.0, 5.0]), 'muzzle': np.array([0.0, 24.0, 6.0])}
    near = {'trigger': np.array([0.0, 1.0, -2.0]), 'mag': np.array([0.0, 14.0, 1.0]), 'muzzle': np.array([0.0, 25.0, 2.0])}
    far = {'trigger': np.array([0.0, 17.0, 0.0]), 'mag': np.array([0.0, 21.0, 0.0]), 'muzzle': np.array([0.0, 43.0, 3.0])}
    assert GC._distance(ours, near) == pytest.approx(0.0 + GC.MUZZLE_WEIGHT * 4.0)
    assert GC._distance(ours, far) > GC._distance(ours, near)
    assert GC._distance(dict(ours, mag=None), far) == pytest.approx(GC.MUZZLE_WEIGHT * (4.0 ** 2 + 1.0 ** 2))


def test_replacement_table_lays_a_user_file_over_the_defaults(tmp_path):
    """A user entry replaces the default one; another plugin becomes a master and may only be an item."""
    user = tmp_path / 'mine.json'
    user.write_text('{"WeapBBGun": {"use": "BBGunMod.esp|BBGun", "as": "item"}}', encoding='utf-8')
    table = RP.load(user)
    assert table['WeapBBGun'] == RP.Replacement('BBGunMod.esp', 'BBGun', 'item')
    assert table['WeapBaseballBat'].mode == 'fnv' and table['VaultSuit21'].mode == 'item'
    assert RP.extra_masters(table) == ['BBGunMod.esp']
    user.write_text('{"WeapBBGun": {"use": "BBGunMod.esp|BBGun", "as": "stats"}}', encoding='utf-8')
    with pytest.raises(ValueError):
        RP.load(user)


def test_another_plugins_formid_is_renumbered_to_our_masters():
    """Its own record takes its place in our masters; its override of a Fallout4.esm record stays index 0."""
    ours = ['Fallout4.esm', 'TES4Helpers.esl', 'XDI.esm', 'BBGunMod.esp']
    assert RP._ours(0x01000F99, ['Fallout4.esm'], 'BBGunMod.esp', ours) == 0x03000F99
    assert RP._ours(0x00004822, ['Fallout4.esm'], 'BBGunMod.esp', ours) == 0x00004822
    with pytest.raises(ValueError):
        RP._ours(0x01000F99, ['Fallout4.esm', 'Other.esm'], 'BBGunMod.esp', ours)


def test_fnv_alternate_textures_list_shape_index_and_texture_set():
    """Entries are (3D name, TXST, 3D index); the index decides (FNV's names are sometimes another shape's)."""
    body = struct.pack('<I', 2)
    for name, txst, index in ((b'pipboyoff', 0x10, 5), (b'Arms', 0x99, 0)):
        body += struct.pack('<I', len(name)) + name + struct.pack('<Ii', txst, index)
    sets = {0x10: ('armor\\a.dds', 'armor\\a_n.dds')}
    assert E._alternates(body, sets) == [(5, ('armor\\a.dds', 'armor\\a_n.dds'))]


def test_copy_puts_a_material_swap_right_after_its_model():
    """The template has no MO2S; the copy writes the swap after MOD2, where vanilla armor has it."""
    eq = E.Equipment.__new__(E.Equipment)
    eq.strings, eq.vanilla = {}, {}
    template = [(b'EDID', b'X\0'), (b'MOD2', b'old.nif\0'), (b'BOD2', b'\0' * 4)]
    out = eq._copy({'EditorID': 'Y'}, {b'MOD2': b'new.nif\0', b'MO2S': b'\1\0\0\3'}, source=template)
    assert [sig for sig, _ in out] == [b'EDID', b'MOD2', b'MO2S', b'BOD2']


def test_an_fnv_sound_becomes_a_descriptor_of_its_kind(tmp_path):
    """A looping FNV SOUN copies the loop template's playback, its folder's files named .wav under FX\\FNV."""
    folder = tmp_path / 'sound' / 'fx' / 'amb' / 'hum'
    folder.mkdir(parents=True)
    for name in ('hum_01.wav', 'hum_02.ogg', 'notes.txt'):
        (folder / name).write_bytes(b'x')
    added = []
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x01000800, add_record=lambda sig, rec: added.append(rec))
    sounds = object.__new__(SO.Sounds)
    sounds.builder = SimpleNamespace(writer=writer, data_dir=tmp_path / 'Data', counts={'SNDR': 0})
    sounds.export_dir, sounds.jobs, sounds.made, sounds.markers = tmp_path, [], {}, {}
    sounds.records = {0x123: {'EditorID': 'Hum', 'FNAM.Filename': 'fx\\amb\\hum', 'SNDD.Flags': str(SO.LOOP)}}
    sounds.templates = {SO.LOOP_TEMPLATE: {b'CNAM': b'C', b'LNAM': b'LOOP'}, SO.ONE_SHOT_TEMPLATE: {b'LNAM': b'ONCE'}}
    assert sounds.descriptor(0x123) == 0x01000800
    assert b'LOOP' in added[0] and b'ONCE' not in added[0]
    assert b'data\\Sound\\FX\\FNV\\fx\\amb\\hum\\hum_01.wav' in added[0] and b'hum_02.wav' in added[0]
    assert b'notes' not in added[0] and [job[1].suffix for job in sounds.jobs] == ['.xwm', '.xwm']



def _ids():
    """A stand-in CellBuilder carrying only what fnv_id and new_id read."""
    builder = SimpleNamespace(writer=FO4PluginWriter(masters=['Fallout4.esm', 'A.esl', 'B.esm']), owned=Counter(),
                              top=0x800)
    return builder, CellBuilder.fnv_id, CellBuilder.new_id


def test_a_converted_fnv_record_keeps_its_object_id():
    """FNV's id under our plugin's index, and the header's next id clears it."""
    builder, fnv_id, _ = _ids()
    assert fnv_id(builder, '0010C6F2') == 0x0310C6F2 == fnv_id(builder, 0x0010C6F2)
    assert builder.top == 0x10C6F3


def test_a_generated_formid_depends_only_on_its_owner():
    """The same owners give the same ids in any order; one owner's repeats differ."""
    first, _, new_id = _ids()
    a, a2, b = new_id(first, 'DIAL x'), new_id(first, 'DIAL x'), new_id(first, 'DIAL y')
    second = _ids()[0]
    assert (new_id(second, 'DIAL y'), new_id(second, 'DIAL x'), new_id(second, 'DIAL x')) == (b, a, a2)
    assert len({a, a2, b}) == 3


def test_an_edge_link_inside_the_build_gains_the_facing_edge_and_one_outside_is_opened():
    """A's edge 1-2 links to B's triangle (whose edge 2-0 faces back); its edge 2-0 links to C, not built."""
    a = [(0, 0, 0), (10, 0, 0), (0, 10, 0)], [[0, 1, 2, -1, 0, 1, 0x6, 0]], [(0, 'B', 0), (0, 'C', 0)]
    b = [(10, 0, 0), (10, 10, 0), (0, 10, 0)], [[0, 1, 2, -1, -1, -1, 0, 0]], []
    out = NM.linked({'A': a, 'B': b})
    assert out['A'][1:] == ([[0, 1, 2, -1, 0, -1, 0x2, 0]], [(0, 'B', 0, 2)])
    assert out['B'][1:] == ([[0, 1, 2, -1, -1, -1, 0, 0]], [])


def test_the_facing_edge_holds_the_middle_of_a_split_border():
    """A border split differently on each side: the edge under the link's midpoint, not a shared corner."""
    verts, tri = [(0, 0, 0), (0, 20, 0), (-10, 10, 0)], [0, 1, 2]
    assert NM.facing(((0, 4, 0), (0, 8, 0)), verts, tri) == 0


def test_an_exterior_pathing_cell_stores_y_then_x():
    """As all 7,113 Fallout4.esm exterior navmeshes do."""
    assert struct.pack('<I', NM.grid_parent(-18, 3)) == struct.pack('<hh', 3, -18)


def test_interiors_reached_follow_doors_from_the_block_and_through_interiors():
    """Block door -> saloon -> cellar is reached; a door into another worldspace and an unlinked cell are not."""
    cells = {c: {'FormID': c} for c in ('DOC', 'SALOON', 'CELLAR', 'FAR')}
    door = lambda fid, cell, to: {'FormID': fid, 'ParentCELL': cell, 'XTEL.Door': to}
    refs = [door('d1', 'BLOCK', 'd2'), door('d2', 'SALOON', 'd1'), door('d3', 'SALOON', 'd4'),
            door('d4', 'CELLAR', 'd3'), door('d5', 'CELLAR', 'd6'), door('d6', 'OTHERWORLD', 'd5'),
            {'FormID': 'r', 'ParentCELL': 'FAR'}]
    found = IN.reached(cells, refs, cells['DOC'], [refs[0]])
    assert [c['FormID'] for c in found] == ['DOC', 'CELLAR', 'SALOON']


def test_a_global_property_takes_fallout4s_engine_global_beside_the_helper_globals():
    """GameHour fills from Fallout4.esm (0x38, as in FNV); only engine globals qualify; helper globals stay."""
    forms = SC.base_forms(1)
    assert SC.fill([('GlobalVariable', 'GameHour')], forms, 1) == {'GameHour': 0x38}
    assert all(fid < 0x800 for fid in SC.fo4_forms()['GlobalVariable'].values())
    assert set(HP.helper_forms(1)['GlobalVariable']) <= set(forms['GlobalVariable'])


def test_a_mopp_over_a_list_is_not_a_mesh_but_one_over_strips_is():
    """CookingStove's MOPP wraps a list (hull + MOPP mesh): its shapes convert one by one, not as one mesh."""
    strips = type('bhkPackedNiTriStripsShape', (), {})()
    mopp = type('bhkMoppBvTreeShape', (), {})
    over_strips, over_list = mopp(), mopp()
    over_strips.shape, over_list.shape = strips, type('bhkListShape', (), {})()
    assert CO.is_mesh(strips) and CO.is_mesh(over_strips) and not CO.is_mesh(over_list)


def test_still_collision_gets_both_sides_once_and_moving_collision_keeps_one():
    """FacRmWallONLY01's inward faces: a fixed body adds each reversed face not already there; a dynamic one none."""
    a, b, c = (0, 0, 0), (1, 0, 0), (0, 1, 0)
    soup = ([(a, b, c), (a, c, b), (b, c, (1, 1, 0))], [1, 2, 3])
    tris, mats = CO.both_sides(soup, SimpleNamespace(motion_system=7))
    assert len(tris) == 4 and tris[3] == (b, (1, 1, 0), c) and mats == [1, 2, 3, 3]
    assert CO.both_sides(soup, SimpleNamespace(motion_system=1)) == soup


def test_a_phantom_trigger_volume_is_left_out_of_the_collision():
    """The bear trap's bhkSimpleShapePhantom (its pressure-plate trigger) adds no block."""
    phantom = SimpleNamespace(collision_object=SimpleNamespace(body=type('bhkSimpleShapePhantom', (), {})()))
    root = SimpleNamespace(collision_object=None, tree=lambda: [root, phantom])
    nif = SimpleNamespace(blocks=[('BSFadeNode', {'children': []})])
    CO.collision_nodes(nif, root, 0, 0)
    assert nif.blocks == [('BSFadeNode', {'children': []})]


def test_an_interiors_height_fog_takes_fnvs_fog_colour_not_the_templates():
    """QASmoke's green height fog showed in Doc's house (7,400 units up); both height-fog colours are FNV's fog."""
    keys = ('Ambient', 'Directional', 'Fog')
    cell = {f'XCLL.{k}{c}': v for k in keys for c, v in zip('RGB', (77, 62, 32))}
    cell.update({f'XCLL.{k}': 1 for k in ('FogNear', 'FogFar', 'DirectionalRotXY', 'DirectionalRotZ',
                                          'DirectionalFade', 'FogClipDist', 'FogPower')})
    out = CB.lighting(cell, bytes(range(136)))
    assert out[100:108] == bytes((77, 62, 32, 0)) * 2 and out[108:] == bytes(range(108, 136))
    assert struct.unpack_from('<f', out, 76)[0] == 1.0 and struct.unpack_from('<f', out, 32)[0] == 0.0
    assert struct.unpack_from('<f', out, 36)[0] == pytest.approx(IM.DISPLAY_GAMMA)


def test_an_interior_takes_the_fields_its_inherit_flags_name_from_its_lighting_template(monkeypatch):
    """Doc's house (LNAM 0x9F) showed its unused own fog (100-1,500) instead of its template's (64-5,000)."""
    data = bytes((31, 31, 45, 0, 32, 30, 21, 0, 73, 68, 48, 0)) + struct.pack('<2f2i3f', 64, 5000, 0, 267, 1, 5000, 0.84)
    monkeypatch.setattr(LT, 'inherit_flags', lambda: {0x103DF9: 0x9F})
    monkeypatch.setattr(LT, '_templates', lambda _: {'0008F58B': data})
    cell = {'FormID': '00103DF9', 'LTMP.LightingTemplate': '0008F58B', 'XCLL.FogNear': '100.0', 'XCLL.FogFar': '1500.0',
            'XCLL.FogPower': '0.6', 'XCLL.AmbientR': '47'}
    out = LT.resolved(Path('.'), cell)
    assert (out['XCLL.FogNear'], out['XCLL.FogFar'], out['XCLL.AmbientR']) == ('64.0', '5000.0', '31')
    assert out['XCLL.FogPower'] == '0.6'


def test_a_weathers_fog_colour_fills_fo4s_near_far_and_high_fogs_and_fog_power_is_gamma_scaled():
    """FNV fog colour lands in FO4 types 1, 12, 17 and 18; fog powers x 2.2, the rest of FNAM kept."""
    fnv = bytearray(240)
    fnv[24:40] = bytes((9, 9, 9, 0)) * 4
    out = WT.colour_table(bytes(608), bytes(fnv))
    assert all(out[t * 32:t * 32 + 32] == bytes((9, 9, 9, 0)) * 8 for t in (1, 12, 17, 18))
    assert out[2 * 32:3 * 32] == bytes(32)
    fog = WT.fog_table(struct.pack('<18f', *range(18)), struct.pack('<6f', 10, 20, 30, 40, 1, 2))
    assert struct.unpack('<18f', fog)[:6] == pytest.approx((10, 20, 30, 40, IM.DISPLAY_GAMMA, 2 * IM.DISPLAY_GAMMA))
    assert struct.unpack('<18f', fog)[6:] == tuple(range(6, 18))


def test_a_region_emittance_weather_takes_fnvs_sunlight_at_each_fo4_time_of_day():
    """FO4's eight times take FNV's four (early/late sunrise and sunset as sunrise and sunset) in two entries."""
    fnv = bytearray(240)
    fnv[4 * 24:4 * 24 + 16] = bytes((1, 1, 1, 0, 2, 2, 2, 0, 3, 3, 3, 0, 4, 4, 4, 0))
    out = WT.colour_table(bytes(range(256)) * 2 + bytes(96), bytes(fnv), EM.SUNLIGHT)
    expected = b''.join(bytes((t, t, t, 0)) for t in (1, 2, 3, 4, 1, 1, 3, 3))
    assert out[4 * 32:5 * 32] == expected == out[9 * 32:10 * 32]
    assert out[:4 * 32] == (bytes(range(256)) * 2)[:4 * 32]


def test_a_fixed_exposure_shows_exposed_colours_as_fnvs_straight_display():
    """Vikki and Vance washed out under 0.5-15x auto exposure; pinned exposure plus the LUT show c as c^(1/2.2)."""
    tonemap_e, grey = 0.02, 0.18
    exposure = IM.fixed_exposure(tonemap_e, grey)
    c = np.array([0.01, 0.05, 0.18, 0.5])
    shown = IM.fnv_tone(IM.fo4_display(exposure * c, tonemap_e), tonemap_e, grey)
    assert exposure == pytest.approx(1.40, abs=0.01) and shown == pytest.approx(c ** (1 / 2.2), abs=1e-4)


def test_a_portal_names_its_rooms_by_fo4_id_and_a_room_keeps_its_bounds(monkeypatch):
    """XPOD's two rooms are renumbered; a portal drops XMBO; a room marker keeps XMBO before XPRM; XRGD carries."""
    raw = {0x5A: {b'XPOD': struct.pack('<2I', 0x57, 0x58), b'XPRM': b'p' * 32, b'XMBO': b'b' * 12},
           0x57: {b'XPRM': b'p' * 32, b'XMBO': b'b' * 12}, 0x99: {b'XRGD': b'r' * 28}}
    monkeypatch.setattr(PL, 'fields', lambda: {fid: list(found.items()) for fid, found in raw.items()})
    ids = {'00000057': 0x03000057, '00000058': 0x03000058}
    assert PL.placement(0x5A, ids) == (pack_subrecord('XPRM', b'p' * 32)
                                       + pack_subrecord('XPOD', struct.pack('<2I', 0x03000057, 0x03000058)))
    assert PL.placement(0x57, ids) == pack_subrecord('XMBO', b'b' * 12) + pack_subrecord('XPRM', b'p' * 32)
    assert PL.placement(0x99, ids) == pack_subrecord('XRGD', b'r' * 28) and PL.placement(0x1, ids) == b''


def test_a_light_keeps_fnvs_falloff_and_fov_and_a_slow_flicker_moves_at_half_speed():
    """Falloff exponent and FOV are FNV's; flicker slow (0x40) doubles the period; a steady light does not move."""
    rec = {'DATA.Radius': '256', 'DATA.Color.R': '255', 'DATA.Color.G': '200', 'DATA.Color.B': '100',
           'DATA.Flags': str(0x40), 'DATA.FalloffExponent': '2.0', 'DATA.FOV': '60.0'}
    assert CB.light_data(rec) == (256, (255, 200, 100), CB.LIGHT_BASE | 0x8, 2.0, 60.0, (0.66, 0.45, 8.0))
    assert CB.light_data(dict(rec, **{'DATA.Flags': '0'}))[5] == CB.STEADY
    assert CB.light_data(dict(rec, **{'DATA.Flags': str(0x80)}))[5] == (0.33, 0.45, 0.0)


def test_a_locked_reference_keeps_its_level_and_key_and_an_unlocked_one_gets_no_lock():
    """FNV XLOC level 0 (very easy) stays 0, FO4's novice; the key is made through items; no XLOC, no lock."""
    builder = SimpleNamespace(items=SimpleNamespace(item=lambda fid: 0x0300ABCD if fid == 0xABCD else None),
                              counts=Counter())
    ref = {'XLOC.Level': '0', 'XLOC.Key': '0000ABCD', 'XLOC.Flags': '4'}
    assert CB._lock(builder, ref) == pack_subrecord('XLOC', struct.pack('<B3xIB3xI', 0, 0x0300ABCD, 4, 0))
    assert CB._lock(builder, {}) == b'' and builder.counts['locked references'] == 1


def test_the_census_flags_an_unrouted_type_and_a_missing_target():
    """A type with no route and a route to a type Fallout 4 lacks are both problems."""
    fo4 = {target for target, _ in RT.ROUTES.values() if target}
    assert C.problems(set(RT.ROUTES), fo4) == []
    assert C.problems({'ZZZZ'}, fo4 - {'COBJ'}) == ['ZZZZ: no route', 'RCPE: target COBJ is not a Fallout 4 type']


def test_painted_layers_become_shares_that_never_pass_one():
    """A layer's share is its opacity times what the layers above leave showing."""
    shares = LL.layer_weights([{0: 1.0, 1: 0.5}, {0: 0.5}])
    assert shares == [{0: 0.5, 1: 0.5}, {0: 0.5}]


def test_texture_zero_draws_fnvs_default_land_texture_not_fo4s():
    """FNV draws DirtWasteland01 for texture 0 and a quadrant without a base; FO4's own default is the pale,
    grassless CommonwealthDefault01. Texture 0 becomes the lowest FNV LTEX using FNV's default."""
    ext = EX.Exterior.__new__(EX.Exterior)
    ext.textures = {'00015457': {'ICON': 'DirtWasteland01.dds'}, '00000A8A': {'ICON': 'DirtWasteland01.dds'},
                    '00020524': {'ICON': 'DirtPathWasteland01.dds'}}
    ext.made, written = {}, []
    ext._write_ltex = lambda builder, rec, data_dir: written.append(rec) or 0x03000A8A
    assert ext._ltex(None, '00000000', None) == 0x03000A8A and ext._ltex(None, None, None) == 0x03000A8A
    assert written == [ext.textures['00000A8A']]


def _mixes(left: dict, right: dict) -> dict:
    """A cell: bottom quadrants `left`, `right` ({texture: share}), top ones 'a'."""
    flat = lambda shares: {t: np.full(LL.QUAD_POINTS, s) for t, s in shares.items()}
    return {(0, 0): {0: flat(left), 1: flat(right), 2: flat({'a': 1.0}), 3: flat({'a': 1.0})}}


def test_a_base_change_at_a_quadrant_border_is_averaged_on_the_shared_vertices():
    """FNV switches base at a border; both quadrants' shared vertices take the average mix, so FO4 shows no seam."""
    mixes = LL.blend_borders(_mixes({'a': 1.0}, {'b': 1.0}))
    left, right = mixes[(0, 0)][0], mixes[(0, 0)][1]
    edge = [p for p in range(LL.QUAD_POINTS) if p % LL.SIDE == LL.SIDE - 1 and p // LL.SIDE < LL.SIDE - 1]
    assert all(left[t][p] == right[t][p - LL.SIDE + 1] == 0.5 for p in edge for t in 'ab')
    assert left['a'][0] == 1.0 and right['b'][LL.SIDE - 1] == 1.0


def test_a_quadrant_keeps_its_four_heaviest_textures_and_shared_vertices_still_match():
    """FO4 draws 4 textures a quadrant; the fifth is dropped, shares sum to 1, and both sides of a border agree."""
    mixes = LL.blend_borders(_mixes({'a': 0.4, 'b': 0.3, 'c': 0.15, 'd': 0.1, 'e': 0.05}, {'a': 1.0}))
    limited = LL.limit_textures(mixes)[(0, 0)]
    left, right = dict(limited[0]), dict(limited[1])
    assert [t for t, _ in limited[0]] == ['a', 'b', 'c', 'd'] and np.allclose(sum(left.values()), 1.0)
    border = LL.SIDE - 1
    assert all(abs(left.get(t, np.zeros(1))[border] - right.get(t, np.zeros(1))[0]) < 1e-9 for t in 'abcd')


def test_only_references_written_as_themselves_are_linked_to():
    """References on an unconverted base or split into parts are not built."""
    builder = SimpleNamespace(parts=SimpleNamespace(parts={0x20}), base=lambda fid: None if fid == 0x30 else fid)
    refs = [{'FormID': f'{i:08X}', 'NAME': f'{base:08X}'} for i, base in ((1, 0x10), (2, 0x20), (3, 0x30))]
    assert [r['FormID'] for r in CB._built(builder, refs)] == ['00000001']


def test_scripted_items_carry_their_vmad_between_edid_and_bounds():
    """Containers, misc items and keys take a VMAD right after EDID, as vanilla's scripted bases do."""
    vmad = b'\x06\x00\x02\x00\x00\x00'
    records = (R.pack_cont(0x801, 'Box', '', 'm.nif', (0,) * 6, [], 0, 0.0, vmad=vmad),
               R.pack_misc(0x802, 'Cap', '', 'm.nif', (0,) * 6, 1, 0.0, vmad=vmad),
               R.pack_keym(0x803, 'Key', '', 'm.nif', (0,) * 6, 1, 0.0, vmad=vmad))
    for record in records:
        tags = [t for t, _ in subrecords(record[24:])]
        assert tags[:3] == [b'EDID', b'VMAD', b'OBND'] and dict(subrecords(record[24:]))[b'VMAD'] == vmad
    assert b'VMAD' not in dict(subrecords(R.pack_misc(0x804, 'Plain', '', 'm.nif', (0,) * 6, 1, 0.0)[24:]))


def test_a_global_comparison_keeps_its_flag_and_names_the_converted_global():
    """The value field's FNV global becomes the FO4 one; an unconverted global or a plain value is handled apart."""
    raw = struct.pack('<B3xIIIIII', 0x24, 0x00012345, 0, 0, 0, 0, 0).hex()
    cond = CD.parse(raw)
    flag, value = CD.fo4_value(cond, {0x12345: 0x03012345})
    assert flag == CD.USE_GLOBAL and struct.pack('<f', value) == struct.pack('<I', 0x03012345)
    assert CD.fo4_value(cond, {}) is None
    plain = CD.parse(struct.pack('<B3xfIIIII', 0x20, 2.5, 0, 0, 0, 0, 0).hex())
    assert CD.fo4_value(plain, {}) == (0, 2.5)


def test_every_fnv_global_is_written_except_the_engine_globals_fo4_shares(tmp_path, monkeypatch):
    """Own globals keep FNV's id, type, value and Constant flag; GameHour stays Fallout4.esm's."""
    records = [{'FormID': '00012345', 'EditorID': 'MyGlobal', 'FNAM.Type': 'l', 'FLTV.Value': '3.0', 'RecordFlags': '64'},
               {'FormID': '00000038', 'EditorID': 'GameHour', 'FNAM.Type': 'f', 'FLTV.Value': '8.0', 'RecordFlags': '0'}]
    monkeypatch.setattr(GL, 'export_records', lambda *_: records)
    monkeypatch.setattr(GL, 'fo4_forms', lambda: {'GlobalVariable': {'GameHour': 0x38}})
    written = []
    builder = SimpleNamespace(fnv_id=lambda fid: 0x03000000 | int(fid, 16), counts=Counter(),
                              writer=SimpleNamespace(add_record=lambda sig, raw: written.append(raw)))
    assert GL.write_all(builder, tmp_path) == {0x12345: 0x03012345, 0x38: 0x38}
    (record,) = written
    assert struct.unpack_from('<I', record, 8)[0] == 0x40 and struct.unpack_from('<I', record, 12)[0] == 0x03012345
    subs = dict(subrecords(record[24:]))
    assert subs[b'EDID'] == b'FNV_MyGlobal\0' and subs[b'FNAM'] == b'l' and struct.unpack('<f', subs[b'FLTV'])[0] == 3.0


def test_a_faction_keeps_relations_to_factions_ranks_and_maps_its_flags():
    """Hidden, special combat and track crime map to FO4 bits; a race relation is dropped; an owner can own."""
    subs = [(b'EDID', b'GSFaction\0'), (b'FULL', b'Goodsprings\0'),
            (b'XNAM', struct.pack('<IiI', 0x10, 20, 2)), (b'XNAM', struct.pack('<IiI', 0x99, -10, 1)),
            (b'DATA', bytes([0x05, 0x01, 0, 0])), (b'RNAM', struct.pack('<I', 0)), (b'MNAM', b'Sheriff\0'),
            (b'INAM', b'icon.dds\0')]
    record = FA.faction_record(0x03000801, subs, {0x10: 0x03000010}, owner=True)
    found = list(subrecords(record[24:]))
    assert [t for t, _ in found] == [b'EDID', b'FULL', b'XNAM', b'DATA', b'CRVA', b'RNAM', b'MNAM', b'VENV']
    data = dict(found)
    assert struct.unpack('<IiI', data[b'XNAM']) == (0x03000010, 20, 2)
    assert struct.unpack('<I', data[b'DATA'])[0] == 0x1 | 0x2 | FA.TRACK_CRIME | FA.CAN_BE_OWNER
    assert data[b'CRVA'] == FA.CRIME_VALUES[True] and data[b'EDID'] == b'FNV_GSFaction\0'
