"""Our menus' translation files: written as F4SE loads them, named after FalloutHelpers.esl.

See: docs/fork/swf_framework.md#translations
"""

import pytest

from fo4_import.base import translations as T


def test_each_source_is_installed_as_utf16_with_a_bom_under_the_helper_plugin(tmp_path):
    """en.txt becomes Interface/Translations/FalloutHelpers_en.txt: BOM, UTF-16 LE, $KEY<tab>text CRLF lines."""
    assert T.install(tmp_path) == len(list(T.SOURCES.glob('*.txt')))
    raw = (tmp_path / 'Interface' / 'Translations' / 'FalloutHelpers_en.txt').read_bytes()
    assert raw[:2] == b'\xff\xfe'
    lines = raw[2:].decode('utf-16-le').split('\r\n')
    assert lines[-1] == '' and '$F3UI_TranslationCheck\tTranslated from FalloutHelpers_en.txt' in lines


def test_the_spike_has_one_key_in_the_file_and_one_in_none():
    """Spike 5's Check key is in en.txt; its Absent key is in no file."""
    keys = set().union(*(T.entries(source) for source in T.SOURCES.glob('*.txt')))
    assert '$F3UI_TranslationCheck' in keys and '$F3UI_TranslationAbsent' not in keys


@pytest.mark.parametrize('line', ['F3UI_NoDollar\ttext', '$F3UI_NoTab', '$\ttext', '$F3UI_Two\ttabs\there',
                                  '$F3UI_Long\t' + 'x' * 520])
def test_a_line_f4se_would_skip_or_cut_fails(tmp_path, line):
    """A line without $KEY, a tab and text, with a second tab, or past F4SE's buffer raises ValueError."""
    source = tmp_path / 'en.txt'
    source.write_text(line + '\n', encoding='utf-8')
    with pytest.raises(ValueError):
        T.entries(source)
