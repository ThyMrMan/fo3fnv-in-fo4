"""Converted FNV human clips come from the work cache when their inputs are unchanged.

See: docs/fork/fo4_idles.md#clip-cache
"""

from pathlib import Path

import pytest

from fo4_import.havok import human_clip as H
from fo4_import.havok.anim_props import Prop
from fo4_import.pipeline import work_cache

EXPORT = Path(__file__).resolve().parents[1] / 'export' / 'FalloutNV.esm'
CLIP = 'characters\\_male\\idleanims\\specialidle_nvcg01docgivemirror.kf'
POSE = 'characters\\_male\\idleanims\\dynamicidle_nvcrucifiedidle.kf'
needs_export = pytest.mark.skipif(not (EXPORT / 'meshes' / CLIP).exists(), reason='needs the FalloutNV.esm export')


@needs_export
def test_an_unchanged_clip_is_written_from_the_cache_and_other_props_convert_again(tmp_path, monkeypatch):
    """The second write of the same clip converts nothing and writes the same bytes; a clip showing a prop
    converts again."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'work')
    converted = []
    real = H.HumanClips._converted
    monkeypatch.setattr(H.HumanClips, '_converted', lambda self, *a: converted.append(a[0]) or real(self, *a))
    clips = H.HumanClips(EXPORT / 'meshes')
    clips.write(CLIP, tmp_path / 'a.hkx')
    clips.write(CLIP, tmp_path / 'b.hkx')
    assert len(converted) == 1 and (tmp_path / 'a.hkx').read_bytes() == (tmp_path / 'b.hkx').read_bytes()
    clips.write(CLIP, tmp_path / 'c.hkx', (Prop('Mirror', 'AnimObjectR', ((0, 0, 0), (1, 0, 0, 0), 1), (), {}),))
    assert len(converted) == 2


@needs_export
def test_an_unchanged_pose_is_written_from_the_cache_and_other_sounds_convert_again(tmp_path, monkeypatch):
    """A furniture pose converts once for the same sound lookup; another lookup's answers convert it again."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'work')
    posed = []
    real = H.HumanClips._posed
    monkeypatch.setattr(H.HumanClips, '_posed', lambda self, *a: posed.append(a[2]) or real(self, *a))
    clips = H.HumanClips(EXPORT / 'meshes')
    clips.write_pose(POSE, tmp_path / 'a.hkx', lambda edid: 'SoundPlay.' + edid)
    clips.write_pose(POSE, tmp_path / 'b.hkx', lambda edid: 'SoundPlay.' + edid)
    assert len(posed) == 1 and (tmp_path / 'a.hkx').read_bytes() == (tmp_path / 'b.hkx').read_bytes()
    clips.write_pose(POSE, tmp_path / 'c.hkx', lambda edid: None)
    assert len(posed) == 2
