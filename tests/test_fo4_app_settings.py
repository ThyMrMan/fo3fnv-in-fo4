"""fo4_import.app.settings: defaults, saving, merging and where each file lives."""

import json

import pytest

from fo4_import.app import settings


def test_round_trip_and_new_keys(tmp_path):
    """A saved file keeps its choices and gains keys added since it was written."""
    path = tmp_path / 'fo4_app.json'
    path.write_text(json.dumps({'source': 'fallout3', 'games': {'fallout4': str(tmp_path)}}), encoding='utf-8')
    loaded = settings.load(path)
    assert loaded['source'] == 'fallout3'
    assert loaded['games'] == {'fallout4': str(tmp_path), 'falloutnv': '', 'fallout3': ''}
    assert loaded['per_source']['falloutnv']['output']['kind'] == 'folder'
    settings.save(loaded, path)
    assert settings.load(path) == loaded


def test_missing_file_is_defaults(tmp_path):
    """No saved file means the defaults."""
    assert settings.load(tmp_path / 'none.json') == settings.defaults()


def test_replacement_file_places(tmp_path):
    """The replacement file sits beside the app, in the output folder, or at the user's path."""
    s = settings.defaults()
    s['per_source']['falloutnv']['output']['path'] = str(tmp_path / 'out')
    block = s['per_source']['falloutnv']['replacements']
    assert settings.replacement_file(s, 'falloutnv') == settings.APP_DIR / 'replacements' / 'falloutnv.json'
    block['where'] = 'output'
    assert settings.replacement_file(s, 'falloutnv') == tmp_path / 'out' / 'replacements.json'
    block.update(where='custom', path=str(tmp_path / 'mine.json'))
    assert settings.replacement_file(s, 'falloutnv') == tmp_path / 'mine.json'


def test_default_output_under_work_dir(tmp_path):
    """With no output chosen, output goes under the work folder, one per game."""
    s = settings.defaults()
    s['work_dir'] = str(tmp_path)
    assert settings.output_dir(s, 'fallout3') == tmp_path / 'output' / 'Fallout3'


def test_bad_choices_refused():
    """Unknown output kinds, replacement places and mod source kinds are refused."""
    s = settings.defaults()
    s['per_source']['falloutnv']['output']['kind'] = 'ba2'
    with pytest.raises(ValueError):
        settings.check(s)
    s = settings.defaults()
    s['mod_sources'] = [{'folder': '.', 'kind': 'vortex'}]
    with pytest.raises(ValueError):
        settings.check(s)


def test_game_dir_prefers_choice(tmp_path):
    """A game folder the user chose wins over detection."""
    s = settings.defaults()
    s['games']['fallout4'] = str(tmp_path)
    assert settings.game_dir(s, 'fallout4') == tmp_path
