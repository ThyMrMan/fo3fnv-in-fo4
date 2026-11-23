"""This project's release: its own `f3nv-<major>.<minor>` tags, apart from the Skyrim fork's numbered tags that a
clone with both remotes also holds. A release download reads it from VERSION (git fills it with the tag while making
the archive); a checkout asks git for the nearest `f3nv-` tag.

See: docs/fork/fo4_plan_release.md#release-identity
"""

import subprocess
from functools import cache
from pathlib import Path

from core.subprocess_flags import POPEN_FLAGS

ROOT = Path(__file__).resolve().parents[2]
#: The prefix of this project's release tags.
PREFIX = 'f3nv-'
#: What a tree with no release tag (no VERSION tag, no git) reports.
DEV = 'f3nv-dev'


def key(release: str) -> 'tuple | None':
    """`release`'s (major, minor) for ordering, a describe suffix ignored; None when it is not one of our tags."""
    if not release.startswith(PREFIX):
        return None
    numbers = release[len(PREFIX):].split('-', 1)[0].split('.')
    return tuple(map(int, numbers)) if len(numbers) == 2 and all(n.isdigit() for n in numbers) else None


def _from_file() -> str:
    """The tag `git archive` wrote into VERSION ('' in a checkout, where it is still a placeholder)."""
    try:
        text = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    except OSError:
        return ''
    return text if key(text) else ''


def _from_git() -> str:
    """`git describe` against our tags: the tag, or `<tag>-<n>-g<sha>` past it ('' without git or a tag)."""
    try:
        done = subprocess.run(['git', 'describe', '--tags', '--match', PREFIX + '*'], cwd=ROOT, capture_output=True,
                              text=True, **POPEN_FLAGS)
    except OSError:
        return ''
    return done.stdout.strip() if done.returncode == 0 else ''


@cache
def current() -> str:
    """The release this tree is: VERSION's tag, else git's, else DEV."""
    return _from_file() or _from_git() or DEV


def older(built: str) -> bool:
    """Whether release `built` comes before this one (False when either has no number)."""
    then, now = key(built or ''), key(current())
    return bool(then and now and then < now)
