"""Play test of New Vegas's intro movie (Bink 1) in Fallout 4.

Fallout 4's `bink2w64.dll` accepts Bink 1 headers, so the source `.bik` may
play unconverted. The open question is its audio: Fallout 4 plays exactly
one audio track ID (`BinkSetSoundTrack(1, &id)`), vanilla `.bk2` files carry
IDs 1-5, and FNVIntro.bik has one track with ID 0. The test writes three
copies of the movie into a mod folder, differing only in their track IDs,
and a plugin whose quest plays each one from the console
(`cqf FNVSpike_BinkTest <function>`), logging to Logs/Script/User/FNVBinkTest.0.log.

Usage: py -3.14 -m fo4_import.spike.bink --out "<MO2 mods>/FNV Bink Test"

See: docs/fork/bink_movies.md#play-test
"""

import argparse
import shutil
from pathlib import Path

from fo4_import.base.bink import retrack, track_ids
from fo4_import.base.install import FALLOUTNV_ESM
from fo4_import.base.papyrus import compile_folder, header_dirs
from fo4_import.base.support_records import pack_script_quest
from fo4_import.base.vmad import quest_fragments
from fo4_import.base.writer import FO4PluginWriter

FNV_INTRO = FALLOUTNV_ESM.parent / 'Video' / 'FNVIntro.bik'
PLUGIN = 'FNVBinkTest.esp'
SCRIPT = 'FNVSpike_BinkTest'
QUEST = 'FNVSpike_BinkTest'
LOG = 'FNVBinkTest'
#: Movie file -> the audio track IDs it carries; FNVIntro.bik itself is (0,).
VARIANTS = {'FNVIntro_T1.bik': (1,), 'FNVIntro_T0to5.bik': (0, 1, 2, 3, 4, 5)}
#: Console function -> the file it plays. Missing plays a name with no file (FNVLogo1.bik's case).
FUNCTIONS = {'Original': 'FNVIntro.bik', 'Track1': 'FNVIntro_T1.bik', 'AllTracks': 'FNVIntro_T0to5.bik',
             'Missing': 'FNVBinkTest_NoSuchFile.bik'}


def script_source() -> str:
    """The test quest's script: one console function per movie, each logging how long the call blocked."""
    lines = [f'Scriptname {SCRIPT} extends Quest',
             '{Plays New Vegas intro movie variants: cqf ' + QUEST + ' <function>. See docs/fork/bink_movies.md}',
             '', 'Function Play(string asFile)', f'    Debug.OpenUserLog("{LOG}")',
             '    float start = Utility.GetCurrentRealTime()',
             f'    Debug.TraceUser("{LOG}", "start " + asFile)',
             '    Game.PlayBink(asFile, abInterruptible = true, abMuteAudio = true, abMuteMusic = true)',
             f'    Debug.TraceUser("{LOG}", "end " + asFile + " after " + (Utility.GetCurrentRealTime() - start) + " s")',
             'EndFunction']
    for name, movie in FUNCTIONS.items():
        lines += ['', f'Function {name}()', f'    Play("{movie}")', 'EndFunction']
    return '\n'.join(lines) + '\n'


def build(out: Path, source: Path = FNV_INTRO) -> str:
    """Write the movies, plugin and compiled script under mod folder `out`; the compiler's output."""
    video = out / 'Video'
    video.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, video / FUNCTIONS['Original'])
    for name, ids in VARIANTS.items():
        retrack(source, video / name, ids)
    w = FO4PluginWriter(masters=['Fallout4.esm'], is_esm=False, description='FNV Bink play test')
    vmad = quest_fragments('', [], scripts=[(SCRIPT, {}, {})])
    w.add_record('QUST', pack_script_quest(0x01000800, QUEST, vmad))
    w.next_object_id = 0x801
    w.write(str(out / PLUGIN))
    source_dir = out / 'Scripts' / 'Source' / 'User'
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / f'{SCRIPT}.psc').write_text(script_source(), encoding='utf-8')
    return compile_folder(source_dir, out / 'Scripts', f'{header_dirs()};{source_dir}')


def main():
    """Build the test mod and print each movie's track IDs."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True, help='Mod folder to write (Video, Scripts, the plugin)')
    ap.add_argument('--source', default=str(FNV_INTRO), help='Bink 1 movie to test')
    args = ap.parse_args()
    out = Path(args.out)
    print(build(out, Path(args.source)).strip() or 'compiled')
    for movie in sorted((out / 'Video').glob('*.bik')):
        print(f'{movie.name}: {movie.stat().st_size / 1e6:.0f} MB, track IDs {track_ids(movie)}')


if __name__ == '__main__':
    main()
