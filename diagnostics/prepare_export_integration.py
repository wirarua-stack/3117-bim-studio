#!/usr/bin/env python3
"""Stage a *diagnostic* native-export fix in a copy of the frozen source tree.

No files below inputs/ are edited. The frozen public ZIP and acceptance checks
remain unchanged, and this copy must never be treated as an accepted release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

from export_fsync_candidate import RELATIVE, candidate

KIT = Path(__file__).resolve().parents[1]
FROZEN_ROOT = KIT / "inputs" / "3117-bim-studio"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_inventory(root: Path) -> dict[str, str]:
    """Inventory every source file and reject symlinks, including linked folders."""
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Expected a real frozen source directory")
    records = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("Source links are not allowed: " + str(path))
        if path.is_file():
            records[path.relative_to(root).as_posix()] = sha256(path)
        elif not path.is_dir():
            raise RuntimeError("Unexpected source entry: " + str(path))
    if not records or RELATIVE.as_posix() not in records:
        raise RuntimeError("Frozen source lacks the export module")
    return records


def prepare(frozen_root: Path, candidate_root: Path) -> dict:
    frozen = frozen_root.resolve(strict=True)
    destination = candidate_root.resolve()
    if destination == frozen or destination.is_relative_to(frozen) or frozen.is_relative_to(destination):
        raise RuntimeError("Candidate source must be staged in a disjoint directory")
    if destination.exists():
        raise FileExistsError("Refusing existing candidate root: " + str(destination))
    if not destination.parent.is_dir():
        raise RuntimeError("Candidate root parent must already exist")
    before = source_inventory(frozen)
    shutil.copytree(frozen, destination, symlinks=True)
    copied = source_inventory(destination)
    if copied != before:
        raise RuntimeError("Isolated source copy does not match frozen source")
    with tempfile.TemporaryDirectory(prefix="3117-export-fix-", dir=destination.parent) as temporary:
        generated = candidate(frozen, Path(temporary))
        target = destination / RELATIVE
        if sha256(target) != generated["frozen_sha256"]:
            raise RuntimeError("Candidate target differs from reviewed frozen bytes")
        shutil.copy2(generated["candidate_path"], target)
    after = source_inventory(destination)
    changed = sorted(set(before) ^ set(after) | {
        name for name in before.keys() & after.keys() if before[name] != after[name]
    })
    if changed != [RELATIVE.as_posix()] or after[RELATIVE.as_posix()] != generated["candidate_sha256"]:
        raise RuntimeError("Candidate contains unreviewed source modifications: " + repr(changed))
    if source_inventory(frozen) != before:
        raise RuntimeError("Frozen source changed during candidate generation")
    return {
        "schema": 1, "kind": "isolated_export_candidate_source",
        "status": "prepared_for_diagnostic_tests_only",
        "changed_files": changed,
        "source_files_checked": len(before),
        "frozen_export_sha256": generated["frozen_sha256"],
        "candidate_export_sha256": generated["candidate_sha256"],
        "frozen_unchanged": True,
        "candidate_source_root": str(destination),
        "freecad_cmd_executed": False,
        "windows_acceptance_passed": False,
        "release_ready": False,
        "note": "One-file diagnostic overlay only; original source and public ZIP are frozen.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, default=FROZEN_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.frozen_root, args.output_root)
        code = 0
    except (OSError, ValueError, RuntimeError) as exc:
        result = {
            "schema": 1, "kind": "isolated_export_candidate_source",
            "status": "failed", "error": str(exc),
            "freecad_cmd_executed": False,
            "windows_acceptance_passed": False, "release_ready": False,
        }
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
