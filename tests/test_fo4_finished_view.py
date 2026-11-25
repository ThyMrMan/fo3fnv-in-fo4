"""The Finished screen's headline: what ended the run, in words.

See: docs/fork/fo4_gui.md#child-output
"""

from types import SimpleNamespace

from fo4_import.app.finished_view import headline, summary


def _stage(label: str, code, seconds: float = 1.0) -> SimpleNamespace:
    """A stage result."""
    return SimpleNamespace(label=label, code=code, seconds=seconds)


def test_stage_times_read_in_minutes_and_hours():
    """Seconds under a minute, then minutes, then hours."""
    lines = summary([_stage('Export', 0, 42), _stage('Build', 0, 754), _stage('Faces', 0, 3903)]).splitlines()
    assert lines == ['Export: done in 42s', 'Build: done in 12m 34s', 'Faces: done in 1h 05m 03s']


def test_the_headline_names_the_stage_that_ended_the_run():
    """Finished; nothing ran; a stopped stage; a failed stage with its exit code and where to read why."""
    assert headline([_stage('Export', 0)]) == 'Conversion finished.'
    assert headline([]).startswith('Nothing was converted')
    assert '"Faces" was stopped' in headline([_stage('Export', 0), _stage('Faces', None)])
    failed = headline([_stage('Export', 0), _stage('Rebuild what changed', 1)])
    assert '"Rebuild what changed" failed (exit code 1)' in failed and '"logs" folder' in failed
