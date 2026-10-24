#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Seal the exact patched runtime after automated Windows acceptance passes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

RUNTIME_FAMILIES = ("bin", "data", "doc", "Ext", "lib", "Mod")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def same_path(left: Path, right: Path) -> bool:
    # Windows paths are case-insensitive. normcase is a no-op on POSIX, which is
    # useful for the portable unit tests below.
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def seal(run_root: Path, *, run_id: str = "", run_attempt: str = "", source_commit: str = "") -> Path:
    root = run_root.resolve(strict=True)
    report_path = root / "WINDOWS_ACCEPTANCE.json"
    host_manifest_path = root / "hosts" / "patched" / "host-manifest.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"Acceptance report missing: {report_path}")
    if not host_manifest_path.is_file():
        raise FileNotFoundError(f"Patched host manifest missing: {host_manifest_path}")

    report = read_json(report_path)
    if report.get("status") != "passed" or report.get("windows_automated_acceptance_passed") is not True:
        raise RuntimeError("Refusing to seal a runtime because automated Windows acceptance did not pass")
    if report.get("release_ready") is not False:
        raise RuntimeError("Automated acceptance must retain release_ready=false")

    host = read_json(host_manifest_path)
    if host.get("variant") != "patched":
        raise RuntimeError("Expected the patched host manifest")
    host_root_value = host.get("host_root")
    if not isinstance(host_root_value, str) or not host_root_value:
        raise RuntimeError("Patched host manifest does not identify host_root")
    build_root = Path(host_root_value)
    expected_build_root = root / "hosts" / "patched" / "build"
    if not same_path(build_root, expected_build_root):
        raise RuntimeError(f"Patched host root is not the tested build tree: {build_root}")

    records: list[dict[str, Any]] = []
    for family in RUNTIME_FAMILIES:
        family_root = expected_build_root / family
        if not family_root.is_dir():
            raise FileNotFoundError(f"Accepted runtime directory missing: {family_root}")
        for path in sorted((item for item in family_root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()):
            records.append({
                "path": path.relative_to(expected_build_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    if not records:
        raise RuntimeError("Accepted runtime seal would be empty")

    output_dir = root / "accepted-runtime-seal"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "accepted-runtime-manifest.json"
    value = {
        "schema": 1,
        "purpose": "Exact patched FreeCAD runtime retained from the host that passed automated Windows acceptance",
        "source_run_id": run_id,
        "source_run_attempt": run_attempt,
        "source_commit": source_commit,
        "accepted_host_manifest": {"path": "hosts/patched/host-manifest.json", "sha256": sha256(host_manifest_path)},
        "acceptance_report": {"path": "WINDOWS_ACCEPTANCE.json", "sha256": sha256(report_path)},
        "runtime_root": "hosts/patched/build",
        "runtime_families": list(RUNTIME_FAMILIES),
        "files": records,
        "release_ready": False,
    }
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output_path)
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    parser.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA", ""))
    args = parser.parse_args(argv)
    output = seal(args.run_root, run_id=args.run_id, run_attempt=args.run_attempt, source_commit=args.source_commit)
    print(json.dumps({"status": "sealed", "manifest": str(output), "release_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
