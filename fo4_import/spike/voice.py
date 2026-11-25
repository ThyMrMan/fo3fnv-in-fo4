"""Spike 1 voice: the FNV recordings of the plugin's NPC lines as FO4 .fuz files with lip sync.

FO4 finds a line at Sound/Voice/<plugin>/<voice type>/<INFO id, load-order byte 0>_<n>.fuz,
by the speaker's voice type. Each speaker maps its FNV voice folder to its
stand-in's FO4 voice type; a line gets a file under every stand-in whose FNV
folder recorded it. Audio comes from our xWMA encoder (native/src/xwma); lips from the recording's own .lip
(lip.from_fnv), else the Creation Kit's LipGenerator, else the recording's loudness (loudness_lip).

See: docs/fork/fo4_spikes.md#spike-1-voice
"""

import functools
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from core.build_resources import profile_cores

from asset_convert.audio.audio_converter import (WAV_FORMAT, SilentSource, convert_file_to_xwm, encode_xwm,
                                                  find_ffmpeg, has_samples, pack_fuz)
from asset_convert.paths import XWMA_ENC
from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base import lip
from fo4_import.base.source import asset_dirs, plugin_name
from fo4_import.pipeline.export_index import export_masters
from fo4_import.pipeline.stage_timer import counted
from fo4_import.pipeline.work_cache import lookup_versioned, store_versioned

#: FNV voice file name: <quest>_<topic>_<INFO id>_<response number>.ogg.
_FILE_RE = re.compile(r'_([0-9a-f]{8})_(\d+)\.ogg$', re.I)
#: Bracketed tags in response text ([SUCCEEDED], [Medicine 30]) are shown, not spoken.
_TAG_RE = re.compile(r'\[[^\]]*\]')
#: The player's voice types (Fallout4.esm), whose folders hold lines the player says.
PLAYER_VOICES = ('PlayerVoiceMale01', 'PlayerVoiceFemale01')
#: Seconds a silent line's recording lasts, and its sample rate (as converted voice).
SILENT_SECONDS, SILENT_RATE = 0.2, 44100
#: How built .fuz lips are made; a staging root stamped with another value has its lips redone (relip_once).
LIP_SCHEME = 'fnv-lip-1'
#: Failed-job keys carry this, so lines an older build left lipless (.xwm) are tried once with the loudness lip.
LIP_FALLBACK = 'loudness-1'
#: Sample rate a recording is decoded at for its loudness lip.
LOUDNESS_RATE = 16000
#: Work-cache site of converted voice files, and its version: bump it when a converted file's bytes change.
VOICE_SITE, VOICE_VERSION = 'voice_file', 2
#: Recordings one ffmpeg run decodes at most; its command line's length bound (Windows: 32,767); seconds it may take.
DECODE_BATCH, COMMAND_CHARS, DECODE_TIMEOUT = 32, 24000, 600
#: Command-line characters one recording's decode needs beyond its paths (its -i, -map and output options).
ARGUMENT_CHARS = 80


def fnv_folders(export_dir: Path, voice_type: str) -> tuple:
    """`voice_type`'s recordings folder in each export plugin, in master-byte order.
    See: docs/fork/fo4_plugin_layout.md#dlc-voice
    """
    return tuple(root / voice_type.lower() for root in _voice_roots(str(export_dir)))


@functools.cache
def _voice_roots(export_dir: str) -> tuple:
    """Each export plugin's sound/voice/<plugin> folder, master-byte order.
    See: docs/fork/fo4_build_speed.md#staged-first
    """
    plugins = (*map(Path, export_masters(export_dir)), Path(export_dir))
    return tuple(asset_dirs(p)[-1] / 'sound' / 'voice' / plugin_name(p).lower() for p in plugins)


def recorded(folders: tuple) -> bool:
    """Whether any of fnv_folders()'s `folders` exists."""
    return any(folder.is_dir() for folder in folders)


def index_recordings(folders: tuple) -> dict:
    """{(FNV INFO FormID, response number): path} over fnv_folders()'s `folders`, each folder's index its
    master byte (a file names its INFO with byte 0)."""
    out = {}
    for byte, folder in enumerate(folders):
        for path in folder.glob('*.ogg'):
            m = _FILE_RE.search(path.name)
            if m:
                out[(byte << 24 | int(m.group(1), 16) & 0xFFFFFF, int(m.group(2)))] = path
    return out


