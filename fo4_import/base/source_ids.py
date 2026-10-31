"""FormIDs across plugins: a source record's FO4 FormID by its master byte, and the masters' ledgers.

A source plugin with masters (an FNV DLC on FalloutNV.esm) names its masters' records by their index in its own
master list. Each source plugin becomes the FO4 plugin of the same name (fo4_plugin), so a record of source master
i is that FO4 plugin's record with the same object id, at the index the build's FO4 master list gives it; the
source plugin's own records are the build's own. A master built before keeps its ledger beside it
(`<stem>.formids.tsv`); a build reads those, so a generated record a master already holds is that master's.

See: docs/fork/fo4_plugin_layout.md#formids
"""

from pathlib import Path

from fo4_import.base.install import file_masters
from fo4_import.base.ledger import Ledger, ledger_path

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
        self.own_index = own_index

    def is_own(self, fid: int) -> bool:
        """Whether source FormID `fid` is the source plugin's own record (not a master's)."""
        return fid >> MASTER_SHIFT >= len(self.indexes)

    def fo4(self, fid: int) -> int:
        """Source FormID `fid` in FO4: its master plugin's, else the build's."""
        byte = fid >> MASTER_SHIFT
        index = self.indexes[byte] if byte < len(self.indexes) else self.own_index
        return index << MASTER_SHIFT | fid & OBJECT_ID


def built_plugins(source_masters: list, dirs: tuple) -> list:
    """The FO4 plugins built from `source_masters`, each from the first of `dirs` holding it; a build of a source
    with masters needs its masters built first."""
    out = []
    for name in map(fo4_plugin, source_masters):
        found = next((Path(d) / name for d in dirs if (Path(d) / name).is_file()), None)
        if found is None:
            raise SystemExit(f'{name} is not built in {[str(d) for d in dirs]}: build it before its dependents')
        out.append(found)
    return out


def dependent_masters(built: list, extras: list, base: list) -> list:
    """A dependent build's FO4 masters: `base`, each `built` plugin's masters and itself in load order, then
    `extras`; a built plugin's FormIDs then read alike in it and in the build (master_overrides).
    See: docs/fork/fo4_plugin_layout.md#dlc
    """
    order = list(base)
    for path in built:
        order += file_masters(path) + [path.name]
    return list(dict.fromkeys(order + list(extras)))


def master_ledgers(masters: list, dirs: tuple) -> dict:
    """{master index: Ledger} of the build's masters that have a ledger in one of `dirs`, the first found."""
    out = {}
    for index, name in enumerate(masters):
        found = next((p for p in (ledger_path(Path(d) / name) for d in dirs) if p.is_file()), None)
        if found:
            out[index] = Ledger(found)
    return out
