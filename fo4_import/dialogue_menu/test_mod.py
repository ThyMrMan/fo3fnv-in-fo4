"""A test mod for our dialogue menu: F3NV.dll, the menu movie, and a scratch plugin with its option links.

    py -3.14 -m fo4_import.dialogue_menu.test_mod [--out DIR] [--dll F3NV.dll]

The scratch plugin, F3NV_MenuTest.esp (Fallout4.esm its only master), has
one menu of DEMO options; each option's answer topic tests one rule. With the
global F3NVMenuTest at 1 (2: also the alternate lines), any NPC the player
talks to greets with the menu. A links file names each option's answer
topic for F3NV.dll (dialogue.cpp).

See: docs/fork/fo4_dialogue_menu_plan.md#test-build
"""

import argparse
import shutil
from pathlib import Path

from fo4_import.base.ffdec import REPO
from fo4_import.base.support_records import pack_global
from fo4_import.base.writer import FO4PluginWriter, pack_quest, pack_topic
from fo4_import.dialogue_menu import movie
from fo4_import.dialogue_menu import LINKS, write_links
from fo4_import.spike import records as R

DEMO = 'F3NV_MenuTest.esp'
MASTERS = ['Fallout4.esm']
DLL = REPO / 'tes_runtime' / 'dist' / 'F3NV.dll'
#: FO4 condition functions (xEdit wbDefinitionsFO4.pas): GetGlobalValue, GetPlayerActivated.
GLOBAL_VALUE, PLAYER_ACTIVATED = 74, 483
#: CTDA compare: equal, greater or equal.
EQUAL, AT_LEAST = 0x00, 0x60
#: FO4 INFO ENAM flags Random and Random End (R has the others).
RANDOM, RANDOM_END = 0x0002, 0x0020
#: Above the build's quests, so the test greeting wins while the global is on.
PRIORITY = 200
#: (prompt, option flags, the global value the option needs (0: none), [(answer, flags, global value needed)]).
DEMO_OPTIONS = (
    ('Tell me about yourself.', 0, 0, [('With the global at 2 this line passes first, so you hear it.', 0, 2),
                                       ("The first line of my topic that passes is the one you hear.", 0, 0)]),
    ('Say something random.', 0, 0, [('Random line one.', RANDOM, 0), ('Random line two.', RANDOM, 0),
                                     ('Random line three.', RANDOM | RANDOM_END, 0)]),
    ('Ask once: this option is Say Once.', R.INFO_SAY_ONCE, 0, [('You will not see that option again.', 0, 0)]),
    ('Ask for a Say Once answer.', 0, 0, [('First time: this answer is Say Once.', R.INFO_SAY_ONCE, 0),
                                          ('Every later time: the Say Once answer was said.', 0, 0)]),
    ('Goodbye.', 0, 0, [('Goodbye, then: this answer ends the scene.', R.INFO_END_SCENE, 0)]),
    ('A long option, to show how the list fits a long prompt: it should stay on one row and keep the other rows '
     'inside the box.', 0, 0, [('Long prompt answered.', 0, 0)]),
    ('Only listed while the global is 2.', 0, 2, [('Option conditions work.', 0, 0)]),
    ('Never listed: no line of my answer topic passes.', 0, 0, [('You should never hear this.', 0, 99)]),
)


class Ids:
    """Object ids in the plugin's own index, from 0x800."""

    def __init__(self):
        """Start after the masters."""
        self.next = len(MASTERS) << 24 | 0x800

    def take(self) -> int:
        """The next FormID."""
        fid, self.next = self.next, self.next + 1
        return fid


def _global_is(glob: int, op: int, value: int) -> bytes:
    """GetGlobalValue `glob` compared by `op` with `value`; b'' for value 0."""
    return R.pack_ctda(op, float(value), GLOBAL_VALUE, glob) if value else b''


