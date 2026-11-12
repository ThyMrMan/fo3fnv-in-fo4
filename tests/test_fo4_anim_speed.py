"""AnimationSpeedInfo: reading, writing, and an own-rig creature's file from its graph and clips."""

import struct

import pytest

from fo4_import.havok import anim_speed as S
from fo4_import.havok import graph as G
from fo4_import.havok import packfile_write
from fo4_import.havok.anim_offsets import Motion

#: Root speeds (units per second) of the synthetic walk and run clips.
WALK, RUN = 50.0, 300.0


def _f32(x: float) -> float:
    """`x` rounded to float32."""
    return struct.unpack('<f', struct.pack('<f', x))[0]


def _sample_file() -> list:
    """Entries using every contour kind, a collection of an individual clip and a sampled blend."""
    clip = S.Individual((0.0, 1.0, 0.0), 'fPlaybackSpeed', 120.5)
    blend = S.Sampled(3, (0.0, 0.0, 10.0, 90.0), [(0.0, [(10.0, 11.0), (90.0, 95.0)])], [(0.0, 10.0), (0.0, 90.0)])
    kids = [(clip, S.Tail('moveStart', 'iSyncState', 1, 0.0)), (blend, S.Tail())]
    return [S.Entry('Root.hkb/LocomotionSM', S.Collection(kids, 1), S.Tail(stop=0.0625)),
            S.Entry('Root.hkb/Other', blend)]


def test_a_file_reads_back_to_the_same_bytes():
    """Every contour kind and an empty string pack to the bytes they were read from."""
    data = S.pack(_sample_file())
    assert S.parse(data) == _sample_file() and S.pack(S.parse(data)) == data


def test_a_wrong_version_or_trailing_bytes_are_refused():
    """Another version, or bytes past the counts, mean the layout was misread."""
    data = S.pack(_sample_file())
    with pytest.raises(ValueError):
        S.parse(data + b'\0')
    with pytest.raises(ValueError):
        S.parse(struct.pack('<I', 5) + data[4:])


def _graph(name: str) -> bytes:
    """A root graph with LocoSM: Standing (an idle) and Moving (walk and run blended on Speed, at their speeds)."""
    g = G.Graph(name)
    fx = g.blend_effect('MoveTransition', 0.2)
    blend = g.blend('MoveBlend', [(g.clip('Walk', 'Animations\\Walk.hkt', G.LOOPING), WALK),
                                  (g.clip('Run', 'Animations\\Run.hkt', G.LOOPING), RUN)],
                    'Speed', G.FLAG_SYNC | G.FLAG_PARAMETRIC)
    states = [g.state(0, 'Standing', g.clip('Idle', 'Animations\\Idle.hkt', G.LOOPING), to=[('moveStart', 1)],
                      effect=fx),
              g.state(1, 'Moving', blend, to=[('moveStop', 0)], effect=fx)]
    g.finish(g.machine('LocoSM', states, 0))
    return packfile_write.write(g.objects, g.top)


def _clips(travel: bool):
    """Clip lookup: walk and run move at WALK and RUN with `travel`; idle stays."""
    speeds = {'Animations\\Walk.hkt': WALK, 'Animations\\Run.hkt': RUN} if travel else {}
    return lambda name: Motion(1.0, 31, [(0.0, 0.0, 0.0, 0.0), (0.0, speeds.get(name, 0.0), 0.0, 0.0)], 1.0)


def test_a_speed_blend_gets_one_sampled_entry():
    """A linear blend keeps its first and last 20-unit step; the outline holds the children's speeds."""
    data = S.rig_speed(_graph('XRootBehavior'), 'Actors\\X\\Behaviors\\XRootBehavior.hkx', _clips(True))
    (entry,) = S.parse(data)
    assert entry.key == 'XRootBehavior.hkb/LocoSM'
    assert (entry.tail.event, entry.tail.sync, entry.tail.value) == ('', '', -1)
    assert entry.tail.stop == _f32(2.5 / 30)
    c = entry.contour
    assert (c.node, c.bounds, c.centered) == (1, (0.0, 0.0, WALK, RUN), 1)
    assert c.directions == [(0.0, [(WALK, WALK), (290.0, 290.0)])]
    assert c.outline == [(0.0, WALK), (0.0, RUN)]


def test_no_root_travel_writes_no_file():
    """Walk and run that stay in place (spore plant, raven): no file."""
    assert S.rig_speed(_graph('XRootBehavior'), 'Actors\\X\\Behaviors\\XRootBehavior.hkx', _clips(False)) is None


def test_missing_clips_write_no_file():
    """No root motion for any clip the blend plays: nothing to measure."""
    assert S.rig_speed(_graph('XRootBehavior'), 'Actors\\X\\Behaviors\\XRootBehavior.hkx', lambda name: None) is None
