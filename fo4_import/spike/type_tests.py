"""FNV's weapon skill, weapon animation and creature type tests as FO4 keyword tests.

FNV tests three properties FO4's records do not carry: a weapon's skill
(IsWeaponSkillType), its animation type (GetWeaponAnimType) and a
creature's type (GetIsCreatureType). The build stamps a keyword for each on
the weapons and creatures it converts, from FNV's own fields, and a test
becomes HasKeyword on a weapon subject (a perk's weapon tab) or a creature,
and WornHasKeyword on an actor holding the weapon, as vanilla's perks, idles
and lines test WeaponType* and ActorType*.

See: docs/fork/fo4_perks.md#type-tests
"""

import struct

from fo4_import.base.install import source_esm
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

SKILL, ANIM, CREATURE = 'IsWeaponSkillType', 'GetWeaponAnimType', 'GetIsCreatureType'
TESTS = frozenset({SKILL, ANIM, CREATURE})
#: FNV weapon animation types and creature types, in enum order (xEdit wbWeaponAnimTypeEnum, wbCreatureTypeEnum).
ANIM_TYPES = ('HandToHand', 'Melee1Hand', 'Melee2Hand', 'PistolBallistic', 'PistolEnergy', 'RifleBallistic',
              'RifleAutomatic', 'RifleEnergy', 'Handle', 'Launcher', 'GrenadeThrow', 'LandMine', 'MineDrop', 'Thrown')
CREATURE_TYPES = ('Animal', 'MutatedAnimal', 'MutatedInsect', 'Abomination', 'SuperMutant', 'FeralGhoul', 'Robot',
                  'Giant')
#: FNV WEAP DNAM offsets of the animation type (u32) and skill (s32 actor value); CREA DATA offset of the type (u8).
DNAM_ANIM, DNAM_SKILL, DATA_TYPE = 0, 104, 0
#: derive_formid site of the keywords (key: EditorID); vanilla WeaponType*/ActorType* keywords' TNAM.
SITE, KIND = 'FNV type keyword', 0
#: form_map key of the build's TypeKeywords (say_topics.conditions_of).
FORM_KEY = 'type keywords'
#: FO4 condition functions: a keyword on the subject itself, and on what an actor wears or holds.
HAS, WORN = 'HasKeyword', 'WornHasKeyword'
EQUAL, COMPARE = 0x00, 0xE0


class TypeKeywords:
    """The keywords standing for FNV's types, each written once on first use, and the FNV records they mark."""

    def __init__(self, writer):
        """Keywords written through `writer`, marking the source plugin's records."""
        self.writer, self.written, self.fields = writer, set(), None

    def keyword(self, edid: str) -> int:
        """The FormID of keyword `edid`, written the first time."""
        fid = self.writer.derive_formid(SITE, edid)
        if fid not in self.written:
            self.written.add(fid)
            self.writer.add_record('KYWD', R.pack_kywd(fid, edid, KIND))
        return fid

    def _fields(self) -> dict:
        """{FNV FormID: keyword EditorIDs} of the source plugin's weapons and creatures, read once."""
        if self.fields is None:
            self.fields = {}
            for rec, _ in walk(source_esm(), b'WEAP', b'CREA'):
                subs = dict(subrecords(rec.body))
                self.fields[rec.form_id] = weapon_names(subs) if rec.sig == b'WEAP' else creature_names(subs)
        return self.fields

    def of(self, fnv: int) -> list:
        """The keywords marking FNV weapon or creature `fnv`."""
        return [self.keyword(edid) for edid in self._fields().get(fnv & 0xFFFFFF, ())]


def weapon_names(subs: dict) -> tuple:
    """Keyword EditorIDs of an FNV weapon's DNAM: its animation type and skill."""
    dnam = subs.get(b'DNAM', b'')
    if len(dnam) < DNAM_SKILL + 4:
        return ()
    anim, skill = struct.unpack_from('<I', dnam, DNAM_ANIM)[0], struct.unpack_from('<i', dnam, DNAM_SKILL)[0]
    out = (anim_keyword(anim),) if anim < len(ANIM_TYPES) else ()
    return out + ((skill_keyword(skill),) if 0 <= skill < len(C.FNV_AV_NAMES) else ())


