"""An NPC's FO4 facial hair is chosen once, against all its FNV facial hair meshes drawn together, so a mustache
and a goatee pick the beard covering both, whatever their PNAM order.

See: docs/fork/fo4_pipeline.md#face-fit-head-parts
"""

from types import SimpleNamespace

from fo4_import.spike import head_parts as hp


def test_facial_hair_matches_every_facial_mesh_at_once(monkeypatch):
    """best_part runs once, on the coverage of both meshes; their order does not change what it sees."""
    seen = []
    assets = SimpleNamespace(kept_value=lambda key, make: ('face', 'depths'))
    monkeypatch.setattr(hp, 'digest', lambda data: 'baseline')
    monkeypatch.setattr(hp.fnv_npc, 'frame', lambda d, edid, face: SimpleNamespace(npc={}))
    monkeypatch.setattr(hp.fnv_npc, 'mesh_texture', lambda d, mesh: mesh)
    monkeypatch.setattr(hp.hair, 'image', lambda path: hp.np.zeros(1))
    monkeypatch.setattr(hp, '_drawn', lambda mesh, drawn, at: mesh)
    monkeypatch.setattr(hp.hair, 'coverage', lambda parts, depths: frozenset(parts))
    monkeypatch.setattr(hp.hair, 'best_part', lambda a, kind, female, target, depths: seen.append(target) or (7, 0.5))
    for order in (['mustache', 'goatee'], ['goatee', 'mustache']):
        monkeypatch.setattr(hp.fnv_npc, 'sorted_parts', lambda d, at, o=order: (o, [], []))
        assert hp.choose(None, 'Npc', assets, b'').facial_hair == 7
    assert seen == [frozenset({'mustache', 'goatee'})] * 2
