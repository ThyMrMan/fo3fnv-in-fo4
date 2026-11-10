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


def test_a_base_typed_property_names_a_placed_base_its_own_too():
    """Nero's couch script names its own base: a Form, Activator or other base-typed property naming an FNV placed
    base by EditorID (any case) gets that base, made on demand (counted when first made); while the couch is
    written its own script reads its FNV-derived FormID, so making it does not recurse."""
    from fo4_import.spike import cell as CL
    builder = CL.CellBuilder.__new__(CL.CellBuilder)
    builder.counts, builder.made = collections.Counter(), {}
    builder.bases = {0x11C245: ('FURN', {'EditorID': 'VMS21NeroCouch'}), 0x2000: ('ACTI', {'EditorID': 'FXSparks'})}
    builder.fnv_id = lambda fid: 0x03000000 | fid
    scripts = A.ObjectScripts.__new__(A.ObjectScripts)
    scripts.builder, scripts.base_names = builder, None
    seen = []

    def record(fnv_fid, sig, rec):
        """A converter whose base's script names the couch while the base is written."""
        seen.append(scripts._base('vms21nerocouch'))
        return builder.fnv_id(fnv_fid)
    builder.record = record
    assert scripts._base('VMS21NeroCouch') == 0x0311C245 and seen == [0x0311C245]
    assert scripts._base('FXSparks') == 0x03002000 and scripts._base('NoSuchBase') is None
    assert builder.counts['base made for a script property'] == 2
