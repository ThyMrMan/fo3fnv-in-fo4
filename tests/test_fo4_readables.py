"""FNV notes and books as FO4 readables."""
from types import SimpleNamespace

from fo4_import.spike.readables import Readables


def test_an_image_note_authored_without_an_image_reads_blank():
    """An image note with no XNAM gets an empty page instead of a texture copy."""
    assert Readables._image(None, {'XNAM': ''}) == ''
    assert Readables._image(None, {}) == ''


def test_comprehension_is_a_skill_book_bonus_perk_on_its_own_fo4_perk():
    """An Adjust Book Skill Points (11) Add Value perk effect is a bonus; other entry points are not."""
    comprehension = {'FormID': '00031DE1', 'EffectCount': '1', 'Effect[0].EntryPoint': '11',
                     'Effect[0].Function': '2', 'Effect[0].Value': '0000803f'}
    other = {**comprehension, 'FormID': '00031DE0', 'Effect[0].EntryPoint': '56'}
    readables = Readables.__new__(Readables)
    readables.bonuses = None
    readables.builder = SimpleNamespace(perks=SimpleNamespace(records=[comprehension, other],
                                                              first={0x31DE1: 0x0A031DE1, 0x31DE0: 0x0A031DE0}))
    assert readables.book_bonuses() == ([0x0A031DE1], [1.0])
