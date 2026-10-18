"""The interval a converted GameMode poll re-arms at.

An authored quest delay (FO3/FNV `DATA.Delay`) wins; otherwise the interval
follows what the script's body does with time.

See: docs/commentary/script_convert.md#poll-interval
"""

from script_convert.target import arm_update, is_fallout4

#: Fastest Papyrus poll the converter emits; an authored delay never goes below it.
MIN_INTERVAL = 0.1
#: FO3/FNV's quest script delay when the quest authors none (seconds).
QUEST_DEFAULT = 5.0
#: Fallout 4: the quest-script property its poll re-arms at, which SetQuestDelay sets for good.
QUEST_DELAY_VAR = 'TES4_Delay'


def update_interval(sc, quest: bool = False) -> str:
    """The RegisterForSingleUpdate literal for one script's poll; a Fallout 4 `quest` script's runs at the source
    game's quest delay.
    See: docs/fork/performance.md#papyrus
    """
    if sc.quest_delay > 0:
        return float_literal(max(sc.quest_delay, MIN_INTERVAL))
    if quest and is_fallout4():
        return float_literal(QUEST_DEFAULT)
    if sc.uses_getsecondspassed or sc.moves_in_poll:
        return '0.1'
    if sc.uses_say_timer:
        return '0.15'
    if sc.uses_timer:
        return '0.25'
    return '0.5'


def quest_delay_arm(quest_ref: str, value: str) -> str:
    """`set Q.fQuestDelayTime to N`: one update of the quest's poll after N seconds, 5 for 0 or less.

    Never RegisterForUpdate: it repeats every frame until unregistered, and
    shipped in 45 scripts. The converted OnUpdate re-arms itself.
    """
    try:
        fval = float(value)
    except ValueError:
        return f'{arm_update(value, quest_ref + ".")}  ;fQuestDelayTime'
    if fval <= 0:
        return f'{arm_update(float_literal(QUEST_DEFAULT), quest_ref + ".")}  ;fQuestDelayTime = 0 (TES4 default cadence)'
    return f'{arm_update(f"{fval:g}", quest_ref + ".")}  ;fQuestDelayTime'


def float_literal(value: float) -> str:
    """A Papyrus Float literal: never an integer spelling, which the checker rejects."""
    text = f'{value:g}'
    return text if ('.' in text or 'e' in text) else text + '.0'


def quest_script_delays(by_type: dict) -> dict:
    """SCPT FormID string -> authored quest delay in seconds, where one is written."""
    out = {}
    for rec in by_type.get('QUST', []):
        delay = float(rec.get('DATA.Delay') or 0)
        scri = rec.get('SCRI') or ''
        if delay > 0 and scri:
            out[scri.upper()] = delay
    return out
