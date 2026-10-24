#!/usr/bin/env python3
"""Summarize existing Windows acceptance evidence; never turn failures into passes."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

STAGES = ("regression-unpatched", "regression-patched", "native-patched", "public-gui-patched")

def load(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"status": "unreadable", "error": str(exc)}

def summarize(root: Path):
    report = load(root / "WINDOWS_ACCEPTANCE.json")
    run = load(root / "run.json")
    output = {"evidence_root": str(root), "release_ready": False,
              "windows_automated_acceptance_passed": False, "gates": {}, "steps": [],
              "stage_reports": {}, "missing": []}
    if report is None:
        output["missing"].append("WINDOWS_ACCEPTANCE.json")
    else:
        output["reported_status"] = report.get("status")
        output["gates"] = {name: {"status": value.get("status"),
                                  "errors": value.get("errors", [])}
                           for name, value in report.get("gates", {}).items()
                           if value.get("status") != "passed"}
    if run is None:
        output["missing"].append("run.json")
    else:
        for step in run.get("steps", []):
            if step.get("status") != "passed":
                output["steps"].append({key: step.get(key) for key in
                                        ("name", "status", "exit_code", "timed_out", "error", "log")})
    for stage in STAGES:
        stage_path = root / "results" / stage / "summary.json"
        value = load(stage_path)
        if value is None:
            output["missing"].append(str(stage_path.relative_to(root)))
        else:
            output["stage_reports"][stage] = {
                "status": value.get("status"), "errors": value.get("errors", []),
                "checks_passed": value.get("checks_passed"),
                "gui_checks_passed": value.get("gui_checks_passed"),
                "packaging_checks_passed": value.get("packaging_checks_passed"),
            }
    return output

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("evidence_root", type=Path, help="Directory containing WINDOWS_ACCEPTANCE.json or run.json")
    args = p.parse_args()
    root = args.evidence_root.resolve()
    if not root.is_dir():
        p.error(f"evidence directory not found: {root}")
    print(json.dumps(summarize(root), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
