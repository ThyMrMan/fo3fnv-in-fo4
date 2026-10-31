"""Spike 1 voice: the FNV recordings of the plugin's NPC lines as FO4 .fuz files with lip sync.

FO4 finds a line at Sound/Voice/<plugin>/<voice type>/<INFO id, load-order byte 0>_<n>.fuz,
by the speaker's voice type. Each speaker maps its FNV voice folder to its
stand-in's FO4 voice type; a line gets a file under every stand-in whose FNV
folder recorded it. Audio and lips come from the FO4 Creation Kit's own tools.

See: docs/fork/fo4_spikes.md#spike-1-voice
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from asset_convert.audio.audio_converter import SilentSource, convert_file_to_xwm, find_ffmpeg

#: FNV voice file name: <quest>_<topic>_<INFO id>_<response number>.ogg.
_FILE_RE = re.compile(r'_([0-9a-f]{8})_(\d+)\.ogg$', re.I)
#: Bracketed tags in response text ([SUCCEEDED], [Medicine 30]) are shown, not spoken.
_TAG_RE = re.compile(r'\[[^\]]*\]')
#: The player's voice types (Fallout4.esm), whose folders hold lines the player says.
PLAYER_VOICES = ('PlayerVoiceMale01', 'PlayerVoiceFemale01')
#: Seconds a silent line's recording lasts, and its sample rate (as converted voice).
SILENT_SECONDS, SILENT_RATE = 0.2, 44100


def fnv_folder(export_dir: Path, voice_type: str) -> Path:
    """The export's recordings folder of FNV voice type EditorID `voice_type`."""
    return export_dir / 'sound' / 'voice' / 'falloutnv.esm' / voice_type.lower()


def index_recordings(folder: Path) -> dict:
    """{(INFO id, response number): path} for one FNV voice-type folder."""
    out = {}
    for path in folder.glob('*.ogg'):
        m = _FILE_RE.search(path.name)
        if m:
            out[(int(m.group(1), 16), int(m.group(2)))] = path
    return out


def jobs(lines: list, voices: list, data_dir: Path, plugin: str) -> list:
    """(source .ogg, destination .fuz, transcript) for every recorded response of every line.

    lines: (FO4 INFO FormID, FNV INFO record); voices: (FNV voice folder, FO4 voice type EditorID).
    """
    out = []
    for folder, voice_type in voices:
        recorded = index_recordings(folder)
        dest = data_dir / 'Sound' / 'Voice' / plugin / voice_type
        for fid, rec in lines:
            source = int(rec['FormID'], 16)
            for i in range(int(rec.get('ResponseCount', 0) or 0)):
                path = recorded.get((source, int(rec.get(f'Response[{i}].ResponseNumber') or i + 1)))
                if path:
                    text = _TAG_RE.sub('', rec[f'Response[{i}].ResponseText'])
                    out.append((path, dest / f'{fid & 0xFFFFFF:08X}_{i + 1}.fuz', text))
    return out


def silent_recording() -> Path:
    """A SILENT_SECONDS mono 16-bit WAV of silence in the temp folder (written once).
    See: docs/fork/fo4_spikes.md#silent-line
    """
    path = Path(tempfile.gettempdir()) / 'fnv_silent_line.wav'
    if not path.is_file():
        with wave.open(str(path), 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SILENT_RATE)
            out.writeframes(bytes(2 * round(SILENT_SECONDS * SILENT_RATE)))
    return path


def silent_jobs(lines: list, voice_types: list, data_dir: Path, plugin: str) -> list:
    """(silent recording, .xwm, None) jobs for `lines` [(INFO, the player's)] (silent_recording).
    See: docs/fork/fo4_spikes.md#silent-line
    """
    source, root = silent_recording(), data_dir / 'Sound' / 'Voice' / plugin
    return [(source, root / kind / f'{fid & 0xFFFFFF:08X}_1.xwm', None) for fid, player in lines
            for kind in (PLAYER_VOICES if player else voice_types)]


