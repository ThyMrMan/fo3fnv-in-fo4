"""FNV ammo subtypes, effects and casings: the export's new fields, the FO4 ammo mods and the casing script's data.

See: docs/fork/fo4_pipeline.md#nv-ammo
"""
import struct
import zlib
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import ammo_casings, ammo_mods, ammo_switch, hotkey_items
from fo4_import.spike.ammo_mods import (ACTOR_VALUES, AMMO, ATTACK_DAMAGE, ENCHANTMENTS, MAX_CONE, MIN_CONE,
                                        NUM_PROJECTILES, PROPERTY, KEYWORDS, AmmoMods, with_point)
from fo4_import.spike.gun_choice import includes, includes_at
from tes4_export.record_types.ammo_falloutnv import emit_ammo_deltas, export_AMMO_EFFECT
from tes4_export.tes4_reader import Record, Subrecord

LIST, PLAIN, HOLLOW, HAND = 0x1537E6, 0x4241, 0x13E43B, 0x140AA8
CASE, HP_DAMAGE, HP_DT, JHP_CONDITION, SLUG = 0x140AA7, 0x157B54, 0x157B56, 0x17BA45, 0x157B59
GUN, OTHER_GUN, KEYWORD_AT = 0x1000, 0x2000, 0x9999


def _export(subs: list, export=None) -> list:
    """Export lines of a record of `subs` [(tag, data)] (an AMMO's deltas unless `export` is given)."""
    rec = Record('AMMO', 0, 0, HOLLOW, [Subrecord(t, d) for t, d in subs])
    if export:
        return export(rec)
    lines = []
    emit_ammo_deltas(lines, rec)
    return lines


def test_ammo_exports_its_casing_names_and_effects():
    """FNV's DAT2 casing and chance, short name, abbreviation and every effect reach the export."""
    lines = _export([('DATA', struct.pack('<fB3xiB', 1.0, 0, 5, 12)),
                     ('DAT2', struct.pack('<IIfIf', 0, 0, 0.033, CASE, 20.0)), ('ONAM', b'10mm HP\0'),
                     ('QNAM', b'HP\0'), ('RCIL', struct.pack('<I', HP_DAMAGE)), ('RCIL', struct.pack('<I', HP_DT))])
    assert {'DAT2.Casing=00140AA7', 'DAT2.CasingChance=20.0', 'ONAM=10mm HP', 'QNAM=HP', 'RCIL[0]=00157B54',
            'RCIL[1]=00157B56', 'DATA.Value=5'} <= set(lines)


def test_fallout3_ammo_has_no_casing_keys():
    """A 12-byte DAT2 (FO3's) exports its weight and no casing."""
    lines = _export([('DAT2', struct.pack('<IIf', 0, 0, 0.5))])
    assert 'DATA.Weight=0.5' in lines and not any(line.startswith('DAT2.Casing') for line in lines)


def test_ammo_effect_exports_type_operation_and_value():
    """An AMEF exports its name and DATA."""
    lines = _export([('EDID', b'AmmoEffectHPDTPenalty\0'), ('FULL', b'Dam. Thresh. Increase\0'),
                     ('DATA', struct.pack('<IIf', 2, 1, 3.0))], export_AMMO_EFFECT)
    assert lines == ['EditorID=AmmoEffectHPDTPenalty', 'FULL=Dam. Thresh. Increase', 'DATA.Type=2',
                     'DATA.Operation=1', 'DATA.Value=3.0']


class _Writer:
    """A plugin writer keeping what is written."""

    def __init__(self):
        """No records yet."""
        self.records, self.keys = [], []

    def derive_formid(self, site: str, key: str) -> int:
        """A FormID from the site and key."""
        self.keys.append((site, key))
        return 0x01000000 | zlib.crc32(f'{site}|{key}'.encode()) & 0xFFFFFF

    def add_record(self, sig: str, data: bytes) -> None:
        """Keep the record."""
        self.records.append((sig, data))


