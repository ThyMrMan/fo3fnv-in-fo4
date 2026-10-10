"""Spike 1 voice: the FNV recordings of the plugin's NPC lines as FO4 .fuz files with lip sync.

FO4 finds a line at Sound/Voice/<plugin>/<voice type>/<INFO id, load-order byte 0>_<n>.fuz,
by the speaker's voice type. Each speaker maps its FNV voice folder to its
stand-in's FO4 voice type; a line gets a file under every stand-in whose FNV
folder recorded it. Audio and lips come from the FO4 Creation Kit's own tools.

See: docs/fork/fo4_spikes.md#spike-1-voice
"""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from asset_convert.audio.audio_converter import SilentSource, convert_file_to_xwm, find_ffmpeg

#: FNV voice file name: <quest>_<topic>_<INFO id>_<response number>.ogg.
_FILE_RE = re.compile(r'_([0-9a-f]{8})_(\d+)\.ogg$', re.I)
#: Bracketed tags in response text ([SUCCEEDED], [Medicine 30]) are shown, not spoken.
_TAG_RE = re.compile(r'\[[^\]]*\]')


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


def remove_stale(job_list: list, folders: list) -> int:
    """Delete the .fuz files in `folders` no job writes; how many.

    A line that is gone, or moved to another voice type, would otherwise leave its file behind.
    """
    keep = {job[1] for job in job_list}
    stale = [p for folder in folders if folder.is_dir() for p in folder.glob('*.fuz') if p not in keep]
    for path in stale:
        path.unlink()
    return len(stale)


def _convert_one(job: tuple, tools: tuple) -> bool:
    """One recording to .fuz (or .xwm); False when it fails or decodes to silence."""
    try:
        return convert_file_to_xwm(job[0], job[1], *tools, job[2]) and job[1].is_file()
    except SilentSource:
        return False


def convert(job_list: list, lipgen_dir: Path) -> int:
    """Run every job (source, .fuz with a transcript or .xwm without) with the CK's xWMAEncode and LipGenerator;
    return how many files were written."""
    tools = (find_ffmpeg(need_decoder='vorbis'), str(lipgen_dir / 'xWMAEncode.exe'),
             str(lipgen_dir / 'LipGenerator.exe'))
    with ThreadPoolExecutor() as pool:
        return sum(pool.map(lambda job: _convert_one(job, tools), job_list))
