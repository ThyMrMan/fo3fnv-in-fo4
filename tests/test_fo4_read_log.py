"""The read recorder of the replay spike: Rec stays a dict, reads go to the running unit, the unit stack survives an
exception, master records keep their number, and uninstalling puts every bound name back.

See: docs/fork/fo4_build_speed.md#replay-spike
"""

import copy
import json
import os
import pickle
import sys

import numpy as np
import pytest

from fo4_import.base import install as source_install
from fo4_import.pipeline import export_index as EI
from fo4_import.pipeline import ran_code as RC
from fo4_import.pipeline import read_log as RL
from fo4_import.spike import glow_cards
from tes5_import.base import text_reader

PLAIN = {'Signature': 'NPC_', 'FormID': '00000002', 'EditorID': 'Doc', 'Items': ['a', 'b']}


def export(folder, sig: str, records: list, masters: tuple = ()) -> None:
    """Write `records` (dicts) as export folder `folder`'s type `sig`, its header listing `masters`."""
    folder.mkdir(parents=True, exist_ok=True)
    blocks = ['---RECORD_BEGIN---\n' + ''.join(f'{k}={v}\n' for k, v in {'Signature': sig, **rec}.items())
              + '---RECORD_END---\n' for rec in records]
    (folder / f'{sig}.txt').write_text('\n'.join(blocks), encoding='utf-8')
    (folder / '_HEADER.txt').write_text(''.join(f'Master[{i}]={m}\n' for i, m in enumerate(masters)), encoding='utf-8')


def maker(fnv_fid: int, recs: tuple) -> str:
    """A unit: the EditorID of the record `fnv_fid` among `recs`, found by FormID."""
    rec = next(r for r in recs if int(r['FormID'], 16) == fnv_fid)
    return rec.get('EditorID')


def asker(fnv_fid: int, recs: tuple) -> str:
    """A unit asking maker()'s."""
    return maker(fnv_fid, recs)


def failing(fnv_fid: int, recs: tuple) -> None:
    """A unit that reads a field, then raises."""
    recs[0]['RecordFlags']
    raise KeyError(fnv_fid)


def walker(count: int):
    """A generator unit."""
    yield from range(count)


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    """(a Game.esm export of three NPC_, the installed recorder's log folder), test makers as its units."""
    game = tmp_path / 'export' / 'Game.esm'
    export(game, 'NPC_', [{'FormID': f'0000000{n}', 'EditorID': f'Npc{n}', 'RecordFlags': '0'} for n in (1, 2, 3)])
    units = tuple((__name__, name, kind, ('fnv_fid',)) for name, kind in (
        ('maker', 'base'), ('asker', 'cell'), ('failing', 'broken'))) + ((__name__, 'walker', 'walk', ('count',)),)
    monkeypatch.setattr(RL, 'UNITS', units)
    RL.install(tmp_path / 'log', [tmp_path / 'export'])
    yield game, tmp_path / 'log'
    RL.uninstall()


def loaded(path) -> tuple:
    """(meta, {unit label: {(file's type, record position, field name)}}, {asker label: {asked labels}},
    {unit label: {questions}}) of the log at `path`."""
    data = np.load(path)
    meta = json.loads(bytes(data['meta']))
    label = [f'{kind} {key}' for kind, key in meta['units']]
    file_of = {number: (sig, base) for _, sig, base, count, _ in meta['files'] for number in range(base, base + count)}
    reads, edges, asked = {}, {}, {}
    for unit, rec, field in zip(data['unit'], data['rec'], data['field']):
        sig, base = file_of[int(rec)]
        reads.setdefault(label[unit], set()).add((sig, int(rec) - base, meta['field_names'][field]))
    for a, b in zip(data['edge_a'], data['edge_b']):
        edges.setdefault(label[a], set()).add(label[b])
    for unit, name in zip(data['asked_a'], data['asked_b']):
        asked.setdefault(label[unit], set()).add(meta['names'][name])
    return meta, reads, edges, asked


