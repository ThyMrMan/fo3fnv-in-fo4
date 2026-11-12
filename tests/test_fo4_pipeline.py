"""The FO4 pipeline's infrastructure: the shared export reads, the code tag, the mesh and Elric caches.

See: docs/fork/fo4_pipeline.md#skeleton
"""

import json
import os
import time
from types import SimpleNamespace

from fo4_import.nif.convert_static import Converted
from fo4_import.nif.file import NifFile
from fo4_import.pipeline import build_steps as BS
from fo4_import.pipeline import code_tag as CT
from fo4_import.pipeline import converters as CV
from fo4_import.pipeline import elric_cache as EC
from fo4_import.pipeline import export_index as EI
from fo4_import.pipeline import master_copies as MCP
from fo4_import.pipeline import mesh_cache as MC
from fo4_import.pipeline import run as RUN
from fo4_import.pipeline import stale_files as SF
from fo4_import.pipeline import work_cache as WC
from fo4_import.record_routes import ROUTES
from fo4_import.spike.cell import CellBuilder


def test_an_export_file_is_parsed_once_and_shared(tmp_path):
    """Two reads of one type return the same parse; a missing type is empty."""
    (tmp_path / 'MISC.txt').write_text('---RECORD_BEGIN---\nSignature=MISC\nFormID=00000801\n---RECORD_END---\n',
                                       encoding='utf-8')
    first = EI.export_records(tmp_path, 'MISC')
    assert first is EI.export_records(tmp_path, 'MISC') and first[0]['FormID'] == '00000801'
    assert EI.export_records(tmp_path, 'NOTE') == ()


def test_relative_and_from_imports_name_their_modules(tmp_path):
    """Relative imports resolve against the package, `from` names as submodules."""
    source = tmp_path / 'm.py'
    source.write_text('from . import a\nfrom ..b import c\nimport x.y\n', encoding='utf-8')
    assert CT.imported(source, 'p.q') == {'p.q', 'p.q.a', 'p.b', 'p.b.c', 'x.y'}


