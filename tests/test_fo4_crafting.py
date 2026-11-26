"""A mod's own recipe categories convert: their stations, keywords and recipes, and what is still left out.

See: docs/fork/fo4_pipeline.md#mod-recipe-categories
"""

import collections
import struct
from types import SimpleNamespace

from fo4_import.spike import crafting as CR
from tes5_import.base.tes5_reader import subrecords

BOUNDS = (-56, -44, 0, 63, 27, 147)
CATEGORIES = {5: {'FormID': '00000005', 'EditorID': 'CampfireRecipes'},
              0x01000006: {'FormID': '01000006', 'EditorID': 'NVDLC01VendingMachineRecipes'}}


def _crafting() -> CR.Crafting:
    """A Crafting over vanilla's campfire and a mod's own category, each opened by one script (7, 8)."""
    crafting = CR.Crafting.__new__(CR.Crafting)
    writer = SimpleNamespace(records=[])
    writer.add_record = lambda sig, rec: writer.records.append((sig, rec))
    crafting.builder = SimpleNamespace(writer=writer, counts=collections.Counter(), fnv_id=lambda fid: int(fid, 16))
    crafting.sides, crafting.keywords, crafting.menus = {}, {}, {7: 5, 8: 0x01000006}
    crafting.categories = CATEGORIES
    crafting.templates = {name: [(b'EDID', b'x\0'), (b'KWDA', struct.pack('<2I', 0x99, kw))]
                          for name, kw in CR.BENCHES.items()}
    crafting._spots = lambda rec, bounds: []
    return crafting


def test_a_mods_category_is_a_chemistry_bench_with_its_own_keyword():
    """A mod's category gets BENCH, the campfire the cooking fire; the copy swaps the bench keyword for the category's."""
    crafting = _crafting()
    assert (crafting.bench(5), crafting.bench(0x01000006)) == ('WorkbenchCookingFire', CR.BENCH)
    rec = {'FormID': '01000009', 'EditorID': 'NVDLC01VendingArtDeco', 'SCRI': '8', 'FULL': 'Vending'}
    station = crafting.station(0x10, rec, 'm.nif', BOUNDS)
    kwda = dict(subrecords(station[24:]))[b'KWDA']
    assert struct.unpack('<2I', kwda) == (0x99, 0x01000006)
    assert [sig for sig, _ in crafting.builder.writer.records] == ['KYWD']


def test_every_recipe_in_a_category_is_built_and_the_rest_counted():
    """Both categories' recipes are built; one in a category no station opens is counted; one without is skipped."""
    crafting = _crafting()
    crafting.menus, built, crafting.tokens = {8: 0x01000006}, [], []
    crafting._recipe = lambda rec, category: built.append((rec['EditorID'], category))
    crafting.recipes = [{'EditorID': 'Stew', 'DATA.Category': '00000005'},
                        {'EditorID': 'Snack', 'DATA.Category': '01000006'},
                        {'EditorID': 'Loose', 'DATA.Category': '00000000'}]
    crafting.build()
    assert built == [('Stew', 5), ('Snack', 0x01000006)]
    counts = crafting.builder.counts
    assert counts['recipe skipped (no category)'] == 1 and counts['recipes of a category no station opens'] == 1
