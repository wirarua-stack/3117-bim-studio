"""Shared Windows acceptance helpers. Importable on Linux; execution is Windows-only.

The module enumerator runs *inside the tested FreeCAD process*, not in an
unrelated Python process. API references:
https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-enumprocessmodulesex
https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getmodulefilenameexw
"""
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

KIT = Path(__file__).resolve().parents[1]
CORE = ("FreeCADBase.dll", "FreeCADApp.dll", "FreeCADGui.dll", "Part.pyd", "TechDraw.pyd")


def is_runtime_module(path):
    return bool(re.fullmatch(r"(?:qt[56](?:core|gui|widgets)|python\d+|pyside\d[^\\/]*|shiboken\d[^\\/]*|coin\d*)\.dll"
                             r"|(?:qtcore|qtgui|qtwidgets|shiboken)[^\\/]*\.pyd", ntpath.basename(str(path)), re.I))


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value, None
    except (OSError, ValueError) as error:
        return {}, str(error)


def require_windows():
    if os.name != "nt" or platform.system() != "Windows":
        raise RuntimeError("Native Windows is required; no Windows test has been executed")
    import ctypes
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("Run with a native 64-bit Windows Python")
    if any(name.startswith("WINE") for name in os.environ):
        raise RuntimeError("Wine does not establish native Windows acceptance")
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    if getattr(ntdll, "wine_get_version", None) is not None:
        raise RuntimeError("Wine does not establish native Windows acceptance")


def new_output(path):
    path = Path(path).resolve()
    if path.exists():
        raise RuntimeError("Output must not already exist: " + str(path))
    path.mkdir(parents=True)
    return path


