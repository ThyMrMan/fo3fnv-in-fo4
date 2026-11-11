"""A mesh worker caps its own memory: an allocation past the cap is a MemoryError in that worker, the mesh is
recorded as too large, and the build faults it instead of converting it again uncapped.

See: docs/fork/fo4_build_speed.md#worker-memory
"""

import subprocess
import sys

import pytest

from fo4_import.base.source_fault import SourceFault
from fo4_import.pipeline import mesh_cache as MC

CAPPED = ('import sys; sys.path.insert(0, r"{root}"); from core.process_job import limit_own_memory\n'
          'print(limit_own_memory(256 * 2 ** 20))\n'
          'try:\n    bytearray(1024 * 2 ** 20)\nexcept MemoryError:\n    print("MemoryError")\n')


@pytest.mark.skipif(sys.platform != 'win32', reason='job objects are Windows only')
def test_a_capped_process_gets_a_memory_error_not_a_swap_storm():
    """A process capped at 256 MB that asks for 1 GB gets MemoryError."""
    out = subprocess.run([sys.executable, '-c', CAPPED.format(root=MC.ROOT)], capture_output=True, text=True,
                         timeout=60).stdout.split()
    assert out == ['True', 'MemoryError']


def test_a_mesh_out_of_memory_in_the_pool_is_faulted_not_retried(monkeypatch, tmp_path):
    """_warm says a mesh ran out of memory; cached_convert then faults it untouched."""
    def huge(*_args):
        """A conversion that runs out of memory."""
        raise MemoryError
    monkeypatch.setattr(MC, 'cached_convert', huge)
    mesh = tmp_path / 'Big.nif'
    assert MC._warm((str(mesh), None, None, True, {})) == (True, None)
    monkeypatch.undo()
    monkeypatch.setattr(MC, 'TOO_LARGE', {MC._same(str(mesh).replace('\\', '/'))})
    with pytest.raises(SourceFault, match='too large'):
        MC.cached_convert(mesh)
