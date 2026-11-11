"""Rebuild a built XDI menu in our dialogue menu's model: a scratch plugin with one answer topic per option, and the
links file F3NV.dll reads.

    py -3.14 -m tools.dialog.menu_rebuild --plugins GAME.esm [MOD.esm ...] --player TOPIC --npc TOPIC --out MOD_DIR

The menu's lines are merged in load order (an override in place, a new line
appended) and paired as XDI pairs them (xdi_menus.pair_lines). Each option
gets an answer topic under the menu's quest (an unchanged copy of the quest
record carries it) with a copy of each paired answer: its own conditions,
flags, scripts and next step, its responses and voice shared (DNAM). FormIDs
keep the last plugin's numbering, so each plugin's masters must start with
the earlier plugins' own.

See: docs/fork/fo4_dialogue_menu_plan.md#vulpes
"""

import argparse
from pathlib import Path

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest, pack_topic
from fo4_import.dialogue_menu.test_mod import LINKS, write_links
from fo4_import.spike import records as R
from tes5_import.base.writer import pack_subrecord
from tools.validate.preflight.plugin_index import first, load_plugin, u32
from tools.validate.preflight.xdi_menus import pair_lines

#: An INFO's response subrecords, which a copy sharing them (DNAM) leaves out.
RESPONSE_TAGS = frozenset({'TRDA', 'NAM1', 'NAM2', 'NAM3', 'NAM4', 'SNAM', 'LNAM', 'DNAM'})


def numbered(plugins: list) -> list:
    """The plugin names by FormID index of [(name, PluginIndex)] in load order (the last one's masters, then it);
    raises ValueError when a plugin's masters do not start with the earlier plugins' own."""
    names = list(plugins[-1][1].masters) + [plugins[-1][0]]
    for name, index in plugins:
        if list(index.masters) + [name] != names[:len(index.masters) + 1]:
            raise ValueError(f'{name}: its masters are not a prefix of {plugins[-1][0]}\'s')
    return names


def merged(indexes: list, topic: int) -> list:
    """Topic `topic`'s INFOs over the load order: an override in its master's place, a new INFO appended."""
    order, by_fid = [], {}
    for index in indexes:
        for info in index.by_type['INFO']:
            if info.parent_dial == topic:
                order += [] if info.form_id in by_fid else [info.form_id]
                by_fid[info.form_id] = info
    return [by_fid[fid] for fid in order]


def winner(indexes: list, fid: int):
    """Record `fid` as the last plugin that has it leaves it."""
    return next((i.by_fid[fid] for i in reversed(indexes) if fid in i.by_fid), None)


def body(rec, skip: frozenset = frozenset()) -> bytes:
    """`rec`'s subrecords, less the tags in `skip`."""
    return b''.join(pack_subrecord(s.type, s.data) for s in rec.subrecords if s.type not in skip)


def shared_copy(answer, fid: int) -> bytes:
    """INFO `fid`: `answer` sharing its responses (DNAM right after ENAM, as xEdit orders INFO)."""
    subs = b''
    for sub in answer.subrecords:
        if sub.type not in RESPONSE_TAGS:
            subs += pack_subrecord(sub.type, sub.data)
        if sub.type == 'ENAM':
            subs += R.pack_u32('DNAM', answer.form_id)
    return pack_fo4_record('INFO', fid, answer.flags, subs)


def rebuild(plugins: list, player: int, npc: int, name: str) -> tuple:
    """(FO4PluginWriter of the scratch plugin `name`, links rows, counts) for the menu of topics `player`, `npc`
    over [(name, PluginIndex)] in load order."""
    names, indexes = numbered(plugins), [index for _, index in plugins]
    own = len(names) << 24
    quest = u32(first(winner(indexes, player), 'QNAM'))
    next_id, topics, rows, copied = 0x800, [], [], 0
    for option, _, answers in pair_lines(merged(indexes, player), merged(indexes, npc)):
        if not answers:
            continue
        dial, next_id = own | next_id, next_id + 1
        infos = [shared_copy(a, own | (next_id + k)) for k, a in enumerate(answers)]
        next_id += len(infos)
        edid = f'F3NVMenu_{option.form_id:08X}'
        topics.append(pack_topic(R.pack_dial(dial, edid, quest, R.TOPIC_SCENE, len(infos)), dial, infos))
        rows.append((names[option.form_id >> 24], option.form_id, name, dial))
        copied += len(infos)
    qust = winner(indexes, quest)
    w = FO4PluginWriter(masters=names, is_esm=False, description='F3NV dialogue menu test: a rebuilt menu')
    w.add_record('QUST', pack_quest(pack_fo4_record('QUST', quest, qust.flags, body(qust)), quest, (), topics, []))
    w.next_object_id = next_id
    return w, rows, {'options': len(rows), 'answers': copied}


def main():
    """Rebuild the menu into a mod folder: the plugin and its links file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--plugins', nargs='+', type=Path, required=True, help='built plugins in load order')
    parser.add_argument('--player', type=lambda s: int(s, 16), required=True, help="the menu's first player topic")
    parser.add_argument('--npc', type=lambda s: int(s, 16), required=True, help="the menu's NPC topic")
    parser.add_argument('--out', type=Path, required=True, help='the mod folder to write')
    parser.add_argument('--name', default='F3NV_MenuHub.esp', help='the scratch plugin')
    args = parser.parse_args()
    plugins = [(path.name, load_plugin(str(path))) for path in args.plugins]
    w, rows, counts = rebuild(plugins, args.player, args.npc, args.name)
    args.out.mkdir(parents=True, exist_ok=True)
    w.write(str(args.out / args.name))
    links = write_links(args.out / LINKS / f'{Path(args.name).stem}.txt', rows)
    print(f'{args.out / args.name}: {counts["options"]} options, {counts["answers"]} answers; links {links}')


if __name__ == '__main__':
    main()