class _Items:
    """Converted items: FNV FormID -> FO4 FormID, and the FNV records."""

    def __init__(self, records: dict):
        """`records` {FNV FormID: (type, export record)}; each AMMO converts."""
        self.records = records

    def item(self, fnv: int) -> 'int | None':
        """The FO4 FormID of FNV `fnv`."""
        return 0x02000000 | fnv if fnv in self.records else None


class _Builder:
    """The parts of a cell builder AmmoMods uses."""

    def __init__(self, items: dict):
        """A builder converting `items`."""
        self.writer, self.items, self.counts, self.fo4 = _Writer(), _Items(items), Counter(), b''


def _effect(fid: int, kind: int, op: int, value: float, name: str) -> tuple:
    """(FormID, AMEF export record)."""
    return fid, {'FormID': f'{fid:08X}', 'FULL': name, 'DATA.Type': str(kind), 'DATA.Operation': str(op),
                 'DATA.Value': str(value)}


def _ammo(fid: int, edid: str, effects: tuple = (), **fields) -> dict:
    """An AMMO export record."""
    return {'FormID': f'{fid:08X}', 'EditorID': edid, 'FULL': edid, **{f'RCIL[{i}]': f'{e:08X}' for i, e in
                                                                         enumerate(effects)}, **fields}


def _mods(monkeypatch) -> AmmoMods:
    """AmmoMods over a 10mm-like list (plain, hollow point, hand load) and a 12ga slug."""
    ammo = {PLAIN: _ammo(PLAIN, 'Ammo10mm'), HOLLOW: _ammo(HOLLOW, 'Ammo10mmHollowPoint', (HP_DAMAGE, HP_DT)),
            HAND: _ammo(HAND, 'Ammo10mmJHPHandLoad', (JHP_CONDITION,)),
            SLUG: _ammo(SLUG, 'Ammo12GaSlug', (), **{'DAT2.ProjPerShot': '1'})}
    items = {a: ('AMMO', r) for a, r in ammo.items()}
    items[GUN] = ('WEAP', {'NAM0': f'{LIST:08X}'})
    items[OTHER_GUN] = ('WEAP', {'NAM0': f'{PLAIN:08X}'})
    mods = AmmoMods.__new__(AmmoMods)
    mods.builder, mods.point, mods.dt, mods.made, mods.loaded, mods.marks = _Builder(items), None, None, {}, {}, {}
    mods.lists = {LIST: {'FormID': f'{LIST:08X}', 'EditorID': 'AmmoList10mm', 'LNAM[0]': f'{PLAIN:08X}',
                         'LNAM[1]': f'{HOLLOW:08X}', 'LNAM[2]': f'{HAND:08X}'}}
    mods.ammo = ammo
    mods.effects = dict([_effect(HP_DAMAGE, 0, 1, 1.75, 'Damage Bonus'), _effect(HP_DT, 2, 1, 3.0, 'DT Increase'),
                         _effect(JHP_CONDITION, 4, 1, 1.5, 'COND Decay Increase')])
    monkeypatch.setattr(ammo_mods, '_vanilla', lambda fo4: {
        b'AVIF': [(b'EDID', b'ArmorPenetration\0'), (b'FULL', b'\1\0\0\0'), (b'AVFL', struct.pack('<I', 0x400))],
        b'MGEF': [(b'EDID', b'x\0'), (b'DATA', bytes(140))], b'ENCH': [(b'EDID', b'x\0'), (b'EFID', bytes(4))]})
    return mods


def _props(data: bytes) -> dict:
    """{property: (value type, function, value 1, value 2)} of an OMOD DATA."""
    count = struct.unpack_from('<I', data, 4)[0]
    start = len(data) - PROPERTY.size * count
    out = {}
    for i in range(count):
        vtype, func, which, v1, v2, _ = PROPERTY.unpack_from(data, start + PROPERTY.size * i)
        out.setdefault(which, []).append((vtype, func, v1, v2))
    return out


