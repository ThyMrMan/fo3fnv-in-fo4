"""Fallout 4 runs a line's Begin fragment once per response; FO3/FNV ran a line's result scripts once.

A line with several responses counts them in two script variables: its
FO3/FNV Begin result runs on the first response, and its End result (with its
service menu and done calls) once the last response has begun, whether
Fallout 4 runs the End fragment after each response or only after the last.
A pause over RESPONSE_GAP seconds starts a new play, so a line cut short runs
whole the next time.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from script_convert.target import is_fallout4

#: Seconds between two responses' Begin past which the line is playing again.
RESPONSE_GAP = 30.0
#: The fragment script's response counter and the real time its last response began.
COUNTER, STAMP = 'TES4Response', 'TES4ResponseAt'


def response_count(rec: dict) -> int:
    """A line's responses to count: on Fallout 4 when over one, else 0."""
    count = int(rec.get('ResponseCount', 0) or 0)
    return count if is_fallout4() and count > 1 else 0


def declarations(count: int) -> list:
    """The counter's script variables, when the line counts responses."""
    return [f'Int {COUNTER}', f'Float {STAMP}', ''] if count else []


def first_response(lines: list, count: int) -> list:
    """Begin fragment `lines` (indented) run on the first response; the counter steps before them."""
    if not count:
        return list(lines)
    step = ['  Float TES4Now = Utility.GetCurrentRealTime()',
            f'  If {COUNTER} >= {count} || TES4Now - {STAMP} > {RESPONSE_GAP}', f'    {COUNTER} = 0', '  EndIf',
            f'  {COUNTER} += 1', f'  {STAMP} = TES4Now']
    return step + _gated(lines, f'{COUNTER} == 1')


def last_response(lines: list, count: int) -> list:
    """End fragment `lines` (indented) run once the last response has begun."""
    return _gated(lines, f'{COUNTER} == {count}') if count else list(lines)


def _gated(lines: list, test: str) -> list:
    """`lines` inside `If test`; nothing for no lines."""
    return [f'  If {test}', *('  ' + line for line in lines), '  EndIf'] if lines else []
