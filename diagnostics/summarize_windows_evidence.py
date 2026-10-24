#!/usr/bin/env python3
"""Read-only triage of Windows acceptance evidence. Never grants acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STAGES = ("regression-unpatched", "regression-patched", "native-patched", "public-gui-patched")
MAX_FAILURES = 100
MAX_LOG_LINES = 25


def load(path: Path):
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(result, dict):
            return {"status": "unreadable", "error": "JSON root must be an object"}
        return result
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {"status": "unreadable", "error": str(error)}


def failed_items(value, *, prefix=""):
    """Collect only explicit failures; avoid interpreting missing evidence as success."""
    out = []
    def visit(node, location, depth=0):
        if len(out) >= MAX_FAILURES or depth > 8:
            return
        if isinstance(node, dict):
            status = node.get("status")
            if status in ("failed", "blocked", "error", "unreadable"):
                out.append({"location": location, "status": status,
                            "errors": node.get("errors", node.get("error"))})
            for key, child in node.items():
                if isinstance(child, (dict, list)):
                    visit(child, location + "/" + str(key), depth + 1)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{location}/{index}", depth + 1)
    visit(value, prefix or "root")
    return out


def log_tail(path: Path):
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        lines = stream.readlines()
    return [line.rstrip("\r\n") for line in lines[-MAX_LOG_LINES:]]


def summarize(root: Path):
    report = load(root / "WINDOWS_ACCEPTANCE.json")
    run = load(root / "run.json")
    result = {
        "evidence_root": str(root),
        "release_ready": False,
        "windows_automated_acceptance_passed": False,
        "gates": {}, "steps": [], "stage_reports": {}, "missing": [],
    }
    if report is None:
        result["missing"].append("WINDOWS_ACCEPTANCE.json")
    else:
        result["reported_status"] = report.get("status")
        result["gates"] = {
            name: {"status": value.get("status"), "errors": value.get("errors", [])}
            for name, value in report.get("gates", {}).items()
            if isinstance(value, dict) and value.get("status") != "passed"
        }
    if run is None:
        result["missing"].append("run.json")
    else:
        for step in run.get("steps", []):
            if not isinstance(step, dict) or step.get("status") == "passed":
                continue
            selected = {key: step.get(key) for key in
                        ("name", "status", "exit_code", "timed_out", "error")}
            name = step.get("name")
            if isinstance(name, str) and name and "/" not in name and "\\" not in name:
                tail = log_tail(root / "controller-logs" / (name + ".log"))
                if tail is not None:
                    selected["log_tail"] = tail
            result["steps"].append(selected)
    for stage in STAGES:
        relative = Path("results") / stage / "summary.json"
        value = load(root / relative)
        if value is None:
            result["missing"].append(relative.as_posix())
        else:
            result["stage_reports"][stage] = {
                "status": value.get("status"),
                "errors": value.get("errors", value.get("error", [])),
                "checks_passed": value.get("checks_passed"),
                "gui_checks_passed": value.get("gui_checks_passed"),
                "packaging_checks_passed": value.get("packaging_checks_passed"),
                "explicit_failures": failed_items(value, prefix=stage),
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path)
    args = parser.parse_args()
    root = args.evidence_root.resolve()
    if not root.is_dir():
        parser.error(f"evidence directory not found: {root}")
    print(json.dumps(summarize(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
