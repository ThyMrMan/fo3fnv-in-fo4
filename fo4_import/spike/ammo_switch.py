"""FNV's Ammo Type hotkey on Fallout 4: an aid item for the Favorites wheel that loads the equipped gun's next round.

FNV's Ammo Type hotkey reloads with the next round of the gun's list the
player carries. Fallout 4 has no such key, so this follows Loads of Ammo v2's
method in vanilla Papyrus: a start-game quest (F3NV_AmmoSwitch) holds every
ammo list the build made mods for (ammo_mods), and its Cycle() attaches the
next carried round's mod to the equipped gun. A gun's list is found by the
list keyword on its weapon record, its loaded round by the keyword that round's mod
adds (AmmoMods.mark). The hotkey is an aid item whose script effect
(F3NV_AmmoSwitchItem) gives itself back and calls Cycle(); the quest hands
the player one. Each round shows its FNV name as a notification.

See: docs/fork/fo4_pipeline.md#ammo-switch
"""

from fo4_import.base.support_records import pack_mesg, pack_script_quest
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.spike.hotkey_items import hotkey_effect, hotkey_item

#: derive_formid site (keys: 'quest', 'item', 'effect', a message's name, 'note <FNV ammo FormID>').
SITE = 'FNV ammo switch'
SCRIPT, ITEM_SCRIPT = 'F3NV_AmmoSwitch', 'F3NV_AmmoSwitchItem'
#: The F3NV plugin's natives for the Pip-Boy's ammo list (tes_runtime/fo4_condition/ammo.cpp).
NATIVES = 'F3NV_PipboyAmmo'
#: F3NV_AmmoSwitch's per-round arrays, one row per round, Starts[g] to Starts[g + 1] list g's.
ROUND_COLUMNS = ('Rounds', 'Mods', 'Loaded', 'Notes')
#: The hotkey item's name (FNV's own for the hotkey).
ITEM_NAME = 'Ammo Type'
#: The quest's messages: property, text.
MESSAGES = (('NoOtherAmmo', 'No other ammo for this weapon.'),
            ('SingleAmmo', 'This weapon takes one kind of ammo.'),
            ('TwoCopies', 'You carry two of this weapon; drop one to change its ammo.'))


def groups(made: dict) -> list:
    """[(list keyword, [(FNV ammo, its mod)])] of AmmoMods.made, lists with mods only."""
    return [(keyword, mods) for _, (keyword, mods) in sorted(made.items()) if keyword and len(mods) > 1]


def arrays(builder, mods, grouped: list) -> dict:
    """F3NV_AmmoSwitch's array properties {name: (kind, value)} for `grouped` (groups()); each round's message
    written once."""
    out = {'Lists': [], 'Starts': [], 'Rounds': [], 'Mods': [], 'Loaded': [], 'Notes': []}
    notes = {}
    for keyword, members in grouped:
        out['Lists'].append(keyword)
        out['Starts'].append(len(out['Rounds']))
        for ammo, mod in members:
            if ammo not in notes:
                notes[ammo] = builder.writer.derive_formid(SITE, f'note {ammo:08X}')
                rec = mods.ammo[ammo]
                builder.writer.add_record('MESG', pack_mesg(notes[ammo], f'FNV_AmmoNote_{rec["EditorID"]}', '',
                                                            rec.get('FULL', rec['EditorID']), 0, []))
            out['Rounds'].append(builder.items.item(ammo))
            out['Mods'].append(mod)
            out['Loaded'].append(mods.mark(ammo))
            out['Notes'].append(notes[ammo])
    out['Starts'].append(len(out['Rounds']))
    return {name: ('ints' if name == 'Starts' else 'objects', value) for name, value in out.items()}


def _grouped_rows(values: dict) -> dict:
    """{list keyword: [(round, mod, loaded keyword, note)]} of F3NV_AmmoSwitch's array properties `values`."""
    starts, columns = values['Starts'][1], [values[c][1] for c in ROUND_COLUMNS]
    return {keyword: list(zip(*(c[starts[g]:starts[g + 1]] for c in columns)))
            for g, keyword in enumerate(values['Lists'][1])}


def merge(game: dict, dlc: dict) -> dict:
    """F3NV_AmmoSwitch's arrays as the game's lists, each with the DLC's new rounds after its own, then the DLC's
    new lists (quest_merge)."""
    merged = _grouped_rows(game)
    for keyword, rows in _grouped_rows(dlc).items():
        have = {row[0] for row in merged.setdefault(keyword, [])}
        merged[keyword] += [row for row in rows if row[0] not in have]
    out = {'Lists': [], 'Starts': [], **{c: [] for c in ROUND_COLUMNS}}
    for keyword, rows in merged.items():
        out['Lists'].append(keyword)
        out['Starts'].append(len(out['Rounds']))
        for row in rows:
            for column, value in zip(ROUND_COLUMNS, row):
                out[column].append(value)
    out['Starts'].append(len(out['Rounds']))
    return {name: (game[name][0], value) for name, value in out.items()}


def write(builder, mods) -> None:
    """The Ammo Type hotkey for AmmoMods `mods`: quest, messages, script effect and aid item; nothing without lists."""
    grouped = groups(mods.made)
    if not grouped:
        return
    quest, item, effect = (builder.writer.derive_formid(SITE, key) for key in ('quest', 'item', 'effect'))
    messages = {}
    for name, text in MESSAGES:
        messages[name] = builder.writer.derive_formid(SITE, name)
        builder.writer.add_record('MESG', pack_mesg(messages[name], f'FNV_AmmoSwitch{name}', '', text, 0, []))
    props = {**messages, 'Hotkey': item}
    vmad = quest_fragments('', [], scripts=[(SCRIPT, props, arrays(builder, mods, grouped))])
    builder.writer.add_record('QUST', pack_script_quest(quest, 'FNV_AmmoSwitch', vmad))
    hotkey_effect(builder, effect, 'FNV_AmmoSwitchEffect', ITEM_NAME,
                  object_scripts([(ITEM_SCRIPT, {'Switch': quest, 'Hotkey': item}, {})]))
    hotkey_item(builder, item, 'FNV_AmmoSwitchHotkey', ITEM_NAME, effect)
    builder.scripts.used += [SCRIPT, ITEM_SCRIPT, NATIVES]
    builder.counts['ammo switch lists'] = len(grouped)

