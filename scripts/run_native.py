#!/usr/bin/env python3
"""Run all 19 frozen native stages in fresh real Windows FreeCADCmd processes."""
import argparse
import json
from pathlib import Path
import sys
import traceback
sys.dont_write_bytecode = True

from windows_common import (KIT, capture_host, file_record, host_inventory, ifc_inventory,
                            new_output, profile_env, read_json, require_windows, run_process,
                            sha, stamp, validate_checks, validate_identity, validate_ifc,
                            validate_installed_modules, verify_inputs, verify_recorded_file, write_json)

REPORTS = {
    "install": "install-report.json", "foundation": "foundation-test-report.json",
    "reopen": "reopen-test-report.json", "architecture": "architecture-test-report.json",
    "architecture_reopen": "architecture-reopen-test-report.json", "exchange": "exchange-test-report.json",
    "exchange_reopen": "exchange-reopen-test-report.json", "building": "building-test-report.json",
    "building_reopen": "building-reopen-test-report.json", "drawing_geometry": "drawing-geometry-test-report.json",
    "drawings": "drawings-test-report.json", "drawings_reopen": "drawings-reopen-test-report.json",
    "drawing_render": "drawing-render-test-report.json", "types": "types-test-report.json",
    "types_reopen": "types-reopen-test-report.json", "types_exchange": "types-exchange-test-report.json",
    "types_exchange_reopen": "types-exchange-reopen-test-report.json",
    "schedules": "schedules-test-report.json", "schedules_reopen": "schedules-reopen-test-report.json",
}
EXPECTED_CHECKS = dict(zip(REPORTS, (1, 35, 9, 63, 12, 47, 10, 112, 19, 31, 70, 25, 33, 54, 21, 37, 7, 49, 16)))
DRAWING_STAGES = {"drawing_geometry", "drawings", "drawings_reopen", "drawing_render"}
IFC_STAGES = {"exchange", "exchange_reopen", "building", "building_reopen", "types_exchange", "types_exchange_reopen"}


def make_entry(scripts, profile, output, test_file, ifc_path):
    text = f'''import sys, os, traceback
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, {str(scripts)!r})
from windows_common import capture_host, configure_ifc_path, write_json
configure_ifc_path({str(ifc_path)!r})
stage = os.environ["BIM3117_QA_STAGE"]
profile = Path({str(profile)!r})
output = Path({str(output)!r})
test_file = Path({str(test_file)!r})
sentinel = output / (stage + "-entry-started.txt")
with sentinel.open("x", encoding="utf-8") as stream:
    stream.write(str(os.getpid()))
completed = False
try:
    before = capture_host(profile, stage, False)
    write_json(output / (stage + "-host-before.json"), before)
    import FreeCAD as App
    assert profile.resolve() in Path(App.getUserAppDataDir()).resolve().parents, "Unexpected profile"
    assert not App.GuiUp, "Expected a headless native process"
    scope = dict(globals(), __file__=str(test_file), __name__="__main__")
    exec(compile(test_file.read_text(encoding="utf-8"), str(test_file), "exec"), scope, scope)
    completed = True
except BaseException:
    write_json(output / (stage + "-launcher-error.json"), {{"status": "failed", "traceback": traceback.format_exc()}})
    traceback.print_exc()
finally:
    write_json(output / (stage + "-host-after.json"), capture_host(profile, stage, completed))
'''
    compile(text, "native-entry.py", "exec")
    return text


