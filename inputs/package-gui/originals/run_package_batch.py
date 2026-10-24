"""Run the installer and six unmodified public macros from one exact ZIP.

No source/package mutation is performed here. Each stage launches the existing
reviewed GUI runner sequentially, sharing only this ZIP's disposable profile.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback


STAGES = (
    ("install", "packaged-installer-gui-report.json", None),
    ("publicsmoke", "public-smoke-macro-report.json", 24),
    ("publicarchitecture", "public-architecture-macro-report.json", 43),
    ("publicmacro", "public-exchange-macro-report.json", 41),
    ("publicbuilding", "public-building-macro-report.json", 35),
    ("publicdrawings", "public-drawings-macro-report.json", 53),
    ("publictypes", "public-types-macro-report.json", 52),
)
TASK = Path("/tmp/bim3117-release-v050")
RUNNER = TASK / "run_package_check.py"
AUTOPILOT = TASK / "package_autopilot.FCMacro"
EVIDENCE = TASK / "evidence"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python run_package_batch.py /absolute/path/to/final-v050.zip")
    archive = Path(sys.argv[1]).resolve()
    if not archive.is_file() or archive.suffix.lower() != ".zip":
        raise SystemExit("Provide the finalized ZIP file before running the package batch")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    digest = sha(archive)
    script_hashes = {str(path): sha(path) for path in (RUNNER, AUTOPILOT, Path(__file__))}
    summary_path = EVIDENCE / "package-seven-modes-report.json"
    summary = {"status": "running", "archive": str(archive), "zip_sha256": digest,
               "started_utc": utc(), "qa_script_sha256": script_hashes, "stages": [],
               "scope": "Exact ZIP public installer plus six unchanged public GUI feature macros",
               "host_history_branch_gate": "failed_native_host", "overall_release_ready": False,
               "windows_acceptance": "pending",
               "host_gate_scope": "Known separate create/delete/two-Undo/new-edit/Undo/Redo crash on tested Linux FreeCAD 1.1.4; packaging and isolated feature passes do not resolve it."}

    def save():
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for mode, report_name, expected_gui_checks in STAGES:
            if sha(archive) != digest:
                raise RuntimeError("The ZIP changed between package stages")
            row = {"stage": mode, "status": "running", "started_utc": utc(),
                   "expected_gui_checks": expected_gui_checks}
            summary["stages"].append(row)
            save()
            print("PACKAGE_BATCH_START", mode, flush=True)
            output_log = EVIDENCE / ("batch-" + mode + ".log")
            with output_log.open("w", encoding="utf-8") as stream:
                result = subprocess.run([sys.executable, str(RUNNER), str(archive), mode],
                                        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
            report_path = EVIDENCE / report_name
            report = json.loads(report_path.read_text()) if report_path.exists() else {}
            row.update(exit_code=result.returncode, finished_utc=utc(), report=str(report_path),
                       log=str(output_log), checks_passed=report.get("checks_passed"),
                       gui_checks_passed=report.get("gui_checks_passed"),
                       actual_user_data=report.get("actual_user_data"),
                       example=report.get("example"), screenshot=report.get("screenshot"))
            passed = (result.returncode == 0 and report.get("status") == "passed"
                      and report.get("zip_sha256") == digest
                      and (expected_gui_checks is None or report.get("gui_checks_passed") == expected_gui_checks))
            row["status"] = "passed" if passed else "failed"
            save()
            print("PACKAGE_BATCH_RESULT", mode, row["status"], row["gui_checks_passed"], flush=True)
            if not passed:
                row["error"] = report.get("error") or "Package stage failed; inspect the stage/GUI logs"
                print(output_log.read_text(errors="replace")[-8000:], flush=True)
                raise RuntimeError(mode + ": " + row["error"])
        if sha(archive) != digest or any(sha(path) != value for path, value in script_hashes.items()):
            raise RuntimeError("The ZIP or QA scripts changed during the package batch")
        profiles = {row["actual_user_data"] for row in summary["stages"]}
        if len(profiles) != 1 or None in profiles:
            raise RuntimeError("The seven package stages did not share one isolated native user-data profile")
        summary.update(status="passed", finished_utc=utc(), stages_passed=len(STAGES),
                       public_gui_checks_passed=sum(row["gui_checks_passed"] or 0 for row in summary["stages"]),
                       packaging_checks_passed=sum(row["checks_passed"] or 0 for row in summary["stages"]),
                       final_zip_sha256=sha(archive), qa_scripts_unchanged=True,
                       actual_user_data=next(iter(profiles)))
    except BaseException as error:
        summary.update(status="failed", finished_utc=utc(), error=str(error), traceback=traceback.format_exc())
    finally:
        save()
    print(json.dumps({"status": summary["status"], "zip_sha256": digest,
                      "stages_passed": sum(row["status"] == "passed" for row in summary["stages"]),
                      "public_gui_checks_passed": summary.get("public_gui_checks_passed"),
                      "report": str(summary_path)}, ensure_ascii=False), flush=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
