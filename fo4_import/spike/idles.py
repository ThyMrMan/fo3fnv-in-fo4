"""FNV IDLE records as Fallout 4 dynamic idles, their .kf clips converted, for the cell spike.

An FNV idle the build uses (a converted script's Idle property, a line's
speaker or listener idle) becomes an FO4 IDLE on FNV's FormID: FO4's human
root behavior graph (DNAM), the dynamic-idle event (ENAM; the looping one
when FNV loops the idle forever) and the clip converted onto FO4's skeleton
(GNAM, under Actors\\Character\\Animations\\<plugin>\\). It keeps FNV's
conditions, parent and previous idles when built, and replay delay; an idle
without a parent is loose, as vanilla's loose dynamic idles are. An idle
whose clip is missing or not a human one is left out. A clip that starts
seated plays only by script (PlayIdle), on the chair's furniture graph, as
vanilla's seated scripted idles do, when a script's Idle property names it.
A line's seated idle is left out: as SNAM it crashed on both graphs, and
played by script as each line began it crashed later in a plain graph update.

FNV's ambient idle tree is built whole (fo4_idles.md#trees): its root under
FO4's ActionIdle, its group nodes as vanilla's (graph and conditions only).

See: docs/fork/fo4_idles.md#records
"""

import struct
from collections import defaultdict
from pathlib import Path

