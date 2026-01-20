import os
import fcntl
import time
import contextlib

LOCK_FILE = '/tmp/nhi.lock'

class LockManager:
    """
    Manages filesystem locks using fcntl (POSIX).
    Ensures that only one process can modify critical infrastructure files at a time.
    """
    
    def __init__(self, lock_file=LOCK_FILE):
        self.lock_file = lock_file
        self.file_handle = None

    def acquire(self):
        """
        Acquire an exclusive lock. Blocks until the lock is available.
        """
        print(f"Attempting to acquire lock: {self.lock_file}")
        self.file_handle = open(self.lock_file, 'w')
        try:
            # LOCK_EX: Exclusive lock
            # LOCK_NB: Non-blocking (we don't use it here because we WANT to wait)
            fcntl.flock(self.file_handle, fcntl.LOCK_EX)
            print("Lock acquired.")
        except IOError as e:
            # Should not happen without LOCK_NB, but good practice
            print(f"Failed to acquire lock: {e}")
            self.file_handle.close()
            raise

    def release(self):
        """Release the lock."""
        if self.file_handle:
            try:
                fcntl.flock(self.file_handle, fcntl.LOCK_UN)
                self.file_handle.close()
                print("Lock released.")
            except Exception as e:
                print(f"Error releasing lock: {e}")
            finally:
                self.file_handle = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

@contextlib.contextmanager
def acquire_lock(lock_file=LOCK_FILE):
    """
    Context manager wrapper for LockManager.
    Usage:
        with acquire_lock():
            # critical section
    """
    manager = LockManager(lock_file)
    manager.acquire()
    try:
        yield
    finally:
        manager.release()