@pytest.mark.parametrize('kind', [RL.Rec, RL.CoarseRec])
def test_rec_behaves_as_a_dict(kind):
    """A Rec's repr, JSON, equality, lookups and unhashability are a dict's; its copies and pickle are plain."""
    rec = kind(PLAIN)
    assert isinstance(rec, dict) and rec == PLAIN and PLAIN == rec and not rec != PLAIN and len(rec) == 4
    assert repr(rec) == repr(PLAIN) and str([rec]) == str([PLAIN]) and json.dumps(rec) == json.dumps(PLAIN)
    assert rec['FormID'] == '00000002' and rec.get('Missing', 5) == 5 and 'EditorID' in rec and 'X' not in rec
    assert list(rec) == list(PLAIN) and list(rec.items()) == list(PLAIN.items()) and sorted(rec.values(), key=str)
    with pytest.raises(TypeError):
        hash(rec)
    with pytest.raises(KeyError):
        rec['Missing']
    for made in ({**rec}, dict(rec), rec.copy(), rec | {}, {} | rec, copy.copy(rec), copy.deepcopy(rec),
                 pickle.loads(pickle.dumps(rec)), pickle.loads(pickle.dumps([rec], protocol=2))[0]):
        assert type(made) is dict and made == PLAIN and list(made) == list(PLAIN)
    assert (rec | {'FormID': 'x'})['FormID'] == 'x' and ({'FormID': 'x'} | rec)['FormID'] == '00000002'


def test_rec_writes_are_a_dicts():
    """A Rec takes a dict's writes."""
    rec = RL.Rec(PLAIN)
    rec['New'] = '1'
    rec.update(Other='2')
    rec |= {'Third': '3'}
    assert rec.pop('New') == '1' and rec.setdefault('EditorID', 'x') == 'Doc' and rec.setdefault('Set', 'y') == 'y'
    del rec['Other']
    assert rec == {**PLAIN, 'Third': '3', 'Set': 'y'} and type(rec) is RL.Rec


def test_reads_go_to_the_running_unit(recorded):
    """Each read through the real export_records lands on the unit running, with the field read; the unit asked
    is an edge; the whole-type request and the file open are the asker's."""
    game, folder = recorded
    recs = EI.export_records(game, 'NPC_')
    assert all(type(rec) is RL.Rec for rec in recs) and recs is EI.export_records(game, 'NPC_')
    assert asker(2, recs) == 'Npc2' and maker(3, recs) == 'Npc3'
    assert {**recs[0]}['EditorID'] == 'Npc1' and list(walker(2)) == [0, 1]
    meta, reads, edges, asked = loaded(RL.dump())
    assert meta['fields'] and not meta['missing'] and not meta['errors']
    assert reads['base 00000002'] == {('NPC_', 0, 'FormID'), ('NPC_', 1, 'FormID'), ('NPC_', 1, 'EditorID')}
    assert reads['base 00000003'] == {('NPC_', n, 'FormID') for n in range(3)} | {('NPC_', 2, 'EditorID')}
    assert 'cell 00000002' not in reads and edges['cell 00000002'] == {'base 00000002'}
    process = f'process {os.getpid()}'
    assert ('NPC_', 0, RL.WHOLE) in reads[process] and ('NPC_', 0, 'EditorID') in reads[process]
    assert {'cell 00000002', 'base 00000003', 'walk 00000002'} <= edges[process]
    assert any(q.startswith('records\texport_records\tGame.esm\tNPC_\ttests/test_fo4_read_log.py:')
               for q in asked[process])
    assert f'open\tgame.esm{os.sep}npc_.txt' in asked[process]
    assert [site[:1] for site in meta['sites']] == [['keys']] and (folder / f'{os.getpid()}.reads').is_file()


def test_records_only_mode(recorded, tmp_path):
    """With fields off a read logs its record under ANY."""
    game, _ = recorded
    RL.uninstall()
    RL.install(tmp_path / 'log', [tmp_path / 'export'], fields=False)
    recs = EI.export_records(game, 'NPC_')
    assert type(recs[0]) is RL.CoarseRec and maker(1, recs) == 'Npc1'
    meta, reads, _, _ = loaded(RL.dump())
    assert not meta['fields'] and reads['base 00000001'] == {('NPC_', 0, RL.ANY)}


