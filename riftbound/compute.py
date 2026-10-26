"""Keeping long runs (audits, self-play) gentle on the machine they run on.

Runs default to a quarter of the logical cores, below-normal priority and one
math thread per process, so the machine keeps plenty of headroom (and heat
margin) and stays usable while they run.
"""

from __future__ import annotations

import os
import sys


def default_workers() -> int:
    """A quarter of the logical cores, at least 1 (4 on a 16-thread CPU)."""
    return max(1, (os.cpu_count() or 4) // 4)


def be_gentle() -> None:
    """Call at the start of every worker process: below-normal priority (other
    programs come first) and a single thread for numpy / torch math."""
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ.setdefault(var, "1")
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        below_normal = 0x00004000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # The process handle is pointer-sized: with ctypes' default int it was
        # truncated and the call failed silently.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), below_normal)
    else:
        try:
            os.nice(10)
        except OSError:
            pass
    if "torch" in sys.modules:
        sys.modules["torch"].set_num_threads(1)