def own_lines(lines: list, own: int) -> list:
    """The `lines` [(FO4 INFO FormID, ...)] whose INFO has load byte `own`.
    See: docs/fork/fo4_plugin_layout.md#dlc-voice
    """
    return [line for line in lines if line[0] >> 24 == own]


def jobs(lines: list, voices: list, data_dir: Path, plugin: str) -> list:
    """(source .ogg, destination .fuz, transcript) for every recorded response of every line.

    lines: (FO4 INFO FormID, FNV INFO record); voices: (fnv_folders(), FO4 voice type EditorID).
    """
    out = []
    for folders, voice_type in voices:
        found = index_recordings(folders)
        dest = data_dir / 'Sound' / 'Voice' / plugin / voice_type
        for fid, rec in lines:
            source = int(rec['FormID'], 16)
            for i in range(int(rec.get('ResponseCount', 0) or 0)):
                path = found.get((source, int(rec.get(f'Response[{i}].ResponseNumber') or i + 1)))
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
    """Move the .fuz and silent .xwm files in `folders` no job writes into `cache` (<voice type>/<file>); how many.

    A line that is gone, or whose voice type no built NPC uses, would otherwise be packed; restore() brings
    it back when a later build needs it, saving its LipGenerator run.
    See: docs/fork/fo4_pipeline.md#voice-cache
    """
    keep = {job[1] for job in job_list}
    stale = [p for folder in folders if folder.is_dir() for p in folder.iterdir()
             if p.suffix.lower() in ('.fuz', '.xwm') and p not in keep]
    for path in stale:
        target = cache / path.parent.name / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, target)
    return len(stale)


def restore(job_list: list, cache: Path) -> int:
    """Move back from `cache` each job's missing .fuz an earlier remove_stale kept, its lip redone (relip); how
    many."""
    restored = []
    for job in job_list:
        dest = job[1]
        kept = cache / dest.parent.name / dest.name
        if not dest.exists() and kept.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(kept, dest)
            restored.append(job)
    relip(restored)
    return len(restored)


def own_lip(recording: Path) -> 'bytes | None':
    """The Fallout 4 lip of `recording`'s own .lip beside it (lip.from_fnv), or None when it has none.
    See: docs/fork/research/lip_format.md#conversion
    """
    path = Path(recording).with_suffix('.lip')
    try:
        return lip.from_fnv(path.read_bytes()) if path.is_file() else None
    except (ValueError, struct.error):
        return None


def relip(job_list: list) -> int:
    """Give each job's built .fuz its recording's own lip (own_lip) where it holds another; how many changed."""
    changed = 0
    for source, dest, _ in job_list:
        made = own_lip(source) if dest.suffix.lower() == '.fuz' and dest.is_file() else None
        fuz = dest.read_bytes() if made else b''
        if made and lip.fuz_lip(fuz) != made:
            dest.write_bytes(lip.with_lip(fuz, made))
            changed += 1
    return changed


def relip_once(job_list: list, stamp: Path) -> int:
    """relip() every job unless `stamp` already names LIP_SCHEME, then stamp it; how many changed.
    See: docs/fork/research/lip_format.md#conversion
    """
    if stamp.is_file() and stamp.read_text(encoding='utf-8') == LIP_SCHEME:
        return 0
    changed = relip(job_list)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(LIP_SCHEME, encoding='utf-8')
    return changed


