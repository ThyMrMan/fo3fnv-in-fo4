"""Spike 1b dialogue rules confirmed in game: Random piles, [Leave], walking away.

See: docs/fork/fo4_spikes.md#spike-1b
"""

import math
import pickle
import struct
import wave
from collections import Counter
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from fo4_import.base.ba2 import Archives
from fo4_import.base import strings as ST
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.source_ids import SourceIds
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.havok import human_clip as HC
from fo4_import.nif import collision as CO
from fo4_import.nif import file as nf
from fo4_import.spike import conditions as CD
from fo4_import.spike import dialogue as D
from fo4_import.spike import globals as GL
from fo4_import.spike import equipment as E
from fo4_import.spike import factions as FA
from fo4_import.spike import gun_choice as GC
from fo4_import.spike import sounds as SO
from fo4_import.spike import quest_scope as QS
from fo4_import.spike import say_once as SO1
from fo4_import.base import vmad as VM
from tools.validate import fo4_audit as AU
from fo4_import.spike import replacements as RP
from fo4_import.spike import imods as I
from fo4_import.spike import imagespace as IM
from fo4_import.spike import lighting_template as LT
from fo4_import.spike import emittance as EM
from fo4_import.spike import weathers as WT
from fo4_import.spike import exterior as EX
from fo4_import.pipeline import work_cache as WC
from fo4_import.spike import land_layers as LL
from fo4_import.spike import locations as LO
from fo4_import.spike import holotapes as HT
from fo4_import.spike import interiors as IN
from fo4_import.spike import say_topics as SAY
from fo4_import.spike import navmesh as NM
from fo4_import.spike import actor_data as AD
from fo4_import.spike import idles as ID
from fo4_import.spike import packages as PK
from fo4_import.spike import readiness as RD
from fo4_import.spike import npcs as N
from fo4_import.spike import placement as PL
from fo4_import.spike import poses as P
from fo4_import.spike import records as R
from fo4_import.spike import script as SC
from fo4_import import helpers_plugin as HP
from fo4_import.spike import skeleton as S
from fo4_import.spike import voice as V
from fo4_import.spike.voice_types import with_voice
from fo4_import.spike import cell as CB
from fo4_import.spike import condition_forms as CF
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
    jobs = V.jobs([(0x02000869, rec)], [((folder,), 'NPCMDocWeathers')], tmp_path / 'Data', 'Spike.esp')
    assert [(j[1].relative_to(tmp_path).as_posix(), j[2]) for j in jobs] == [
        ('Data/Sound/Voice/Spike.esp/NPCMDocWeathers/00000869_1.fuz', ' Of course.')]


def test_a_dlc_line_is_found_under_the_plugin_holding_its_info(tmp_path):
    """fnv_folders(): the game's folder, then the DLC's; a line's master byte picks the folder its file is in."""
    game, dlc = tmp_path / 'FalloutNV.esm', tmp_path / 'HonestHearts.esm'
    game.mkdir()
    dlc.mkdir()
    (dlc / '_HEADER.txt').write_text('Master[0]=FalloutNV.esm\n')
    folders = V.fnv_folders(dlc, 'MaleUniqueJoshua')
    assert [f.relative_to(tmp_path).as_posix() for f in folders] == [
        'FalloutNV.esm/sound/voice/falloutnv.esm/maleuniquejoshua',
        'HonestHearts.esm/sound/voice/honesthearts.esm/maleuniquejoshua']
    for folder, name in zip(folders, ('a_b_000101f6_1.ogg', 'a_b_000101f6_2.ogg')):
        folder.mkdir(parents=True)
        (folder / name).write_bytes(b'')
    assert {key: path.parent.parent.name for key, path in V.index_recordings(folders).items()} == {
        (0x000101F6, 1): 'falloutnv.esm', (0x010101F6, 2): 'honesthearts.esm'}


def test_a_stale_silent_line_is_set_aside_like_a_stale_recording(tmp_path):
    """remove_stale(): a .fuz and a silent .xwm no job writes go to the cache; a job's file stays."""
    folder, cache = tmp_path / 'Voice' / 'FNV_RobotUniqueRex', tmp_path / 'cache'
    folder.mkdir(parents=True)
    for name in ('00000800_1.fuz', '00000801_1.xwm', '00000802_1.xwm'):
        (folder / name).write_bytes(b'x')
    assert V.remove_stale([(None, folder / '00000802_1.xwm', None)], [folder], cache) == 2
    assert sorted(p.name for p in folder.iterdir()) == ['00000802_1.xwm']
    assert sorted(p.name for p in (cache / folder.name).iterdir()) == ['00000800_1.fuz', '00000801_1.xwm']


def test_a_dlc_build_voices_only_the_infos_it_holds():
    """own_lines() keeps the plugin's own INFOs (byte 1), not the master's."""
    assert V.own_lines([(0x00001234, 'game'), (0x01000800, 'dlc')], 1) == [(0x01000800, 'dlc')]


def test_a_silent_line_plays_a_short_silent_recording(tmp_path):
    """An NPC's silent line gets the silent .xwm under each voice type; the player's under both player voices."""
    jobs = V.silent_jobs([(0x02000900, False), (0x02000901, True)], ['NPCMDocWeathers'], tmp_path, 'Spike.esp')
    assert [j[1].relative_to(tmp_path).as_posix() for j in jobs] == [
        'Sound/Voice/Spike.esp/NPCMDocWeathers/00000900_1.xwm',
        'Sound/Voice/Spike.esp/PlayerVoiceMale01/00000901_1.xwm',
        'Sound/Voice/Spike.esp/PlayerVoiceFemale01/00000901_1.xwm']
    with wave.open(str(jobs[0][0])) as recording:
        assert recording.getnframes() == round(V.SILENT_SECONDS * V.SILENT_RATE) and jobs[0][2] is None


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
    builder = SimpleNamespace(counts={'WEAP': 0}, type_keywords=SimpleNamespace(of=lambda fnv: []), writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x01ABCDEF, add_record=lambda sig, rec: written.append(rec)))
    eq = E.Equipment.__new__(E.Equipment)
    eq.weapon_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.builder, eq.fnv, eq.vanilla = builder, {}, {'BaseballBat': template}
    eq.by_anim, eq.fired = {}, {}
    eq.guns = SimpleNamespace(default_only=lambda subs: None)
    eq.ammo_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.condition = SimpleNamespace(wire=lambda fnv, fid, subs: subs)
    eq.vats = SimpleNamespace(apply=lambda rec, dnam, template: template.get(b"CRDT", b""))
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
                              type_keywords=SimpleNamespace(of=lambda fnv: []),
                              writer=SimpleNamespace(derive_formid=lambda site, key: 7,
                                                     add_record=lambda sig, rec: written.append(rec)))
    eq = E.Equipment.__new__(E.Equipment)
    eq.weapon_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.builder, eq.fnv, eq.vanilla, eq.strings = builder, {}, {'RollingPin': template}, {1: b'Rolling Pin'}
    eq.poses = {}
    eq.by_anim, eq.fired = {}, {}
    eq.ammo_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
    eq.condition = SimpleNamespace(wire=lambda fnv, fid, subs: subs)
    eq.vats = SimpleNamespace(apply=lambda rec, dnam, template: template.get(b"CRDT", b""))
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
    (tmp_path / 'BBGunMod.esp').write_bytes(b'TES4' + struct.pack('<I', 0) + bytes(16))
    user.write_text('{"weapon": {"WeapBBGun": {"use": "BBGunMod.esp|BBGun", "as": "item"}}}', encoding='utf-8')
    table = RP.load(user, dirs=(tmp_path,))
    assert table['WeapBBGun'] == RP.Replacement('BBGunMod.esp', 'BBGun', 'item', (), 'weapon', 'user')
    assert table['WeapBaseballBat'].mode == 'fnv' and table['VaultSuit21'].mode == 'item'
    assert RP.extra_masters(table) == ['BBGunMod.esp']
    user.write_text('{"weapon": {"WeapBBGun": {"use": "BBGunMod.esp|BBGun", "as": "stats"}}}', encoding='utf-8')
    with pytest.raises(ValueError):
        RP.load(user, dirs=(tmp_path,))


def test_another_plugins_formid_is_renumbered_to_our_masters():
    """Its own record takes its place in our masters; its override of a Fallout4.esm record stays index 0."""
    ours = ['Fallout4.esm', 'FalloutHelpers.esl', 'XDI.esm', 'BBGunMod.esp']
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
    eq.weapon_mods = SimpleNamespace(wire=lambda fnv, subs: subs)
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


def test_an_fnv_sound_keeps_its_own_volume_and_reach():
    """FNV's static attenuation (cdB) replaces the template's; its reach picks the nearest mono model."""
    sounds = object.__new__(SO.Sounds)
    sounds.models = {250.0: 0xA, 350.0: 0xB, 500.0: 0xC}
    template = {b'ONAM': b'tmpl', b'BNAM': bytes((0, 5, 128, 0)) + struct.pack('<H', 1894)}
    sconce = {'SNDD.MaxAttDist': '4', 'SNDD.StaticAttenuation': '5727'}
    out = sounds.playback(sconce, template)
    assert out[b'ONAM'] == struct.pack('<I', 0xB) and out[b'BNAM'] == bytes((0, 5, 128, 0)) + struct.pack('<H', 5727)
    assert sounds.playback({}, template) == {**template, b'BNAM': bytes((0, 5, 128, 0, 0, 0))}



def _ids():
    """A stand-in CellBuilder carrying only what fnv_id and new_id read."""
    builder = SimpleNamespace(writer=FO4PluginWriter(masters=['Fallout4.esm', 'A.esl', 'B.esm']), owned=Counter(),
                              top=0x800, keyed=set(), counts=Counter(), ids=SourceIds([], [], 3))
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
    """A border split unevenly: the edge under the link's midpoint, not a corner."""
    verts, tri = [(0, 0, 0), (0, 20, 0), (-10, 10, 0)], [0, 1, 2]
    assert NM.facing(((0, 4, 0), (0, 8, 0)), verts, tri) == 0


def test_an_exterior_pathing_cell_stores_y_then_x():
    """As all 7,113 Fallout4.esm exterior navmeshes do."""
    assert struct.pack('<I', NM.grid_parent(-18, 3)) == struct.pack('<hh', 3, -18)


def test_the_world_maps_bounds_grow_and_its_image_is_reframed_to_match(monkeypatch):
    """FNV's -35,35 to 25,-25 grows MAP_MARGIN cells a side; the image is staged resampled by map_axis, across
    from FNV's west edge to the east edge of its SE cell, down from the north edge of its NW cell."""
    staged = []
    monkeypatch.setattr(EX, 'stage_derived', lambda data, rel, work, sources, *args: staged.append((rel, args)))
    monkeypatch.setattr(EX, 'export_file', lambda root, rel: Path(root) / rel)
    world = {'ICON': 'interface\\worldmap\\map.dds', 'MNAM.NWCellX': '-35', 'MNAM.NWCellY': '35',
             'MNAM.SECellX': '25', 'MNAM.SECellY': '-25'}
    out = EX._world_map(world, Path('export'), Path('data'))
    m = EX.MAP_MARGIN
    assert struct.unpack('<ii4h', out[b'MNAM'])[2:] == (-35 - m, 35 + m, 25 + m, -25 - m)
    across = EX.map_axis((-35 - m, 25 + m), (-35, 26), EX.PIPBOY_GUTTERS[0])
    down = EX.map_axis((35 + m, -25 - m), (36, -25), EX.PIPBOY_GUTTERS[1])
    assert staged == [(EX.fo4_texture('interface\\worldmap\\map.dds'), (across, down, EX.MAP_SIDE))]


