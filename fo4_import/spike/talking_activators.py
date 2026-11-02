"""FNV talking activators that are not radio stations (intercoms, loudspeakers) as Fallout 4 talking activators.

FNV lets a TACT speak as an actor: `[talker.]SetTalkingActivatorActor
<actor>` makes it pass the actor's GetIsID, in the actor's voice. Fallout 4
has neither the command nor IsActorTalkingThroughActivator. Each actor a
talker speaks as gets a FLST holding its own base, all listed in
TES4TalkingAsLists; TES4Polyfill.SetTalkingActivatorActor moves the
talker's base into the actor's list, and a line's conditions read it
(conditions.talking_through). A talker that speaks as one actor starts in
that actor's list. A TACT takes the voice type of the actors it
speaks as when they share one, else its own, as vanilla intercoms carry the
speaker's.

See: docs/fork/fo4_pipeline.md#talking-activators
"""

import struct
from pathlib import Path

from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike.conditions import TALKING_AS
from fo4_import.spike.radio import RADIO_STATION
from script_convert.constants import TALKING_LISTS_PROPERTY
from tes5_import.base.writer import pack_formid_subrecord, pack_string_subrecord, pack_subrecord
from tes5_import.dialogue.talking_lists_falloutnv import scan_pairs

#: The ledger site of the talking-as lists.
SITE = 'FNV talking as'
#: The export types scan_pairs reads: talkers, scripts and result scripts naming them, placed references.
SCANNED = ('TACT', 'SCPT', 'INFO', 'QUST', 'REFR', 'ACHR', 'ACRE')
#: EditorID prefix of an actor's talking-as list (then the actor's FNV FormID in hex).
LIST_PREFIX = 'TES4TalkingAs_'


def pack_tact(fid: int, edid: str, name: str, model: str, bounds: tuple, vmad: bytes, voice: 'int | None') -> bytes:
    """A talking activator in vanilla's order: scripts, bounds, name, model, PNAM and FNAM 0, voice type."""
    subs = pack_string_subrecord('EDID', edid) + (pack_subrecord('VMAD', vmad) if vmad else b'')
    subs += pack_subrecord('OBND', struct.pack('<6h', *bounds)) + (pack_string_subrecord('FULL', name) if name else b'')
    subs += (pack_string_subrecord('MODL', model) if model else b'') + pack_subrecord('PNAM', bytes(4))
    subs += pack_subrecord('FNAM', bytes(2)) + (pack_formid_subrecord('VNAM', voice) if voice else b'')
    return pack_fo4_record('TACT', fid, 0, subs)


def pack_list(fid: int, edid: str, members: list) -> bytes:
    """A FLST of `members` in order."""
    return pack_fo4_record('FLST', fid, 0, pack_string_subrecord('EDID', edid)
                           + b''.join(pack_formid_subrecord('LNAM', m) for m in members))


def speakers_of(pairs: set, talkers: dict) -> dict:
    """{talker FNV FormID: {actor base FNV FormID}} of scan_pairs' (TACT EditorID lower, actor hex) `pairs`."""
    edids = {rec['EditorID'].lower(): fid for fid, rec in talkers.items() if rec.get('EditorID')}
    out = {}
    for edid, actor in pairs:
        if edid in edids:
            out.setdefault(edids[edid], set()).add(int(actor, 16))
    return out


class Talkers:
    """FO4 talking activators for FNV's non-station TACTs and the talking-as lists of the actors they speak as."""

    def __init__(self, builder, export_dir: Path):
        """Talkers made through `builder`, paired with actors by every SetTalkingActivatorActor in `export_dir`."""
        self.builder = builder
        by_type = {sig: export_records(export_dir, sig) for sig in SCANNED}
        self.records = {int(r['FormID'], 16): r for r in by_type['TACT']
                        if not int(r.get('RecordFlags', 0)) & RADIO_STATION}
        self.speaks_as = speakers_of(scan_pairs(by_type), self.records)
        self.voices = {int(r['FormID'], 16): int(r.get('VTCK.Voice', '0'), 16)
                       for sig in ('NPC_', 'CREA') for r in export_records(export_dir, sig)}
        self.all_lists = builder.writer.derive_formid(SITE, TALKING_LISTS_PROPERTY)
        self.made, self.lists = {}, {}

    def base(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 TACT of FNV talker `rec` (FormID `fnv`), reserved once and written by write(); None for a
        radio station."""
        if fnv not in self.records:
            return None
        if fnv not in self.made:
            model = rec.get('Model.MODL', '')
            path, bounds = self.builder.mesh(model) if model else ('', None)
            bounds = bounds or tuple(int(rec.get(f'OBND.{k}', 0)) for k in ('X1', 'Y1', 'Z1', 'X2', 'Y2', 'Z2'))
            self.made[fnv] = (self.builder.fnv_id(fnv), path, bounds)
        return self.made[fnv][0]

    def form_map(self, form_map: dict) -> dict:
        """The talkers made and each built actor's talking-as list (key (TALKING_AS, actor)), for line conditions."""
        actors = {a for spoken in self.speaks_as.values() for a in spoken if a in form_map}
        self.lists = {a: self.builder.writer.derive_formid(SITE, f'{a:08X}') for a in sorted(actors)}
        return {**{fnv: made[0] for fnv, made in self.made.items()},
                **{(TALKING_AS, a): fid for a, fid in self.lists.items()}}

    def voice(self, fnv: int, rec: dict) -> 'int | None':
        """The FO4 voice type of talker `fnv`: its actors' when they share one, else its own (VNAM); None for none."""
        shared = {self.voices.get(a, 0) for a in self.speaks_as.get(fnv, ())} - {0}
        own = next(iter(shared)) if len(shared) == 1 else int(rec.get('VNAM', '0'), 16)
        return self.builder.npcs.voices.of(own) if own else None

    def members(self, actor: int, form_map: dict) -> list:
        """A talking-as list's forms: its actor's base, then each talker made that speaks as only that actor, so a
        line asks no script first (FO4 opens the talker's dialogue before its OnActivate runs)."""
        return [form_map[actor]] + [self.made[t][0] for t in sorted(self.made) if self.speaks_as.get(t) == {actor}]

    def write(self, form_map: dict) -> None:
        """Write the talking-as lists (members), their list, and every talker made."""
        for actor, fid in self.lists.items():
            self.builder.writer.add_record('FLST', pack_list(fid, f'{LIST_PREFIX}{actor:08X}',
                                                             self.members(actor, form_map)))
        self.builder.writer.add_record('FLST', pack_list(self.all_lists, TALKING_LISTS_PROPERTY,
                                                         list(self.lists.values())))
        for fnv, (fid, model, bounds) in sorted(self.made.items()):
            rec = self.records[fnv]
            vmad = self.builder.scripts.vmad(int(rec['SCRI'], 16)) if rec.get('SCRI') else b''
            self.builder.writer.add_record('TACT', pack_tact(fid, f'FNV_{rec["EditorID"]}', rec.get('FULL', ''),
                                                             model, bounds, vmad, self.voice(fnv, rec)))
        self.builder.counts['TACT'] += len(self.made)
        self.builder.counts['talking-as lists'] = len(self.lists)
