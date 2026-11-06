"""FO3/FNV GetTalkedToPC on Fallout 4: a GREETING line beginning marks its speaker (helper actor value TalkedToPC),
which the converted conditions read, since Fallout 4's own flag is set by the silent line opening every talk.

See: docs/fork/fo4_pipeline.md#talked-to-pc
"""

from script_convert.target import is_fallout4

#: FO3/FNV GREETING topic.
GREETING = '000000C8'


def greeted(rec: dict) -> list:
    """Begin-fragment lines marking FO3/FNV INFO `rec`'s speaker as talked to, for a GREETING line on Fallout 4."""
    if not is_fallout4() or (rec.get('ParentDIAL') or '').upper() != GREETING:
        return []
    return ['  TES4Polyfill.Greeted(akSpeakerRef)']
