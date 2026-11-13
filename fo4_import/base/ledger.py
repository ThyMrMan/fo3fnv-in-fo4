"""The build's ledger: every generated FormID and stable number a build gave, kept beside the plugin and read back
first by the next build, so a value never moves once given.

A line is `kind`, site, key (its repr) and value (hex), tab-separated: kind `id` is a generated record's object id,
kind `n` a small number (a quest's alias id or marker stage). Lines are sorted, so the file is the same for the same
values. LedgerWriter is the plugin writer that keeps one; it lives here, apart from writer.py, so the caches whose
code tag covers the writer (face fits, through spike.records) do not rerun when the ledger changes.

See: docs/fork/fo4_pipeline.md#formid-ledger
"""

import hashlib
import os
import struct
from pathlib import Path

from fo4_import.base.build_files import moved_in
from fo4_import.base.writer import FO4PluginWriter
from fo4_import.pipeline.build_inputs import MASTERS

ID, NUMBER = 'id', 'n'
#: A light plugin's own object ids: LIGHT_FIRST up to LIGHT_FIRST + LIGHT_SPAN - 1 (0x001-0xFFF).
LIGHT_FIRST, LIGHT_SPAN = 0x001, 0xFFF
#: The ledger site of a source record made 1:1 in a light plugin, keyed by its object id in the source plugin.
ONE_TO_ONE = 'FNV 1:1'


class LightFull(RuntimeError):
    """A light plugin needs more own ids than 0x001-0xFFF holds."""


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

    def drop(self, kind: str) -> None:
        """Keep no value of `kind` any more."""
        self.sites = {(k, site): keys for (k, site), keys in self.sites.items() if k != kind}

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
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        partial.replace(self.path)


def ledger_path(plugin: Path) -> Path:
    """`plugin`'s ledger, `<stem>.formids.tsv`, in its build records."""
    return moved_in(Path(plugin).with_suffix('.formids.tsv'))


