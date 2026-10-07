"""An FNV quest's scripted lines as FO4 Custom topics, for the cell spike.

FNV's Say/SayTo plays a topic's first line whose conditions pass, and Say
Once lines step through a chain. FO4's Say does the same with a Custom topic
(DATA 0, SNAM CUST) in a branch of its quest, as vanilla's MS09Branch. The
quest's Conversation-type topics (FNV DIAL type 1) become such topics; each
line keeps its responses, Say Once flag, conditions (forms through the cell;
GetQuestVariable as GetVMQuestVariable on the converted property) and its
converted result fragments. Lines with a condition that cannot convert are
left out and counted.

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

from pathlib import Path

from fo4_import.base.vmad import info_fragments
from fo4_import.base.writer import pack_topic
from fo4_import.spike import conditions as C
from fo4_import.spike import records as R
from tes5_import.base.text_reader import parse_export_file

#: FNV DIAL type of the topics scripts Say: Conversation.
CONVERSATION = '1'
#: FNV INFO DATA flag Say Once.
SAY_ONCE = 0x04
FRAGMENT_PREFIX = 'FALLOUTNV_TIF__'
#: CTDA operator bits: the comparison, OR with the next, use a global as the value.
COMPARE, OR, USE_GLOBAL = 0xE0, 0x01, 0x04
#: FNV GetQuestVariable and FO4's GetVMQuestVariable, which names the Papyrus property in its CIS2.
QUEST_VARIABLE, VM_QUEST_VARIABLE = 'GetQuestVariable', 'GetVMQuestVariable'


class SayTopics:
    """FO4 Custom topics for FNV quests' Conversation topics; `voiced` lists [(FO4 INFO, FNV INFO)]."""

    def __init__(self, builder, export_dir: Path):
        """Index FNV topics, lines and quest script variables; topics are written through `builder`."""
        self.builder, self.voiced = builder, []
        self.dials = {r['FormID']: r for r in parse_export_file(str(export_dir / 'DIAL.txt'))}
        self.infos = {}
        for rec in parse_export_file(str(export_dir / 'INFO.txt')):
            self.infos.setdefault(rec.get('QSTI.Quest', '').upper(), []).append(rec)
        self.variables = {}
        for rec in parse_export_file(str(export_dir / 'SCPT.txt')):
            names, i = {}, 0
            while f'Variable[{i}].Index' in rec:
                names[int(rec[f'Variable[{i}].Index'])] = rec[f'Variable[{i}].Name']
                i += 1
            self.variables[rec['FormID'].upper()] = names

    def topics(self, quest: dict) -> list:
        """FNV FormIDs of `quest`'s Conversation topics, in first-line order."""
        seen = {}
        for rec in self.infos.get(quest['FormID'].upper(), []):
            if self.dials.get(rec['ParentDIAL'], {}).get('DATA.Type') == CONVERSATION:
                seen.setdefault(rec['ParentDIAL'], None)
        return list(seen)

    def build(self, quest: dict, quest_fid: int, topic_ids: dict, form_map: dict) -> tuple:
        """(DLBR record, [topic blobs]) of `quest`'s topics `topic_ids` ({FNV DIAL: FO4 FormID}, not empty).

        `form_map` maps the FNV forms conditions name to FO4 ones.
        """
        quest_vars = self.variables.get(quest.get('SCRI', '').upper(), {})
        branch, blobs = self.builder.new_id(), []
        for dial, fid in topic_ids.items():
            lines = [rec for rec in self.infos[quest['FormID'].upper()] if rec['ParentDIAL'] == dial]
            infos = [i for i in (self._info(rec, form_map, quest_vars) for rec in lines) if i]
            record = R.pack_dial(fid, f'FNV_{self.dials[dial]["EditorID"]}', quest_fid, R.TOPIC_CUSTOM, len(infos),
                                 branch)
            blobs.append(pack_topic(record, fid, infos))
        dlbr = R.pack_dlbr(branch, f'FNV_{quest["EditorID"]}Branch', quest_fid, next(iter(topic_ids.values())))
        return dlbr, blobs

    def _info(self, rec: dict, form_map: dict, quest_vars: dict) -> bytes:
        """One FNV line as an FO4 INFO; b'' when a condition cannot convert."""
        conditions = conditions_of(rec, form_map, quest_vars)
        if conditions is None:
            self.builder.counts['line left out (condition)'] += 1
            return b''
        fid = self.builder.new_id()
        name = f'{FRAGMENT_PREFIX}{rec["FormID"].upper()}'
        scripts, vmad = self.builder.scripts, b''
        if scripts.dir and (scripts.dir / f'{name}.psc').exists():
            vmad = info_fragments(name, scripts.properties(name), begin='Fragment_1', end='Fragment_0')
            scripts.used.append(name)
        lines = [rec[f'Response[{i}].ResponseText'] for i in range(int(rec.get('ResponseCount', 0) or 0))]
        flags = R.INFO_SAY_ONCE if int(rec.get('DATA.Flags', 0)) & SAY_ONCE else 0
        self.voiced.append((fid, rec))
        self.builder.counts['INFO'] += 1
        return R.pack_info(fid, flags, tuple(lines) or ('...',), conditions, notes=f'FNV {rec["FormID"]}', vmad=vmad)


def _unmapped(cond: dict, form_map: dict) -> bool:
    """True when a condition uses a global or names an FNV form `form_map` lacks."""
    slots = C.FNV.form_slots.get(C.FNV.index(cond['func']), set())
    return bool(cond['op_flags'] & USE_GLOBAL) or any(
        s in slots and p not in form_map for s, p in ((1, cond['p1']), (2, cond['p2'])))


def conditions_of(rec: dict, form_map: dict, quest_vars: dict) -> 'bytes | None':
    """An FNV record's conditions as FO4 CTDAs (and CIS2s); None when one cannot convert.

    GetQuestVariable becomes GetVMQuestVariable on `quest_vars`' name for its
    index (`::<name>_var`, the converted property's backing variable).
    """
    out, i = b'', 0
    while f'Condition[{i}].Raw' in rec:
        cond = C.parse(rec[f'Condition[{i}].Raw'])
        i += 1
        variable = quest_vars.get(cond['p2']) if cond['func'] == QUEST_VARIABLE else None
        name = VM_QUEST_VARIABLE if cond['func'] == QUEST_VARIABLE else C.RENAMED.get(cond['func'], cond['func'])
        func = C.FO4.index(name)
        if func < 0 or (cond['func'] == QUEST_VARIABLE and variable is None) or _unmapped(
                dict(cond, p2=0) if variable else cond, form_map):
            return None
        run_on, ref = C.run_on_of(cond, False, form_map)
        p2 = 0 if variable else form_map.get(cond['p2'], cond['p2'])
        out += R.pack_ctda(cond['op_flags'] & (COMPARE | OR), cond['value'], func, form_map.get(cond['p1'], cond['p1']),
                           p2, run_on, ref) + (R.pack_cis2(f'::{variable}_var') if variable else b'')
    return out
