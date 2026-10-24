#!/usr/bin/env python3
"""Run the unchanged archived crash/history cases in isolated Windows GUI hosts.

The frozen Linux harness's macro bodies are reused with a Windows-only outer
header. No native document operation, timing, Undo/Redo call or assertion is
replaced. Unpatched Windows outcomes are observations, not assumed Linux results.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import traceback
sys.dont_write_bytecode = True

from windows_common import (KIT, host_inventory, new_output, profile_env, read_json, require_windows,
                            run_process, sha, stamp, validate_checks, validate_identity, validate_installed_modules,
                            verify_inputs, verify_recorded_file, write_json)

REGRESSION = KIT / "inputs" / "regression"
REPOSITORY = KIT / "inputs" / "3117-bim-studio"
CASES = ("minimal-native", "timed-native", "timed-non-python", "unbranched-control", "history-invariants", "original-3117-ui")
COUNTS = {"history-invariants": 127, "history-reopen": 13, "original-3117-ui": 27}


def archived_harness():
    spec = importlib.util.spec_from_file_location("frozen_linux_regression_body", REGRESSION / "run_regressions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.verify_originals()
    return module


def macro_header(profile, output, stage, ifc_path=None):
    ifc_setup = ("configure_ifc_path(" + repr(str(ifc_path)) + ")\n") if ifc_path else ""
    text = f'''import sys, json, traceback
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
sys.dont_write_bytecode = True
sys.path.insert(0, {str(KIT / 'scripts')!r})
from windows_common import capture_host, configure_ifc_path, write_json
{ifc_setup}output = Path({str(output)!r})
profile = Path({str(profile)!r})
stage = {stage!r}
_entry_started = False
def record_host():
    global _entry_started
    if _entry_started:
        raise RuntimeError("The frozen entry was invoked more than once")
    _entry_started = True
    user_data = Path(App.getUserAppDataDir()).resolve()
    assert profile.resolve() in user_data.parents, ("Unexpected profile", str(user_data))
    write_json(output / "host-before.json", capture_host(profile, stage, False))
def _record_after():
    try:
        write_json(output / "host-after.json", capture_host(profile, stage, _entry_started))
    except BaseException:
        write_json(output / "identity-error.json", {{"status": "failed", "traceback": traceback.format_exc()}})
def launcher_error():
    write_json(output / "launcher-error.json", {{"status": "failed", "traceback": traceback.format_exc()}})
    traceback.print_exc()
    QtCore.QTimer.singleShot(150, QtWidgets.QApplication.quit)
QtWidgets.QApplication.instance().aboutToQuit.connect(_record_after)
'''
    compile(text, "windows-header.FCMacro", "exec")
    return text


def make_macro(case, profile, output, *, install=False, source_output=None, ifc_path=None):
    original = archived_harness()
    stage = case + "-install" if install else case
    original.macro_header = lambda p, o: macro_header(p, o, stage, ifc_path)
    return original.write_macro(case, profile, output, REPOSITORY, install=install, source_output=source_output)


def validate_case_report(case, report):
    if case.endswith("-install"):
        return report.get("status") == "passed" and isinstance(report.get("installation"), dict)
    if case in COUNTS:
        return validate_checks(report, COUNTS[case])
    if report.get("status") != "passed":
        return False
    if case in ("timed-native", "timed-non-python"):
        actions = ("baseline target", "create disposable", "delete disposable", "Undo deletion", "Undo creation",
                   "new Label edit branch", "Undo label edit", "Redo label edit")
        expected = [edge + action for action in actions for edge in ("before ", "after ")] + ["all passed"]
        variant = "feature" if case == "timed-non-python" else "yield"
        return report.get("steps") == expected and report.get("variant") == variant
    baseline = ["baseline target", "created disposable feature", "deleted disposable feature", "Undo deletion", "Undo creation"]
    tail = (["Redo creation", "Redo deletion", "all passed"] if case == "unbranched-control" else
            ["branched label edit", "Undo label edit", "Redo label edit", "all passed"])
    return report.get("steps") == baseline + tail and report.get("addon_imported") is False


def classify_outcome(case, process, report, before, after, expected_host, profile, *, launcher_error=False):
    before_ok, before_errors = validate_identity(before, expected_host, profile, gui=True, completed=False,
                                                expected_pid=process.get("pid"))
    if not case.startswith("original-3117-ui") and (before.get("addon_modules_at_entry") or before.get("addon_directories")):
        before_ok = False
        before_errors.append("No-addon regression loaded a workbench installation")
    required = ("Part",) if case in ("history-invariants", "history-reopen", "original-3117-ui", "timed-non-python") else ()
    after_ok, after_errors = validate_identity(after, expected_host, profile, gui=True, completed=True,
                                              required_modules=required, expected_pid=process.get("pid"))
    stage_ok = before.get("stage") == case and (not after or after.get("stage") == case)
    check_ok = validate_case_report(case, report)
    installed_ok = validate_installed_modules(after, REPOSITORY) if case == "original-3117-ui" and after else None
    code = process.get("returncode")
    native_exception = type(code) is int and (code & 0xffffffff) in {0xc0000005, 0xc00000fd, 0xc0000409}
    status = "failed"
    if process.get("launch_error"):
        status = "launch_error"
    elif process.get("timed_out"):
        status = "timed_out"
    elif launcher_error:
        status = "failed_launcher"
    elif not before_ok or not stage_ok:
        status = "failed_host_identity"
    elif code == 0 and check_ok and after_ok and installed_ok is not False:
        status = "passed"
    elif native_exception and report.get("status") in (None, "running"):
        status = "native_crash_observed"
    elif code != 0:
        status = "failed_process"
    elif not after_ok:
        status = "failed_host_identity"
    elif not report:
        status = "missing_completed_report"
    else:
        status = "failed_assertion"
    return {"status": status, "gate_passed": status == "passed", "pid": process.get("pid"),
            "exit_code": code, "process": process, "checks_passed": report.get("checks_passed"),
            "expected_checks": COUNTS.get(case), "check_count_verified": check_ok,
            "raw_report_status": report.get("status"), "last_steps": report.get("steps", [])[-5:],
            "before_identity_verified": before_ok, "after_identity_verified": after_ok,
            "installed_modules_verified": installed_ok,
            "identity_errors": before_errors + after_errors, "stage_identity_verified": stage_ok,
            "native_exception_exit": native_exception, "launcher_error_present": bool(launcher_error),
            "specific_crash_location_confirmed": False,
            "baseline_observation_complete": status in ("passed", "native_crash_observed")}


def verify_summary(path, host_manifest=None, variant=None):
    """Validate recorded raw case reports, process logs and loaded DLL evidence."""
    summary, error = read_json(path)
    errors = [error] if error else []
    baseline = (variant or summary.get("tag", "")).lower() == "unpatched"
    if summary.get("platform") != "windows" or summary.get("status") not in ("passed", "failed"):
        errors.append("No completed Windows regression run")
    if not baseline and summary.get("status") != "passed":
        errors.append("Patched regression run did not pass")
    cases = summary.get("cases", {})
    if not isinstance(cases, dict) or set(cases) != set(CASES):
        return {"valid": False, "errors": errors + ["Missing/extra regression cases"], "cases": 0}
    expected = summary.get("expected_host", {})
    if host_manifest:
        try:
            if host_inventory(expected["executable"]["path"], host_manifest) != expected:
                errors.append("Host inventory does not match its build manifest and files")
            manifest, _ = read_json(host_manifest)
            if variant and str(manifest.get("variant", "")).lower() != variant.lower():
                errors.append("Wrong build variant")
        except (OSError, ValueError, RuntimeError, KeyError) as failure:
            errors.append(str(failure))
    pids = []
    observed = []
    def inspect(case, item, can_crash=False):
        if not isinstance(item, dict):
            errors.append(case + ": missing result")
            return
        try:
            process = item.get("process", {})
            report, _ = read_json(item.get("raw_report", ""))
            before, _ = read_json(item.get("before_identity", ""))
            after, _ = read_json(item.get("after_identity", ""))
            checked = classify_outcome(case, process, report, before, after, expected, item["profile"],
                                        launcher_error=item.get("launcher_error_present") is not False)
            accepted = checked["status"] == "passed" or can_crash and checked["status"] == "native_crash_observed"
            if not accepted:
                errors.append(case + ": raw evidence result " + checked["status"])
            if checked["status"] == "native_crash_observed":
                observed.append(case)
            for key, hash_key in (("before_identity", "before_identity_sha256"), ("macro", "macro_sha256")):
                if not verify_recorded_file(item.get(key, ""), item.get(hash_key)):
                    errors.append(case + ": missing/changed " + key)
            for key, hash_key in (("raw_report", "raw_report_sha256"), ("after_identity", "after_identity_sha256")):
                if checked["status"] == "passed" or item.get(hash_key) is not None:
                    if not verify_recorded_file(item.get(key, ""), item.get(hash_key)):
                        errors.append(case + ": missing/changed " + key)
            if not verify_recorded_file(process.get("log_path", ""), process.get("log_sha256")):
                errors.append(case + ": missing/changed process log")
            pids.append(process.get("pid"))
        except (OSError, ValueError, KeyError, TypeError) as failure:
            errors.append(case + ": " + str(failure))
    for case in CASES:
        item = cases[case]
        inspect(case, item, can_crash=baseline and case != "unbranched-control")
        if case == "original-3117-ui":
            inspect(case + "-install", item.get("installation"))
        if case == "history-invariants" and item.get("status") == "passed":
            inspect("history-reopen", item.get("fresh_process_reopen"))
        elif case == "history-invariants" and not baseline:
            errors.append("Fresh-process history reopen did not complete")
    if any(type(pid) is not int or pid <= 0 for pid in pids) or len(set(pids)) != len(pids):
        errors.append("Regression process IDs are missing or reused")
    if summary.get("source_unchanged_during_run") is not True or summary.get("frozen_inputs_before") != summary.get("frozen_inputs_after"):
        errors.append("Frozen input evidence mismatch")
    return {"valid": not errors, "errors": errors, "cases": len(cases), "processes": len(pids),
            "observed_native_crashes": observed, "baseline": baseline}


def launch(case, host, expected_host, macro, profile, output, env, report_name, timeout, ifc_path=None):
    command = [str(host), "-u", str(profile / "home" / "user.cfg")]
    if ifc_path:
        command += ["--python-path", str(ifc_path)]
    command.append(str(macro))
    process = run_process(command, env, output, output / "gui.log", timeout)
    report_path, before_path, after_path = output / report_name, output / "host-before.json", output / "host-after.json"
    report, report_error = read_json(report_path)
    before, before_error = read_json(before_path)
    after, after_error = read_json(after_path)
    result = classify_outcome(case, process, report, before, after, expected_host, profile,
                              launcher_error=(output / "launcher-error.json").exists() or (output / "identity-error.json").exists())
    result.update(raw_report=str(report_path), before_identity=str(before_path), after_identity=str(after_path),
                  raw_report_sha256=sha(report_path) if report_path.is_file() else None,
                  before_identity_sha256=sha(before_path) if before_path.is_file() else None,
                  after_identity_sha256=sha(after_path) if after_path.is_file() else None,
                  macro=str(macro), macro_sha256=sha(macro), profile=str(profile),
                  report_read_error=report_error, before_read_error=before_error, after_read_error=after_error)
    write_json(output / "external-outcome.json", result)
    return result


def run(args):
    root = new_output(args.output)
    summary = {"schema": 1, "status": "not_executed", "platform": "windows", "system": "Windows",
               "tag": args.tag, "started_at_utc": stamp(), "cases": {}, "release_ready": False,
               "expected_cases": list(CASES), "original_test_changes": False,
               "outer_changes": ["Windows profile paths", "Windows in-process DLL and desktop attestation",
                                 "outer process deadlines and exact count validation"]}
    try:
        require_windows()
        summary["status"] = "running"
        summary["frozen_inputs_before"] = verify_inputs()
        expected_host = host_inventory(args.host, args.host_manifest)
        host = Path(args.host).resolve()
        ifc_path = Path(args.ifc_python_path).resolve() if args.ifc_python_path else None
        summary.update(expected_host=expected_host, originals=archived_harness().verify_originals(),
                       frozen_harness_sha256=sha(REGRESSION / "run_regressions.py"), runner_sha256=sha(__file__))
        selected = args.case or list(CASES)
        write_json(root / "summary.json", summary)
        for case in selected:
            case_root = root / case
            output, profile = case_root / "evidence", case_root / "โปรไฟล์3117"
            output.mkdir(parents=True)
            env = profile_env(profile, gui=True)
            installation = None
            if case == "original-3117-ui":
                installation_output = case_root / "installation"
                installation_output.mkdir()
                macro = make_macro(case, profile, installation_output, install=True, ifc_path=ifc_path)
                installation = launch(case + "-install", host, expected_host, macro, profile, installation_output,
                                      env, "install-report.json", args.ui_timeout, ifc_path)
                if installation["status"] != "passed":
                    summary["cases"][case] = {"status": "blocked_by_installation", "gate_passed": False,
                                               "baseline_observation_complete": False, "installation": installation}
                    write_json(root / "summary.json", summary)
                    continue
                fixture = output / "Types_Quantities_Workbench.FCStd"
                shutil.copy2(REGRESSION / "fixture/Types_Quantities_Workbench.FCStd", fixture)
                fixture_report, error = read_json(REGRESSION / "fixture/fixture-types-gui-report.json")
                if error:
                    raise RuntimeError(error)
                old_sample = fixture_report["sample"]
                fixture_report["sample"] = str(fixture)
                write_json(output / "types-gui-report.json", fixture_report)
                write_json(output / "fixture-provenance.json", {
                    "only_report_field_changed": "sample", "sample_original_path": old_sample,
                    "sample_sha256": sha(fixture), "native_fixture_bytes_unchanged": True,
                    "original_json_sha256": sha(REGRESSION / "fixture/fixture-types-gui-report.json"),
                    "adjusted_json_sha256": sha(output / "types-gui-report.json")})
            report_name = "types-gui-reopen-report.json" if case == "original-3117-ui" else "report.json"
            macro = make_macro(case, profile, output, ifc_path=ifc_path if case == "original-3117-ui" else None)
            result = launch(case, host, expected_host, macro, profile, output, env, report_name,
                            args.ui_timeout if case == "original-3117-ui" else args.timeout,
                            ifc_path if case == "original-3117-ui" else None)
            if installation:
                result["installation"] = installation
            if case == "history-invariants" and result["status"] == "passed":
                reopen_output = case_root / "reopen-evidence"
                reopen_output.mkdir()
                macro = make_macro("history-reopen", profile, reopen_output, source_output=output)
                reopened = launch("history-reopen", host, expected_host, macro, profile, reopen_output,
                                  env, "report.json", args.timeout)
                result["fresh_process_reopen"] = reopened
                if reopened["status"] != "passed":
                    result.update(status="failed_fresh_process_reopen", gate_passed=False, baseline_observation_complete=False)
            summary["cases"][case] = result
            print(json.dumps({"case": case, "status": result["status"], "exit_code": result["exit_code"]}), flush=True)
            write_json(root / "summary.json", summary)
        summary["frozen_inputs_after"] = verify_inputs()
        summary["source_unchanged_during_run"] = summary["frozen_inputs_before"] == summary["frozen_inputs_after"]
        pids = []
        for result in summary["cases"].values():
            if result.get("pid"):
                pids.append(result["pid"])
            for child in ("installation", "fresh_process_reopen"):
                if result.get(child, {}).get("pid"):
                    pids.append(result[child]["pid"])
        summary["distinct_process_ids"] = len(pids) == len(set(pids))
        all_cases = set(summary["cases"]) == set(CASES)
        summary["complete_case_set"] = all_cases
        summary["baseline_observations_complete"] = (all_cases and summary["source_unchanged_during_run"]
                 and summary["distinct_process_ids"] and summary["cases"]["unbranched-control"]["status"] == "passed"
                 and all(item.get("baseline_observation_complete") for item in summary["cases"].values()))
        summary["status"] = "passed" if (all_cases and summary["source_unchanged_during_run"] and summary["distinct_process_ids"]
                         and all(item["status"] == "passed" for item in summary["cases"].values())) else "failed"
        summary["observed_native_crashes"] = [case for case, item in summary["cases"].items()
                                              if item["status"] == "native_crash_observed"]
    except BaseException as error:
        if summary["status"] != "not_executed":
            summary["status"] = "failed"
        summary.update(error=str(error), traceback=traceback.format_exc())
    finally:
        summary["finished_at_utc"] = stamp()
        write_json(root / "summary.json", summary)
        write_json(root / "regression-summary.json", summary)
    print(json.dumps({"status": summary["status"], "summary": str(root / "summary.json")}), flush=True)
    return 0 if summary["status"] == "passed" else 2 if summary["status"] == "not_executed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--host-manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--ifc-python-path", type=Path)
    parser.add_argument("--case", action="append", choices=CASES)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--ui-timeout", type=int, default=900)
    args = parser.parse_args()
    if args.timeout <= 0 or args.ui_timeout <= 0:
        parser.error("Timeouts must be positive")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
