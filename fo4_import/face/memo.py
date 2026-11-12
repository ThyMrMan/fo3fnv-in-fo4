"""Pure face computations remembered per process by the contents of their inputs.

Every NPC of one sex fits against the same FO4 face and the same FNV mean
head, so the texel mapping, alignment and masks between them come out the
same each time. `by_content` keeps the last KEPT results of such a function,
keyed by a SHA-1 of its arguments' bytes (`digest`), and hands them back
read-only, so no caller can change a value another shares.

See: docs/fork/fo4_tool_audit.md#meshes
"""

import functools
import hashlib
from collections import OrderedDict

import numpy as np

#: Results kept per function: one per sex for the build's fits, with room for a bake's per-NPC heads.
KEPT = 4


def _feed(sha, value) -> None:
    """Add `value` (an array, bytes, a sequence of values, or anything with a stable repr) to `sha`."""
    if isinstance(value, np.ndarray):
        sha.update(f'{value.dtype}{value.shape}'.encode())
        sha.update(np.ascontiguousarray(value).data)
    elif isinstance(value, bytes):
        sha.update(b'bytes%d:' % len(value) + value)
    elif isinstance(value, (tuple, list)):
        sha.update(f'({len(value)}'.encode())
        for item in value:
            _feed(sha, item)
    else:
        sha.update(repr(value).encode())


def digest(*values) -> bytes:
    """The SHA-1 of `values`' contents (arrays by dtype, shape and bytes)."""
    sha = hashlib.sha1()
    _feed(sha, values)
    return sha.digest()


def frozen(value):
    """`value` with every array in it (or in its tuples and lists) made read-only."""
    if isinstance(value, np.ndarray):
        value.flags.writeable = False
    elif isinstance(value, (tuple, list)):
        for item in value:
            frozen(item)
    return value


def by_content(fn, kept: int = KEPT):
    """`fn` (pure; arrays, sequences or plain values in) remembered per process for its last `kept` inputs."""
    held, limit = OrderedDict(), kept

    @functools.wraps(fn)
    def remembered(*args):
        """fn(*args), from the kept results when the same contents were seen."""
        key = digest(*args)
        if key in held:
            held.move_to_end(key)
            return held[key]
        held[key] = value = frozen(fn(*args))
        if len(held) > limit:
            held.popitem(last=False)
        return value
    return remembered
