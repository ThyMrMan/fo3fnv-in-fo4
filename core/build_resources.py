"""One resource setting for the whole build: how many worker processes each pool may start.

A profile (low, balanced, full) gives the share of the logical cores the build's workers may keep busy and the
share of physical memory the whole build (the main process and its workers) may hold. Every pool asks
pool_workers() with what one of its workers commits; the answer is the fewest of the jobs, the profile's cores,
an explicit worker count, and what the memory budget holds. Free memory always keeps SPARE_BYTES, and a
TESCONV_JOB_MEM_GB cap (process_job) bounds the budget too. Worker counts never change what a pool makes.

The profile comes from TESCONV_RESOURCES (pipeline.run --resources sets it), else DEFAULT.

See: docs/fork/fo4_build_resources.md#profiles
"""
import os
from dataclasses import dataclass

from core.memory_budget import free_ram_bytes
from core.process_job import job_memory_limit_bytes, total_memory
from core.process_memory import own_commit

__all__ = ["PROFILES", "DEFAULT", "ENV_VAR", "Machine", "profile_name", "machine", "plan_workers", "pool_workers",
           "profile_cores", "core_workers", "memory_budget"]

ENV_VAR = "TESCONV_RESOURCES"
GB = 1 << 30
#: Free memory every profile leaves to the system and the desktop.
SPARE_BYTES = 2 * GB


@dataclass(frozen=True)
class Profile:
    """Shares of the logical cores the workers may use and of physical memory the whole build may hold."""
    cores: float
    memory: float


#: low leaves half the cores and memory free; full is the build as it was (every core but one, all free memory).
PROFILES = {'low': Profile(0.5, 0.5), 'balanced': Profile(0.75, 0.75), 'full': Profile(1.0, 1.0)}
DEFAULT = 'balanced'


@dataclass(frozen=True)
class Machine:
    """What a worker plan reads of a machine: logical cores, physical and free memory, and the main process's
    commit, in bytes (0: unknown)."""
    cpus: int
    total: int = 0
    free: int = 0
    main: int = 0
    job_cap: int = 0


def profile_name() -> str:
    """The profile TESCONV_RESOURCES names, else DEFAULT."""
    name = os.environ.get(ENV_VAR, '').strip().lower()
    return name if name in PROFILES else DEFAULT


def machine() -> Machine:
    """This machine and process now."""
    return Machine(max(1, os.cpu_count() or 2), total_memory(), free_ram_bytes() or 0, own_commit() or 0,
                   job_memory_limit_bytes())


def core_workers(cpus: int, profile: str) -> int:
    """Workers `profile` keeps busy on `cpus` cores (full: all but one)."""
    share = PROFILES[profile].cores
    return max(1, cpus - 1 if share >= 1 else int(cpus * share))


def memory_budget(box: Machine, profile: str) -> 'int | None':
    """Bytes the pool's workers may commit together: free memory less SPARE_BYTES, within the profile's share of
    physical memory and any job cap less the main process; None when free memory is unknown."""
    if not box.free:
        return None
    room = box.free - SPARE_BYTES
    share = PROFILES[profile].memory
    if share < 1 and box.total:
        room = min(room, int(box.total * share) - box.main)
    if box.job_cap:
        room = min(room, box.job_cap - box.main)
    return room


def plan_workers(each: int, jobs: int, box: Machine, profile: str, asked: int = 0) -> int:
    """Workers for `jobs` jobs of `each` bytes a worker on `box` under `profile`; `asked` (an explicit count) stands
    in for the profile's cores. At least one."""
    count = min(asked or core_workers(box.cpus, profile), jobs or 1)
    budget = memory_budget(box, profile)
    if budget is not None and each:
        count = min(count, budget // each)
    return max(1, count)


def pool_workers(each: int, jobs: int, asked: int = 0) -> int:
    """plan_workers() on this machine now, under the chosen profile."""
    return plan_workers(each, jobs, machine(), profile_name(), asked)


def profile_cores() -> int:
    """Workers the chosen profile keeps busy on this machine's cores, memory aside."""
    return core_workers(max(1, os.cpu_count() or 2), profile_name())
