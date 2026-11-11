"""FNV quest objectives on the FO4 QUST: a target's alias id comes from its authored place, not what is built.

See: docs/fork/fo4_tool_audit.md#formids
"""

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
