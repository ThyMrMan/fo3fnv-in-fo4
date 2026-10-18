"""The build's ledger: every generated FormID and stable number a build gave, kept beside the plugin and read back
first by the next build, so a value never moves once given.

A line is `kind`, site, key (its repr) and value (hex), tab-separated: kind `id` is a generated record's object id,
kind `n` a small number (a quest's alias id or marker stage). Lines are sorted, so the file is the same for the same
values. LedgerWriter is the plugin writer that keeps one; it lives here, apart from writer.py, so the caches whose
code tag covers the writer (face fits, through spike.records) do not rerun when the ledger changes.

See: docs/fork/fo4_pipeline.md#formid-ledger
"""

import os
from pathlib import Path

from fo4_import.base.writer import FO4PluginWriter

ID, NUMBER = 'id', 'n'


class Ledger:
    """Values by kind and site, then key repr; read from and saved to `path` (None: nothing is read or kept)."""

    def __init__(self, path: 'Path | None' = None):
        """The ledger at `path`; empty when it has no file yet."""
        self.path, self.sites = (Path(path) if path else None), {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                kind, site, key, value = line.split('\t')
                self.sites.setdefault((kind, site), {})[key] = int(value, 16)

    def get(self, kind: str, site: str, key) -> 'int | None':
        """The value kept for `key` at `site`; None when it has none."""
        return self.sites.get((kind, site), {}).get(repr(key))

    def put(self, kind: str, site: str, key, value: int) -> None:
        """Keep `value` for `key` at `site`."""
        self.sites.setdefault((kind, site), {})[repr(key)] = value

    def pop(self, kind: str, site: str, key) -> 'int | None':
        """The value kept for `key` at `site`, no longer kept; None when it has none."""
        return self.sites.get((kind, site), {}).pop(repr(key), None)

    def values(self, kind: str, site: 'str | None' = None) -> list:
        """Every value of `kind`, or of `kind` at `site`."""
        if site is not None:
            return list(self.sites.get((kind, site), {}).values())
        return [v for (k, _), keys in self.sites.items() if k == kind for v in keys.values()]

    def save(self) -> None:
        """Write the ledger to its path (sorted lines), replacing it whole."""
        if self.path is None:
            return
        lines = sorted(f'{kind}\t{site}\t{key}\t{value:X}' for (kind, site), keys in self.sites.items()
                       for key, value in keys.items())
        partial = self.path.with_name(f'{self.path.name}.{os.getpid()}.tmp')
        partial.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        partial.replace(self.path)


def ledger_path(plugin: Path) -> Path:
    """Where the ledger of `plugin` lives: beside it, `<stem>.formids.tsv`."""
    return Path(plugin).with_suffix('.formids.tsv')


class LedgerWriter(FO4PluginWriter):
    """FO4PluginWriter whose generated FormIDs and stable numbers a Ledger keeps (an empty one until use_ledger)."""

    def __init__(self, *args, **kwargs):
        """FO4PluginWriter's arguments; no ledger file yet."""
        super().__init__(*args, **kwargs)
        self.ledger = Ledger()

    def use_ledger(self, ledger: Ledger) -> None:
        """Keep `ledger`'s ids (reserved) and numbers; call after reserve_source_ids."""
        self.ledger = ledger
        self._derived_taken.update(self.own_index << 24 | oid for oid in ledger.values(ID))

    def derive_formid(self, site: str, key, legacy=None) -> int:
        """The FormID of generated record `key` at `site`: the ledger's for `key`, else the one it kept for `legacy`
        (the key this one replaced; that entry moves to `key`), else the hash of `legacy` or `key`; then kept."""
        if (site, key) in self._derived:
            return self._derived[site, key]
        kept = self.ledger.get(ID, site, key)
        if kept is None and legacy is not None:
            kept = self.ledger.pop(ID, site, legacy)
        fid = self.own_index << 24 | kept if kept is not None else super().derive_formid(
            site, key if legacy is None else legacy)
        self._derived[site, key] = fid
        self.ledger.put(ID, site, key, fid & 0xFFFFFF)
        return fid

    def stable_number(self, site: str, key, make) -> int:
        """The number kept for `key` at `site` (an alias id, a marker stage); else make()'s, then kept."""
        value = self.ledger.get(NUMBER, site, key)
        if value is None:
            value = make()
            self.ledger.put(NUMBER, site, key, value)
        return value