def creature_names(subs: dict) -> tuple:
    """Keyword EditorID of an FNV creature's type."""
    data = subs.get(b'DATA', b'')
    return (creature_keyword(data[DATA_TYPE]),) if data and data[DATA_TYPE] < len(CREATURE_TYPES) else ()


def anim_keyword(anim: int) -> str:
    """EditorID of the keyword of FNV weapon animation type `anim`."""
    return f'FNV_WeaponAnim{ANIM_TYPES[anim]}'


def skill_keyword(skill: int) -> str:
    """EditorID of the keyword of FNV skill actor value `skill`."""
    return 'FNV_WeaponSkill' + C.FNV_AV_NAMES[skill].replace(' ', '')


def creature_keyword(kind: int) -> str:
    """EditorID of the keyword of FNV creature type `kind`."""
    return f'FNV_CreatureType{CREATURE_TYPES[kind]}'


def with_keywords(subs: list, keywords: list) -> list:
    """Subrecords [(tag, data)] with `keywords` added to KSIZ/KWDA; unchanged without a KWDA or keywords."""
    have = next((d for t, d in subs if t == b'KWDA'), None)
    if not keywords or have is None:
        return subs
    ids = list(struct.unpack(f'<{len(have) // 4}I', have)) + [k for k in keywords if struct.pack('<I', k) not in have]
    return [(t, struct.pack('<I', len(ids)) if t == b'KSIZ' else struct.pack(f'<{len(ids)}I', *ids) if t == b'KWDA'
             else d) for t, d in subs]


def keywords_edit(keywords: list):
    """A clone edit (records.clone_npc) adding `keywords`; None without any."""
    if not keywords:
        return None

    def edit(subs: bytes) -> bytes:
        """The subrecords with the keywords added."""
        return b''.join(pack_subrecord(t.decode(), d) for t, d in with_keywords(subrecords(subs), keywords))
    return edit


def translated(conds: list, keywords: 'TypeKeywords | None', item: bool) -> 'list | None':
    """Parsed FNV conditions with each type test as keyword tests (HasKeyword on a weapon subject when `item` or a
    creature, WornHasKeyword on an actor); None when one cannot be (no keywords, a global, a test that settles to
    a constant, or several negated keywords inside an OR group)."""
    out = []
    for i, cond in enumerate(conds):
        if cond['func'] not in TESTS:
            out.append(cond)
            continue
        names = None if keywords is None or cond['op_flags'] & C.USE_GLOBAL else _keywords_held(cond)
        if names is None:
            return None
        edids, held = names
        grouped = cond['op_flags'] & C.OR_NEXT or (i and conds[i - 1]['op_flags'] & C.OR_NEXT)
        if not held and len(edids) > 1 and grouped:
            return None
        func = HAS if item or cond['func'] == CREATURE else WORN
        for j, edid in enumerate(edids):
            last = j == len(edids) - 1
            joined = cond['op_flags'] & C.OR_NEXT if last else (C.OR_NEXT if held else 0)
            flags = cond['op_flags'] & ~(COMPARE | C.OR_NEXT | C.USE_GLOBAL) | EQUAL | joined
            out.append({**cond, 'func': func, 'p1': keywords.keyword(edid), 'p2': 0, 'op_flags': flags,
                        'value': 1.0 if held else 0.0})
    return out


def _keywords_held(cond: dict) -> 'tuple | None':
    """(keyword EditorIDs, whether the test holds when one is present) of one FNV type test; None when it settles
    to a constant."""
    if cond['func'] == ANIM:
        holds = [t for t in range(len(ANIM_TYPES)) if C.compare(cond, float(t))]
        if not holds or len(holds) == len(ANIM_TYPES):
            return None
        if len(holds) <= len(ANIM_TYPES) // 2:
            return [anim_keyword(t) for t in holds], True
        return [anim_keyword(t) for t in range(len(ANIM_TYPES)) if t not in holds], False
    kinds = C.FNV_AV_NAMES if cond['func'] == SKILL else CREATURE_TYPES
    present, absent = C.compare(cond, 1.0), C.compare(cond, 0.0)
    if present == absent or not 0 <= cond['p1'] < len(kinds):
        return None
    name = skill_keyword(cond['p1']) if cond['func'] == SKILL else creature_keyword(cond['p1'])
    return [name], present
