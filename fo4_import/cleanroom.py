"""Cleanroom UI (ThyMrMan/cleanroom-ui), the menu framework whose releases the converter ships: where its checkout
is, the commit our copies of its DLLs were built from, and its movies and words built by its own `python -m crui`.

See: docs/fork/spin_offs.md#move
"""

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.mxmlc import FLEX, REPO

#: The committed DLLs, ours and Cleanroom UI's.
DIST = REPO / 'tes_runtime' / 'dist'
#: The Cleanroom UI commit the DLLs in DIST were built from.
PIN = DIST / 'cleanroom_ui.txt'
#: Where `python -m crui` writes the plugin, movies and words a build installs.
BUILT = REPO / 'temp' / 'cleanroom_ui'
#: Its dialogue release: the DLL (in DIST) and the files of BUILT it installs.
DIALOGUE_DLL = 'CleanroomDialogue.dll'
DIALOGUE_FILES = ('Interface/DialogueMenu.swf', 'Interface/Translations/CleanroomDialogue_*.txt')
#: Its shared plugin, which the helpers stage writes beside FalloutHelpers.esl.
PLUGIN_FILES = ('CleanroomUI.esl',)
#: Its level-up menu's movie and the words of every CleanroomUI movie (F4SE reads them for CleanroomUI.esl).
LEVEL_UP_FILES = ('Interface/CRUI_LevelUp.swf', 'Interface/Translations/CleanroomUI_*.txt')
#: Its Papyrus scripts (papyrus/) our scripts use, shipped with the static scripts: level-up, arrays, DLL natives.
SCRIPTS = ('CRUI_Array', 'CRUI_LevelUp', 'CRUI_LevelUpHolder', 'CRUI_LevelUpTable', 'CRUI_Condition', 'CRUI_ItemCard',
           'CRUI_Pipboy', 'CRUI_PipboyAmmo', 'CRUI_Sex')
#: Its framework DLL (in DIST), which sends these F4SE external events: a Pip-Boy repair and an ammo choice confirmed.
FRAMEWORK_DLL = 'CleanroomUI.dll'
EVENTS = ('CRUI_ConditionRepair', 'CRUI_AmmoSwitch')


def checkout() -> 'Path | None':
    """Cleanroom UI's checkout: external/cleanroom_ui, else CRUI_HOME, else beside this checkout (or beside the main
    checkout, from a worktree under .claude/worktrees); None when there is none."""
    home = os.environ.get('CRUI_HOME')
    places = [REPO / 'external' / 'cleanroom_ui', *([Path(home)] if home else []), REPO.parent / 'cleanroom_ui',
              REPO.parents[3] / 'cleanroom_ui']
    return next((place for place in places if (place / 'crui' / '__main__.py').is_file()), None)


def pinned() -> str:
    """The commit our copies of Cleanroom UI's DLLs were built from."""
    return PIN.read_text(encoding='utf-8').strip()


def commit(root: Path) -> str:
    """The commit checked out at `root`; '' when git can't say."""
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            **POPEN_FLAGS)
    return result.stdout.strip() if result.returncode == 0 else ''


def scripts() -> dict:
    """{`<name>.psc`: path} of SCRIPTS in the checkout's papyrus/; FileNotFoundError without a checkout."""
    root = checkout()
    if root is None:
        raise FileNotFoundError(f'Cleanroom UI checkout needed for its scripts ({", ".join(SCRIPTS)})')
    return {f'{name}.psc': root / 'papyrus' / f'{name}.psc' for name in SCRIPTS}


@functools.cache
def build() -> 'Path | None':
    """Cleanroom UI's plugin, movies and words built into BUILT by its `python -m crui` (once per run); BUILT, None
    without a checkout. What failed (no Flex SDK) is printed and left out."""
    root = checkout()
    if root is None:
        print('Cleanroom UI: no checkout (external/cleanroom_ui, CRUI_HOME, or beside this one)')
        return None
    env = {**os.environ, **({'CRUI_FLEX': str(FLEX)} if FLEX.is_dir() else {})}
    steps = ['plugin', 'movies', 'translations']
    result = subprocess.run([sys.executable, '-m', 'crui', *steps, '--out', str(BUILT)], cwd=root, env=env,
                            capture_output=True, text=True, **POPEN_FLAGS)
    if result.returncode:
        print(f'Cleanroom UI: python -m crui failed\n{result.stdout}{result.stderr}')
    return BUILT


def install(data_dir: Path, patterns: tuple) -> list:
    """Copy the files of build() matching `patterns` (paths under a data folder, globs allowed) into `data_dir`; the
    copies."""
    built = build()
    copies = []
    for source in (path for pattern in patterns for path in sorted(built.glob(pattern))) if built else ():
        target = Path(data_dir) / source.relative_to(built)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copies.append(target)
    return copies


def drifted() -> bool:
    """Whether the checkout is at another commit than our DLL copies' (PIN)."""
    root = checkout()
    return root is not None and commit(root) != pinned()
