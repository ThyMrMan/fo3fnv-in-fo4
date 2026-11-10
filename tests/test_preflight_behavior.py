"""The behavior audit: FNV packages a Fallout 4 build left out, by cause, and actors left with none."""

import json
import struct

from fo4_import.spike.readiness import PACKAGE_LEFT_OUT
from tests.test_preflight_audits import export_file, zs
from tools.esm.tes5_esm_reader import Sub, TES5Record
from tools.validate.preflight import behavior
from tools.validate.preflight.plugin_index import PluginIndex


def rec(sig, fid, subs=()):
    """A built record with `subs` as (signature, bytes) pairs."""
    return TES5Record(sig, 0, 0, fid, 131, [Sub(t, d) for t, d in subs])


def actor(fid, name, packs):
    """An FNV actor export record listing package FormIDs `packs`."""
    return {'FormID': fid, 'EditorID': name, 'AIPackageCount': len(packs),
            **{f'AIPackage[{i}]': p for i, p in enumerate(packs)}}


def game(tmp_path):
    """An export, a built plugin and a readiness report: Jack keeps Sandbox but not FindJanet (type Find), the
    Gambler loses his only package, Unreached's actor is not built, ScriptedFlee is named by a script only."""
    export = tmp_path / 'export'
    export.mkdir()
    packs = [('00000101', 'JackSandbox'), ('00000102', 'NellisFindJanet'), ('00000103', 'GamblerPackage'),
             ('00000104', 'UnreachedPackage'), ('00000105', 'ScriptedFlee')]
    export_file(export, 'PACK', [{'FormID': f, 'EditorID': n} for f, n in packs])
    export_file(export, 'NPC_', [actor('00000201', 'NellisJack', ['00000101', '00000102']),
                                 actor('00000202', 'Gambler', ['00000103']),
                                 actor('00000203', 'Unbuilt', ['00000104'])])
    export_file(export, 'CREA', [])
    report = tmp_path / 'readiness.json'
    report.write_text(json.dumps([
        {'kind': PACKAGE_LEFT_OUT, 'owner': '00000201', 'detail': 'NellisFindJanet (type Find; keeps 1 of 2)'},
        {'kind': PACKAGE_LEFT_OUT, 'owner': '00000202', 'detail': 'GamblerPackage (type Find; keeps 0 of 1)'}]))
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'Q.psc').write_text('Scriptname Q extends Quest\nPackage Property ScriptedFlee Auto\n')
    index = PluginIndex([rec('PACK', 0x0A000001, [('EDID', zs('FNV_JackSandbox'))]),
                         rec('NPC_', 0x0A000002, [('EDID', zs('FNV_NellisJack')),
                                                  ('PKID', struct.pack('<I', 0x0A000001))]),
                         rec('NPC_', 0x0A000003, [('EDID', zs('FNV_Gambler'))])], edid_prefix='FNV_', fo4=True)
    return index, export, report, scripts


def test_left_out_packages_are_paired_by_editor_id_and_given_the_builds_cause(tmp_path):
    """A built copy pairs by EditorID; an unreached package is not reported; a script-only one has no cause."""
    rows, _lists = behavior.left_out(*game(tmp_path))
    assert [(n, why, held, named) for n, why, held, named in rows] == [
        ('GamblerPackage', 'type Find', ['Gambler'], False),
        ('NellisFindJanet', 'type Find', ['NellisJack'], False),
        ('ScriptedFlee', behavior.NO_CAUSE, [], True)]


def test_an_actor_running_no_package_is_an_error(tmp_path):
    """The Gambler's only package is left out, so the actor runs nothing; Jack keeps one."""
    found = {f.key: f.severity for f in behavior.audit('Test.esm', *game(tmp_path))}
    assert found['behavior|Test.esm|no-package|Gambler'] == 'error'
    assert 'behavior|Test.esm|no-package|NellisJack' not in found
    assert found['behavior|Test.esm|package|NellisFindJanet'] == 'review'


def test_a_package_entry_without_an_npc_gives_its_cause(tmp_path):
    """A package's own entry (left out through a script property) and an NPC's both name the cause."""
    report = tmp_path / 'readiness.json'
    report.write_text(json.dumps([
        {'kind': PACKAGE_LEFT_OUT, 'owner': '00000105', 'detail': 'ScriptedFlee (condition GetEquipped (global))'},
        {'kind': PACKAGE_LEFT_OUT, 'owner': '00000201', 'detail': 'NellisFindJanet (type Find; keeps 1 of 2)'}]))
    why, owners = behavior.readiness_causes(report)
    assert why == {'scriptedflee': 'condition GetEquipped (global)', 'nellisfindjanet': 'type Find'}
    assert owners['scriptedflee'] == {'00000105'}
