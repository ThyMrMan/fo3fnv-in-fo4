"""Rebuild built XDI menus in our dialogue menu's model: a scratch plugin with one answer topic per option, and the
links file F3NV.dll reads.

    py -3.14 -m tools.dialog.menu_rebuild --plugins GAME.esm [MOD.esm ...] --out MOD_DIR

The menus are every Player Dialogue action of every scene in the plugins: a
talk opens through the shared GREETING scene, whose lines start scenes no
menu reaches. Lines are merged in load order (an override in place, a new
line appended) and paired as XDI pairs them (xdi_menus.pair_lines). Each option
gets an answer topic under its scene's quest (an unchanged copy of the quest
record carries it) with a copy of each paired answer: its own conditions,
flags, scripts and next step, its responses and voice shared (DNAM). FormIDs
keep the last plugin's numbering, so each plugin's masters must start with
the earlier plugins' own.

See: docs/fork/fo4_dialogue_menu_plan.md#vulpes
"""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record, pack_quest, pack_topic
from fo4_import.dialogue_menu.test_mod import LINKS, write_links
from fo4_import.spike import records as R
from tes5_import.base.writer import pack_subrecord
from tools.validate.preflight.plugin_index import first, load_plugin, u32
from tools.validate.preflight.xdi_menus import PLAYER_TOPICS, pair_lines

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


def merged(indexes: list) -> dict:
    """{topic: [INFOs]} over the load order: an override in its master's place, a new INFO appended."""
    by_topic = defaultdict(dict)
    for index in indexes:
        for info in index.by_type['INFO']:
            by_topic[info.parent_dial][info.form_id] = info
    return defaultdict(list, {topic: list(infos.values()) for topic, infos in by_topic.items()})


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


def scene_menus(scene) -> list:
    """[([player topics], NPC topic)] of `scene`'s Player Dialogue actions, in record order."""
    out = []
    for sub in scene.subrecords:
        if sub.type == 'PTOP':
            out.append(([u32(sub.data)], 0))
        elif sub.type in PLAYER_TOPICS[1:] and out:
            out[-1][0].append(u32(sub.data))
        elif sub.type == 'NPOT' and out:
            out[-1] = (out[-1][0], u32(sub.data))
    return out


def scenes(indexes: list) -> list:
    """Every scene of the load order once, its winning record, in load order."""
    fids = dict.fromkeys(s.form_id for i in indexes for s in i.by_type['SCEN'])
    return [winner(indexes, fid) for fid in fids]


def rebuild(plugins: list, name: str) -> tuple:
    """(FO4PluginWriter of the scratch plugin `name`, links rows, counts): every menu of [(name, PluginIndex)] in
    load order. An option in two menus keeps its first."""
    names, indexes = numbered(plugins), [index for _, index in plugins]
    own, lines = len(names) << 24, merged(indexes)
    by_quest, rows, linked, counts = defaultdict(list), [], set(), Counter()
    next_id = 0x800
    for scene in scenes(indexes):
        quest = u32(first(scene, 'PNAM'))
        menus = scene_menus(scene)
        counts['scenes with menus'] += bool(menus)
        for topics, npc in menus:
            counts['menus'] += 1
            for option, _, answers in pair_lines([i for t in topics for i in lines[t]], lines[npc]):
                if not answers or option.form_id in linked:
                    counts['shared options' if answers else 'options without answers'] += 1
                    continue
                linked.add(option.form_id)
                dial, next_id = own | next_id, next_id + 1
                infos = [shared_copy(a, own | (next_id + k)) for k, a in enumerate(answers)]
                next_id += len(infos)
                edid = f'F3NVMenu_{option.form_id:08X}'
                by_quest[quest].append(pack_topic(R.pack_dial(dial, edid, quest, R.TOPIC_SCENE, len(infos)), dial, infos))
                rows.append((names[option.form_id >> 24], option.form_id, name, dial))
                counts['answers'] += len(infos)
    w = FO4PluginWriter(masters=names, is_esm=False, description='F3NV dialogue menu test: rebuilt menus')
    for quest, topics in by_quest.items():
        qust = winner(indexes, quest)
        w.add_record('QUST', pack_quest(pack_fo4_record('QUST', quest, qust.flags, body(qust)), quest, (), topics, []))
    w.next_object_id = next_id
    counts.update({'options': len(rows), 'quests': len(by_quest)})
    return w, rows, counts


def main():
    """Rebuild the menu into a mod folder: the plugin and its links file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--plugins', nargs='+', type=Path, required=True, help='built plugins in load order')
    parser.add_argument('--out', type=Path, required=True, help='the mod folder to write')
    parser.add_argument('--name', default='F3NV_MenuHub.esp', help='the scratch plugin')
    args = parser.parse_args()
    plugins = [(path.name, load_plugin(str(path))) for path in args.plugins]
    w, rows, counts = rebuild(plugins, args.name)
    args.out.mkdir(parents=True, exist_ok=True)
    w.write(str(args.out / args.name))
    links = write_links(args.out / LINKS / f'{Path(args.name).stem}.txt', rows)
    print(f'{args.out / args.name}: {dict(counts)}; links {links}')


if __name__ == '__main__':
    main()
