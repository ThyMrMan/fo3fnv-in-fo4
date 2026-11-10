"""FNV idle props (ANIO) played as vanilla Fallout 4 animated objects (data/anim_props.json).

FNV pairs a prop mesh with an idle (ANIO DATA.Idle). FO4 loads a prop by
events in the clip naming its ANIO's EditorID (vanilla to_smoking.hkx:
AnimObjLoad.<object>, then AnimObjDraw.<object>; AnimObjUnequip removes it)
and hangs it from a prop bone (AnimObjectR1) the clip holds against the hand.
A converted clip whose idle has a listed prop carries those events, the
object's own (cigOn, cigDrag) and vanilla's hold of the bone.

See: docs/fork/fo4_idles.md#props
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from asset_convert.havok.kf_decode import BoneTrack
from external.pynifly_hkx.anim_fo4 import parse_fo4_animation, parse_fo4_skeleton
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.pipeline.export_index import export_records

TABLE = Path(__file__).resolve().parents[1] / 'data' / 'anim_props.json'
ANIMATIONS = 'Fallout4 - Animations.ba2'
SKELETON = 'meshes\\actors\\character\\characterassets\\skeleton.hkx'
#: FO4's prop events: load the object, show it (a frame later, as vanilla shows it after loading), remove it.
LOAD, DRAW, UNEQUIP = 'AnimObjLoad.', 'AnimObjDraw.', 'AnimObjUnequip'
DRAW_DELAY = 1.0 / 30.0


@dataclass
class Prop:
    """A vanilla animated object a clip shows: its EditorID, prop bone, the bone's hold (translation, rotation
    wxyz, scale), its start events and {FNV text key: its event}."""
    name: str
    bone: str
    hold: tuple
    start: tuple
    keys: dict

    def events(self, text_keys: list, duration: float) -> list:
        """[(time, event)] of a clip `duration` long with FNV `text_keys` [(time, text)] showing this prop."""
        keys = {k.lower(): v for k, v in self.keys.items()}
        out = [(0.0, LOAD + self.name), (DRAW_DELAY, DRAW + self.name), *((DRAW_DELAY, e) for e in self.start)]
        out += [(t, keys[text.lower()]) for t, text in text_keys if text.lower() in keys]
        return out + [(duration, UNEQUIP)]

    def track(self, clip, fnv) -> BoneTrack:
        """The prop bone's track over FNV `clip`: the hold on every frame."""
        frames = len(clip.times)
        return BoneTrack(self.bone, np.tile(self.hold[0], (frames, 1)), np.tile(self.hold[1], (frames, 1)))


class AnimProps:
    """{FNV idle FormID: {prop bone: Prop}} of an export's ANIO records whose model the table lists."""

    def __init__(self, export_dir: Path):
        """Props of `export_dir`'s ANIO records, each listed model's bone hold read once from vanilla's clip."""
        table = json.loads(TABLE.read_text(encoding='utf-8'))['props']
        archives, made = Archives(FALLOUT4_DIR / 'Data', ANIMATIONS), {}
        self.by_idle, self.models = {}, set(table)
        for rec in export_records(export_dir, 'ANIO'):
            model = rec.get('Model.MODL', '').lower()
            if model not in table or not rec.get('DATA.Idle'):
                continue
            if model not in made:
                made[model] = prop_of(table[model], archives)
            self.by_idle.setdefault(int(rec['DATA.Idle'], 16), {})[made[model].bone] = made[model]

    def get(self, idle: int) -> tuple:
        """The props FNV idle `idle` shows, one per prop bone."""
        return tuple(self.by_idle.get(idle, {}).values())


def prop_of(entry: dict, archives: Archives) -> Prop:
    """The Prop of table `entry`, its bone's hold read from vanilla clip `entry['hold']` at the frame it draws the
    object (frame 0 when it never does)."""
    bones = parse_fo4_skeleton(archives.read(SKELETON)).bones
    anim = parse_fo4_animation(archives.read('meshes\\' + entry['hold']))
    bone = bones.index(entry['bone'])
    track = anim.tracks[anim.track_to_bone_indices.index(bone) if anim.track_to_bone_indices else bone]
    frame = draw_frame(anim, entry['object'], len(track.rotations))
    x, y, z, w = track.rotations[frame]
    return Prop(entry['object'], entry['bone'], (tuple(track.translations[frame]), (w, x, y, z), 1.0),
                tuple(entry['start']), dict(entry['keys']))


def draw_frame(anim, name: str, frames: int) -> int:
    """The frame of `anim` (`frames` long) at its AnimObjDraw of object `name`, or 0."""
    draw = next((a.time for a in anim.annotations if a.text == DRAW + name), 0.0)
    return min(frames - 1, round(draw / anim.duration * (frames - 1))) if anim.duration else 0