def verify_inputs(kit=KIT):
    kit = Path(kit).resolve()
    lock_path = kit / "inputs.lock.json"
    lock, error = read_json(lock_path)
    if error or not isinstance(lock.get("files"), list) or not lock["files"]:
        raise RuntimeError("Missing/malformed frozen input lock: " + str(error))
    seen = set()
    for item in lock["files"]:
        relative = item["path"]
        path = (kit / relative).resolve()
        if path == kit or kit not in path.parents or relative in seen:
            raise RuntimeError("Unsafe or duplicate frozen input path: " + relative)
        seen.add(relative)
        if not path.is_file() or sha(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise RuntimeError("Frozen input changed or missing: " + relative)
    return {"files_verified": len(seen), "lock_sha256": sha(lock_path)}


def profile_env(profile, *, gui=True):
    profile = Path(profile).resolve()
    env = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "FREECAD_USER_HOME", "FREECAD_USER_DATA", "FREECAD_USER_TEMP",
                 "QT_QPA_PLATFORM", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH",
                 "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        env.pop(name, None)
    for name, child in (("FREECAD_USER_HOME", "home"), ("FREECAD_USER_DATA", "data"),
                        ("FREECAD_USER_TEMP", "temp")):
        directory = profile / child
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    if not gui:
        env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def winpath(value):
    return ntpath.normcase(ntpath.normpath(str(value)))


def file_record(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def host_inventory(host, host_manifest=None):
    host = Path(host).resolve(strict=True)
    inventory = {"executable": file_record(host), "libraries": {}, "build_manifest": None,
                 "host_root": str(host.parent.parent), "runtime_libraries": []}
    manifest = None
    if host_manifest:
        manifest, error = read_json(host_manifest)
        if error:
            raise RuntimeError("Cannot read build host manifest: " + error)
        inventory["build_manifest"] = file_record(host_manifest)
        inventory["build_variant"] = manifest.get("variant")
        inventory["expected_python_version"] = manifest.get("expected_python_version")
        inventory["expected_qt_version"] = manifest.get("expected_qt_version")
        inventory["host_root"] = str(Path(manifest.get("host_root", host.parent.parent)).resolve(strict=True))
        host_records = manifest.get("executables", {})
        if not any(isinstance(item, dict) and winpath(item.get("path", "")) == winpath(host)
                   and item.get("sha256") == inventory["executable"]["sha256"]
                   for item in host_records.values()):
            raise RuntimeError("Host executable does not match its build manifest")
        source_libraries = manifest.get("libraries", {})
        for name in CORE:
            item = source_libraries.get(name)
            if not isinstance(item, dict) or not item.get("path"):
                raise RuntimeError("Build manifest is missing " + name)
            actual = file_record(item["path"])
            if actual["sha256"] != item.get("sha256"):
                raise RuntimeError("Build library changed: " + name)
            inventory["libraries"][name] = actual
        if not isinstance(manifest.get("runtime_libraries"), list) or not manifest["runtime_libraries"]:
            raise RuntimeError("Build manifest has no Qt/Python runtime inventory")
        for item in manifest["runtime_libraries"]:
            actual = file_record(item["path"])
            if actual["sha256"] != item.get("sha256"):
                raise RuntimeError("Runtime library changed: " + item["path"])
            inventory["runtime_libraries"].append(actual)
    else:
        root = host.parent.parent
        for name in CORE:
            direct = host.parent / name
            matches = [direct] if direct.is_file() else list(root.rglob(name))
            matches = [path for path in matches if path.is_file()]
            if len(matches) != 1:
                raise RuntimeError("Expected one " + name + " below " + str(root) + "; found " + str(len(matches)))
            inventory["libraries"][name] = file_record(matches[0])
        inventory["runtime_libraries"] = [file_record(path) for path in sorted(root.rglob("*"))
                                          if path.is_file() and is_runtime_module(path)]
    return inventory


def _loaded_windows_modules():
    """Return OS executable path and DLL paths from this exact process."""
    require_windows()
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.GetCurrentProcess()
    enum = kernel.K32EnumProcessModulesEx
    enum.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
                     ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    enum.restype = wintypes.BOOL
    filename = kernel.K32GetModuleFileNameExW
    filename.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    filename.restype = wintypes.DWORD
    size = 256
    for _ in range(8):
        modules = (wintypes.HMODULE * size)()
        needed = wintypes.DWORD()
        if not enum(handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3):
            raise ctypes.WinError(ctypes.get_last_error())
        count = needed.value // ctypes.sizeof(wintypes.HMODULE)
        if needed.value <= ctypes.sizeof(modules):
            break
        size = count + 64
    else:
        raise RuntimeError("Loaded DLL list did not stabilize")
    paths = []
    for module in list(modules)[:count]:
        buffer = ctypes.create_unicode_buffer(32768)
        length = filename(handle, module, buffer, len(buffer))
        if not length or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        paths.append(str(Path(buffer.value).resolve(strict=True)))
    own_filename = kernel.GetModuleFileNameW
    own_filename.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    own_filename.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    length = own_filename(None, buffer, len(buffer))
    if not length or length >= len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    return str(Path(buffer.value).resolve(strict=True)), sorted(set(paths))


def capture_host(profile, stage, completed=False):
    """Call within FreeCAD. No substitute Qt runtime is imported or installed."""
    require_windows()
    import ctypes
    import FreeCAD as App
    # Suppress modal Windows Error Reporting for these disposable test processes.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel.SetErrorMode.restype = ctypes.c_uint
    kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    executable, paths = _loaded_windows_modules()
    interesting = [path for path in paths if ntpath.basename(path).casefold() in {x.casefold() for x in CORE}
                   or is_runtime_module(path) or ntpath.basename(path).startswith("_ifcopenshell_wrapper")]
    modules = {}
    for name in ("Part", "TechDraw", "ifcopenshell", "ifcopenshell._ifcopenshell_wrapper",
                 "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "shiboken6.Shiboken"):
        module = sys.modules.get(name)
        filename = getattr(module, "__file__", None)
        if filename:
            modules[name] = file_record(filename)
    addon_modules = {}
    for name, module in list(sys.modules.items()):
        if name.startswith(("bim3117", "ui3117")) and getattr(module, "__file__", None):
            addon_modules[name] = file_record(module.__file__)
    qt = None
    desktop = None
    if App.GuiUp:
        from ctypes import wintypes
        from PySide import QtCore, QtWidgets
        qt = QtCore.qVersion()
        session = wintypes.DWORD()
        kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel.ProcessIdToSessionId.restype = wintypes.BOOL
        session_ok = bool(kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)))
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetProcessWindowStation.restype = wintypes.HANDLE
        station = user.GetProcessWindowStation()
        class USEROBJECTFLAGS(ctypes.Structure):
            _fields_ = [("inherit", wintypes.BOOL), ("reserved", wintypes.BOOL), ("flags", wintypes.DWORD)]
        flags, needed = USEROBJECTFLAGS(), wintypes.DWORD()
        user.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                 wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        user.GetUserObjectInformationW.restype = wintypes.BOOL
        station_ok = bool(user.GetUserObjectInformationW(station, 1, ctypes.byref(flags),
                                                        ctypes.sizeof(flags), ctypes.byref(needed)))
        application = QtWidgets.QApplication.instance()
        screens = application.screens() if application else []
        desktop = {"session_id": session.value if session_ok else None,
                   "window_station_visible": bool(flags.flags & 1) if station_ok else None,
                   "qt_platform": application.platformName() if application else None,
                   "screens": [{"name": screen.name(), "width": screen.size().width(),
                                "height": screen.size().height()} for screen in screens]}
    windows = sys.getwindowsversion()
    user_data = Path(App.getUserAppDataDir()).resolve()
    return {"schema": 1, "system": "Windows", "platform": platform.platform(), "native_windows": True,
            "windows_version": {"major": windows.major, "minor": windows.minor, "build": windows.build,
                                "platform_version": list(windows.platform_version)},
            "architecture": platform.machine(), "pid": os.getpid(), "recorded_at_utc": stamp(),
            "freecad": App.Version(), "python": sys.version, "python_version": list(sys.version_info[:3]),
            "qt": qt, "desktop": desktop, "gui_up": bool(App.GuiUp), "user_data": str(user_data),
            "stage": stage, "entry_completed": bool(completed), "executable": file_record(executable),
            "loaded_library_sha256": {path: sha(path) for path in interesting},
            "loaded_module_paths": paths, "module_files": modules, "addon_module_files": addon_modules,
            "addon_modules_at_entry": sorted(addon_modules),
            "addon_directories": sorted(str(path) for path in (user_data / "Mod").glob("*")),
            "ifcopenshell_version": getattr(sys.modules.get("ifcopenshell"), "__version__", None)}


def validate_identity(identity, expected_host, profile, *, gui, completed=None,
                      required_modules=(), expected_pid=None):
    reasons = []
    if identity.get("system") != "Windows" or identity.get("native_windows") is not True:
        reasons.append("Not native Windows evidence")
    version = identity.get("freecad", [])
    if not isinstance(version, (list, tuple)) or list(version[:3]) != ["1", "1", "4"]:
        reasons.append("FreeCAD version is not 1.1.4")
    if expected_host.get("expected_python_version") and identity.get("python_version") != expected_host["expected_python_version"]:
        reasons.append("Embedded Python version differs from the build manifest")
    if identity.get("gui_up") is not bool(gui):
        reasons.append("GUI/headless mode mismatch")
    if gui:
        if expected_host.get("expected_qt_version") and identity.get("qt") != expected_host["expected_qt_version"]:
            reasons.append("Qt version differs from the build manifest")
        desktop = identity.get("desktop") or {}
        if (desktop.get("qt_platform") != "windows" or not desktop.get("screens")
                or desktop.get("window_station_visible") is not True
                or type(desktop.get("session_id")) is not int or desktop["session_id"] == 0):
            reasons.append("Interactive Windows desktop evidence is missing")
    if completed is not None and identity.get("entry_completed") is not completed:
        reasons.append("Entry completion mismatch")
    if expected_pid is not None and identity.get("pid") != expected_pid:
        reasons.append("Evidence PID differs from the launched process")
    expected_exe = expected_host["executable"]
    actual_exe = identity.get("executable", {})
    if winpath(actual_exe.get("path", "")) != winpath(expected_exe["path"]) or actual_exe.get("sha256") != expected_exe["sha256"]:
        reasons.append("Executable path/hash mismatch")
    user_data, base = winpath(identity.get("user_data", "")), winpath(profile)
    if not user_data.startswith(base.rstrip("\\") + "\\"):
        reasons.append("Profile is not isolated")
    loaded = {winpath(path): digest for path, digest in identity.get("loaded_library_sha256", {}).items()}
    if expected_host.get("host_root"):
        root = winpath(expected_host["host_root"]).rstrip("\\") + "\\"
        runtime = {winpath(item["path"]): item["sha256"] for item in expected_host.get("runtime_libraries", [])}
        for path, digest in loaded.items():
            if is_runtime_module(path) and (not path.startswith(root) or runtime.get(path) != digest):
                reasons.append("Foreign/unrecorded Qt/Python runtime module loaded: " + path)
        required_runtime = ["qt6core.dll", "python312.dll"] + (["qt6gui.dll", "qt6widgets.dll"] if gui else [])
        for name in required_runtime:
            if not any(ntpath.basename(path) == name and runtime.get(path) == digest for path, digest in loaded.items()):
                reasons.append("Expected Qt/Python runtime module not loaded: " + name)
    required = ["FreeCADBase.dll", "FreeCADApp.dll"] + (["FreeCADGui.dll"] if gui else [])
    required += [name + ".pyd" for name in required_modules]
    for name in required:
        item = expected_host["libraries"].get(name, {})
        if not item or loaded.get(winpath(item["path"])) != item["sha256"]:
            reasons.append("Expected loaded library missing/mismatched: " + name)
    for name, item in expected_host["libraries"].items():
        collisions = [(path, digest) for path, digest in loaded.items() if ntpath.basename(path) == name.casefold()]
        if any(path != winpath(item["path"]) or digest != item["sha256"] for path, digest in collisions):
            reasons.append("Foreign host library loaded: " + name)
    module_files = identity.get("module_files", {})
    for module in required_modules:
        actual = module_files.get(module, {})
        expected = expected_host["libraries"][module + ".pyd"]
        if winpath(actual.get("path", "")) != winpath(expected["path"]) or actual.get("sha256") != expected["sha256"]:
            reasons.append("Imported module path/hash mismatch: " + module)
    return not reasons, reasons


def validate_checks(report, expected):
    checks = report.get("checks")
    return (report.get("status") == "passed" and type(report.get("checks_passed")) is int
            and report["checks_passed"] == expected and isinstance(checks, list) and len(checks) == expected
            and all(isinstance(check, dict) and check.get("status") == "passed" for check in checks))


def ifc_inventory(directory):
    directory = Path(directory).resolve(strict=True)
    package = directory / "ifcopenshell" / "__init__.py"
    wrappers = list((directory / "ifcopenshell").glob("_ifcopenshell_wrapper*.pyd"))
    if not package.is_file() or len(wrappers) != 1:
        raise RuntimeError("Expected exactly one Windows IfcOpenShell package and wrapper in " + str(directory))
    return {"version": "0.8.4", "package": file_record(package), "wrapper": file_record(wrappers[0])}


def configure_ifc_path(directory):
    """Select the isolated IFC dependencies before their first import.

    FreeCAD's --python-path appends to sys.path. A LibPack may already ship an
    older IfcOpenShell; prepend the explicitly attested runtime, never delete
    a live imported extension or mix it with another Qt runtime.
    """
    directory = Path(directory).resolve(strict=True)
    for name, module in list(sys.modules.items()):
        if name == "ifcopenshell" or name.startswith("ifcopenshell.") or name == "shapely" or name.startswith("shapely."):
            filename = getattr(module, "__file__", None)
            if not filename or directory not in Path(filename).resolve().parents:
                raise RuntimeError("Foreign IFC dependency already loaded: " + name)
    sys.path.insert(0, str(directory))


def validate_ifc(identity, expected):
    modules = identity.get("module_files", {})
    loaded = {winpath(path): digest for path, digest in identity.get("loaded_library_sha256", {}).items()}
    if identity.get("ifcopenshell_version") != expected["version"]:
        return False
    for name, key in (("ifcopenshell", "package"), ("ifcopenshell._ifcopenshell_wrapper", "wrapper")):
        actual, wanted = modules.get(name, {}), expected[key]
        if winpath(actual.get("path", "")) != winpath(wanted["path"]) or actual.get("sha256") != wanted["sha256"]:
            return False
    return loaded.get(winpath(expected["wrapper"]["path"])) == expected["wrapper"]["sha256"]


def validate_installed_modules(identity, repository):
    user_data = Path(identity.get("user_data", ""))
    destination = user_data / "Mod" / "BIM3117"
    modules = identity.get("addon_module_files", {})
    if not modules:
        return False
    for item in modules.values():
        path = Path(item["path"])
        try:
            relative = path.relative_to(destination)
        except ValueError:
            return False
        source = Path(repository) / "workbench" / relative
        if not source.is_file() or sha(source) != item["sha256"]:
            return False
    return True


def run_process(command, env, cwd, log_path, timeout):
    require_windows()
    if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
        raise ValueError("Expected an argument array; shell commands are not accepted")
    log_path = Path(log_path)
    result = {"command": command, "pid": None, "returncode": None, "exit_code": None,
              "timed_out": False, "launch_error": None, "started_at_utc": stamp(), "log_path": str(log_path)}
    start = time.monotonic()
    with log_path.open("wb") as log:
        try:
            process = subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            result["pid"] = process.pid
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                # This targets the process created above, never unrelated FreeCAD windows.
                try:
                    if process.poll() is None:
                        killer = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
                        cleanup = subprocess.run([str(killer), "/PID", str(process.pid), "/T", "/F"],
                                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                                 timeout=20, check=False)
                        result["cleanup_exit_code"] = cleanup.returncode
                except (OSError, subprocess.TimeoutExpired) as error:
                    result["cleanup_error"] = str(error)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=10)
            result["returncode"] = result["exit_code"] = process.returncode
        except OSError as error:
            result["launch_error"] = str(error)
            log.write((str(error) + "\n").encode("utf-8"))
    result.update(finished_at_utc=stamp(), elapsed_seconds=round(time.monotonic() - start, 3),
                  log_sha256=sha(log_path))
    return result


def verify_recorded_file(path, expected_sha256):
    try:
        return isinstance(expected_sha256, str) and Path(path).is_file() and sha(path) == expected_sha256
    except (OSError, TypeError, ValueError):
        return False
