"""fo4_import.spike.npcs template actors: the clone's attack race goes, and creatures' own parts resolve.

See: docs/fork/fo4_pipeline.md#template-actors
"""

import collections
import struct
from types import SimpleNamespace

from fo4_import.nif.creature import HEAD_SLOT
from fo4_import.spike import npcs as N
from fo4_import.spike import void_actors as VA
from fo4_import.spike.creatures import skeleton_folder
from script_convert.constants import FALLOUT4_HELPER_CREATURE_KEYWORD
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def test_a_template_actor_drops_the_clones_attack_race_and_unique_flag():
    """The stand-in's ATKR (the mole rat's) and Doc Weathers' Unique go; TPLT/TPTA land before RNAM, the rest
    is kept in order."""
    body = b''.join(pack_subrecord(tag, data) for tag, data in (
        ('ACBS', struct.pack('<I', 0x820) + bytes(16)), ('RNAM', struct.pack('<I', 0x1D810)),
        ('ATKR', struct.pack('<I', 0x1D810)), ('AIDT', bytes(24))))
    out = N.with_template(0x0300B001, 0x40)(body)
    tags = [t for t, _ in subrecords(out)]
    assert tags == [b'ACBS', b'TPLT', b'TPTA', b'RNAM', b'AIDT']
    tpta = struct.unpack('<13I', dict(subrecords(out))[b'TPTA'])
    assert tpta[6] == 0x0300B001 and tpta.count(0) == 12
    assert struct.unpack_from('<I', dict(subrecords(out))[b'ACBS'])[0] == 0x800


def test_a_copy_never_keeps_the_bodys_unique_flag():
    """FNV has no Unique flag: Doc Weathers' 0x820 keeps neither Unique nor (unasked) Protected."""
    from fo4_import.spike import actor_data as A
    body = struct.pack('<I', 0x820) + bytes(16)
    assert struct.unpack_from('<I', A.acbs(body, {'ACBS.Flags': '0'}, A.NPC_FLAGS))[0] == 0
    assert struct.unpack_from('<I', A.acbs(body, {'ACBS.Flags': '2'}, A.NPC_FLAGS, True))[0] == 0x802


def _npcs() -> N.Npcs:
    """An Npcs over one NPC and three creatures: one owning its packages, one taking them, their template."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.records = {0xA01: {'FormID': '00000A01', 'AIPackageCount': '1', 'AIPackage[0]': '00000F01'}}
    base = {'FormID': '00000C01', 'AIPackageCount': '1', 'AIPackage[0]': '00000F02'}
    own = {'FormID': '00000C02', 'ACBS.TemplateFlags': '349', 'TPLT.Template': '00000C01',
           'AIPackageCount': '1', 'AIPackage[0]': '00000F03'}
    taken = {'FormID': '00000C03', 'ACBS.TemplateFlags': '32', 'TPLT.Template': '00000C01'}
    npcs.creatures = SimpleNamespace(records={0xC01: base, 0xC02: own, 0xC03: taken})
    return npcs


def test_a_template_actors_script_naming_its_own_base_gets_its_reserved_formid():
    """A templated creature's script property naming that creature's base (ActorBase) gets the FormID the creature
    is being written on, not a second making of it (which recursed until Python stopped it)."""
    npcs = N.Npcs.__new__(N.Npcs)
    rec = {'FormID': '00008E70', 'EditorID': 'Brute', 'TPLT.Template': '000086D3', 'ACBS.TemplateFlags': '1'}
    npcs.records, npcs.made, npcs.lists, npcs.bodies = {}, {}, {}, {N.body_kind(False, False): 'male body'}
    npcs.creatures = SimpleNamespace(records={0x8E70: rec}, stand_in=lambda fnv: None, own_guns=lambda r: (False, None),
                                     actor_data=lambda *a: None, own_parts=lambda r, templated: (),
                                     inventory=lambda *a: None, keeps_look=lambda fnv: False, traits_variant=lambda r: 0,
                                     label=lambda fnv: 'creatures\tunneler')
    npcs.builder = SimpleNamespace(new_id=lambda key: 0x04118A44 if key == N.NPC_KEY.format(0x8E70) else 1,
                                   counts=collections.Counter(), npc_ids={})
    real, seen = npcs.actor_form, []
    npcs.actor_form = lambda hex_id: 0x0300AAAA if hex_id == '000086D3' else real(hex_id)
    npcs._packages, npcs._template_style, npcs._template_flags = (lambda fnv: None), (lambda r: None), (lambda r: 1)
    npcs._template_script = lambda r: seen.append(npcs.actor_form('00008E70'))
    npcs._template_actor = lambda fnv, r, template, flags, parts, body, traits, fid: fid
    assert npcs._creature(0x8E70) == 0x04118A44 and seen == [0x04118A44]


def test_a_templated_creature_takes_packages_from_itself_unless_flagged():
    """Jacobstown's nightstalker (flags 349, no Use AI Packages) keeps its own; with 0x20, its template's."""
    npcs = _npcs()
    assert npcs.source(0xC02, N.USE_PACKAGES)['FormID'] == '00000C02'
    assert npcs.source(0xC03, N.USE_PACKAGES)['FormID'] == '00000C01'
    assert npcs.source(0xA01, N.USE_PACKAGES)['FormID'] == '00000A01'
    assert npcs.source(0xD00, N.USE_PACKAGES) is None


def test_an_npc_with_its_own_traits_takes_its_listed_parts_from_the_lists_copy():
    """Freeside's vaporized tourist (flags 392: inventory, base data, actor effects; traits its own) gets a
    template on the squatter list's copy for those three parts; an NPC with nothing listed gets none."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.records = {0xA01: {'FormID': '00000A01', 'ACBS.TemplateFlags': '392', 'TPLT.Template': '00000B01'},
                    0xA02: {'FormID': '00000A02'}}
    npcs.creatures, npcs.lists = SimpleNamespace(records={}), {0xB01: {}}
    npcs.builder = SimpleNamespace(counts={'NPC_ with a listed template': 0})
    npcs.actor_form = lambda hex_id: 0x0300B001 if hex_id == '00000B01' else None
    body = b''.join(pack_subrecord(t, d) for t, d in (('ACBS', bytes(20)), ('RNAM', struct.pack('<I', 0x13746))))
    out = dict(subrecords(npcs._listed_template(0xA01)(body)))
    assert struct.unpack_from('<H', out[b'ACBS'], N.ACBS_TEMPLATE)[0] == 392
    assert struct.unpack('<I', out[b'TPLT'])[0] == 0x0300B001
    assert npcs._listed_template(0xA02) is None and npcs.builder.counts['NPC_ with a listed template'] == 1


