"""FO3/FNV movies on Fallout 4: Bink 1 retracking, the movies a build ships, and PlayBink's conversion."""

import struct

from fo4_import.base import bink
from fo4_import.base.bink import retrack, track_ids
from script_convert.converter import ScriptConverter
from script_convert.cross_ref import CrossRefGraph
from tests.test_script_converter import conv_lines

#: Two frames: (keyframe, [audio packet per track], video bytes); even sizes, since offset bit 0 marks a keyframe.
FRAMES = [(1, [b'\x04\0\0\0' + b'A' * 4, b'\x02\0\0\0' + b'B' * 2], b'video-one!'),
          (0, [b'\0\0\0\0', b'\0\0\0\0'], b'v2v2')]


def _bink(path, frames=FRAMES):
    """Write a Bink 1 file holding `frames`, its audio tracks IDs 0 then 7."""
    tracks = len(frames[0][1])
    body = [b''.join(packets) + video for _, packets, video in frames]
    pos = 44 + 12 * tracks + 4 * (len(frames) + 1)
    offsets = []
    for (key, _, _), data in zip(frames, body):
        offsets.append(pos | key)
        pos += len(data)
    header = struct.pack('<4s10I', b'BIKi', pos - 8, len(frames), max(map(len, body)), len(frames),
                         64, 32, 30, 1, 0, tracks)
    tables = struct.pack(f'<{tracks}I', *[100] * tracks) + struct.pack('<HHHH', 48000, 0x7000, 22050, 0x3000)[:4 * tracks]
    ids = struct.pack(f'<{tracks}I', *(0, 7)[:tracks])
    path.write_bytes(header + tables + ids + struct.pack(f'<{len(frames) + 1}I', *offsets, pos) + b''.join(body))


def _frames(path):
    """[(keyframe, frame bytes)] of a Bink 1 file, checking its size fields against its length."""
    data = path.read_bytes()
    fields = struct.unpack_from('<4s10I', data)
    index = struct.unpack_from(f'<{fields[2] + 1}I', data, 44 + 12 * fields[10])
    assert index[-1] == len(data) == fields[1] + 8
    frames = [(index[i] & 1, data[index[i] & ~1:index[i + 1] & ~1]) for i in range(fields[2])]
    assert fields[3] == max(len(f) for _, f in frames)
    return frames


def test_retrack_repeats_first_track_under_each_id(tmp_path):
    """Every frame keeps its keyframe flag and video; the first track's packet appears once per ID."""
    src, dst = tmp_path / 'in.bik', tmp_path / 'out.bik'
    _bink(src)
    retrack(src, dst, (1, 2, 3))
    assert track_ids(dst) == (1, 2, 3)
    out = _frames(dst)
    for (key, packets, video), (out_key, frame) in zip(FRAMES, out):
        assert out_key == key and frame == packets[0] * 3 + video


def test_retrack_single_id_relabels_only(tmp_path):
    """One track to one new ID changes only that ID in the header."""
    src, dst = tmp_path / 'in.bik', tmp_path / 'out.bik'
    _bink(src, [(k, p[:1], v) for k, p, v in FRAMES])
    retrack(src, dst, (5,))
    before, after = src.read_bytes(), dst.read_bytes()
    assert track_ids(dst) == (5,) and len(before) == len(after)
    assert [i for i in range(len(before)) if before[i] != after[i]] == [52]


def _source(tmp_path, monkeypatch, masters=''):
    """An export folder whose plugin reads from a Data folder holding a voiced and a silent movie."""
    data, export = tmp_path / 'Data', tmp_path / 'export' / 'Game.esm'
    (data / 'Video' / 'Sub').mkdir(parents=True)
    export.mkdir(parents=True)
    (export / '_HEADER.txt').write_text(masters, encoding='utf-8')
    _bink(data / 'Video' / 'Intro.bik', [(k, p[:1], v) for k, p, v in FRAMES])
    _bink(data / 'Video' / 'Sub' / 'Card.bik', [(k, [], v) for k, _, v in FRAMES])
    monkeypatch.setattr(bink.source_registry, 'directory_for', lambda root, plugin: str(data))
    return export


def test_write_movies_relabels_audio_and_copies_silent_ones(tmp_path, monkeypatch):
    """Voiced movies get TRACK_IDS; a silent one is copied; a second run writes nothing."""
    export, out = _source(tmp_path, monkeypatch), tmp_path / 'out'
    assert sorted(bink.source_movies(export)) == ['intro.bik', 'sub\\card.bik']
    assert bink.write_movies(export, out) == 2
    assert track_ids(out / 'Video' / 'Intro.bik') == bink.TRACK_IDS
    assert (out / 'Video' / 'Sub' / 'Card.bik').read_bytes() == (tmp_path / 'Data' / 'Video' / 'Sub' / 'Card.bik').read_bytes()
    assert bink.write_movies(export, out) == 0


def test_dependent_plugin_ships_no_movies(tmp_path, monkeypatch):
    """The shared Video folder belongs to the masterless plugin."""
    export = _source(tmp_path, monkeypatch, 'Master[0]=Game.esm\n')
    assert bink.write_movies(export, tmp_path / 'out') == 0


def _converted(source, movies, target='fallout4', monkeypatch=None):
    """One FNV statement converted with `movies` shipped, on `target`."""
    monkeypatch.setenv('TES4SKYRIM_PAPYRUS_TARGET', target)
    xref = CrossRefGraph()
    xref._is_fallout, xref.movies = True, frozenset(movies)
    return conv_lines(ScriptConverter(xref), source, 'Quest')


def test_playbink_plays_a_shipped_movie_with_its_flags(monkeypatch):
    """FNV's intro call keeps its flags; omitted ones take PlayBink's defaults."""
    out = _converted('PlayBink "FNVIntro.bik" 1 1 0 1', {'fnvintro.bik'}, monkeypatch=monkeypatch)
    assert out == 'Game.PlayBink("FNVIntro.bik", true, true, false, true)'
    out = _converted('PlayBink "1 year later.bik"', {'1 year later.bik'}, monkeypatch=monkeypatch)
    assert out == 'Game.PlayBink("1 year later.bik", false, true, true, true)'


def test_playbink_of_a_missing_movie_is_dropped(monkeypatch):
    """A movie the build does not ship would hang Fallout 4; Skyrim keeps its note row."""
    out = _converted('PlayBink "FNVLogo1.bik" 0 0 0 1', {'fnvintro.bik'}, monkeypatch=monkeypatch)
    assert 'Game.PlayBink' not in out and 'movie not shipped' in out
    assert 'Game.PlayBink' not in _converted('PlayBink "FNVIntro.bik"', {'fnvintro.bik'}, 'skyrim', monkeypatch)