def _float(raw: bytes) -> float:
    """A property value as a float."""
    return struct.unpack('<f', raw)[0]


def _int(raw: bytes) -> int:
    """A property value as an unsigned int."""
    return struct.unpack('<I', raw)[0]


def _subs(record: bytes) -> dict:
    """{subrecord: data} of a packed FO4 record."""
    out, pos = {}, 24
    while pos < len(record):
        size = struct.unpack_from('<H', record, pos + 4)[0]
        out[record[pos:pos + 4]] = record[pos + 6:pos + 6 + size]
        pos += 6 + size
    return out


def _gun() -> list:
    """A converted gun's subrecords: keywords, attach points, one default combination of one part."""
    obts = struct.pack('<II4xhB', 1, 0, -1, 1) + b'\0' + bytes(2) + struct.pack('<IBBB', 0x5555, 0, 0, 1)
    return [(b'EDID', b'FNV_Weap10mmPistol\0'), (b'KSIZ', struct.pack('<I', 1)), (b'KWDA', struct.pack('<I', 7)),
            (b'APPR', struct.pack('<I', 8)), (b'OBTE', struct.pack('<I', 1)), (b'OBTF', b''), (b'FULL', b'\0'),
            (b'OBTS', obts), (b'STOP', b'')]


def test_a_gun_of_a_list_takes_every_ammo_as_a_mod(monkeypatch):
    """The list's keyword and our attach point join the gun; its default combination adds its first ammo's mod;
    each ammo is an OMOD setting the gun's ammo and adding its round's keyword, with its free recipe."""
    mods = _mods(monkeypatch)
    subs = dict(mods.wire(GUN, _gun()))
    keyword, made = mods.made[LIST]
    assert [a for a, _ in made] == [PLAIN, HOLLOW, HAND]
    assert struct.unpack('<2I', subs[b'KWDA']) == (7, keyword) and subs[b'KSIZ'] == struct.pack('<I', 2)
    assert struct.unpack('<2I', subs[b'APPR']) == (8, mods.point)
    assert includes(subs[b'OBTS']) == [0x5555, made[0][1]] and len(subs[b'OBTS']) == includes_at(subs[b'OBTS']) + 14
    written = Counter(sig for sig, _ in mods.builder.writer.records)
    assert written['OMOD'] == 3 and written['COBJ'] == 3 and written['KYWD'] == 2 + 3
    recipe = _subs(next(d for s, d in mods.builder.writer.records if s == 'COBJ'))
    assert set(recipe) == {b'EDID', b'CNAM', b'INTV'}
    assert ('FNV ammo mod', f'{LIST:08X} {HOLLOW:08X}') in mods.builder.writer.keys


def test_ammo_effects_become_properties(monkeypatch):
    """Damage x1.75 is AttackDamage MUL+ADD 0.75, DT x3 the multiplier actor value 2 with the DT enchantment; the
    ammo is SET; a condition effect is counted, not written."""
    mods = _mods(monkeypatch)
    mods.wire(GUN, _gun())
    omods = {_subs(d)[b'FULL'].rstrip(b'\0'): _subs(d) for s, d in mods.builder.writer.records if s == 'OMOD'}
    hollow = _props(omods[b'Ammo10mmHollowPoint'][b'DATA'])
    assert _float(hollow[ATTACK_DAMAGE][0][2]) == 0.75
    assert _int(hollow[ACTOR_VALUES][0][2]) == mods.dt[ammo_mods.DT_MULT]
    assert _float(hollow[ACTOR_VALUES][0][3]) == 2.0
    assert _int(hollow[ENCHANTMENTS][0][2]) == mods.dt[ammo_mods.DT_ENCH]
    assert [(t, f, _int(a), _int(b)) for t, f, a, b in hollow[AMMO]] == [(4, 0, 0x02000000 | HOLLOW, ammo_mods.FORM_VALUE2)]
    assert omods[b'Ammo10mmHollowPoint'][b'DESC'] == b'Damage Bonus x1.75, DT Increase x3\0'
    assert set(_props(omods[b'Ammo10mmJHPHandLoad'][b'DATA'])) == {AMMO, KEYWORDS}
    assert [_int(a) for _, _, a, _ in hollow[KEYWORDS]] == [mods.mark(HOLLOW)]
    assert mods.mark(HOLLOW) != mods.mark(HAND)
    assert mods.builder.counts['ammo effect left out (condition)'] == 1


