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

See: docs/fork/fo4_idles.md#records
"""

import struct
from pathlib import Path

from external.pynifly_hkx.anim_fo4 import parse_fo4_animation, write_fo4_animation
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import pack_fo4_record
from fo4_import.havok.human_clip import HumanClips
from fo4_import.pipeline.export_index import asset_root, export_records
from fo4_import.spike.say_topics import conditions_of
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
#: FO4 dynamic-idle events: played once, and looped until stopped.
PLAY_ONCE, PLAY_LOOPED = 'dyn_Activation', 'dyn_ActivationLoop'
#: FNV loop counts (min, max) meaning "forever", FO4's looping seconds meaning the same.
FOREVER = (255, 255)
#: FO4 IDLE DATA flag of an idle with no parent.
LOOSE = 0x01
#: FNV human clips' folder (lowercase), and where their conversions go under Meshes.
FNV_HUMAN = 'characters\\_male\\'
FO4_CLIPS = 'Actors\\Character\\Animations'
#: The FNV response keys naming a line's idles: the speaker's and the listener's.
LINE_IDLE_KEYS = ('SpeakerIdle', 'ListenerIdle')


class Idles:
    """The build's FO4 idles: `idle`/`named` hand out an FNV idle's FormID, `write` converts what was handed out."""

    def __init__(self, builder, export_dir: Path):
        """Idles of `export_dir`'s IDLE records for `builder`; `form_map` (FNV -> FO4 forms) is set before write."""
        self.builder, self.meshes, self.plugin = builder, asset_root(export_dir, 'meshes'), Path(export_dir.name).stem
        self.records = {int(r['FormID'], 16): r for r in export_records(export_dir, 'IDLE')}
        self.names = {r['EditorID'].lower(): fid for fid, r in self.records.items() if r.get('EditorID')}
        self.used, self.checked, self.counted, self.form_map, self.clips = {}, {}, set(), {}, None

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
        """Why an idle playing `model` is left out; '' when it converts."""
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

    def write(self, data_dir: Path) -> None:
        """Convert every handed-out idle's clip into `data_dir` and add its IDLE record."""
        for fnv, fid in sorted(self.used.items()):
            rec = self.records[fnv]
            clip = Path(FO4_CLIPS, self.plugin, rec['Model.MODL'][len(FNV_HUMAN):]).with_suffix('.hkx')
            if PROBE.get(rec['EditorID']):
                clip = self._probe(*PROBE[rec['EditorID']], data_dir)
            else:
                self.clips.write(rec['Model.MODL'], data_dir / 'Meshes' / clip)
            conditions = conditions_of(rec, self.form_map, self.builder.script_vars)
            if conditions is None:
                self.builder.counts['idle conditions not converted'] += 1
            graph = FURNITURE_GRAPH if self.checked[fnv] == SEATED else ROOT_GRAPH
            self.builder.writer.add_record('IDLE', pack_idle(fid, rec, conditions or b'', (graph, str(clip)),
                                                             self.used))
            self.builder.counts['IDLE' + (' (seated, scripted)' if graph == FURNITURE_GRAPH else '')] += 1


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


def pack_idle(fid: int, rec: dict, conditions: bytes, clip: tuple, built: dict) -> bytes:
    """FO4 IDLE `fid` of FNV idle `rec` playing `clip` (behavior graph, clip path), its parent and previous idles
    among `built` {FNV: FO4}."""
    loops = (int(rec.get('DATA.LoopMin', 0)), int(rec.get('DATA.LoopMax', 0)))
    parent, previous = (built.get(int(rec.get(f'ANAM.{k}', '0'), 16), 0) for k in ('Parent', 'Previous'))
    data = struct.pack('<BBBBH', *(loops if loops == FOREVER else (0, 0)), 0 if parent else LOOSE, 0,
                       int(rec.get('DATA.ReplayDelay', 0)))
    subs = pack_string_subrecord('EDID', rec['EditorID']) + conditions
    subs += pack_string_subrecord('DNAM', clip[0])
    subs += pack_string_subrecord('ENAM', PLAY_LOOPED if loops == FOREVER else PLAY_ONCE)
    subs += pack_subrecord('ANAM', struct.pack('<II', parent, previous)) + pack_subrecord('DATA', data)
    return pack_fo4_record('IDLE', fid, 0, subs + pack_string_subrecord('GNAM', clip[1]))