def test_a_place_shows_on_the_image_where_fo4_marks_it():
    """Where FO4 marks a cell position (between its corner cells' origins, inside the gutters), the reframed image
    shows FNV's picture of it (FNV_MAP_INSET plus FNV_MAP_SCALE across FNV's bounds, SE cell included)."""
    fo4, fnv, (near, far) = (39, -29), (36, -25), EX.PIPBOY_GUTTERS[1]
    a, b = EX.map_axis(fo4, fnv, (near, far))
    for cell in (36.0, -13.0, -25.0, 0.5):
        p = near + (1 - near - far) * (cell - fo4[0]) / (fo4[1] - fo4[0])
        q = EX.FNV_MAP_INSET + EX.FNV_MAP_SCALE * (cell - fnv[0]) / (fnv[1] - fnv[0])
        assert math.isclose(a * p + b, q, abs_tol=1e-12)


def test_a_reframed_map_samples_its_source_and_fills_outside_it_black():
    """A 64-pixel map white on the left half, shown from a quarter across with half the width: white then black
    across; shown from below its bottom: black."""
    half = Image.new('RGBA', (64, 64), (0, 0, 0, 255))
    half.paste((255, 255, 255, 255), (0, 0, 32, 64))
    raw = BytesIO()
    half.save(raw, 'PNG')
    out = Image.open(BytesIO(WC.reframed_dds(raw.getvalue(), (0.5, 0.25), (1.0, 0.0), 64))).convert('RGB')
    assert out.size == (64, 64) and min(out.getpixel((8, 32))) > 240 and max(out.getpixel((56, 32))) < 16
    below = Image.open(BytesIO(WC.reframed_dds(raw.getvalue(), (1.0, 0.0), (1.0, 1.5), 64))).convert('RGB')
    assert below.getpixel((8, 32)) == (0, 0, 0)


def test_a_child_world_sharing_its_parents_ground_names_its_parent():
    """A Diamond City-like child (LOD, map, climate; FNV's image space bit dropped): WNAM, PNAM, ONAM with Z 0."""
    world = {'WNAM.Parent': '000DA726', 'PNAM.Flags': str(0x36), 'ONAM.Scale': '0.5',
             'ONAM.CellXOffset': '-16000.0', 'ONAM.CellYOffset': '103000.0'}
    out = EX._linked(world, {b'ICON': b'map\0', b'MNAM': bytes(16), b'NAMA': b'x'}, 0xDA726)
    assert struct.unpack('<I', out[b'WNAM'])[0] == 0xDA726 and struct.unpack('<H', out[b'PNAM'])[0] == 0x16
    assert struct.unpack('<4f', out[b'ONAM']) == (0.5, -16000.0, 103000.0, 0.0)
    assert b'ICON' not in out and b'MNAM' not in out and out[b'NAMA'] == b'x'


def test_a_child_map_moves_the_parents_map_bounds_by_the_map_offset():
    """Offset (-16400, 90000), scale 1: the bounds move 4 cells east, 22 south."""
    world = {'ONAM.Scale': '1.0', 'ONAM.CellXOffset': '-16400.0', 'ONAM.CellYOffset': '90000.0'}
    out = EX.child_map(world, struct.pack('<ii4h', 0, 0, -39, 39, 29, -29))
    assert struct.unpack('<ii4h', out) == (0, 0, -35, 17, 33, -51)


def test_a_child_map_scales_the_parents_map_bounds_about_the_world_centre():
    """Scale 0.5 about the centre of NAM0/NAM9 (0, 0): the parent's -2..1 cells become -4..3."""
    world = {'ONAM.Scale': '0.5', 'NAM0.MinX': '-8192.0', 'NAM0.MinY': '-8192.0', 'NAM9.MaxX': '8192.0',
             'NAM9.MaxY': '8192.0'}
    out = EX.child_map(world, struct.pack('<ii4h', 0, 0, -2, 1, 1, -2))
    assert struct.unpack('<ii4h', out)[2:] == (-4, 3, 3, -4)


def test_interiors_reached_follow_doors_from_the_block_and_through_interiors():
    """Block door -> saloon -> cellar is reached; a door into another worldspace and an unlinked cell are not."""
    cells = {c: {'FormID': c} for c in ('DOC', 'SALOON', 'CELLAR', 'FAR')}
    door = lambda fid, cell, to: {'FormID': fid, 'ParentCELL': cell, 'XTEL.Door': to}
    refs = [door('d1', 'BLOCK', 'd2'), door('d2', 'SALOON', 'd1'), door('d3', 'SALOON', 'd4'),
            door('d4', 'CELLAR', 'd3'), door('d5', 'CELLAR', 'd6'), door('d6', 'OTHERWORLD', 'd5'),
            {'FormID': 'r', 'ParentCELL': 'FAR'}]
    found = IN.reached(cells, refs, cells['DOC'], [refs[0]])
    assert [c['FormID'] for c in found] == ['DOC', 'CELLAR', 'SALOON']


def test_an_interior_a_placed_objects_script_names_is_reached_too():
    """The casino's elevator door names a marker in the control room (its script's SCRO): the control room is
    reached, and a door there is followed in turn; an interior nothing names stays out."""
    cells = {c: {'FormID': c} for c in ('DOC', 'CASINO', 'CONTROL', 'SUITE', 'FAR')}
    door = lambda fid, cell, to: {'FormID': fid, 'ParentCELL': cell, 'XTEL.Door': to}
    refs = [door('d1', 'BLOCK', 'd2'), door('d2', 'CASINO', 'd1'), {'FormID': 'lift', 'ParentCELL': 'CASINO'},
            {'FormID': 'marker', 'ParentCELL': 'CONTROL'}, door('d3', 'CONTROL', 'd4'), door('d4', 'SUITE', 'd3'),
            {'FormID': 'r', 'ParentCELL': 'FAR'}]
    found = IN.reached(cells, refs, cells['DOC'], [refs[0]], {'lift': {'CONTROL'}})
    assert [c['FormID'] for c in found] == ['DOC', 'CASINO', 'CONTROL', 'SUITE']


def test_an_interior_a_quest_moves_the_player_into_is_reached(tmp_path):
    """VEnding's quest script moves the player to a marker in Endgame, which no door reaches; an object's script
    and an unlinked cell are not seeds."""
    rows = [('00000001', '1', 'player.MoveTo SlideMarker'), ('00000002', '0', 'player.MoveTo FarMarker')]
    (tmp_path / 'SCPT.txt').write_text(''.join(
        f'---RECORD_BEGIN---\nSignature=SCPT\nFormID={f}\nSCHR.Type={t}\nSCTX={s}\n---RECORD_END---\n' for f, t, s in rows),
        encoding='utf-8')
    refs = [{'FormID': 'm', 'EditorID': 'SlideMarker', 'ParentCELL': 'END'},
            {'FormID': 'f', 'EditorID': 'FarMarker', 'ParentCELL': 'FAR'}]
    seeds = IN.moved_to(tmp_path, refs)
    cells = {c: {'FormID': c} for c in ('DOC', 'END', 'FAR')}
    assert seeds == {'END'} and [c['FormID'] for c in IN.reached(cells, refs, cells['DOC'], [], {}, seeds)] == [
        'DOC', 'END']


def test_a_note_on_a_shared_topic_keeps_only_lines_naming_its_speaker():
    """On a note's own topic a line with no speaker test is the note's; on a topic two quests share (GREETING)
    only a line naming the speaker by GetIsID is."""
    is_id = CD.FNV.index('GetIsID')
    raw = lambda who: struct.pack('<B3xfIIIII', 0, 1.0, is_id, who, 0, 0, 0).hex()
    speaker = {'FormID': '0013DBEC', 'VTCK.Voice': '00000000'}
    own = [{'FormID': 'A', 'QSTI.Quest': 'Q1', 'ConditionCount': '0'}]
    shared = [{'FormID': 'B', 'QSTI.Quest': 'Q1', 'ConditionCount': '1', 'Condition[0].Raw': raw(0x13DBEC)},
              {'FormID': 'C', 'QSTI.Quest': 'Q2', 'ConditionCount': '0'}]
    assert [line['FormID'] for line in HT.note_lines(own, speaker)] == ['A']
    assert [line['FormID'] for line in HT.note_lines(shared, speaker)] == ['B']


def test_talking_through_an_activator_reads_0_in_an_fo4_build():
    """IsActorTalkingThroughActivator == 0 drops out of a line's conditions; == 1 never passes."""
    talking = CD.FNV.index('IsActorTalkingThroughActivator')
    raw = lambda value: struct.pack('<B3xfIIIII', 0, value, talking, 0, 0, 0, 0).hex()
    rec = lambda value: {'ConditionCount': '1', 'Condition[0].Raw': raw(value)}
    assert CD.without_absent([CD.parse(rec(0.0)['Condition[0].Raw'])], {}) == []
    assert CD.without_absent([CD.parse(rec(1.0)['Condition[0].Raw'])], {}) is None


def test_exists_reads_1_and_a_test_of_no_form_reads_0():
    """Exists == 1 drops out; GetQuestVariable on no quest == 0 drops out, == 1 never passes; the player stays."""
    test = lambda func, value, p1=0: CD.parse(struct.pack('<B3xfIIIII', 0, value, CD.FNV.index(func), p1, 1, 0, 0).hex())
    assert CD.without_absent([test('Exists', 1.0)], {}) == []
    assert CD.without_absent([test('GetQuestVariable', 0.0)], {}) == []
    assert CD.without_absent([test('GetQuestVariable', 1.0)], {}) is None
    assert CD.absent(test('GetIsID', 1.0, 0x7), {}) is None


def test_a_line_testing_a_form_list_makes_the_list():
    """IsInList's form list (BoomerKidGiftList, which a script fills) is made on demand, as an item test's is."""
    made = {}
    builder = SimpleNamespace(cell_ids={}, regions={}, counts=Counter(),
                              items=SimpleNamespace(item=lambda fid: made.setdefault(fid, 0x900000 | fid & 0xFFFF)))
    in_list = struct.pack('<B3xfIIIII', 0, 1.0, CD.FNV.index('IsInList'), 0x106182, 0, 0, 0).hex()
    out = CF.condition_forms(builder, [{'ConditionCount': '1', 'Condition[0].Raw': in_list}])
    assert out == {0x106182: 0x906182}


def test_a_line_testing_a_package_names_the_package_written():
    """The dialogue form map holds each written package; one left out (0) is absent, so GetIsCurrentPackage of it
    reads 0."""
    builder = SimpleNamespace(globals={}, factions={}, actor_refs={}, objectives={}, quest_vars={},
                              reputation_slots={}, hardcore=SimpleNamespace(form_map=dict),
                              casino=SimpleNamespace(form_map=dict),
                              packages=SimpleNamespace(made={'000F631E': 0x0F631E, '000F631D': 0}))
    form_map = CB._form_map(builder, {}, [], {})
    assert form_map[0x0F631E] == 0x0F631E and 0x0F631D not in form_map
    running = CD.FNV.index('GetIsCurrentPackage')
    cond = CD.parse(struct.pack('<B3xfIIIII', 0, 1.0, running, 0x0F631D, 0, 0, 0).hex())
    assert CD.absent(cond, form_map) is False


def test_an_objective_its_built_quest_does_not_author_is_never_displayed():
    """GetObjectiveDisplayed 30 == 1 on a built quest authoring 10 and 20 never passes and == 0 always does; an
    authored objective, or a quest the form map lists no objectives for, stays to convert."""
    shown = CD.FNV.index('GetObjectiveDisplayed')
    test = lambda index, value: CD.parse(struct.pack('<B3xfIIIII', 0, value, shown, 0x1638F0, index, 0, 0).hex())
    form_map = {0x1638F0: 0x801, (CD.AUTHORED, 0x1638F0): frozenset({10, 20})}
    assert CD.without_absent([test(30, 1.0)], form_map) is None
    assert CD.without_absent([test(30, 0.0)], form_map) == []
    assert CD.absent(test(20, 1.0), form_map) is None
    assert CD.absent(test(30, 1.0), {0x1638F0: 0x801}) is None


