"""Run an external tool so it can never wait on a click: no crash dialog, and a time limit.

A crashing tool can leave Windows Error Reporting or a registered just-in-time
debugger (vsjitdebugger) waiting for someone to answer, and an unattended
build waits with it. The tool starts with the error mode that asks no
crash dialog (inherited from us, restored after the start), joins a job of
its own whose limit forces that mode on every process in it, and the job is
ended at the time limit. Off Windows only the time limit applies.

See: docs/fork/fo4_pipeline.md#lodgen-unattended
"""

import ctypes
import queue
import subprocess
import sys
import threading
import time

from core.process_job import kill_process_tree
from core.subprocess_flags import POPEN_FLAGS

#: SetErrorMode: no critical-error box, no Windows Error Reporting on a crash, no missing-file box; children inherit it.
QUIET_ERRORS = 0x0001 | 0x0002 | 0x8000
#: JOBOBJECT_BASIC_LIMIT_INFORMATION's class, and its limit forcing that crash mode on every process in the job.
BASIC_LIMITS, DIE_ON_UNHANDLED_EXCEPTION = 2, 0x400
#: Rights needed to put a process in a job.
PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001
IS_WINDOWS = sys.platform == 'win32'


class BasicLimits(ctypes.Structure):
    """JOBOBJECT_BASIC_LIMIT_INFORMATION."""
    _fields_ = (('per_process_time', ctypes.c_longlong), ('per_job_time', ctypes.c_longlong),
                ('flags', ctypes.c_uint32), ('min_working_set', ctypes.c_size_t),
                ('max_working_set', ctypes.c_size_t), ('process_limit', ctypes.c_uint32),
                ('affinity', ctypes.c_size_t), ('priority', ctypes.c_uint32), ('scheduling', ctypes.c_uint32))


def kernel32():
    """kernel32 with pointer-sized handles declared for every call made here."""
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = ctypes.c_void_p
    k32.CreateJobObjectW.restype = k32.OpenProcess.restype = handle
    k32.CreateJobObjectW.argtypes = (handle, ctypes.c_wchar_p)
    k32.SetInformationJobObject.argtypes = (handle, ctypes.c_int, handle, ctypes.c_uint32)
    k32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    k32.AssignProcessToJobObject.argtypes = (handle, handle)
    k32.TerminateJobObject.argtypes = (handle, ctypes.c_uint)
    k32.CloseHandle.argtypes = (handle,)
    k32.SetErrorMode.argtypes, k32.SetErrorMode.restype = (ctypes.c_uint,), ctypes.c_uint
    return k32


def quiet_job(k32):
    """A new job forcing the no-crash-dialog mode on its processes; None when it cannot be made."""
    job = k32.CreateJobObjectW(None, None)
    limits = BasicLimits(flags=DIE_ON_UNHANDLED_EXCEPTION)
    if job and k32.SetInformationJobObject(job, BASIC_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)):
        return job
    if job:
        k32.CloseHandle(job)
    return None


def quiet_start(k32, cmd, cwd) -> subprocess.Popen:
    """Popen of `cmd` (output piped) under QUIET_ERRORS, which it inherits; ours is restored after."""
    old = k32.SetErrorMode(QUIET_ERRORS) if k32 else 0
    try:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0, cwd=cwd,
                                **POPEN_FLAGS)
    finally:
        if k32:
            k32.SetErrorMode(old)


def contain(k32, job, pid: int) -> None:
    """Put process `pid` in `job` (no-op without one)."""
    if job is None:
        return
    process = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
    if process:
        k32.AssignProcessToJobObject(job, process)
        k32.CloseHandle(process)


def read_lines(pipe, lines: queue.Queue) -> None:
    """Queue each line of `pipe` (decoded, newline stripped), then None."""
    for raw in iter(pipe.readline, b''):
        lines.put(raw.decode('utf-8', errors='replace').rstrip('\r\n'))
    lines.put(None)


def drain(lines: queue.Queue, kept: list, deadline) -> bool:
    """Echo and keep queued lines until the pipe closes (False) or `deadline` (monotonic; None: never) passes
    (True)."""
    while deadline is None or time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if line is None:
            return False
        print(line, flush=True)
        kept.append(line)
    return True


def run_unattended(cmd, timeout: 'float | None' = None, cwd=None) -> tuple:
    """Run `cmd` with no crash dialog for it or its children, ended after `timeout` seconds (None: no limit), its
    output echoed as it comes; (output, exit code, timed out)."""
    k32 = kernel32() if IS_WINDOWS else None
    job = quiet_job(k32) if k32 else None
    proc = quiet_start(k32, cmd, cwd)
    contain(k32, job, proc.pid)
    lines, kept = queue.Queue(), []
    threading.Thread(target=read_lines, args=(proc.stdout, lines), daemon=True).start()
    timed_out = drain(lines, kept, None if timeout is None else time.monotonic() + timeout)
    if timed_out and not (job and k32.TerminateJobObject(job, 1)):
        kill_process_tree(proc.pid)
    code = proc.wait()
    if job:
        k32.CloseHandle(job)
    return '\n'.join(kept), code, timed_out
