"""Fallout 4 runs a line's Begin fragment once per response; FO3/FNV ran a line's result scripts once.

A line with several responses counts them in the helper plugin's
TES4_LineResponses (TES4Polyfill.ResponseBegan, LineOver), as a topic info
fragment's own variables do not last between calls: its FO3/FNV Begin result
runs on the first response, and its End result (with its service menu and
done calls) once the line is over: when the last response has begun, or when
no other response begins within the helper's wait after an End fragment. A
choice menu's answer runs Begin and End once for the whole line, a scene's
Dialogue action Begin per response. A pause over the helper's gap starts a
new play, so a line cut short runs whole the next time.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from script_convert.target import is_fallout4

#: End fragment variable: the line is over.
OVER = 'TES4LineOver'


def response_count(rec: dict) -> int:
    """A line's responses to count: on Fallout 4 when over one, else 0."""
    count = int(rec.get('ResponseCount', 0) or 0)
    return count if is_fallout4() and count > 1 else 0


def first_response(lines: list, count: int) -> list:
    """Begin fragment `lines` (indented) run on the first response; the response is counted before them."""
    if not count:
        return list(lines)
    began = f'TES4Polyfill.ResponseBegan(Self, {count})'
    return [f'  If {began} == 1', *('  ' + line for line in lines), '  EndIf'] if lines else [f'  {began}']


def line_over(count: int, needed: bool) -> list:
    """End fragment start setting OVER, when counting and `needed`."""
    return [f'  Bool {OVER} = TES4Polyfill.LineOver(Self, {count})'] if count and needed else []


def last_response(lines: list, count: int) -> list:
    """End fragment `lines` (indented) run once the line is over (line_over() sets it)."""
    if not count or not lines:
        return list(lines)
    return [f'  If {OVER}', *('  ' + line for line in lines), '  EndIf']
