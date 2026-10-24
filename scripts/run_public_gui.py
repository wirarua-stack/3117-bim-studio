"""Run the exact frozen installer and six public macros on native Windows.

Every mode gets a fresh GUI process; the installed isolated Thai profile is
shared. The original public macros and model assertions are not modified.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import zipfile

from prepare_ifc import safe_member
from windows_common import (KIT, host_inventory, ifc_inventory, new_output,
                            profile_env, read_json, require_windows, run_process,
                            sha, stamp, validate_checks, validate_identity,
                            validate_ifc, validate_installed_modules, verify_inputs,
                            winpath, write_json)

FROZEN_ZIP_SHA256 = "ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7"
AUTOPILOT_SHA256 = "4a9dfa0f7e9feb61294502044e90aced3febf22d97f872631a186ba5ba126fe5"
STAGES = (
    ("install", "Install_3117_BIM_Studio.FCMacro", "packaged-installer-gui-report.json", 0, 6),
    ("publicsmoke", "Run_3117_Smoke_Test.FCMacro", "public-smoke-macro-report.json", 24, 7),
    ("publicarchitecture", "Run_3117_Architecture_Test.FCMacro", "public-architecture-macro-report.json", 43, 7),
    ("publicmacro", "Run_3117_Exchange_Test.FCMacro", "public-exchange-macro-report.json", 41, 7),
    ("publicbuilding", "Run_3117_Building_Test.FCMacro", "public-building-macro-report.json", 35, 7),
    ("publicdrawings", "Run_3117_Drawings_Test.FCMacro", "public-drawings-macro-report.json", 53, 7),
    ("publictypes", "Run_3117_Types_Test.FCMacro", "public-types-macro-report.json", 52, 7),
)
IFC_MODES = {"publicmacro", "publicbuilding", "publictypes"}


def checked_package(archive, extraction):
    archive = Path(archive).resolve(strict=True)
    if sha(archive) != FROZEN_ZIP_SHA256:
        raise RuntimeError("This gate requires the exact frozen v0.5.0 public ZIP")
    extraction = Path(extraction)
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if not members or any(not safe_member(row.filename) or (row.external_attr >> 16) & 0o170000 == 0o120000 for row in members):
            raise RuntimeError("Unsafe public ZIP paths")
        roots = {row.filename.split("/")[0] for row in members}
        if len(roots) != 1:
            raise RuntimeError("The frozen ZIP must have one top-level folder")
        names = [row.filename.casefold() for row in members]
        if len(names) != len(set(names)):
            raise RuntimeError("Duplicate Windows ZIP member names")
        root = extraction / roots.pop()
        if not root.exists():
            if extraction.exists():
                raise RuntimeError("Extraction directory must be new")
            extraction.mkdir(parents=True)
            package.extractall(extraction)
        manifest, error = read_json(root / "MANIFEST.json")
        if error or manifest.get("version") != "0.5.0" or not manifest.get("sha256"):
            raise RuntimeError("Invalid package manifest")
        for name, digest in manifest["sha256"].items():
            if not safe_member(name) or sha(root / name) != digest:
                raise RuntimeError("Extracted package differs from its frozen manifest: " + name)
        for _, macro, *_ in STAGES:
            if (root / macro).read_bytes() != package.read(root.name + "/" + macro):
                raise RuntimeError("A public macro differs from the frozen ZIP")
    return root


def make_windows_autopilot(path, profile, ifc_path):
    """Port only OS plumbing; preserve the original check/event-handler body.

    The public macro's __file__ hint avoids an OS-native folder chooser that a
    QObject-only automation cannot inspect on Windows. The installer still
    displays and receives its original destination-confirmation dialog.
    """
    original_path = KIT / "inputs" / "package-gui" / "package_autopilot.FCMacro"
    if sha(original_path) != AUTOPILOT_SHA256:
        raise RuntimeError("The archived Linux autopilot changed")
    original = original_path.read_text(encoding="utf-8")
    marker = "def _package_attest_host(phase):"
    end_marker = "\n\n_package_host_start = _package_attest_host('start')"
    start, end = original.index(marker), original.index(end_marker)
    attestation = '''def _package_attest_host(phase):
    report = {"status": "running", "phase": phase}
    try:
        manifest_path = Path(os.environ["BIM3117_HOST_MANIFEST"])
        if _windows_sha(manifest_path) != os.environ["BIM3117_HOST_MANIFEST_SHA256"]:
            raise RuntimeError("Host manifest changed after launch")
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
        report.update(_windows_capture(_windows_profile, _package_mode, completed=phase == "end"))
        required = ("Part",) if phase == "end" and _package_mode != "install" else ()
        okay, reasons = _windows_validate(report, expected, _windows_profile, gui=True,
                                         completed=phase == "end", required_modules=required)
        if not okay:
            raise RuntimeError("Windows DLL/runtime attestation failed: " + repr(reasons))
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
    (_package_output / ("package-" + _package_mode + "-host-" + phase + ".json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    return report
'''
    converted = original[:start] + attestation + original[end:]
    old_profile = "Path(os.environ['XDG_DATA_HOME']).resolve()"
    if converted.count(old_profile) != 1:
        raise RuntimeError("Unexpected archived profile assertion")
    converted = converted.replace(old_profile, "Path(os.environ['FREECAD_USER_DATA']).resolve()")
    prefix = ("# Windows-only transport of the frozen public GUI autopilot.\n"
              "import sys\nfrom pathlib import Path\n"
              "sys.path.insert(0, " + repr(str(KIT / "scripts")) + ")\n"
              "from windows_common import capture_host as _windows_capture, validate_identity as _windows_validate, sha as _windows_sha, configure_ifc_path as _configure_ifc\n"
              "_windows_profile = Path(" + repr(str(profile)) + ")\n"
              "_configure_ifc(" + repr(str(ifc_path)) + ")\n")
    suffix = ("\n# Supply the actual unchanged public macro location to the native interpreter.\n"
              "# This is launcher path plumbing, not a modification of public test code.\n"
              "__file__ = os.environ['BIM3117_PUBLIC_MACRO']\n")
    generated = prefix + converted + suffix
    # Every check, count, installed-file comparison and modal response remains
    # byte-identical to the reviewed Linux autopilot after this anchor, with
    # only explicit UTF-8 added to the three JSON reads on Windows.
    body_marker = "def _package_check(name, condition):"
    old_body = original[original.index(body_marker):]
    new_body = converted[converted.index(body_marker):]
    if old_body != new_body:
        raise RuntimeError("Windows port changed package assertions or modal behavior")
    if converted.count(".read_text()") != 3:
        raise RuntimeError("Unexpected archived JSON read count")
    converted = converted.replace(".read_text()", ".read_text(encoding='utf-8')")
    generated = prefix + converted + suffix
    normalized_body = converted[converted.index(body_marker):].replace(".read_text(encoding='utf-8')", ".read_text()")
    if normalized_body != old_body:
        raise RuntimeError("The Windows UTF-8 adjustment changed more than JSON decoding")
    compile(generated, str(path), "exec")
    Path(path).write_text(generated, encoding="utf-8")
    diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), generated.splitlines(keepends=True),
                                     fromfile="frozen-linux-autopilot", tofile="generated-windows-autopilot"))
    Path(path).with_suffix(".diff").write_text(diff, encoding="utf-8")
    return {"original_sha256": AUTOPILOT_SHA256, "generated_sha256": sha(path),
            "unchanged_assertions_and_handlers_sha256": hashlib.sha256(old_body.encode("utf-8")).hexdigest(),
            "assertions_and_handlers_equal_after_utf8_io_normalization": True,
            "transport_changes": ["Windows loaded-DLL identity instead of /proc", "FREECAD_USER_DATA profile",
                                  "isolated IFC takes precedence over LibPack IFC", "actual public macro __file__ hint",
                                  "explicit UTF-8 for three JSON file reads"]}


def validate_stage(report, inner, process, expected_gui, expected_package):
    reasons = []
    if type(process.get("exit_code")) is not int or process.get("exit_code") != 0 or process.get("timed_out") or process.get("launch_error"):
        reasons.append("GUI process did not exit cleanly")
    if not validate_checks(report, expected_package):
        reasons.append("Package report lacks every expected passing assertion")
    if report.get("zip_sha256") != FROZEN_ZIP_SHA256:
        reasons.append("Package report does not identify the frozen ZIP")
    if expected_gui:
        if not validate_checks(inner, expected_gui) or report.get("gui_checks_passed") != expected_gui:
            reasons.append("Public GUI report lacks every expected passing assertion")
    elif inner:
        reasons.append("Installer must not claim model GUI checks")
    return not reasons, reasons


def evidence_file(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path), "bytes": Path(path).stat().st_size}


def verify_summary(summary_path, host_manifest=None):
    """Re-read raw evidence and hashes; never trust summary totals alone."""
    summary, error = read_json(summary_path)
    errors = []
    if error or summary.get("status") != "passed" or summary.get("schema") != 1 or summary.get("platform") != "windows":
        return {"status": "failed", "errors": [error or "Not a completed native Windows public suite"]}
    if len(summary.get("stages", [])) != len(STAGES):
        return {"status": "failed", "errors": ["Missing public stages"]}
    expected_host = summary["host"]
    if host_manifest:
        try:
            fresh = host_inventory(expected_host["executable"]["path"], host_manifest)
            if fresh != expected_host:
                errors.append("Current host inventory differs from the suite")
        except (OSError, ValueError, RuntimeError) as exception:
            errors.append(str(exception))
    pids, profiles = set(), set()
    for row, (mode, macro_name, _, gui_count, package_count) in zip(summary["stages"], STAGES):
        if row.get("stage") != mode or row.get("status") != "passed":
            errors.append("Missing/premature stage: " + mode)
            continue
        for item in row.get("files", {}).values():
            try:
                if sha(item["path"]) != item["sha256"] or Path(item["path"]).stat().st_size != item["bytes"]:
                    errors.append("Evidence file changed: " + item["path"])
            except OSError:
                errors.append("Evidence file missing: " + item["path"])
        required_files = {"process", "package", "host_start", "host_end", "macro", "log"} | ({"inner"} if gui_count else set())
        if not required_files.issubset(row.get("files", {})):
            errors.append("Required raw evidence missing for " + mode)
            continue
        process, process_error = read_json(row["files"]["process"]["path"])
        report, report_error = read_json(row["files"]["package"]["path"])
        inner, inner_error = read_json(row["files"]["inner"]["path"]) if gui_count else ({}, None)
        if process_error or report_error or inner_error:
            errors.append("Malformed raw evidence for " + mode)
        valid, reasons = validate_stage(report, inner, process, gui_count, package_count)
        errors.extend(mode + ": " + reason for reason in reasons)
        if row["files"]["macro"]["sha256"] != summary["public_macro_sha256"].get(macro_name):
            errors.append("Wrong frozen public macro for " + mode)
        for phase, completed in (("host_start", False), ("host_end", True)):
            identity, identity_error = read_json(row["files"][phase]["path"])
            modules = ("Part",) if completed and mode != "install" else ()
            okay, reasons = validate_identity(identity, expected_host, summary["profile"], gui=True, completed=completed,
                                             required_modules=modules, expected_pid=process.get("pid"))
            if identity_error or identity.get("status") != "passed" or not okay:
                errors.append(mode + "/" + phase + ": " + str(identity_error or reasons))
            if completed:
                profiles.add(winpath(identity.get("user_data", "")))
                if mode != "install" and not validate_installed_modules(identity, KIT / "inputs/3117-bim-studio"):
                    errors.append("Loaded addon is not the frozen installed code: " + mode)
                if mode in IFC_MODES and not validate_ifc(identity, summary["ifc_inventory"]):
                    errors.append("Wrong actual IFC runtime: " + mode)
        pid = process.get("pid")
        if type(pid) is not int or pid <= 0 or pid in pids:
            errors.append("Missing/reused fresh process identifier for " + mode)
        pids.add(pid)
    if len(profiles) != 1 or "" in profiles:
        errors.append("Public modes did not use one isolated profile")
    if summary.get("public_gui_checks_passed") != 248 or summary.get("packaging_checks_passed") != 48:
        errors.append("Wrong total assertion counts")
    if summary.get("zip_sha256") != FROZEN_ZIP_SHA256 or sha(summary["archive"]) != FROZEN_ZIP_SHA256:
        errors.append("Frozen ZIP changed")
    return {"status": "passed" if not errors else "failed", "errors": errors,
            "stages_verified": len(summary["stages"]), "public_gui_checks": 248 if not errors else 0,
            "packaging_checks": 48 if not errors else 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--host-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ifc-python-path", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--archive", type=Path, default=KIT / "inputs/3117_BIM_Studio_v0_5_0_FreeCAD.zip")
    args = parser.parse_args(argv)
    output = new_output(args.output)
    summary_path = output / "summary.json"
    summary = {"schema": 1, "status": "running", "platform": "windows", "started_at_utc": stamp(), "stages": [],
               "scope": "Unchanged public installer and six public GUI macros in seven fresh native Windows GUI processes",
               "host_history_branch_gate": "not_evaluated_by_package_suite", "release_ready": False,
               "windows_acceptance": "not_executed", "host_executed": False}
    write_json(summary_path, summary)
    try:
        require_windows()
        summary["inputs"] = verify_inputs()
        if args.timeout < 30:
            raise RuntimeError("GUI timeout must allow initialization")
        expected = host_inventory(args.host, args.host_manifest)
        summary["host"] = expected
        expected_file = output / "expected-host.json"
        write_json(expected_file, expected)
        archive = args.archive.resolve(strict=True)
        summary.update(archive=str(archive), zip_sha256=sha(archive))
        case = output / "ทดสอบ_แพ็กเกจ_3117"
        profile = case / "โปรไฟล์_ทดสอบ"
        root = checked_package(archive, case / "แตกไฟล์")
        env = profile_env(profile, gui=True)
        ifc_path = args.ifc_python_path.resolve(strict=True)
        summary.update(profile=str(profile), extracted_root=str(root), ifc_inventory=ifc_inventory(ifc_path),
                       public_macro_sha256={macro: sha(root / macro) for _, macro, *_ in STAGES})
        autopilot = output / "windows-package-autopilot.FCMacro"
        summary["autopilot_transport"] = make_windows_autopilot(autopilot, profile, ifc_path)
        for mode, macro_name, report_name, gui_count, package_count in STAGES:
            checked_package(archive, case / "แตกไฟล์")
            if host_inventory(args.host, args.host_manifest) != expected:
                raise RuntimeError("Host files changed between modes")
            mode_output = output / mode
            mode_output.mkdir()
            macro = root / macro_name
            row = {"stage": mode, "status": "running", "expected_gui_checks": gui_count,
                   "expected_package_checks": package_count, "started_at_utc": stamp(), "files": {}}
            summary["stages"].append(row)
            write_json(summary_path, summary)
            stage_env = dict(env, BIM3117_PACKAGE_ROOT=str(root), BIM3117_PACKAGE_EVIDENCE=str(mode_output),
                             BIM3117_PACKAGE_STAGE=mode, BIM3117_PACKAGE_SHA256=FROZEN_ZIP_SHA256,
                             BIM3117_HOST_MANIFEST=str(expected_file), BIM3117_HOST_MANIFEST_SHA256=sha(expected_file),
                             BIM3117_PUBLIC_MACRO=str(macro))
            command = [str(args.host.resolve()), "--python-path", str(ifc_path), "-u", str(profile / "user.cfg"),
                       str(autopilot), str(macro)]
            process = run_process(command, stage_env, mode_output, mode_output / "gui.log", args.timeout)
            summary["host_executed"] = True
            process_path = mode_output / "process.json"
            write_json(process_path, process)
            report_path = mode_output / report_name
            report, report_error = read_json(report_path)
            inner_name = report_name.replace("-macro-report.json", "-gui-report.json")
            inner_path = mode_output / inner_name
            inner, inner_error = read_json(inner_path) if gui_count else ({}, None)
            start_path, end_path = (mode_output / ("package-" + mode + "-host-" + phase + ".json") for phase in ("start", "end"))
            start, start_error = read_json(start_path)
            end, end_error = read_json(end_path)
            valid, reasons = validate_stage(report, inner, process, gui_count, package_count)
            for error in (report_error, inner_error, start_error, end_error):
                if error:
                    reasons.append(error)
            for identity, completed in ((start, False), (end, True)):
                modules = ("Part",) if completed and mode != "install" else ()
                okay, detail = validate_identity(identity, expected, profile, gui=True, completed=completed,
                                                required_modules=modules, expected_pid=process.get("pid"))
                if identity.get("status") != "passed" or not okay:
                    reasons.extend(detail or ["Incomplete Windows host identity"])
            if mode != "install" and not validate_installed_modules(end, KIT / "inputs/3117-bim-studio"):
                reasons.append("Actual loaded modules differ from the installed frozen addon")
            if mode in IFC_MODES and not validate_ifc(end, summary["ifc_inventory"]):
                reasons.append("Actual IFC version/path/DLL differs from the isolated pinned runtime")
            items = {"process": process_path, "package": report_path, "host_start": start_path, "host_end": end_path,
                     "macro": macro, "log": mode_output / "gui.log"}
            if gui_count:
                items["inner"] = inner_path
            row["files"] = {name: evidence_file(path) for name, path in items.items() if path.is_file()}
            row.update(status="passed" if not reasons else "failed", reasons=reasons, pid=process.get("pid"),
                       gui_checks_passed=gui_count if not reasons else None, checks_passed=package_count if not reasons else None,
                       actual_user_data=report.get("actual_user_data"), finished_at_utc=stamp())
            write_json(summary_path, summary)
            print(json.dumps({"stage": mode, "status": row["status"], "reasons": reasons}, ensure_ascii=False), flush=True)
            if reasons:
                raise RuntimeError("Public mode failed: " + mode)
        summary.update(status="passed", windows_acceptance="public_gui_automation_passed", stages_passed=7,
                       public_gui_checks_passed=248, packaging_checks_passed=48, finished_at_utc=stamp())
        write_json(summary_path, summary)
        verified = verify_summary(summary_path, args.host_manifest)
        summary["verification"] = verified
        if verified["status"] != "passed":
            raise RuntimeError("Final raw public evidence verification failed: " + repr(verified["errors"]))
    except BaseException as error:
        summary.update(status="failed" if summary["host_executed"] or os.name == "nt" else "not_executed",
                       error=str(error), traceback=traceback.format_exc(), finished_at_utc=stamp())
    write_json(summary_path, summary)
    print(json.dumps({"status": summary["status"], "stages_passed": sum(row["status"] == "passed" for row in summary["stages"]),
                      "report": str(summary_path)}, ensure_ascii=False), flush=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