def _void_npcs() -> N.Npcs:
    """An Npcs over a void creature, a list holding it and a coyote, a creature templated on that list (own
    script, no Use Script), one with Use Script, one templated on the void itself, and the plain coyote;
    scripts.vmad records its calls."""
    npcs = N.Npcs.__new__(N.Npcs)
    folders = {0xE01: 'creatures\\nvvoid', 0xE03: 'creatures\\coyote', 0xE04: 'creatures\\coyote',
               0xE05: 'creatures\\coyote', 0xE06: 'creatures\\coyote'}
    entry = lambda i, form: {f'Entry[{i}].Level': '1', f'Entry[{i}].FormID': form, f'Entry[{i}].Count': '1'}
    npcs.records, npcs.lists = {}, {0xE02: {'FormID': '00000E02', 'EditorID': 'L', 'EntryCount': '2',
                                            **entry(0, '00000E01'), **entry(1, '00000E05')}}
    npcs.creatures = SimpleNamespace(records={
        0xE01: {'FormID': '00000E01'},
        0xE03: {'FormID': '00000E03', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000E02', 'SCRI': '00000F0A'},
        0xE04: {'FormID': '00000E04', 'ACBS.TemplateFlags': '513', 'TPLT.Template': '00000E02'},
        0xE05: {'FormID': '00000E05'},
        0xE06: {'FormID': '00000E06', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000E01', 'SCRI': '00000F0B'}},
        label=folders.get)
    calls = []
    npcs.builder = SimpleNamespace(scripts=SimpleNamespace(vmad=lambda scpt, extra=(): calls.append((scpt, extra))
                                                           or b'vmad'))
    npcs.voids = SimpleNamespace(actor=lambda: 0x0300F00D, check=lambda: (('F3NV_VoidActor', {'VoidRace': 7}, {}),))
    npcs.calls = calls
    return npcs


def test_a_void_share_follows_lists_and_traits_templates():
    """The void is 1, its half of a two-entry list 0.5, a creature whose traits come from that list 0.5 too; a
    plain coyote 0. Only a template on the void alone always draws it."""
    npcs = _void_npcs()
    assert npcs.actor_form('00000E01') == 0x0300F00D
    assert [npcs.void_share(f) for f in (0xE01, 0xE02, 0xE03, 0xE05, 0xE06)] == [1.0, 0.5, 0.5, 0.0, 1.0]
    assert npcs._draws_void(0xE06) and not npcs._draws_void(0xE02) and not npcs._draws_void(0xE03)


def test_a_list_leaves_out_its_void_entries():
    """FO4 draws each template part on its own, so a void entry would mix into the coyote: only the coyote stays."""
    npcs = _void_npcs()
    written = []
    npcs.made_lists = {}
    npcs.builder = SimpleNamespace(fnv_id=lambda hex_id: 0x0300E002, counts=collections.Counter(),
                                   writer=SimpleNamespace(add_record=lambda sig, rec: written.append(rec)))
    npcs.actor_form = lambda hex_id: {'00000E01': 0x0300F00D, '00000E05': 0x0300E005}[hex_id]
    assert npcs._list(0xE02) == 0x0300E002
    assert struct.pack('<I', 0x0300E005) in written[0] and struct.pack('<I', 0x0300F00D) not in written[0]


def test_a_template_actor_runs_its_own_script_and_the_void_check_only_on_the_void_itself():
    """Without Use Script: VMAD of its own script after EDID, plus the void check when its template is the void
    itself (a list holds none); with Use Script: no edit (FO4's Script slot gives the template's)."""
    npcs = _void_npcs()
    rec = npcs.creatures.records
    edit = npcs._template_script(rec[0xE03])
    out = edit(pack_subrecord('EDID', b'X\0') + pack_subrecord('OBND', bytes(12)))
    assert [t for t, _ in subrecords(out)] == [b'EDID', b'VMAD', b'OBND']
    npcs._template_script(rec[0xE06])
    assert npcs.calls == [(0xF0A, ()), (0xF0B, (('F3NV_VoidActor', {'VoidRace': 7}, {}),))]
    assert npcs._template_script(rec[0xE04]) is None


def test_a_placed_actor_rolls_its_bases_void_share():
    """chance: the roll script with the share as a float, marked used once; nothing at 0."""
    voids = VA.VoidActors(SimpleNamespace(scripts=SimpleNamespace(used=[])))
    assert voids.chance(0.0) == ()
    assert voids.chance(0.25) == ((VA.CHANCE_SCRIPT, {}, {'Chance': ('float', 0.25)}),)
    voids.chance(0.5)
    assert voids.builder.scripts.used == [VA.CHANCE_SCRIPT]


def test_the_void_actor_is_the_copy_on_its_race_with_its_script_and_nothing_of_the_copys():
    """The void copy: VMAD after EDID, race and skin replaced, a ghost, template flags and aggression 0, factions,
    packages, items and attack race left out."""
    from fo4_import.spike import void_actors as V
    calls = []
    voids = V.VoidActors(SimpleNamespace(scripts=SimpleNamespace(vmad=lambda s, e: calls.append((s, e)) or b'V')))
    voids.race = 0x0300AAAA
    body = b''.join(pack_subrecord(tag, data) for tag, data in (
        ('EDID', b'EncMolerat01Template\0'), ('OBND', bytes(12)), ('ACBS', bytes(14) + b'\xff\x01' + bytes(4)),
        ('SNAM', bytes(5)), ('RNAM', struct.pack('<I', 0x1D810)), ('WNAM', struct.pack('<I', 1)),
        ('ATKR', struct.pack('<I', 0x1D810)), ('AIDT', b'\x02' + bytes(23)), ('PKID', bytes(4))))
    vanilla = SimpleNamespace(sig=b'NPC_', body=body, flags=0)
    record = V.copy_record(vanilla, 0x0300BBBB, 'FNV_VoidActor', drop=V.DROPPED, edit=voids._actor_edit(0x0300CCCC))
    subs = list(subrecords(record[24:]))
    assert [t for t, _ in subs] == [b'EDID', b'VMAD', b'OBND', b'ACBS', b'RNAM', b'WNAM', b'AIDT']
    found = dict(subs)
    assert found[b'EDID'] == b'FNV_VoidActor\0' and found[b'VMAD'] == b'V'
    assert struct.unpack('<I', found[b'RNAM'])[0] == 0x0300AAAA and struct.unpack('<I', found[b'WNAM'])[0] == 0x0300CCCC
    assert found[b'ACBS'][14:16] == b'\0\0' and found[b'AIDT'][0] == 0
    assert struct.unpack_from('<I', found[b'ACBS'])[0] & V.GHOST
    assert calls == [(0, ((V.SCRIPT, {}, {}),))]


def test_an_invisible_race_has_no_attacks():
    """The race copy keeps everything but its attack data, so the void actor cannot hurt anyone."""
    from fo4_import.spike import void_actors as V
    race = b''.join(pack_subrecord(tag, data) for tag, data in (
        ('EDID', b'MoleratRace\0'), ('ATKD', bytes(8)), ('ATKE', b'bite\0'), ('DATA', bytes(40))))
    record = V.copy_record(SimpleNamespace(sig=b'RACE', body=race, flags=0), 0x0300AAAA, 'FNV_VoidRace',
                           drop=V.ATTACKS)
    assert [t for t, _ in subrecords(record[24:])] == [b'EDID', b'DATA']


def test_traits_bring_fo4s_three_extra_slots_but_a_creature_on_a_creature_keeps_its_keywords():
    """Traits from a list: Attack Data, Def Pack List and Keywords too; from a creature: not Keywords (its own
    sound set may differ); an NPC on an NPC: all three; no Traits: FNV's bits only."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.records = {0xA01: {'FormID': '00000A01'},
                    0xA02: {'FormID': '00000A02', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000A01'}}
    npcs.creatures = SimpleNamespace(records={
        0xC01: {'FormID': '00000C01'},
        0xC02: {'FormID': '00000C02', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000C01'},
        0xC03: {'FormID': '00000C03', 'ACBS.TemplateFlags': '513', 'TPLT.Template': '00000D00'},
        0xC04: {'FormID': '00000C04', 'ACBS.TemplateFlags': '4', 'TPLT.Template': '00000C01'}})
    creatures = npcs.creatures.records
    extra = N.USE_ATTACKS | N.USE_DEF_PACKS
    assert npcs._template_flags(creatures[0xC02]) == 0x1 | extra
    assert npcs._template_flags(creatures[0xC03]) == 0x201 | extra | N.USE_KEYWORDS
    assert npcs._template_flags(npcs.records[0xA02]) == 0x1 | extra | N.USE_KEYWORDS
    assert npcs._template_flags(creatures[0xC04]) == 0x4
    tpta = dict(subrecords(N.with_template(5, N.ALL_PARTS)(pack_subrecord('RNAM', bytes(4)))))[b'TPTA']
    assert struct.unpack('<13I', tpta) == (5,) * 13


def test_a_keyword_edit_gives_a_record_without_keywords_a_list_after_its_ai_data():
    """No KWDA: KSIZ/KWDA land after the last AIDT/PKID; with one, the keyword joins it once."""
    from fo4_import.spike import type_tests as T
    bare = pack_subrecord('AIDT', bytes(24)) + pack_subrecord('PKID', bytes(4)) + pack_subrecord('CNAM', bytes(4))
    out = list(subrecords(T.keywords_edit([7])(bare)))
    assert [t for t, _ in out] == [b'AIDT', b'PKID', b'KSIZ', b'KWDA', b'CNAM']
    assert dict(out)[b'KSIZ'] == struct.pack('<I', 1) and dict(out)[b'KWDA'] == struct.pack('<I', 7)
    again = dict(subrecords(T.keywords_edit([7, 9])(T.keywords_edit([7])(bare))))
    assert struct.unpack('<2I', again[b'KWDA']) == (7, 9)


def test_a_body_without_items_gets_them_before_its_ai_data():
    """with_inventory on a mole rat (no COCT): COCT and CNTO land before AIDT; its outfit goes when none."""
    body = pack_subrecord('DOFT', struct.pack('<I', 9)) + pack_subrecord('AIDT', bytes(24))
    out = list(subrecords(N.with_inventory(0, [(0x0300A001, 2, None)])(body)))
    assert [t for t, _ in out] == [b'COCT', b'CNTO', b'AIDT']
    assert dict(out)[b'CNTO'] == struct.pack('<Ii', 0x0300A001, 2)


def test_fnv_attack_gear_is_its_non_playable_weapons_and_ammo():
    """EyeBot1HP (0xA8) and Ammo5mmRobot (0x2) are gear; a playable gun, ammo or anything else is not."""
    from fo4_import.spike import creatures as CR
    assert CR.fnv_gear('WEAP', {'DNAM.Flags1': '168'}) and CR.fnv_gear('AMMO', {'DATA.Flags': '2'})
    assert not CR.fnv_gear('WEAP', {'DNAM.Flags1': '0'}) and not CR.fnv_gear('AMMO', {'DATA.Flags': '0'})
    assert not CR.fnv_gear('LVLI', {}) and not CR.fnv_gear(None, {})


def test_a_creature_keeps_its_stand_ins_attack_gear_and_carries_fnvs_loot():
    """The stand-in's non-playable weapon stays, its loot list goes; FNV's playable loot is added, its attack
    weapon is not; the outfit stays only when asked (stats mode)."""
    from fo4_import.spike import creatures as CR
    made = {0xF01: 0x0300F001}
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.gear, creatures.ranged = {0x7001}, {}
    creatures.records = {0xC01: {'FormID': '00000C01', 'ItemCount': '2', 'Item[0].FormID': '00000F01',
                                 'Item[0].Count': '3', 'Item[1].FormID': '00000F02', 'Item[1].Count': '1'}}
    creatures.builder = SimpleNamespace(counts=__import__('collections').Counter(), items=SimpleNamespace(
        records={0xF01: ('LVLI', {}), 0xF02: ('WEAP', {'DNAM.Flags1': '160'})}, item=made.get))
    body = SimpleNamespace(body=pack_subrecord('DOFT', struct.pack('<I', 9)) + pack_subrecord('COCT', b'\2\0\0\0')
                           + pack_subrecord('CNTO', struct.pack('<Ii', 0x7001, 1))
                           + pack_subrecord('CNTO', struct.pack('<Ii', 0x7002, 1)) + pack_subrecord('AIDT', bytes(24)))
    for outfit in (True, False):
        out = list(subrecords(creatures.inventory(creatures.records[0xC01], body, outfit)(body.body)))
        assert [d for t, d in out if t == b'CNTO'] == [struct.pack('<Ii', 0x7001, 1), struct.pack('<Ii', 0x0300F001, 3)]
        assert (b'DOFT' in dict(out)) is outfit


def test_a_stand_ins_ranged_gear_stays_only_with_a_ranged_fnv_creature():
    """A deathclaw's dirt throw (ranged gear and its ammo) goes when FNV's creature has no ranged weapon; melee gear
    stays; an FNV creature with a ranged weapon (animation type 3+) keeps it all.
    See: docs/fork/fo4_creature_audit.md#deathclaws
    """
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.gear, creatures.ranged = {0x7001, 0x7003, 0x7004}, {0x7001: 0x7003}
    creatures.records = {0xC01: {'FormID': '00000C01', 'ItemCount': '0'},
                         0xC02: {'FormID': '00000C02', 'ItemCount': '1', 'Item[0].FormID': '00000F02',
                                 'Item[0].Count': '1'}}
    laser = {'DNAM.Flags1': '160', 'DNAM.FalloutAnimType': '3'}
    creatures.builder = SimpleNamespace(counts=collections.Counter(), items=SimpleNamespace(
        records={0xF02: ('WEAP', laser)}, item=lambda fnv: None))
    body = SimpleNamespace(body=b''.join(pack_subrecord('CNTO', struct.pack('<Ii', f, 1)) for f in (0x7001, 0x7003, 0x7004)) + pack_subrecord("AIDT", bytes(24)))
    kept = {}
    for fnv, rec in creatures.records.items():
        out = subrecords(creatures.inventory(rec, body, False)(body.body))
        kept[fnv] = [struct.unpack_from('<I', d)[0] for t, d in out if t == b'CNTO']
    assert kept == {0xC01: [0x7004], 0xC02: [0x7001, 0x7003, 0x7004]}


def test_an_armed_creature_keeps_its_fnv_gun_with_the_copys_ammo():
    """A ranged rig keeps its FNV attack gun (its table copy) with the copy's ammo: FNV's count of the gun's own
    ammo, else ARMED_AMMO; a creature gun copy goes to its forced-inventory mod (_guns), leaving only the ammo."""
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    gun = {'DNAM.Flags1': '160', 'NAM0': '00000F03'}
    creatures.builder = SimpleNamespace(
        counts=__import__('collections').Counter(), equipment=SimpleNamespace(weapon_ammo={0xF02: 0x0300A001}, creature_guns={}),
        items=SimpleNamespace(records={0xF02: ('WEAP', gun), 0xF03: ('AMMO', {'DATA.Flags': '2'})},
                              item={0xF02: 0x0300F002}.get))
    rec = {'FormID': '00000C01', 'ItemCount': '2', 'Item[0].FormID': '00000F02', 'Item[0].Count': '1',
           'Item[1].FormID': '00000F03', 'Item[1].Count': '40'}
    assert [(f, n) for f, n, _ in creatures._carried(rec, armed=True)] == [(0x0300A001, 40), (0x0300F002, 1)]
    assert creatures._carried(rec) == []
    rec_no_ammo = {**rec, 'ItemCount': '1'}
    assert [n for _, n, _ in creatures._carried(rec_no_ammo, armed=True)] == [CR.ARMED_AMMO, 1]
    assert creatures._guns(rec) == []
    creatures.builder.equipment.creature_guns[0xF02] = 0x13F42
    assert [(f, n) for f, n, _ in creatures._carried(rec, armed=True)] == [(0x0300A001, 40)]
    assert creatures._guns(rec) == [(0xF02, 0x0300F002, 0x13F42)]


def test_a_placed_actor_links_to_an_actor_placed_after_it_and_keeps_no_ai_acquire_and_scale(monkeypatch):
    """placed() numbers every built actor first, so A's linked ref (B, sorted after A) resolves; A keeps FNV's
    No AI Acquire flag and its scale (XSCL before DATA); an actor whose base is not built gets no FormID."""
    monkeypatch.setattr(N, 'placement', lambda fid, ids, owners, pose=True: b'')
    monkeypatch.setattr(N, 'starts_disabled', lambda ref, ids: False)
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.records, ids = {}, iter(range(0x0300A000, 0x0300B000))
    npcs.creatures = SimpleNamespace(records={}, as_is={}, speaker_look=lambda *_: b"")
    npcs.builder = SimpleNamespace(counts=__import__('collections').Counter(), actor_ids={},
                                   new_id=lambda key: next(ids),
                                   scripts=SimpleNamespace(named={}, vmad=lambda scpt, extra=(): b''))
    npcs.lists, npcs.voids = {}, SimpleNamespace(chance=lambda share: ())
    npcs.warm_faces = lambda bases: None
    npcs._base_of = lambda fnv: None if fnv == 0xB03 else 0x03000B00 | fnv
    npcs._unbuilt = lambda ref: 'unbuilt'
    ref = lambda fid, **extra: {'FormID': fid, 'NAME': fid[-3:].rjust(8, '0'), 'RecordFlags': '33554432',
                                'PosX': '0', 'PosY': '0', 'PosZ': '0', 'RotX': '0', 'RotY': '0', 'RotZ': '0', **extra}
    refs = [ref('00000B01', **{'XLKR.LinkedRef': '00000B02', 'XSCL.Scale': '1.5'}), ref('00000B02'), ref('00000B03')]
    placed = npcs.placed(refs, lambda r: 'cell', {}, {})['cell'][1]
    first = placed[:24 + struct.unpack_from('<I', placed, 4)[0]]
    subs = list(subrecords(first[24:]))
    assert struct.unpack_from('<I', first, 8)[0] & N.NO_AI_ACQUIRE
    assert [t for t, _ in subs] == [b'NAME', b'XLKR', b'XSCL', b'DATA']
    assert dict(subs)[b'XLKR'] == struct.pack('<II', 0, npcs.builder.actor_ids['00000B02'])
    assert struct.unpack('<f', dict(subs)[b'XSCL'])[0] == 1.5 and '00000B03' not in npcs.builder.actor_ids


def test_the_traits_slot_can_name_its_own_template():
    """`traits` fills slot 0 only; other flagged slots keep the template."""
    tpta = dict(subrecords(N.with_template(5, 0x1 | 0x2, traits=9)(pack_subrecord('RNAM', bytes(4)))))[b'TPTA']
    assert struct.unpack('<13I', tpta)[:3] == (9, 5, 0)


def _sized_creatures():
    """A Creatures over a stand-in base (scale 1), a variant with its own Stats at 1.5 and speed 80, one at the
    same scale, one taking Stats from its template; base() and _sized are recorded."""
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.records = {
        0xD01: {'FormID': '00000D01', 'EditorID': 'Base', 'BNAM.BaseScale': '1.0'},
        0xD02: {'FormID': '00000D02', 'EditorID': 'Big', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000D01',
                'BNAM.BaseScale': '1.5', 'ACBS.SpeedMultiplier': '80'},
        0xD03: {'FormID': '00000D03', 'EditorID': 'Same', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000D01',
                'BNAM.BaseScale': '1.0'},
        0xD04: {'FormID': '00000D04', 'EditorID': 'Taken', 'ACBS.TemplateFlags': '3', 'TPLT.Template': '00000D01',
                'BNAM.BaseScale': '1.5'}}
    creatures.converts = lambda fnv: True
    creatures._entry = lambda rec: (SimpleNamespace(mode='rig', edid='EncMolerat01Template'), 'creatures/x')
    creatures.calls = []
    creatures.base = lambda fnv, packages=(), stats=None: creatures.calls.append((fnv, stats['EditorID'])) or 0x0300E000
    return creatures


def test_a_template_actor_sized_by_its_own_stats_takes_a_resized_copy_of_its_traits_creature():
    """Own Stats at another scale: the traits creature's base built at that scale; same scale or Stats taken from
    the template: none."""
    creatures = _sized_creatures()
    assert creatures.traits_variant(creatures.records[0xD02]) == 0x0300E000
    assert creatures.calls == [(0xD01, 'Big')]
    assert creatures.traits_variant(creatures.records[0xD03]) is None
    assert creatures.traits_variant(creatures.records[0xD04]) is None


def test_a_template_actor_with_its_own_stats_runs_at_its_own_speed():
    """On a rig: FNV's own SpeedMult (80) in PRPS; traits from a list: no edit."""
    from fo4_import.spike import creature_speed as CS
    creatures = _sized_creatures()
    out = creatures._own_speed(creatures.records[0xD02])(pack_subrecord('AIDT', bytes(24)))
    prps = dict(subrecords(out))[b'PRPS']
    assert struct.unpack('<If', prps) == (CS.SPEED_MULT, 80.0)
    creatures.records[0xD05] = {'FormID': '00000D05', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000F00'}
    assert creatures._own_speed(creatures.records[0xD05]) is None


def test_a_creature_takes_essential_and_ghost_from_base_data_and_its_level_mult_from_stats():
    """Stats template: PC Level Mult (0x80); Base Data template: Essential, Is Ghost, Invulnerable; acbs keeps
    all of them, and Invulnerable (bit 31) survives FO4's flags word."""
    from fo4_import.spike import actor_data as A
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.records = {
        0xE10: {'FormID': '00000E10', 'ACBS.Flags': str(0x80 | 0x8)},
        0xE11: {'FormID': '00000E11', 'ACBS.Flags': str(0x2 | A.IS_GHOST | A.INVULNERABLE)},
        0xE12: {'FormID': '00000E12', 'ACBS.Flags': '0', 'ACBS.TemplateFlags': str(0x2 | 0x80),
                'TPLT.Template': '00000E10'}}
    seen = []
    creatures.actor_data = lambda rec, stats, ai: seen.append(int(stats['ACBS.Flags']))
    creatures._actor_data(creatures.records[0xE12])
    creatures.records[0xE12]['TPLT.Template'] = '00000E11'
    creatures.records[0xE12]['ACBS.TemplateFlags'] = str(0x80)
    creatures._actor_data(creatures.records[0xE12])
    assert seen == [0x80 | 0x8, 0x2 | A.IS_GHOST | A.INVULNERABLE]
    flags = struct.unpack_from('<I', A.acbs(bytes(20), {'ACBS.Flags': str(seen[1])}, A.CREATURE_FLAGS))[0]
    assert flags == 0x2 | A.IS_GHOST | A.INVULNERABLE


def test_a_creature_taking_its_model_from_its_template_takes_its_traits_too():
    """Model/Animation from the template (BMRoadblock1Mutant's 0x3C0): a template actor whose FO4 flags add Traits,
    so FO4's race and skin come with the model; an NPC's flags stay FNV's."""
    npcs = N.Npcs.__new__(N.Npcs)
    npcs.records = {0xA03: {'FormID': '00000A03', 'ACBS.TemplateFlags': '64', 'TPLT.Template': '00000A01'}}
    npcs.creatures = SimpleNamespace(records={
        0xC01: {'FormID': '00000C01'},
        0xC05: {'FormID': '00000C05', 'ACBS.TemplateFlags': '960', 'TPLT.Template': '00000C01'}})
    flags = npcs._template_flags(npcs.creatures.records[0xC05])
    assert flags & N.USE_TRAITS and flags & 0x3C0 == 0x3C0
    assert npcs._template_flags(npcs.records[0xA03]) == 0x40
    assert N._model_templated(npcs.creatures.records[0xC05]) and not N._model_templated({'ACBS.TemplateFlags': '64'})


def test_an_fnv_creatures_skin_shows_fo4s_head_over_fo4s_body_and_is_written_once_for_its_sized_copies():
    """FNV's armor over FO4's body: the skin and addon add FX (61), not the head, so the race's head shows, and the
    creature gets the tinted face set; the skin lists FO4's tinted body addon first, then FNV's; a sized copy
    reuses the skin. Without FO4's body (no bare skin) both add FaceGen head (32), hiding the race's head."""
    from fo4_import.spike import creatures as CR
    added = []

    def vanilla(sig: str, *subs: tuple) -> SimpleNamespace:
        """A vanilla record of `subs` [(tag, data)]."""
        return SimpleNamespace(sig=sig.encode(), flags=0, body=b''.join(pack_subrecord(t, d) for t, d in subs))
    skin = vanilla('ARMO', ('EDID', b'SkinSuperMutant\0'), ('BOD2', struct.pack('<I', 0x8)), ('MODL', bytes(4)))
    addon = vanilla('ARMA', ('EDID', b'SuperMutantBody\0'), ('BOD2', struct.pack('<I', 0x8)), ('MOD2', b'x.nif\0'))
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.skins, creatures.faces, creatures.worn = {}, {}, {'encsupermutanttemplate': (None, skin, addon)}
    creatures.records = {fid: {'FormID': f'{fid:08X}', 'EditorID': f'Cr{fid:X}',
                               'Model.MODL': 'Creatures\\SMSpineBreaker\\Skeleton.nif'} for fid in (0x3A147, 0x3A148)}
    creatures._mesh = lambda rec, folder: ('body.nif', 'textures\\skin.dds' if rec['FormID'] == '0003A147' else None)
    creatures._fo4_body = lambda vanilla_addon, folder, bare: 0x0300_1234
    creatures._face = lambda npc, bare: 0x0300_5555
    creatures.builder = SimpleNamespace(writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x0300_0000 + len(key) + int(key[:8], 16) % 7,
        add_record=lambda sig, data: added.append(data)))
    entry = SimpleNamespace(edid='EncSuperMutantTemplate')
    assert creatures._skin(0x3A147, entry) == creatures._skin(0x3A147, entry) and len(added) == 2
    creatures._skin(0x3A148, entry)
    slots = [struct.unpack('<I', dict(subrecords(record[24:]))[b'BOD2'])[0] for record in added]
    assert slots == [0x8 | CR.FX_SLOT, 0x8 | CR.FX_SLOT, 0x8 | HEAD_SLOT, 0x8 | HEAD_SLOT]
    assert creatures.faces == {0x3A147: 0x0300_5555}
    arma = struct.unpack_from('<I', added[0], 12)[0]
    models = [struct.unpack('<I', d)[0] for t, d in subrecords(added[1][24:]) if t == b'MODL']
    assert models == [0x0300_1234, arma]


def test_with_face_puts_ftst_before_qnam():
    """with_face sets FTST once, right before QNAM, as vanilla's super mutants have it."""
    from fo4_import.spike import records
    subs = pack_subrecord('DPLT', bytes(4)) + pack_subrecord('FTST', bytes(4)) + pack_subrecord('QNAM', bytes(16))
    out = records.with_face(0x0300_5555)(subs)
    assert [t for t, _ in subrecords(out)] == [b'DPLT', b'FTST', b'QNAM']
    assert dict(subrecords(out))[b'FTST'] == struct.pack('<I', 0x0300_5555)


def test_fo4s_body_addon_wears_the_tint_swap_after_each_model(monkeypatch):
    """_fo4_body writes an MSWP of the tinted pairs and a copy of the vanilla addon with MO2S/MO3S naming it right
    after MOD2/MOD3, once per folder and skin."""
    from fo4_import.spike import creatures as CR
    added = []
    addon = SimpleNamespace(sig=b'ARMA', flags=0, form_id=0x1A000, body=b''.join(pack_subrecord(t, d) for t, d in (
        ('EDID', b'SuperMutantBody\0'), ('MOD2', b'm.nif\0'), ('MO2T', bytes(4)), ('MOD3', b'f.nif\0'))))
    monkeypatch.setattr(CR, 'tinted', lambda *args: [('actors\\a.bgsm', 'fnv\\tinted\\a.bgsm')])
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.tinted, creatures.tint_archives, creatures.export_dir, creatures.data_dir = {}, object(), None, None
    creatures.builder = SimpleNamespace(writer=SimpleNamespace(
        derive_formid=lambda site, key: 0x0300_0000 + len(key), add_record=lambda sig, data: added.append((sig, data))))
    first = creatures._fo4_body(addon, 'creatures\\smspinebreaker', 'textures\\skin.dds')
    assert creatures._fo4_body(addon, 'creatures\\smspinebreaker', 'textures\\skin.dds') == first
    (sig_a, swap), (sig_b, arma) = added
    assert (sig_a, sig_b) == ('MSWP', 'ARMA') and struct.unpack_from('<I', arma, 12)[0] == first
    tags = [t for t, _ in subrecords(arma[24:])]
    assert tags == [b'EDID', b'MOD2', b'MO2S', b'MOD3', b'MO3S']
    assert struct.unpack('<I', dict(subrecords(arma[24:]))[b'MO2S'])[0] == struct.unpack_from('<I', swap, 12)[0]


def test_a_templated_creature_carrying_its_own_guns_is_armed_with_them():
    """Freeside's gate securitron takes traits from a template but not its inventory (played 2026-11-02: no guns,
    no fire): own_guns arms it with its own creature gun copies; one whose inventory is its template's is not."""
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    own = {'FormID': '00119790', 'ACBS.TemplateFlags': '27', 'TPLT.Template': '00158646'}
    borrowed = {'FormID': '00119791', 'ACBS.TemplateFlags': str(0x100), 'TPLT.Template': '00158646'}
    template = {'FormID': '00158646'}
    creatures.records = {0x119790: own, 0x119791: borrowed, 0x158646: template}
    creatures._guns = lambda rec: [(0x10A709, 0x0300_0001, 'slot')] if rec is not template else []
    creatures.gun_mods = SimpleNamespace(edit=lambda guns: ('edit', tuple(guns)))
    assert CR.Creatures.own_guns(creatures, own) == (True, ('edit', ((0x10A709, 0x0300_0001, 'slot'),)))
    assert CR.Creatures.own_guns(creatures, borrowed) == (False, None)


def test_a_dlc_creatures_skeleton_folder_is_the_one_holding_its_skeleton():
    """Dead Money keeps its creatures a level deeper (nvdlc01/creatures/ghosts): each folder keys its own rule."""
    assert skeleton_folder(r'Creatures\Dog\Skeleton.nif') == r'creatures\dog'
    assert skeleton_folder(r'NVDLC01\Creatures\Ghosts\skeleton.nif') == r'nvdlc01\creatures\ghosts'
    assert skeleton_folder('NVDLC01/Creatures/Hologram/skeleton.nif') == r'nvdlc01\creatures\hologram'
    assert skeleton_folder('marker_creature.nif') == 'marker_creature.nif'


def test_a_creature_on_fo4s_human_speaks_with_its_sound_sets_unrecorded_voice():
    """A ghost has no VTCK; its sound set (CSCR) speaks VoiceDoNotRecordF, which FNV never recorded: on FO4's human
    it takes that voice type, silent, not the raider body's."""
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    ghost, audio = {'FormID': '01000BAD'}, {'FormID': '01012177', 'VTCK.Voice': '00094EED'}
    creatures.sounds = SimpleNamespace(source=lambda rec: audio)
    creatures.voices = SimpleNamespace(of=lambda fnv: 0x0300_0000 | fnv)
    subs = pack_subrecord('VTCK', struct.pack('<I', 0x1234))
    voiced = creatures._own_voice(ghost)(subs)
    assert struct.unpack('<I', dict(subrecords(voiced))[b'VTCK'])[0] == 0x0309_4EED


def test_a_creature_standing_in_on_a_tunneling_race_never_tunnels():
    """A mole rat stand-in (and its template actors) gets DisableTunnelingKeyword, a protectron the helper robot
    keyword; a speaker or a brahmin neither.
    See: docs/fork/fo4_creature_audit.md#race-abilities
    """
    from fo4_import.spike import creatures as CR
    creatures = CR.Creatures.__new__(CR.Creatures)
    creatures.records = {
        0xE01: {'FormID': '00000E01', 'EditorID': 'Rat', 'Model.MODL': 'rat'},
        0xE02: {'FormID': '00000E02', 'EditorID': 'Pup', 'ACBS.TemplateFlags': '1', 'TPLT.Template': '00000E01'},
        0xE03: {'FormID': '00000E03', 'EditorID': 'Cow', 'Model.MODL': 'cow'},
        0xE04: {'FormID': '00000E04', 'EditorID': 'Box', 'Model.MODL': 'box'},
        0xE05: {'FormID': '00000E05', 'EditorID': 'Bot', 'Model.MODL': 'bot'}}
    entries = {'rat': ('stats', 'EncMolerat01Template'), 'cow': ('stats', 'EncBrahminTemplate'),
               'box': ('speaker', 'EncMolerat01Template'), 'bot': ('stats', 'EncProtectron01Template')}
    creatures._entry = lambda rec: (SimpleNamespace(mode=entries[rec['Model.MODL']][0],
                                                    edid=entries[rec['Model.MODL']][1]), rec['Model.MODL'])
    races = {'encmolerat01template': 0x1D810, 'encbrahmintemplate': 0x1BF08, 'encprotectron01template': 0xDFB33}
    creatures.npcs = {k: SimpleNamespace(body=pack_subrecord('RNAM', struct.pack('<I', v))) for k, v in races.items()}
    creatures.builder = SimpleNamespace(type_keywords=SimpleNamespace(of=lambda fnv: [7]),
                                        scripts=SimpleNamespace(helper_index=2))
    ids = {}
    for fid, rec in creatures.records.items():
        kwda = dict(subrecords(creatures._keywords(rec)(pack_subrecord('KWDA', b''))))[b'KWDA']
        ids[fid] = struct.unpack(f'<{len(kwda) // 4}I', kwda)
    robot = 2 << 24 | FALLOUT4_HELPER_CREATURE_KEYWORD
    assert ids == {0xE01: (7, CR.DISABLE_TUNNELING), 0xE02: (7, CR.DISABLE_TUNNELING), 0xE03: (7,), 0xE04: (7,),
                   0xE05: (7, robot)}