def test_a_topic_a_script_says_is_built_as_a_scripted_topic():
    """Every topic a script says with SayWhenFree is picked, a top-level or Detection one too; GREETING (the
    greeting scene's) and a topic no script says are not."""
    dials = {'T1': {'DATA.Type': '0', 'EditorID': 'TourStop'}, 'T3': {'DATA.Type': '0', 'EditorID': 'Top', 'DATA.Flags': '2'},
             'T4': {'DATA.Type': '4', 'EditorID': 'StartCombatResponse'}, 'T5': {'DATA.Type': '0', 'EditorID': 'Unsaid'},
             '000000C8': {'DATA.Type': '0', 'EditorID': 'GREETING'}}
    said = {'tourstop', 'top', 'startcombatresponse', 'greeting'}
    assert SAY.script_said(dials, said) == {'T1', 'T3', 'T4'}
    assert SAY.SAY_FREE.findall('TES4Polyfill.SayWhenFree(akSpeakerRef, TourStop, None)') == ['TourStop']


def test_a_said_topic_borrows_its_shared_lines_into_their_quest():
    """ArcadeThreeCard's only line is a GREETING line it shares: the copy is ArcadeThreeCard's, in that line's
    quest; a shared info that is the topic's own is not copied again."""
    dials = {'00168AD3': {'SharedInfoCount': '2', 'SharedInfo[0].Info': '001676c8', 'SharedInfo[1].Info': '00000001'}}
    lines = {'001676C8': {'FormID': '001676C8', 'ParentDIAL': '000000C8', 'QSTI.Quest': '0016117f'},
             '00000001': {'FormID': '00000001', 'ParentDIAL': '00168ad3', 'QSTI.Quest': '0016117F'}}
    copies = SAY.borrowed_lines(dials, {'00168AD3'}, lines)
    assert copies == {'0016117F': [{'FormID': '001676C8', 'ParentDIAL': '00168AD3', 'QSTI.Quest': '0016117f',
                                    SAY.SHARED: '00168AD3'}]}


def test_a_scripts_topic_property_names_the_topics_quests():
    """A player or Conversation topic names its DIAL quests; GREETING and a Radio topic name none."""
    dials = [{'FormID': '00126763', 'EditorID': 'NCRSnifferChallengePlayer', 'DATA.Type': '0', 'QuestCount': '1',
              'Quest[0]': '00126760'},
             {'FormID': '000000C8', 'EditorID': 'GREETING', 'DATA.Type': '0', 'QuestCount': '1', 'Quest[0]': '1'},
             {'FormID': '00000126', 'EditorID': 'RadioHello', 'DATA.Type': '7', 'QuestCount': '1', 'Quest[0]': '2'}]
    assert QS.topic_quests(dials) == {'ncrsnifferchallengeplayer': {0x126760}}


def test_a_test_of_the_player_names_fallout4s_own_player():
    """Target GetIsID Player == 1 (a HELLO for the player only) converts with no form map entry, as vanilla's 56
    such lines; an unbuilt actor's GetIsID still does not."""
    player = CD.parse('000000000000803f480000000700000000000000010000000000000000000000')
    assert SAY._fo4_condition(player, {}, {}) == (CD.FO4.index('GetIsID'), 0x7, 0, '', '')
    rec = {'Condition[0].Raw': '000000000000803f480000000700000000000000010000000000000000000000'}
    assert SAY.conditions_of(rec, {}, {}) == R.pack_ctda(0, 1.0, CD.FO4.index('GetIsID'), 0x7, 0, R.RUN_TARGET, 0, -1)
    other = CD.parse('000000000000803f4800000099990100000000000000000000000000')
    assert SAY._fo4_condition(other, {}, {}) is None


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


def test_moving_props_layer_body_takes_clutter_and_a_fixed_one_keeps_props():
    """A moving props (10) body is FO4 clutter (4); a fixed one stays props."""
    props = SimpleNamespace(layer=10, flags_and_part_number=0, unknown_short=0)
    assert CO.havok_filter(props, moving=True)[0] == 4 and CO.havok_filter(props)[0] == 10


def test_still_collision_gets_both_sides_once_and_moving_collision_keeps_one():
    """FacRmWallONLY01's inward faces: a fixed body adds each reversed face not already there; a dynamic one none."""
    a, b, c = (0, 0, 0), (1, 0, 0), (0, 1, 0)
    soup = ([(a, b, c), (a, c, b), (b, c, (1, 1, 0))], [1, 2, 3])
    tris, mats = CO.both_sides(soup, SimpleNamespace(motion_system=7))
    assert len(tris) == 4 and tris[3] == (b, (1, 1, 0), c) and mats == [1, 2, 3, 3]
    assert CO.both_sides(soup, SimpleNamespace(motion_system=1)) == soup


def test_a_water_phantom_is_left_out_of_the_collision():
    """A bhkSimpleShapePhantom on FNV's water layer (placeable water converts on its own) adds no block."""
    body = type('bhkSimpleShapePhantom', (), {'havok_col_filter': SimpleNamespace(layer=CO.FNV_WATER)})()
    phantom = SimpleNamespace(collision_object=SimpleNamespace(body=body))
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


def test_a_weathers_directional_ambient_is_fnvs_ambient_at_that_time():
    """FO4 night (time 3) and late sunset (time 7, FNV sunset) DALC: six FNV ambient colours, specular kept."""
    fnv = bytearray(240)
    fnv[72:88] = bytes((1, 1, 1, 0, 2, 2, 2, 0, 3, 3, 3, 0, 4, 4, 4, 0))
    vanilla = bytes(range(24)) + b'SPECFRES'
    assert WT.directional_ambient(vanilla, bytes(fnv), 3) == bytes((4, 4, 4, 0)) * 6 + b'SPECFRES'
    assert WT.directional_ambient(vanilla, bytes(fnv), 7)[:24] == bytes((3, 3, 3, 0)) * 6


def test_a_region_emittance_weather_takes_fnvs_sunlight_at_each_fo4_time_of_day():
    """FO4's eight times take FNV's four (early/late sunrise and sunset as sunrise and sunset) in two entries."""
    fnv = bytearray(240)
    fnv[4 * 24:4 * 24 + 16] = bytes((1, 1, 1, 0, 2, 2, 2, 0, 3, 3, 3, 0, 4, 4, 4, 0))
    out = WT.colour_table(bytes(range(256)) * 2 + bytes(96), bytes(fnv), EM.SUNLIGHT)
    expected = b''.join(bytes((t, t, t, 0)) for t in (1, 2, 3, 4, 1, 1, 3, 3))
    assert out[4 * 32:5 * 32] == expected == out[9 * 32:10 * 32]
    assert out[:4 * 32] == (bytes(range(256)) * 2)[:4 * 32]


def test_a_fixed_exposure_shows_middle_grey_and_shadows_as_fnv_and_rolls_highlights_off():
    """FO4's curve at the pinned exposure: middle grey at FNV's 0.459, shadows close, white under 1 for bloom."""
    tonemap_e, grey = 0.02, 0.18
    exposure = IM.fixed_exposure(tonemap_e, grey)
    shown = IM.fo4_display(exposure * np.array([0.01, 0.18, 1.0]), tonemap_e)
    assert exposure == pytest.approx(1.46, abs=0.01)
    assert shown == pytest.approx([0.13, 0.459, 0.80], abs=0.01)


def test_the_lut_grades_only_saturation_and_tint(tmp_path):
    """An FNV cinematic with every flag set: contrast and brightness don't reach the LUT; grey takes the tint."""
    dnam = bytearray(152)
    struct.pack_into('<8fI', dnam, IM.CINEMATIC, 0.5, 0.2, 2.0, 3.0, 1.0, 0.5, 0.0, 0.5, 15)
    grading = IM.cinematic(bytes(dnam))
    assert grading == IM.Cinematic(0.5, (1.0, 0.5, 0.0), 0.5)
    grey = IM.grade(np.array([0.4, 0.4, 0.4]), grading)
    assert grey == pytest.approx([0.4, 0.3, 0.2])
    rel = IM.write_lut(grading, 'Test', tmp_path)
    assert (tmp_path / 'Textures' / rel.replace('\\', '/')).stat().st_size == 128 + 16 * 256 * 3


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


def test_a_trigger_box_keeps_its_primitive_but_no_room_bound(monkeypatch):
    """An activator's reference (a trigger box) is no room: no XMBO; a room marker's keeps it."""
    monkeypatch.setattr(PL, '_activators', lambda: frozenset({0xACAC}))
    trigger = [(b'NAME', struct.pack('<I', 0xACAC)), (b'XMBO', b'b' * 12), (b'XPRM', b'p' * 32)]
    room = [(b'NAME', struct.pack('<I', 0x1F)), (b'XMBO', b'b' * 12), (b'XPRM', b'p' * 32)]
    assert not PL._room_bound(trigger) and PL._room_bound(room)


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
    grassless CommonwealthDefault01. Texture 0 becomes the lowest FNV LTEX using FNV's default; a second
    worldspace reuses the first's LTEX instead of writing it again."""
    ext = EX.Exterior.__new__(EX.Exterior)
    ext.textures = {'00015457': {'ICON': 'DirtWasteland01.dds'}, '00000A8A': {'ICON': 'DirtWasteland01.dds'},
                    '00020524': {'ICON': 'DirtPathWasteland01.dds'}}
    builder, written = SimpleNamespace(land_textures={}), []
    ext._write_ltex = lambda builder, rec, data_dir: written.append(rec) or 0x03000A8A
    assert ext._ltex(builder, '00000000', None) == 0x03000A8A and ext._ltex(builder, None, None) == 0x03000A8A
    other = EX.Exterior.__new__(EX.Exterior)
    other.textures, other._write_ltex = ext.textures, ext._write_ltex
    assert other._ltex(builder, '00000A8A', None) == 0x03000A8A
    assert written == [ext.textures['00000A8A']]


def test_a_land_layer_with_no_share_is_left_out_and_the_next_takes_its_number():
    """A kept texture whose shares are all under MIN_SHARE writes no ATXT/VTXT (vanilla's 37,020 LANDs have none;
    Black Landscape Fix strips them as invalid); the layer after it is numbered 0; counted."""
    ext = EX.Exterior.__new__(EX.Exterior)
    ext._ltex = lambda builder, texture, data_dir: int(texture, 16)
    builder = SimpleNamespace(counts=Counter(), fnv_id=lambda fid: 0x01000800)
    full, empty, half = (np.full(LL.QUAD_POINTS, s) for s in (1.0, 0.0, 0.5))
    mix = {q: [('10', full), ('20', empty), ('30', half)] for q in range(4)}
    subs = list(_fo4_subrecords(ext._land(builder, {'FormID': '00000800'}, mix, None)[24:]))
    atxt = [struct.unpack('<IBBH', d) for tag, d in subs if tag == b'ATXT']
    assert atxt == [(0x30, q, 0, 0) for q in range(4)] and sum(tag == b'VTXT' for tag, _ in subs) == 4
    assert builder.counts['land alpha layers left out (no share)'] == 4


def _fo4_subrecords(raw: bytes):
    """(tag, data) of packed subrecords `raw`."""
    at = 0
    while at < len(raw):
        tag, size = raw[at:at + 4], struct.unpack_from('<H', raw, at + 4)[0]
        yield tag, raw[at + 6:at + 6 + size]
        at += 6 + size


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


