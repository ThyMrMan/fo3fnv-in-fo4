"""FormIDs across plugins: a source record's FO4 FormID by its master byte, and the masters' ledgers.

A source plugin with masters (an FNV DLC on FalloutNV.esm) names its masters' records by their index in its own
master list. Each source plugin becomes the FO4 plugin of the same name (fo4_plugin), so a record of source master
i is that FO4 plugin's record with the same object id, at the index the build's FO4 master list gives it; the
source plugin's own records are the build's own. A master built before keeps its ledger beside it
(`<stem>.formids.tsv`); a build reads those, so a generated record a master already holds is that master's.

See: docs/fork/fo4_plugin_layout.md#formids
"""

import functools
import struct
from pathlib import Path

from fo4_import.base.install import HEADER, file_masters
from fo4_import.base.ledger import ID, ONE_TO_ONE, Ledger, ledger_path
from fo4_import.base.writer import FLAG_ESL
from fo4_import.pipeline.build_inputs import MASTERS

#: FormID master byte and object id.
MASTER_SHIFT, OBJECT_ID = 24, 0xFFFFFF


def fo4_plugin(source: str) -> str:
    """The FO4 plugin made from source plugin `source`: the same name."""
    return source


class SourceIds:
    """FO4 FormIDs of one source plugin's records, given its masters and the build's FO4 masters."""

    def __init__(self, source_masters: list, fo4_masters: list, own_index: int):
        """`source_masters`: the source plugin's master names, in its order; `fo4_masters`: the build's."""
        lower = [m.lower() for m in fo4_masters]
        missing = [m for m in source_masters if fo4_plugin(m).lower() not in lower]
        if missing:
            raise ValueError(f'the build has no FO4 master for source masters {missing}')
        self.indexes = [lower.index(fo4_plugin(m).lower()) for m in source_masters]
        self.own_index, self.keyed = own_index, {}

    def key(self, index: int, resolve) -> None:
        """Map light plugin `index`'s records by `resolve`(object id)."""
        self.keyed[index] = resolve

    def is_own(self, fid: int) -> bool:
        """Whether source FormID `fid` is the source plugin's own record (not a master's)."""
        return fid >> MASTER_SHIFT >= len(self.indexes)

    def held(self, fid: int) -> 'int | None':
        """Source FormID `fid` in FO4: its master plugin's, else the build's; through key() for a light plugin,
        None when its ledger has no id for it."""
        byte = fid >> MASTER_SHIFT
        index = self.indexes[byte] if byte < len(self.indexes) else self.own_index
        if index in self.keyed:
            return self.keyed[index](fid & OBJECT_ID)
        return index << MASTER_SHIFT | fid & OBJECT_ID

    def fo4(self, fid: int) -> int:
        """held(), which must find `fid`."""
        found = self.held(fid)
        if found is None:
            raise KeyError(f'{fid:08X}: its light plugin\'s ledger has no {ONE_TO_ONE!r} id for it')
        return found


def built_plugins(source_masters: list, dirs: tuple) -> list:
    """The FO4 plugins built from `source_masters`, each from the first of `dirs` holding it; a build of a source
    with masters needs its masters built first."""
    out = []
    for name in map(fo4_plugin, source_masters):
        found = next((Path(d) / name for d in dirs if (Path(d) / name).is_file()), None)
        if found is None:
            raise SystemExit(f'{name} is not built in {[str(d) for d in dirs]}: build it before its dependents')
        MASTERS.cover('plugin', found)
        out.append(found)
    return out


def dependent_masters(built: list, extras: list, base: list) -> list:
    """A dependent build's FO4 masters: `base`, each `built` plugin's masters and itself in load order, then
    `extras`; a built plugin's FormIDs then read alike in it and in the build (master_overrides).
    See: docs/fork/fo4_plugin_layout.md#dlc
    """
    order = list(base)
    for path in built:
        MASTERS.header(path, file_masters(path))
        order += file_masters(path) + [path.name]
    return list(dict.fromkeys(order + list(extras)))


def master_ledgers(masters: list, dirs: tuple) -> dict:
    """{master index: Ledger} of the build's masters that have a ledger in one of `dirs`, the first found."""
    out = {}
    for index, name in enumerate(masters):
        found = next((p for p in (ledger_path(Path(d) / name) for d in dirs) if p.is_file()), None)
        if found:
            MASTERS.cover(f'ledger:{index}', found)
            out[index] = Ledger(found)
    return out


def is_light(path: Path) -> bool:
    """Whether plugin file `path`'s header has the ESL flag (any extension)."""
    with open(path, 'rb') as f:
        return bool(struct.unpack_from('<I', f.read(HEADER), 8)[0] & FLAG_ESL)


def key_light(ids: SourceIds, writer, built: list, masters: list, ledgers: dict) -> None:
    """Map light plugins' records through their ledgers (ONE_TO_ONE): the build's own when `writer` is light, and
    each light plugin of `built` (by `masters` index; it must have its ledger in `ledgers`).
    See: docs/fork/research/fo4_light_plugins.md#reading
    """
    if writer.light:
        ids.key(writer.own_index, writer.one_to_one)
    lower = [m.lower() for m in masters]
    for path in built:
        if not is_light(path):
            continue
        index = lower.index(path.name.lower())
        if index not in ledgers:
            raise SystemExit(f'{path.name} is a light plugin with no ledger beside it: its records can not be found')
        ids.key(index, functools.partial(_ledger_id, ledgers[index], index))


def _ledger_id(ledger: Ledger, index: int, oid: int) -> 'int | None':
    """Light master `index`'s FormID of source record `oid`; None if unkept."""
    kept = ledger.get(ID, ONE_TO_ONE, f'{oid:06X}')
    return None if kept is None else index << MASTER_SHIFT | kept
