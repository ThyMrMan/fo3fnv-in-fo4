"""A recording that never converts is tried once, not every build, until its source or transcript changes.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

from fo4_import.spike import voice


def test_a_failed_job_is_skipped_until_its_recording_changes(tmp_path, monkeypatch):
    """Build 1 tries both missing jobs, one fails; build 2 tries neither (one written, one known failed); a changed
    recording is tried again."""
    good, bad = tmp_path / 'good.ogg', tmp_path / 'bad.ogg'
    good.write_bytes(b'g')
    bad.write_bytes(b'b')
    out = tmp_path / 'out' / 'Type'
    jobs = [(good, out / 'a.fuz', 'Hello.'), (bad, out / 'b.fuz', 'Nope.')]
    tried = []

    def fake_convert(todo, lipgen):
        """Write the good one's file only."""
        tried.append(sorted(dest.name for _, dest, _ in todo))
        for source, dest, _ in todo:
            if source == good:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b'fuz')
        return sum(source == good for source, _, _ in todo)
    monkeypatch.setattr(voice, 'convert', fake_convert)
    record = tmp_path / 'failed.json'
    assert voice.convert_new(jobs, tmp_path, record) == 1
    assert voice.convert_new(jobs, tmp_path, record) == 0
    bad.write_bytes(b'changed')
    voice.convert_new(jobs, tmp_path, record)
    assert tried == [['a.fuz', 'b.fuz'], ['b.fuz']]
