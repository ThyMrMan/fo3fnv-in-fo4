"""tools.disasm.fnv_names: demangling, the function holding an address, and the two sources side by side."""

import json

from tools.disasm import fnv_names as N


def test_demangle_gives_class_then_method():
    """Class::Method, a template class by name; a C name loses its underscore."""
    assert N.demangle('?Create@NiRenderedTexture@@SAPAV1@XZ') == 'NiRenderedTexture::Create'
    assert N.demangle('?Highlight@?$ListBox@H@@QAE_NPAVTile@@@Z') == 'ListBox::Highlight'
    assert N.demangle('_memcpy') == 'memcpy'


def _sources(tmp_path):
    """A units.json with two functions and an engine map naming the first."""
    units = tmp_path / 'units.json'
    units.write_text(json.dumps({'units': [{'source': 'src/a.cpp', 'functions': [
        {'address': '0x00741500', 'symbol': '?FUN_00741500@CaravanGame@@QAEXXZ', 'size': 0x40},
        {'address': '0x00741600', 'symbol': '?Run@Thing@@QAEXXZ', 'size': 0x10}]}]}), encoding='utf-8')
    engine = tmp_path / 'engine_map.tsv'
    engine.write_text('# header\naddress\tsize\tname\tname_tier\txbox\tunit\tsubsystem\tplaced\n'
                      '00741500\t64\tCaravanMenu::DoIdle\tvt\t82000000\tcaravanmenu.cpp\tfallout/interface\tvt\n',
                      encoding='utf-8')
    return N.decomp(units), N.engine_map(engine)


def test_an_address_inside_a_function_finds_it(tmp_path):
    """An address in a body maps to its function's start; past the body or before any function, none."""
    functions, _ = _sources(tmp_path)
    starts = sorted(functions)
    assert N.holder(functions, starts, 0x741520) == 0x741500
    assert N.holder(functions, starts, 0x741540) is None
    assert N.holder(functions, starts, 0x401000) is None


def test_a_line_shows_both_names_and_marks_placeholders(tmp_path):
    """The decomp's address-made name is marked; the Xbox name and its tier follow; a missing one says none."""
    functions, xbox = _sources(tmp_path)
    first = N.line(0x741500, functions, xbox)
    assert 'decomp=CaravanGame::FUN_00741500 (placeholder)' in first and 'xbox=CaravanMenu::DoIdle [vt]' in first
    assert N.line(0x741600, functions, xbox).endswith('xbox=none')