def _land(base: str, painted: str, opacity: float) -> dict:
    """An FNV LAND record: quadrant 0 on `base` with `painted` at `opacity` on its first 20 vertices."""
    rec = {'LayerCount': '2', 'Layer[0].Type': 'BASE', 'Layer[0].BTXT.Quadrant': '0', 'Layer[0].BTXT.Texture': base,
           'Layer[1].Type': 'ALPHA', 'Layer[1].ATXT.Quadrant': '0', 'Layer[1].ATXT.Layer': '0',
           'Layer[1].ATXT.Texture': painted, 'Layer[1].VTXTCount': '20', 'VHGT.Offset': '0'}
    rec.update({f'Layer[1].VT[{v}].Pos': str(v) for v in range(20)})
    rec.update({f'Layer[1].VT[{v}].Opacity': str(opacity) for v in range(20)})
    return rec


def test_the_land_texture_step_is_kept_in_the_work_cache(tmp_path, monkeypatch):
    """land_textures gives limit_textures(blend_borders()) of the quadrant mixes; a height change reuses the kept
    value, a layer change makes it again."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path)
    lands = {(0, 0): _land('00000A01', '00000A02', 0.5), (1, 0): _land('00000A03', '00000A02', 0.25), (2, 0): None}
    direct = LL.limit_textures(LL.blend_borders({g: LL.quadrant_mix(r) for g, r in lands.items() if r}))
    assert pickle.dumps(LL.land_textures(lands)) == pickle.dumps(direct)
    made = []
    monkeypatch.setattr(LL, 'blend_borders', lambda mixes: made.append(1) or mixes)
    lands[(0, 0)]['VHGT.Offset'] = '8'
    assert pickle.dumps(LL.land_textures(lands)) == pickle.dumps(direct) and not made
    lands[(0, 0)]['Layer[1].VT[3].Opacity'] = '0.75'
    LL.land_textures(lands)
    assert made == [1]


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


def test_an_owner_converts_to_fo4s_twelve_bytes_and_an_unconverted_one_drops_its_rank(monkeypatch):
    """A converted owner keeps its rank; an owner not converted drops both XOWN and XRNK."""
    found = [(b'XOWN', struct.pack('<I', 0x500)), (b'XRNK', struct.pack('<i', 2))]
    monkeypatch.setattr(PL, 'fields', lambda: {0x900: found})
    kept = dict(subrecords(PL.placement(0x900, {}, {0x500: 0x03000500})))
    assert kept[b'XOWN'] == struct.pack('<I', 0x03000500) + bytes(8) and kept[b'XRNK'] == struct.pack('<i', 2)
    assert PL.placement(0x900, {}, {}) == b''


def test_a_map_marker_keeps_its_name_flags_radius_and_fo4_type_but_other_refs_drop_tnam(monkeypatch):
    """FNV's Settlement type (2) is FO4's (13); a TNAM on a reference with no XMRK is not a map marker's."""
    marker = [(b'XRDS', struct.pack('<f', 2000.0)), (b'XMRK', b''), (b'FNAM', b'\x01'), (b'FULL', b'Goodsprings\0'),
              (b'TNAM', b'\x02\x00')]
    monkeypatch.setattr(PL, 'fields', lambda: {0x901: marker, 0x902: [(b'TNAM', b'\x05\x00'), (b'XRDS', bytes(4))]})
    kept = list(subrecords(PL.placement(0x901, {})))
    assert [t for t, _ in kept] == [b'XRDS', b'XMRK', b'FNAM', b'FULL', b'TNAM'] and dict(kept)[b'TNAM'] == b'\x0d\x00'
    assert PL.placement(0x902, {}) == b''


def test_a_point_is_inside_a_region_polygon_by_the_even_odd_rule():
    """A square region holds its centre and not a point past its edge."""
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert LO.inside(square, 5.0, 5.0) and not LO.inside(square, 15.0, 5.0)


def test_an_interior_takes_the_location_of_the_exterior_door_leading_in_and_passes_it_on():
    """Outside door A (in the region) leads into cell X; X's door leads into Y; both take A's location."""
    locations = LO.Locations.__new__(LO.Locations)
    locations.root, locations.regions = 1, [(2, [[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]])]
    a = {'FormID': '0A', 'ParentCELL': 'W', 'XTEL.Door': '0B', 'PosX': '50', 'PosY': '50'}
    refs = [a, {'FormID': '0B', 'ParentCELL': 'X', 'XTEL.Door': '0A'},
            {'FormID': '0C', 'ParentCELL': 'X', 'XTEL.Door': '0D'}, {'FormID': '0D', 'ParentCELL': 'Y', 'XTEL.Door': '0C'}]
    places = locations.interiors(refs, [a], [{'FormID': 'X'}, {'FormID': 'Y'}, {'FormID': 'Z'}])
    assert places == {'X': 2, 'Y': 2}


def test_an_encounter_zone_gains_fo4s_location_and_maximum_level_slots():
    """FNV's owner, rank, minimum level and flags in FO4's DATA order, owner through the converted forms."""
    written = []
    builder = SimpleNamespace(fnv_id=lambda fid: 0x03000000 | int(fid, 16), counts=Counter(),
                              writer=SimpleNamespace(add_record=lambda sig, raw: written.append(raw)))
    rec = {'FormID': '000D6FB0', 'EditorID': 'BisonSteve', 'DATA.Owner': '00000500', 'DATA.Rank': '1',
           'DATA.MinLevel': '2', 'DATA.Flags': '1'}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(LO, 'export_records', lambda *_: [rec])
        assert LO.encounter_zones(builder, None, {0x500: 0x03000500}) == {0xD6FB0: 0x030D6FB0}
    data = dict(subrecords(written[0][24:]))[b'DATA']
    assert struct.unpack('<IIbbBb', data) == (0x03000500, 0, 1, 2, 1, 0)


def test_a_package_schedule_stores_any_month_as_zero_and_its_hours_in_minutes():
    """Form version 122+ months shift by one; 22x8 is 22:00 for 480 minutes."""
    rec = {'PSDT.Month': '-1', 'PSDT.DayOfWeek': '-1', 'PSDT.Date': '0', 'PSDT.Time': '22', 'PSDT.Duration': '8'}
    assert struct.unpack('<bbbbb3xi', PK.schedule(rec)) == (0, -1, 0, 22, -1, 480)


def test_packages_go_right_after_aidt_in_place_of_the_bodys():
    """All 1,120 vanilla NPCs with packages list them after AIDT; a body's own PKIDs are dropped."""
    subs = pack_subrecord('AIDT', b'\0' * 4) + pack_subrecord('PKID', b'\1\0\0\0') + pack_subrecord('KSIZ', b'\0' * 4)
    tags = [(t, d) for t, d in subrecords(R.packages_edit([7, 8])(subs))]
    assert [t for t, _ in tags] == [b'AIDT', b'PKID', b'PKID', b'KSIZ']
    assert [struct.unpack('<I', d)[0] for t, d in tags if t == b'PKID'] == [7, 8]


def test_a_force_greet_only_a_quest_script_names_is_made_before_the_greeting(tmp_path):
    """VMS40's quest script names Markland's Dialogue package, filled only with the quest record: it is made
    first, so the greeting takes its topic; the script's other properties are left to the fill."""
    (tmp_path / 'FALLOUTNV_VMS40TimerSCRIPT.psc').write_text(
        'Package Property VBSLtMarklandTrainingGreet Auto\nPackage Property VMS40Sandbox Auto\n', encoding='utf-8')
    packages = PK.Packages.__new__(PK.Packages)
    packages.packs = {'00142AB1': {'PKDT.Type': '15'}, '00142AB2': {'PKDT.Type': '12'}}
    packages.by_name = {'vbsltmarklandtraininggreet': '00142AB1', 'vms40sandbox': '00142AB2'}
    made = []
    packages.named = made.append
    scripts = SimpleNamespace(dir=tmp_path, name=lambda scpt: 'FALLOUTNV_VMS40TimerSCRIPT')
    packages.named_by_quests(scripts, [{'EditorID': 'VMS40', 'SCRI': '00139B8E'}])
    assert made == ['VBSLtMarklandTrainingGreet']


def test_an_in_cell_sleep_goes_to_the_npcs_own_bed_else_an_unowned_one():
    """Chet's sleep in his store takes the mattress he owns; another NPC takes the unowned bed."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.beds = {0x1057F1: [(0x100, 0), (0x200, 0x104C78)]}
    rec = {'PLDT.Type': '1', 'PLDT.Location': '001057F1'}
    assert packages._bed(rec, 0x104C78) == 0x200
    assert packages._bed(rec, 0x999) == 0x100


def test_a_sandbox_copy_takes_each_allow_from_fnvs_no_flag():
    """Primm residents (no flags) may sit and use idle markers; Chet's No Sleeping turns only sleeping off."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.slots = {'Sandbox': {'Allow Eating': 1, 'Allow Sleeping': 2, 'Allow Conversation': 3,
                                  'Allow Idle Markers': 4, 'Allow Sitting': 5, 'Allow Special Furniture': 6,
                                  'Allow Wandering': 7}}
    residents = packages._values({'PKDT.Type': '12', 'PKDT.TypeFlags': '0'}, 'Sandbox')
    chet = packages._values({'PKDT.Type': '12', 'PKDT.TypeFlags': '2'}, 'Sandbox')
    assert set(residents.values()) == {b'\1'} and len(residents) == 7
    assert chet[2] == b'\0' and chet[5] == b'\1'
    assert packages._values({'PKDT.Type': '9', 'PKDT.TypeFlags': '1'}, 'Sandbox') == {}
    assert packages._values({'PKDT.Type': '12', 'PKDT.TypeFlags': '0'}, 'Travel') == {}


def test_a_follow_copy_stops_at_fnvs_follow_distance():
    """FNV's distance (PTDT count) is Min Radius; Max Radius keeps vanilla's 600 unless FNV's is farther; none
    keeps both."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.slots = {'FollowNPC': {'Min Radius': 0, 'Max Radius': 1}}
    packages.vanilla = {'FollowNPC': pack_subrecord('CNAM', struct.pack('<f', 300))
                        + pack_subrecord('CNAM', struct.pack('<f', 600))}
    near = packages._values({'PTDT.Count': '128'}, 'FollowNPC')
    assert near == {0: struct.pack('<f', 128), 1: struct.pack('<f', 600)}
    assert packages._values({'PTDT.Count': '768'}, 'FollowNPC')[1] == struct.pack('<f', 768)
    assert packages._values({'PTDT.Count': '0'}, 'FollowNPC') == {}


def test_fnvs_own_behavior_flags_become_fo4_interrupt_flags():
    """With 0x1000 set FNV's eight shared bits replace FO4's low byte (Avoid Radiation dropped); without it the
    vanilla instance's flags stay. The override byte is the caller's."""
    vanilla = struct.pack('<I4BHH', 0, 18, 0, 0, 0, 0xFEFF, 0)
    own = PK._pkdt({'PKDT.Flags': str(0x1000), 'PKDT.BehaviorFlags': str(0x100 | 0x40 | 0x1)}, vanilla, 4)
    assert struct.unpack_from('<H', own, 8)[0] == 0xFE41 and own[5] == 4
    default = PK._pkdt({'PKDT.Flags': '0', 'PKDT.BehaviorFlags': str(0xCDCD)}, vanilla, 0)
    assert struct.unpack_from('<H', default, 8)[0] == 0xFEFF and default[5] == 0
    assert struct.unpack_from('<I', own)[0] == 0


def test_a_guard_held_through_combat_gets_a_combat_override_list():
    """An FNV Guard flagged Continue During Combat gets a second HoldPosition copy with the Combat override, listed
    in its NPC's ECOR form list; a Guard without the flag and a cowering flee (a HoldPosition) with it get none."""
    ids = {PK.COMBAT_SITE: 0x900, PK.COMBAT_LIST_SITE: 0x901}
    writer = SimpleNamespace(added=[], add_record=lambda sig, data: writer.added.append((sig, data)),
                             derive_formid=lambda site, key: ids[site])
    packages = PK.Packages.__new__(PK.Packages)
    packages.builder = SimpleNamespace(writer=writer, fnv_id=lambda fnv: int(fnv, 16), counts=Counter())
    packages.vanilla = {'HoldPosition': pack_subrecord('EDID', b'V\0') + pack_subrecord('PKDT', bytes(12))}
    packages.combat, packages.combat_lists, packages.greets, packages.topics = {}, {}, [], {}
    packages._fragments = lambda rec, form_map: b''
    rec = {'EditorID': 'Guard', 'PKDT.Type': '14', 'PKDT.Flags': str(PK.CONTINUE_DURING_COMBAT), 'PSDT.Month': '-1',
           'PSDT.DayOfWeek': '-1', 'PSDT.Date': '0', 'PSDT.Time': '-1', 'PSDT.Duration': '0'}
    assert packages._write('00000010', rec, ('HoldPosition', b''), b'', {}) == 0x10
    assert packages._write('00000011', {**rec, 'PKDT.Flags': '0'}, ('HoldPosition', b''), b'', {}) == 0x11
    assert packages._write('00000012', {**rec, 'PKDT.Type': '10'}, ('HoldPosition', b''), b'', {}) == 0x12
    npc = {'FormID': '00000020', 'EditorID': 'Trooper', 'AIPackageCount': '2', 'AIPackage[0]': '00000011',
           'AIPackage[1]': '00000010'}
    assert packages.combat_list(npc) == 0x901 and packages.combat_list({}) == 0
    combat = dict(subrecords(writer.added[1][1][24:]))
    assert combat[b'PKDT'][5] == PK.COMBAT_OVERRIDE and combat[b'EDID'] == b'FNV_GuardCombat\0'
    assert [s for s, _ in writer.added] == ['PACK', 'PACK', 'PACK', 'PACK', 'FLST']
    assert dict(subrecords(writer.added[4][1][24:]))[b'LNAM'] == struct.pack('<I', 0x900)


