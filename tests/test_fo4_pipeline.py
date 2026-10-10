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


def test_every_placed_type_has_a_converter_and_a_route():
    """PLACED names only builder methods and routed types; stand-ins are placed."""
    assert all(callable(getattr(CellBuilder, method, None)) for method in CV.PLACED.values())
    assert set(CV.PLACED) <= set(ROUTES) and CV.STATIC_STAND_INS <= set(CV.PLACED)


def test_a_region_is_its_two_corners_and_around_is_its_square():
    """--region in any corner order is (low, high); --around is its square."""
    region = SimpleNamespace(region=[-17, 1, -19, -1], around=(0, 0), radius=1)
    assert RUN.scope_cells(region) == ((-19, -1), (-17, 1))
    assert RUN.scope_cells(SimpleNamespace(region=None, around=(-18, 0), radius=1)) == ((-19, -1), (-17, 1))
