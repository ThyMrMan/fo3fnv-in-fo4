"""FNV .kf clips decoded once (kf_decode.decode_kf): kept in the work cache by the file's bytes, and in memory for
the clips decoded most recently this run, since one gun's clips read the same aim clip several times. Each call
gets fresh copies, as callers change the clips they are given (split_root_motion works in place).

See: docs/fork/fo4_pipeline.md#clip-cache
"""

import functools
import pickle
from pathlib import Path

from asset_convert.havok import kf_decode
from asset_convert.havok.kf_decode import DEFAULT_FPS, decode_kf, split_root_motion
from fo4_import.pipeline.work_cache import cached

#: Decoded .kf files kept in memory (pickled), most recently used first.
IN_MEMORY = 256


@functools.lru_cache(maxsize=IN_MEMORY)
def _pickled(path: str, fps: float) -> bytes:
    """decode_kf(`path`, `fps`) pickled, through the work cache."""
    clips = cached('kf', kf_decode.__name__, (Path(path).read_bytes(), fps), lambda: decode_kf(path, fps))
    return pickle.dumps(clips)


def decoded(path, fps: float = DEFAULT_FPS) -> list:
    """decode_kf(`path`, `fps`): fresh copies of the .kf's clips."""
    return pickle.loads(_pickled(str(path), float(fps)))


def decoded_clip(path, fps: float = DEFAULT_FPS, extract_motion: bool = True) -> tuple:
    """hkx_anim.decode_clip(`path`, `fps`, `extract_motion`) through decoded(): (first clip, its root motion or
    None)."""
    clips = decoded(path, fps)
    if not clips:
        raise ValueError(f'no NiControllerSequence in {path}')
    return clips[0], split_root_motion(clips[0]) if extract_motion else None