def test_a_dialogue_package_with_an_npc_travels_to_it_and_plays_the_topics_chat():
    """Captain Parker's arrest of Keith: a Travel near Keith within 128 units whose fragments play the
    TES4Chat_CaptainParkerArrest scene with Keith; an unbuilt target is left out."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.topic_names = {'0014D99A': 'CaptainParkerArrest'}
    talks = {}
    scripts = SimpleNamespace(talk=lambda prop: talks.setdefault(prop, 0x77))
    packages.builder = SimpleNamespace(scripts=scripts, counts=Counter())
    rec = {'FormID': '0000ABCD', 'PKDT.Type': '15', 'PTDT.Type': '0', 'PTDT.Target': '000F83A5', 'PTDT.Count': '128',
           'PKDD.Topic': '0014D99A'}
    assert packages._plan(rec, {0xF83A5: 0x55}, 0) == ('Travel', struct.pack('<iIi', 0, 0x55, 128))
    assert packages._plan(rec, {}, 0) == 'dialogue target not built'
    vmad = packages._fragments(rec, {0xF83A5: 0x55})
    assert b'F3NV_DialoguePackage' in vmad and talks == {'TES4Chat_CaptainParkerArrest': 0x77}
    assert struct.pack('<I', 0x77) in vmad and struct.pack('<I', 0x55) in vmad


def test_a_use_weapon_package_shoots_its_target_with_fnvs_weapon_and_firing():
    """The Novac nightkin's brahmin shot: UseWeapon at its start, its target and weapon in inputs 1 and 2,
    PKW3 into the firing values; an unbuilt target is left out, a weapon type converts to FO4's."""
    packages = PK.Packages.__new__(PK.Packages)
    names = ('Always Hit?', 'Volley Fire?', 'Do No Damage?', 'Volley Wait Min', 'Volleys To Fire', 'Volley Shots Max')
    packages.slots = {'UseWeapon': {name: slot for slot, name in enumerate(names)}}
    packages.builder = SimpleNamespace(items=SimpleNamespace(item={0x1234: 0x88}.get))
    rec = {'PKDT.Type': '16', 'PTDT.Type': '1', 'PTDT.Target': '00001234', 'PTD2.Type': '0', 'PTD2.Target': '000B9A00',
           'PKW3.Flags': '257', 'PKW3.FireRate': '1', 'PKW3.FireCount': '0', 'PKW3.Bursts': '3', 'PKW3.ShotsMin': '1',
           'PKW3.ShotsMax': '2', 'PKW3.PauseMin': '1.5', 'PKW3.PauseMax': '2.0'}
    assert packages._plan(rec, {0xB9A00: 0x55}, 0) == ('UseWeapon', struct.pack('<iIi', 2, 0, 0))
    assert packages._plan(rec, {}, 0) == 'weapon target not built'
    assert packages._weapon(rec, {0xB9A00: 0x55}) == {1: struct.pack('<iIi', 1, 0x88, 0), 2: struct.pack('<iIi', 0, 0x55, 0)}
    typed = packages._weapon({**rec, 'PTDT.Type': '2', 'PTDT.Target': '21'}, {0xB9A00: 0x55})
    assert typed[1] == struct.pack('<iIi', 2, 20, 0)
    assert packages._firing(rec) == {0: b'\x01', 1: b'\x01', 2: b'\x01', 3: struct.pack('<f', 1.5),
                                     4: struct.pack('<i', 3), 5: struct.pack('<i', 2)}
    assert packages._firing({**rec, 'PKW3.FireCount': '1'})[4] == struct.pack('<i', 0)


def test_a_force_greet_takes_fnvs_trigger_location_and_activate_distance():
    """The Primm trooper's trigger box (radius 0) reaches its smaller half extent; an unbuilt one keeps vanilla's.
    Without PLD2 (Ringo, Sunny, Oscar Velasco in his cave) the trigger is near the actor within FNV's loaded area, so
    no one crosses the map for the player. The greet distance is FNV's Activate Distance (150 where it is 0), at most
    TALK_REACH: the trooper's 1,024 left him standing out of talking range."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.boxes = {0x172555: 1874.9}
    rec = {'PLD2.Type': '0', 'PLD2.Location': '00172555', 'PLD2.Radius': '0'}
    near_player = lambda reach: struct.pack('<iIi', PK.NEAR_REFERENCE, 0x14, reach)
    trigger = packages._trigger(rec, {0x172555: 0x0B172555})
    assert trigger == {PK.TRIGGER_INPUT: struct.pack('<iIi', 0, 0x0B172555, 1875),
                       PK.GREET_INPUT: near_player(PK.ACTIVATE_DISTANCE)}
    wide = packages._trigger({**rec, 'PLD2.Radius': '300'}, {0x172555: 1})
    assert wide[PK.TRIGGER_INPUT][-4:] == struct.pack('<i', 300)
    assert packages._trigger(rec, {}) == {PK.GREET_INPUT: near_player(PK.ACTIVATE_DISTANCE)}
    oscar = packages._trigger({'PTDT.Count': '1024'}, {})
    assert oscar == {PK.TRIGGER_INPUT: struct.pack('<iIi', PK.NEAR_SELF, 0, PK.FNV_LOADED_REACH),
                     PK.GREET_INPUT: near_player(PK.TALK_REACH)}


def test_a_travel_to_a_linked_seat_sits_in_it():
    """Nipton's crucified: a Travel to the linked crucifix sits there (linked target); a linked non-seat travels."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.furniture, packages.links = {0x1375D8}, {'001384AB': {0x1375D8}, '00000500': {0x1375D8, 0x77}}
    rec = {'FormID': '001384AB', 'PKDT.Type': PK.FNV_TRAVEL, 'PLDT.Type': PK.NEAR_LINKED, 'PLDT.Location': '0',
           'PLDT.Radius': '0'}
    assert packages._plan(rec, {}, 0) == ('Sit', struct.pack('<iIi', PK.TARGET_LINKED, 0, 0))
    assert packages._plan({**rec, 'FormID': '00000500'}, {}, 0) == ('Travel', struct.pack('<iIi', 6, 0, 0))


def test_an_escort_leads_its_built_target_to_its_location():
    """Orris's VFSOrrisLeadPlayerPackage: EscortPlayer to its marker, the player as Target to Escort, its count as
    the wait distance; an unbuilt target leaves it out."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.furniture, packages.slots = set(), {'EscortPlayer': {'Distance to Wait for Followers': 1}}
    rec = {'FormID': '0011BEE1', 'PKDT.Type': PK.FNV_ESCORT, 'PLDT.Type': '0', 'PLDT.Location': '0011BEDE',
           'PLDT.Radius': '0', 'PTDT.Type': '0', 'PTDT.Target': '00000014', 'PTDT.Count': '256'}
    forms = {0x11BEDE: 0x55, 0x14: 0x14}
    assert packages._plan(rec, forms, 0) == ('EscortPlayer', struct.pack('<iIi', 0, 0x55, 0))
    assert packages._plan(rec, {0x11BEDE: 0x55}, 0) == 'escort target not built'
    assert packages._escorted(rec, forms) == {PK.ESCORTED_INPUT: struct.pack('<iIi', 0, 0x14, 0)}
    assert packages._values(rec, 'EscortPlayer') == {1: struct.pack('<f', 256)}
    assert packages._values({**rec, 'PTDT.Count': '0'}, 'EscortPlayer') == {}


def _packages_for(packs: dict, made: dict) -> PK.Packages:
    """Packages over FNV `packs` whose builder makes items from `made` and records readiness; _write gives 0x77."""
    packages = PK.Packages.__new__(PK.Packages)
    packages.packs, packages.made, packages.why, packages.furniture = packs, {}, {}, set()
    packages.builder = SimpleNamespace(counts=Counter(), script_vars={}, readiness=RD.Readiness(),
                                       fnv_id=lambda fnv: int(fnv, 16),
                                       items=SimpleNamespace(item=made.get))
    packages._write = lambda *_: 0x77
    return packages


def test_a_left_out_package_is_in_the_readiness_report_and_a_tested_item_is_made():
    """A Find is left out with a readiness entry of its own (no NPC needed); a Travel testing GetItemCount of an
    item no reference places makes the item and converts."""
    item = struct.pack('<B3xfIIIII', 0x60, 1.0, CD.FNV.index('GetItemCount'), 0x500, 0, 0, 0).hex()
    packs = {'00000101': {'FormID': '00000101', 'EditorID': 'NellisFindJanet', 'PKDT.Type': '0'},
             '00000102': {'FormID': '00000102', 'EditorID': 'VMS49ChaserPackage', 'PKDT.Type': PK.FNV_TRAVEL,
                          'ConditionCount': '1', 'Condition[0].Raw': item}}
    packages, forms = _packages_for(packs, {0x500: 0x900500}), {}
    assert packages.package('00000101', forms) == 0
    assert packages.builder.readiness.entries == [
        {'kind': RD.PACKAGE_LEFT_OUT, 'owner': '00000101', 'detail': 'NellisFindJanet (type Find)'}]
    assert packages.package('00000102', forms) == 0x77 and forms == {0x500: 0x900500}


def test_a_faction_enemy_test_asks_whether_the_actor_is_hostile_to_the_player():
    """GetActorFactionPlayerEnemy is FO4's IsHostileToActor of the player."""
    cond = CD.parse(struct.pack('<B3xfIIIII', 0, 1.0, CD.FNV.index('GetActorFactionPlayerEnemy'), 0, 0, 0, 0).hex())
    assert SAY._fo4_condition(cond, {}, {}) == (CD.FO4.index('IsHostileToActor'), CD.PLAYER_REF, 0, '', '')


def test_a_force_greet_without_a_location_waits_where_its_actor_is():
    """A Dialogue package without a location waits near self; a wander, at its start."""
    packages = PK.Packages.__new__(PK.Packages)
    assert packages._at({}, PK.FNV_DIALOGUE, 'ForceGreet', {}) == ('ForceGreet', struct.pack('<iIi', PK.NEAR_SELF, 0, 0))
    assert packages._at({}, '5', 'Sandbox', {}) == ('Sandbox', struct.pack('<iIi', PK.NEAR_START, 0, 0))


