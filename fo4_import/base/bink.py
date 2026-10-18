"""FO3/FNV movies on Fallout 4: the source Bink 1 files, shipped unconverted with their audio as tracks FO4 plays.

Fallout 4's player reads Bink 1, but plays one audio track ID per movie and
not ID 0, which every FO3/FNV movie uses. `retrack` relabels or repeats the
audio packets without re-encoding. The masterless plugin owns its Data
folder's `Video` (DLCs play movies from the same folder); `source_movies` is
also what the script stage checks a `PlayBink` against, since a missing movie
hangs Fallout 4.

See: docs/fork/bink_movies.md#plan
"""

import os
import shutil
import struct
from pathlib import Path

from core.plugin_masters import masters_from_export_header
from fo4_import.base.source import source_data

#: Audio track IDs written: 1 is English's (played); 2-5 stand for the other four voiced languages (unplayed).
TRACK_IDS = (1, 2, 3, 4, 5)
MOVIE_EXTS = ('.bik',)
#: Bink 1 header: signature, file size - 8, frames, largest frame, frames, width, height, fps, video flags, tracks.
_HEADER = struct.Struct('<4s10I')
BINK1 = (b'BIKf', b'BIKg', b'BIKh', b'BIKi')


def _audio_spans(f, start: int, tracks: int) -> tuple:
    """(end of the first audio packet, end of all audio) of the frame at `start`, relative to it."""
    first, end = 0, 0
    for _ in range(tracks):
        f.seek(start + end)
        end += 4 + struct.unpack('<I', f.read(4))[0]
        first = first or end
    return first, end


def retrack(src: Path, dst: Path, ids: tuple):
    """Write `src` (Bink 1) to `dst` with its first audio track repeated under each of `ids`.

    Each frame starts with one audio packet per track (a 4-byte size, then
    that many bytes) before its video, so the packet is written once per new
    track. The frame index (bit 0 marks a keyframe), file size and largest
    frame are rewritten to match; the video data is unchanged.
    """
    with open(src, 'rb') as f, open(dst, 'wb') as out:
        fields = list(_HEADER.unpack(f.read(_HEADER.size)))
        frames, tracks = fields[2], fields[10]
        if fields[0] not in BINK1 or tracks < 1:
            raise ValueError(f'{src}: not a Bink 1 file with audio')
        table = [f.read(4 * tracks) for _ in range(3)]
        index = struct.unpack(f'<{frames + 1}I', f.read(4 * (frames + 1)))
        track_info = b''.join(t[:4] * len(ids) for t in table[:2]) + struct.pack(f'<{len(ids)}I', *ids)
        pos = _HEADER.size + len(track_info) + 4 * (frames + 1)
        plan, offsets, largest = [], [], 0
        for i in range(frames):
            start, size = index[i] & ~1, (index[i + 1] & ~1) - (index[i] & ~1)
            first, audio = _audio_spans(f, start, tracks)
            plan.append((start, first, audio, size))
            offsets.append(pos | (index[i] & 1))
            new_size = first * len(ids) + size - audio
            pos, largest = pos + new_size, max(largest, new_size)
        fields[1], fields[3], fields[10] = pos - 8, largest, len(ids)
        out.write(_HEADER.pack(*fields) + track_info + struct.pack(f'<{frames + 1}I', *offsets, pos))
        for start, first, audio, size in plan:
            f.seek(start)
            frame = f.read(size)
            out.write(frame[:first] * len(ids) + frame[audio:])


def track_ids(path: Path) -> tuple:
    """The audio track IDs in a Bink 1 file's header (empty for a silent movie)."""
    with open(path, 'rb') as f:
        tracks = _HEADER.unpack(f.read(_HEADER.size))[10]
        f.seek(_HEADER.size + 8 * tracks)
        return struct.unpack(f'<{tracks}I', f.read(4 * tracks))


def movie_key(name: str) -> str:
    """A movie path relative to Data\\Video as one spelling: lowercase, backslashes."""
    return name.replace('/', '\\').lower()


def source_movies(export_dir) -> dict:
    """{movie_key: source file} of the movies in the Data folder `export_dir`'s plugin was read from."""
    data = source_data(export_dir)
    video = data / 'Video' if data else None
    if not video or not video.is_dir():
        return {}
    return {movie_key(str(p.relative_to(video))): p for p in sorted(video.rglob('*'))
            if p.suffix.lower() in MOVIE_EXTS and p.is_file()}


def _wanted_ids(src: Path) -> tuple:
    """The track IDs `src` ships with: TRACK_IDS, or none for a movie without audio."""
    return TRACK_IDS if track_ids(src) else ()


def _current(src: Path, dst: Path) -> bool:
    """Is `dst` already `src` as written: same timestamp and the wanted track IDs?"""
    return dst.is_file() and dst.stat().st_mtime == src.stat().st_mtime and track_ids(dst) == _wanted_ids(src)


def write_movies(export_dir, data_dir: Path) -> int:
    """Write the masterless plugin's source movies into `data_dir`/Video; how many were (re)written."""
    if masters_from_export_header(str(export_dir)):
        return 0
    written = 0
    for key, src in source_movies(export_dir).items():
        dst = Path(data_dir, 'Video', *src.parts[-len(key.split('\\')):])
        if _current(src, dst):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if _wanted_ids(src):
            retrack(src, dst, TRACK_IDS)
        else:
            shutil.copyfile(src, dst)
        os.utime(dst, (src.stat().st_atime, src.stat().st_mtime))
        written += 1
    return written
