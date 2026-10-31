"""Values computed from files, kept between builds while each file's size and modification time stay the same.

A build reads thousands of unchanged sources only to hash or scan them (the
script compile's source and header hashes, the type scan): opening a file
costs about 1.4 ms here, so a rebuild spent minutes on it. `Stamps` keeps
each value in a JSON file beside the work, keyed by path, and reads a file
again only when its stamp changed. This machine's only, like the caches.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import json
from pathlib import Path


class Stamps:
    """{path: value} read from `memo`, reused while a file's [size, mtime_ns] match; save() keeps what was used."""

    def __init__(self, memo: Path):
        """The kept values in `memo` (none when it is missing or unreadable)."""
        self.memo, self.used = Path(memo), {}
        try:
            self.kept = json.loads(self.memo.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.kept = {}

    def value(self, path: Path, read):
        """read(path) (a JSON value), or the kept one when `path`'s stamp is unchanged."""
        stat = Path(path).stat()
        stamp, key = [stat.st_size, stat.st_mtime_ns], str(path).lower()
        entry = self.kept.get(key)
        value = entry[1] if entry and entry[0] == stamp else read(Path(path))
        self.used[key] = [stamp, value]
        return value

    def save(self) -> None:
        """Write the entries used since loading (others are dropped)."""
        self.memo.parent.mkdir(parents=True, exist_ok=True)
        self.memo.write_text(json.dumps(self.used), encoding='utf-8')