def test_a_package_copy_replaces_later_location_inputs_by_ordinal():
    """The second PLDT takes `inputs[1]`; the third keeps vanilla's bytes."""
    vanilla = b''.join(pack_subrecord('PLDT', bytes([v]) * 16) for v in (5, 6, 7))
    rec = {'EditorID': 'X', 'PSDT.Month': '-1', 'PSDT.DayOfWeek': '-1', 'PSDT.Date': '0', 'PSDT.Time': '-1',
           'PSDT.Duration': '0'}
    out = PK.pack_package(0x800, rec, vanilla, b'\1' * 12, b'', inputs={1: b'\2' * 12})
    pldts = [d for t, d in subrecords(out[24:]) if t == b'PLDT']
    assert pldts == [b'\1' * 12 + b'\5' * 4, b'\2' * 12 + b'\6' * 4, b'\7' * 16]


def test_an_fnv_script_resetting_health_on_hit_is_hit_proof(tmp_path, monkeypatch):
    """The Well 3 gecko's OnHit block resets health; an OnDeath-only script and a later block's reset do not count."""
    gecko = 'ScriptName G\r\n\r\nBEGIN OnHit VCG02GSSettlerREF\r\n\tif(bVulnerable == 0)\r\n\t\tResetHealth;\r\n\tendif\r\nEND\r\n'
    later = 'BEGIN OnHit\r\n\tset x to 1\r\nEND\r\nBEGIN OnDeath\r\n\tResetHealth\r\nEND'
    records = [{'FormID': '0010A1F4', 'SCTX': gecko}, {'FormID': '00000002', 'SCTX': later}]
    monkeypatch.setattr(AD, 'export_records', lambda _dir, _sig: records)
    AD.hit_proof_scripts.cache_clear()
    assert AD.hit_proof_scripts(tmp_path) == {0x10A1F4}
    assert AD.hit_proof(tmp_path, {'SCRI': '0010A1F4'}) and not AD.hit_proof(tmp_path, {})
    AD.hit_proof_scripts.cache_clear()


def test_a_package_copy_sets_value_inputs_by_slot():
    """CNAM slot 1 is replaced; slots 0 and 2 keep the vanilla values."""
    vanilla = b''.join(pack_subrecord('CNAM', bytes([v])) for v in (5, 6, 7))
    rec = {'EditorID': 'X', 'PSDT.Month': '-1', 'PSDT.DayOfWeek': '-1', 'PSDT.Date': '0', 'PSDT.Time': '-1',
           'PSDT.Duration': '0'}
    body = PK.pack_package(0x800, rec, vanilla, b'', b'', values={1: b'\1'})[24:]
    assert [d for t, d in subrecords(body) if t == b'CNAM'] == [b'\5', b'\1', b'\7']


def test_a_subrecord_goes_before_the_first_listed_tag_in_place_of_its_own():
    """ZNAM lands before NAM5 (all 1,745 vanilla ZNAMs do), replacing an old one; without NAM5 it goes last."""
    subs = pack_subrecord('ZNAM', b'\1\0\0\0') + pack_subrecord('HCLF', b'\0' * 4) + pack_subrecord('NAM5', b'\0\0')
    out = [(t, d) for t, d in subrecords(R.with_sub(b'ZNAM', b'\2\0\0\0', (b'NAM5',))(subs))]
    assert out[1:] == [(b'ZNAM', b'\2\0\0\0'), (b'NAM5', b'\0\0')] and out[0][0] == b'HCLF'
    tail = [t for t, _ in subrecords(R.with_sub(b'ECOR', b'\3\0\0\0', (b'PRKZ',))(pack_subrecord('RNAM', b'\0' * 4)))]
    assert tail == [b'RNAM', b'ECOR'] and R.with_sub(b'ECOR', b'', ()) is None


def test_an_npc_takes_its_fnv_voice_type_in_place_of_its_bodys():
    """VTCK becomes the converted voice type; the other subrecords are untouched."""
    subs = pack_subrecord('VTCK', b'\1\0\0\0') + pack_subrecord('RNAM', b'\2\0\0\0')
    out = dict(subrecords(with_voice(0x0310512F)(subs)))
    assert struct.unpack('<I', out[b'VTCK'])[0] == 0x0310512F and out[b'RNAM'] == b'\2\0\0\0'
    assert with_voice(None) is None


def test_quest_scope_counts_writes_to_a_quests_variables():
    """A script starting, advancing, adding to or setting a quest's variable pulls the quest in; a read or a
    comparison does not (VCG01's psych test answers tally in VCG01Test)."""
    text = ('VCG01Test.TES4Add_nBarter((2))\nVMS01.LookingForStealthBoys = 1\nTES4SetStage(VCG02, 10)\n'
            'VDoctors.Start()\nIf Generic.Cost == 3\nx = VFreeformNellis.State\nTES4Polyfill.SetStage(CG03Test, 9)\n')
    found = {n for m in QS.STARTS.finditer(text) for n in m.groups() if n}
    assert found == {'VCG01Test', 'VMS01', 'VCG02', 'VDoctors', 'CG03Test'}


def test_quest_scope_follows_speaker_tests_to_placed_actors():
    """A generic quest comes in when a placed actor passes its line's faction or voice type test by having the form,
    through templates, leveled lists and form lists (vDialogueNCRCivilian, vDialogueSuperMutant); a negated test,
    tests no one passes together, or a faction no placed actor has, keep it out."""
    def cond(func: str, form: int, value: float = 1.0) -> str:
        """An FNV Subject condition `func(form) == value`, raw hex."""
        return struct.pack('<B3xfIIIII', 0, value, CD.FNV.index(func), form, 0, 0, 0).hex()

    def line(*conds: str) -> dict:
        """An FNV INFO with conditions `conds`."""
        return {f'Condition[{i}].Raw': c for i, c in enumerate(conds)}

    scope = QS.QuestScope.__new__(QS.QuestScope)
    scope.quests = {q: {'EditorID': f'Q{q:X}', **({'Condition[0].Raw': cond('GetIsVoiceType', 0x70)} if q == 0x101 else {})}
                    for q in range(0x100, 0x105)}
    scope.lines = {0x100: [line(cond('GetInFaction', 0x50))], 0x101: [line()],
                   0x102: [line(cond('GetInFaction', 0x51, 0.0))],
                   0x103: [line(cond('GetIsVoiceType', 0x80), cond('GetInFaction', 0x50))],
                   0x104: [line(cond('GetInFaction', 0x52))]}
    scope.actors = {0x1: {'FormID': '00000001', 'ACBS.TemplateFlags': str(QS.USE_FACTIONS), 'TPLT.Template': '00000060',
                          'VTCK.Voice': '00000081'},
                    0x2: {'FormID': '00000002', 'FactionCount': '1', 'Faction[0].FormID': '00000050',
                          'Faction[0].Rank': '0', 'VTCK.Voice': '00000081'},
                    0x3: {'FormID': '00000003', 'VTCK.Voice': '00000080'}}
    scope.leveled = {0x60: [0x2], 0x61: [0x3]}
    scope.form_lists = {0x70: frozenset({0x80})}
    assert scope._spoken({0x1, 0x61}, set()) == {0x100, 0x101}
    assert scope._spoken({0x1, 0x61}, {0x100}) == {0x101}
    assert scope._spoken({0x2}, set()) == {0x100}


def test_say_once_markers_live_in_their_own_quest_and_ride_on_the_line():
    """A Say Once line's marker is a stage of the marker quest (FO4's GetStage reads a quest's highest done stage,
    so a marker in the line's own quest hid its story stage); the line carries F3NV_SayOnce beside its fragments."""
    once = SO1.SayOnce()
    once.quest = 0x0300ABCD
    stage = once.stage('00104BEE')
    assert SO1.FIRST <= stage < SO1.FIRST + SO1.COUNT and once.stage('00104bee') == stage
    ctda = once.unsaid(['00104BEE'])
    assert struct.pack('<II', 0x0300ABCD, stage) in ctda
    vmad = VM.info_fragments('FALLOUTNV_TIF__00104BEE', {}, begin='Fragment_1', end='Fragment_0',
                             scripts=[once.script('00104BEE')])
    assert [s for s, _ in AU.vmad_scripts(b'INFO', vmad)] == ['F3NV_SayOnce', 'FALLOUTNV_TIF__00104BEE']
    assert dict(AU.vmad_scripts(b'INFO', vmad))['F3NV_SayOnce'] == {'Marks': 0x0300ABCD}


def test_placeable_water_tiles_cover_a_strip_with_squares_of_its_width():
    """A 512 x 2048 strip is four 512 tiles (scale 0.5) in a row along its length; a round mesh is one tile."""
    from fo4_import.spike import placeable_water as PW
    strip = PW.tiles((0.0, 0.0), (512.0, 2048.0), False)
    assert [t[1] for t in strip] == [-768.0, -256.0, 256.0, 768.0] and {t[6] for t in strip} == {0.5}
    assert PW.tiles((10.0, 20.0), (512.0, 512.0), True) == [(10.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.5)]


def test_two_fnv_items_may_share_one_item_replacement():
    """Every FNV entry naming the same Fallout4.esm record gets it (frag mines and powder charges: fragMine)."""
    from fo4_import.base.writer import pack_fo4_record
    from tes5_import.base.writer import pack_string_subrecord
    weap = pack_fo4_record('WEAP', 0xE56C2, 0, pack_string_subrecord('EDID', 'fragMine'))
    plugin = pack_fo4_record('TES4', 0, 0, b'') + b'GRUP' + struct.pack('<I4sIII', 24 + len(weap), b'WEAP', 0, 0, 0) + weap
    table = {fnv: RP.Replacement(RP.BASE, 'fragMine', 'item') for fnv in ('WeapMineFrag', 'WeapNVMinePowderCharge')}
    assert RP.items(table, plugin, ['Fallout4.esm']) == {'WeapMineFrag': 0xE56C2, 'WeapNVMinePowderCharge': 0xE56C2}


def test_a_weather_region_keeps_its_areas_in_order_and_only_its_weather_entries(monkeypatch):
    """FNV's areas stay RPLI/RPLD pairs in order; a map entry is dropped; the weather and worldspace convert."""
    from fo4_import.spike import regions as RG
    from tes5_import.base.tes5_reader import subrecords
    monkeypatch.setattr(RG, 'fnv_weather', lambda builder, fnv: 0x03000000 | fnv & 0xFFFFFF)
    builder = SimpleNamespace(globals={}, counts=Counter(), fnv_id=lambda f: 0x03000000 | f & 0xFFFFFF,
                              writer=SimpleNamespace(derive_formid=lambda site, key: 0x03ABCDEF, records=[]))
    builder.writer.add_record = lambda sig, rec: builder.writer.records.append(rec)
    made = RG.Regions.__new__(RG.Regions)
    made.builder, made.made = builder, {}
    made.fnv = {0x123CE3: [(b'EDID', b'GSWeatherRegion\0'), (b'RCLR', b'\xff\x80\x80\0'), (b'WNAM', struct.pack('<I', 0xDA726)),
                           (b'RPLI', b'\0\4\0\0'), (b'RPLD', b'A' * 16), (b'RPLI', b'\0\0\0\0'), (b'RPLD', b'B' * 16),
                           (b'RDAT', struct.pack('<I4x', 4)), (b'RDMP', b'Goodsprings\0'),
                           (b'RDAT', struct.pack('<IBB2x', 3, 0, 100)), (b'RDWT', struct.pack('<IiI', 0x1237D7, 100, 0))]}
    assert made.region(0x123CE3) == 0x03ABCDEF
    subs = list(subrecords(builder.writer.records[0][24:]))
    assert [t for t, _ in subs] == [b'EDID', b'RCLR', b'WNAM', b'RPLI', b'RPLD', b'RPLI', b'RPLD', b'RDAT', b'RDWT']
    assert dict(subs)[b'WNAM'] == struct.pack('<I', 0x030DA726)
    assert dict(subs)[b'RDWT'] == struct.pack('<IiI', 0x031237D7, 100, 0)


