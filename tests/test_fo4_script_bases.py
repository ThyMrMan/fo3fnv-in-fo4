"""An ActorBase script property names an FNV NPC or creature; its base is made on demand (attach.ObjectScripts).

See: docs/fork/fo4_plugin_layout.md#dlc-script-bases
"""

import collections
from types import SimpleNamespace

from fo4_import.spike import attach as A


def _scripts(monkeypatch, builder) -> A.ObjectScripts:
    """ObjectScripts on `builder`, naming Sawbones, over one FNV NPC and one templated creature."""
    records = {'CREA': [{'FormID': '01008E70', 'EditorID': 'NVDLC04DivideCaveTBrute'}],
               'NPC_': [{'FormID': '00001234', 'EditorID': 'Sawbones'}]}
    monkeypatch.setattr(A, 'export_records', lambda export_dir, sig: records.get(sig, []))
    scripts = A.ObjectScripts.__new__(A.ObjectScripts)
    scripts.builder, scripts.export_dir, scripts.actor_bases = builder, None, None
    scripts.named = A.NameMap({'Sawbones': 0x03001234})
    return scripts


def test_an_actor_base_property_makes_the_base_through_the_people_maker(monkeypatch):
    """A base the build already named is used as is; one it has not is made by Npcs.actor_form (which makes
    templated creatures too); an unknown name stays unfilled."""
    made = []
    npcs = SimpleNamespace(actor_form=lambda fnv_hex: made.append(fnv_hex) or 0x04118A44)
    scripts = _scripts(monkeypatch, SimpleNamespace(npcs=npcs, counts=collections.Counter()))
    assert scripts.actor_base('sawbones') == 0x03001234
    assert scripts.actor_base('nvdlc04dividecavetbrute') == 0x04118A44 and made == ['01008E70']
    assert scripts.actor_base('NoSuchBase') is None


def test_the_player_enemy_list_is_written_empty_once_like_the_destroyed_list():
    """TES4PlayerEnemyFactions (GetPCEnemyOfFaction's list) and TES4DestroyedRefs get one empty FLST each; another
    name gets none."""
    written = []
    writer = SimpleNamespace(derive_formid=lambda site, name: hash(name) & 0xFFFF,
                             add_record=lambda sig, body: written.append(sig))
    scripts = A.ObjectScripts.__new__(A.ObjectScripts)
    scripts.builder, scripts.globals = SimpleNamespace(writer=writer), {}
    enemies = scripts.form_list('TES4PlayerEnemyFactions')
    assert enemies and scripts.form_list('TES4PlayerEnemyFactions') == enemies
    assert scripts.form_list('TES4DestroyedRefs') and scripts.form_list('SomethingElse') is None
    assert written == ['FLST', 'FLST']


def test_before_the_people_stage_the_property_is_counted(monkeypatch):
    """With no Npcs yet the property stays None, counted so a build log shows it."""
    builder = SimpleNamespace(counts=collections.Counter())
    assert _scripts(monkeypatch, builder).actor_base('NVDLC04DivideCaveTBrute') is None
    assert sum(builder.counts.values()) == 1


def test_a_base_typed_property_names_a_placed_base_its_own_too(monkeypatch):
    """Nero's couch script names its own base: a Form, Activator or other base-typed property naming an FNV base by
    EditorID (any case) gets that base, made on demand (counted when first made); while the couch is written its
    own script reads its FNV-derived FormID, so making it does not recurse. A base no reference places (a script
    spawns it) joins builder.bases and is made the same way."""
    from fo4_import.spike import cell as CL
    couch, sparks = ('FURN', {'EditorID': 'VMS21NeroCouch'}), ('ACTI', {'EditorID': 'FXSparks'})
    monkeypatch.setattr(A, 'base_records', lambda export_dir: [(0x11C245, *couch), (0x2000, *sparks)])
    builder = CL.CellBuilder.__new__(CL.CellBuilder)
    builder.counts, builder.made, builder.bases = collections.Counter(), {}, {0x11C245: couch}
    builder.fnv_id = lambda fid: 0x03000000 | fid
    scripts = A.ObjectScripts.__new__(A.ObjectScripts)
    scripts.builder, scripts.base_names, scripts.export_dir = builder, None, None
    seen = []

    def record(fnv_fid, sig, rec):
        """A converter whose base's script names the couch while the base is written."""
        seen.append(scripts._base('vms21nerocouch'))
        return builder.fnv_id(fnv_fid)
    builder.record = record
    assert scripts._base('VMS21NeroCouch') == 0x0311C245 and seen == [0x0311C245]
    assert scripts._base('FXSparks') == 0x03002000 and scripts._base('NoSuchBase') is None
    assert builder.counts['base made for a script property'] == 2 and builder.bases[0x2000] == sparks


def test_a_holotape_property_gets_its_note_through_the_item_converter():
    """A Holotape property (an FO3 voice note) is made by the item converter."""
    scripts = A.ObjectScripts.__new__(A.ObjectScripts)
    scripts.builder = SimpleNamespace(items=SimpleNamespace(by_name=lambda name: 0x0300AB12 if name == 'MS08Note2' else None))
    assert scripts._made('Holotape', 'MS08Note2') == 0x0300AB12


def test_a_speech_threshold_property_gets_a_float_global_at_the_first_roll(monkeypatch):
    """TES4SpeechNeed<n> is written once as a float global holding first_needs' value."""
    written = []
    monkeypatch.setattr(A, 'export_records', lambda export_dir, sig: [])
    scripts = A.ObjectScripts.__new__(A.ObjectScripts)
    scripts.export_dir, scripts.speech_needs, scripts.globals = None, None, {}
    scripts.builder = SimpleNamespace(counts=collections.Counter(), writer=SimpleNamespace(
        derive_formid=lambda site, name: 0x0300F000 + len(name), add_record=lambda sig, body: written.append(body)))
    fid = scripts._global_form('TES4SpeechNeed3')
    assert fid == scripts._global_form('TES4SpeechNeed3') and len(written) == 1 and b'FNAM\x01\x00f' in written[0]
