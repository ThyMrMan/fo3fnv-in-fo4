"""FNV's casings on Fallout 4: the item a round leaves when fired (AMMO DAT2), at FNV's own chance.

FNV adds the casing (Case10mm, Hull12Ga, a drained cell) to the player's
inventory at its percent chance each time a round is fired; Hand Loader and
Vigilant Recycler multiply that chance for their weapon skill (entry point
57, Modify Chance for Ammo Item). Fallout 4 has no such field, so a
start-game quest's player alias runs F3NV_AmmoCasings: on each weaponFire
animation event it finds the group of the equipped gun's ammo (its base
ammo, its FNV list's first) and, once firing pauses, takes the drop in each
of the group's ammo counts as rounds fired and rolls each round's casing.
Vanilla Papyrus only: no F4SE instance data. Groups are the build's guns'
ammo lists, keyed by their first ammo.

See: docs/fork/fo4_pipeline.md#nv-ammo
"""

import struct

from fo4_import.base.install import source_esm
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.base.vmad import quest_fragments
from tes5_import.base.tes5_reader import first_sub, walk

SITE, SCRIPT, PLAYER = 'FNV ammo casings', 'F3NV_AmmoCasings', 0x14
#: FNV WEAP DNAM offset of its skill (xEdit's FNV WEAP DNAM); FNV entry point Modify Chance for Ammo Item, Multiply.
SKILL_AT, CHANCE_ENTRY, MULTIPLY = 104, 57, 3
#: FNV condition function IsWeaponSkillType, and where a raw CTDA holds its function and parameter.
IS_WEAPON_SKILL, CTDA_FUNCTION, CTDA_PARAM = 109, 8, 12


def fnv_skills() -> dict:
    """{FNV WEAP FormID: its skill actor value}, read from the source plugin (the export drops it)."""
    out = {}
    for rec, _ in walk(source_esm(), b'WEAP'):
        dnam = first_sub(rec.body, b'DNAM')
        if dnam and len(dnam) >= SKILL_AT + 4:
            out[rec.form_id] = struct.unpack_from('<i', dnam, SKILL_AT)[0]
    return out


def chance_perks(perks: list) -> dict:
    """{FNV skill actor value: (FNV PERK FormID, multiplier)} of export `perks` multiplying the casing chance for
    one weapon skill; the first perk per skill."""
    out = {}
    for rec in perks:
        i = 0
        while f'Effect[{i}].Type' in rec:
            key = f'Effect[{i}]'
            raw = bytes.fromhex(rec.get(f'{key}.Tab[0].Condition[0].Raw', ''))
            if (int(rec.get(f'{key}.EntryPoint', -1)) == CHANCE_ENTRY and int(rec.get(f'{key}.Function', 0)) == MULTIPLY
                    and len(raw) >= CTDA_PARAM + 4 and struct.unpack_from('<H', raw, CTDA_FUNCTION)[0] == IS_WEAPON_SKILL):
                value = struct.unpack('<f', bytes.fromhex(rec[f'{key}.Value']))[0]
                out.setdefault(struct.unpack_from('<I', raw, CTDA_PARAM)[0], (int(rec['FormID'], 16), value))
            i += 1
    return out


def groups(loaded: dict, ammo: dict, skills: dict) -> list:
    """[(first FNV ammo, [(FNV ammo, FNV casing, chance)], FNV skill)] of AmmoMods.loaded {first ammo: {FNV gun: its
    ammo}}: each group's ammo that leave a casing, and its first gun's skill; groups with none left out."""
    out = []
    for first in sorted(loaded):
        guns = loaded[first]
        members = sorted({a for listed in guns.values() for a in listed})
        cased = [(a, int(ammo[a]['DAT2.Casing'], 16), float(ammo[a].get('DAT2.CasingChance', 0.0))) for a in members
                 if a in ammo and int(ammo[a].get('DAT2.Casing', '0'), 16) and float(ammo[a].get('DAT2.CasingChance', 0))]
        if cased:
            out.append((first, cased, skills.get(min(guns), -1)))
    return out


def script_arrays(builder, grouped: list, perks: dict) -> tuple:
    """([(FO4 ammo, FO4 casing, chance)] each ammo once, {property: (kind, value)}) of F3NV_AmmoCasings for
    `grouped` (groups()), `perks` (chance_perks()); a group whose first ammo or every casing does not convert goes."""
    items, entries, index = builder.items, [], {}
    out = {'Defaults': [], 'Starts': [], 'Members': [], 'Perks': [], 'PerkMults': []}
    for first, cased, skill in grouped:
        made = [m for m in ((items.item(a), items.item(c), chance) for a, c, chance in cased) if None not in m[:2]]
        if items.item(first) is None or not made:
            continue
        out['Defaults'].append(items.item(first))
        out['Starts'].append(len(out['Members']))
        for entry in made:
            if entry[0] not in index:
                index[entry[0]] = len(entries)
                entries.append(entry)
            out['Members'].append(index[entry[0]])
        perk, mult = perks.get(skill, (None, 1.0))
        out['Perks'].append(builder.perks.first.get(perk, 0))
        out['PerkMults'].append(mult)
    out['Starts'].append(len(out['Members']))
    kinds = {'Defaults': 'objects', 'Starts': 'ints', 'Members': 'ints', 'Perks': 'objects', 'PerkMults': 'floats'}
    values = {name: (kinds[name], value) for name, value in out.items()}
    values.update(Casings=('objects', [c for _, c, _ in entries]), Chances=('floats', [ch for _, _, ch in entries]))
    return entries, values


def write(builder, loaded: dict) -> None:
    """The start-game quest whose player alias gives FNV's casings (F3NV_AmmoCasings), for AmmoMods.loaded `loaded`;
    nothing when no group leaves casings."""
    ammo = {int(r['FormID'], 16): r for r in export_records(builder.export_dir, 'AMMO')}
    perks = chance_perks(export_records(builder.export_dir, 'PERK'))
    entries, values = script_arrays(builder, groups(loaded, ammo, fnv_skills()), perks)
    if not entries:
        return
    quest, listed = (builder.writer.derive_formid(SITE, key) for key in ('quest', 'ammo'))
    builder.writer.add_record('FLST', R.pack_flst(listed, 'FNV_CasingAmmo', [a for a, _, _ in entries]))
    vmad = quest_fragments('', [], aliases=[(0, quest, [(SCRIPT, {'AmmoList': listed}, values)])])
    builder.writer.add_record('QUST', R.pack_qust(quest, 'FNV_AmmoCasings', '', 0, [], 'Player', PLAYER, vmad))
    builder.scripts.used.append(SCRIPT)
    builder.counts['casing ammo'] = len(entries)
    builder.counts['QUST (ammo casings)'] += 1