def test_a_radioactive_reference_takes_the_nearest_vanilla_hazard():
    """FNV's rate picks the grade (1, 3, 6 a tick), its radius the size; no radius reads as the smallest."""
    from fo4_import.spike import radiation as RA
    table = {(g, r): i for i, (g, r) in enumerate((g, r) for g in RA.GRADES for r in (256, 512, 768, 2048))}
    assert RA.nearest(table, 1.0, None) == table[('Light', 256)]
    assert RA.nearest(table, 4.0, 700.0) == table[('Strong', 768)]
    assert RA.nearest(table, 720.0, 10.0) == table[('Deadly', 256)]


def test_a_music_zone_reaches_the_cells_its_radius_touches():
    """A marker's zone is a 16-gon of its radius; a cell counts when any of it lies within the radius."""
    from fo4_import.spike import music as MU
    points = list(struct.iter_unpack('<2f', MU.polygon(100.0, 200.0, 50.0)))
    assert len(points) == MU.SIDES and points[0] == (150.0, 200.0)
    assert MU.reaches((0, 0), 4196.0, 100.0, 200.0) and not MU.reaches((0, 0), 4400.0, 100.0, 200.0)
    assert MU.reaches((-1, -1), 10.0, 10.0, 20.0)


def test_a_decal_keeps_fnv_data_but_fo4_shininess_and_shared_flags():
    """Sizes, depth, parallax and colour stay; shininess is FO4's 1.0; flags keep 0x0E; FNV's junk bytes are 0."""
    from fo4_import.spike import decals as DE
    fnv = struct.pack('<7fBB2s4s', 25, 45, 25, 45, 32, 300, 1.0, 4, 0xCA, b'\xcd\xcd', b'\xb4\x18\x07\x00')
    out = struct.unpack('<7fBB2s4s', DE.decal_data(fnv))
    assert out[:5] == (25, 45, 25, 45, 32) and out[5] == 1.0 and out[7:] == (4, 0x0A, bytes(2), b'\xb4\x18\x07\x00')


def test_standing_idles_are_built_and_seated_ones_only_when_played_by_script():
    """A standing idle is built from a line or a script; a seated one only when a script plays one
    SEATED_PLAYED names."""
    idles = ID.Idles.__new__(ID.Idles)
    idles.builder = SimpleNamespace(fnv_id=lambda fnv: 0x0B000000 | fnv, counts=Counter())
    idles.records = {0x1: {'EditorID': 'VCG01DocGiveMirror'}, 0x2: {'EditorID': 'SeatedShrug'},
                     0x3: {'EditorID': 'StandingWave'}}
    idles.used, idles.counted, idles.checked = {}, set(), {0x1: ID.SEATED, 0x2: ID.SEATED, 0x3: ''}
    assert idles.idle(0x3) == 0x0B000003 and idles.idle(0x1, scripted=True) == 0x0B000001
    assert idles.idle(0x1) is None and idles.idle(0x2, scripted=True) is None
    assert idles.builder.counts['idle left out (seated)'] == 2


def test_probe_idle_plays_vanillas_own_clip_when_not_re_encoded():
    """A PROBE entry not re-encoded names vanilla's clip path as is."""
    idles = ID.Idles.__new__(ID.Idles)
    assert idles._probe(r'Actors\X.hkx', False, None, Path('.')) == Path(r'Actors\X.hkx')


def test_converted_clip_leaves_its_track_names_blank(monkeypatch, tmp_path):
    """A converted FNV clip's annotation tracks are unnamed, as vanilla's are (named ones crashed Havok)."""
    written = []
    clips = HC.HumanClips.__new__(HC.HumanClips)
    clips.meshes, clips.fnv, clips.fo4, clips.deltas, clips.pose = tmp_path, None, SimpleNamespace(names=['Root']), {}, {}
    monkeypatch.setattr(HC, 'decoded', lambda path: [SimpleNamespace(duration=1.0)])
    monkeypatch.setattr(HC, 'retarget_clip', lambda *a, **k: None)
    monkeypatch.setattr(HC, 'clip_to_animation_data',
                        lambda *a: SimpleNamespace(num_tracks=2, bone_names=['Root', 'COM']))
    monkeypatch.setattr(HC, 'write_fo4_animation', lambda path, anim: written.append(anim.bone_names))
    clips.write('x.kf', tmp_path / 'out' / 'x.hkx')
    assert written == [['', '']]


def test_trimmed_clip_keeps_its_first_seconds_and_their_events():
    """A 10.7 s clip cut to 3 s keeps 91 frames per track, one block, and only the events inside the cut."""
    track = SimpleNamespace(translations=list(range(322)), rotations=list(range(322)), scales=list(range(322)))
    anim = SimpleNamespace(num_frames=322, frame_duration=1 / 30, duration=10.7, num_blocks=2,
                           max_frames_per_block=256, tracks=[track],
                           annotations=[SimpleNamespace(time=0.0), SimpleNamespace(time=5.0)])
    ID.trimmed(anim, 3.0)
    assert (anim.num_frames, anim.num_blocks, len(track.rotations), len(anim.annotations)) == (91, 1, 91, 1)
    assert abs(anim.duration - 3.0) < 1e-6


def test_radio_station_xrdo_reaches_everywhere_or_weakens_over_fnvs_static_share():
    """Everywhere ignores distance; a 5000 radius at 50% static weakens from 2500 out; frequencies in the Pip-Boy's
    80-110 band, one slot per station in FormID order."""
    from fo4_import.spike import radio as RA
    assert struct.unpack('<3fI', RA.xrdo_data(96.0, (0.0, 1, 0.0, 0))) == (96.0, 0.0, 0.0, RA.IGNORES_DISTANCE)
    assert struct.unpack('<3fI', RA.xrdo_data(96.0, (5000.0, RA.RADIUS, 50.0, 0)))[1:] == (2500.0, 5000.0, 0)
    assert [RA.frequency_of(s, {9: 0, 2: 0, 5: 0}) for s in (2, 5, 9)] == list(RA.FREQUENCIES[:3])
    assert all(80.0 <= f <= 110.0 for f in RA.FREQUENCIES)


def test_only_radio_stations_the_pipboy_lists_become_transmitters(monkeypatch):
    """A Radio Station talking activator is a Pip-Boy station unless flagged Non-Pipboy; others are not."""
    from fo4_import.spike import radio as RA
    monkeypatch.setattr(RA, 'export_records', lambda d, sig: [
        {'FormID': '00000001', 'RecordFlags': str(0x40020000)}, {'FormID': '00000002', 'RecordFlags': str(0x10020000)},
        {'FormID': '00000003', 'RecordFlags': '0'}])
    assert list(RA.pipboy_stations(Path('x'))) == [1]


def test_a_quest_naming_no_station_takes_the_one_its_radio_lines_name():
    """Hanlon's recording quest has no conditions; its lines GetIsID one station. Lines naming two give none."""
    from fo4_import.spike import radio as RA

    def named(form):
        return {'Condition[0].Raw': (bytes(8) + struct.pack('<II', RA.GET_IS_ID, form) + bytes(12)).hex()}
    stations = {7: {}, 8: {}}
    assert RA.station_of(named(8), stations, [named(7)]) == 8
    assert RA.station_of({}, stations, [named(7), named(7)]) == 7
    assert RA.station_of({}, stations, [named(7), named(8)]) is None


def test_a_quest_with_several_stage_acts_gives_each_its_own_quest():
    """The Tops acts: a quest whose radio lines name three stations writes a start-enabled quest per station,
    keyed by the quest's FormID and the station's, holding that station's lines and the playlist script; a line
    typed Conversation in a Radio topic is a radio line."""
    from fo4_import.spike import radio as RA
    from fo4_import.spike import radio_program as RP

    def line(fid, dial, form, kind='7'):
        raw = (bytes(8) + struct.pack('<II', RA.GET_IS_ID, form) + bytes(12)).hex()
        return {'FormID': fid, 'ParentDIAL': dial, 'DATA.DialogType': kind, 'Condition[0].Raw': raw}
    lines = [line('A1', RP.RADIO_HELLO, 7, '1'), line('A2', '0000D001', 7), line('B1', RP.RADIO_HELLO, 8),
             line('C1', '0000D002', 9)]
    say = SimpleNamespace(infos={'00000100': lines}, dials={RP.RADIO_HELLO: {'DATA.Type': '7'},
                                                            '0000D001': {'DATA.Type': '7'}})
    rec = {'FormID': '00000100', 'EditorID': 'Shows', 'DATA.Flags': '21'}
    assert [r['FormID'] for r in RP.radio_lines(say, rec)] == ['A1', 'A2', 'B1']
    radio = RA.Radio.__new__(RA.Radio)
    written, keys, built = [], [], []
    radio.builder = SimpleNamespace(say=say, counts=Counter(), new_id=lambda key: keys.append(key) or len(keys),
                                    writer=SimpleNamespace(add_record=lambda sig, data: written.append((sig, data))))
    radio.stations = {7: {'EditorID': 'Drifter'}, 8: {'EditorID': 'Bruce'}, 9: {'EditorID': 'RadPack'}}
    radio._built = lambda act, quest, station, own, *_: built.append((act['EditorID'], quest, own)) or (
        [], [], [], [(RP.PLAYLIST_SCRIPT, {}, {})])
    assert radio.program(rec, 0x900, {}, {}) is None
    assert keys == ['QUST radio 00000100 00000007', 'QUST radio 00000100 00000008']
    assert [(name, quest, [r['FormID'] for r in own]) for name, quest, own in built] == [
        ('Shows_Drifter', 1, ['A1', 'A2']), ('Shows_Bruce', 2, ['B1'])]
    assert [sig for sig, _ in written] == ['QUST', 'QUST'] and radio.builder.counts['radio act quests'] == 2
    assert all(b'F3NV_RadioPlaylist' in data and b'FNV_Shows_' in data for _, data in written)


def test_a_station_a_script_starts_whose_line_ends_the_run_plays_on_demand(monkeypatch):
    """A script's live `<ref>.StartRadioConversation` (not a commented one) marks the station; its program is on
    demand only off the Pip-Boy (FO3's Galaxy News is started too) and with a Goodbye line, and only then gets its
    built receivers."""
    from fo4_import.spike import radio as RA
    text = 'begin gamemode\n  ;QuietREF.StartRadioConversation RadioHello\n  ShowREF.StartRadioConversation RadioHello\n'
    assert RA.START_CALL.findall(text) == ['ShowREF']
    made = []

    class Fake:
        """Records what the program is given."""

        def __init__(self, *args):
            made.append(args[-1])

        def build(self, *args):
            made.append(args[-1])
            return 'built'
    monkeypatch.setattr(RA, 'Program', Fake)
    radio = RA.Radio.__new__(RA.Radio)
    radio.builder = SimpleNamespace(counts=Counter())
    lounge = {'RecordFlags': str(RA.RADIO_STATION | RA.NON_PIPBOY)}
    radio.stations, radio.started = {7: lounge, 8: lounge, 9: {'RecordFlags': str(RA.RADIO_STATION)}}, {7, 8, 9}
    radio.refs, radio.receivers = {7: ['R7'], 8: ['R8'], 9: ['R9']}, {7: ['S7', 'unbuilt'], 8: ['S8'], 9: ['S9']}
    radio.npc_radios = set()
    ref_ids = {'R7': 0x70, 'R8': 0x80, 'R9': 0x90, 'S7': 0x71, 'S8': 0x81, 'S9': 0x91}
    assert radio._built({}, 1, 7, [{'DATA.Flags': '1'}], {}, ref_ids) == 'built'
    assert radio._built({}, 1, 8, [{'DATA.Flags': '2'}], {}, ref_ids) == 'built'
    assert radio._built({}, 1, 9, [{'DATA.Flags': '1'}], {}, ref_ids) == 'built'
    assert made == [True, ([0x71], 0), False, ([], 0), False, ([], 0)]
    assert radio.builder.counts['radio programs on demand'] == 1