def _write(made: tuple, destinations: list) -> int:
    """Write `made` (suffix, bytes: a .fuz, or the .xwm left when its lips failed) to each of `destinations` under
    that suffix, a .fuz replacing an .xwm beside it; how many destinations were written as named."""
    suffix, data = made
    for dest in destinations:
        target = dest.with_suffix(suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if suffix == '.fuz':
            dest.with_suffix('.xwm').unlink(missing_ok=True)
    return sum(dest.suffix.lower() == suffix for dest in destinations)


def _digest(path: Path) -> str:
    """SHA-1 of the file at `path`, '' when there is none."""
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else ''


def cache_inputs(source: tuple, first: Path, lipgen: bool) -> tuple:
    """VOICE_SITE inputs of `source` (recording, text) made as `first`'s kind.
    See: docs/fork/fo4_build_speed.md#voice-cache
    """
    recording = Path(source[0])
    return _digest(recording), _digest(recording.with_suffix('.lip')), source[1] or '', first.suffix.lower(), lipgen


def _convert_own_lip(recording: Path, fuz: Path, made: bytes, tools: tuple) -> bool:
    """`recording` as .xwm, packed with its own lip `made` into `fuz`; whether it was written."""
    audio = fuz.with_suffix('.xwm')
    if not convert_file_to_xwm(recording, audio, *tools[:2]):
        return False
    fuz.write_bytes(pack_fuz(made, audio.read_bytes()))
    audio.unlink()
    return True


def loudness_lip(recording: Path, ffmpeg: str) -> 'bytes | None':
    """A lip of `recording` from its loudness (lip.from_loudness), decoded by `ffmpeg`; None when it can't decode."""
    try:
        done = subprocess.run([ffmpeg, '-v', 'error', '-i', str(recording), '-ac', '1', '-ar', str(LOUDNESS_RATE),
                               '-f', 's16le', '-'], capture_output=True, timeout=60, **POPEN_FLAGS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode or not done.stdout:
        return None
    return lip.from_loudness(np.frombuffer(done.stdout, '<i2').astype(np.float32) / 32768, LOUDNESS_RATE)


def _convert_one(source: tuple, first: Path, tools: tuple, wav: 'Path | None' = None) -> bool:
    """`source` (recording, transcript) converted to `first` (read from its decoded `wav` when given), with the
    recording's own lip when it has one, else LipGenerator's when it is installed and works, else one from its
    loudness (loudness_lip)."""
    audio_in = wav or source[0]
    made = own_lip(source[0]) if first.suffix.lower() == '.fuz' else None
    if made:
        return _convert_own_lip(audio_in, first, made, tools)
    lipgen = tools[2] if Path(tools[2]).is_file() else None
    if not convert_file_to_xwm(audio_in, first, tools[0], tools[1], lipgen, source[1]):
        return False
    audio = first.with_suffix('.xwm')
    made = loudness_lip(source[0], tools[0]) if first.suffix.lower() == '.fuz' and audio.is_file() else None
    if made:
        first.write_bytes(pack_fuz(made, audio.read_bytes()))
        audio.unlink()
    return True


def _made(source: tuple, first: Path, tools: tuple, wav: 'Path | None') -> 'tuple | None':
    """(suffix, bytes) of `source` converted to `first` (_convert_one): the .fuz, or the .xwm left when its lips
    failed; None when it fails or decodes to silence."""
    try:
        if not _convert_one(source, first, tools, wav):
            return None
    except SilentSource:
        return None
    fallback = first.with_suffix('.xwm')
    written = fallback if first.suffix.lower() == '.fuz' and fallback.is_file() else first
    return written.suffix.lower(), written.read_bytes()


def _keep(key: tuple, made: tuple, destinations: list) -> int:
    """Keep `made` under VOICE_SITE `key`, then _write it to `destinations`."""
    store_versioned(VOICE_SITE, VOICE_VERSION, key, made)
    return _write(made, destinations)


def _convert_shared(source: tuple, destinations: list, tools: tuple, key: tuple, wav: 'Path | None' = None) -> int:
    """_made `source` once, _keep it under `key` to `destinations`; how many."""
    made = _made(source, destinations[0], tools, wav)
    return 0 if made is None else _keep(key, made, destinations)


def _from_cache(key: tuple, destinations: list) -> 'int | None':
    """Files _write wrote from the VOICE_SITE entry `key`; None without one."""
    made = lookup_versioned(VOICE_SITE, VOICE_VERSION, key)
    return None if made is None else _write(made, destinations)


def decode(recordings: list, folder: Path, ffmpeg: str) -> dict:
    """{recording: its WAV in `folder`} of `recordings`, all decoded to WAV_FORMAT by one ffmpeg run; {} when that
    run fails (each is then decoded alone).
    See: docs/fork/fo4_build_speed.md#voice-batches
    """
    wavs = {path: folder / f'{i}.wav' for i, path in enumerate(dict.fromkeys(recordings))}
    cmd = [ffmpeg, '-v', 'error', '-y', *(a for path in wavs for a in ('-i', str(path)))]
    cmd += [a for i, wav in enumerate(wavs.values()) for a in ('-map', f'{i}:a', *WAV_FORMAT, str(wav))]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=DECODE_TIMEOUT, **POPEN_FLAGS)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return wavs if done.returncode == 0 and all(wav.is_file() for wav in wavs.values()) else {}


def batches(groups: list, workers: int) -> list:
    """`groups` [(source, destinations)] cut into runs of at most DECODE_BATCH (fewer when that keeps `workers`
    busy), each run's recordings naming under COMMAND_CHARS of command line."""
    size = max(1, min(DECODE_BATCH, -(-len(groups) // max(1, workers))))
    out, run, chars = [], [], 0
    for group in groups:
        need = 2 * len(str(group[0][0])) + ARGUMENT_CHARS
        if run and (len(run) == size or chars + need > COMMAND_CHARS):
            out.append(run)
            run, chars = [], 0
        run.append(group)
        chars += need
    return out + [run] if run else out


def _batched_lip(source: tuple, first: Path, wav: 'Path | None') -> 'bytes | None':
    """What a batch encode packs `source` with as `first`'s kind, from its decoded `wav`: b'' for an .xwm, its own
    lip for a .fuz; None when it is converted alone (not decoded, no audio, or no lip of its own)."""
    has_audio = wav is not None and has_samples(wav)
    if not has_audio:
        return None
    return b'' if first.suffix.lower() != '.fuz' else own_lip(source[0])


def _convert_batch(batch: list, tools: tuple) -> int:
    """Each of `batch` [(source, destinations, key: cache_inputs)] decoded in one ffmpeg run, and those with a
    _batched_lip encoded in one encoder run and kept; the rest, and any the encoder left, by _convert_shared; how
    many files were written.
    See: docs/fork/fo4_build_speed.md#voice-batches
    """
    with tempfile.TemporaryDirectory(prefix='voice_batch_') as folder:
        folder = Path(folder)
        wavs = decode([s[0] for s, _, _ in batch if Path(s[0]).suffix.lower() != '.wav'], folder, tools[0])
        lips = [_batched_lip(source, dests[0], wavs.get(source[0])) for source, dests, _ in batch]
        plain = [i for i, own in enumerate(lips) if own is not None]
        encoded = encode_xwm(tools[1], [(wavs[batch[i][0][0]], folder / f'{i}.xwm') for i in plain]) if plain else []
        audio = dict(zip(plain, encoded))
        return sum(_finish(item, tools, wavs.get(item[0][0]), lips[i], audio.get(i)) for i, item in enumerate(batch))


def _finish(item: tuple, tools: tuple, wav: 'Path | None', own: 'bytes | None', audio: 'bytes | None') -> int:
    """Files written for `item` (source, destinations, key): its batch-encoded `audio`, packed with `own` lip into a
    .fuz unless that is b'', kept; else _convert_shared from its `wav`."""
    source, destinations, key = item
    if audio is None:
        return _convert_shared(source, destinations, tools, key, wav)
    return _keep(key, ('.fuz', pack_fuz(own, audio)) if own else ('.xwm', audio), destinations)


def _attempt(job: tuple) -> str:
    """A job's failure-record key: destination, source and transcript hashes, and its own lip's when it has one."""
    source, dest, text = job
    own = Path(source).with_suffix('.lip')
    lip_hash = '|' + hashlib.sha1(own.read_bytes()).hexdigest() if own.is_file() else ''
    return f'{LIP_FALLBACK}|{dest.parent.name}/{dest.name}|{hashlib.sha1(Path(source).read_bytes()).hexdigest()}|' \
        + hashlib.sha1((text or '').encode()).hexdigest() + lip_hash


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
    """Run every job (source, .fuz with a transcript or .xwm without) with our xWMA encoder and the CK's
    LipGenerator, each (source, transcript) once to each distinct destination: from the work cache when it keeps
    one (_from_cache), else converted in batches (_convert_batch); how many files were written.
    See: docs/fork/fo4_build_speed.md#voice-cache
    """
    tools = (find_ffmpeg(need_decoder='vorbis'), str(XWMA_ENC), str(lipgen_dir / 'LipGenerator.exe'))
    shared = {}
    for source, dest, text in job_list:
        dests = shared.setdefault((source, text), [])
        dests += [] if dest in dests else [dest]
    lipgen, workers = Path(tools[2]).is_file(), profile_cores()
    with ThreadPoolExecutor(workers) as pool:
        keys = pool.map(lambda item: cache_inputs(item[0], item[1][0], lipgen), shared.items())
        items = [(source, dests, key) for (source, dests), key in zip(shared.items(), keys)]
        kept = list(pool.map(lambda item: _from_cache(item[2], item[1]), items))
        todo = batches([item for item, n in zip(items, kept) if n is None], workers)
        made = sum(counted(pool.map(lambda batch: _convert_batch(batch, tools), todo), len(todo), 'voice batches'))
    return made + sum(n for n in kept if n is not None)