from external.pynifly_hkx.anim_fo4 import parse_fo4_animation, write_fo4_animation
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.source import plugin_stem
from fo4_import.base.writer import pack_fo4_record
from fo4_import.havok.human_clip import HumanClips
from fo4_import.pipeline.export_index import asset_root, export_records
from fo4_import.rig.table import rigs
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.idle_props import IdleProps
from fo4_import.spike.say_topics import conditions_of, parsed
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Seated idles a script may play, each played safely in game; other seated idles stay out (fo4_idles.md#standing).
SEATED_PLAYED = frozenset({'VCG01DocGiveMirror'})
#: Encoder probe (fo4_idles.md#encoder-test), {FNV idle: (vanilla clip, re-encoded, seconds kept)}; empty when off.
PROBE = {}
#: The archive holding vanilla's clips (under Meshes).
ANIMATIONS = 'Fallout4 - Animations.ba2'
#: Behavior graphs: standing (the human root) and a chair's (AnimFurnChairSitAnims, HumanRaceSubGraphData).
ROOT_GRAPH = 'Actors\\Character\\Behaviors\\RaiderRootBehavior.hkx'
FURNITURE_GRAPH = 'Actors\\Character\\Behaviors\\FurnitureBehavior.hkx'
#: Why a seated clip is left out of a line (and the mark of one a script plays on the furniture graph).
SEATED = 'seated'
#: FO4 dynamic-idle events (played once, and looped until stopped): the human graphs', and vanilla creatures' (ENAM).
HUMAN_EVENTS, RIG_EVENTS = ('dyn_Activation', 'dyn_ActivationLoop'), ('dynamicAnim', 'dynamicAnimLooping')
#: FNV loop counts (min, max) meaning "forever", FO4's looping seconds meaning the same.
FOREVER = (255, 255)
#: FO4 IDLE DATA flag of an idle with no parent.
LOOSE = 0x01
#: FNV human clips' folder (lowercase), and where their conversions go under Meshes.
FNV_HUMAN = 'characters\\_male\\'
FO4_CLIPS = 'Actors\\Character\\Animations'
#: The FNV response keys naming a line's idles: the speaker's and the listener's.
LINE_IDLE_KEYS = ('SpeakerIdle', 'ListenerIdle')
#: FNV's ambient idle tree (its root's EditorID); Fallout4.esm's ActionIdle, the action its ambient trees hang under.
AMBIENT_ROOT, ACTION_IDLE = 'GeneralIdles', 0x00013002
#: FNV's drawn-weapon test: its idles play on FO4's weapon graph (vanilla WeaponAltIdleRoot), not built.
WEAPON_OUT = 'IsWeaponOut'
#: GetSitting == 0, first on a standing idle's conditions (as vanilla's CreateABotTalkRoot): a sitter never stands.
STANDING = R.pack_ctda(0, 0.0, C.FO4.index('GetSitting'))
#: How often an idle FNV actor retries its idle tree (fAIIdleWaitTime, FalloutNV.exe default), in seconds.
FNV_IDLE_WAIT = 1.0
#: FNV's random test and its "less than" comparison (CTDA op bits).
RANDOM, LESS = 'GetRandomPercent', 0x80


class Idles:
    """The build's FO4 idles: `idle`/`named` hand out an FNV idle's FormID, `write` converts what was handed out."""

    def __init__(self, builder, export_dir: Path):
        """Idles of `export_dir`'s IDLE records for `builder`; `form_map` (FNV -> FO4 forms) is set before write."""
        self.builder, self.meshes, self.plugin = builder, asset_root(export_dir, 'meshes'), plugin_stem(export_dir)
        self.export_dir, self.props = export_dir, None
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'IDLE')}
        self.names = {r['EditorID'].lower(): fid for fid, r in self.records.items() if r.get('EditorID')}
        self.used, self.checked, self.counted, self.form_map, self.clips = {}, {}, set(), {}, None
        self.kids, self.tree, self.groups, self.root = defaultdict(list), {}, set(), None
        for fid, rec in self.records.items():
            self.kids[int(rec.get('ANAM.Parent', '0'), 16)].append(fid)

    def idle(self, fnv: int, scripted: bool = False) -> 'int | None':
        """The FO4 FormID of FNV idle `fnv`, played by a script when `scripted`; None when it is left out (the
        module notes)."""
        played = scripted and self.records.get(fnv, {}).get('EditorID') in SEATED_PLAYED
        why = '' if played and self._reason(fnv) == SEATED else self._reason(fnv)
        if why:
            if (fnv, why) not in self.counted:
                self.counted.add((fnv, why))
                self.builder.counts[f'idle left out ({why})'] += 1
            return None
        self.used.setdefault(fnv, self.builder.fnv_id(fnv))
        return self.used[fnv]

    def _reason(self, fnv: int) -> str:
        """`_left_out` of FNV idle `fnv`'s clip, worked out once."""
        if fnv not in self.checked:
            self.checked[fnv] = self._left_out(self.records.get(fnv, {}).get('Model.MODL', ''))
        return self.checked[fnv]

    def _left_out(self, model: str) -> str:
        """Why an idle playing `model` is left out; '' when it converts (a human clip, or one in an own rig's folder)."""
        if rig_of(model) and (self.meshes / model).is_file():
            return ''
        if not model.lower().startswith(FNV_HUMAN) or not (self.meshes / model).is_file():
            return 'no human clip'
        self.clips = self.clips or HumanClips(self.meshes)
        return SEATED if self.clips.seated(model) else ''

    def named(self, edid: str) -> 'int | None':
        """`idle` of the FNV idle named `edid`, played by a script; None if unknown."""
        fnv = self.names.get(edid.lower())
        return None if fnv is None else self.idle(fnv, scripted=True)

    def line(self, rec: dict) -> tuple:
        """(speaker, listener) FO4 idle (0: none) per response of FNV line `rec`."""
        named = [[rec.get(f'Response[{i}].{key}') for key in LINE_IDLE_KEYS]
                 for i in range(int(rec.get('ResponseCount', 0) or 0))]
        return tuple(tuple(self.idle(int(v, 16)) or 0 if v else 0 for v in pair) for pair in named)

    def ambient_records(self) -> list:
        """FNV's ambient idle tree's records, root first, if this plugin owns it."""
        root = self.names.get(AMBIENT_ROOT.lower())
        return [] if root is None or not self.builder.ids.is_own(root) else self._subtree(root)

    def _subtree(self, fnv: int) -> list:
        """FNV idle `fnv`'s record and every one below it."""
        return [self.records[fnv], *(rec for kid in self.kids.get(fnv, ()) for rec in self._subtree(kid))]

    def _ambient_tree(self) -> None:
        """Hand out FNV's ambient idle tree, its root under FO4's ActionIdle (_branch).
        See: docs/fork/fo4_idles.md#trees
        """
        records, self.delays = self.ambient_records(), {}
        if records:
            self.root = int(records[0]['FormID'], 16)
            self.tree_map = {**self.form_map, **{fnv: self.builder.fnv_id(fnv)
                                                 for fnv in (int(r['FormID'], 16) for r in records)}}
            self._branch(self.root)
            for group in self.groups:
                self._space(group)

    def _space(self, group: int) -> None:
        """Give each kept leaf of `group` a replay delay: its group's FNV mean gap (FNV_IDLE_WAIT over the chance of
        the random tests on the group and its parents) times its kept leaves, or FNV's own delay if longer.
        See: docs/fork/fo4_idles.md#trees
        """
        leaves = [kid for kid in self.kids.get(group, ()) if kid in self.tree and kid not in self.groups]
        chance, node = 1.0, group
        while node in self.tree:
            chance *= random_chance(self.records[node])
            node = int(self.records[node].get('ANAM.Parent', '0'), 16)
        gap = round(FNV_IDLE_WAIT / chance * len(leaves)) if chance else 0
        for leaf in leaves:
            self.delays[leaf] = min(max(gap, int(self.records[leaf].get('DATA.ReplayDelay', 0) or 0)), 0xFFFF)

    def _branch(self, fnv: int) -> bool:
        """Hand out ambient tree node `fnv` when its conditions convert, it does not need the weapon drawn, and it
        plays a clip (idle) or holds a node that does; whether it is kept."""
        rec = self.records[fnv]
        conditions = None if needs_weapon(rec) else conditions_of(rec, self.tree_map, self.builder.script_vars)
        if conditions is None:
            self.builder.counts['ambient idle left out (conditions)'] += 1
            return False
        group = not rec.get('Model.MODL', '').lower().endswith('.kf')
        if not any([kid for kid in self.kids.get(fnv, ()) if self._branch(kid)] if group else [self.idle(fnv)]):
            return False
        self.tree[fnv] = conditions
        if group:
            self.groups.add(fnv)
            self.used.setdefault(fnv, self.tree_map[fnv])
        return True

    def _links(self, fnv: int) -> tuple:
        """(parent, previous) FO4 idles of FNV idle `fnv`: built ones (a left-out previous skipped to the one before
        it); the ambient root's ActionIdle."""
        if fnv == self.root:
            return ACTION_IDLE, 0
        rec, seen = self.records[fnv], set()
        previous = int(rec.get('ANAM.Previous', '0'), 16)
        while previous and previous not in self.used and previous not in seen:
            seen.add(previous)
            previous = int(self.records.get(previous, {}).get('ANAM.Previous', '0'), 16)
        return self.used.get(int(rec.get('ANAM.Parent', '0'), 16), 0), self.used.get(previous, 0)

    def write(self, data_dir: Path) -> None:
        """Convert every handed-out idle's clip into `data_dir` and add its IDLE record, the ambient tree's
        (_ambient_tree) among them."""
        self._ambient_tree()
        for fnv, fid in sorted(self.used.items()):
            rec = self.records[fnv]
            group = fnv in self.groups
            conditions = self.tree[fnv] if fnv in self.tree else conditions_of(rec, self.form_map,
                                                                                self.builder.script_vars)
            if conditions is None:
                self.builder.counts['idle conditions not converted'] += 1
            played, links = self._played(fnv, rec, group, data_dir), self._links(fnv)
            standing = fnv == self.root or not links[0] and played[0] == ROOT_GRAPH and played[1]
            conditions = (STANDING if standing else b'') + (conditions or b'')
            rec = {**rec, 'DATA.ReplayDelay': str(self.delays[fnv])} if fnv in self.delays else rec
            self.builder.writer.add_record('IDLE', pack_idle(fid, rec, conditions, played, links))
            kind = ' (ambient tree)' if fnv in self.tree else ' (seated, scripted)' if played[0] == FURNITURE_GRAPH \
                else ' (own rig)' if played[2] == RIG_EVENTS else ''
            self.builder.counts['IDLE' + kind] += 1

    def _played(self, fnv: int, rec: dict, group: bool, data_dir: Path) -> tuple:
        """(behavior graph, clip under Meshes, (once, looped) events) of handed-out idle `fnv`: a group node plays
        no clip; a clip in an own rig's folder plays on that rig (Rigs.idle_clip), a human one on the human root or
        chair graph.
        See: docs/fork/fo4_own_rig.md#idles
        """
        rig = None if group else rig_of(rec.get('Model.MODL', ''))
        if rig:
            name = rec['Model.MODL'][len(rig.folder) + 1:]
            clip = self.builder.creatures.own_rigs().idle_clip(rig, self.meshes / rec['Model.MODL'], name)
            return rig.path('Behaviors', f'{rig.project}RootBehavior.hkx'), clip, RIG_EVENTS
        graph = FURNITURE_GRAPH if self.checked.get(fnv) == SEATED else ROOT_GRAPH
        return graph, '' if group else str(self._clip(rec, data_dir)), HUMAN_EVENTS

    def _clip(self, rec: dict, data_dir: Path) -> Path:
        """Convert FNV idle `rec`'s clip into `data_dir` (PROBE's when it names `rec`); its path under Meshes."""
        if PROBE.get(rec['EditorID']):
            return self._probe(*PROBE[rec['EditorID']], data_dir)
        clip = Path(FO4_CLIPS, self.plugin, rec['Model.MODL'][len(FNV_HUMAN):]).with_suffix('.hkx')
        self.props = self.props or IdleProps(self.builder, self.export_dir, self.clips)
        props = self.props.get(int(rec['FormID'], 16))
        self.clips.write(rec['Model.MODL'], data_dir / 'Meshes' / clip, props)
        self.builder.counts['idle clip with a prop'] += bool(props)
        return clip

    def _probe(self, vanilla: str, encoded: bool, seconds: 'float | None', data_dir: Path) -> Path:
        """The clip a PROBE idle plays: vanilla's own path, or its clip decoded and written by our encoder,
        cut to its first `seconds` when given.
        See: docs/fork/fo4_idles.md#encoder-test
        """
        if not encoded:
            return Path(vanilla)
        raw = Archives(FALLOUT4_DIR / 'Data', ANIMATIONS).read('meshes\\' + vanilla.lower())
        clip = Path(FO4_CLIPS, self.plugin, 'Probe', Path(vanilla.replace('\\', '/')).name)
        (data_dir / 'Meshes' / clip).parent.mkdir(parents=True, exist_ok=True)
        anim = parse_fo4_animation(raw)
        write_fo4_animation(str(data_dir / 'Meshes' / clip), trimmed(anim, seconds) if seconds else anim)
        self.builder.counts['idle probe clip re-encoded'] += 1
        return clip


