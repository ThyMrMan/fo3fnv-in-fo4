"""The script-package quest: a collection alias per scripted package, the actors held at their placed spot, and a
plugin's own quest when its master holds the game's."""

import struct
from collections import Counter
from types import SimpleNamespace

from fo4_import.base.vmad import read_quest
from fo4_import.spike import script_packages as SP
from tes5_import.base.tes5_reader import subrecords, walk

#: FNV forms: Ringo's reference, another actor's, Ringo's greet package and a sandbox package.
RINGO, OTHER, GREET, SANDBOX = '00104C7D', '00104AAA', '0010ABAC', '0010ABA9'
#: The FO4 references the build gave them, and the FO4 copy of the greet package.
REFS, FO4_GREET = {0x104C7D: 0x0A0000AA, 0x104AAA: 0x0A0000BB}, 0x0A00ABAC
#: The trigger script as the export writes it (escaped newlines): one live call, one commented out.
TRIGGER = ('scn GSRingoDialogueTriggerScript\\r\\nbegin OnTriggerEnter player\\r\\n'
           '\\tRingoRef.AddScriptPackage GSRingoDialoguePackage\\r\\n'
           '\\t;OtherRef.AddScriptPackage GSRingoDialoguePackage\\r\\n'
           '\\tOtherRef.AddScriptPackage GSRingoSandboxPackage\\r\\nend')
EXPORT = {
    'SCPT': ({'FormID': '0010ABAD', 'EditorID': 'GSRingoDialogueTriggerScript', 'SCTX': TRIGGER},),
    'ACHR': ({'FormID': RINGO, 'EditorID': 'RingoRef'}, {'FormID': OTHER, 'EditorID': 'OtherRef'}),
    'PACK': ({'FormID': GREET, 'EditorID': 'GSRingoDialoguePackage', 'PKDT.Type': '15', 'PLDT.Type': '3'},
             {'FormID': SANDBOX, 'EditorID': 'GSRingoSandboxPackage', 'PKDT.Type': '12', 'PLDT.Type': '1'}),
}


#: The game's quest as a DLC build sees it (its master's, index 01), and the DLC's own (index 0A).
MASTER_QUEST, DLC_QUEST = 0x0100F000, 0x0A00F001


def _builder(monkeypatch, dlc: bool = False) -> SimpleNamespace:
    """A builder over EXPORT whose writer keeps what it is given; `dlc`: its master holds the game's quest."""
    monkeypatch.setattr(SP, 'export_records', lambda _, sig: EXPORT.get(sig, ()))
    written = []
    own = {(SP.SITE, SP.EDID): MASTER_QUEST, (SP.SITE, SP.PLUGIN_KEY): DLC_QUEST} if dlc else {}
    writer = SimpleNamespace(derive_formid=lambda site, key: own.get((site, key), 0x0A00F000), own_index=0x0A,
                             add_record=lambda sig, blob: written.append(blob))
    packs = {r['FormID']: r for r in EXPORT['PACK']}
    packages = SimpleNamespace(packs=packs, scripted_made=lambda: [('GSRingoDialoguePackage', FO4_GREET)])
    return SimpleNamespace(export_dir='DeadMoney.esm', packages=packages, actor_refs=REFS, counts=Counter(), writer=writer,
                           scripts=SimpleNamespace(used=[]), written=written)


def test_held_actors_are_those_given_a_dialogue_package_waiting_at_their_editor_location(monkeypatch):
    """Ringo's live call holds him; the commented-out call and the sandbox package hold no one."""
    builder = _builder(monkeypatch)
    assert SP.held_actors(builder) == [REFS[0x104C7D]]
    assert builder.counts['held actor outside the build'] == 0


def test_a_held_actor_gets_a_forced_alias_running_vanillas_stay_at_editor_package(monkeypatch):
    """After the package aliases, Hold0 is forced to Ringo and runs DefaultStayAtEditorLocation; not a collection."""
    builder = _builder(monkeypatch)
    assert SP.write_script_packages(builder) == 1
    subs = subrecords(_record(builder, b'QUST').body)
    names = [d.rstrip(b'\0') for t, d in subs if t == b'ALID']
    assert names == [b'Package0', b'Hold0'] and sum(t == b'ALCS' for t, _ in subs) == 1
    hold = subs[[i for i, (t, d) in enumerate(subs) if t == b'ALID'][1]:]
    get = dict(hold)
    assert struct.unpack('<I', get[b'ALFR'])[0] == REFS[0x104C7D]
    assert struct.unpack('<I', get[b'ALPC'])[0] == SP.STAY_AT_EDITOR
    assert struct.unpack('<I', get[b'FNAM'])[0] & 0x2 and b'KWDA' not in get
    assert builder.counts['actors held at their placed spot'] == 1



def _record(builder, sig: bytes):
    """The one `sig` record `builder` wrote."""
    (blob,) = [b for b in builder.written if b[:4] == sig]
    (rec, _), = list(walk(blob, span=(0, len(blob))))
    return rec


def _quest(builder) -> tuple:
    """(FormID, EditorID, script entry) of the one quest `builder` wrote."""
    rec = _record(builder, b'QUST')
    get = dict(subrecords(rec.body))
    (entry,), _ = read_quest(get[b'VMAD'])
    return rec.form_id, get[b'EDID'].rstrip(b'\0').decode(), entry


def test_the_game_build_writes_the_hub_with_no_hub_of_its_own(monkeypatch):
    """The game's quest keeps its EditorID and FormID, and names no Hub."""
    builder = _builder(monkeypatch)
    assert SP.quest_id(builder) == 0x0A00F000
    SP.write_script_packages(builder)
    fid, edid, (script, objects, _) = _quest(builder)
    assert (fid, edid, script) == (0x0A00F000, SP.EDID, SP.SCRIPT) and 'Hub' not in objects


def test_package_aliases_put_the_quests_keyword_on_their_actors(monkeypatch):
    """Release skips the alias search for an actor without the keyword, so every package alias applies it."""
    builder = _builder(monkeypatch)
    SP.write_script_packages(builder)
    keyword = _record(builder, b'KYWD')
    _, _, (_, objects, _) = _quest(builder)
    package = dict(subrecords(_record(builder, b'QUST').body))
    assert objects['InPackage'] == keyword.form_id
    assert struct.unpack('<I', package[b'KWDA'])[0] == keyword.form_id


def test_a_dlc_writes_its_own_quest_naming_the_games_as_hub(monkeypatch):
    """A DLC whose master holds the game's quest writes one of its own (kept: not a master record), its scripts are
    filled with it, and it names the game's so its packages and the game's share one actor's script package."""
    builder = _builder(monkeypatch, dlc=True)
    assert SP.quest_id(builder) == DLC_QUEST
    assert SP.write_script_packages(builder) == 1
    fid, edid, (_, objects, values) = _quest(builder)
    assert (fid, edid) == (DLC_QUEST, f'{SP.EDID}_DeadMoney')
    assert objects['Hub'] == MASTER_QUEST and values['Packages'] == ('objects', [FO4_GREET])
