"""FO3/FNV patrol points: Skyrim's own patrol data, the embedded script run by the arrival topic.

A FO3/FNV patrol point (a REFR on a Patrol package's linked chain) carries an
idle time, an idle, an embedded script and a topic. Skyrim's REFR keeps the
idle time, the Patrol Script Marker and a topic natively (XPRD XPPA INAM
PDTO, 3,179 vanilla markers), and a patroller says that topic as it arrives.
A marker with a script names a silent topic of its own instead, whose one
INFO runs the marker's PM_ fragment on the arriving actor; that fragment says
the marker's own topic after the script.

See: docs/commentary/tes5_import_package.md#patrol-points
"""

import os
import struct

from ..base.owned_records import WELL_KNOWN_PROPERTIES
from ..base.text_reader import get_float, get_formid, parse_record_block
from ..base.writer import pack_group, pack_subrecord
from .scripts_falloutnv import has_code

#: The key every exported patrol point carries (its XPRD idle time).
PATROL_KEY = 'Patrol.IdleTime'

#: Scripted patrol marker REFR FormID (upper hex) -> (topic FormID, INFO FormID, fragment properties).
_PATROL_TOPICS: dict = {}

#: The quest owning the arrival topics.
PATROL_QUEST = 'TES4PatrolTopics'


def is_patrol_point(rec: dict) -> bool:
    """Whether a reference is a FO3/FNV patrol point."""
    return PATROL_KEY in rec


def has_patrol_script(rec: dict) -> bool:
    """Whether a patrol point's embedded script does anything."""
    return has_code(rec.get('Patrol.Script') or '')


def patrol_subrecords(rec: dict) -> bytes:
    """XPRD XPPA INAM PDTO, Skyrim's patrol data, for a patrol point; b'' otherwise.

    The idle stays 0 as on every vanilla marker: a FO3/FNV IDLE names no
    Skyrim animation. The topic is a Topic Ref PDTO: a scripted marker's
    arrival topic, else its own, 0 when there is none.
    """
    if not is_patrol_point(rec):
        return b''
    planned = _PATROL_TOPICS.get((rec.get('FormID') or '').upper())
    topic = planned[0] if planned else get_formid(rec, 'Patrol.Topic')
    return (pack_subrecord('XPRD', struct.pack('<f', get_float(rec, PATROL_KEY)))
            + pack_subrecord('XPPA', b'') + pack_subrecord('INAM', bytes(4))
            + pack_subrecord('PDTO', struct.pack('<II', 0, topic)))


def patrol_scan_source(rec: dict, formid_to_edid: dict) -> str:
    """A patrol point's script and `Say <topic>`, for the call-site scans."""
    topic = formid_to_edid.get((rec.get('Patrol.Topic') or '').upper(), '')
    return (rec.get('Patrol.Script') or '') + (f'\nSay {topic}\n' if topic else '')


def load_patrol_points(export_dir: str) -> list:
    """The REFR records carrying patrol data, without parsing every other REFR."""
    path = os.path.join(export_dir, 'REFR.txt')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8', errors='replace') as f:
        chunks = f.read().split('---RECORD_BEGIN---')
    return [parse_record_block(c.splitlines()) for c in chunks if f'\n{PATROL_KEY}=' in c]


def plan_patrol_topics(by_type: dict, xref, writer) -> int:
    """Reserve each scripted patrol marker's arrival topic and INFO, binding its fragment's properties; how many.

    script_convert is imported here, not at module scope: its converter
    imports the importer's dialogue package, a cycle at load.
    """
    from script_convert.patrol_scripts import patrol_property_refs
    from ..dialogue.converter import bind_script_properties
    _PATROL_TOPICS.clear()
    for rec in by_type.get('REFR', ()):
        fid = (rec.get('FormID') or '').upper()
        if not is_patrol_point(rec) or not has_patrol_script(rec):
            continue
        props = bind_script_properties(patrol_property_refs(rec, xref), xref, WELL_KNOWN_PROPERTIES)
        _PATROL_TOPICS[fid] = (writer.derive_formid('PATROL_DIAL', fid),
                               writer.derive_formid('PATROL_INFO', fid), props)
    return len(_PATROL_TOPICS)


def build_patrol_topics(writer, master_index=None) -> set:
    """Write the arrival topics planned by plan_patrol_topics under TES4PatrolTopics; {its FormID}, else empty.

    The dialogue modules and script_convert are imported here: both import
    the packages package, a cycle at load.
    """
    from script_convert.patrol_scripts import patrol_script_name
    from script_convert.pipeline import build_vmad_info_fragment
    from ..dialogue.arrest import blank_info
    from ..dialogue.converter import convert_DIAL, make_generic_quest
    if not _PATROL_TOPICS:
        return set()
    quest = make_generic_quest(writer, PATROL_QUEST, 'TES4 Patrol Topics', master_index)
    for marker, (dial_fid, info_fid, props) in sorted(_PATROL_TOPICS.items()):
        vmad = build_vmad_info_fragment(f'{info_fid:08X}', props, patrol_script_name(marker))
        dial = convert_DIAL({'RecordFlags': '0'}, info_count=1, dlbr_fid=0, quest_fid=quest,
                            category=0, subtype=0, snam=b'CUST', edid_override=f'TES4PatrolTopic_{marker}',
                            formid_override=dial_fid)
        writer.add_raw_group('DIAL', dial + pack_group(7, struct.pack('<I', dial_fid),
                                                         blank_info(info_fid, vmad=pack_subrecord('VMAD', vmad))))
    return {quest}
