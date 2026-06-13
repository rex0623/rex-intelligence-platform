"""Phase 17B — File-based runtime lock for concurrent access prevention.

Provides a non-blocking exclusive advisory lock on runtime/rip.lock using
POSIX fcntl.flock.  WSL2/Linux only.

Infrastructure only: no operator reply text or Mock LINE messages.
"""

import contextlib
import fcntl
from pathlib import Path

from app.core.config import get_runtime_dir


class RuntimeLockBusy(RuntimeError):
    """Raised when the runtime lock is held by another process."""


@contextlib.contextmanager
def acquire_runtime_lock():
    """Non-blocking exclusive flock on runtime/rip.lock.

    Raises RuntimeLockBusy immediately if another process holds the lock.
    The lock is automatically released when the holding process exits (OS
    closes all fds on death); no manual stale-lock cleanup needed.
    Not re-entrant within the same process.
    """
    lock_path = get_runtime_dir() / "rip.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise RuntimeLockBusy("runtime_lock_busy")
    try:
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()
