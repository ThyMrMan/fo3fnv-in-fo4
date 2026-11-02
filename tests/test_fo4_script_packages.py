"""The script-package quest: a collection alias per scripted package, and the actors held at their placed spot."""

import struct
from collections import Counter
from types import SimpleNamespace

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


def _builder(monkeypatch) -> SimpleNamespace:
    """A builder over EXPORT whose writer keeps what it is given."""
    monkeypatch.setattr(SP, 'export_records', lambda _, sig: EXPORT.get(sig, ()))
    written = []
    writer = SimpleNamespace(derive_formid=lambda site, key: 0x0A00F000,
                             add_record=lambda sig, blob: written.append(blob))
    packs = {r['FormID']: r for r in EXPORT['PACK']}
    packages = SimpleNamespace(packs=packs, scripted_made=lambda: [('GSRingoDialoguePackage', FO4_GREET)])
    return SimpleNamespace(export_dir='export', packages=packages, actor_refs=REFS, counts=Counter(), writer=writer,
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
    (blob,) = builder.written
    (rec, _), = list(walk(blob, span=(0, len(blob))))
    subs = subrecords(rec.body)
    names = [d.rstrip(b'\0') for t, d in subs if t == b'ALID']
    assert names == [b'Package0', b'Hold0'] and sum(t == b'ALCS' for t, _ in subs) == 1
    hold = subs[[i for i, (t, d) in enumerate(subs) if t == b'ALID'][1]:]
    get = dict(hold)
    assert struct.unpack('<I', get[b'ALFR'])[0] == REFS[0x104C7D]
    assert struct.unpack('<I', get[b'ALPC'])[0] == SP.STAY_AT_EDITOR
    assert builder.counts['actors held at their placed spot'] == 1