def validate_stage(stage, process, report, before, after, expected_host, profile, expected_ifc, repository):
    required = [] if stage == "install" else ["Part"]
    if stage in DRAWING_STAGES:
        required.append("TechDraw")
    before_ok, before_errors = validate_identity(before, expected_host, profile, gui=False,
                                                 completed=False, expected_pid=process.get("pid"))
    after_ok, after_errors = validate_identity(after, expected_host, profile, gui=False, completed=True,
                                               required_modules=required, expected_pid=process.get("pid"))
    stages_match = before.get("stage") == stage == after.get("stage")
    ifc_required = stage in IFC_STAGES or "ifcopenshell" in after.get("module_files", {})
    ifc_ok = validate_ifc(after, expected_ifc) if ifc_required else None
    installed_ok = validate_installed_modules(after, repository) if stage != "install" else True
    checks_ok = validate_checks(report, EXPECTED_CHECKS[stage])
    process_ok = process.get("returncode") == 0 and not process.get("timed_out") and not process.get("launch_error")
    gate = process_ok and before_ok and after_ok and stages_match and checks_ok and installed_ok and ifc_ok is not False
    return {"stage": stage, "status": "passed" if gate else "failed", "gate_passed": bool(gate),
            "process": process, "pid": process.get("pid"), "exit_code": process.get("returncode"),
            "report_status": report.get("status"), "checks_passed": report.get("checks_passed"),
            "expected_checks": EXPECTED_CHECKS[stage], "check_count_verified": checks_ok,
            "before_identity_verified": before_ok, "after_identity_verified": after_ok,
            "identity_errors": before_errors + after_errors, "stage_identity_verified": stages_match,
            "installed_modules_verified": installed_ok, "ifc_identity_required": ifc_required,
            "isolated_ifc_identity_verified": ifc_ok, "error": report.get("error")}


def verify_summary(path, host_manifest=None, variant=None):
    """Re-read raw evidence and its hashes; never trust summary pass booleans."""
    summary, error = read_json(path)
    errors = [error] if error else []
    if summary.get("status") != "passed" or summary.get("platform") != "windows":
        errors.append("Native summary is not a Windows pass")
    if [item.get("stage") for item in summary.get("stages", [])] != list(REPORTS):
        errors.append("Native stage set/order differs from the frozen 19-stage gate")
    expected = summary.get("expected_host", {})
    if host_manifest:
        try:
            verified_host = host_inventory(expected["executable"]["path"], host_manifest)
            if expected != verified_host:
                errors.append("Host inventory does not match current build manifest and files")
            manifest, _ = read_json(host_manifest)
            if variant is not None and str(manifest.get("variant", "")).lower() != variant.lower():
                errors.append("Wrong build variant")
        except (OSError, ValueError, KeyError, RuntimeError) as failure:
            errors.append(str(failure))
    pids = []
    total = 0
    for item in summary.get("stages", []):
        stage = item.get("stage")
        if stage not in REPORTS:
            continue
        for key, hash_key in (("report", "report_sha256"), ("before_identity", "before_identity_sha256"),
                              ("after_identity", "after_identity_sha256")):
            if not verify_recorded_file(item.get(key, ""), item.get(hash_key)):
                errors.append(stage + ": missing/changed " + key)
        process = item.get("process", {})
        if not verify_recorded_file(process.get("log_path", ""), process.get("log_sha256")):
            errors.append(stage + ": missing/changed process log")
        report, _ = read_json(item.get("report", ""))
        before, _ = read_json(item.get("before_identity", ""))
        after, _ = read_json(item.get("after_identity", ""))
        try:
            checked = validate_stage(stage, process, report, before, after, expected,
                                     summary["profile"], summary["expected_ifc"], KIT / "inputs/3117-bim-studio")
            if not checked["gate_passed"]:
                errors.append(stage + ": raw evidence failed validation")
        except (ValueError, OSError, KeyError, TypeError) as failure:
            errors.append(stage + ": " + str(failure))
        if type(report.get("checks_passed")) is int:
            total += report["checks_passed"]
        pids.append(process.get("pid"))
    if total != 651 or summary.get("checks_passed") != 651:
        errors.append("Expected exactly 651 native checks")
    if len(pids) != 19 or any(type(pid) is not int or pid <= 0 for pid in pids) or len(set(pids)) != 19:
        errors.append("Expected 19 distinct native process IDs")
    if summary.get("source_unchanged_during_run") is not True or summary.get("frozen_inputs_before") != summary.get("frozen_inputs_after"):
        errors.append("Frozen input evidence mismatch")
    return {"valid": not errors, "errors": errors, "checks_passed": total, "processes": len(pids)}


