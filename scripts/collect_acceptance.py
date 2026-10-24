#!/usr/bin/env python3
"""Collect native Windows evidence; preparation-only reports cannot pass."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from run_acceptance import KIT, SOURCE_COMMIT, now, sha256, verify_inputs, write_json
import run_native
import run_regression
import run_public_gui
import prepare_ifc
sys.path.insert(0, str(KIT / "build"))
from build_freecad import binding_definitions, tree_records


def read(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return result


def record_valid(record: dict) -> bool:
    try:
        path = Path(record["path"])
        return path.is_file() and sha256(path) == record["sha256"]
    except (KeyError, TypeError, OSError):
        return False


def validate_build(path: Path, variant: str, lock: dict) -> dict:
    errors = []
    value = read(path)
    if value.get("status") != "built_not_acceptance_tested" or value.get("variant") != variant:
        errors.append("Wrong/missing completed build variant")
    if value.get("source_commit") != SOURCE_COMMIT or value.get("source_version") != "1.1.4":
        errors.append("Wrong FreeCAD source identity")
    native = value.get("platform", {})
    if native.get("system") != "Windows" or native.get("machine", "").lower() not in ("amd64", "x86_64"):
        errors.append("Build did not run on native Windows x64")
    expected_patch = lock["patch_sha256"] if variant == "patched" else None
    if value.get("patch_sha256") != expected_patch or value.get("patch_helper_sha256") != lock["patch_helper_sha256"]:
        errors.append("Reviewed patch identity mismatch")
    expected_document = lock["source_document_patched_sha256" if variant == "patched" else "source_document_before_sha256"]
    if value.get("document_cpp", {}).get("sha256") != expected_document or not record_valid(value.get("document_cpp", {})):
        errors.append("Document.cpp does not match the reviewed before/after bytes")
    if value.get("expected_python_version") != [3, 12, 10] or value.get("expected_qt_version") != "6.8.3":
        errors.append("The Windows runtime does not match the pinned LibPack")
    flags = value.get("cmake", {}).get("flags", {})
    if flags.get("FREECAD_USE_PYSIDE") != "ON" or flags.get("FREECAD_USE_SHIBOKEN") != "ON":
        errors.append("Compiled Qt bindings are not enabled")
    definitions = value.get("bindings", {}).get("definitions", {})
    if definitions.get("status") != "passed" or not record_valid(definitions.get("project", {})):
        errors.append("Compiled Qt binding definitions were not verified")
    else:
        try:
            if binding_definitions(Path(definitions["project"]["path"])) != definitions:
                errors.append("Actual Release Qt binding definitions differ from the manifest")
        except (OSError, ValueError, RuntimeError) as error:
            errors.append("Cannot verify actual Release Qt binding definitions: " + str(error))
    binary_records = (list(value.get("executables", {}).values()) + list(value.get("libraries", {}).values())
                      + value.get("runtime_libraries", []))
    required_libs = {"FreeCADBase.dll", "FreeCADApp.dll", "FreeCADGui.dll", "Part.pyd", "TechDraw.pyd"}
    if set(value.get("executables", {})) != {"gui", "cmd"} or not required_libs.issubset(value.get("libraries", {})):
        errors.append("Host binary inventory is incomplete")
    if any(not record_valid(item) for item in binary_records):
        errors.append("A built executable or library is missing or changed")
    for name, pinned in lock["assets"].items():
        actual = value.get("inputs", {}).get(name, {})
        if actual.get("sha256") != pinned["sha256"] or not record_valid(actual):
            errors.append("Missing/changed pinned build archive: " + name)
    for command_name in ("configure", "compile"):
        command = value.get("build_commands", {}).get(command_name, {})
        if command.get("exit_code") != 0 or not record_valid(command.get("log", {})):
            errors.append("Build command lacks successful original log: " + command_name)
    imports = value.get("bindings", {}).get("imports", {})
    if imports.get("exit_code") != 0 or not record_valid(imports.get("log", {})):
        errors.append("Qt binding import evidence is missing or changed")
    elif not all(name in Path(imports["log"]["path"]).read_text(encoding="utf-8", errors="replace").lower()
                 for name in ("pyside6", "shiboken6")):
        errors.append("GUI does not import the compiled Qt binding libraries")
    source_record = value.get("source_integrity", {})
    source_before_hash = None
    if not record_valid(source_record):
        errors.append("Source integrity evidence is missing or changed")
    else:
        source = read(Path(source_record["path"]))
        expected_changes = ["src/Gui/Document.cpp"] if variant == "patched" else []
        before, after = source.get("before", {}), source.get("after", {})
        actual_changes = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        if not before or not after or source.get("changes") != expected_changes or actual_changes != expected_changes:
            errors.append("Unexpected or unrecorded changes to the FreeCAD source")
        source_root = Path(value.get("source_root", ""))
        if not source_root.is_dir() or tree_records(source_root) != after:
            errors.append("Current FreeCAD source tree differs from its recorded build input")
        source_before_hash = hashlib.sha256(json.dumps(before, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    dependency = value.get("dependency_identity", {})
    signature = hashlib.sha256(json.dumps(dependency, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if not dependency or value.get("dependency_signature") != signature:
        errors.append("Dependency signature is missing or invalid")
    compiler = value.get("compiler", {})
    cmake = value.get("cmake", {})
    for name, record in (("compiler", compiler.get("compiler", {})), ("linker", compiler.get("linker", {})),
                         ("CMake", cmake.get("binary", {})), ("CMake cache", cmake.get("cache", {}))):
        if not record_valid(record):
            errors.append("Current toolchain file missing or changed: " + name)
    normalized_options = dict(flags)
    normalized_options["FREECAD_LIBPACK_DIR"] = "<shared verified LibPack>"
    normalized_options["CMAKE_GENERATOR_INSTANCE"] = "<recorded Visual Studio2022 instance>"
    actual_dependency = {
        "assets": {key: asset["sha256"] for key, asset in lock["assets"].items()},
        "compiler_sha256": compiler.get("compiler", {}).get("sha256"),
        "linker_sha256": compiler.get("linker", {}).get("sha256"),
        "toolset_version": compiler.get("toolset_version"),
        "windows_sdk_version": definitions.get("windows_sdk_version"),
        "cmake_sha256": cmake.get("binary", {}).get("sha256"),
        "configuration": "Release", "options": normalized_options}
    if dependency != actual_dependency:
        errors.append("Dependency signature does not describe the actual recorded toolchain")
    return {"status": "passed" if not errors else "failed", "errors": errors,
            "variant": variant, "manifest": {"path": str(path), "sha256": sha256(path)},
            "dependency_signature": value.get("dependency_signature"),
            "source_before_sha256": source_before_hash,
            "executables": value.get("executables"), "libraries": value.get("libraries")}


def gate(callback, *args, **kwargs) -> dict:
    try:
        result = callback(*args, **kwargs)
        if "valid" in result:
            result["status"] = "passed" if result["valid"] else "failed"
        return result
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        return {"status": "failed", "errors": [str(error)]}


def collect(root: Path) -> dict:
    lock = read(KIT / "build/windows-build.lock.json")
    manifests = {variant: root / "hosts" / variant / "host-manifest.json" for variant in ("unpatched", "patched")}
    gates = {"build_" + variant: gate(validate_build, path, variant, lock) for variant, path in manifests.items()}
    signatures = [gates["build_" + variant].get("dependency_signature") for variant in manifests]
    source_hashes = [gates["build_" + variant].get("source_before_sha256") for variant in manifests]
    same_dependencies = all(signatures) and signatures[0] == signatures[1] and all(source_hashes) and source_hashes[0] == source_hashes[1]
    gates["same_toolchain"] = {"status": "passed" if same_dependencies else "failed",
                              "errors": [] if same_dependencies else ["A/B toolchain or dependency identities differ"]}
    results = root / "results"
    gates["ifc_runtime"] = gate(prepare_ifc.verify_preflight,
        root / "ifc-runtime/ifc-preflight.json", manifests["unpatched"])
    gates["unpatched_observation"] = gate(run_regression.verify_summary,
        results / "regression-unpatched/summary.json", manifests["unpatched"], "unpatched")
    gates["patched_regression"] = gate(run_regression.verify_summary,
        results / "regression-patched/summary.json", manifests["patched"], "patched")
    gates["native_3117"] = gate(run_native.verify_summary,
        results / "native-patched/summary.json", manifests["patched"], "patched")
    gates["public_zip_gui"] = gate(run_public_gui.verify_summary,
        results / "public-gui-patched/summary.json", manifests["patched"])
    gates["frozen_inputs"] = verify_inputs()
    try:
        native = read(results / "native-patched/summary.json")
        public = read(results / "public-gui-patched/summary.json")
        regression = read(results / "regression-patched/summary.json")
        hosts = [native["expected_host"], public["host"], regression["expected_host"]]
        identity_ok = all(host["libraries"] == hosts[0]["libraries"] and
                          host["build_manifest"] == hosts[0]["build_manifest"] for host in hosts)
        ifc_ok = native["expected_ifc"] == public["ifc_inventory"]
        gates["cross_suite_identity"] = {"status": "passed" if identity_ok and ifc_ok else "failed",
            "errors": [] if identity_ok and ifc_ok else ["Patched suites did not use one host/IFC runtime"]}
    except (OSError, ValueError, TypeError, KeyError) as error:
        gates["cross_suite_identity"] = {"status": "failed", "errors": [str(error)]}
    passed = all(value.get("status") == "passed" for value in gates.values())
    return {"schema": 1, "created_at": now(), "status": "passed" if passed else "failed",
            "scope": "Native Windows automated build/history/native/public-GUI acceptance",
            "source_commit": SOURCE_COMMIT, "windows_automated_acceptance_passed": passed,
            "gates": gates, "windows_desktop_acceptance": "pending",
            "manual_checklist": "inputs/3117-bim-studio/docs/WINDOWS_ACCEPTANCE.md",
            "release_ready": False, "installer_built": False, "upstream_submitted": False,
            "note": "A3 physical print, external BIM application inspection, desktop upgrade/restore/uninstall, and target Windows 10/11 visual review remain separate."}


def markdown(report: dict) -> str:
    rows = []
    for name, value in report["gates"].items():
        details = "; ".join(value.get("errors", [])) or "Raw evidence and hashes verified"
        rows.append(f"| {name} | {value.get('status')} | {details.replace('|', '/').replace(chr(10), ' ')} |")
    return ("# Windows acceptance result\n\n"
            f"Automated result: **{report['status']}**. Generated: {report['created_at']}.\n\n"
            "| Gate | Result | Detail |\n| --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
            "Desktop checklist: **pending**. `release_ready: false`. No installer or upstream submission was created.\n\n"
            "An unpatched Windows result is observed independently; this report does not borrow the Linux crash outcome. "
            "See WINDOWS_ACCEPTANCE.json and original logs/reports for process exits, DLL identities and check counts.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.run_root.resolve(strict=True)
    report = collect(root)
    write_json(root / "WINDOWS_ACCEPTANCE.json", report)
    (root / "WINDOWS_ACCEPTANCE.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "windows_automated_acceptance_passed": report["windows_automated_acceptance_passed"],
                      "release_ready": False, "report": str(root / "WINDOWS_ACCEPTANCE.json")}))
    return 0 if report["windows_automated_acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
