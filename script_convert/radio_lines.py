"""FO3/FNV radio lines' fragment scripts on Fallout 4: their messages show only while the player hears the station.

FNV runs a radio line's scripts only as the player listens; FO4's station
scenes say every line whether anyone listens, so a line's ShowMessage
(Camp Guardian's) fired as a notification everywhere. In a radio line
(dialog type 7) each message shown is guarded by F3NV_Radio.Heard; its
other statements (a playlist's song history) run as FO4's stations do.

See: docs/fork/fo4_radio.md#heard
"""

#: FO3/FNV INFO dialog type Radio.
RADIO = '7'
#: A converted ShowMessage (constants_falloutnv 'showmessage').
SHOW = '.Show('


def is_radio(rec: dict) -> bool:
    """Whether FO3/FNV INFO `rec` is a radio line."""
    return rec.get('DATA.DialogType') == RADIO


def gated(lines: list) -> list:
    """Fragment script `lines` with each message shown guarded by F3NV_Radio.Heard."""
    out = []
    for line in lines:
        if SHOW in line:
            indent = line[:len(line) - len(line.lstrip())]
            out += [f'{indent}If F3NV_Radio.Heard(akSpeakerRef)', f'  {line}', f'{indent}EndIf']
        else:
            out.append(line)
    return out