def test_unit_stack_survives_an_exception(recorded):
    """A unit left by an exception ends there: its reads are kept and later reads go to the unit below."""
    game, _ = recorded
    recs = EI.export_records(game, 'NPC_')
    with pytest.raises(KeyError):
        failing(7, recs)
    assert RL.LOG.stack == [0] and len(RL.LOG.live) == 1
    recs[2]['EditorID']
    _, reads, _, _ = loaded(RL.dump())
    assert reads['broken 00000007'] == {('NPC_', 0, 'RecordFlags')}
    assert reads[f'process {os.getpid()}'] == {('NPC_', 2, 'EditorID')}


def test_big_reads_are_shared(recorded, monkeypatch):
    """A unit's run of BIG or more reads is kept once per content and still names its unit."""
    game, _ = recorded
    monkeypatch.setattr(RL, 'BIG', 4)
    recs = EI.export_records(game, 'NPC_')
    assert maker(3, recs) == 'Npc3' and maker(3, recs) == 'Npc3'
    data = np.load(RL.dump())
    meta = json.loads(bytes(data['meta']))
    unit = meta['units'].index(['base', '00000003'])
    assert list(data['big_a']) == [unit] and list(data['big_start']) == [0, 4] and unit not in data['unit']


def test_master_records_keep_their_number(tmp_path, recorded):
    """A master's record renumbered into its dependent's FormIDs, and the disabled copy of a master reference the
    plugin deletes, log as the master's own record."""
    root = tmp_path / 'export'
    export(root / 'A.esm', 'REFR', [{'FormID': '00000010', 'RecordFlags': '0'}])
    export(root / 'B.esm', 'REFR', [{'FormID': '00000020', 'RecordFlags': '0', 'NAME': '00000021'}])
    export(root / 'Mod.esp', 'REFR', [{'FormID': '00000010', 'RecordFlags': str(EI.DELETED)}], ('A.esm', 'B.esm'))
    recs = {rec['FormID']: rec for rec in EI.export_records(root / 'Mod.esp', 'REFR')}
    assert set(recs) == {'00000010', '01000020'} and all(isinstance(rec, RL.Rec) for rec in recs.values())
    assert recs['01000020'].kf == EI.own_records(root / 'B.esm', 'REFR')[0].kf and recs['01000020']['NAME'] == '01000021'
    assert recs['00000010'].kf == EI.own_records(root / 'A.esm', 'REFR')[0].kf
    assert int(recs['00000010']['RecordFlags']) == EI.DISABLED
    _, reads, _, _ = loaded(RL.dump())
    assert ('REFR', 0, 'NAME') in reads[f'process {os.getpid()}']


def test_uninstall_restores_every_name(tmp_path):
    """install() binds the readers and the memo functions and takes a monitoring tool; uninstall() puts each
    back and leaves plain records. The module stays out of code records from its import on."""
    def bound():
        """The names install() binds, as they are now."""
        return (text_reader.parse_export_file, EI.parse_export_file, EI.renumber_record, getattr(EI, '_layered'),
                source_install.walk, EI.Layered.path, glow_cards.glow_cards, glow_cards.light_only)
    before, env = bound(), dict(os.environ)
    game = tmp_path / 'export' / 'Game.esm'
    export(game, 'MISC', [{'FormID': '00000001'}])
    assert type(EI.export_records(game, 'MISC')[0]) is dict
    RL.install(tmp_path / 'log', [tmp_path / 'export'])
    during = bound()
    assert all(new is not old for new, old in zip(during, before)) and RL.SELF in RC.RECORDERS
    assert not [key for key in RC.RAN if key.startswith(RL.SELF)]
    assert sys.monitoring.get_tool(RL.TOOL) == RL.NAME and os.environ[RL.ENV] == str(tmp_path / 'log')
    assert during[6].__wrapped__ is before[6].__wrapped__ and during[6].cache_info() == before[6].cache_info()
    assert type(EI.export_records(game, 'MISC')[0]) is RL.Rec
    RL.uninstall()
    assert all(new is old for new, old in zip(bound(), before)) and sys.monitoring.get_tool(RL.TOOL) is None
    assert not RL.LOG.patched and RL.ENV not in os.environ and RL.RUN_ENV not in os.environ
    assert type(EI.export_records(game, 'MISC')[0]) is dict and dict(os.environ) == env
    RL.uninstall()