class LedgerWriter(FO4PluginWriter):
    """FO4PluginWriter whose generated FormIDs and stable numbers a Ledger keeps (an empty one until use_ledger)."""

    def __init__(self, *args, **kwargs):
        """FO4PluginWriter's arguments; no ledger file yet, no masters' ledgers."""
        super().__init__(*args, **kwargs)
        self.ledger, self.masters_ledgers, self.from_masters, self.left_to_masters = Ledger(), {}, set(), 0
        self.masters_hold = None
        self.compare_masters = False
        self.light = False

    def make_light(self) -> None:
        """Light ids (0x001-0xFFF) and the ESL flag; in place of reserve_source_ids.
        See: docs/fork/research/fo4_light_plugins.md#scheme
        """
        self.light = self.is_esl = True

    def use_ledger(self, ledger: Ledger) -> None:
        """Keep `ledger`'s ids (reserved) and numbers; call after reserve_source_ids."""
        self.ledger = ledger
        self._derived_taken.update(self.own_index << 24 | oid for oid in ledger.values(ID))

    def use_master_ledgers(self, ledgers: dict, hold: 'frozenset | None' = None) -> None:
        """Read `ledgers` ({index: Ledger}) after the own; `hold`: from_master."""
        self.masters_ledgers, self.masters_hold = ledgers, hold

    def from_master(self, site: str, key) -> 'int | None':
        """The FormID a master's ledger keeps for `key` at `site` (that master's record); None if none, or if the
        built master no longer holds it (the build's own copy, then).
        See: docs/fork/fo4_plugin_layout.md#dlc-stale-ids
        """
        answer = None
        for index, ledger in sorted(self.masters_ledgers.items()):
            oid = ledger.get(ID, site, key)
            if oid is not None and (self.masters_hold is None or index << 24 | oid in self.masters_hold):
                answer = index << 24 | oid
                break
        if self.masters_ledgers:
            MASTERS.ledger(site, key, answer)
        return answer

    def add_record(self, group_sig: str, record_bytes: bytes):
        """Add a record unless it is a generated record a master already holds (from_masters), counted; with
        `compare_masters` (a DLC build) every record is added, for master_overrides to compare."""
        if (not self.compare_masters and record_bytes[:4] != b'GRUP'
                and struct.unpack_from('<I', record_bytes, 12)[0] in self.from_masters):
            self.left_to_masters += 1
            return
        super().add_record(group_sig, record_bytes)

    def write(self, filepath: str):
        """FO4PluginWriter.write() with each top group of plain records in FormID order (stable), so the plugin
        does not depend on the order its makers ran in; a group holding GRUPs (cells, worlds, topics) keeps its own.
        See: docs/fork/fo4_plugin_layout.md#shared-state
        """
        for sig, blobs in self._top_groups.items():
            if all(b[:4] != b'GRUP' for b in blobs):
                blobs.sort(key=lambda b: struct.unpack_from('<I', b, 12)[0])
        super().write(filepath)

    def derive_formid(self, site: str, key, legacy=None) -> int:
        """The FormID of generated record `key` at `site`: a master's (that record, not made again; the own
        ledger's entry for it dropped), else the own ledger's, else the one it kept for `legacy` (the key this one
        replaced; that entry moves to `key`), else the hash of `legacy` or `key`; then kept.
        See: docs/fork/fo4_plugin_layout.md#dlc-shadowed-ids
        """
        if (site, key) in self._derived:
            return self._derived[site, key]
        master = self.from_master(site, key)
        if master is not None:
            self.ledger.pop(ID, site, key)
            self._derived[site, key] = master
            self.from_masters.add(master)
            return master
        return self._kept(site, key, legacy)

    def one_to_one(self, oid: int) -> int:
        """In a light build, the FormID of the source plugin's own record with object id `oid` (site ONE_TO_ONE).
        See: docs/fork/research/fo4_light_plugins.md#scheme
        """
        key = f'{oid:06X}'
        found = self._derived.get((ONE_TO_ONE, key))
        return found if found is not None else self._kept(ONE_TO_ONE, key)

    def _kept(self, site: str, key, legacy=None) -> int:
        """The own ledger's id for `key` at `site`, else the one it kept for `legacy` (that entry moves to `key`),
        else the hash of `legacy` or `key`; then kept."""
        kept = self.ledger.get(ID, site, key)
        if kept is None and legacy is not None:
            kept = self.ledger.pop(ID, site, legacy)
        hashed = self._light_id if self.light else super().derive_formid
        fid = self.own_index << 24 | kept if kept is not None else hashed(site, key if legacy is None else legacy)
        self._derived[site, key] = fid
        self.ledger.put(ID, site, key, fid & 0xFFFFFF)
        return fid

    def _light_id(self, site: str, key) -> int:
        """derive_formid's hash of `key` at `site` and its salted rehashes into 0x001-0xFFF, uncapped: the first
        free id; LightFull when none is.
        See: docs/fork/research/fo4_light_plugins.md#collisions
        """
        payload, probe = f'{site}\x00{key!r}'.encode('utf-8'), 0
        with self._lock:
            if (site, key) in self._derived:
                return self._derived[site, key]
            if len(self._derived_taken) >= LIGHT_SPAN:
                raise LightFull(f'{site}/{key!r}: all {LIGHT_SPAN} light ids are taken')
            while True:
                salt = b'' if probe == 0 else b'\x00%d' % probe
                hashed = struct.unpack('<I', hashlib.md5(payload + salt).digest()[:4])[0]
                fid = self.own_index << 24 | LIGHT_FIRST + hashed % LIGHT_SPAN
                if fid not in self._derived_taken:
                    break
                probe += 1
            self._derived_taken.add(fid)
            self._derived[site, key] = fid
        return fid

    def _high_water_id(self) -> int:
        """HEDR next object id; a light plugin's is one above its highest own id."""
        if not self.light:
            return super()._high_water_id()
        return max((fid & 0xFFFFFF for fid in self._derived_taken), default=0) + 1

    def stable_number(self, site: str, key, make) -> int:
        """The number kept for `key` at `site` (an alias id, a marker stage); else make()'s, then kept."""
        value = self.ledger.get(NUMBER, site, key)
        if value is None:
            value = make()
            self.ledger.put(NUMBER, site, key, value)
        return value
