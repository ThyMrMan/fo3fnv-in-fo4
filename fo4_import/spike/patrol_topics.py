"""FNV patrol points' scripts and topics, run by Fallout 4's patrol arrival topic (REFR PDTO).

An FNV patrol point runs its embedded script on the patroller that reaches
it and has it say the point's topic. FO4's patrol data keeps the topic a
patroller says on arriving (PDTO, Topic Ref), and a said line runs its INFO's
fragments on the speaker. So each such point names a silent topic of its own,
held by one start-game quest, whose one blank line runs the point's converted
script (`FALLOUTNV_PM__<FormID>`, which says the point's topic after it) or,
for a point with only a topic, F3NV_PatrolSay saying that topic.

See: docs/fork/fo4_pipeline.md#patrol-points
"""


from fo4_import.base.vmad import info_fragments, quest_fragments
from fo4_import.base.writer import pack_quest, pack_topic
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from fo4_import.spike.script import PATROL, prefix
from tes5_import.packages.scripts_falloutnv import has_code

#: Ledger site of the arrival topics, their lines and their quest (keys: the FNV patrol point).
SITE = 'FNV patrol topic'
#: The quest holding the arrival topics.
EDID = 'FNV_TES4PatrolTopics'
#: The topic-only patrol point's script.
SAY_SCRIPT = 'F3NV_PatrolSay'
#: The export key every FNV patrol point carries (its idle time).
PATROL_KEY = 'Patrol.IdleTime'


def _acts(rec: dict) -> bool:
    """Whether FNV reference `rec` is a patrol point with a script or a topic."""
    topic = int(rec.get('Patrol.Topic') or '0', 16)
    return PATROL_KEY in rec and (has_code(rec.get('Patrol.Script') or '') or bool(topic))


class PatrolTopics:
    """The arrival topics of FNV's patrol points: `arrivals` {FNV point FormID: FO4 topic} for the points' PDTO,
    and `write()` writing those of the built points."""

    def __init__(self, builder, export_dir):
        """Each patrol point with a script or topic, and its arrival topic's FormID, hashed from the point."""
        self.builder, writer = builder, builder.writer
        self.quest = writer.derive_formid(SITE, EDID)
        self.points = {int(r['FormID'], 16): r for r in export_records(export_dir, 'REFR') if _acts(r)}
        self.arrivals = {fid: writer.derive_formid(SITE, f'DIAL {fid:08X}') for fid in self.points}

    def _script(self, rec: dict) -> 'tuple | None':
        """(script, object properties) the arrival line of patrol point `rec` runs; None when it has nothing to run
        (its script was not converted, its topic was not built)."""
        scripts = self.builder.scripts
        name = f'{prefix(PATROL)}{rec["FormID"].upper()}'
        if scripts.dir and (scripts.dir / f'{name}.psc').exists():
            scripts.used.append(name)
            return name, scripts.properties(name)
        dial = self.builder.say.dials.get((rec.get('Patrol.Topic') or '').upper(), {})
        topic = scripts.named_lower().get((dial.get('EditorID') or '').lower())
        return (SAY_SCRIPT, {'Arrival': topic}) if topic else None

    def _topic(self, fid: int, script: 'tuple | None') -> bytes:
        """The arrival topic of patrol point `fid`: one blank line running `script` (name, properties) as it ends;
        without one the line runs nothing, as the point's PDTO still names the topic."""
        info = self.builder.writer.derive_formid(SITE, f'INFO {fid:08X}')
        begin = 'Fragment_1' if script and script[0] != SAY_SCRIPT else None
        vmad = info_fragments(script[0], script[1], begin=begin, end='Fragment_0') if script else b''
        dial = R.pack_dial(self.arrivals[fid], f'FNV_TES4PatrolTopic_{fid:08X}', self.quest, R.TOPIC_CUSTOM, 1)
        return pack_topic(dial, self.arrivals[fid], [R.pack_info(info, 0, ('',), vmad=vmad)])

    def write(self) -> None:
        """Write the quest and the arrival topics of the patrol points the build places (its references)."""
        topics = []
        for fid, rec in sorted(self.points.items()):
            if f'{fid:08X}' not in self.builder.ref_ids:
                continue
            script = self._script(rec)
            self.builder.counts['patrol point with nothing to run'] += script is None
            topics.append(self._topic(fid, script))
        if topics:
            record = R.pack_fnv_quest(self.quest, EDID, '', 0, quest_fragments('', []), [], [], [], True)
            self.builder.writer.add_record('QUST', pack_quest(record, self.quest, (), topics))
            self.builder.counts['patrol arrival topics'] = len(topics)
