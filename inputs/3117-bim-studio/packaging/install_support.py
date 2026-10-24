# SPDX-License-Identifier: GPL-3.0-or-later
"""User-level workbench install/restore, using only Python's standard library.

FreeCAD supplies the actual user data path; no Windows path is guessed.
Uninstall moves our installation into a backup, never deletes user projects.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid
import xml.etree.ElementTree as ET

PROJECT_ID = "org.3117.bimstudio.workbench"
INSTALL_NAME = "BIM3117"
BACKUP_NAME = "BIM3117_Backups"
RECEIPT_NAME = "bim3117-install.json"
BASELINE = "1.1.4"
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}


class InstallError(RuntimeError):
    """An installation cannot proceed safely."""


def _is_link(path):
    details = path.lstat()
    # Windows junctions/reparse points are not always reported as symlinks.
    return stat.S_ISLNK(details.st_mode) or bool(getattr(details, "st_file_attributes", 0) & 0x400)


def _plain(path, *, directory=False):
    if _is_link(path):
        raise InstallError(f"Linked paths are not supported: {path}")
    if directory and not path.is_dir():
        raise InstallError(f"Expected a directory: {path}")
    if not directory and not path.is_file():
        raise InstallError(f"Expected a regular file: {path}")


def source_files(directory):
    """Return regular payload files, rejecting links rather than following them."""
    directory = Path(directory)
    _plain(directory, directory=True)
    files = []
    for current, directories, names in os.walk(directory, followlinks=False):
        for name in directories:
            _plain(Path(current) / name, directory=True)
        directories[:] = sorted(name for name in directories if name not in SKIP_DIRS)
        for name in sorted(names):
            source = Path(current) / name
            _plain(source)
            if source.suffix in {".pyc", ".pyo"} or name == RECEIPT_NAME:
                continue
            files.append(source)
    return files


def package_info(source_root):
    source_root = Path(source_root)
    _plain(source_root, directory=True)
    workbench = source_root / "workbench"
    _plain(workbench, directory=True)
    for filename in ("Init.py", "InitGui.py", "package.xml"):
        _plain(workbench / filename)
    _plain(source_root / "LICENSE")
    _plain(source_root / "THIRD_PARTY.md")
    try:
        package = ET.parse(workbench / "package.xml").getroot()
        name = package.findtext("{*}name")
        version = package.findtext("{*}version")
    except ET.ParseError as exc:
        raise InstallError("Invalid workbench package.xml") from exc
    if name != INSTALL_NAME or not version or not all(c.isalnum() or c in ".-+" for c in version):
        raise InstallError("Package identity/version does not match BIM3117")
    return {"project_id": PROJECT_ID, "version": version, "baseline": BASELINE}


def _layout(user_data):
    user_data = Path(user_data)
    if not user_data.is_absolute():
        raise InstallError("Use FreeCAD.getUserAppDataDir(); an absolute path is required")
    _plain(user_data, directory=True)
    # Resolve the host-supplied location once, then only fixed children are used.
    user_data = user_data.resolve()
    modules, backups = user_data / "Mod", user_data / BACKUP_NAME
    for directory in (modules, backups):
        if directory.exists() or directory.is_symlink():
            _plain(directory, directory=True)
    target = modules / INSTALL_NAME
    if target.exists() or target.is_symlink():
        _plain(target, directory=True)
    return user_data, modules, backups, target


def installed_info(directory):
    directory = Path(directory)
    _plain(directory, directory=True)
    receipt = directory / RECEIPT_NAME
    if not receipt.exists():
        raise InstallError(f"Folder is not owned by the 3117 installer; preserve or rename it manually: {directory}")
    _plain(receipt)
    try:
        info = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError(f"Cannot read the installation receipt: {directory}") from exc
    if not isinstance(info, dict) or info.get("project_id") != PROJECT_ID:
        raise InstallError(f"Folder does not have a matching 3117 installation identity: {directory}")
    return info


@contextmanager
def _install_lock(user_data):
    path = user_data / "BIM3117-install.lock"
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise InstallError("Another installer is running, or an interrupted run left BIM3117-install.lock. Close installer sessions and inspect the lock before retrying.") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def _backup_path(backups, purpose):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return backups / f"{purpose}-{stamp}-{uuid.uuid4().hex[:8]}"


def _receipt(stage, info):
    hashes = {}
    for path in source_files(stage):
        hashes[path.relative_to(stage).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {**info, "installed_at_utc": datetime.now(timezone.utc).isoformat(), "sha256": hashes}
    (stage / RECEIPT_NAME).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install(source_root, user_data):
    """Stage and replace only our fixed workbench folder, restoring on failure."""
    source_root = Path(source_root)
    info = package_info(source_root)
    source = (source_root / "workbench").resolve()
    payload = source_files(source)
    user_data, modules, backups, target = _layout(user_data)
    if source == target or target in source.parents or source in target.parents:
        raise InstallError("Install from a separate extracted distribution, not the active workbench")
    previous = None
    with _install_lock(user_data):
        if target.exists():
            installed_info(target)
        modules.mkdir(exist_ok=True)
        backups.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="BIM3117-stage-", dir=user_data))
        try:
            for item in payload:
                destination = stage / item.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
            for filename in ("LICENSE", "THIRD_PARTY.md"):
                shutil.copy2(source_root / filename, stage / filename)
            _receipt(stage, info)
            if target.exists():
                previous = _backup_path(backups, "previous")
                target.replace(previous)
            try:
                stage.replace(target)
            except BaseException:
                if previous is not None and not target.exists():
                    previous.replace(target)
                raise
        finally:
            # This is the exact private temporary directory created above.
            if stage.exists():
                shutil.rmtree(stage)
    return {**info, "target": str(target), "backup": str(previous) if previous else None,
            "restart_required": True}


def list_backups(user_data):
    _, _, backups, _ = _layout(user_data)
    result = []
    if not backups.exists():
        return result
    for path in sorted(backups.iterdir(), reverse=True):
        try:
            info = installed_info(path)
        except (InstallError, OSError):
            continue
        result.append({"name": path.name, "version": info.get("version", "unknown"),
                       "installed_at_utc": info.get("installed_at_utc", "unknown")})
    return result


def uninstall(user_data):
    """Disable by moving our installed folder outside Mod; preserve all files."""
    user_data, _, backups, target = _layout(user_data)
    with _install_lock(user_data):
        if not target.exists():
            raise InstallError("3117 BIM Studio is not installed in this FreeCAD user profile")
        info = installed_info(target)
        backups.mkdir(exist_ok=True)
        backup = _backup_path(backups, "uninstalled")
        target.replace(backup)
    return {"version": info.get("version"), "backup": str(backup), "restart_required": True}


def restore(user_data, backup_name):
    """Restore one listed backup; preserve the current version as another backup."""
    if not isinstance(backup_name, str) or not backup_name or Path(backup_name).name != backup_name or "/" in backup_name or "\\" in backup_name or backup_name in {".", ".."}:
        raise InstallError("Choose a backup name from the list; paths are not accepted")
    user_data, modules, backups, target = _layout(user_data)
    chosen = backups / backup_name
    with _install_lock(user_data):
        info = installed_info(chosen)
        previous = None
        if target.exists():
            installed_info(target)
            previous = _backup_path(backups, "before-restore")
        modules.mkdir(exist_ok=True)
        if previous is not None:
            target.replace(previous)
        try:
            chosen.replace(target)
        except BaseException:
            if previous is not None and not target.exists():
                previous.replace(target)
            raise
    return {"version": info.get("version"), "target": str(target),
            "backup": str(previous) if previous else None, "restart_required": True}