def trimmed(anim, seconds: float):
    """`anim` (anim_fo4.AnimationData) cut to its first `seconds`, in place; its events past the cut dropped."""
    frames = min(anim.num_frames, round(seconds / anim.frame_duration) + 1)
    anim.num_frames, anim.duration = frames, (frames - 1) * anim.frame_duration
    anim.num_blocks = -(-(frames - 1) // (anim.max_frames_per_block - 1)) or 1
    for track in anim.tracks:
        track.translations, track.rotations, track.scales = (
            track.translations[:frames], track.rotations[:frames], track.scales[:frames])
    anim.annotations = [a for a in anim.annotations if a.time <= anim.duration]
    return anim


def needs_weapon(rec: dict) -> bool:
    """Whether FNV idle `rec` needs the weapon drawn (IsWeaponOut == 1, no OR)."""
    return any(len(group) == 1 and group[0]['func'] == WEAPON_OUT and not group[0]['op_flags'] & 0xE0
               and group[0]['value'] == 1 for group in C.groups(parsed(rec)))


def random_chance(rec: dict) -> float:
    """The chance FNV idle `rec`'s lone `GetRandomPercent < N` tests pass (1.0 without one)."""
    chance = 1.0
    for group in C.groups(parsed(rec)):
        test = group[0]
        if len(group) == 1 and test['func'] == RANDOM and test['op_flags'] & 0xE0 == LESS:
            chance *= min(max(test['value'], 0.0), 100.0) / 100
    return chance


def rig_of(model: str):
    """The own rig (rig.table) whose FNV folder holds clip `model`, or None."""
    low = model.lower()
    return next((rig for folder, rig in rigs().items() if low.startswith(folder + '\\')), None)


def pack_idle(fid: int, rec: dict, conditions: bytes, clip: tuple, links: tuple) -> bytes:
    """FO4 IDLE `fid` of FNV idle `rec` playing `clip` (behavior graph, clip path, (once, looped) events; a group
    node's clip empty: no event, no clip) under `links` (FO4 parent, previous)."""
    loops = (int(rec.get('DATA.LoopMin', 0) or 0), int(rec.get('DATA.LoopMax', 0) or 0))
    data = struct.pack('<BBBBH', *(loops if loops == FOREVER else (0, 0)), 0 if links[0] else LOOSE, 0,
                       int(rec.get('DATA.ReplayDelay', 0) or 0))
    subs = pack_string_subrecord('EDID', rec['EditorID']) + conditions
    subs += pack_string_subrecord('DNAM', clip[0])
    subs += pack_string_subrecord('ENAM', clip[2][loops == FOREVER]) if clip[1] else b''
    subs += pack_subrecord('ANAM', struct.pack('<II', *links)) + pack_subrecord('DATA', data)
    return pack_fo4_record('IDLE', fid, 0, subs + (pack_string_subrecord('GNAM', clip[1]) if clip[1] else b''))
