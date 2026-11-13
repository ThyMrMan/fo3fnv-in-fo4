"""The build's stage timer: each stage's own seconds, a nested stage taken out of the one it runs in.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import pstats
import time

from fo4_import.pipeline import stage_timer
from fo4_import.pipeline.stage_timer import charged, report, timed


def test_a_nested_stage_is_taken_out_of_the_outer_one():
    """The outer stage's 0.3 s holds the inner's 0.6 s run through charged(); each reports its own."""
    @timed('test outer')
    def outer():
        """Wait, then run the inner stage."""
        time.sleep(0.3)
        charged('test inner', time.sleep, 0.6)

    outer()
    spent = {line.split(': ')[0]: float(line.split(': ')[1][:-1]) for line in report()}
    assert 0.3 <= spent['stage test outer'] <= 0.4
    assert 0.6 <= spent['stage test inner'] <= 0.7


def test_a_named_stage_runs_under_cprofile(tmp_path, monkeypatch):
    """With PROFILE_ENV naming a stage, its calls (two here) add up in one .prof with a .txt summary; a nested
    profiled stage does not start a second profiler; unnamed stages write nothing."""
    monkeypatch.setenv(stage_timer.PROFILE_ENV, 'test profiled, test nested')
    monkeypatch.setattr(stage_timer, 'PROFILE_DIR', tmp_path)

    def busy():
        """Some Python work to profile, and a nested profiled stage."""
        charged('test nested', sum, range(1000))
        return sorted(range(1000), reverse=True)[0]

    assert charged('test profiled', busy) == 999 and charged('test profiled', busy) == 999
    charged('test plain', sum, range(10))
    stats = pstats.Stats(str(tmp_path / 'test_profiled.prof'))
    assert next(v[0] for k, v in stats.stats.items() if k[2] == 'busy') == 2
    assert 'busy' in (tmp_path / 'test_profiled.txt').read_text(encoding='utf-8')
    assert sorted(p.name for p in tmp_path.iterdir()) == ['test_profiled.prof', 'test_profiled.txt']
