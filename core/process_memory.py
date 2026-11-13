"""Committed memory (private bytes) of this process and of the other processes in the build's job.

Windows only, read through the documented kernel32 calls; elsewhere every reading is None. Never raises.

See: docs/fork/fo4_build_resources.md#stage-memory
"""
import ctypes
import os
import sys

from core.process_job import JOB_ENV_VAR

__all__ = ["own_commit", "job_commits", "process_commit"]

_IS_WIN = sys.platform == "win32"
#: OpenProcess right enough for GetProcessMemoryInfo, and OpenJobObject's right to list the job's processes.
_QUERY_LIMITED, _JOB_QUERY = 0x1000, 0x0004
#: QueryInformationJobObject's class for JOBOBJECT_BASIC_PROCESS_ID_LIST.
_PROCESS_ID_LIST = 3
#: Process ids one listing holds.
_MAX_IDS = 4096


class _Counters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS_EX."""
    _fields_ = (("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), *(
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            "PrivateUsage")))


class _IdList(ctypes.Structure):
    """JOBOBJECT_BASIC_PROCESS_ID_LIST with room for _MAX_IDS ids."""
    _fields_ = (("assigned", ctypes.c_ulong), ("listed", ctypes.c_ulong), ("ids", ctypes.c_size_t * _MAX_IDS))


def _kernel32():
    """kernel32 with pointer-sized handle types on the calls used here."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k32.OpenJobObjectW.restype = ctypes.c_void_p
    k32.OpenJobObjectW.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p]
    k32.QueryInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong,
                                              ctypes.c_void_p]
    k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    return k32


_K32 = _kernel32() if _IS_WIN else None


def process_commit(pid: int) -> "int | None":
    """Private bytes of process `pid`; None when it cannot be read (gone, no right, not Windows)."""
    if _K32 is None:
        return None
    handle = _K32.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return None
    try:
        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        ok = _K32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        return int(counters.PrivateUsage) if ok else None
    finally:
        _K32.CloseHandle(handle)


def own_commit() -> "int | None":
    """Private bytes of this process."""
    return process_commit(os.getpid())


def _job_ids() -> list:
    """Ids of the processes in the job named by JOB_ENV_VAR (process_job.create_pool_job); [] without one."""
    name = os.environ.get(JOB_ENV_VAR, "").strip()
    job = _K32.OpenJobObjectW(_JOB_QUERY, False, name) if _K32 is not None and name else None
    if not job:
        return []
    try:
        listing = _IdList()
        ok = _K32.QueryInformationJobObject(job, _PROCESS_ID_LIST, ctypes.byref(listing), ctypes.sizeof(listing),
                                            None)
        return list(listing.ids[:listing.listed]) if ok else []
    finally:
        _K32.CloseHandle(job)


def job_commits() -> list:
    """Private bytes of each other readable process in the build's job."""
    own = os.getpid()
    return [c for c in (process_commit(pid) for pid in _job_ids() if pid != own) if c is not None]
