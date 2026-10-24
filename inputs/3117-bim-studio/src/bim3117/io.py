# SPDX-License-Identifier: GPL-3.0-or-later
"""Single-file atomic replacement; not a multi-file or crash-durability protocol."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_path(destination):
    """Keep an existing destination intact until a complete new file is ready."""
    target = Path(destination)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=target.suffix,
                                       dir=target.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