def remove_stale(job_list: list, folders: list, cache: Path) -> int:
    """Move the .fuz files in `folders` no job writes into `cache` (<voice type>/<file>); how many.

    A line that is gone, or whose voice type no built NPC uses, would otherwise be packed; restore() brings
    it back when a later build needs it, saving its LipGenerator run.
    See: docs/fork/fo4_pipeline.md#voice-cache
    """
    keep = {job[1] for job in job_list}
    stale = [p for folder in folders if folder.is_dir() for p in folder.glob('*.fuz') if p not in keep]
    for path in stale:
        target = cache / path.parent.name / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
    return len(stale)


def restore(job_list: list, cache: Path) -> int:
    """Move back from `cache` each job's missing .fuz an earlier remove_stale kept; how many."""
    restored = 0
    for _, dest, _ in job_list:
        kept = cache / dest.parent.name / dest.name
        if not dest.exists() and kept.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(kept, dest)
            restored += 1
    return restored


def _copy_converted(written: Path, first: Path, dest: Path) -> bool:
    """Copy `written` (what converting to `first` wrote: it, or the .xwm left when its lips failed) to `dest` as
    the conversion would have written it; whether `dest` itself was written."""
    target = dest if written == first else dest.with_suffix('.xwm')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(written, target)
    if target.suffix.lower() == '.fuz':
        dest.with_suffix('.xwm').unlink(missing_ok=True)
    return target == dest


def _convert_shared(source: tuple, destinations: list, tools: tuple) -> int:
    """`source` (recording, transcript) converted once to the first of `destinations`, then copied to the rest;
    how many destinations were written (none when it fails or decodes to silence)."""
    first = destinations[0]
    try:
        if not convert_file_to_xwm(source[0], first, *tools, source[1]):
            return 0
    except SilentSource:
        return 0
    fallback = first.with_suffix('.xwm')
    written = fallback if first.suffix.lower() == '.fuz' and fallback.is_file() else first
    return int(written == first) + sum(_copy_converted(written, first, dest) for dest in destinations[1:])


def _attempt(job: tuple) -> str:
    """A job's failure-record key: destination, source and transcript hashes."""
    source, dest, text = job
    return f'{dest.parent.name}/{dest.name}|{hashlib.sha1(Path(source).read_bytes()).hexdigest()}|' + \
        hashlib.sha1((text or '').encode()).hexdigest()


def convert_new(job_list: list, lipgen_dir: Path, record: Path) -> int:
    """convert() of the jobs whose destination is missing, less those an earlier build already failed on with the
    same recording, transcript and destination (`record`, a JSON list); each that fails now is recorded, so a
    recording that never converts (silent, or LipGenerator fails) is not tried again every build.
    See: docs/fork/fo4_plugin_layout.md#stage-times
    """
    failed = set(json.loads(record.read_text(encoding='utf-8'))) if record.is_file() else set()
    missing = [job for job in job_list if not job[1].exists()]
    keys = {id(job): _attempt(job) for job in missing}
    todo = [job for job in missing if keys[id(job)] not in failed]
    written = convert(todo, lipgen_dir) if todo else 0
    now = {keys[id(job)] for job in missing if not job[1].exists()}
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(sorted(now)), encoding='utf-8')
    return written


def convert(job_list: list, lipgen_dir: Path) -> int:
    """Run every job (source, .fuz with a transcript or .xwm without) with the CK's xWMAEncode and LipGenerator,
    each (source, transcript) once to each distinct destination (_convert_shared); how many files were written."""
    tools = (find_ffmpeg(need_decoder='vorbis'), str(lipgen_dir / 'xWMAEncode.exe'),
             str(lipgen_dir / 'LipGenerator.exe'))
    shared = {}
    for source, dest, text in job_list:
        dests = shared.setdefault((source, text), [])
        dests += [] if dest in dests else [dest]
    with ThreadPoolExecutor() as pool:
        return sum(pool.map(lambda item: _convert_shared(*item, tools), shared.items()))
