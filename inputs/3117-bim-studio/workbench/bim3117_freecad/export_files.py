# SPDX-License-Identifier: GPL-3.0-or-later
"""Publish a local export bundle with file-level atomic replace and rollback.

The final path is the metadata commit marker. This is not a crash-atomic
filesystem transaction: readers must check payload hashes in that metadata.
Caught publication failures restore previous files. Backups are retained and
their location is reported if restoration itself fails.
"""
import os
from pathlib import Path
import shutil
import tempfile


class ExportFileError(ValueError):
    pass


def _check_targets(paths, overwrite):
    if not paths:
        raise ExportFileError("No export files were requested")
    if len({str(path).casefold() for path in paths}) != len(paths):
        raise ExportFileError("Export destinations overlap")
    parent = paths[0].parent
    if not parent.is_dir() or any(path.parent != parent for path in paths):
        raise ExportFileError("Choose an existing output folder for the complete export bundle")
    for path in paths:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ExportFileError(f"Export destination is not a regular file: {path.name}")
        if path.exists() and not overwrite:
            raise ExportFileError(f"File already exists; confirm replacement of the complete bundle: {path.name}")


def publish_bundle(paths, writer, overwrite=False, before_commit=None):
    """Call writer(staged_paths), then publish payloads followed by metadata.

    All paths must share an existing directory. ``writer`` must produce every
    staged file; it may validate readback before any destination is replaced.
    ``before_commit`` checks that the source model is still the captured revision.
    Adjacent exclusive locks cover every output, including sidecar collisions
    between exports with different main filenames.
    """
    paths = [Path(os.path.abspath(os.fspath(path))) for path in paths]
    _check_targets(paths, overwrite)
    lock_paths = sorted((path.with_name(path.name + ".3117-export.lock") for path in paths),
                        key=lambda path: str(path).casefold())
    acquired = []
    stage = None
    preserve_recovery = False
    try:
        for lock_path in lock_paths:
            try:
                descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as error:
                raise ExportFileError(f"Export is locked: {lock_path.name}. Finish the other export; if a previous process stopped, inspect its output before removing its lock.") from error
            acquired.append(lock_path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
                lock.write(f"3117 export process {os.getpid()}\n")
        _check_targets(paths, overwrite)
        stage = Path(tempfile.mkdtemp(prefix=".3117-export-", dir=paths[0].parent))
        staged = [stage / path.name for path in paths]
        result = writer(staged)
        for path in staged:
            if not path.is_file() or path.is_symlink():
                raise ExportFileError(f"Exporter did not produce {path.name}")
            with path.open("rb") as file:
                os.fsync(file.fileno())
        if before_commit is not None:
            before_commit()
        _check_targets(paths, overwrite)
        backups = {}
        for index, path in enumerate(paths):
            if path.exists():
                backup = stage / (f"backup-{index}-" + path.name)
                shutil.copy2(path, backup)
                backups[path] = backup
        published = []
        try:
            for temporary, destination in zip(staged, paths):
                os.replace(temporary, destination)
                published.append(destination)
        except BaseException as error:
            recovery_errors = []
            for destination in reversed(published):
                try:
                    if destination in backups:
                        os.replace(backups[destination], destination)
                    else:
                        destination.unlink()
                except OSError as recovery_error:
                    recovery_errors.append(f"{destination.name}: {recovery_error}")
            if recovery_errors:
                preserve_recovery = True
                raise ExportFileError(f"Export failed and recovery needs attention. Retained backup folder: {stage}. " + "; ".join(recovery_errors)) from error
            raise
        return result
    finally:
        if stage is not None and not preserve_recovery:
            shutil.rmtree(stage, ignore_errors=True)
        if not preserve_recovery:
            for lock_path in reversed(acquired):
                lock_path.unlink(missing_ok=True)
