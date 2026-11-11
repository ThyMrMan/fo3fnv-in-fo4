"""FNV quest objectives on the FO4 QUST: a target's alias id comes from its authored place, not what is built.

See: docs/fork/fo4_tool_audit.md#formids
"""

import struct

from fo4_import.spike import quest as Q

#: Two objectives: the first targets A then B, the second B again then C.
QUEST = {'FormID': '00012345', 'Objective[0].Index': '10', 'Objective[0].Text': 'Find A',
         'Objective[0].Target[0].FormID': '0000000a', 'Objective[0].Target[1].FormID': '0000000B',
         'Objective[1].Index': '20', 'Objective[1].Target[0].FormID': '0000000B',
         'Objective[1].Target[1].FormID': '0000000C'}


def test_a_target_keeps_its_alias_id_whichever_targets_are_built():
    """C is alias first+2 whether A is built or not; an unbuilt target leaves its id unused."""
    every = Q.objectives(QUEST, {'0000000A': 1, '0000000B': 2, '0000000C': 3}, first=1)
    assert every == ([(10, 'Find A', [1, 2]), (20, '', [2, 3])],
                     [(1, 'Target0000000A', 1), (2, 'Target0000000B', 2), (3, 'Target0000000C', 3)])
    some = Q.objectives(QUEST, {'0000000C': 3}, first=1)
    assert some == ([(10, 'Find A', []), (20, '', [3])], [(3, 'Target0000000C', 3)])


def test_a_mod_plugin_mirrors_what_its_masters_conditions_test(monkeypatch):
    """A master's line tests objective 10 and variable 0 of its quest: the mod's copy of the script mirrors both.

    See: docs/fork/fo4_pipeline.md#master-mirrors
    """
    from script_convert import context_setup, pipeline, target
    from tes5_import.base.conditions import GET_QUEST_VARIABLE
    done = struct.pack('<B3xfHHIIII', 0, 1.0, 420, 0, 0x0E5123, 10, 0, 0).hex()
    qvar = struct.pack('<B3xfHHIIII', 0, 1.0, GET_QUEST_VARIABLE, 0, 0x0E5123, 0, 0, 0).hex()
    master = {'QUST': [{'FormID': '000E5123', 'EditorID': 'VMQTops', 'SCRI': '000E5124'}],
              'SCPT': [{'FormID': '000E5124', 'EditorID': 'VMQTopsScript', 'Variable[0].Index': '0',
                        'Variable[0].Name': 'bMet'}],
              'INFO': [{'Condition[0].Raw': done, 'Condition[1].Raw': qvar}], 'PACK': []}
    monkeypatch.setattr(context_setup, 'export_dirs_with_masters', lambda d: ['master', d])
    monkeypatch.setattr(context_setup, 'load_records', lambda d, sigs: {s: master.get(s, []) for s in sigs})
    monkeypatch.setattr(pipeline, 'export_is_fallout', lambda d: True)
    monkeypatch.setattr(target, 'is_fallout4', lambda: True)
    objectives, quest_vars = pipeline._mirrors('mod', {'INFO': [], 'QUST': []})
    assert objectives == {('vmqtops', 10): {'Done': 'TES4ObjDone_VMQTops_10'}}
    assert quest_vars == {('vmqtops', 'bmet'): 'TES4QVar_VMQTops_bMet', ('vmqtopsscript', 'bmet'): 'TES4QVar_VMQTops_bMet'}
