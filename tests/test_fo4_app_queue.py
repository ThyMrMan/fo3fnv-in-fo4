"""The Convert screen's queue off screen: targets convert one after another, a failure stops the queue, and the
Finished screen gets every target's stages.

See: docs/fork/fo4_gui.md#queue
"""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from fo4_import.app import convert_view as CV
from fo4_import.app import settings as S
from fo4_import.app import stages as ST
from fo4_import.app.queue_box import Queued, named, settings_for
from fo4_import.app.runner import Result

GAME, DLC = Queued('fallout3', '', ('build',), ST.Scope('world')), Queued('fallout3', 'Anchorage.esm', ('build',),
                                                                          ST.Scope('world'))


@pytest.fixture(scope='module')
def app():
    """One QApplication for the module, drawing off screen when none exists yet."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    return QApplication.instance() or QApplication([])


class Hook:
    """A stand-in Qt signal: connect, then emit calls the slots."""

    def __init__(self):
        """No slots yet."""
        self.slots = []

    def connect(self, slot) -> None:
        """Add `slot`."""
        self.slots.append(slot)

    def emit(self, *args) -> None:
        """Call every slot with `args`."""
        for slot in self.slots:
            slot(*args)


class FakeThread:
    """A StageThread that ends at once with the next queued outcome, noting which target it ran."""
    outcomes, ran = [], []

    def __init__(self, plan: list, settings: dict, source: str):
        """Note the target `settings` converts."""
        self.line, self.done, self.target = Hook(), Hook(), settings['per_source'][source]['target']

    def start(self) -> None:
        """Finish with the next outcome."""
        FakeThread.ran.append(self.target)
        self.done.emit(*FakeThread.outcomes.pop(0))


def _view(monkeypatch, outcomes: list) -> tuple:
    """A ConvertView over default settings whose stages finish with `outcomes`; (view, what it reported)."""
    FakeThread.outcomes, FakeThread.ran = list(outcomes), []
    monkeypatch.setattr(CV, 'StageThread', FakeThread)
    monkeypatch.setattr(ST, 'plan', lambda settings, source, chosen, scope, file: [('build', 'Build', ['x'])])
    monkeypatch.setattr(ST, 'target', lambda settings, source: type('T', (), {'output': Path('out') / source})())
    view, reported = CV.ConvertView(lambda: (S.defaults(), Path('settings.json'))), []
    view.finished.connect(lambda *args: reported.append(args))
    return view, reported


def test_queued_targets_convert_in_order_and_report_together(app, monkeypatch):
    """The game, then its DLC: both run, and Finished gets both builds named by target."""
    view, reported = _view(monkeypatch, [([Result('build', 'Build', 0, 1.0)], ['a'], ''),
                                         ([Result('build', 'Build', 0, 2.0)], ['b'], 'x.zip')])
    view.queue.add(GAME)
    view.queue.add(DLC)
    view._run_queue()
    assert FakeThread.ran == ['', 'Anchorage.esm'] and not view.queue.items
    results, warnings, zips, _folder = reported[0]
    assert [r.label for r in results] == ['Fallout3.esm: Build', 'Anchorage.esm: Build']
    assert warnings == ['a', 'b'] and zips == 'x.zip' and len(reported) == 1
    assert view.start.isEnabled() and not view.stop.isEnabled()


def test_a_failed_target_stops_the_queue_and_keeps_the_rest_waiting(app, monkeypatch):
    """The game fails: its DLC stays queued, and Finished gets the game's build alone, unnamed."""
    view, reported = _view(monkeypatch, [([Result('build', 'Build', 1, 1.0)], [], '')])
    view.queue.add(GAME)
    view.queue.add(DLC)
    view._run_queue()
    assert FakeThread.ran == [''] and view.queue.items == [DLC]
    assert [r.label for r in reported[0][0]] == ['Build'] and view.queue.run.isEnabled()


def test_a_queued_run_converts_its_own_target_and_labels_name_it():
    """settings_for picks the item's game and target on a copy; named leads each label with the plugin."""
    settings = S.defaults()
    got = settings_for(settings, DLC)
    assert got['source'] == 'fallout3' and got['per_source']['fallout3']['target'] == 'Anchorage.esm'
    assert settings['per_source']['fallout3'].get('target', '') == ''
    assert named([Result('build', 'Build', 0, 1.0)], 'X.esp')[0].label == 'X.esp: Build'
