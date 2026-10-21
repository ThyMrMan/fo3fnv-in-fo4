"""The FO4 pipeline's infrastructure: the shared export reads, the code tag, the mesh and Elric caches.

See: docs/fork/fo4_pipeline.md#skeleton
"""

from types import SimpleNamespace

from fo4_import.nif.convert_static import Converted
from fo4_import.nif.file import NifFile
from fo4_import.pipeline import code_tag as CT
from fo4_import.pipeline import converters as CV
from fo4_import.pipeline import elric_cache as EC
from fo4_import.pipeline import export_index as EI
from fo4_import.pipeline import mesh_cache as MC
from fo4_import.pipeline import run as RUN
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
    """elric_cache.finish() finishes only meshes it has not seen; a seen one gets its finished bytes and its
    failed flag back."""
    runs = []

    def fake(paths, run):
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
    assert runs == [[b'a', b'b']]


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


def test_the_first_world_takes_the_rectangle_and_the_rest_are_whole():
    """--world A B: A's cells in --region, B's all."""
    args = SimpleNamespace(export=None, world=['A', 'B'], region=[0, 0, 1, 1], whole=False)
    assert RUN.exteriors(args) == (('A', (0, 0), (1, 1)), ('B', None, None))
    assert RUN.exteriors(SimpleNamespace(export=None, world=[], region=None, whole=False)) == ()
