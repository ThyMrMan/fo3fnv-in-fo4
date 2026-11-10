"""What a build left out of each FNV quest, and of each NPC, for the per-quest readiness report.

Each entry is a kind, its owner (the FNV quest's FormID, the NPC's or the package's for a
package) and a detail. The build writes them as JSON beside its other work
files; tools/validate/fo4_quest_readiness.py joins them with the plugin's unfilled
script properties and prints them by quest.

See: docs/fork/fo4_pipeline.md#readiness
"""

import json
from pathlib import Path

#: Entry kinds.
LINE, LINE_LEFT_OUT, CHOICE_UNANSWERED, TARGET_NOT_BUILT, PACKAGE_LEFT_OUT = (
    'line', 'line left out', 'choice without a line', 'objective target not built', 'package left out')
#: Where a build's entries go, by plugin name.
FOLDER = Path(__file__).resolve().parents[2] / 'temp' / 'fo4_readiness'


class Readiness:
    """A build's entries; `add` records one, `write` saves them for the plugin."""

    def __init__(self):
        """No entries yet."""
        self.entries = []

    def add(self, kind: str, owner: str, detail: str = '') -> None:
        """Record one `kind` entry for FNV quest or NPC `owner` (FormID hex)."""
        self.entries.append({'kind': kind, 'owner': owner.upper(), 'detail': detail})

    def write(self, plugin: str) -> Path:
        """Save the entries for `plugin` (its file name); the path written."""
        FOLDER.mkdir(parents=True, exist_ok=True)
        path = report_path(plugin)
        path.write_text(json.dumps(self.entries, indent=0), encoding='utf-8')
        return path


def report_path(plugin: str) -> Path:
    """Where the build of `plugin` (a path or name) wrote its entries."""
    return FOLDER / f'{Path(plugin).stem}.json'
