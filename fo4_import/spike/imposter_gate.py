"""FNV's region imposter glow cards shown only where FNV shows them: while the player stands in a region whose
imposter list (REGN RDAT type 8, RDID) names them.

The build places the glow cards (glow_cards) starting disabled. Cards listed by the same regions form a group;
each group gets a player ability of F3NV_ImposterGate script effects: one enables the group at night while
a region's watch global (region_watch) is 1; others disable it while all are 0 or by day, as the cards'
own night script cannot run unloaded. A start-game quest's player alias gives the abilities (ALSP).

See: docs/fork/fo4_look.md#route-horizon
"""

import collections
import struct

from fo4_import.base.install import source_walk
from fo4_import.base.vmad import object_scripts
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from fo4_import.spike.consumable_effects import effect_pair
from fo4_import.spike.regions import IMPOSTER
from fo4_import.spike.script import fo4_forms
from fo4_import.spike.script_effects import CONSTANT, DELIVERY
from tes5_import.base.tes5_reader import subrecords

#: derive_formid site of the gate quest (key: 'quest'); the effect script; the player.
SITE, SCRIPT, PLAYER = 'FNV imposter gate', 'F3NV_ImposterGate', 0x14
#: CTDA type flags: OR with the next; FO4's GetGlobalValue.
OR_NEXT, GLOBAL_VALUE = C.OR_NEXT, C.FO4.index('GetGlobalValue')
#: CTDA compare operators: >, >=, <, <=.
GREATER, AT_LEAST, LESS, AT_MOST = 0x40, 0x60, 0x80, 0xA0
#: Lucky38LightScript's night: lit after 20:00 and before 06:00.
DUSK, DAWN = 20.0, 6.0


def listing() -> dict:
    """{FNV reference: frozenset of the FNV regions whose imposter list names it}."""
    out = collections.defaultdict(set)
    for rec, _ in source_walk(b'REGN'):
        kind = None
        for tag, data in subrecords(rec.body):
            kind = struct.unpack_from('<I', data)[0] if tag == b'RDAT' else kind
            for (ref,) in struct.iter_unpack('<I', data) if tag == b'RDID' and kind == IMPOSTER else ():
                out[ref].add(rec.form_id)
    return {ref: frozenset(regions) for ref, regions in out.items()}


def shown_while(globs: list, show: bool) -> bytes:
    """CTDAs: some of `globs` is 1 (`show`), else every one is 0."""
    if show:
        return b''.join(R.pack_ctda(OR_NEXT if i < len(globs) - 1 else 0, 1.0, GLOBAL_VALUE, g)
                        for i, g in enumerate(globs))
    return b''.join(R.pack_ctda(0, 0.0, GLOBAL_VALUE, g) for g in globs)


def by_hour(hour: int, night: bool) -> bytes:
    """CTDAs on GameHour `hour`: after DUSK or before DAWN (`night`), else between."""
    if night:
        return R.pack_ctda(GREATER | OR_NEXT, DUSK, GLOBAL_VALUE, hour) + R.pack_ctda(LESS, DAWN, GLOBAL_VALUE, hour)
    return R.pack_ctda(AT_MOST, DUSK, GLOBAL_VALUE, hour) + R.pack_ctda(AT_LEAST, DAWN, GLOBAL_VALUE, hour)


class ImposterGate:
    """The glow cards a build places, and their abilities and quest."""

    def __init__(self, builder):
        """For `builder` (spike.cell.CellBuilder), with no card placed."""
        self.builder, self.placed, self.regions = builder, {}, None

    def gated(self, fnv: int) -> bool:
        """Whether FNV ref `fnv` is an imposter a region lists (starts disabled)."""
        self.regions = listing() if self.regions is None else self.regions
        return fnv in self.regions

    def add(self, fnv: int, fid: int) -> None:
        """Note glow card `fnv`, placed as `fid`."""
        self.placed[fnv] = fid

    def write(self) -> None:
        """The abilities and the player quest; nothing without a card. Before region_watch.write, as it names the
        regions' globals."""
        groups = collections.defaultdict(list)
        for fnv, fid in sorted(self.placed.items()):
            groups[self.regions[fnv]].append(fid)
        ordered = sorted(groups.items(), key=lambda group: sorted(group[0]))
        spells = [s for s in (self._ability(regions, cards) for regions, cards in ordered) if s]
        if not spells:
            return
        quest = self.builder.writer.derive_formid(SITE, 'quest')
        self.builder.writer.add_record('QUST', R.pack_qust(quest, 'FNV_ImposterGate', '', 0, [], 'Player', PLAYER,
                                                           spells=tuple(spells)))
        self.builder.scripts.used.append(SCRIPT)
        self.builder.counts['imposter gate groups'] = len(spells)

    def _ability(self, regions: frozenset, cards: list) -> 'int | None':
        """The ability showing `cards` at night while the player is in one of FNV `regions`, hiding them outside
        the regions or by day; None (counted: the cards stay hidden) when no region has polygons to watch."""
        watch, effects = self.builder.region_watch, self.builder.scripts.effects
        globs = [g for g in (watch.global_of(r) for r in sorted(regions)) if g]
        if not globs:
            self.builder.counts['imposter group never shown (no region polygons)'] += 1
            return None
        key, hour = '_'.join(f'{r:06X}' for r in sorted(regions)), fo4_forms()['GlobalVariable']['GameHour']
        pairs = b''
        for name, show, ctdas in (('Show', True, shown_while(globs, True) + by_hour(hour, True)),
                                  ('Hide', False, shown_while(globs, False)), ('Day', False, by_hour(hour, False))):
            vmad = object_scripts([(SCRIPT, {}, {'Cards': ('objects', cards), 'Show': ('bool', show)})])
            effect = effects.vmad_effect(f'FNV_ImposterGate_{key}_{name}', vmad, DELIVERY['Self'], CONSTANT)
            pairs += effect_pair(effect, 0.0, 0, 0) + ctdas
        return effects.ability(f'FNV_ImposterGate_{key}', pairs)
