"""An OS-released lock shared by serve, backup, init and restore commands."""
import os
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def process_lock(directory):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    handle=open(root/'process.lock','a+b')
    handle.seek(0)
    if not handle.read(1): handle.write(b'0');handle.flush()
    handle.seek(0)
    acquired=False
    try:
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except OSError as exc:
            raise RuntimeError('Ця база вже використовується. Спершу зупиніть сервер.') from exc
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()
