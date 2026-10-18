"""Free physical memory, and how many processes of a known size it holds.

Kept apart from worker_budget, which the face fits' cache tag covers: an edit
here must not rerun them.

See: docs/fork/fo4_pipeline.md#audit-fixes
"""
import ctypes

__all__ = ["free_ram_bytes", "memory_workers"]


def free_ram_bytes() -> "int | None":
    """Free physical memory in bytes (Windows' GlobalMemoryStatusEx); None where it cannot be read."""
    status = (ctypes.c_uint64 * 8)(64)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(status)
    except AttributeError:
        return None
    return int(status[2]) if ok else None


def memory_workers(wanted: int, each: int, spare: int) -> int:
    """How many of `wanted` processes of `each` bytes free memory holds with `spare` bytes left over, at least one;
    `wanted` when free memory cannot be read."""
    free = free_ram_bytes()
    if free is None:
        return wanted
    return max(1, min(wanted, (free - spare) // each))
