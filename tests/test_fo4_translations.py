"""Our menus' translation files: written as F4SE loads them, named after FalloutHelpers.esl, one per game language
with English filling the gaps; every key our movies and F3NV.dll use is in the English file.

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


def _code(folder, text):
    """[(folder, glob)] over one movie source holding `text` under `folder`."""
    (folder / 'menu' / 'as3').mkdir(parents=True, exist_ok=True)
    (folder / 'menu' / 'as3' / 'Menu.as').write_text(text, encoding='utf-8')
    return [(folder, '**/as3/**/*.as')]


def _installed(data, language):
    """The lines of installed language file `language` under `data`, after its BOM."""
    raw = (data / 'Interface' / 'Translations' / f'FalloutHelpers_{language}.txt').read_bytes()
    assert raw[:2] == b'\xff\xfe'
    return raw[2:].decode('utf-16-le').split('\r\n')


def test_every_game_language_is_installed_as_utf16_with_english_filling_the_gaps(tmp_path):
    """Each sLanguage gets FalloutHelpers_<language>.txt (BOM, UTF-16 LE, CRLF); a language's own text wins and
    its missing keys are English."""
    sources = _sources(tmp_path / 'src', en=['$F3NV_A\tOne', '$F3NV_B\tTwo'], de=['$F3NV_A\tEins'])
    assert T.install(tmp_path / 'data', sources) == len(T.LANGUAGES)
    assert _installed(tmp_path / 'data', 'en') == ['$F3NV_A\tOne', '$F3NV_B\tTwo', '']
    assert _installed(tmp_path / 'data', 'de') == ['$F3NV_A\tEins', '$F3NV_B\tTwo', '']
    assert _installed(tmp_path / 'data', 'ja') == ['$F3NV_A\tOne', '$F3NV_B\tTwo', '']


def test_no_file_while_english_has_no_keys(tmp_path):
    """With an empty English source nothing is installed."""
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
    """A used key en.txt lacks, an en.txt key nothing uses and a key only German has are found; a template's key
    counts as used; fonts and comment lines are not keys."""
    code = _code(tmp_path / 'code', '   // a "$F3UI_Comment" here\n'
                                    'f("$F3UI_Used"); g("$F3UI_Missing"); h("$MAIN_Font_Bold"); k("$ 5");\n'
                                    'm("$F3UI_Template\\t" + n);')
    sources = _sources(tmp_path / 'src', en=['$F3UI_Used\tUsed', '$F3UI_Spare\tSpare', '$F3UI_Template\t{0} x'],
                       de=['$F3UI_Used\tBenutzt', '$F3UI_German\tNur'])
    assert T.check(code, sources) == {'key missing from en.txt': ['$F3UI_Missing (Menu.as)'],
                                      'en.txt key no movie uses': ['$F3UI_Spare'],
                                      'key only in another language': ['de.txt: $F3UI_German']}


def test_our_code_uses_only_keys_the_english_file_has():
    """Every "$KEY" in our movies and F3NV.dll is in en.txt, and en.txt and the other languages hold no stray keys."""
    assert T.check() == {'key missing from en.txt': [], 'en.txt key no movie uses': [],
                         'key only in another language': []}


def test_the_code_scanned_includes_the_dll_and_its_pipboy_keys():
    """F3NV.dll's sources are scanned: the Pip-Boy's CND and REPAIR keys come from pipboy.cpp."""
    used = T.used_keys()
    assert 'pipboy.cpp' in used['$F3NV_CND'] and 'pipboy.cpp' in used['$F3NV_REPAIR']
    assert 'DialogueMenu.as' in used['$F3NV_LEAVE']
