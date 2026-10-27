#!/usr/bin/env python3
"""Fail-closed evidence qualification of a real Windows graphics runner.

This is NOT FreeCAD GUI testing and can never grant Windows acceptance.
A hardware-capability check is necessary but not sufficient for Qt/Coin tests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

BAD_RENDERERS = (
    "gdi generic", "microsoft basic render", "llvmpipe",
    "softpipe", "swiftshader", "software rasterizer",
)
EXPECTED_RUN_FIELDS = (
    ("run_id", "run_id"),
    ("run_attempt", "run_attempt"),
    ("commit", "sha"),
    ("repository", "repository"),
)


def _positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def _version(value: object) -> tuple[int, int] | None:
    match = re.match(r"^\s*(\d+)\.(\d+)(?:\D|$)", value) if isinstance(value, str) else None
    return (int(match.group(1)), int(match.group(2))) if match else None


def qualify(
    preflight: object,
    opengl: object,
    *,
    expected_run_id: str | None = None,
    expected_run_attempt: str | None = None,
    expected_sha: str | None = None,
    expected_repository: str | None = None,
) -> dict:
    """Evaluate measurements, not assertions from unit tests or an exit code."""
    problems: list[str] = []
    if not isinstance(preflight, dict):
        preflight, problems = {}, ["runner_preflight_missing_or_invalid"]
    if not isinstance(opengl, dict):
        opengl = {}
        problems.append("opengl_probe_missing_or_invalid")

    if preflight.get("kind") != "runner_preparation":
        problems.append("runner_preflight_wrong_kind")
    if preflight.get("status") != "capacity_prepared_not_acceptance":
        problems.append("runner_capacity_not_prepared")
    if "windows" not in str(preflight.get("operating_system") or "").lower():
        problems.append("runner_not_native_windows")
    if not isinstance(preflight.get("selected_work_root"), str) or not preflight["selected_work_root"].strip():
        problems.append("runner_no_selected_build_root")
    probes = preflight.get("write_probes")
    if not isinstance(probes, list) or not any(
        isinstance(item, dict) and item.get("writable") is True for item in probes
    ):
        problems.append("runner_no_successful_write_probe")

    expectation = {
        "run_id": expected_run_id,
        "run_attempt": expected_run_attempt,
        "sha": expected_sha,
        "repository": expected_repository,
    }
    for field, arg_name in EXPECTED_RUN_FIELDS:
        expected = expectation[arg_name]
        if expected is not None and str(preflight.get(field) or "") != str(expected):
            problems.append(f"runner_{field}_provenance_mismatch")

    observation = preflight.get("desktop_observation")
    if not isinstance(observation, dict):
        problems.append("desktop_observation_missing")
        observation = {}
    if observation.get("user_interactive") is not True:
        problems.append("desktop_not_user_interactive")
    if observation.get("window_station_visible") is not True:
        problems.append("desktop_window_station_not_visible")
    if not _positive_integer(observation.get("session_id")):
        problems.append("desktop_no_nonzero_session")
    if not _positive_integer(observation.get("monitor_count")):
        problems.append("desktop_no_monitor")
    virtual = observation.get("virtual_screen")
    if not isinstance(virtual, dict) or not (
        _positive_integer(virtual.get("width")) and _positive_integer(virtual.get("height"))
    ):
        problems.append("desktop_invalid_virtual_screen")
    if observation.get("errors") != []:
        problems.append("desktop_winapi_errors_or_missing_record")

    if opengl.get("kind") != "windows_opengl_capability_probe" or opengl.get("system") != "Windows":
        problems.append("opengl_not_native_windows_probe")
    if opengl.get("status") != "compatible_for_further_gui_testing":
        problems.append("opengl_probe_not_compatible")
    parsed = _version(opengl.get("version"))
    if parsed is None or parsed < (2, 0):
        problems.append("opengl_below_2_0_or_unknown")
    vendor = opengl.get("vendor")
    renderer = opengl.get("renderer")
    if not isinstance(vendor, str) or not vendor.strip():
        problems.append("opengl_vendor_missing")
    if not isinstance(renderer, str) or not renderer.strip():
        problems.append("opengl_renderer_missing")
    elif any(term in renderer.lower() for term in BAD_RENDERERS):
        problems.append("opengl_known_software_fallback")
    if opengl.get("windows_gui_acceptance") != "not_executed":
        problems.append("opengl_probe_wrong_evidence_kind")

    return {
        "schema": 1,
        "kind": "windows_desktop_gpu_runner_qualification",
        "status": "eligible_for_gui_test_attempt" if not problems else "blocked",
        "reason_codes": problems,
        "evidence": {
            "runner_preflight_kind": preflight.get("kind"),
            "runner_run_id": preflight.get("run_id"),
            "runner_run_attempt": preflight.get("run_attempt"),
            "runner_commit": preflight.get("commit"),
            "desktop_session_id": observation.get("session_id"),
            "desktop_user_interactive": observation.get("user_interactive"),
            "desktop_window_station_visible": observation.get("window_station_visible"),
            "desktop_monitor_count": observation.get("monitor_count"),
            "opengl_version": opengl.get("version"),
            "opengl_vendor": vendor,
            "opengl_renderer": renderer,
        },
        "freecad_launch_test_executed": False,
        "qt_coin_gui_tests_executed": False,
        "windows_automated_acceptance_passed": False,
        "release_ready": False,
        "note": "Qualifies a runner for an attempt only. No FreeCAD acceptance is certified.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-preflight", type=Path, required=True)
    parser.add_argument("--opengl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-run-id")
    parser.add_argument("--expected-run-attempt")
    parser.add_argument("--expected-sha")
    parser.add_argument("--expected-repository")
    parser.add_argument("--require-qualified", action="store_true")
    args = parser.parse_args()
    try:
        p = json.loads(args.runner_preflight.read_text(encoding="utf-8-sig"))
        g = json.loads(args.opengl.read_text(encoding="utf-8-sig"))
        report = qualify(p, g, expected_run_id=args.expected_run_id,
                         expected_run_attempt=args.expected_run_attempt,
                         expected_sha=args.expected_sha,
                         expected_repository=args.expected_repository)
    except (OSError, ValueError, UnicodeError, TypeError) as error:
        report = {
            "schema": 1,
            "kind": "windows_desktop_gpu_runner_qualification",
            "status": "blocked",
            "reason_codes": ["evidence_unreadable: " + str(error)],
            "freecad_launch_test_executed": False,
            "qt_coin_gui_tests_executed": False,
            "windows_automated_acceptance_passed": False,
            "release_ready": False,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 2 if args.require_qualified and report["status"] != "eligible_for_gui_test_attempt" else 0


if __name__ == "__main__":
    sys.exit(main())
