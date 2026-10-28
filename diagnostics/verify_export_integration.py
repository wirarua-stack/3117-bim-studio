#!/usr/bin/env python3
"""Exercise a diagnostic installed export candidate on real Windows Python.

FreeCADCmd, geometry, IfcOpenShell and GUI are NOT executed here. This suite
must never be reported as native FreeCAD/Windows acceptance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest import mock

from prepare_export_integration import RELATIVE, sha256, source_inventory
from run_acceptance import verify_inputs

KIT = Path(__file__).resolve().parents[1]
FROZEN_ROOT = KIT / "inputs" / "3117-bim-studio"


def import_file(label: str, path: Path):
    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load module: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_clean(folder: Path) -> None:
    if list(folder.glob("*.3117-export.lock")) or list(folder.glob(".3117-export-*")):
        raise AssertionError("Export left an unexpected lock or temporary directory")


def run(candidate_root: Path, frozen_root: Path, preparation: dict) -> dict:
    if os.name != "nt" or platform.system() != "Windows":
        raise RuntimeError("Real Windows Python required; Linux/offline cannot pass the integration lane")
    frozen_root = frozen_root.resolve(strict=True)
    candidate_root = candidate_root.resolve(strict=True)
    result = {
        "schema": 1, "kind": "windows_installed_export_candidate_integration",
        "status": "running", "checks": [], "checks_passed": 0,
        "windows_native_python_executed": True, "freecad_cmd_executed": False,
        "ifc_geometry_tested": False, "windows_automated_acceptance_passed": False,
        "release_ready": False,
        "scope": "Frozen source copy, user-profile installer upgrade/restore, staged CSV/IFC byte publication",
    }

    def check(name: str, condition: bool) -> None:
        passed = condition is True
        result["checks"].append({"name": name, "status": "passed" if passed else "failed"})
        if not passed:
            raise AssertionError(name)
        result["checks_passed"] += 1

    before = verify_inputs()
    check("frozen input hashes verified before integration", before["status"] == "passed")
    original_files = source_inventory(frozen_root)
    candidate_files = source_inventory(candidate_root)
    changed = sorted(set(original_files) ^ set(candidate_files) | {
        name for name in original_files.keys() & candidate_files.keys()
        if original_files[name] != candidate_files[name]
    })
    check("exact one-file source overlay", changed == [RELATIVE.as_posix()])
    check("candidate provenance matches generated manifest",
          preparation.get("status") == "prepared_for_diagnostic_tests_only"
          and preparation.get("changed_files") == [RELATIVE.as_posix()]
          and preparation.get("frozen_export_sha256") == original_files[RELATIVE.as_posix()]
          and preparation.get("candidate_export_sha256") == candidate_files[RELATIVE.as_posix()]
          and preparation.get("frozen_unchanged") is True)
    check("candidate and frozen exporter are distinct", original_files[RELATIVE.as_posix()] != candidate_files[RELATIVE.as_posix()])

    installer = import_file("candidate_install_support", candidate_root / "packaging/install_support.py")
    with tempfile.TemporaryDirectory(prefix="3117-installed-export-") as temporary:
        root = Path(temporary)
        user_data = root / "FreeCADUserData"
        user_data.mkdir()
        first = installer.install(frozen_root, user_data)
        target = user_data / "Mod/BIM3117"
        active_export = target / "bim3117_freecad/export_files.py"
        check("frozen package installs into isolated user profile",
              Path(first["target"]).resolve() == target.resolve()
              and sha256(active_export) == original_files[RELATIVE.as_posix()])

        second = installer.install(candidate_root, user_data)
        backup = Path(second["backup"]) if second.get("backup") else None
        receipt = installer.installed_info(target)
        check("candidate upgrades workbench with separate recoverable backup",
              backup is not None and backup.is_dir()
              and sha256(backup / "bim3117_freecad/export_files.py") == original_files[RELATIVE.as_posix()])
        check("installed exporter and receipt match exact candidate hash",
              sha256(active_export) == candidate_files[RELATIVE.as_posix()]
              and receipt.get("sha256", {}).get("bim3117_freecad/export_files.py") == candidate_files[RELATIVE.as_posix()])
        check("installer leaves no lock or staging folder",
              not (user_data / "BIM3117-install.lock").exists()
              and not list(user_data.glob("BIM3117-stage-*")))

        module = import_file("installed_candidate_export_files", active_export)
        out = root / "synthetic-exchange-output"
        out.mkdir()
        destinations = [out / "walls.csv", out / "walls.ifc", out / "walls-metadata.json"]
        expected_csv = b"id,quantity\nW-01,3.25\n"
        expected_ifc = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"

        def writer(staged):
            staged[0].write_bytes(expected_csv)
            staged[1].write_bytes(expected_ifc)
            with staged[0].open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            if rows != [{"id": "W-01", "quantity": "3.25"}]:
                raise AssertionError("Staged CSV failed synthetic readback")
            if not staged[1].read_bytes().endswith(b"END-ISO-10303-21;\n"):
                raise AssertionError("Staged synthetic IFC bytes failed readback")
            staged[2].write_text(json.dumps({
                "source_revision": "synthetic-integration-fixture",
                "sha256": {"walls.csv": sha256(staged[0]), "walls.ifc": sha256(staged[1])},
            }), encoding="utf-8")
            return "synthetic_readback_ok"

        replaced = []
        original_replace = module.os.replace

        def track_replace(source, destination):
            replaced.append(Path(destination).name)
            return original_replace(source, destination)

        with mock.patch.object(module.os, "replace", side_effect=track_replace):
            publication = module.publish_bundle(destinations, writer, before_commit=lambda: (
                None if all(not path.exists() for path in destinations)
                else (_ for _ in ()).throw(AssertionError("Destination published before revision check"))
            ))
        check("installed exporter publishes synthetic CSV/IFC and sidecar with successful readback",
              publication == "synthetic_readback_ok"
              and destinations[0].read_bytes() == expected_csv
              and destinations[1].read_bytes() == expected_ifc)
        metadata = json.loads(destinations[2].read_text(encoding="utf-8"))
        check("metadata matches payload hashes and is committed last",
              metadata["sha256"] == {destinations[0].name: sha256(destinations[0]),
                                     destinations[1].name: sha256(destinations[1])}
              and replaced[-3:] == [path.name for path in destinations])
        assert_clean(out)
        check("successful export cleans all private locks and staging directories", True)

        saved = {path: path.read_bytes() for path in destinations}
        try:
            with mock.patch.object(module.os, "fsync", side_effect=OSError("simulated staged sync failure")):
                module.publish_bundle(destinations, writer, overwrite=True)
        except OSError as exc:
            check("staged fsync failure is surfaced", "simulated staged sync failure" in str(exc))
        else:
            raise AssertionError("Staged fsync failure was silently ignored")
        check("fsync failure retains previous complete published bundle",
              all(path.read_bytes() == saved[path] for path in destinations))
        assert_clean(out)
        check("fsync failure cleans owned staging files and locks", True)

        def stale_revision():
            raise ValueError("synthetic source revision changed")
        try:
            module.publish_bundle(destinations, writer, overwrite=True, before_commit=stale_revision)
        except ValueError as exc:
            check("revision mismatch aborts before publication", "source revision changed" in str(exc))
        else:
            raise AssertionError("Unexpected stale revision commit")
        check("revision mismatch preserves prior bundle",
              all(path.read_bytes() == saved[path] for path in destinations))
        assert_clean(out)

        published_count = 0
        def fail_second_replace(source, destination):
            nonlocal published_count
            src, dst = Path(source), Path(destination)
            if src.name == dst.name and dst in destinations and src.parent.name.startswith(".3117-export-"):
                published_count += 1
                if published_count == 2:
                    raise OSError("synthetic second publish failure")
            return original_replace(source, destination)
        try:
            with mock.patch.object(module.os, "replace", side_effect=fail_second_replace):
                module.publish_bundle(destinations, writer, overwrite=True)
        except OSError as exc:
            check("second destination replace failure is surfaced", "synthetic second publish failure" in str(exc))
        else:
            raise AssertionError("Simulated replace failure was not raised")
        check("second replace failure restores all original payload/metadata bytes",
              published_count == 2 and all(path.read_bytes() == saved[path] for path in destinations))
        assert_clean(out)
        check("rollback removes private locks and staging directories", True)

        restored = installer.restore(user_data, backup.name)
        check("installer restores original frozen workbench from preserved backup",
              Path(restored["target"]).resolve() == target.resolve()
              and sha256(active_export) == original_files[RELATIVE.as_posix()])
        check("replaced candidate is retained in a second recoverable backup",
              restored.get("backup") is not None
              and sha256(Path(restored["backup"]) / "bim3117_freecad/export_files.py") == candidate_files[RELATIVE.as_posix()])

    after = verify_inputs()
    check("frozen inputs remain byte-for-byte locked after native Python tests",
          after["status"] == "passed" and after == before and source_inventory(frozen_root) == original_files)
    result["status"] = "passed_diagnostic_integration_not_freecad_acceptance"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, default=FROZEN_ROOT)
    parser.add_argument("--preparation-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        preparation = json.loads(args.preparation_report.read_text(encoding="utf-8"))
        result = run(args.candidate_root, args.frozen_root, preparation)
        code = 0
    except BaseException as exc:
        result = {
            "schema": 1, "kind": "windows_installed_export_candidate_integration",
            "status": "failed", "error": str(exc),
            "freecad_cmd_executed": False, "ifc_geometry_tested": False,
            "windows_automated_acceptance_passed": False, "release_ready": False,
        }
        code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
