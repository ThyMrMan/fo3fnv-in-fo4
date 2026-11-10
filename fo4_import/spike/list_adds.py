"""A DLC's additions to its masters' form lists and perks, made at run time instead of overriding them.

Two plugins overriding one record do not stack: the last loaded wins and the
other's additions are gone. So a dependent build overrides no master form list
or perk it only adds to (master_overrides.drop_unchanged collects the
additions). A start-game quest of its own runs F3NV_FormListAdds, which adds
each new form to its list (FormList.AddForm, kept by the save) and gives the
player the plugin's own perks. A perk's added entries go on a hidden perk of
the plugin's own, each entry also requiring the player to have the master perk
(HasPerk, first in its perk-owner tab), so the entries apply exactly when the
master perk's did.

See: docs/fork/fo4_plugin_layout.md#dlc-lists
"""

import struct

from fo4_import.base.source import plugin_stem
from fo4_import.base.support_records import pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: derive_formid site (keys: 'quest', 'perk <master perk FormID>'), and the script the quest runs.
SITE, SCRIPT = 'FNV form list adds', 'F3NV_FormListAdds'
#: A perk's DATA: not a trait, level 0, one rank, not playable, hidden.
HIDDEN_PERK = bytes([0, 0, 1, 0, 1])
#: The condition tab of the perk's owner (the player).
OWNER_TAB = 0


def write(builder, adds: dict) -> int:
    """Write the quest making `adds` ({FormID: (signature, EditorID, [forms or perk entries])}) and the plugin's
    perks; how many forms and perk entries it adds (0: no quest)."""
    pairs = [(fid, form) for fid, (sig, _, forms) in sorted(adds.items()) if sig == b'FLST' for form in forms]
    perks = [_perk(builder, fid, edid, entries) for fid, (sig, edid, entries) in sorted(adds.items()) if sig == b'PERK']
    if not pairs and not perks:
        return 0
    rows = {'Lists': ('objects', [fid for fid, _ in pairs]), 'Forms': ('objects', [form for _, form in pairs]),
            'Perks': ('objects', perks)}
    vmad = quest_fragments('', [], scripts=[(SCRIPT, {}, rows)])
    edid = f'FNV_FormListAdds_{plugin_stem(builder.export_dir)}'
    builder.writer.add_record('QUST', pack_script_quest(builder.writer.derive_formid(SITE, 'quest'), edid, vmad))
    return len(pairs) + sum(len(entries) for sig, _, entries in adds.values() if sig == b'PERK')


def _perk(builder, master: int, edid: str, entries: list) -> int:
    """Write the plugin's hidden perk holding master perk `master`'s (EditorID `edid`) added `entries`; its FormID."""
    fid = builder.writer.derive_formid(SITE, f'perk {master:08X}')
    gate = R.pack_ctda(0, 1.0, C.FO4.index('HasPerk'), master)
    body = pack_string_subrecord('EDID', f'{edid}_{plugin_stem(builder.export_dir)}')
    body += pack_subrecord('DATA', HIDDEN_PERK)
    body += b''.join(pack_subrecord(tag.decode(), data) for entry in entries for tag, data in gated(entry, gate))
    builder.writer.add_record('PERK', pack_fo4_record('PERK', fid, 0, body))
    return fid


def gated(entry: tuple, gate: bytes) -> list:
    """Perk entry `entry` ((tag, data) subrecords, PRKE to PRKF) with condition `gate` (a packed CTDA) first in its
    perk-owner tab, that tab added after the entry's DATA when it has none."""
    subs, condition = list(entry), (b'CTDA', gate[6:])
    tab = next((i for i, (tag, data) in enumerate(subs) if tag == b'PRKC' and data[0] == OWNER_TAB), None)
    if tab is not None:
        return subs[:tab + 1] + [condition] + subs[tab + 1:]
    at = next((i + 1 for i, (tag, _) in enumerate(subs) if tag == b'DATA'), 1)
    return subs[:at] + [(b'PRKC', struct.pack('<B', OWNER_TAB)), condition] + subs[at:]
