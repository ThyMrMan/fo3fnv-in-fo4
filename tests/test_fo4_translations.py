"""Our menus' translation files: written as F4SE loads them, named after FalloutHelpers.esl; every key our movies
use is in the English file.

See: docs/fork/swf_framework.md#translations
"""

import pytest

from fo4_import.base import translations as T


def _sources(folder, **languages):
    """Write `languages` ({language: lines}) as UTF-8 sources in `folder`; the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for language, lines in languages.items():
        (folder / f'{language}.txt').write_text(''.join(f'{line}\n' for line in lines), encoding='utf-8')
    return folder


def _movie(folder, text):
    """An as3/ source holding `text` under `folder`; the folder."""
    (folder / 'menu' / 'as3').mkdir(parents=True, exist_ok=True)
    (folder / 'menu' / 'as3' / 'Menu.as').write_text(text, encoding='utf-8')
    return folder


def test_each_source_is_installed_as_utf16_with_a_bom_under_the_helper_plugin(tmp_path):
    """en.txt becomes Interface/Translations/FalloutHelpers_en.txt: BOM, UTF-16 LE, $KEY<tab>text CRLF lines."""
    sources = _sources(tmp_path / 'src', en=['$F3UI_Key\tText'], de=['$F3UI_Key\tTekst'])
    assert T.install(tmp_path / 'data', sources) == 2
    raw = (tmp_path / 'data' / 'Interface' / 'Translations' / 'FalloutHelpers_en.txt').read_bytes()
    assert raw[:2] == b'\xff\xfe'
    assert raw[2:].decode('utf-16-le').split('\r\n') == ['$F3UI_Key\tText', '']


def test_an_empty_source_writes_no_file(tmp_path):
    """A language with no keys yet is not installed."""
    assert T.install(tmp_path / 'data', _sources(tmp_path / 'src', en=[])) == 0
    assert not (tmp_path / 'data' / 'Interface').exists()


@pytest.mark.parametrize('line', ['F3UI_NoDollar\ttext', '$F3UI_NoTab', '$\ttext', '$F3UI_Two\ttabs\there',
                                  '$F3UI_Long\t' + 'x' * 520])
def test_a_line_f4se_would_skip_or_cut_fails(tmp_path, line):
    """A line without $KEY, a tab and text, with a second tab, or past F4SE's buffer raises ValueError."""
    source = tmp_path / 'en.txt'
    source.write_text(line + '\n', encoding='utf-8')
    with pytest.raises(ValueError):
        T.entries(source)


def test_check_finds_missing_unused_and_english_less_keys_but_not_fonts(tmp_path):
    """A used key en.txt lacks, an en.txt key nothing uses and a key only German has are found; fonts and comment
    lines are not keys."""
    movies = _movie(tmp_path / 'movies', '   // a "$F3UI_Comment" here\n'
                                         'f("$F3UI_Used"); g("$F3UI_Missing"); h("$MAIN_Font_Bold"); k("$ 5");')
    sources = _sources(tmp_path / 'src', en=['$F3UI_Used\tUsed', '$F3UI_Spare\tSpare'],
                       de=['$F3UI_Used\tBenutzt', '$F3UI_German\tNur'])
    assert T.check(movies, sources) == {'key missing from en.txt': ['$F3UI_Missing (Menu.as)'],
                                        'en.txt key no movie uses': ['$F3UI_Spare'],
                                        'key only in another language': ['de.txt: $F3UI_German']}


def test_our_movies_use_only_keys_the_english_file_has():
    """Every "$KEY" in our movies' sources is in en.txt, and en.txt and the other languages hold no stray keys."""
    assert T.check() == {'key missing from en.txt': [], 'en.txt key no movie uses': [],
                         'key only in another language': []}
