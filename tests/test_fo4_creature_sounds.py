"""FNV creature sounds on FO4 actors (fo4_import.spike.creature_sounds)."""

import struct
from collections import Counter

from fo4_import.spike import creature_sounds as S
from tes5_import.base.tes5_reader import subrecords
from tes5_import.base.writer import pack_subrecord

GECKO, GREEN, TEMPLATED, INHERITS = '00000100', '00000200', '00000300', '00000400'


class _Writer:
    """Records by signature; FormIDs numbered by (site, key)."""

    def __init__(self):
        self.ids, self.records = {}, []

    def derive_formid(self, site: str, key: str) -> int:
        return self.ids.setdefault((site, key), 0x1000 + len(self.ids))

    def add_record(self, sig: str, data: bytes) -> None:
        self.records.append((sig, data))


class _Sounds:
    """Sounds' stand-in: every SOUN has a file; a layer records its conditions."""

    def __init__(self):
        self.records = {0x10: {'FormID': '00000010', 'EditorID': 'NPCGeckoIdleLick'}}
        self.layers = {}

    def descriptor(self, fnv: int) -> int:
        return 0x2000 + fnv

    def layer(self, fnv: int, key: str, edid: str, conditions: bytes) -> int:
        """A numbered layer remembering its name and conditions."""
        self.layers[key] = (edid, conditions)
        return 0x3000 + len(self.layers)


class _Builder:
    def __init__(self):
        self.writer, self.sounds, self.counts = _Writer(), _Sounds(), Counter()


class _Rig:
    folder, project = 'creatures\\nvgecko', 'FNVGecko'


def sound_set(fid: str, edid: str, entries: list) -> dict:
    """An FNV creature carrying sound `entries` [(type, SOUN, chance)]."""
    rec = {'FormID': fid, 'EditorID': edid, 'SoundTypeCount': str(len(entries))}
    for i, (kind, soun, chance) in enumerate(entries):
        rec.update({f'SoundType[{i}].Type': str(kind), f'SoundType[{i}].Sound': f'{soun:08X}',
                    f'SoundType[{i}].Sound.Chance': str(chance)})
    return rec


def creatures() -> dict:
    """A fire gecko set (feet, attack at 50, death, loop), a green one (attack), a templated and an inheriting one."""
    recs = [sound_set(GECKO, 'AudioFire', [(0, 0x20, 100), (6, 0x21, 50), (8, 0x22, 100), (11, 0x23, 100)]),
            sound_set(GREEN, 'AudioGreen', [(6, 0x24, 0)]),
            {'FormID': TEMPLATED, 'EditorID': 'Young', 'TPLT.Template': INHERITS, 'ACBS.TemplateFlags': '64'},
            {'FormID': INHERITS, 'EditorID': 'Fire', 'CSCR.InheritSound': GECKO}]
    return {int(r['FormID'], 16): r for r in recs}


def test_a_set_comes_through_the_model_template_and_inherited_sounds():
    """A model template's set, itself inherited (CSCR), is the creature's."""
    sounds = S.CreatureSounds(_Builder(), creatures())
    assert sounds.source(creatures()[0x300])['EditorID'] == 'AudioFire'
    assert sounds.source({'FormID': '00000500', 'EditorID': 'Mute'}) is None


def test_types_keep_a_zero_chance():
    """Chance 0 (never) is not read as the default 100."""
    assert S.types(creatures()[0x200]) == {6: (0x24, 0)}


def test_the_loop_replaces_inherited_sounds_after_nam8():
    """CSCR goes; CS2H 1, CS2D, CS2E, CS2F follow NAM8; without a loop the actor sounds just go."""
    subs = b''.join(pack_subrecord(t, b'\1\0\0\0') for t in ('EDID', 'NAM8', 'CSCR', 'DPLT'))
    out = [(t, d) for t, d in subrecords(S.with_loop(0x99)(subs))]
    assert [t for t, _ in out] == [b'EDID', b'NAM8', b'CS2H', b'CS2D', b'CS2E', b'CS2F', b'DPLT']
    assert struct.unpack('<I', out[3][1])[0] == 0x99 and out[5][1] == b'\0'
    assert [t for t, _ in subrecords(S.with_loop(0)(subs))] == [b'EDID', b'NAM8', b'DPLT']


def test_a_rig_plays_a_compound_per_type_with_a_keyed_layer_per_set():
    """Attack layers both sets, each on its keyword (GetRandomPercent under 100); the loop is the NPC's, not the
    graph's; text keys and death name the compounds."""
    builder = _Builder()
    sounds = S.CreatureSounds(builder, creatures())
    rig = sounds.rig(_Rig, creatures().values())
    assert rig.of('Enum: Attack') == 'SoundPlay.FNV_FNVGecko_Attack' and rig.death == 'SoundPlay.FNV_FNVGecko_Death'
    assert rig.feet and rig.of('Enum: Idle') is None and rig.of('Hit') is None
    assert rig.of('Sound: npcgeckoidlelick') == 'SoundPlay.FNV_NPCGeckoIdleLick'
    assert not any(key.endswith(' 11') for key in builder.sounds.layers)
    compounds = {dict(subrecords(d[24:]))[b"EDID"]: [v for t, v in subrecords(d[24:]) if t == b'DNAM']
                 for sig, d in builder.writer.records if sig == 'SNDR'}
    assert len(compounds[b'FNV_FNVGecko_Attack\0']) == 2
    edid, conditions = builder.sounds.layers['00000100 6']
    funcs = [struct.unpack_from('<H', d, 8)[0] for _, d in subrecords(conditions)]
    assert edid == 'FNV_AudioFire_Attack' and funcs == [S.HAS_KEYWORD, S.RANDOM_PERCENT]
    assert len(list(subrecords(builder.sounds.layers['00000100 0'][1]))) == 1


def test_a_keyword_list_is_made_after_the_packages_when_missing():
    """No KWDA: KSIZ 1 and KWDA follow the last PKID; an existing list just grows."""
    subs = b''.join(pack_subrecord(t, b'\1\0\0\0') for t in ('EDID', 'AIDT', 'PKID', 'PKID', 'CNAM'))
    assert [t for t, _ in subrecords(S.with_keyword(9)(subs))] == [b'EDID', b'AIDT', b'PKID', b'PKID', b'KSIZ',
                                                                    b'KWDA', b'CNAM']
