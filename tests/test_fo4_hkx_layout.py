"""PyNifly's FO4 clip and skeleton writer lays packfiles out as vanilla Fallout 4 does.

A clip whose resource container had a null name, written unpadded, crashed the game when it freed the clip.

See: docs/fork/fo4_spikes.md#own-rig-clip-layout
"""

import struct

from external.pynifly_hkx.anim_fo4 import (AnimationData, Annotation, BonePose, Skeleton, TrackData,
                                           parse_fo4_animation, parse_fo4_skeleton, write_fo4_animation,
                                           write_fo4_skeleton)

BONES = ['Root', 'Pelvis', 'Tail']


def packfile(raw: bytes) -> dict:
    """The data section of a 64-bit hk_2014 packfile: its start, fixup table bounds, objects and local fixups."""
    first = 0x40 + struct.unpack_from('<H', raw, 0x3E)[0]
    heads = [raw[first + i * 0x40:first + (i + 1) * 0x40] for i in range(3)]
    names_at = struct.unpack_from('<I', heads[0], 0x14)[0]
    start, lf, gf, vf, ex = struct.unpack_from('<5I', heads[2], 0x14)
    rows = lambda a, b, fmt: [struct.unpack_from(fmt, raw, p) for p in range(start + a, start + b, struct.calcsize(fmt))
                              if raw[p:p + 4] != b'\xff\xff\xff\xff']
    objects = [(src, raw[names_at + name:raw.index(b'\x00', names_at + name)].decode())
               for src, _, name in rows(vf, ex, '<3I')]
    return {'raw': raw, 'heads': heads, 'start': start, 'tables': (gf - lf, vf - gf, ex - vf),
            'objects': objects, 'local': dict(rows(lf, gf, '<2I'))}


def clip() -> AnimationData:
    """A five-frame, three-track clip with one annotation."""
    tracks = [TrackData(translations=[[float(i), 0.0, float(f)] for f in range(5)],
                        rotations=[[0.0, 0.0, 0.0, 1.0]] * 5, scales=[[1.0, 1.0, 1.0]] * 5) for i in range(3)]
    return AnimationData(duration=4 / 30, num_frames=5, num_tracks=3, bone_names=list(BONES), tracks=tracks,
                         annotations=[Annotation(0.1, 'HitFrame')], original_skeleton_name='Root')


def skeleton() -> Skeleton:
    """Three bones in a chain."""
    return Skeleton(name='Root', bones=list(BONES), parents=[-1, 0, 1],
                    reference_pose=[BonePose([0.0, 0.0, float(i)]) for i in range(3)])


def assert_vanilla_frame(pf: dict) -> None:
    """Objects 16-aligned, fixup tables padded to 16, section names zero-padded before the 0xFF000000 marker."""
    assert all(src % 16 == 0 for src, _ in pf['objects'])
    assert all(size % 16 == 0 for size in pf['tables'])
    for head in pf['heads']:
        name = head[:16].split(b'\x00')[0]
        assert head[:16] == name.ljust(16, b'\x00')
        assert struct.unpack_from('<I', head, 0x10)[0] == 0xFF000000


def test_clip_layout_matches_vanilla(tmp_path):
    """The clip's frame is vanilla's and its resource container is 64 bytes named '' (not null)."""
    path = tmp_path / 'clip.hkx'
    write_fo4_animation(str(path), clip())
    pf = packfile(path.read_bytes())
    assert_vanilla_frame(pf)
    classes = [cls for _, cls in pf['objects']]
    assert classes == ['hkRootLevelContainer', 'hkaAnimationContainer', 'hkaSplineCompressedAnimation',
                       'hkaDefaultAnimatedReferenceFrame', 'hkaAnimationBinding', 'hkMemoryResourceContainer']
    container = dict((cls, src) for src, cls in pf['objects'])['hkMemoryResourceContainer']
    name = pf['local'][container + 0x10]
    assert name == container + 64
    assert pf['raw'][pf['start'] + name] == 0
    back = parse_fo4_animation(pf['raw'])
    assert back.bone_names == BONES and [a.text for a in back.annotations] == ['HitFrame']


def test_skeleton_layout_matches_vanilla(tmp_path):
    """The skeleton's frame is vanilla's: one named variant, no resource container, its bones read back."""
    path = tmp_path / 'skeleton.hkx'
    write_fo4_skeleton(str(path), skeleton())
    pf = packfile(path.read_bytes())
    assert_vanilla_frame(pf)
    assert [cls for _, cls in pf['objects']] == ['hkRootLevelContainer', 'hkaAnimationContainer', 'hkaSkeleton']
    assert struct.unpack_from('<i', pf['raw'], pf['start'] + 8)[0] == 1
    back = parse_fo4_skeleton(pf['raw'])
    assert back.bones == BONES and back.parents == [-1, 0, 1]
