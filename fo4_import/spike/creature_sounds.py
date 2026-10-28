"""FNV creature sounds on FO4 actors.

An FNV creature plays a sound set: per sound type (CSDT) one SOUN at a
chance, its own or inherited (CSCR; a templated creature takes it with its
Model/Animation). Animation text keys `Enum: <type>` play a type and
`Sound: <EditorID>` a SOUN; Death plays on dying and the conscious loop while
alive. FO4 plays a creature's sounds from its behaviour graph
(`SoundPlay.<SNDR EditorID>` events) and a loop from the NPC's actor sounds
(CS2H count, CS2D descriptor, CS2E, CS2F after NAM8).

- Every mode: the NPC's inherited sounds (CSCR) give way to FNV's conscious
  loop (none without one), and it carries its sound set's keyword.
- Own rig: each type the rig's creatures use becomes a compound SNDR
  `FNV_<project>_<type>` the graph plays, one layer per sound set: a copy of
  the type's SOUN conditioned on the set's keyword and, under 100, on
  GetRandomPercent < its chance (vanilla's layer pattern).

See: docs/fork/fo4_own_rig.md#sounds
"""

from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike import records as R
from fo4_import.spike.conditions import FO4
from fo4_import.spike.npcs import composed, template_source
from fo4_import.spike.type_tests import keywords_edit
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

#: FNV creature sound types by CSDT value; `Enum: <name>` text keys play them.
NAMES = ('Left', 'Right', 'BackLeft', 'BackRight', 'Idle', 'Aware', 'Attack', 'Hit', 'Death', 'Weapon',
         'MovementLoop', 'ConsciousLoop', *(f'Auxiliary{i}' for i in range(1, 9)), 'Jump', 'PlayRandomLoop')
TYPES = {name: i for i, name in enumerate(NAMES)}
FEET, DEATH, CONSCIOUS = frozenset(range(4)), 8, 11
#: FNV template flag Use Model/Animation, which carries the sound set.
USE_MODEL = 0x40
#: derive_formid site (keys: the sound set's FormID; the rig folder and type).
SITE = 'FNV creature sounds'
#: SNDR CNAM Compound; the NPC_ subrecords holding actor sounds, written after NAM8.
COMPOUND, ACTOR_SOUNDS, AFTER = 0x54651A43, frozenset({b'CSCR', b'CS2H', b'CS2K', b'CS2D', b'CS2E', b'CS2F'}), b'NAM8'
HAS_KEYWORD, RANDOM_PERCENT, OP_EQUAL, OP_LESS = FO4.index('HasKeyword'), FO4.index('GetRandomPercent'), 0x00, 0x80
PLAY = 'SoundPlay.'


class RigSounds:
    """The graph events playing an own rig's sounds: per FNV type its compound, per SOUN its descriptor."""

    def __init__(self, types: dict, named):
        """`types` {type: event}; `named(EditorID)` gives a SOUN's event or None."""
        self.types, self.named = types, named
        self.death, self.feet = types.get(DEATH), bool(FEET & set(types))

    def of(self, key: str) -> 'str | None':
        """The event FNV text key `key` plays a sound with (`Enum: <type>`, `Sound: <EditorID>`); None if none."""
        kind, _, value = key.partition(':')
        if kind.strip().lower() == 'sound':
            return self.named(value.strip())
        return self.types.get(TYPES.get(value.strip())) if kind.strip().lower() == 'enum' else None