def test_a_station_an_npc_plays_gets_one_invisible_receiver_on_its_frequency():
    """A live `SetNPCRadio <flag> <station>` (Lily's recording; not a commented one) gives the station one receiver
    activator, written once on vanilla's dummy-radio marker model and the station's frequency; others get none."""
    from fo4_import.spike import radio as RA
    from tes5_import.base.tes5_reader import subrecords
    text = '  ;EDE.SetNPCRadio 1 QuietREF\n  LilyREF.SetNPCRadio 1 VLilyGrandkidsRecordingREF\n'
    assert RA.NPC_RADIO_CALL.findall(text) == ['VLilyGrandkidsRecordingREF']
    radio, written = RA.Radio.__new__(RA.Radio), []
    radio.builder = SimpleNamespace(counts=Counter(), new_id=lambda key: 0x500 + len(key),
                                    writer=SimpleNamespace(add_record=lambda sig, data: written.append(data)))
    lounge = {'RecordFlags': str(RA.RADIO_STATION | RA.NON_PIPBOY), 'EditorID': 'Lily'}
    radio.stations, radio.refs, radio.npc_radios, radio.made = {7: lounge, 8: lounge}, {7: ['a'], 8: ['b']}, {7}, set()
    assert radio.npc_receiver(8) == 0 and radio.npc_receiver(7) == radio.npc_receiver(7) != 0
    subs = dict(subrecords(written[0][24:]))
    assert len(written) == 1 and subs[b'MODL'] == RA.NPC_RECEIVER_MODEL.encode() + b'\0'
    assert struct.unpack('<IffBB', subs[b'RADR'])[1] == RA.LOUNGE_FREQUENCIES[0]


def test_an_on_demand_programs_goodbye_line_ends_the_run():
    """The act's closing line (Goodbye) leads to no step on demand; on an always-on station it returns to
    RadioHello as before."""
    from fo4_import.spike import radio_program as RP
    program = RP.Program.__new__(RP.Program)
    program.topics = {RP.RADIO_HELLO: [{}]}
    program.steps = RP.steps(program.topics)
    bye, song = {'DATA.Flags': '1'}, {'DATA.Flags': '2'}
    program.on_demand = True
    assert (program.next_step(bye), program.next_step(song)) == (0, 1)
    program.on_demand = False
    assert program.next_step(bye) == 1


def test_a_step_scene_plays_each_song_on_its_own_gated_phase():
    """A step scene: its first topic's phase, later topics only while Said is 0, then each song phase only on its
    CurrentSong, playing its SNDR through a Radio action's sound (HTID), as DiamondCityRadioMusicScene's songs; its
    end fragment is F3NV_RadioScene's."""
    from fo4_import.spike import radio_program as RP
    from fo4_import.base.vmad import scene_fragments
    from fo4_import.spike.holotapes import pack_scene
    from tes5_import.base.tes5_reader import subrecords
    gates = [b'', RP.quest_var(0x0100, RP.SAID, 0), RP.quest_var(0x0100, RP.CURRENT_SONG, 1)]
    record = pack_scene(0x0200, 'Step', 0x0100, [0x0300, 0x0301, 0], RP.PLAYLIST_FLAGS, RP.HOST_ALIAS, 0,
                        sounds=[0, 0, 0x0401], conditions=gates, vmad=scene_fragments(RP.SCENE_SCRIPT, RP.SCENE_END))
    subs = subrecords(record[24:])
    tags = [t for t, _ in subs]
    assert tags[1] == b'VMAD' and b'F3NV_RadioScene' in subs[1][1] and subs[1][1].endswith(b'Fragment_End\0\0')
    assert [d for t, d in subs if t == b'CIS2'] == [b'::Said_var\0', b'::CurrentSong_var\0']
    ctda = subs[tags.index(b'CTDA')][1]
    assert struct.unpack_from('<fH', ctda, 4) == (0.0, CD.FO4.index('GetVMQuestVariable'))
    assert struct.unpack_from('<I', ctda, 12)[0] == 0x0100
    sounds = [struct.unpack('<I', d)[0] for t, d in subs if t == b'HTID']
    topics = [struct.unpack('<I', d)[0] for t, d in subs if t == b'DATA']
    assert sounds == [0, 0, 0x0401] and topics == [0x0300, 0x0301, 0]


def test_a_stations_steps_follow_its_lines_choices_from_radiohello():
    """Steps are the topic sets lines choose from, RadioHello first; a line without Choices (or naming a topic the
    station has no lines in) returns to RadioHello. Black Mountain's shape: a song, then one of its segments, each
    segment line leading to the segment again or back to RadioHello. A topic no line chooses (one a script starts)
    starts steps of its own after those; a station without RadioHello lines has none."""
    from fo4_import.spike import radio_program as RP
    hello, seg_a, seg_b, other = RP.RADIO_HELLO, '0000A001', '0000A002', '0000FFFF'

    def line(*choices):
        return {'ChoiceCount': str(len(choices)), **{f'Choice[{i}]': c for i, c in enumerate(choices)}}
    topics = {hello: [line(seg_a, seg_b)], seg_a: [line(seg_a), line(hello)], seg_b: [line(other)]}
    assert RP.steps(topics) == [(hello,), (seg_a, seg_b), (seg_a,)]
    assert RP.choices(line(other), topics) == (hello,) and RP.choices(line(), topics) == (hello,)
    raul, intro, music = '0000B001', '0000B002', '0000B003'
    scripted = {**topics, raul: [line()], intro: [line(music)], music: [line()]}
    assert RP.steps(scripted) == [(hello,), (seg_a, seg_b), (seg_a,), (raul,), (intro,), (music,)]
    assert RP.steps({raul: [line()]}) == []


def test_a_radio_activator_becomes_a_receiver_on_its_stations_frequency():
    """An FNV activator naming a placed Pip-Boy station gets RADR on that station's frequency, off until activated,
    and FNAM Is a Radio; a Non-Pipboy (lounge) station's frequency is outside the Pip-Boy's band; one naming no
    placed station stays a plain activator."""
    from fo4_import.spike import radio as RA
    from tes5_import.base.tes5_reader import subrecords
    radio = RA.Radio.__new__(RA.Radio)
    lounge = {'RecordFlags': str(RA.RADIO_STATION | RA.NON_PIPBOY)}
    radio.builder, radio.refs, radio.stations_of = SimpleNamespace(counts=Counter()), {5: ['a'], 9: ['b'], 3: ['c']}, \
        {1: 9, 2: 7, 4: 3}
    radio.stations = {5: {'RecordFlags': str(RA.RADIO_STATION)}, 9: {'RecordFlags': str(RA.RADIO_STATION)}, 3: lounge}
    data = radio.receiver(1)
    assert struct.unpack('<IffBB', data) == (RA.RECEIVER_OUTPUT, RA.FREQUENCIES[1], RA.RECEIVER_VOLUME, 0, 0) and radio.receiver(2) == b''
    assert struct.unpack('<IffBB', radio.receiver(4))[1] == RA.LOUNGE_FREQUENCIES[0]
    subs = dict(subrecords(R.pack_acti(0x10, 'Radio', 'Radio', 'r.nif', (0,) * 6, b'', '', 0, data)[24:]))
    assert subs[b'FNAM'] == struct.pack('<H', R.IS_A_RADIO) and subs[b'RADR'] == data


def test_standings_quests_hang_off_vanillas_event_nodes_after_their_last_child():
    """A Story Manager quest node goes under Fallout4.esm's event node after its last child (the one no sibling
    names as previous), sharing the event; an int array property packs as VMAD type 13."""
    from fo4_import.base.support_records import SHARES_EVENT, pack_story_node
    from fo4_import.spike import standings as ST
    from script_convert.pipeline import script_entry
    from tes5_import.base.tes5_reader import subrecords

    def node(fid, parent, previous):
        return pack_story_node(fid, f'N{fid}', parent, previous, (0x99,))
    raw = b''.join(node(fid, 0x50, prev) for fid, prev in ((0x51, 0), (0x52, 0x51), (0x53, 0x52)))
    raw += node(0x60, 0x70, 0)
    assert ST.last_child(raw, 0x50) == 0x53 and ST.last_child(raw, 0x80) == 0
    subs = dict(subrecords(node(0x54, 0x50, 0x53)[24:]))
    assert struct.unpack('<I', subs[b'DNAM'])[0] == SHARES_EVENT and struct.unpack('<I', subs[b'NNAM'])[0] == 0x99
    entry = script_entry('S', {}, {'KillMurders': ('ints', [1, 0, 2])})
    assert entry.endswith(struct.pack('<BBI3i', 13, 1, 3, 1, 0, 2))


def test_an_outfit_wears_one_item_per_slot_the_best_rated_as_fnv_equips():
    """Red Lucy's duster (DT 6) and sleepwear (DT 0) share the upper body: the duster is worn; a hat and a
    leveled list are worn too."""
    duster, sleepwear, hat, listed = 0x10D8DB, 0x340E6, 0x1, 0x2
    npcs = N.Npcs.__new__(N.Npcs)
    records = {duster: ('ARMO', {'BMDT.BipedFlags': '4'}), sleepwear: ('ARMO', {'BMDT.BipedFlags': '4'}),
               hat: ('ARMO', {'BMDT.BipedFlags': '1'}), listed: ('LVLI', {})}
    fields = {duster: {'rating': 6.0, 'value': 70}, sleepwear: {'rating': 0.0, 'value': 6}, hat: {'rating': 1.0}}
    npcs.builder = SimpleNamespace(items=SimpleNamespace(records=records), equipment=SimpleNamespace(fnv=fields))
    assert npcs._dressed([sleepwear, duster, hat, listed]) == {duster, hat, listed}


def test_a_reference_whose_enable_parent_is_not_built_starts_as_the_parent_leaves_it(monkeypatch):
    """Parent 0x2000 starts disabled: child 0x1000 (unbuilt parent) starts disabled, child 0x1001 (opposite bit)
    enabled; with the parent built, the child keeps its own flag."""
    def xesp(parent, opposite):
        """One XESP field."""
        return [(b'XESP', struct.pack('<IB3x', parent, opposite))]
    monkeypatch.setattr(PL, '_scan', lambda: ({0x1000: xesp(0x2000, 0), 0x1001: xesp(0x2000, 1)}, {0x2000: 0x800}))
    assert PL.starts_disabled({'FormID': '00001000', 'RecordFlags': '0'}, {})
    assert not PL.starts_disabled({'FormID': '00001001', 'RecordFlags': '0'}, {})
    assert not PL.starts_disabled({'FormID': '00001000', 'RecordFlags': '0'}, {'00002000': 0x123})


def test_a_receiver_of_a_station_past_the_free_frequencies_stays_a_plain_activator():
    """With more placed Pip-Boy stations than FREQUENCIES, a receiver naming the last one gets no RADR."""
    from fo4_import.spike import radio as RA
    radio = RA.Radio.__new__(RA.Radio)
    count = len(RA.FREQUENCIES) + 1
    radio.builder, radio.refs = SimpleNamespace(counts=Counter()), {i: ['r'] for i in range(count)}
    radio.stations = {i: {'RecordFlags': str(RA.RADIO_STATION)} for i in range(count)}
    radio.stations_of = {100: count - 1, 101: 0}
    assert radio.receiver(100) == b'' and radio.receiver(101) != b''
