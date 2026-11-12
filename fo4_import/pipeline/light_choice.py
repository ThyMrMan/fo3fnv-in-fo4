"""Whether a build writes a light (ESL-flagged) plugin: the user's per-mod opt-in, locked after the mod's first
build; a plugin with no new records light either way.

The opt-in is kept in the build stamp (STAMP_KEY). A build whose choice differs from the one its plugin was built
with stops, saying how many FormIDs would move, unless the switch is confirmed; a confirmed switch gives every own
record a new id (the ledger's ids are dropped). A light build refuses a built plugin without its ledger, or one
whose own ids its ledger does not hold (renumbered outside the converter); a full build refuses a built plugin
that was made light outside it.

See: docs/fork/research/fo4_light_plugins.md#policy
"""

import json
from dataclasses import dataclass
from pathlib import Path

from fo4_import.base.install import file_masters
from fo4_import.base.ledger import ID, ONE_TO_ONE, Ledger, ledger_path
from fo4_import.base.source_ids import is_light
from fo4_import.pipeline.build_steps import stamp_path
from tes5_import.base.tes5_reader import subrecords, walk

#: The build stamp's key for the user's choice.
STAMP_KEY = 'light opt-in'
#: CELL precombine (XCRI, XPRI, PCMB) and previs (VISI, RVIS) data; their files are named by FormID & 0xFFFFFF.
PRECOMBINE_DATA = (b'XCRI', b'XPRI', b'PCMB', b'VISI', b'RVIS')


@dataclass(frozen=True)
class Choice:
    """`light`: build a light plugin; `fresh_ids`: the plugin type switched, so no ledger id is kept."""
    light: bool = False
    fresh_ids: bool = False


def choose(plugin: Path, requested: bool, switch: bool = False) -> Choice:
    """The build of `plugin`: light when `requested` on its first build, else as it was built; a different
    `requested` only with `switch` (the user confirmed that saves using the mod break). SystemExit otherwise.
    See: docs/fork/research/fo4_light_plugins.md#who-decides
    """
    ledger = Ledger(ledger_path(plugin))
    ids = ledger.values(ID)
    if not plugin.is_file() and not ids:
        return Choice(requested)
    before = built_light(plugin, ledger)
    if requested != before:
        if not switch:
            moved = len(own_ids(plugin)) if plugin.is_file() else len(ids)
            raise SystemExit(f'{plugin.name} was built as a {_kind(before)} plugin; building it {_kind(requested)} '
                             f'moves {moved} FormIDs and breaks saves that use it. Confirm the switch to do it.')
        return Choice(requested, True)
    _check_built(plugin, ledger, requested)
    return Choice(requested)


def built_light(plugin: Path, ledger: Ledger) -> bool:
    """Whether `plugin` was built with the light opt-in: its stamp says so, else its ledger keeps light 1:1 ids."""
    stamp = stamp_path(plugin)
    if stamp.is_file():
        kept = json.loads(stamp.read_text(encoding='utf-8')).get(STAMP_KEY)
        if kept is not None:
            return bool(kept)
    return bool(ledger.values(ID, ONE_TO_ONE))


def _check_built(plugin: Path, ledger: Ledger, light: bool) -> None:
    """SystemExit when built `plugin` was renumbered or made light outside the converter."""
    if not plugin.is_file():
        return
    own = own_ids(plugin)
    if light and not ledger.path.is_file():
        raise SystemExit(f'{plugin.name} is a light plugin with no ledger ({ledger.path.name}): a new numbering would '
                         'break saves that use it. Put its ledger back, or confirm a switch.')
    if light and not own <= set(ledger.values(ID)):
        raise SystemExit(f'{plugin.name}: {len(own - set(ledger.values(ID)))} of its FormIDs are not in its ledger '
                         '(compacted outside the converter?); rebuilding would move them.')
    if not light and own and is_light(plugin):
        raise SystemExit(f'{plugin.name} was made light outside the converter (its own FormIDs were renumbered); '
                         'rebuilding it full would move them. Use the light opt-in instead.')


def _kind(light: bool) -> str:
    """'light' or 'full'."""
    return 'light' if light else 'full'


def own_ids(plugin: Path) -> set:
    """Object ids of `plugin`'s own records (its index: after its masters)."""
    own = len(file_masters(plugin))
    return {rec.form_id & 0xFFFFFF for rec, _ in walk(plugin.read_bytes(), bodies=()) if rec.form_id >> 24 == own}


def finish_flag(writer) -> str:
    """Before `writer` writes: a full plugin with no own record is made light (no FormID moves); a light one may
    not carry precombine or previs data on its own cells (SystemExit). What it is, for the counts.
    See: docs/fork/research/fo4_light_plugins.md#override-only
    """
    if not writer.light:
        writer.is_esl = writer.is_esl or not any(_own(writer, ()))
        return 'light (no new records)' if writer.is_esl else 'full'
    cells = [rec.form_id for rec in _own(writer, (b'CELL',))
             if rec.sig == b'CELL' and any(tag in PRECOMBINE_DATA for tag, _ in subrecords(rec.body))]
    if cells:
        raise SystemExit(f'{len(cells)} own cells carry precombine or previs data, which a light plugin cannot: '
                         f'{", ".join(f"{fid:08X}" for fid in cells[:5])}')
    return 'light (opted in)'


def _own(writer, bodies: tuple):
    """`writer`'s own records, in its top records and pre-built groups, with `bodies` read."""
    for blob in (*writer.top_records(), *writer.raw_groups()):
        for rec, _ in walk(blob, bodies=bodies, span=(0, len(blob))):
            if rec.form_id >> 24 == writer.own_index:
                yield rec