class CreatureSounds:
    """FNV sound sets as FO4 actor sounds and own-rig compounds, each written once."""

    def __init__(self, builder, records: dict):
        """For `builder` (its writer and sounds) and FNV creatures `records`."""
        self.builder, self.records = builder, records
        self.by_edid = {r['EditorID'].lower(): r for r in builder.sounds.records.values() if r.get('EditorID')}
        self.keywords, self.rigs = {}, {}

    def source(self, rec: dict) -> 'dict | None':
        """The creature whose sound set `rec` plays (its Model/Animation template's, then CSCR); None if none."""
        rec, seen = template_source(self.records, rec, USE_MODEL)[0], set()
        while rec.get('CSCR.InheritSound') and rec['FormID'] not in seen:
            seen.add(rec['FormID'])
            rec = self.records.get(int(rec['CSCR.InheritSound'], 16), {})
        return rec if rec.get('SoundTypeCount') else None

    def edit(self, rec: dict):
        """The NPC edit giving FNV creature `rec` its conscious loop and its sound set's keyword."""
        source = self.source(rec)
        found = types(source) if source else {}
        loop = self.builder.sounds.descriptor(found[CONSCIOUS][0]) if CONSCIOUS in found else 0
        return composed(with_loop(loop), with_keyword(self.keyword(source)) if source else None)

    def keyword(self, source: dict) -> int:
        """Sound set `source`'s keyword, written once."""
        fnv = int(source['FormID'], 16)
        if fnv not in self.keywords:
            fid = self.builder.writer.derive_formid(SITE, f'{fnv:08X}')
            self.builder.writer.add_record('KYWD', R.pack_kywd(fid, f'FNV_{source["EditorID"]}Sounds', 0))
            self.keywords[fnv] = fid
        return self.keywords[fnv]

    def rig(self, rig, members) -> RigSounds:
        """The sounds of own rig `rig` (once), whose creatures are `members`: a compound per type their sets use."""
        if rig.folder not in self.rigs:
            sets = {int(s['FormID'], 16): s for s in map(self.source, members) if s}
            layers = {}
            for fnv, source in sorted(sets.items()):
                for kind, (soun, chance) in sorted(types(source).items()):
                    fid = self.builder.sounds.layer(soun, f'{fnv:08X} {kind}', f'FNV_{source["EditorID"]}_{NAMES[kind]}',
                                                    self._conditions(source, chance)) if kind != CONSCIOUS else 0
                    layers.setdefault(kind, []).extend([fid] if fid else [])
            events = {kind: PLAY + self._compound(rig, kind, fids) for kind, fids in layers.items() if fids}
            self.rigs[rig.folder] = RigSounds(events, self.named)
        return self.rigs[rig.folder]

    def named(self, edid: str) -> 'str | None':
        """The event playing FNV SOUN `edid` (its descriptor); None if none."""
        rec = self.by_edid.get(edid.lower())
        return f'{PLAY}FNV_{rec["EditorID"]}' if rec and self.builder.sounds.descriptor(int(rec['FormID'], 16)) else None

    def _conditions(self, source: dict, chance: int) -> bytes:
        """HasKeyword(the set's keyword) and, under 100, GetRandomPercent < `chance`."""
        out = R.pack_ctda(OP_EQUAL, 1.0, HAS_KEYWORD, self.keyword(source))
        return out + (R.pack_ctda(OP_LESS, float(chance), RANDOM_PERCENT) if chance < 100 else b'')

    def _compound(self, rig, kind: int, layers: list) -> str:
        """Write rig `rig`'s compound SNDR of type `kind` playing `layers`; its EditorID."""
        edid = f'FNV_{rig.project}_{NAMES[kind]}'
        subs = pack_subrecord('EDID', edid.encode() + b'\0') + R.pack_u32('CNAM', COMPOUND)
        subs += b''.join(R.pack_u32('DNAM', fid) for fid in layers)
        fid = self.builder.writer.derive_formid(SITE, f'{rig.folder} {kind}')
        self.builder.writer.add_record('SNDR', pack_fo4_record('SNDR', fid, 0, subs))
        self.builder.counts['creature sound compounds'] += 1
        return edid


def types(source: dict) -> dict:
    """{type: (SOUN FormID, chance)} of FNV sound set `source`."""
    count = int(source.get('SoundTypeCount', 0) or 0)
    return {int(source[f'SoundType[{i}].Type']): (int(source[f'SoundType[{i}].Sound'], 16),
                                                   int(source.get(f'SoundType[{i}].Sound.Chance', 100)))
            for i in range(count) if source.get(f'SoundType[{i}].Sound')}


def with_keyword(keyword: int):
    """An NPC edit adding `keyword` (type_tests.keywords_edit)."""
    return keywords_edit([keyword])


def with_loop(loop: int):
    """An NPC edit replacing its actor sounds (CSCR, CS2*) with actor sound loop `loop` after NAM8 (0: none)."""
    block = (R.pack_u32('CS2H', 1) + R.pack_u32('CS2D', loop) + pack_subrecord('CS2E', b'')
             + pack_subrecord('CS2F', b'\0')) if loop else b''

    def edit(subs: bytes) -> bytes:
        """The subrecords with the loop in place of their actor sounds."""
        return b''.join(pack_subrecord(tag.decode(), data) + (block if tag == AFTER else b'')
                        for tag, data in subrecords(subs) if tag not in ACTOR_SOUNDS)
    return edit