def run(args):
    root = new_output(args.output)
    summary = {"schema": 1, "status": "not_executed", "platform": "windows", "system": "Windows",
               "scope": "19 native processes; desktop acceptance remains separate",
               "started_at_utc": stamp(), "stages": [], "checks_passed": 0,
               "expected_checks": 651, "expected_processes": 19, "release_ready": False}
    try:
        require_windows()
        summary["status"] = "running"
        summary["frozen_inputs_before"] = verify_inputs()
        host = host_inventory(args.host, args.host_manifest)
        expected_ifc = ifc_inventory(args.ifc_python_path)
        summary["expected_host"] = host
        summary["expected_ifc"] = expected_ifc
        summary["runner_sha256"] = sha(__file__)
        repository = KIT / "inputs" / "3117-bim-studio"
        profile = root / "โปรไฟล์3117"
        output = root / "output"
        output.mkdir()
        env = profile_env(profile, gui=False)
        env["BIM3117_QA_OUTPUT"] = str(output)
        entry = root / "native-entry.py"
        entry.write_text(make_entry(KIT / "scripts", profile, output, repository / "tests/run_freecad_tests.py", Path(args.ifc_python_path).resolve()),
                         encoding="utf-8")
        command = [str(Path(args.host).resolve()), "-u", str(profile / "home" / "user.cfg"),
                   "--python-path", str(Path(args.ifc_python_path).resolve()), str(entry)]
        summary.update(command=command, profile=str(profile), entry_sha256=sha(entry))
        write_json(root / "summary.json", summary)
        for stage, report_name in REPORTS.items():
            process = run_process(command, dict(env, BIM3117_QA_STAGE=stage), repository,
                                  output / (stage + "-host.log"), args.timeout)
            report_path = output / report_name
            before_path, after_path = output / (stage + "-host-before.json"), output / (stage + "-host-after.json")
            report, report_error = read_json(report_path)
            before, before_error = read_json(before_path)
            after, after_error = read_json(after_path)
            item = validate_stage(stage, process, report, before, after, host, profile, expected_ifc, repository)
            item.update(report=str(report_path), before_identity=str(before_path), after_identity=str(after_path),
                        report_sha256=sha(report_path) if report_path.is_file() else None,
                        before_identity_sha256=sha(before_path) if before_path.is_file() else None,
                        after_identity_sha256=sha(after_path) if after_path.is_file() else None,
                        report_read_error=report_error, before_read_error=before_error, after_read_error=after_error)
            launcher_error = output / (stage + "-launcher-error.json")
            if launcher_error.exists():
                item.update(status="failed", gate_passed=False, launcher_error=str(launcher_error))
            summary["stages"].append(item)
            summary["checks_passed"] = sum(x["checks_passed"] for x in summary["stages"]
                                           if type(x.get("checks_passed")) is int)
            write_json(root / "summary.json", summary)
            print(json.dumps(item, ensure_ascii=False), flush=True)
            if not item["gate_passed"]:
                break
        summary["frozen_inputs_after"] = verify_inputs()
        summary["source_unchanged_during_run"] = summary["frozen_inputs_before"] == summary["frozen_inputs_after"]
        pids = [item["pid"] for item in summary["stages"]]
        summary["distinct_process_ids"] = all(type(pid) is int and pid > 0 for pid in pids) and len(set(pids)) == len(pids)
        summary["status"] = "passed" if (len(summary["stages"]) == 19 and summary["checks_passed"] == 651
                         and summary["source_unchanged_during_run"] and summary["distinct_process_ids"]
                         and all(item["gate_passed"] for item in summary["stages"])) else "failed"
    except BaseException as error:
        if summary["status"] != "not_executed":
            summary["status"] = "failed"
        summary.update(error=str(error), traceback=traceback.format_exc())
    finally:
        summary["finished_at_utc"] = stamp()
        write_json(root / "summary.json", summary)
        write_json(root / "native-summary.json", summary)
        if (root / "output").exists():
            write_json(root / "output" / "native-process-manifest.json", summary)
    print(json.dumps({"status": summary["status"], "summary": str(root / "summary.json")}), flush=True)
    return 0 if summary["status"] == "passed" else 2 if summary["status"] == "not_executed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--host-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ifc-python-path", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
