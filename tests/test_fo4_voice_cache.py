"""Converted voice kept in the work cache across output folders, and recordings decoded many to one ffmpeg run.

See: docs/fork/fo4_build_speed.md#voice-cache
"""

import wave
from pathlib import Path

import pytest

from asset_convert.audio import audio_converter as AC
from fo4_import.pipeline import work_cache
from fo4_import.spike import voice


def _wav(path: Path, rate: int, channels: int, frames: int = 2205) -> Path:
    """A 16-bit PCM WAV of `frames` frames of a ramp at `path`."""
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(range(256)) * (frames * channels * 2 // 256) + bytes(frames * channels * 2 % 256))
    return path


def test_a_second_output_folder_reads_the_cache(tmp_path, monkeypatch):
    """A line converted for one output folder is written into a second one from the work cache, with no tool run;
    a changed transcript converts again."""
    monkeypatch.setattr(work_cache, 'CACHE', tmp_path / 'work')
    monkeypatch.setattr(voice, 'decode', lambda recordings, folder, ffmpeg: {})
    monkeypatch.setattr(voice, 'find_ffmpeg', lambda need_decoder: 'ffmpeg')
    runs = []

    def fake_xwm(src, dst, *tools):
        """Write a .fuz stand-in naming the transcript, counting the run."""
        runs.append(tools[-1])
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b'FUZE' + tools[-1].encode())
        return True
    monkeypatch.setattr(voice, 'convert_file_to_xwm', fake_xwm)
    monkeypatch.setattr(voice, 'loudness_lip', lambda rec, ffmpeg: None)
    recording = tmp_path / 'line_00104bee_1.ogg'
    recording.write_bytes(b'ogg')
    lipgen = tmp_path / 'tools'
    (lipgen / 'LipGenerator.exe').parent.mkdir()
    (lipgen / 'LipGenerator.exe').write_bytes(b'')
    first = tmp_path / 'one' / 'Type' / '00000001_1.fuz'
    second = tmp_path / 'two' / 'Type' / '00000001_1.fuz'
    assert voice.convert([(recording, first, 'Hi.')], lipgen) == 1
    assert voice.convert([(recording, second, 'Hi.')], lipgen) == 1
    assert runs == ['Hi.'] and second.read_bytes() == first.read_bytes() == b'FUZEHi.'
    third = tmp_path / 'three' / 'Type' / '00000001_1.fuz'
    assert voice.convert([(recording, third, 'Hello.')], lipgen) == 1
    assert runs == ['Hi.', 'Hello.']


def test_batches_stay_small_enough_to_share_and_to_run():
    """Runs hold at most DECODE_BATCH, fewer when there are few groups for the workers, and fit COMMAND_CHARS."""
    groups = [((Path(f'C:/v/{i}.ogg'), 't'), []) for i in range(100)]
    assert [len(b) for b in voice.batches(groups, 12)] == [9] * 11 + [1]
    assert [len(b) for b in voice.batches(groups, 1)] == [32, 32, 32, 4]
    long = [((Path('C:/' + 'x' * 2000 + f'{i}.ogg'), 't'), []) for i in range(10)]
    assert all(len(b) * (2 * 2010 + voice.ARGUMENT_CHARS) <= voice.COMMAND_CHARS for b in voice.batches(long, 1))


def test_one_ffmpeg_run_decodes_a_batch(tmp_path):
    """Two WAVs of other formats come out mono 44.1 kHz 16-bit from one run; a missing input fails the whole run."""
    ffmpeg = AC.find_ffmpeg()
    if not ffmpeg:
        pytest.skip('needs ffmpeg')
    sources = [_wav(tmp_path / 'a.wav', 22050, 2), _wav(tmp_path / 'b.wav', 48000, 1)]
    out = tmp_path / 'out'
    out.mkdir()
    wavs = voice.decode(sources, out, ffmpeg)
    assert sorted(wavs) == sorted(sources) and all(AC.voice_wav(w) for w in wavs.values())
    assert voice.decode([*sources, tmp_path / 'missing.ogg'], out, ffmpeg) == {}


def test_a_voice_format_wav_is_copied_not_decoded(tmp_path):
    """decode_to_wav copies a WAV already in WAV_FORMAT, with no ffmpeg."""
    source = _wav(tmp_path / 'line.wav', AC.WAV_RATE, 1)
    assert AC.decode_to_wav(source, tmp_path / 'copy.wav', 'no-ffmpeg-here')
    assert (tmp_path / 'copy.wav').read_bytes() == source.read_bytes()
