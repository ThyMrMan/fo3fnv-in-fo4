"""FNV talking activators on Fallout 4: line conditions, talking-as lists, the TACT record.

See: docs/fork/fo4_pipeline.md#talking-activators
"""
from collections import Counter
from types import SimpleNamespace

from fo4_import.spike import conditions as C
from fo4_import.spike.talking_activators import Talkers, pack_tact, speakers_of
from tes5_import.base.tes5_reader import subrecords

RAMOS, BENNY, INTERCOM, LIST = 0x100, 0x200, 0x300, 0x900


def cond(func, p1=0, value=1.0, op=0x00):
    """A parsed FNV Subject condition."""
    return {'op_flags': op, 'value': value, 'func': func, 'p1': p1, 'p2': 0, 'run_on': 0, 'ref': 0, 'global': 0}


def outcome(conds, facts):
    """Whether `conds` (AND of OR groups) pass on a speaker whose GetIsID and IsInList results are `facts`."""
    def result(c):
        """One condition's outcome."""
        key = (c['func'], c['p1'])
        return C.compare(c, float(facts.get(key, 0.0)))
    return all(any(result(c) for c in group) for group in C.groups(conds))


def test_an_intercom_line_plays_through_the_talker_and_not_face_to_face():
    """GetIsID Ramos + talking through == 1: the talker in Ramos's list says it, Ramos himself does not."""
    form_map = {(C.TALKING_AS, RAMOS): LIST}
    conds = C.talking_through([cond('GetIsID', RAMOS), cond(C.THROUGH)], form_map)
    talker = {('IsInList', (C.TALKING_AS, RAMOS)): 1}
    ramos = {('GetIsID', RAMOS): 1, ('IsInList', (C.TALKING_AS, RAMOS)): 1}
    assert outcome(conds, talker) and not outcome(conds, ramos)


def test_a_face_to_face_line_stays_off_the_intercom():
    """GetIsID Benny + talking through == 0: Benny says it, his talker does not."""
    form_map = {(C.TALKING_AS, BENNY): LIST}
    conds = C.talking_through([cond('GetIsID', BENNY), cond(C.THROUGH, value=0.0)], form_map)
    assert outcome(conds, {('GetIsID', BENNY): 1, ('IsInList', (C.TALKING_AS, BENNY)): 1})
    assert not outcome(conds, {('IsInList', (C.TALKING_AS, BENNY)): 1})


def test_a_line_naming_no_talked_through_actor_is_unchanged():
    """Without a talking-as list for the line's actor, the conditions pass through as they are."""
    conds = [cond('GetIsID', BENNY), cond(C.THROUGH)]
    assert C.talking_through(conds, {}) == conds


def test_a_talker_speaking_as_one_actor_starts_in_its_list():
    """The list holds the actor's base, then the talkers that speak only as it."""
    talkers = Talkers.__new__(Talkers)
    talkers.made = {INTERCOM: (0x1300, '', (0,) * 6), INTERCOM + 1: (0x1301, '', (0,) * 6)}
    talkers.speaks_as = {INTERCOM: {RAMOS}, INTERCOM + 1: {RAMOS, BENNY}}
    assert talkers.members(RAMOS, {RAMOS: 0x1100}) == [0x1100, 0x1300]


def test_pairs_name_talkers_by_their_editor_ids():
    """scan_pairs' (EditorID lower, actor hex) pairs map to {talker: {actors}}; a station is not a talker."""
    talkers = {INTERCOM: {'EditorID': 'HVIntercomUseless'}}
    pairs = {('hvintercomuseless', '00000100'), ('somestation', '00000200')}
    assert speakers_of(pairs, talkers) == {INTERCOM: {RAMOS}}


def test_a_talker_is_written_in_vanillas_order_with_its_voice():
    """EDID VMAD OBND FULL MODL PNAM FNAM VNAM, as vanilla's scripted intercoms."""
    rec = pack_tact(0x1300, 'FNV_X', 'Intercom', 'x.nif', (0,) * 6, b'v', 0x77)
    tags = [t for t, _ in subrecords(rec[24:])]
    assert tags == [b'EDID', b'VMAD', b'OBND', b'FULL', b'MODL', b'PNAM', b'FNAM', b'VNAM']


def test_the_talkers_voice_is_its_actors_when_they_share_one():
    """One shared actor voice wins; otherwise the talker's own VNAM."""
    talkers = Talkers.__new__(Talkers)
    talkers.builder = SimpleNamespace(npcs=SimpleNamespace(voices=SimpleNamespace(of=lambda v: v + 1)),
                                      counts=Counter())
    talkers.voices, talkers.speaks_as = {RAMOS: 0x50, BENNY: 0x60}, {INTERCOM: {RAMOS}, INTERCOM + 1: {RAMOS, BENNY}}
    assert talkers.voice(INTERCOM, {'VNAM': '00000070'}) == 0x51
    assert talkers.voice(INTERCOM + 1, {'VNAM': '00000070'}) == 0x71