def test_the_dt_perk_reads_both_actor_values(monkeypatch):
    """One hidden perk: Mod Target Damage Resistance, Add AV Mult of the reduction (x -1) and Multiply 1 + AV
    Mult of the multiplier; the perk effect applies it and the enchantment holds the effect."""
    mods = _mods(monkeypatch)
    ids = mods._dt()
    records = {_subs(d)[b'EDID'].rstrip(b'\0'): (s, _subs(d)) for s, d in mods.builder.writer.records}
    perk = mods.builder.writer.records[[s for s, _ in mods.builder.writer.records].index('PERK')][1]
    assert bytes([37, 5, 3]) in perk and bytes([37, 14, 3]) in perk
    assert struct.pack('<If', ids[ammo_mods.DT_OFF], -1.0) in perk
    assert struct.pack('<If', ids[ammo_mods.DT_MULT], 1.0) in perk
    effect = records[b'FNV_AmmoDTPerkEffect'][1][b'DATA']
    assert struct.unpack_from('<I', effect, ammo_mods.PERK_TO_APPLY)[0] == ids[ammo_mods.DT_PERK]
    assert records[b'FNV_enchAmmoDT'][1][b'EFID'] == struct.pack('<I', ids[ammo_mods.DT_EFFECT])
    assert records[b'FNV_AmmoDTReduction'][1][b'FULL'] == b'Ammo DT Reduction\0'


def test_a_single_ammo_gun_is_left_alone(monkeypatch):
    """A gun loading one AMMO (no list) gets no mods; its ammo is noted for casings."""
    mods = _mods(monkeypatch)
    assert mods.wire(OTHER_GUN, _gun()) == _gun()
    assert mods.loaded == {PLAIN: {OTHER_GUN: [PLAIN]}} and not mods.builder.writer.records


def test_projectile_count_and_spread(monkeypatch):
    """Projectiles per shot is NumProjectiles SET; spread x0.35 scales both cones by -0.65."""
    mods = _mods(monkeypatch)
    mods.effects.update([_effect(0x77, 3, 1, 0.35, 'Spread Reduction')])
    props, notes = mods._effects(dict(mods.ammo[SLUG], **{'RCIL[0]': '00000077'}))
    found = _props(ammo_mods.omod_data(1, props))
    assert [(t, f, _int(a)) for t, f, a, _ in found[NUM_PROJECTILES]] == [(0, 0, 1)] and notes == ['Spread Reduction x0.35']
    for cone in (MIN_CONE, MAX_CONE):
        assert abs(_float(found[cone][0][2]) + 0.65) < 1e-6


def test_a_gun_without_attach_points_gets_them_before_its_template():
    """APPR is inserted before OBTE when the gun has none."""
    subs = [(t, d) for t, d in _gun() if t != b'APPR']
    tags = [t for t, _ in with_point(subs, 0x42)]
    assert tags.index(b'APPR') == tags.index(b'OBTE') - 1


