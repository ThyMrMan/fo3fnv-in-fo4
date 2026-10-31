"""A DLC's rows merged into a game quest's script arrays: the game's rows, then the DLC's new ones.

A DLC build remakes the game's start-game quests (the Ammo Type hotkey, condition, challenges) from what it built:
the DLC's entries plus only the game entries it reached. Overriding the whole record would drop the rest. A script
with a rule (`rules`, {script: rule(game values, DLC values) -> values}) takes the game's values with the DLC's new
rows; any other script must be identical on both sides. Each rule's script names its own row layout.

See: docs/fork/fo4_plugin_layout.md#dlc-build
"""

from fo4_import.base.vmad import Unsupported, quest_fragments, read_quest
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord


def appended(game: dict, dlc: dict, key: str, columns: tuple, remap: 'dict | None' = None) -> dict:
    """`columns` (value props, parallel rows keyed by column `key`) as the game's rows then the DLC's whose key the
    game lacks; `remap` ({column: {DLC value: merged value}}) renumbers index columns of the DLC's rows."""
    have, remap = set(game[key][1]), remap or {}
    out = {c: (game[c][0], list(game[c][1])) for c in columns}
    for i, k in enumerate(dlc[key][1]):
        if k in have:
            continue
        have.add(k)
        for c in columns:
            value = dlc[c][1][i]
            out[c][1].append(remap.get(c, {}).get(value, value))
    return out


def regrouped(game: list, dlc: list) -> tuple:
    """(merged groups, {DLC group index: merged index}) of two lists of groups (hashable), the game's first and
    each DLC group equal to one the game has given that one's index."""
    merged, index = list(game), {}
    for i, group in enumerate(dlc):
        if group not in merged:
            merged.append(group)
        index[i] = merged.index(group)
    return merged, index


def _merged_entry(game: tuple, dlc: tuple, rules: dict) -> tuple:
    """Script entry `game` with `dlc`'s rows by its script's rule; Unsupported when it has none and they differ."""
    name, objects, values = game
    if game == dlc:
        return game
    if name not in rules or dlc[0] != name:
        raise Unsupported(f'no merge rule for {name}')
    return name, objects, {**values, **rules[name](values, dlc[2])}


def merged_vmad(game: bytes, dlc: bytes, rules: dict) -> bytes:
    """The game quest's VMAD with the DLC's rows merged in (module notes); Unsupported when it cannot be."""
    (scripts, aliases), (dlc_scripts, dlc_aliases) = read_quest(game), read_quest(dlc)
    if [s[0] for s in scripts] != [s[0] for s in dlc_scripts] or [a[:2] for a in aliases] != [a[:2] for a in dlc_aliases]:
        raise Unsupported('quest scripts differ')
    merged = [_merged_entry(g, d, rules) for g, d in zip(scripts, dlc_scripts)]
    merged_aliases = [(alias, quest, [_merged_entry(g, d, rules) for g, d in zip(entries, dlc_entries)])
                      for (alias, quest, entries), (_, _, dlc_entries) in zip(aliases, dlc_aliases)]
    return quest_fragments('', [], aliases=merged_aliases, scripts=merged)


def merged_quest(game: bytes, dlc: bytes, rules: dict) -> 'bytes | None':
    """QUST body `game` with DLC body `dlc`'s script rows merged into its VMAD; None when it cannot be (another
    subrecord differs, or a script lacks a rule)."""
    theirs, mine = list(subrecords(game)), list(subrecords(dlc))
    if [s for s in theirs if s[0] != b'VMAD'] != [s for s in mine if s[0] != b'VMAD']:
        return None
    vmads = [d for t, d in theirs if t == b'VMAD'], [d for t, d in mine if t == b'VMAD']
    if len(vmads[0]) != 1 or len(vmads[1]) != 1:
        return None
    try:
        if quest_fragments('', [], aliases=read_quest(vmads[0][0])[1], scripts=read_quest(vmads[0][0])[0]) != vmads[0][0]:
            return None
        vmad = merged_vmad(vmads[0][0], vmads[1][0], rules)
    except Unsupported:
        return None
    return b''.join(pack_subrecord(t.decode(), vmad if t == b'VMAD' else d) for t, d in theirs)
