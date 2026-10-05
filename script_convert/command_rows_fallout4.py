"""Fallout 4's rows for the commands whose Skyrim row emits a call Fallout 4 lacks.

Keyed by the Skyrim `Cmd` itself, so every spelling that shares a row takes
the Fallout 4 row too; `emit_row` picks it when Fallout 4 is the target.
Actor values are ActorValue form properties (`target.av_property`) declared
through `self_type`; behavior-graph events go through PlayAnimation.

See: docs/fork/fo4_spikes.md#spike-3-target
"""

from script_convert.command_rows import ACTOR, AV, COMMAND_ROWS, RAW, Cmd
from script_convert.target import av_property


def _av(name: str) -> tuple:
    """`self_type` declaring the ActorValue property for actor value `name`."""
    return av_property(name), 'ActorValue'


#: TES4 command -> its Fallout 4 row, then keyed by the Skyrim row it replaces.
FALLOUT4_ROWS = {COMMAND_ROWS[name]: row for name, row in {
    'getarmorrating': Cmd(f'{{ref}}.GetValue({av_property("DamageResist")})', ACTOR,
                          self_type=_av('DamageResist'), flags='actor_only'),
    'setcurrenthealth': Cmd(f'{{ref}}.SetValue({av_property("Health")}, {{a0}})', RAW,
                            self_type=_av('Health'), defaults={0: '0'}),
    'resethealth': Cmd(f'{{ref}}.RestoreValue({av_property("Health")}, 9999)', AV,
                       self_type=_av('Health'), flags='actor_only branch_only'),
    'advancepclevel': Cmd(f'Game.GetPlayer().ModValue({av_property("Level")}, 1)', self_type=_av('Level')),
    'setforcerun': Cmd(f'{{ref}}.SetValue({av_property("SpeedMult")}, {{?01}})', ACTOR, self_type=_av('SpeedMult'),
                       defaults={0: '0'}, arms=('150.0', '100.0'), flags='actor_only branch_only'),
    'gethealthpercentage': Cmd(f'{{ref}}.GetValuePercentage({av_property("Health")})', ACTOR,
                               self_type=_av('Health'), flags='actor_only zero_arg'),
    'player.gethealthpercentage': Cmd(f'Game.GetPlayer().GetValuePercentage({av_property("Health")})',
                                      self_type=_av('Health'), flags='zero_arg'),
    'pickidle': Cmd('{ref}.PlayAnimation("{s0}")', ACTOR, defaults={0: 'IdleForceDefaultState'}, flags='zero_arg'),
    'playidle': Cmd('{ref}.PlayAnimation("{s0}")', ACTOR, defaults={0: 'IdleForceDefaultState'}),
}.items()}
