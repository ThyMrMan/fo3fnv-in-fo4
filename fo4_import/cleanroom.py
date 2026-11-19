"""Cleanroom UI (ThyMrMan/cleanroom-ui), the menu framework whose releases the converter ships: where its checkout
is, the commit our copies of its DLLs were built from, and its movies and words built by its own `python -m crui`.

See: docs/fork/spin_offs.md#move
"""

import functools
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS
from fo4_import.base.mxmlc import FLEX, REPO, main_checkout

#: The committed DLLs, ours and Cleanroom UI's.
DIST = REPO / 'tes_runtime' / 'dist'
#: The Cleanroom UI commit the DLLs in DIST were built from.
PIN = DIST / 'cleanroom_ui.txt'
#: Where `python -m crui` writes the plugin, movies and words a build installs.
BUILT = REPO / 'temp' / 'cleanroom_ui'
#: Where the pinned commit's tree is unpacked from the checkout, one folder per commit.
PINNED_TREES = REPO / 'temp' / 'cleanroom_ui_src'
#: Its dialogue release: the DLL (in DIST) and the files of BUILT it installs.
DIALOGUE_DLL = 'CleanroomDialogue.dll'
DIALOGUE_FILES = ('Interface/DialogueMenu.swf', 'Interface/Translations/CleanroomDialogue_*.txt')
#: Its shared plugin, which the helpers stage writes beside FalloutHelpers.esl.
PLUGIN_FILES = ('CleanroomUI.esl',)
#: Its level-up menu's movie and the words of every CleanroomUI movie (F4SE reads them for CleanroomUI.esl).
LEVEL_UP_FILES = ('Interface/CRUI_LevelUp.swf', 'Interface/Translations/CleanroomUI_*.txt')
#: Its HUD host (loaded into the HUD by CleanroomUI.dll), the HUD edit menu, and our MCM page that opens it.
HUD_FILES = ('Interface/CRUI_Hud.swf', 'Interface/CRUI_HudEdit.swf', 'MCM/Config/CleanroomUI/*')
#: Its Papyrus scripts our scripts and its MCM page use, shipped with the static scripts.
SCRIPTS = ('CRUI_Array', 'CRUI_Framework', 'CRUI_Hud', 'CRUI_HudNative', 'CRUI_LevelUp', 'CRUI_LevelUpHolder',
           'CRUI_LevelUpNative',
           'CRUI_LevelUpTable', 'CRUI_Condition', 'CRUI_ItemCard', 'CRUI_Pipboy', 'CRUI_PipboyAmmo',
           'CRUI_PipboyActions', 'CRUI_Sex')
#: Its framework DLL (in DIST), which sends these F4SE external events: a Pip-Boy repair and an ammo choice confirmed.
FRAMEWORK_DLL = 'CleanroomUI.dll'
EVENTS = ('CRUI_ConditionRepair', 'CRUI_AmmoSwitch')


def checkout() -> 'Path | None':
    """Cleanroom UI's checkout: external/cleanroom_ui, else CRUI_HOME, else beside this checkout (or beside the main
    checkout, from a worktree under .claude/worktrees); None when there is none."""
    home = os.environ.get('CRUI_HOME')
    places = [REPO / 'external' / 'cleanroom_ui', *([Path(home)] if home else []), REPO.parent / 'cleanroom_ui',
              main_checkout(REPO).parent / 'cleanroom_ui']
    return next((place for place in places if (place / 'crui' / '__main__.py').is_file()), None)


def pinned() -> str:
    """The commit our copies of Cleanroom UI's DLLs were built from."""
    return PIN.read_text(encoding='utf-8').strip()


def commit(root: Path) -> str:
    """The commit checked out at `root`; '' when git can't say."""
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                            **POPEN_FLAGS)
    return result.stdout.strip() if result.returncode == 0 else ''


@functools.cache
def source() -> 'Path | None':
    """The pinned commit's tree, unpacked from the checkout into PINNED_TREES once; None without a checkout. A build
    reads Cleanroom UI here, never the checkout itself, so what it ships always matches our DLL copies (PIN).

    See: docs/fork/spin_offs.md#move
    """
    root, pin = checkout(), pinned()
    if root is None:
        return None
    tree = PINNED_TREES / pin
    if not (tree / 'crui' / '__main__.py').is_file():
        archive = subprocess.run(['git', '-C', str(root), 'archive', '--format=tar', pin], capture_output=True,
                                 check=True, **POPEN_FLAGS).stdout
        part = tree.with_name(f'{pin}.part')
        shutil.rmtree(part, ignore_errors=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(part, filter='data')
        part.replace(tree)
    return tree


def scripts() -> dict:
    """{`<name>.psc`: path} of SCRIPTS in the pinned tree's papyrus/; FileNotFoundError without a checkout."""
    root = source()
    if root is None:
        raise FileNotFoundError(f'Cleanroom UI checkout needed for its scripts ({", ".join(SCRIPTS)})')
    return {f'{name}.psc': root / 'papyrus' / f'{name}.psc' for name in SCRIPTS}


@functools.cache
def build() -> 'Path | None':
    """Cleanroom UI's plugin, movies, words and MCM page built into BUILT by the pinned tree's `python -m crui` (once per run);
    BUILT, None without a checkout. What failed (no Flex SDK) is printed and left out."""
    root = source()
    if root is None:
        print('Cleanroom UI: no checkout (external/cleanroom_ui, CRUI_HOME, or beside this one)')
        return None
    env = {**os.environ, **({'CRUI_FLEX': str(FLEX)} if FLEX.is_dir() else {})}
    steps = ['plugin', 'movies', 'translations', 'mcm']
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