def test_casing_perks_and_groups():
    """Hand Loader's entry point 57 x2 on Guns (41) is read; a group keeps its cased ammo and its first gun's skill."""
    perk = {'FormID': '00031DAA', 'Effect[0].Type': 'EntryPoint', 'Effect[0].EntryPoint': '57',
            'Effect[0].Function': '3', 'Effect[0].Value': '00000040',
            'Effect[0].Tab[0].Condition[0].Raw': '000000000000803f6d00000029000000000000000000000000000000'}
    assert ammo_casings.chance_perks([perk]) == {41: (0x31DAA, 2.0)}
    ammo = {PLAIN: {'DAT2.Casing': f'{CASE:08X}', 'DAT2.CasingChance': '20.0'},
            HOLLOW: {'DAT2.Casing': '00000000', 'DAT2.CasingChance': '0.0'}, HAND: {'DAT2.CasingChance': '10.0'}}
    grouped = ammo_casings.groups({PLAIN: {OTHER_GUN: [PLAIN], GUN: [PLAIN, HOLLOW, HAND]}}, ammo,
                                  {GUN: 41, OTHER_GUN: 34})
    assert grouped == [(PLAIN, [(PLAIN, CASE, 20.0)], 41)]


def test_casing_script_arrays_list_each_ammo_once():
    """Two groups sharing an ammo index one entry; Starts closes on the member count; a group's perk converts."""
    builder = _Builder({PLAIN: ('AMMO', {}), HOLLOW: ('AMMO', {}), CASE: ('MISC', {})})
    builder.perks = type('Perks', (), {})()
    builder.perks.first = {0x31DAA: 0x05000001}
    entries, values = ammo_casings.script_arrays(builder, [(PLAIN, [(PLAIN, CASE, 20.0), (HOLLOW, CASE, 25.0)], 41),
                                                           (HOLLOW, [(HOLLOW, CASE, 25.0)], 34)],
                                                 {41: (0x31DAA, 2.0)})
    assert [a for a, _, _ in entries] == [0x02000000 | PLAIN, 0x02000000 | HOLLOW]
    assert values['Members'] == ('ints', [0, 1, 1]) and values['Starts'] == ('ints', [0, 2, 3])
    assert values['Perks'] == ('objects', [0x05000001, 0]) and values['PerkMults'] == ('floats', [2.0, 1.0])
    assert values['Chances'] == ('floats', [20.0, 25.0])


def test_the_ammo_type_hotkey_lists_each_round_with_its_mod_keyword_and_name(monkeypatch):
    """The switch quest holds the list keyword, each round's FO4 ammo, mod, loaded keyword and message, in order; the
    hotkey item runs a self script effect pointing back at the quest."""
    mods = _mods(monkeypatch)
    mods.wire(GUN, _gun())
    builder = mods.builder
    builder.scripts = SimpleNamespace(used=[], effects=SimpleNamespace(effect_data=lambda cast, delivery: bytes(8)))
    monkeypatch.setattr(hotkey_items, 'model', lambda fo4: b'Ammo/x.nif\0')
    keyword, made = mods.made[LIST]
    values = ammo_switch.arrays(builder, mods, ammo_switch.groups(mods.made))
    assert values['Lists'] == ('objects', [keyword]) and values['Starts'] == ('ints', [0, 3])
    assert values['Rounds'][1] == [0x02000000 | a for a in (PLAIN, HOLLOW, HAND)]
    assert values['Mods'][1] == [m for _, m in made]
    assert values['Loaded'][1] == [mods.mark(a) for a in (PLAIN, HOLLOW, HAND)]
    mods = _mods(monkeypatch)
    mods.wire(GUN, _gun())
    builder, before = mods.builder, len(mods.builder.writer.records)
    builder.scripts = SimpleNamespace(used=[], effects=SimpleNamespace(effect_data=lambda cast, delivery: bytes(8)))
    ammo_switch.write(builder, mods)
    written = Counter(sig for sig, _ in builder.writer.records[before:])
    assert written == {'MESG': 3 + 3, 'QUST': 1, 'MGEF': 1, 'ALCH': 1}
    assert builder.scripts.used == [ammo_switch.SCRIPT, ammo_switch.ITEM_SCRIPT]
    item = _subs(next(d for s, d in builder.writer.records if s == 'ALCH'))
    assert item[b'FULL'] == b'Ammo Type\0' and item[b'EFID'] == struct.pack('<I', builder.writer.derive_formid(
        ammo_switch.SITE, 'effect'))