def _answers(ids: Ids, quest: int, glob: int, option: tuple, menu: int) -> tuple:
    """(answer topic FormID, its pack_topic blob): an option's lines; all but an ending one start the menu again."""
    fid, infos = ids.take(), []
    for text, flags, value in option[3]:
        again = {} if flags & R.INFO_END_SCENE else {'scene': menu, 'phase': 'Menu'}
        flags |= 0 if flags & R.INFO_END_SCENE else R.INFO_START_ON_END
        infos.append(R.pack_info(ids.take(), flags, (text,), _global_is(glob, EQUAL, value), **again))
    edid = f'F3NVMenuTest_Answer{len(infos)}_{fid & 0xFFF:03X}'
    return fid, pack_topic(R.pack_dial(fid, edid, quest, R.TOPIC_SCENE, len(infos)), fid, infos)


def demo_plugin(path: Path) -> list:
    """Write the demo plugin to `path`; its links rows."""
    ids = Ids()
    quest, glob, menu, greeting = ids.take(), ids.take(), ids.take(), ids.take()
    topics, options, rows = [], [], []
    for option in DEMO_OPTIONS:
        answer, blob = _answers(ids, quest, glob, option, menu)
        topics.append(blob)
        info = ids.take()
        options.append(R.pack_info(info, option[1], (option[0],), _global_is(glob, EQUAL, option[2]), prompt=option[0]))
        rows.append((DEMO, info, DEMO, answer))
    npc = [R.pack_info(ids.take())]
    p_ids, n_id = [ids.take() for _ in range(4)], ids.take()
    for i, pid in enumerate(p_ids):
        infos = options if i == 0 else []
        topics.append(pack_topic(R.pack_dial(pid, f'F3NVMenuTest_P{i}', quest, R.TOPIC_SCENE, len(infos)), pid, infos))
    topics.append(pack_topic(R.pack_dial(n_id, 'F3NVMenuTest_N', quest, R.TOPIC_SCENE, 1), n_id, npc))
    action = R.pack_player_dialogue(1, 0, tuple(p_ids), (n_id,))
    opened = _global_is(glob, AT_LEAST, 1) + R.pack_ctda(EQUAL, 1.0, PLAYER_ACTIVATED)
    hello = R.pack_info(ids.take(), 0, (R.SILENT_LINE,), opened, scene=menu, phase='Menu', forced_alias=0)
    topics.insert(0, pack_topic(R.pack_dial(greeting, 'F3NVMenuTest_Greeting', quest, R.TOPIC_GREETING, 1),
                                greeting, [hello]))
    scene = R.pack_scen(menu, 'F3NVMenuTest_Menu', quest, 0, [action], 0)
    qust = R.pack_qust(quest, 'F3NVMenuTest', 'F3NV menu test', PRIORITY, [], 'Speaker', None)
    w = FO4PluginWriter(masters=MASTERS, is_esm=False, description='F3NV dialogue menu test')
    w.add_record('GLOB', pack_global(glob, 'F3NVMenuTest'))
    w.add_record('QUST', pack_quest(qust, quest, (), topics, [scene]))
    w.next_object_id = ids.next & 0xFFFFFF
    path.parent.mkdir(parents=True, exist_ok=True)
    w.write(str(path))
    return rows


def build(out: Path, dll: Path = DLL) -> list:
    """The test mod in `out`: demo plugin, its links, the menu movie and `dll`; the files written."""
    rows = demo_plugin(out / DEMO)
    written = [out / DEMO, write_links(out / LINKS / f'{Path(DEMO).stem}.txt', rows)]
    written.append(movie.install(out))
    target = out / 'F4SE' / 'Plugins' / 'F3NV.dll'
    shutil.copyfile(dll, target)
    return written + [target]


def main():
    """Build the test mod and list its files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=movie.OUTPUT, help='the mod folder to write')
    parser.add_argument('--dll', type=Path, default=DLL, help='the F3NV.dll to ship in it')
    args = parser.parse_args()
    for path in build(args.out, args.dll):
        print(path)


if __name__ == '__main__':
    main()
