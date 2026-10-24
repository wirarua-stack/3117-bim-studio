"""Prepare hash-pinned Windows IFC wheels and verify them in the built host.

The controller can use a different Python version. The actual import probe runs
in FreeCADCmd's embedded Python. --download-only performs no host validation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import traceback
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile

from windows_common import (KIT, capture_host, file_record, host_inventory, ifc_inventory,
                            new_output, profile_env, read_json, require_windows,
                            run_process, sha, stamp, validate_identity,
                            validate_ifc, winpath, write_json)

LOCK = KIT / "build" / "ifc-windows.lock.json"
ALLOWED_PACKAGES = {"ifcopenshell", "shapely", "lark", "isodate", "python-dateutil", "typing-extensions", "six"}


def load_lock(path=LOCK):
    lock, error = read_json(path)
    if error or lock.get("schema") != 1 or lock.get("target") != {
            "system": "Windows", "architecture": "AMD64", "python": [3, 12]}:
        raise RuntimeError("Invalid Windows Python 3.12 IFC dependency lock: " + str(error))
    packages = lock.get("packages", [])
    if {row.get("package") for row in packages} != ALLOWED_PACKAGES or len(packages) != len(ALLOWED_PACKAGES):
        raise RuntimeError("Unexpected dependency set; no host Qt or replacement NumPy is permitted")
    for row in packages:
        url = urlparse(row["url"])
        name = row["filename"]
        if (url.scheme != "https" or url.hostname != "files.pythonhosted.org"
                or url.username or url.password or url.path.rsplit("/", 1)[-1] != name
                or Path(name).name != name or not name.endswith(".whl")
                or not re.fullmatch("[0-9a-f]{64}", row["sha256"])
                or type(row.get("bytes")) is not int or row["bytes"] <= 0):
            raise RuntimeError("Invalid pinned wheel entry")
        if not (name.endswith("-none-any.whl") or "-py312-none-win_amd64.whl" in name
                or "-cp312-cp312-win_amd64.whl" in name):
            raise RuntimeError("Wheel is not compatible with the pinned host")
    return lock


def download_wheel(row, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / row["filename"]
    if destination.exists():
        if destination.stat().st_size == row["bytes"] and sha(destination) == row["sha256"]:
            return destination
        raise RuntimeError("An existing cached wheel has the wrong hash: " + str(destination))
    temporary = destination.with_suffix(destination.suffix + ".partial")
    if temporary.exists():
        raise RuntimeError("Incomplete previous download exists; preserve it and choose a new cache")
    with urlopen(row["url"], timeout=60) as response, temporary.open("xb") as output:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != "files.pythonhosted.org":
            raise RuntimeError("Wheel download redirected outside the pinned publisher")
        shutil.copyfileobj(response, output, length=1024 * 1024)
    if temporary.stat().st_size != row["bytes"] or sha(temporary) != row["sha256"]:
        raise RuntimeError("Wheel size/hash differs from PyPI lock: " + row["filename"])
    temporary.rename(destination)
    return destination


def safe_member(name):
    # Windows drive syntax, alternate data streams, aliases and symlinks must
    # not let wheel extraction escape the isolated runtime.
    path = PurePosixPath(name)
    reserved = {"con", "prn", "aux", "nul", *("com" + str(i) for i in range(1, 10)),
                *("lpt" + str(i) for i in range(1, 10))}
    return (bool(name) and not path.is_absolute() and "\\" not in name and ":" not in name
            and all(part not in ("", ".", "..") and not part.endswith((" ", "."))
                    and part.split(".", 1)[0].casefold() not in reserved for part in path.parts))


def extract_wheel(wheel, destination):
    destination = Path(destination).resolve()
    records = []
    seen = set()
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            if not safe_member(member.filename) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("Unsafe wheel member: " + member.filename)
            if member.is_dir():
                continue
            parts = PurePosixPath(member.filename).parts
            if parts[0].endswith(".data"):
                if len(parts) < 3 or parts[1] not in ("purelib", "platlib"):
                    raise RuntimeError("Wheel requires unsupported script/global installation")
                parts = parts[2:]
            if parts[-1].endswith(".pth") or parts[-1] in ("sitecustomize.py", "usercustomize.py"):
                raise RuntimeError("Wheel would execute code outside explicit host imports")
            relative = "/".join(parts)
            key = relative.casefold()
            if key in seen:
                raise RuntimeError("Duplicate Windows wheel member")
            seen.add(key)
            target = destination.joinpath(*parts)
            if target.exists():
                raise RuntimeError("Wheel attempts to replace an existing runtime file: " + relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = archive.read(member)
            target.write_bytes(payload)
            records.append({"path": relative, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
    return records


def probe_source(scripts, runtime, profile, report):
    prefix = "\n".join(name + " = " + repr(str(value)) for name, value in (
        ("SCRIPTS", scripts), ("RUNTIME", runtime), ("PROFILE", profile), ("REPORT", report))) + "\n"
    return prefix + '''import json, platform, struct, sys, traceback
from pathlib import Path
sys.path.insert(0, SCRIPTS)
from windows_common import capture_host, configure_ifc_path, write_json
record = {"status": "running"}
try:
    configure_ifc_path(RUNTIME)
    if tuple(sys.version_info[:2]) != (3, 12) or struct.calcsize("P") != 8:
        raise RuntimeError("The actual FreeCAD embedded Python is not 3.12 x64")
    import numpy, ifcopenshell, ifcopenshell.geom, shapely, lark, isodate, dateutil, typing_extensions, six
    if numpy.__version__ != "1.26.4":
        raise RuntimeError("Expected NumPy 1.26.4 from the pinned LibPack")
    if Path(numpy.__file__).resolve().is_relative_to(Path(RUNTIME).resolve()):
        raise RuntimeError("The host NumPy must not be replaced by an IFC wheel")
    for name, module in (("ifcopenshell", ifcopenshell), ("shapely", shapely), ("lark", lark),
                         ("isodate", isodate), ("dateutil", dateutil), ("typing_extensions", typing_extensions), ("six", six)):
        if not Path(module.__file__).resolve().is_relative_to(Path(RUNTIME).resolve()):
            raise RuntimeError("IFC preflight dependency resolved outside its isolated target: " + name)
    if shapely.__version__ != "2.1.2" or lark.__version__ != "1.3.1":
        raise RuntimeError("IFC geometry/parser dependency versions differ from the lock")
    model = ifcopenshell.file(schema="IFC4")
    if model.schema != "IFC4":
        raise RuntimeError("IFC4 parser did not initialize")
    record.update(status="passed", identity=capture_host(PROFILE, "ifc-preflight", completed=True),
                  numpy={"version": numpy.__version__, "path": numpy.__file__},
                  dependencies={name: {"path": module.__file__, "version": getattr(module,"__version__",None)}
                                for name,module in [("shapely",shapely),("lark",lark),("isodate",isodate),
                                                    ("dateutil",dateutil),("typing_extensions",typing_extensions),("six",six)]})
except BaseException as error:
    record.update(status="failed", error=str(error), traceback=traceback.format_exc())
write_json(REPORT, record)
'''


def verify_preflight(path, host_manifest=None):
    """Recheck the dependency lock, runtime files and actual embedded import."""
    summary, error = read_json(path)
    errors = []
    if (error or summary.get("status") != "passed" or summary.get("host_executed") is not True
            or summary.get("platform") != "windows"):
        return {"status": "failed", "errors": [error or "No completed Windows IFC import preflight"]}
    try:
        lock = load_lock()
        if summary.get("lock_sha256") != sha(LOCK):
            errors.append("IFC dependency lock changed")
        wanted = {row["filename"]: row for row in lock["packages"]}
        actual = summary.get("wheels", [])
        if len(actual) != len(wanted) or {row.get("filename") for row in actual} != set(wanted):
            errors.append("The seven locked IFC wheels were not all recorded")
        for row in actual:
            pin = wanted.get(row.get("filename"), {})
            wheel = Path(summary["wheel_cache"]) / row["filename"]
            if (row.get("sha256") != pin.get("sha256") or row.get("bytes") != pin.get("bytes")
                    or not wheel.is_file() or wheel.stat().st_size != pin.get("bytes") or sha(wheel) != pin.get("sha256")):
                errors.append("Missing or mismatched locked wheel: " + row["filename"])
        runtime = Path(summary["runtime"])
        manifest_path = runtime / "ifc-files.json"
        manifest, manifest_error = read_json(manifest_path)
        if manifest_error or sha(manifest_path) != summary.get("files_manifest_sha256"):
            errors.append("IFC extracted-file manifest missing or changed")
        files = manifest.get("files", [])
        if not files or len(files) != sum(row.get("files", 0) for row in actual):
            errors.append("Incomplete extracted IFC file inventory")
        seen = set()
        for record in files:
            name = record["path"]
            target = runtime / name
            if not safe_member(name) or name.casefold() in seen:
                errors.append("Unsafe or duplicate extracted IFC path")
                continue
            seen.add(name.casefold())
            if not target.is_file() or sha(target) != record["sha256"] or target.stat().st_size != record["bytes"]:
                errors.append("Changed extracted IFC dependency: " + name)
        if ifc_inventory(runtime) != summary.get("ifc_inventory"):
            errors.append("The IFC package/native wrapper changed after the preflight")
        for key in ("host_probe_file", "host_probe_script"):
            record = summary.get(key, {})
            if not isinstance(record, dict) or not record.get("path") or sha(record["path"]) != record.get("sha256"):
                errors.append("Missing or changed raw IFC preflight evidence: " + key)
        process = summary.get("process", {})
        if (type(process.get("exit_code")) is not int or process["exit_code"] != 0 or process.get("timed_out")
                or process.get("launch_error") or sha(process["log_path"]) != process.get("log_sha256")):
            errors.append("IFC host probe process/log did not validate")
        raw, raw_error = read_json(summary["raw_report"])
        if Path(summary["raw_report"]).resolve() != Path(summary["host_probe_file"]["path"]).resolve():
            errors.append("The raw IFC import report differs from the hashed report")
        expected = summary["host"]
        if host_manifest and host_inventory(expected["executable"]["path"], host_manifest) != expected:
            errors.append("IFC preflight host differs from the build manifest")
        identity = raw.get("identity", {})
        profile = Path(summary["host_probe_script"]["path"]).parent / "profile"
        valid, reasons = validate_identity(identity, expected, profile, gui=False, completed=True,
                                          expected_pid=process.get("pid"))
        if raw_error or raw.get("status") != "passed" or not valid:
            errors.extend(reasons or [raw_error or "Incomplete raw IFC preflight"])
        if not validate_ifc(identity, summary["ifc_inventory"]):
            errors.append("Actual imported IFC wrapper is not the isolated locked runtime")
        numpy = raw.get("numpy", {})
        if (numpy.get("version") != "1.26.4" or not expected.get("host_root")
                or not winpath(numpy.get("path", "")).startswith(winpath(expected["host_root"]).rstrip("\\") + "\\")):
            errors.append("NumPy did not come from the pinned host runtime")
        for name, record in raw.get("dependencies", {}).items():
            module = Path(record["path"]).resolve()
            if not module.is_relative_to(runtime.resolve()):
                errors.append("Dependency module resolved outside the isolated IFC runtime: " + name)
        if set(raw.get("dependencies", {})) != {"shapely", "lark", "isodate", "dateutil", "typing_extensions", "six"}:
            errors.append("Missing actual dependency-origin observations")
    except (KeyError, TypeError, OSError, ValueError, RuntimeError) as exception:
        errors.append(str(exception))
    return {"status": "passed" if not errors else "failed", "errors": errors,
            "wheels_verified": len(summary.get("wheels", [])), "runtime_files_verified": len(seen) if 'seen' in locals() else 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New isolated directory; pass this same directory as --ifc-python-path")
    parser.add_argument("--host", type=Path, help="The built FreeCADCmd.exe for an actual embedded-runtime probe")
    parser.add_argument("--host-manifest", type=Path)
    parser.add_argument("--wheel-cache", type=Path)
    parser.add_argument("--download-only", action="store_true", help="Verify/extract pinned Windows wheels without executing a host; cannot pass acceptance")
    args = parser.parse_args(argv)
    if not args.download_only and args.host is None:
        parser.error("--host is required unless --download-only is requested")
    output = new_output(args.output)
    summary = {"schema": 1, "status": "running", "platform": "windows", "started_at_utc": stamp(),
               "host_executed": False, "windows_acceptance": "not_executed", "runtime": str(output), "wheels": []}
    summary_path = output / "ifc-preflight.json"
    write_json(summary_path, summary)
    try:
        lock = load_lock()
        summary["lock_sha256"] = sha(LOCK)
        if not args.download_only:
            require_windows()
        cache = args.wheel_cache.resolve() if args.wheel_cache else output / "_wheel_cache"
        summary["wheel_cache"] = str(cache)
        records = []
        for row in lock["packages"]:
            wheel = download_wheel(row, cache)
            files = extract_wheel(wheel, output)
            records.extend(files)
            summary["wheels"].append({"filename": row["filename"], "sha256": sha(wheel), "bytes": wheel.stat().st_size, "files": len(files)})
        write_json(output / "ifc-files.json", {"schema": 1, "files": records})
        summary["files_manifest_sha256"] = sha(output / "ifc-files.json")
        summary["ifc_inventory"] = ifc_inventory(output)
        if args.download_only:
            summary.update(status="prepared_only", runtime_imports="not_executed")
        else:
            evidence = output / "_preflight"
            evidence.mkdir()
            profile = evidence / "profile"
            env = profile_env(profile, gui=False)
            expected = host_inventory(args.host, args.host_manifest)
            summary["host"] = expected
            probe = evidence / "probe.py"
            report_path = evidence / "host-probe.json"
            probe.write_text(probe_source(KIT / "scripts", output, profile, report_path), encoding="utf-8")
            command = [str(args.host.resolve()), "--python-path", str(output), "-u", str(profile / "user.cfg"), str(probe)]
            process = run_process(command, env, evidence, evidence / "host-probe.log", 180)
            summary.update(host_executed=True, process=process, raw_report=str(report_path))
            raw, error = read_json(report_path)
            summary["host_probe_file"] = file_record(report_path) if report_path.is_file() else None
            summary["host_probe_script"] = file_record(probe)
            identity = raw.get("identity", {})
            valid, reasons = validate_identity(identity, expected, profile, gui=False, completed=True, expected_pid=process.get("pid"))
            valid_ifc = validate_ifc(identity, summary["ifc_inventory"])
            if (error or raw.get("status") != "passed" or process.get("exit_code") != 0
                    or process.get("timed_out") or not valid or not valid_ifc):
                raise RuntimeError("Embedded IFC preflight failed: " + repr({"report_error": error, "identity": reasons,
                                   "ifc": valid_ifc, "host_error": raw.get("error")}))
            summary.update(status="passed", runtime_imports="passed", identity=identity, numpy=raw["numpy"], dependencies=raw["dependencies"])
            write_json(summary_path, summary)
            summary["verification"] = verify_preflight(summary_path, args.host_manifest)
            if summary["verification"]["status"] != "passed":
                raise RuntimeError("Final IFC runtime evidence verification failed: " + repr(summary["verification"]["errors"]))
        summary["finished_at_utc"] = stamp()
    except BaseException as error:
        summary.update(status="failed" if summary["host_executed"] or os.name == "nt" else "not_executed",
                       error=str(error), traceback=traceback.format_exc(), finished_at_utc=stamp())
    write_json(summary_path, summary)
    print(json.dumps({"status": summary["status"], "runtime": str(output), "host_executed": summary["host_executed"], "report": str(summary_path)}))
    return 0 if summary["status"] in ("passed", "prepared_only") else 1


if __name__ == "__main__":
    raise SystemExit(main())
