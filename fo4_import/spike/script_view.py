"""What a build's record stages take from its converted scripts, kept as one digest per script folder.

The scripts part (script conversion and compile) can run again without the records (part_replay) only when every
converted script still shows the record stages what it showed the build: the same names, and for each script its
first line, properties, stage fragments, the topics it says when free and the quests it starts or writes. A
record stage that reads a converted script's text takes only what view() holds; READERS lists those modules, and
tests/test_fo4_part_replay.py fails when another module reads a .psc.

See: docs/fork/fo4_plugin_layout.md#scripts-replay
"""

import hashlib
import json
from pathlib import Path

from fo4_import.base.file_stamps import Stamps
from fo4_import.spike.quest_scope import STARTS
from fo4_import.spike.say_topics import SAY_FREE
from fo4_import.spike.script import STAGE, declared_properties, stage_fragments

#: The modules (repo paths) whose code reads a converted script's text; record stages among them take only view().
READERS = frozenset(f'fo4_import/spike/{name}.py' for name in (
    'attach', 'equipment', 'packages', 'quest', 'quest_scope', 'say_topics', 'script', 'script_overrides',
    'script_view'))


def view(text: str) -> list:
    """What the record stages read from one converted script (`text`): its first line, properties, stage
    fragments, the topics it says when free, the quests it starts or writes."""
    return [text.split('\n', 1)[0].strip(), declared_properties(text), stage_fragments(text),
            sorted({m.group(1).lower() for m in SAY_FREE.finditer(text)}),
            sorted({name for m in STARTS.finditer(text) for name in m.groups() if name})]


def _digest(path: Path) -> str:
    """The SHA-1 of `path`'s view()."""
    return hashlib.sha1(json.dumps(view(path.read_text(encoding='utf-8', errors='replace'))).encode()).hexdigest()


def folder_digest(folder: Path) -> str:
    """A SHA-1 over each converted script in `folder` (by name) and its view(); '' when it is no folder. Each
    script's view is kept between runs by file stamp."""
    if not Path(folder).is_dir():
        return ''
    stamps = Stamps(STAGE / f'views_{hashlib.sha1(str(Path(folder).resolve()).lower().encode()).hexdigest()[:12]}.json')
    whole = hashlib.sha1()
    for path in sorted(Path(folder).glob('*.psc'), key=lambda p: p.name.lower()):
        whole.update(f'{path.name.lower()}={stamps.value(path, _digest)};'.encode())
    stamps.save()
    return whole.hexdigest()


def digests(folders: list) -> dict:
    """{folder: folder_digest} of `folders` (a build's converted scripts, then its masters')."""
    return {str(folder): folder_digest(Path(folder)) for folder in folders}