def test_a_cached_mesh_is_converted_once_per_key(tmp_path, monkeypatch):
    """The second call with the same NIF and flags comes from the cache; another flag converts again."""
    calls = []
    monkeypatch.setattr(MC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(MC, 'convert', lambda *a: calls.append(a) or Converted(NifFile(), animatable=True))
    nif = tmp_path / 'a.nif'
    nif.write_bytes(b'nif bytes')
    assert MC.cached_convert(nif).animatable and MC.cached_convert(nif).animatable
    MC.cached_convert(nif, animated=False)
    assert len(calls) == 2


def test_elric_runs_only_on_uncached_meshes_and_remembers_a_crash(tmp_path, monkeypatch):
    """A cached mesh skips Elric; a mesh Elric crashed on stays without output and is not run again."""
    runs = []

    def fake(sources):
        """Elric that crashes on 'bad'."""
        runs.append(sorted(sources))
        return {n: d + b'!' for n, d in sources.items() if d != b'bad'}
    monkeypatch.setattr(EC, 'CACHE', tmp_path)
    monkeypatch.setattr(EC, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(EC.elric, 'process', fake)
    monkeypatch.setattr(EC, 'ours', lambda data: None)
    assert EC.process({'a': b'one', 'b': b'bad'}) == {'a': b'one!'}
    assert EC.process({'c': b'one', 'd': b'bad', 'e': b'two'}) == {'c': b'one!', 'e': b'two!'}
    assert runs == [['a', 'b'], ['e']]


def test_cached_work_runs_once_per_input_and_keeps_a_none(tmp_path, monkeypatch):
    """Same inputs come from the cache (even a None value); other inputs run the work again."""
    calls = []
    monkeypatch.setattr(WC, 'CACHE', tmp_path)
    work = lambda: calls.append(1)
    assert WC.cached('site', 'fo4_import.pipeline.work_cache', (b'a', 1), work) is None
    assert WC.cached('site', 'fo4_import.pipeline.work_cache', (b'a', 1), work) is None
    WC.cached('site', 'fo4_import.pipeline.work_cache', (b'a', 2), work)
    assert len(calls) == 2
    assert WC.lookup('site', 'fo4_import.pipeline.work_cache', (b'b',), 'none') == 'none'


def test_a_finished_mesh_is_written_back_from_the_cache_with_its_failure(tmp_path, monkeypatch):
    """elric_cache.finish() finishes only meshes it has not seen, each alone; a seen one gets its finished bytes and
    its failed flag back."""
    runs = []

    def fake(paths, run, names):
        """Stand in for elric.finish: append b'+' to each mesh; 'b' fails."""
        runs.append(sorted(p.read_bytes() for p in paths))
        failed = [p for p in paths if p.read_bytes() == b'b']
        for p in paths:
            p.write_bytes(p.read_bytes() + b'+')
        return failed
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(EC, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(EC.elric, 'finish', fake)
    paths = [tmp_path / 'a.nif', tmp_path / 'b.nif']
    for _ in range(2):
        for p in paths:
            p.write_bytes(p.stem.encode())
        assert EC.finish(paths) == [tmp_path / 'b.nif']
        assert [p.read_bytes() for p in paths] == [b'a+', b'b+']
    assert runs == [[b'a'], [b'b']]


def test_a_mesh_a_master_finished_alike_is_left_out_and_its_mark_recorded(tmp_path, monkeypatch):
    """finish() records each finished mesh's mark; a later build leaves out (deletes, does not write) one whose
    master gives the same mark, keeps its failed flag, and writes one whose mark differs."""
    monkeypatch.setattr(WC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(EC, 'elric_tag', lambda: b'tag')
    monkeypatch.setattr(EC.elric, 'finish', lambda paths, run, names: [p for p in paths if p.read_bytes() == b'b'])
    monkeypatch.setattr(EC, 'MARKS', {})
    monkeypatch.setattr(EC, 'LEFT', {})
    paths = [tmp_path / 'a.nif', tmp_path / 'b.nif', tmp_path / 'c.nif']
    for p in paths:
        p.write_bytes(p.stem.encode())
    EC.finish(paths)
    theirs = {k: v for k, v in EC.MARKS.items() if not k.endswith('c.nif')}
    theirs[os.path.normcase(str(paths[2]))] = ['other', True]
    assert EC.finish(paths, theirs) == [paths[1]]
    assert list(EC.LEFT) == [os.path.normcase(str(p)) for p in paths[:2]]
    assert not paths[0].exists() and paths[2].read_bytes() == b'c'
    assert EC.mesh_bytes(paths[0]) == b'a'


def test_a_dependent_build_trusts_mesh_records_only_when_every_master_has_one(tmp_path):
    """theirs() maps a mesh path to the last master's record of it; one master folder without a record means none."""
    game, dlc, own = tmp_path / 'game', tmp_path / 'dlc', tmp_path / 'own'
    for folder in (game, dlc, own):
        folder.mkdir()
    builder = SimpleNamespace(data_dir=own, built=[game / 'G.esm', dlc / 'D.esm'])
    mesh = own / 'Meshes' / 'fnv' / 'A.nif'
    MCP.write_meshes(game / 'G.esm', game, [game / 'Meshes' / 'fnv' / 'a.nif'], {})
    assert MCP.theirs(builder, [mesh]) == {}
    (game / 'Meshes' / 'fnv').mkdir(parents=True)
    (game / 'Meshes' / 'fnv' / 'a.nif').write_bytes(b'x')
    MCP.write_meshes(game / 'G.esm', game, [game / 'Meshes' / 'fnv' / 'a.nif'],
                     {os.path.normcase(str(game / 'Meshes' / 'fnv' / 'a.nif')): ['m1', True]})
    (dlc / 'D.esm.meshes.json').write_text(json.dumps({'meshes/fnv/a.nif': ['m2', False]}), encoding='utf-8')
    assert MCP.theirs(builder, [mesh]) == {os.path.normcase(str(mesh)): ['m2', False]}
    MCP.moved_in(dlc / 'D.esm.meshes.json').unlink()
    assert MCP.theirs(builder, [mesh]) == {}


def test_warm_leaves_a_mesh_kept_and_unchanged_out_of_the_pool(tmp_path, monkeypatch):
    """A second warm() sends no mesh whose entry is current and textures unchanged; a changed texture sends it."""
    sent = []

    class Pool:
        """An in-process stand-in for the worker pool."""
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def map(self, fn, jobs, chunksize):
            sent.extend(job[0] for job in jobs)
            return [fn(job) for job in jobs]
    monkeypatch.setattr(MC, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(MC.concurrent.futures, 'ProcessPoolExecutor', Pool)
    monkeypatch.setattr(MC, 'addon_map', lambda root: {})
    monkeypatch.setattr(MC, 'convert', lambda *a: Converted(NifFile(), textures={'t.dds'}))
    texture = tmp_path / 'textures' / 't.dds'
    texture.parent.mkdir()
    texture.write_bytes(b'one')
    nif = tmp_path / 'a.nif'
    nif.write_bytes(b'nif')
    for _ in range(2):
        MC.warm([nif], tmp_path)
    texture.write_bytes(b'two!')
    MC.warm([nif], tmp_path)
    assert sent == [str(nif), str(nif)]


def test_every_placed_type_has_a_converter_and_a_route():
    """PLACED names only builder methods and routed types; stand-ins are placed."""
    assert all(callable(getattr(CellBuilder, method, None)) for method in CV.PLACED.values())
    assert set(CV.PLACED) <= set(ROUTES) and CV.STATIC_STAND_INS <= set(CV.PLACED)


def test_a_region_is_its_two_corners_and_around_is_its_square():
    """--region in any corner order is (low, high); --around is its square."""
    region = SimpleNamespace(region=[-17, 1, -19, -1], around=(0, 0), radius=1, whole=False)
    assert RUN.scope_cells(region) == ((-19, -1), (-17, 1))
    assert RUN.scope_cells(SimpleNamespace(region=None, around=(-18, 0), radius=1, whole=False)) == (
        (-19, -1), (-17, 1))
    assert RUN.scope_cells(SimpleNamespace(region=[-17, 1, -19, -1], whole=True)) == (None, None)


def test_a_build_takes_the_heavy_job_lock_before_any_work(monkeypatch):
    """main() queues behind any other heavy job before it starts the build's processes."""
    calls = []
    monkeypatch.setattr(RUN, 'arguments', lambda: SimpleNamespace(resources=None))
    monkeypatch.setattr(RUN, 'hold_heavy_lock', lambda label: calls.append(label))

    def stop():
        """The first step after the lock: end the run here."""
        calls.append('work')
        raise SystemExit
    monkeypatch.setattr(RUN, 'configure_multiprocessing', stop)
    monkeypatch.setattr(RUN.sys, 'argv', ['run.py', '--out', 'x.esm'])
    try:
        RUN.main()
    except SystemExit:
        pass
    assert calls == ['fo4_import.pipeline.run --out x.esm', 'work']


def test_the_stamp_says_running_then_finished_or_failed(tmp_path, monkeypatch):
    """The stamp beside the plugin reads running during the build (recording its inputs), its inputs record is
    written before it reads finished, and it reads failed when the build raises."""
    out = tmp_path / 'FalloutNV.esm'
    seen = []
    monkeypatch.setattr(RUN, 'arguments', lambda: SimpleNamespace(out=out, data=tmp_path, keep_loose=False,
                                                                  resources='low'))
    for name in ('hold_heavy_lock', 'configure_multiprocessing', 'create_pool_job'):
        monkeypatch.setattr(RUN, name, lambda *a: None)
    monkeypatch.setattr(RUN, 'estimate', lambda args: lambda stage, seconds: None)
    monkeypatch.delenv(RUN.build_resources.ENV_VAR, raising=False)
    monkeypatch.setattr(RUN, 'source_state', lambda: {'commit': 'abc', 'changed files': ['x.py']})
    stamp = BS.stamp_path(out)
    status = lambda: json.loads(stamp.read_text())['status']
    monkeypatch.setattr(RUN, 'build_inputs', SimpleNamespace(record_dir=lambda plugin: plugin,
                                                             start=lambda folder: seen.append('record'),
                                                             write=lambda *a: seen.append(f'inputs {status()}')))
    monkeypatch.setattr(RUN, 'build_all', lambda args, started: seen.append(status()) or {'NPC_': 2})
    RUN.main()
    body = json.loads(stamp.read_text())
    assert (seen, body['status'], body['commit'], body['changed files']) == (
        ['record', 'running', 'inputs running'], 'finished', 'abc', ['x.py'])
    assert body['resources']['profile'] == 'low' and body['counts'] == {'NPC_': 2} and 'stages' in body

    def fails(args, started):
        """A build that dies part way."""
        raise RuntimeError('boom')
    monkeypatch.setattr(RUN, 'build_all', fails)
    try:
        RUN.main()
    except RuntimeError:
        pass
    assert json.loads(stamp.read_text())['status'] == 'failed'


def test_a_build_with_scripts_converts_them_first(monkeypatch):
    """--scripts converts the export's scripts into that folder before anything else runs."""
    calls = []
    monkeypatch.setattr(RUN, 'convert_scripts', lambda export, scripts: calls.append((export, scripts)))

    def stop(args):
        """The step after the conversion: end the run here."""
        raise SystemExit
    monkeypatch.setattr(RUN, 'exteriors', stop)
    try:
        RUN.build_all(SimpleNamespace(scripts='s', export='e'), 0.0)
    except SystemExit:
        pass
    assert calls == [('e', 's')]


def test_the_first_world_takes_the_rectangle_and_the_rest_are_whole(monkeypatch):
    """--world A B: A's cells in --region plus its edited cells, B's all."""
    monkeypatch.setattr(RUN, 'edited_cells', lambda export, world: frozenset({(5, 5)}))
    args = SimpleNamespace(export=None, world=['A', 'B'], region=[0, 0, 1, 1], whole=False)
    assert RUN.exteriors(args) == (('A', (0, 0), (1, 1), frozenset({(5, 5)})), ('B', None, None))
    assert RUN.exteriors(SimpleNamespace(export=None, world=[], region=None, whole=False)) == ()


def test_a_dlc_builds_list_also_covers_its_rigs_and_lod_and_a_game_builds_does_not(tmp_path):
    """made(): a DLC build lists fresh files under DLC_ROOTS too; the game build's list is ROOTS alone."""
    for name in ('Meshes/fnv/a.nif', 'Meshes/Actors/FNVGecko/CharacterAssets/skeleton.nif',
                 'Meshes/Terrain/FNV_Zion/Objects/FNV_Zion.4.0.0.bto', 'LODSettings/FNV_Zion.lod', 'Scripts/A.pex'):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b'x')
    started = time.time() - 1
    assert SF.made(tmp_path, 'HonestHearts', started) == {'Meshes/fnv/a.nif'}
    assert SF.made(tmp_path, 'HonestHearts', started, dlc=True) == {
        'Meshes/fnv/a.nif', 'Meshes/Actors/FNVGecko/CharacterAssets/skeleton.nif',
        'Meshes/Terrain/FNV_Zion/Objects/FNV_Zion.4.0.0.bto', 'LODSettings/FNV_Zion.lod'}


def test_stale_files_are_what_the_last_list_named_and_no_list_names_now(tmp_path):
    """A build's files are those under ROOTS dated from its start; the next build deletes its last list's others,
    keeping one another plugin lists; with no earlier list nothing goes."""
    files = {name: tmp_path / name for name in ('Meshes/fnv/a.nif', 'Meshes/fnv/old.nif', 'Materials/fnv/m.bgsm',
                                                'Meshes/fnv/shared.nif', 'Meshes/other/x.nif')}
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    os.utime(files['Meshes/fnv/old.nif'], (1, 1))
    os.utime(files['Meshes/fnv/shared.nif'], (1, 1))
    started = time.time() - 1
    assert SF.made(tmp_path, 'FalloutNV', started) == {'Meshes/fnv/a.nif', 'Materials/fnv/m.bgsm'}
    plugin = tmp_path / 'A.esp'
    assert SF.prune(plugin, tmp_path, {'Meshes/fnv/a.nif', 'Meshes/fnv/old.nif', 'Meshes/fnv/shared.nif'}) == []
    (tmp_path / ('B.esp' + SF.LIST_SUFFIX)).write_text('Meshes/fnv/shared.nif\n', encoding='utf-8')
    assert SF.prune(plugin, tmp_path, {'Meshes/fnv/a.nif'}) == ['Meshes/fnv/old.nif']
    assert not files['Meshes/fnv/old.nif'].exists() and files['Meshes/fnv/shared.nif'].exists()
    assert SF.list_path(plugin).read_text(encoding='utf-8') == 'Meshes/fnv/a.nif\n'
