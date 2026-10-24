#!/usr/bin/env python3
"""Pinned native Windows FreeCAD build. Preparation is never a runtime pass."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import uuid
import zipfile
import xml.etree.ElementTree as ET

KIT = Path(__file__).resolve().parents[1]
LOCK_PATH = Path(__file__).with_name("windows-build.lock.json")
GIB = 1024 ** 3
MODULES_ON = {"GUI", "MATERIAL", "PART", "PART_DESIGN", "SKETCHER", "SPREADSHEET",
              "DRAFT", "IMPORT", "MEASURE", "TECHDRAW", "SHOW", "TEST"}
MODULES_OFF = {"FEM", "SANDBOX", "TEMPLATE", "ADDONMGR", "BIM", "DRAWING", "HELP",
               "IDF", "INSPECTION", "JTREADER", "MATERIAL_EXTERNAL", "MESH", "MESH_PART",
               "FLAT_MESH", "OPENSCAD", "CAM", "ASSEMBLY", "PLOT", "POINTS",
               "REVERSEENGINEERING", "ROBOT", "START", "TUX", "WEB", "SURFACE", "VR", "CLOUD"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_record(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path), "bytes": path.stat().st_size}


def verify(path: Path, digest: str, size: int | None = None) -> None:
    if not path.is_file() or (size is not None and path.stat().st_size != size) or sha(path) != digest:
        raise RuntimeError(f"Pinned file check failed: {path}")


def verify_locks(lock: dict) -> dict:
    for key in ("patch_file", "patch_helper"):
        verify(KIT / lock[key], lock["patch_sha256" if key == "patch_file" else "patch_helper_sha256"])
    for name, item in lock["assets"].items():
        if len(item["sha256"]) != 64 or not all(c in "0123456789abcdef" for c in item["sha256"]):
            raise RuntimeError(f"Invalid SHA256 pin for {name}")
        if not item["url"].startswith("https://") or item["bytes"] <= 0:
            raise RuntimeError(f"Invalid HTTPS/size pin for {name}")
    return {"status": "locks_verified_only", "windows_build_executed": False,
            "lock_sha256": sha(LOCK_PATH), "patch_helper_sha256": lock["patch_helper_sha256"]}


def download(item: dict, cache: Path) -> Path:
    target = cache / item["filename"]
    if target.exists():
        verify(target, item["sha256"], item["bytes"])
        return target
    temporary = cache / (item["filename"] + ".partial-" + uuid.uuid4().hex)
    try:
        request = urllib.request.Request(item["url"], headers={"User-Agent": "3117-Windows-Acceptance/1"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        verify(temporary, item["sha256"], item["bytes"])
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(exist_ok=False)
    base = destination.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(base) or "\\" in member.filename:
                raise RuntimeError(f"Unsafe ZIP path: {member.filename}")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError("Symlinks are not accepted in this Windows ZIP")
        zipped.extractall(destination)


def extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(exist_ok=False)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(destination, filter="data")


def run(argv: list[str], log: Path, *, cwd: Path | None = None,
        env: dict | None = None, timeout: int = 14400, check: bool = True) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with log.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"argv": argv, "cwd": str(cwd) if cwd else None}) + "\n")
        stream.flush()
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Target only this owned process tree; no image-name kills.
            cleanup = {"pid": process.pid, "tree_termination_confirmed": False}
            killer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
            try:
                stopped = subprocess.run([str(killer), "/PID", str(process.pid), "/T", "/F"],
                                         capture_output=True, timeout=30, check=False)
                cleanup.update(taskkill_exit_code=stopped.returncode,
                               tree_termination_confirmed=stopped.returncode == 0)
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup["taskkill_error"] = str(error)
            finally:
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError as error:
                        cleanup["owned_process_kill_error"] = str(error)
                try:
                    cleanup["owned_process_exit_code"] = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    cleanup["owned_process_wait_timed_out"] = True
                write_json(log.with_suffix(".cleanup.json"), cleanup)
            raise RuntimeError(f"Command timed out; bounded owned-process cleanup was attempted. See {log.with_suffix('.cleanup.json')}")
    record = {"argv": argv, "exit_code": code, "elapsed_seconds": round(time.time() - started, 3),
              "log": file_record(log)}
    write_json(log.with_suffix(".command.json"), record)
    if check and code:
        raise RuntimeError(f"Command exited {code}: {argv[0]}. Log: {log}")
    return record


def tree_records(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def cmake_options(libpack: Path) -> dict[str, str]:
    options = {"BUILD_" + name: "ON" for name in MODULES_ON}
    options.update({"BUILD_" + name: "OFF" for name in MODULES_OFF})
    options.update({
        "BUILD_FORCE_DIRECTORY": "ON", "CMAKE_BUILD_TYPE": "Release", "CMAKE_CXX_STANDARD": "20",
        "CMAKE_VS_NO_COMPILE_BATCHING": "ON", "ENABLE_DEVELOPER_TESTS": "OFF",
        "FREECAD_RELEASE_PDB": "ON", "FREECAD_USE_PCH": "OFF",
        "FREECAD_LIBPACK_USE": "ON", "FREECAD_LIBPACK_DIR": str(libpack),
        "FREECAD_COPY_DEPEND_DIRS_TO_BUILD": "ON", "FREECAD_COPY_LIBPACK_BIN_TO_BUILD": "ON",
        "FREECAD_COPY_PLUGINS_BIN_TO_BUILD": "ON", "FREECAD_USE_PYSIDE": "ON",
        "FREECAD_USE_SHIBOKEN": "ON", "FREECAD_QT_VERSION": "6", "FREECAD_USE_EXTERNAL_FMT": "ON",
        "FETCHCONTENT_FULLY_DISCONNECTED": "ON", "FREECAD_3DCONNEXION_SUPPORT": "None",
    })
    return dict(sorted(options.items()))


def find_one(root: Path, filename: str) -> Path:
    found = [p for p in root.rglob(filename) if p.is_file()]
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one {filename} under {root}, found {len(found)}")
    return found[0]


def check_pe_x64(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise RuntimeError(f"Not a Windows PE binary: {path}")
        stream.seek(struct.unpack_from("<I", header, 0x3C)[0])
        pe = stream.read(6)
    if pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 4)[0] != 0x8664:
        raise RuntimeError(f"Expected a Windows AMD64 PE binary: {path}")


def binding_definitions(project: Path) -> dict:
    ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    root = ET.parse(project).getroot()
    groups = [g for g in root.findall("m:ItemDefinitionGroup", ns)
              if "Release|x64" in g.attrib.get("Condition", "")]
    definitions = []
    for group in groups:
        for node in group.findall("m:ClCompile/m:PreprocessorDefinitions", ns):
            definitions.extend((node.text or "").split(";"))
    required = {"HAVE_PYSIDE6", "HAVE_SHIBOKEN6"}
    if not required.issubset(set(definitions)):
        raise RuntimeError("Configured Release GUI lacks compiled PySide6/Shiboken6 definitions")
    sdk_nodes = root.findall("m:PropertyGroup/m:WindowsTargetPlatformVersion", ns)
    sdk_versions = sorted({node.text.strip() for node in sdk_nodes if node.text})
    if len(sdk_versions) != 1:
        raise RuntimeError("Cannot attest one Windows SDK version from the generated GUI project")
    return {"project": file_record(project), "required_definitions": sorted(required),
            "release_definitions": sorted(set(definitions)), "windows_sdk_version": sdk_versions[0], "status": "passed"}


def visual_studio(logs: Path) -> dict:
    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(program_files) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if not vswhere.is_file():
        raise RuntimeError("Visual Studio2022 C++ x64 tools (v143) and WindowsSDK must already be installed; vswhere.exe missing")
    args = [str(vswhere), "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-version", "[17.0,18.0)", "-latest", "-property", "installationPath"]
    found = subprocess.run(args, text=True, capture_output=True, check=True).stdout.strip()
    if not found or not Path(found).is_dir():
        raise RuntimeError("No existing Visual Studio2022 installation with C++ x64 tools found")
    installation = Path(found)
    version_path = installation / "VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt"
    version = version_path.read_text(encoding="utf-8-sig").strip()
    compiler_dir = installation / "VC/Tools/MSVC" / version / "bin/Hostx64/x64"
    compiler = compiler_dir / "cl.exe"
    linker = compiler_dir / "link.exe"
    dumpbin = compiler_dir / "dumpbin.exe"
    for tool in (compiler, linker, dumpbin):
        if not tool.is_file():
            raise RuntimeError(f"Missing VS2022 x64 tool: {tool}")
    probe = run([str(compiler), "/Bv"], logs / "compiler-version.log", timeout=30, check=False)
    return {"installation_path": str(installation), "toolset_version": version,
            "compiler": file_record(compiler), "linker": file_record(linker),
            "dumpbin": file_record(dumpbin), "version_probe": probe}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--variant", choices=["unpatched", "patched"], required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--seven-zip", default="")
    parser.add_argument("--verify-locks", action="store_true")
    args = parser.parse_args(argv)
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locks = verify_locks(lock)
    if args.verify_locks:
        print(json.dumps(locks, indent=2))
        return 0
    if sys.version_info < (3, 12):
        raise RuntimeError("The orchestration Python must be3.12+; FreeCAD uses the pinned LibPack Python")
    if os.name != "nt" or platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Native Windows AMD64 execution is required; Linux/Wine preparation cannot pass this gate")
    if struct.calcsize("P") != 8:
        raise RuntimeError("Use a64-bit orchestration Python on Windows x64")
    import ctypes
    if hasattr(ctypes.WinDLL("ntdll"), "wine_get_version"):
        raise RuntimeError("Wine cannot provide native Windows acceptance")
    work = args.work_root.resolve()
    work.mkdir(parents=True, exist_ok=True)
    variant = work / args.variant
    shared = work / "_build_shared"
    marker = work / "build-work-root.json"
    if marker.exists():
        if json.loads(marker.read_text(encoding="utf-8")).get("lock_sha256") != sha(LOCK_PATH):
            raise RuntimeError("Work root belongs to a different build lock; choose a fresh path")
    else:
        if any((work / name).exists() for name in ("unpatched", "patched", "_build_shared")):
            raise RuntimeError("Refusing existing build paths without this kit's ownership marker")
        write_json(marker, {"schema": 1, "lock_sha256": sha(LOCK_PATH), "purpose": "3117 isolated Windows acceptance"})
    if variant.exists():
        raise RuntimeError(f"Refusing to overwrite an existing attempt: {variant}. Choose a new WorkRoot.")
    minimum_free = (12 if shared.exists() else 30) * GIB
    available = shutil.disk_usage(work).free
    if available < minimum_free:
        raise RuntimeError(f"Need at least {minimum_free // GIB}GiB free for this stage; available {available / GIB:.1f}GiB. No existing files were removed.")
    variant.mkdir()
    logs = variant / "logs"
    logs.mkdir()
    status_path = variant / "build-status.json"
    started = time.time()
    try:
        seven = args.seven_zip or shutil.which("7z.exe") or shutil.which("7z")
        if not seven:
            candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip/7z.exe"
            if candidate.is_file():
                seven = str(candidate)
        if not seven or not Path(seven).is_file():
            raise RuntimeError("Existing 7-Zip executable required; pass --seven-zip or install7-Zip before running")
        toolchain = visual_studio(logs)
        shared.mkdir(exist_ok=True)
        cache = shared / "downloads"
        cache.mkdir(exist_ok=True)
        archives = {key: download(item, cache) for key, item in lock["assets"].items()}
        cmake_extract = shared / "cmake"
        if not cmake_extract.exists():
            extract_zip(archives["cmake"], cmake_extract)
        cmake = cmake_extract / lock["assets"]["cmake"]["archive_root"] / "bin/cmake.exe"
        if not cmake.is_file():
            raise RuntimeError("Pinned CMake archive did not provide bin/cmake.exe")
        cmake_version = run([str(cmake), "--version"], logs / "cmake-version.log", timeout=30)
        if "cmake version 3.31.6" not in (logs / "cmake-version.log").read_text(encoding="utf-8"):
            raise RuntimeError("Unexpected CMake runtime version")
        libpack_extract = shared / "libpack"
        libpack = libpack_extract / lock["assets"]["libpack"]["archive_root"]
        sdk_marker = shared / "libpack-extraction.json"
        if not libpack_extract.exists():
            libpack_extract.mkdir()
            run([str(seven), "x", str(archives["libpack"]), "-o" + str(libpack_extract), "-y"],
                logs / "extract-libpack.log", timeout=1800)
            for required in ("plugins/imageformats/qsvg.dll", "bin/python.exe", "bin/python312.dll", "FREECAD_LIBPACK_VERSION"):
                if not (libpack / required).is_file():
                    raise RuntimeError(f"LibPack layout is incomplete: {required}")
            # Hash all extracted dependency bytes; re-used A/B inputs are checked below.
            write_json(sdk_marker, {"archive_sha256": lock["assets"]["libpack"]["sha256"], "files": tree_records(libpack)})
        if not sdk_marker.is_file():
            raise RuntimeError("Unfinished LibPack extraction; use a fresh WorkRoot")
        recorded_sdk = json.loads(sdk_marker.read_text(encoding="utf-8"))
        if recorded_sdk["archive_sha256"] != lock["assets"]["libpack"]["sha256"]:
            raise RuntimeError("LibPack archive identity changed")
        if recorded_sdk["files"] != tree_records(libpack):
            raise RuntimeError("Extracted LibPack dependency bytes changed between builds")
        source_extract = variant / "source"
        extract_tar(archives["freecad"], source_extract)
        source = source_extract / lock["assets"]["freecad"]["archive_root"]
        gsl_extract = variant / "gsl-source"
        extract_tar(archives["gsl"], gsl_extract)
        gsl_destination = source / "src/3rdParty/GSL"
        if gsl_destination.exists() and any(gsl_destination.iterdir()):
            raise RuntimeError("Source unexpectedly contains a populated GSL submodule")
        gsl_destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(gsl_extract / lock["assets"]["gsl"]["archive_root"], gsl_destination, dirs_exist_ok=True)
        for relative, digest in lock["upstream_source_evidence"].items():
            verify(source / relative, digest)
        document = source / "src/Gui/Document.cpp"
        verify(document, lock["source_document_before_sha256"])
        source_before = tree_records(source)
        if args.variant == "patched":
            run([sys.executable, str(KIT / lock["patch_helper"]), str(document)], logs / "apply-patch.log", timeout=30)
            verify(document, lock["source_document_patched_sha256"])
        source_after = tree_records(source)
        differences = sorted(key for key in source_before.keys() | source_after.keys() if source_before.get(key) != source_after.get(key))
        if differences != (["src/Gui/Document.cpp"] if args.variant == "patched" else []):
            raise RuntimeError(f"Unexpected source changes: {differences}")
        write_json(variant / "source-integrity.json", {"source_commit": lock["source_commit"], "changes": differences,
                   "before": source_before, "after": source_after, "gsl_commit": "543d0dd3fe966ddf20e884b44e5fdbf12cb43784"})
        build = variant / "build"
        options = cmake_options(libpack)
        options["CMAKE_GENERATOR_INSTANCE"] = toolchain["installation_path"]
        env = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "CMAKE_PREFIX_PATH", "FREECAD_LIBPACK_DIR"):
            env.pop(key, None)
        # Do not change the process/user/system environment; only child commands receive this.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        configure = [str(cmake), "-S", str(source), "-B", str(build), "-G", "Visual Studio 17 2022",
                     "-A", "x64", "-T", "v143,host=x64,version=" + toolchain["toolset_version"], "--preset", "release"]
        configure += [f"-D{key}={value}" for key, value in sorted(options.items())]
        configure_record = run(configure, logs / "configure.log", cwd=source, env=env, timeout=1800)
        bindings = binding_definitions(build / "src/Gui/FreeCADGui.vcxproj")
        compile_record = run([str(cmake), "--build", str(build), "--config", "Release", "--parallel", str(args.jobs),
                              "--", "/p:TrackFileAccess=false", "/p:CL_MPcount=1"],
                             logs / "compile.log", cwd=source, env=env, timeout=14400)
        if source_after != tree_records(source):
            raise RuntimeError("Build changed source bytes; inspect before accepting this host")
        binaries = {name: find_one(build, name) for name in ["FreeCAD.exe", "FreeCADCmd.exe", "FreeCADBase.dll",
                    "FreeCADApp.dll", "FreeCADGui.dll", "Part.pyd", "TechDraw.pyd"]}
        for path in binaries.values():
            check_pe_x64(path)
        runtime_libraries = []
        runtime_names = {"qt6core.dll", "qt6gui.dll", "qt6widgets.dll", "python312.dll", "python3.dll", "coin4.dll"}
        for path in sorted((build / "bin").rglob("*")):
            if not path.is_file():
                continue
            name = path.name.lower()
            selected = name in runtime_names or (name.endswith(".dll") and name.startswith(("pyside6", "shiboken6")))
            selected = selected or (name.startswith(("qtcore", "qtgui", "qtwidgets")) and name.endswith(".pyd")
                                    and "pyside6" in str(path.parent).lower())
            selected = selected or (name.startswith("shiboken") and name.endswith(".pyd") and "shiboken6" in str(path.parent).lower())
            if selected:
                check_pe_x64(path)
                runtime_libraries.append({"name": path.name, **file_record(path)})
        if not runtime_names.issubset({item["name"].lower() for item in runtime_libraries}):
            raise RuntimeError("The copied build runtime is missing required Qt/Python/Coin DLLs")
        imports = run([toolchain["dumpbin"]["path"], "/DEPENDENTS", str(binaries["FreeCADGui.dll"])],
                      logs / "gui-imports.log", timeout=60)
        imports_text = (logs / "gui-imports.log").read_text(encoding="utf-8", errors="replace").lower()
        if "pyside6" not in imports_text or "shiboken6" not in imports_text:
            raise RuntimeError("Built GUI DLL does not import both compiled Qt binding libraries")
        normalized_options = dict(options)
        normalized_options["FREECAD_LIBPACK_DIR"] = "<shared verified LibPack>"
        normalized_options["CMAKE_GENERATOR_INSTANCE"] = "<recorded Visual Studio2022 instance>"
        dependency_identity = {"assets": {k: v["sha256"] for k, v in lock["assets"].items()},
                               "compiler_sha256": toolchain["compiler"]["sha256"],
                               "linker_sha256": toolchain["linker"]["sha256"], "toolset_version": toolchain["toolset_version"],
                               "windows_sdk_version": bindings["windows_sdk_version"],
                               "cmake_sha256": sha(cmake), "configuration": "Release", "options": normalized_options}
        signature = hashlib.sha256(json.dumps(dependency_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        manifest = {"schema": 1, "status": "built_not_acceptance_tested", "variant": args.variant,
                    "source_commit": lock["source_commit"], "source_version": "1.1.4",
                    "expected_python_version": [3, 12, 10], "expected_qt_version": "6.8.3",
                    "patch_sha256": lock["patch_sha256"] if args.variant == "patched" else None,
                    "patch_helper_sha256": lock["patch_helper_sha256"], "document_cpp": file_record(document),
                    "host_root": str(build), "source_root": str(source),
                    "executables": {"gui": file_record(binaries["FreeCAD.exe"]), "cmd": file_record(binaries["FreeCADCmd.exe"])},
                    "libraries": {name: file_record(path) for name, path in binaries.items() if not name.endswith(".exe")},
                    "runtime_libraries": runtime_libraries,
                    "cmake": {"binary": file_record(cmake), "version": "3.31.6", "flags": options,
                              "cache": file_record(build / "CMakeCache.txt"), "version_probe": cmake_version},
                    "compiler": toolchain, "bindings": {"definitions": bindings, "imports": imports},
                    "dependency_signature": signature, "dependency_identity": dependency_identity,
                    "inputs": {key: file_record(path) for key, path in archives.items()},
                    "extracted_sdk_manifest": file_record(sdk_marker), "source_integrity": file_record(variant / "source-integrity.json"),
                    "build_commands": {"configure": configure_record, "compile": compile_record},
                    "platform": {"system": platform.system(), "release": platform.release(), "version": platform.version(),
                                 "machine": platform.machine(), "python_orchestrator": sys.version},
                    "windows_acceptance": "not_executed_by_build_script", "release_ready": False,
                    "elapsed_seconds": round(time.time() - started, 3)}
        write_json(variant / "host-manifest.json", manifest)
        write_json(status_path, {"status": "built_not_acceptance_tested", "manifest": file_record(variant / "host-manifest.json"), "release_ready": False})
        print(json.dumps({"status": manifest["status"], "manifest": str(variant / "host-manifest.json")}, indent=2))
        return 0
    except BaseException as error:
        write_json(status_path, {"status": "failed", "variant": args.variant, "error": str(error),
                                "elapsed_seconds": round(time.time() - started, 3), "release_ready": False})
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
