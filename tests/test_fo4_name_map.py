"""The script-name map's kept lower-case index: always what rebuilding it from the dict gives.

See: docs/fork/fo4_plugin_layout.md#stage-times
"""

import random

from fo4_import.spike.attach import NameMap


def test_the_lower_case_index_matches_a_rebuild_after_every_change():
    """Sets and updates of names differing only in case, in place or new, keep `lower` equal to
    {name.lower(): value for name, value in the dict's items()}, the last spelling in insertion order winning."""
    rng = random.Random(7)
    names = ['SunnyRef', 'sunnyref', 'SUNNYREF', 'Doc', 'doc', 'Trudy']
    named = NameMap([('PlayerRef', 0x14)])
    for step in range(2000):
        if rng.random() < 0.2:
            named.update({rng.choice(names): step, rng.choice(names): step + 1})
        else:
            named[rng.choice(names)] = step
        assert named.lower == {name.lower(): value for name, value in named.items()}
