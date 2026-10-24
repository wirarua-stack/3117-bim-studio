#!/usr/bin/env python3
"""Build both Windows hosts and run the frozen 3117 acceptance suites.

This controller does not emulate Windows and never promotes an offline check
to a host result. Each run gets a new output tree. Nothing is published.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

KIT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "4fd3bf320d9566a27e60069fc8387448aaa3a094"
PACKAGE_SHA256 = "ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_inputs(kit: Path = KIT) -> dict:
    manifest_path = kit / "inputs.lock.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    records = manifest.get("files", [])
    if not records:
        errors.append("empty frozen input manifest")
    seen = set()
    for record in records:
        relative = record.get("path", "")
        path = (kit / relative).resolve()
        if not path.is_relative_to((kit / "inputs").resolve()) or relative in seen:
            errors.append("invalid/duplicate input path: " + relative)
            continue
        seen.add(relative)
        if not path.is_file():
            errors.append("missing input: " + relative)
        elif path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            errors.append("changed input: " + relative)
    actual = {p.relative_to(kit).as_posix() for p in (kit / "inputs").rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    unexpected = sorted(actual - seen)
    if unexpected:
        errors.append("unlisted inputs: " + ", ".join(unexpected))
    package = kit / "inputs" / "3117_BIM_Studio_v0_5_0_FreeCAD.zip"
    if not package.is_file() or sha256(package) != PACKAGE_SHA256:
        errors.append("public workbench ZIP differs from frozen v0.5.0")
    return {"status": "passed" if not errors else "failed", "files_checked": len(records),
            "manifest_sha256": sha256(manifest_path), "errors": errors,
            "public_zip_sha256": PACKAGE_SHA256}


def preflight() -> dict:
    return {"schema": 1, "created_at": now(), "kind": "preparation_check",
            "system": platform.system(), "platform": platform.platform(),
            "python": sys.version, "source_commit": SOURCE_COMMIT,
            "frozen_inputs": verify_inputs(),
            "windows_execution": "not_executed", "release_ready": False,
            "note": "Input checks are independent of native Windows build and execution."}


def executable(manifest: dict, name: str) -> Path:
    value = manifest["executables"][name]
    path = Path(value["path"] if isinstance(value, dict) else value)
    if not path.is_file():
        raise RuntimeError("Build did not produce executable: " + str(path))
    if isinstance(value, dict) and value.get("sha256") != sha256(path):
        raise RuntimeError("Build executable hash changed: " + str(path))
    return path


def run_step(journal: dict, root: Path, name: str, argv: list[str], timeout: int) -> int:
    log = root / "controller-logs" / (name + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    record = {"name": name, "argv": argv, "started_at": now(), "status": "running",
              "log": str(log), "timeout_seconds": timeout}
    journal["steps"].append(record)
    write_json(root / "run.json", journal)
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    started = time.monotonic()
    print(f"[{now()}] {name}", flush=True)
    process = None
    try:
        with log.open("wb") as stream:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, env=environment, cwd=KIT)
            record["pid"] = process.pid
            write_json(root / "run.json", journal)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Kill only the tree owned by this controller invocation.
                record["timed_out"] = True
                record["tree_cleanup_confirmed"] = False
                try:
                    killer = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
                    cleanup = subprocess.run([str(killer), "/PID", str(process.pid), "/T", "/F"],
                                             stdout=stream, stderr=subprocess.STDOUT, check=False, timeout=30)
                    record["cleanup_exit_code"] = cleanup.returncode
                    record["tree_cleanup_confirmed"] = cleanup.returncode == 0
                except (OSError, KeyError, subprocess.SubprocessError) as error:
                    record["cleanup_error"] = str(error)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=30)
                code = 124
        record["exit_code"] = code
        record["status"] = "passed" if code == 0 else "failed"
    except (OSError, subprocess.SubprocessError) as error:
        record["error"] = str(error)
        record["exit_code"] = code = 125
        record["status"] = "failed"
    finally:
        record["ended_at"] = now()
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if log.exists():
            record["log_sha256"] = sha256(log)
        write_json(root / "run.json", journal)
    print(f"{name}: exit {code}; log: {log}", flush=True)
    return code


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--work-root", type=Path, required=True,
                        help="A new isolated local directory. Existing runs are never reused.")
    result.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    result.add_argument("--powershell", default="pwsh")
    result.add_argument("--preflight-only", action="store_true",
                        help="Check frozen inputs only; supported on Linux; not acceptance.")
    return result


def main() -> int:
    args = parser().parse_args()
    root = args.work_root.resolve()
    if root.exists():
        raise SystemExit("Use a new --work-root; existing evidence will not be overwritten.")
    root.mkdir(parents=True)
    prep = preflight()
    write_json(root / "preflight.json", prep)
    if prep["frozen_inputs"]["status"] != "passed":
        print(json.dumps(prep, indent=2, ensure_ascii=False))
        return 2
    if args.preflight_only:
        print("Frozen input verification passed. Windows build/tests were not executed.")
        return 0
    journal = {"schema": 1, "started_at": now(), "status": "running",
               "platform": platform.system(), "controller_python": sys.version,
               "controller_pid": os.getpid(), "source_commit": SOURCE_COMMIT,
               "steps": [], "release_ready": False,
               "github": {name: os.environ[name] for name in
                          ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID",
                           "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "RUNNER_OS", "ImageOS", "ImageVersion")
                          if name in os.environ},
               "kit_inputs_sha256": prep["frozen_inputs"]["manifest_sha256"]}
    write_json(root / "run.json", journal)
    try:
        if os.name != "nt" or platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Native Windows x64 is required. Linux/Wine/offline checks cannot satisfy this gate.")
        if sys.version_info < (3, 12):
            raise RuntimeError("The build controller requires Python 3.12 or later.")
        powershell = shutil.which(args.powershell)
        if not powershell:
            raise RuntimeError("PowerShell 7.4+ (pwsh) is required.")
        build_root = root / "hosts"
        results = root / "results"
        results.mkdir()
        build_script = KIT / "build" / "Build-FreeCAD.ps1"
        def build(variant: str) -> dict:
            code = run_step(journal, root, "build-" + variant,
                            [powershell, "-NoProfile", "-File", str(build_script),
                             "-WorkRoot", str(build_root), "-Variant", variant,
                             "-Jobs", str(args.jobs), "-PythonExe", sys.executable], 14400)
            if code:
                raise RuntimeError(f"{variant} build failed; its original log is retained.")
            path = build_root / variant / "host-manifest.json"
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            value["_path"] = str(path)
            return value
        baseline = build("unpatched")
        ifc = root / "ifc-runtime"
        code = run_step(journal, root, "prepare-ifc",
                        [sys.executable, str(KIT / "scripts" / "prepare_ifc.py"),
                         "--output", str(ifc), "--host", str(executable(baseline, "cmd")),
                         "--host-manifest", baseline["_path"]], 1200)
        if code:
            raise RuntimeError("The isolated Windows IFC runtime could not be prepared.")
        def suite(name: str, script: str, host: dict, gui: bool, extra: list[str] | None = None) -> int:
            return run_step(journal, root, name,
                [sys.executable, str(KIT / "scripts" / script), "--host",
                 str(executable(host, "gui" if gui else "cmd")), "--host-manifest", host["_path"],
                 "--output", str(results / name), "--ifc-python-path", str(ifc)] + (extra or []), 7200)
        # Windows baseline may pass or reproduce the crash. Its observed outcome
        # is recorded; the collector rejects incomplete/misconfigured controls.
        suite("regression-unpatched", "run_regression.py", baseline, True, ["--tag", "unpatched"])
        patched = build("patched")
        suite("regression-patched", "run_regression.py", patched, True, ["--tag", "patched"])
        suite("native-patched", "run_native.py", patched, False)
        suite("public-gui-patched", "run_public_gui.py", patched, True)
        collect_code = run_step(journal, root, "collect",
            [sys.executable, str(KIT / "scripts" / "collect_acceptance.py"), "--run-root", str(root)], 300)
        journal["status"] = "automated_windows_acceptance_passed" if collect_code == 0 else "acceptance_failed"
        return 0 if collect_code == 0 else 1
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        journal["status"] = "blocked"
        journal["error"] = str(error)
        print(str(error), file=sys.stderr)
        write_json(root / "WINDOWS_ACCEPTANCE.json", {
            "schema": 1, "status": "blocked", "created_at": now(),
            "reason": str(error), "windows_automated_acceptance_passed": False,
            "windows_desktop_acceptance": "pending", "release_ready": False})
        return 2
    finally:
        journal["ended_at"] = now()
        journal["frozen_inputs_after"] = verify_inputs()
        write_json(root / "run.json", journal)


if __name__ == "__main__":
    raise SystemExit(main())
