"""The app's Qt screens off screen: Setup round trip, saving the settings file, the wizard's result."""

import os

import pytest
from PySide6.QtWidgets import QApplication

from fo4_import.app import settings as S
from fo4_import.app import stages as ST
from fo4_import.app import window as W
from fo4_import.app.setup_view import SetupView
from fo4_import.app.wizard import FirstRunWizard


@pytest.fixture(scope='module')
def app():
    """One QApplication for the module, drawing off screen when none exists yet."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    return QApplication.instance() or QApplication([])


def test_setup_keeps_each_games_own_fields(app, tmp_path):
    """Switching the game keeps what was typed for the other; collect() returns every field."""
    view = SetupView()
    s = S.defaults()
    s['mod_sources'] = [{'folder': str(tmp_path), 'kind': 'flat', 'profile': '', 'enabled': False}]
    view.load(s, 'x', False)
    view.output.edit.setText(str(tmp_path / 'nv'))
    view.profile.setText('look')
    view.source.setCurrentIndex(1)
    view.output.edit.setText(str(tmp_path / 'fo3'))
    got = view.collect()
    assert got['source'] == 'fallout3'
    assert got['per_source']['falloutnv']['output']['path'] == str(tmp_path / 'nv')
    assert got['per_source']['falloutnv']['profile'] == 'look'
    assert got['per_source']['fallout3']['output']['path'] == str(tmp_path / 'fo3')
    assert got['mod_sources'] == s['mod_sources']


def test_saving_moves_the_file_between_places(app, tmp_path, monkeypatch):
    """Saving beside the app removes the config folder's copy, and the other way round."""
    monkeypatch.setattr(S, 'APP_DIR', tmp_path / 'app')
    monkeypatch.setattr(S, 'config_dir', lambda: tmp_path / 'config')
    (tmp_path / 'app').mkdir()
    first = W.save_settings(S.defaults(), portable=False)
    assert first == tmp_path / 'config' / S.FILE_NAME and S.settings_path() == first
    second = W.save_settings(S.defaults(), portable=True)
    assert second == tmp_path / 'app' / S.FILE_NAME and not first.exists() and S.settings_path() == second


def test_wizard_result(app, tmp_path):
    """The wizard's fields become settings: the game folders, a folder of mods, output and place."""
    wizard = FirstRunWizard()
    wizard.games['fallout4'].edit.setText(str(tmp_path / 'fo4'))
    wizard.mod_group.buttons()[2].setChecked(True)
    wizard.mod_folder.edit.setText(str(tmp_path / 'mods'))
    wizard.output.edit.setText(str(tmp_path / 'out'))
    wizard.place.setCurrentIndex(1)
    wizard.portable.setChecked(True)
    made, portable = wizard.result_settings()
    assert portable and made['games']['fallout4'] == str(tmp_path / 'fo4')
    assert made['mod_sources'] == [{'folder': str(tmp_path / 'mods'), 'kind': 'folder_of_mods', 'profile': '',
                                    'enabled': True}]
    block = made['per_source']['falloutnv']
    assert block['output']['path'] == str(tmp_path / 'out') and block['replacements']['where'] == 'output'


def test_main_window_builds(app, tmp_path):
    """The window has its four screens; the Convert screen lists every stage, FO4Edit's check left unticked."""
    window = W.MainWindow(S.defaults(), tmp_path / S.FILE_NAME)
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ['Setup', 'Convert', 'Replacements',
                                                                             'Finished']
    assert list(window.convert.checks) == [key for key, _ in ST.ORDER]
    window.convert.refresh(S.defaults())
    assert window.convert.checks['check'].isChecked() and not window.convert.checks['fo4edit'].isChecked()
