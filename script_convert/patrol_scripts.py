"""FO3/FNV patrol-point scripts as the fragment of the marker's arrival line.

FO3/FNV runs a patrol point's embedded script on the patrolling actor that
reaches it. Skyrim's patrol data names a topic the patroller says when it
arrives (Reference > Patrol Data), and a said line runs its INFO's fragment
with `akSpeakerRef` as the speaker. So each scripted marker gets a silent
topic of its own whose INFO runs `<NS>_PM__<FormID>`, a TopicInfo fragment:
the converted body as the silent line ends (a Say inside it is not lost to
the line still playing), then the marker's own topic, if it had one.

See: docs/commentary/tes5_import_package.md#patrol-points
"""

from script_convert.constants import script_prefix
from script_convert.converter import ScriptConverter
from script_convert.scro_refs import add_scro_ref, resolve_scro_aliases, scro_list
from script_convert.symbols import property_declarations


def patrol_script_name(formid: str) -> str:
    """The PM_ script name of the patrol marker with source FormID `formid`."""
    return f'{script_prefix("_PM__")}{formid.upper()}'


def _source(rec: dict, xref) -> str:
    """The marker's embedded script, then `Say <topic>` for its own topic."""
    topic = xref.formid_to_edid.get((rec.get('Patrol.Topic') or '').upper(), '')
    return (rec.get('Patrol.Script') or '') + (f'\nSay {topic}\n' if topic else '')


def _convert_patrol(rec: dict, xref) -> tuple:
    """(converter, body lines) of a patrol point's script, run on the arriving actor (`akSpeakerRef`)."""
    conv = ScriptConverter(xref)
    source = _source(rec, xref)
    refs = scro_list(rec, 'Patrol.')
    for fid in refs:
        add_scro_ref(conv, fid, xref)
    conv.set_scro_aliases(resolve_scro_aliases(source, refs, xref))
    return conv, conv.convert_fragment(source, 'TopicInfo')


def patrol_psc(rec: dict, xref) -> str:
    """The Papyrus of one patrol marker's arrival fragment."""
    conv, body = _convert_patrol(rec, xref)
    head = [f'ScriptName {patrol_script_name(rec["FormID"])} extends TopicInfo Hidden', '']
    props = property_declarations(dict(conv.sc.property_refs), set())
    begin = ['Function Fragment_1(ObjectReference akSpeakerRef)',
             '  TES4Polyfill.LineBegan(akSpeakerRef, 0.0)', 'EndFunction', '']
    end = ['Function Fragment_0(ObjectReference akSpeakerRef)',
           '  TES4Polyfill.LineEnded(akSpeakerRef, 0.0)'] + body + ['EndFunction', '']
    return '\n'.join(head + props + [''] + begin + end + conv.get_cell_family_helpers())


def patrol_property_refs(rec: dict, xref) -> dict:
    """{property: Papyrus type} the marker's fragment declares from its body."""
    return dict(_convert_patrol(rec, xref)[0].sc.property_refs)
