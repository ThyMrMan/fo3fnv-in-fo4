"""The scene-step check: Dad's package starts a chat with the intercom, whose reply tests the listener."""

import struct

from fo4_import.base.vmad import package_fragments
from fo4_import.spike.packages import DIALOGUE_FRAGMENTS, DIALOGUE_SCRIPT
from fo4_import.spike.records import RUN_QUEST_ALIAS, pack_ctda
from tes5_import.base.tes5_reader import subrecords
from tests.test_preflight_audits import zs
from tools.esm.tes5_esm_reader import Sub, TES5Record
from tools.validate.preflight import scene_targets
from tools.validate.preflight.condition_diff import FO4
from tools.validate.preflight.plugin_index import PluginIndex

#: The own load-order index of the test plugin: one master.
OWN = 0x01000000

#: The quest, Dad and his reference, Jonas, the intercom and its reference, and Jonas's talking-as list.
QUEST, DAD, DAD_REF, JONAS, INTERCOM, INTERCOM_REF, TALKING_AS = (OWN | n for n in range(1, 8))

#: Dad's dialogue package, the chat scene, its step's topic, the reply line and another line.
PACKAGE, SCENE, TOPIC, REPLY, OTHER = OWN | 0x20, OWN | 0x30, OWN | 0x40, OWN | 0x41, OWN | 0x42

#: The source FormID of the reply line, as the ledger pairs it.
SOURCE_REPLY = 0x00031D43

#: Condition function indexes by name.
FUNCS = {name: i for i, name in FO4.names.items()}


def u32(value):
    """Four little-endian bytes."""
    return struct.pack('<I', value)


def rec(sig, fid, subs=(), parent_dial=0):
    """A built Fallout 4 record with `subs` as (signature, bytes) pairs."""
    return TES5Record(sig, 0, 0, fid, 131, [Sub(t, d) for t, d in subs], parent_dial=parent_dial)


def ctda(name, p1, alias=None, op_flags=0):
    """One condition on the speaker, or on quest alias `alias`."""
    raw = pack_ctda(op_flags, 1.0, FUNCS[name], p1, run_on=RUN_QUEST_ALIAS if alias is not None else 0,
                    param3=-1 if alias is None else alias)
    return [(t.decode(), d) for t, d in subrecords(raw)][0]


def alias(ident, name, forced=0):
    """One reference alias's subrecords: optional and empty, or forced to `forced`."""
    return ([('ALST', u32(ident)), ('ALID', zs(name)), ('FNAM', u32(2 if not forced else 0x80))]
            + ([('ALFR', u32(forced))] if forced else []) + [('ALED', b'')])


def plugin(reply_conditions, other_conditions=None):
    """Dad's dialogue package starts the chat scene with the intercom as listener; the scene's one step says
    TOPIC, holding the reply (and another line when `other_conditions` is given)."""
    lines = [rec('INFO', REPLY, reply_conditions, TOPIC)]
    lines += [rec('INFO', OTHER, other_conditions, TOPIC)] if other_conditions is not None else []
    vmad = package_fragments(DIALOGUE_SCRIPT, DIALOGUE_FRAGMENTS, {'Chat': SCENE, 'TES4ChatTarget': INTERCOM_REF})
    return PluginIndex([
        rec('QUST', QUEST, [('EDID', zs('FNV_CG02'))] + alias(0, 'Speaker') + alias(1000, 'Listener')),
        rec('NPC_', DAD, [('EDID', zs('FNV_CG02Dad')), ('PKID', u32(PACKAGE))]),
        rec('ACHR', DAD_REF, [('NAME', u32(DAD))]),
        rec('NPC_', JONAS, [('EDID', zs('FNV_CG02Jonas'))]),
        rec('TACT', INTERCOM, [('EDID', zs('FNV_CG02DinerIntercom'))]),
        rec('REFR', INTERCOM_REF, [('NAME', u32(INTERCOM))]),
        rec('FLST', TALKING_AS, [('EDID', zs('TES4TalkingAs_Jonas')), ('LNAM', u32(JONAS)), ('LNAM', u32(INTERCOM))]),
        rec('PACK', PACKAGE, [('EDID', zs('FNV_CG02DadTalkToJonasOnIntercom')), ('VMAD', vmad)]),
        rec('SCEN', SCENE, [('EDID', zs('FNV_CG02_Scene1')), ('ANAM', struct.pack('<H', 0)), ('ALID', u32(0)),
                            ('INAM', u32(1)), ('DATA', u32(TOPIC)), ('ANAM', b''), ('PNAM', u32(QUEST))]),
        rec('DIAL', TOPIC, [('EDID', zs('FNV_CG02_Scene1_0'))])] + lines, ('Fallout4.esm',), 'FNV_', True)


def audit(index):
    """{finding key: finding} of the check, the reply paired with its source line."""
    return {f.key: f for f in scene_targets.audit('Test.esm', index, {SOURCE_REPLY: {1: [REPLY]}}, [])}


def test_a_reply_whose_listener_test_the_intercom_passes_is_not_reported():
    """The intercom is not Jonas but is in his talking-as list."""
    assert audit(plugin([ctda('GetIsID', DAD), ctda('GetIsID', JONAS, 1000, op_flags=1),
                         ctda('IsInList', TALKING_AS, 1000)])) == {}


def test_a_step_whose_only_line_fails_its_listener_test_plays_nothing():
    """Without the talking-as test the reply wants Jonas as listener: the step is an error naming the source line."""
    found = audit(plugin([ctda('GetIsID', DAD), ctda('GetIsID', JONAS, 1000)]))
    step = found['conditions|Test.esm|scene-step|CG02_Scene1|1']
    assert step.severity == 'error' and 'Listener = CG02DinerIntercom' in step.summary
    assert step.detail == (f'INFO {REPLY:08X} (source 00031D43) fails GetIsID CG02Jonas on alias Listener == 1',)


def test_a_line_for_the_speaker_but_not_this_listener_is_a_review_when_another_line_plays():
    """Another line plays; the reply fits Dad but never the intercom."""
    found = audit(plugin([ctda('GetIsID', DAD), ctda('GetIsID', JONAS, 1000)], [ctda('GetIsID', DAD)]))
    assert [(k, f.severity) for k, f in found.items()] == [
        ('conditions|Test.esm|scene-line|CG02_Scene1|1|00031D43', 'review')]


def test_another_speakers_line_is_only_counted():
    """Jonas's own line in Dad's step fails its speaker test: by design, so no finding."""
    assert audit(plugin([ctda('GetIsID', JONAS)], [ctda('GetIsID', DAD)])) == {}


def test_a_step_whose_speaker_is_unknown_is_not_judged():
    """A scene started on quest start has no known speaker: every speaker test can pass."""
    index = plugin([ctda('GetIsID', JONAS)])
    index.by_fid[PACKAGE].subrecords[:] = [s for s in index.by_fid[PACKAGE].subrecords if s.type != 'VMAD']
    index.by_fid[SCENE].subrecords.append(Sub('FNAM', u32(1)))
    assert audit(index) == {}
