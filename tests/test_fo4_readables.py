"""FNV notes and books as FO4 readables."""
from fo4_import.spike.readables import Readables


def test_an_image_note_authored_without_an_image_reads_blank():
    """An image note with no XNAM gets an empty page instead of a texture copy."""
    assert Readables._image(None, {'XNAM': ''}) == ''
    assert Readables._image(None, {}) == ''
