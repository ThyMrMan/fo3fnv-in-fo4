"""File stamps: a value computed from a file is kept while its size and time stay, read again once they change.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import os

from fo4_import.base.file_stamps import Stamps


def test_a_kept_value_is_reused_until_the_file_changes(tmp_path):
    """The second load reuses the first's value without reading; a rewrite (new size) reads again; an entry
    not used in a run is dropped when it saves."""
    source, other, memo, reads = tmp_path / 'a.psc', tmp_path / 'b.psc', tmp_path / 'memo.json', []
    source.write_text('one')
    other.write_text('two')
    read = lambda path: reads.append(path.name) or path.read_text()
    first = Stamps(memo)
    assert first.value(source, read) == 'one' and first.value(other, read) == 'two'
    first.save()
    second = Stamps(memo)
    assert second.value(source, read) == 'one' and reads == ['a.psc', 'b.psc']
    second.save()
    source.write_text('three')
    os.utime(source, ns=(1, 1))
    third = Stamps(memo)
    assert third.value(source, read) == 'three' and reads[-1] == 'a.psc'
    assert str(other).lower() not in third.kept
