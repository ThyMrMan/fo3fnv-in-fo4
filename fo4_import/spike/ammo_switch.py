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


from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_mesg, pack_script_quest
from fo4_import.base.vmad import object_scripts, quest_fragments
from fo4_import.spike import records as R
from fo4_import.spike.hotkey_items import hotkey_effect, hotkey_item

#: derive_formid site (keys: 'quest', 'sources', 'plugin rounds', 'item', 'effect', a message's name, 'note <ammo>').
SITE = 'FNV ammo switch'
SCRIPT, ITEM_SCRIPT = 'F3NV_AmmoSwitch', 'F3NV_AmmoSwitchItem'
#: Each plugin's ammo lists (the game's on its ammo switch quest, a DLC's on a quest of its own); see write.
SOURCE_SCRIPT = 'F3NV_AmmoSwitchSource'
#: The F3NV plugin's natives for the Pip-Boy's ammo list (tes_runtime/fo4_condition/ammo.cpp).
NATIVES = 'F3NV_PipboyAmmo'
#: The hotkey item's name (FNV's own for the hotkey).
ITEM_NAME = 'Ammo Type'
#: The quest's messages: property, text.
MESSAGES = (('NoOtherAmmo', 'No other ammo for this weapon.'),
            ('SingleAmmo', 'This weapon takes one kind of ammo.'),
            ('TwoCopies', 'You carry two of this weapon; drop one to change its ammo.'))


def groups(made: dict) -> list:
    """[(list keyword, [(FNV ammo, its mod)])] of AmmoMods.made, lists with mods only."""
    return [(keyword, mods) for _, (keyword, mods) in sorted(made.items()) if keyword and len(mods) > 1]


def arrays(builder, mods, grouped: list, kept=None) -> dict:
    """F3NV_AmmoSwitchSource's array properties {name: (kind, value)} for `grouped` (groups()): a list whose keyword
    `kept` admits whole, another only with the rounds whose FO4 FormID it admits (all by default: no `kept`); each
    round's message written once."""
    out = {'Lists': [], 'Starts': [], 'Rounds': [], 'Mods': [], 'Loaded': [], 'Notes': []}
    notes = {}
    for keyword, members in grouped:
        members = [(ammo, mod) for ammo, mod in members
                   if kept is None or kept(keyword) or kept(builder.items.item(ammo))]
        if not members:
            continue
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


def write(builder, mods) -> None:
    """The Ammo Type hotkey for AmmoMods `mods`: quest, registry, messages, script effect and aid item; a plugin
    whose master holds the quest writes only its own rounds' quest (F3NV_AmmoSwitchSource); nothing without lists.
    See: docs/fork/fo4_pipeline.md#ammo-switch-sources
    """
    grouped = groups(mods.made)
    if not grouped:
        return
    writer = builder.writer
    quest, sources = (writer.derive_formid(SITE, key) for key in ('quest', 'sources'))
    builder.scripts.used += [SOURCE_SCRIPT, SCRIPT, NATIVES]
    builder.counts['ammo switch lists'] = len(grouped)
    links = {'Sources': sources, 'Switch': quest}
    if quest >> 24 != writer.own_index:
        rows = arrays(builder, mods, grouped, lambda form: form is not None and form >> 24 == writer.own_index)
        fid = writer.derive_formid(SITE, 'plugin rounds')
        vmad = quest_fragments('', [], scripts=[(SOURCE_SCRIPT, links, rows)])
        writer.add_record('QUST', pack_script_quest(fid, f'FNV_AmmoSwitch_{plugin_stem(builder.export_dir)}', vmad))
        return
    item, effect = (writer.derive_formid(SITE, key) for key in ('item', 'effect'))
    writer.add_record('FLST', R.pack_flst(sources, 'FNV_AmmoSwitchSources', []))
    messages = {}
    for name, text in MESSAGES:
        messages[name] = writer.derive_formid(SITE, name)
        writer.add_record('MESG', pack_mesg(messages[name], f'FNV_AmmoSwitch{name}', '', text, 0, []))
    hub = (SCRIPT, {**messages, 'Hotkey': item, 'Sources': sources}, {})
    vmad = quest_fragments('', [], scripts=[hub, (SOURCE_SCRIPT, links, arrays(builder, mods, grouped))])
    writer.add_record('QUST', pack_script_quest(quest, 'FNV_AmmoSwitch', vmad))
    hotkey_effect(builder, effect, 'FNV_AmmoSwitchEffect', ITEM_NAME,
                  object_scripts([(ITEM_SCRIPT, {'Switch': quest, 'Hotkey': item}, {})]))
    hotkey_item(builder, item, 'FNV_AmmoSwitchHotkey', ITEM_NAME, effect)
    builder.scripts.used += [ITEM_SCRIPT]

