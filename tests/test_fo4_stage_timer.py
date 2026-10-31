"""The build's stage timer: each stage's own seconds, a nested stage taken out of the one it runs in.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import time

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
