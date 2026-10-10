"""The export, each type file parsed once a run and shared by every reader.

See: docs/fork/fo4_pipeline.md#skeleton
"""

import functools
from pathlib import Path

from tes5_import.base.text_reader import parse_export_file


@functools.cache
def _parsed(path: str) -> tuple:
    """Every record in the export file at `path` (() for none), parsed once."""
    return tuple(parse_export_file(path))


def export_records(export_dir, sig: str) -> tuple:
    """Type `sig`'s records in `export_dir`; shared, so callers never change them."""
    return _parsed(str(Path(export_dir) / f'{sig}.txt'))
