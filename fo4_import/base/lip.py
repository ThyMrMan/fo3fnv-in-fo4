"""FO3/FNV .lip files as Fallout 4 .lip files: the same container, a wider frame.

See: docs/fork/research/lip_format.md#conversion
"""

import re
import struct

import numpy as np

#: FO3/FNV mouth shapes per frame (Aah ... W); Fallout 4's first 16 targets are the same, in the same order.
MOUTH_SHAPES = 16
#: Modifiers per frame in both games (blinks, brows, eye look, squint, head pitch/roll/yaw).
MODIFIERS = 17
#: Fallout 4's targets per frame, as LipGenerator writes them.
FO4_TARGETS = 43
#: Flags LipGenerator writes on a Fallout 4 lip (bit 0: compressed body).
FO4_FLAGS = 13
#: The header's size field is the body's length plus this, in every lip of both games.
SIZE_PAD = 16
#: Lip frames per second (both games).
FPS = 30
#: A loudness lip: frames quieter than GATE of the line's loud level stay shut; the loudest open Aah to OPEN.
GATE, OPEN = 0.15, 0.8


#: A run of zero bytes as one compressed marker holds it (u16 count).
_ZERO_RUN = re.compile(rb'\x00{1,65535}')


def inflate(data: bytes) -> bytes:
    """The body with its zero runs (00 + u16 count) expanded."""
    out, i = bytearray(), 0
    while (zero := data.find(b'\0', i)) >= 0:
        out += data[i:zero] + bytes(struct.unpack_from('<H', data, zero + 1)[0])
        i = zero + 3
    return bytes(out + data[i:])


def deflate(body: bytes) -> bytes:
    """`body` with each zero run (at most 0xFFFF bytes) written as 00 + u16 count."""
    return _ZERO_RUN.sub(lambda run: b'\0' + struct.pack('<H', len(run.group())), body)


def fnv_frames(lip: bytes) -> tuple:
    """(start offset, frames x 16 mouth shapes, frames x 17 modifiers) of an FO3/FNV lip.
    See: docs/fork/research/lip_format.md#body
    """
    version, _, flags = struct.unpack_from('<III', lip)
    if version != 1:
        raise ValueError(f'lip version {version}')
    body = inflate(lip[12:]) if flags & 1 else lip[12:]
    frames, offset = struct.unpack_from('<Ii', body)
    grid = np.frombuffer(body, '<f4', frames * (MOUTH_SHAPES + MODIFIERS), 8)
    grid = grid.reshape(frames, MOUTH_SHAPES + MODIFIERS)
    return offset, grid[:, :MOUTH_SHAPES], grid[:, MOUTH_SHAPES:]


def fo4_lip(offset: int, shapes: np.ndarray, modifiers: np.ndarray) -> bytes:
    """A Fallout 4 lip as LipGenerator writes it: `shapes` in targets 0-15, the rest zero, then `modifiers`."""
    grid = np.zeros((len(shapes), FO4_TARGETS + MODIFIERS), '<f4')
    grid[:, :MOUTH_SHAPES] = shapes
    grid[:, FO4_TARGETS:] = modifiers
    body = struct.pack('<IiI', len(shapes), offset, FO4_TARGETS) + grid.tobytes()
    return struct.pack('<III', 1, len(body) + SIZE_PAD, FO4_FLAGS) + deflate(body)


def from_loudness(samples: np.ndarray, rate: int) -> bytes:
    """A Fallout 4 lip opening the mouth (Aah) with the loudness of mono `samples` (floats) at `rate` Hz: each
    frame's RMS over the line's 95th percentile, quiet frames shut, three frames averaged.
    See: docs/fork/fo4_ck_replacements.md#lips
    """
    frames = max(1, -(-len(samples) * FPS // rate))
    starts = np.arange(frames) * rate // FPS
    padded = np.zeros(max(len(samples), starts[-1] + 1), np.float32)
    padded[:len(samples)] = samples
    sizes = np.diff(np.append(starts, len(padded)))
    rms = np.sqrt(np.add.reduceat(np.square(padded), starts) / sizes)
    level = np.clip(rms / (np.percentile(rms, 95) or 1.0), 0, 1)
    level[level < GATE] = 0
    shapes = np.zeros((frames, MOUTH_SHAPES), np.float32)
    shapes[:, 0] = np.convolve(level, np.ones(3) / 3, 'same') * OPEN
    return fo4_lip(0, shapes, np.zeros((frames, MODIFIERS), np.float32))


def from_fnv(lip: bytes) -> bytes:
    """An FO3/FNV lip as a Fallout 4 lip."""
    return fo4_lip(*fnv_frames(lip))


def fuz_lip(fuz: bytes) -> bytes:
    """The lip bytes of a .fuz (FUZE, u32 version, u32 lip size, lip, audio)."""
    return fuz[12:12 + struct.unpack_from('<I', fuz, 8)[0]]


def with_lip(fuz: bytes, lip: bytes) -> bytes:
    """`fuz` with its lip replaced by `lip`, the audio kept."""
    audio = fuz[12 + struct.unpack_from('<I', fuz, 8)[0]:]
    return fuz[:8] + struct.pack('<I', len(lip)) + lip + audio
