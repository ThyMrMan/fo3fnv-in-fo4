"""FNV idle props shown as vanilla Fallout 4 animated objects: the smoking idles' cigarette.

See: docs/fork/fo4_idles.md#props
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from external.pynifly_hkx.anim_fo4 import parse_fo4_animation
from fo4_import.havok.anim_props import DRAW, LOAD, UNEQUIP, AnimProps, draw_frame
from fo4_import.havok.human_clip import HumanClips

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
SMOKING = {0x00071EE3, 0x000711A8, 0x00083518}
SMOKE_CLIP = 'characters\\_male\\idleanims\\smokingstanding.kf'
VANILLA_HOLD = (11.012, 0.0, -1.336)
SCIENTIST = 0x000A24FF
SCIENTIST_CLIP = 'characters\\_male\\idleanims\\scientistinspectterminala.kf'
needs_export = pytest.mark.skipif(not (EXPORT / 'ANIO.txt').exists(), reason='needs the FalloutNV.esm export')


@needs_export
def test_the_smoking_idles_show_vanillas_cigarette_on_the_right_hand_prop_bone():
    """Each FNV smoking idle's ANIO becomes AnimObjectCigarette, held where vanilla's smoking clips hold it."""
    props = AnimProps(EXPORT)
    for idle in SMOKING:
        (prop,) = props.get(idle)
        assert (prop.name, prop.bone) == ('AnimObjectCigarette', 'AnimObjectR1')
        assert np.allclose(prop.hold[0], VANILLA_HOLD, atol=0.01)
    assert props.get(0x00022C10) == ()


@needs_export
def test_a_smoking_clip_loads_draws_puffs_and_unequips_the_cigarette(tmp_path):
    """The converted clip loads then draws the object, puffs on FNV's inhale, unequips at its end and holds the
    prop bone at vanilla's spot."""
    (prop,) = AnimProps(EXPORT).get(0x00071EE3)
    clips = HumanClips(EXPORT / 'meshes')
    out = tmp_path / 'smoking.hkx'
    clips.write(SMOKE_CLIP, out, (prop,))
    anim = parse_fo4_animation(out.read_bytes())
    events = [(round(a.time, 2), a.text) for a in anim.annotations]
    times = {text: t for t, text in events}
    assert times[LOAD + prop.name] < times[DRAW + prop.name]
    assert times['cigDrag'] == 0.97
    assert times[UNEQUIP] == round(anim.duration, 2)
    track = anim.tracks[clips.fo4.names.index('AnimObjectR1')]
    assert np.allclose(track.translations[len(track.translations) // 2], VANILLA_HOLD, atol=0.01)


@needs_export
def test_a_scientist_idle_shows_the_clipboard_and_pencil_once_each(tmp_path):
    """An idle two ANIOs name shows both objects, each on its own hand's bone, and unequips once."""
    props = AnimProps(EXPORT).get(SCIENTIST)
    assert sorted((p.name, p.bone) for p in props) == [('AnimObjectClipboardLeftHand', 'AnimObjectL1'),
                                                      ('AnimObjectPencil', 'AnimObjectR1')]
    out = tmp_path / 'inspect.hkx'
    HumanClips(EXPORT / 'meshes').write(SCIENTIST_CLIP, out, props)
    texts = [a.text for a in parse_fo4_animation(out.read_bytes()).annotations]
    assert {LOAD + p.name for p in props} <= set(texts)
    assert texts.count(UNEQUIP) == 1


def test_a_hold_is_read_where_the_clip_draws_the_object():
    """The hold is read at the clip's AnimObjDraw of the object, else frame 0."""
    anim = SimpleNamespace(duration=2.0, annotations=[SimpleNamespace(time=1.0, text=DRAW + 'AnimObjectWrench')])
    assert draw_frame(anim, 'AnimObjectWrench', 61) == 30
    assert draw_frame(anim, 'AnimObjectMedX', 61) == 0
