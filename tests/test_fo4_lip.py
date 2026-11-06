"""FO3/FNV .lip files as Fallout 4 .lip files, and the voice stage using them in place of LipGenerator.

See: docs/fork/research/lip_format.md#conversion
"""

import struct
from pathlib import Path

import numpy as np
import pytest

from asset_convert.audio.audio_converter import pack_fuz
from fo4_import.base import lip
from fo4_import.spike import voice

FO4_VOICES = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Fallout 4\Data\Fallout4 - Voices.ba2')


def fnv_lip(offset: int, shapes: np.ndarray, modifiers: np.ndarray) -> bytes:
    """An FO3/FNV lip as shipped: flags 1, 16 shapes + 17 modifiers a frame."""
    body = struct.pack('<Ii', len(shapes), offset) + np.hstack([shapes, modifiers]).astype('<f4').tobytes()
    return struct.pack('<III', 1, len(body) + lip.SIZE_PAD, 1) + lip.deflate(body)


def frames(count: int, seed: int) -> tuple:
    """(mouth shapes, modifiers) with zero gaps, as real lips have."""
    rng = np.random.default_rng(seed)
    shapes = rng.random((count, 16)).astype('<f4') * (rng.random((count, 16)) > 0.7)
    modifiers = rng.random((count, 17)).astype('<f4') * (rng.random((count, 17)) > 0.8)
    return shapes, modifiers


def test_zero_runs_round_trip():
    """Lone zeros, runs over 0xFFFF and zero bytes inside a run's count all come back."""
    body = b'\x01\x00\x02' + bytes(70000) + b'\x03' + bytes(0x100) + b'\x04\x00'
    packed = lip.deflate(body)
    assert lip.inflate(packed) == body
    assert packed[:6] == b'\x01\x00\x01\x00\x02\x00'


def test_fnv_lip_becomes_the_fo4_layout():
    """Same frames and offset; mouth shapes in targets 0-15, targets 16-42 zero, the modifiers after them."""
    shapes, modifiers = frames(40, 1)
    out = lip.from_fnv(fnv_lip(-4, shapes, modifiers))
    version, size, flags = struct.unpack_from('<III', out)
    body = lip.inflate(out[12:])
    count, offset, targets = struct.unpack_from('<IiI', body)
    grid = np.frombuffer(body, '<f4', count * 60, 12).reshape(count, 60)
    assert (version, size, flags, count, offset, targets) == (1, len(body) + 16, 13, 40, -4, 43)
    assert np.array_equal(grid[:, :16], shapes) and not grid[:, 16:43].any()
    assert np.array_equal(grid[:, 43:], modifiers)


@pytest.mark.skipif(not FO4_VOICES.is_file(), reason='Fallout 4 voice archive not installed')
def test_vanilla_lip_bodies_round_trip():
    """Vanilla Fallout 4 compressed lips inflate and deflate back to the same bytes."""
    from fo4_import.base.ba2 import Archive
    arc = Archive(FO4_VOICES)
    names = [k for k in arc.entries if k.endswith('.fuz')][::5000]
    lips = [lip.fuz_lip(arc.read(name)) for name in names]
    lips = [one for one in lips if one[:4] == b'\x01\0\0\0' and struct.unpack_from('<I', one, 8)[0] & 1]
    assert lips
    assert all(lip.deflate(lip.inflate(one[12:])) == one[12:] for one in lips)


def test_a_recording_with_its_own_lip_skips_lipgenerator(tmp_path, monkeypatch):
    """The .fuz holds the recording's own lip, converted; LipGenerator is never handed the job."""
    recording = tmp_path / 'line_00104bee_1.ogg'
    recording.write_bytes(b'ogg')
    shapes, modifiers = frames(10, 2)
    recording.with_suffix('.lip').write_bytes(fnv_lip(-3, shapes, modifiers))
    calls = []

    def fake_xwm(src, dst, *tools):
        """Write an audio stand-in, recording the tools passed."""
        calls.append(tools)
        Path(dst).write_bytes(b'XWMA')
        return True
    monkeypatch.setattr(voice, 'convert_file_to_xwm', fake_xwm)
    dest = tmp_path / 'out' / 'Type' / '00000001_1.fuz'
    dest.parent.mkdir(parents=True)
    assert voice._convert_shared((recording, 'Hi.'), [dest], ('ffmpeg', 'xwma', 'lipgen')) == 1
    assert calls == [('ffmpeg', 'xwma')]
    assert dest.read_bytes() == pack_fuz(lip.fo4_lip(-3, shapes, modifiers), b'XWMA')
    assert not dest.with_suffix('.xwm').exists()


def test_built_lips_are_redone_once(tmp_path):
    """A .fuz from LipGenerator gets the recording's own lip on the first build stamped, not again after."""
    recording = tmp_path / 'line_00104bee_1.ogg'
    shapes, modifiers = frames(8, 3)
    recording.with_suffix('.lip').write_bytes(fnv_lip(-2, shapes, modifiers))
    dest = tmp_path / 'Type' / '00000001_1.fuz'
    dest.parent.mkdir()
    dest.write_bytes(pack_fuz(b'old lip', b'AUDIO'))
    stamp = tmp_path / 'VoiceLips' / 'X.esm.txt'
    jobs = [(recording, dest, 'Hi.')]
    assert voice.relip_once(jobs, stamp) == 1
    assert dest.read_bytes() == pack_fuz(lip.fo4_lip(-2, shapes, modifiers), b'AUDIO')
    dest.write_bytes(pack_fuz(b'old lip', b'AUDIO'))
    assert voice.relip_once(jobs, stamp) == 0


def test_restored_files_get_their_own_lip(tmp_path):
    """A .fuz brought back from the voice cache is relipped as it returns."""
    recording = tmp_path / 'line_00104bee_1.ogg'
    shapes, modifiers = frames(5, 4)
    recording.with_suffix('.lip').write_bytes(fnv_lip(-1, shapes, modifiers))
    dest = tmp_path / 'Voice' / 'Type' / '00000001_1.fuz'
    cache = tmp_path / 'VoiceCache'
    (cache / 'Type').mkdir(parents=True)
    (cache / 'Type' / dest.name).write_bytes(pack_fuz(b'old lip', b'AUDIO'))
    assert voice.restore([(recording, dest, 'Hi.')], cache) == 1
    assert lip.fuz_lip(dest.read_bytes()) == lip.fo4_lip(-1, shapes, modifiers)
