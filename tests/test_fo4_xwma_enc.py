"""Our xWMA encoder (native/src/xwma): the layout Microsoft's decoder plays, and only the measured setup."""

import struct
import subprocess
import wave

import numpy as np
import pytest

from asset_convert.audio.audio_converter import convert_file_to_xwm
from asset_convert.paths import XWMA_ENC

pytestmark = pytest.mark.skipif(not XWMA_ENC.is_file(), reason='native/dist xwma_enc not built')


def tone(path, rate: int = 44100, channels: int = 1) -> None:
    """Half a second of a 440 Hz tone as 16-bit PCM WAV."""
    t = np.arange(rate // 2) / rate
    samples = (np.sin(2 * np.pi * 440 * t) * 12000).astype('<i2')
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(np.repeat(samples, channels).tobytes())


def chunks(data: bytes) -> dict:
    """{chunk id: body} of a RIFF file."""
    out, at = {}, 12
    while at + 8 <= len(data):
        cid, size = data[at:at + 4], struct.unpack_from('<I', data, at + 4)[0]
        out[cid] = data[at + 8:at + 8 + size]
        at += 8 + size + (size & 1)
    return out


def test_voice_setup_writes_xwma(tmp_path):
    """Mono 44.1 kHz at 48 kbps: RIFF XWMA, format 0x161, 2230-byte packets, one dpds entry per packet."""
    tone(tmp_path / 'in.wav')
    done = subprocess.run([str(XWMA_ENC), '-b', '48000', str(tmp_path / 'in.wav'), str(tmp_path / 'out.xwm')],
                          capture_output=True)
    assert done.returncode == 0, done.stderr
    data = (tmp_path / 'out.xwm').read_bytes()
    assert data[:4] == b'RIFF' and data[8:12] == b'XWMA'
    parts = chunks(data)
    tag, channels, rate, byte_rate, block = struct.unpack_from('<HHIIH', parts[b'fmt '])
    assert (tag, channels, rate, byte_rate, block) == (0x161, 1, 44100, 6000, 2230)
    packets = len(parts[b'data']) // block
    dpds = struct.unpack(f'<{len(parts[b"dpds"]) // 4}I', parts[b'dpds'])
    assert len(parts[b'data']) % block == 0 and len(dpds) == packets
    assert list(dpds) == sorted(dpds) and dpds[-1] >= 2 * 44100 // 2


@pytest.mark.parametrize('rate, channels, bits', [(44100, 1, '64000'), (22050, 1, '48000'), (44100, 2, '48000')])
def test_unmeasured_setup_refused(tmp_path, rate, channels, bits):
    """A setup whose packet size xWMAEncode was never measured at fails with a message and writes nothing."""
    tone(tmp_path / 'in.wav', rate, channels)
    done = subprocess.run([str(XWMA_ENC), '-b', bits, str(tmp_path / 'in.wav'), str(tmp_path / 'out.xwm')],
                          capture_output=True)
    assert done.returncode == 1 and b'unsupported' in done.stderr
    assert not (tmp_path / 'out.xwm').exists()


def test_voice_conversion_runs_it(tmp_path):
    """convert_file_to_xwm drives it with xWMAEncode's arguments."""
    tone(tmp_path / 'in.wav')
    assert convert_file_to_xwm(tmp_path / 'in.wav', tmp_path / 'line.xwm', 'ffmpeg', str(XWMA_ENC))
    assert (tmp_path / 'line.xwm').read_bytes()[8:12] == b'XWMA'
