# Windows public GUI acceptance runner

Status of this implementation: **prepared; no Windows host execution is recorded by preparing these files**. Offline Python tests exercise the report gates and generated launcher. They do not execute FreeCAD on Windows.

The runner uses the frozen `3117_BIM_Studio_v0_5_0_FreeCAD.zip` with SHA-256 `ddfdaed0c10a4d93f4f9e808106f7c31db553d825619cd1ce39cd21ab70b9eb7`. It extracts that archive into a Thai path, installs via the original public installer macro, and starts six further GUI processes using the same isolated Thai user-data directory. The public macros and their model-test sources are unchanged.

| Mode | GUI assertions | Package assertions |
|---|---:|---:|
| Installer | 0 | 6 |
| Foundation smoke | 24 | 7 |
| Wall / Door | 43 | 7 |
| Quantity / IFC | 41 | 7 |
| Building Authoring | 35 | 7 |
| Drawings / Sheets | 53 | 7 |
| Types / Quantities / Schedules | 52 | 7 |
| Required total | **248** | **48** |

## Run after building the patched Windows host

Use the top-level acceptance entrypoint for the complete sequence. The individual commands below are for diagnosis. Use new output directories for every attempt; failed evidence is preserved.

```powershell
python scripts/prepare_ifc.py --host C:/3117/patched/build/bin/FreeCADCmd.exe --host-manifest C:/3117/patched/host-manifest.json --output C:/3117/ifc-runtime
python scripts/run_public_gui.py --host C:/3117/patched/build/bin/FreeCAD.exe --host-manifest C:/3117/patched/host-manifest.json --ifc-python-path C:/3117/ifc-runtime --output C:/3117/evidence/public-gui
```

Use the actual executable paths from the build manifest. Run in an interactive native Windows x64 desktop. A service session, Wine, an offscreen Qt platform, missing visible desktop, missing JSON, mismatched DLL, timeout, or incomplete assertion list fails the gate. A zero process exit code alone cannot pass.

Each FreeCAD process records its actual executable and loaded DLL paths/hashes, Windows version, Python/Qt versions, PID and user-data location. After each public macro, the runner checks loaded installed-addon module hashes. IFC modes also require the actual IfcOpenShell package and native wrapper to come from the isolated verified runtime. `summary.json` references every raw report and hash; `verify_summary()` independently rereads the evidence.

## Preserved assertions and the Windows launcher changes

`inputs/package-gui/package_autopilot.FCMacro` remains the exact reviewed Linux artifact. The runner generates a Windows transport beside the run evidence and saves a unified diff. It changes only:

- Linux `/proc` inspection to Windows in-process loaded-DLL enumeration through the shared helper.
- The isolated profile lookup to `FREECAD_USER_DATA`.
- Explicit UTF-8 decoding for three JSON reads.
- IFC dependency-path precedence before any IFC import, with rejection of already-loaded foreign IFC/Shapely modules.
- The public macro's `__file__` location hint so it locates the extracted package directly. This avoids automating a native Windows folder chooser. The original installer destination confirmation still appears and is checked.

Every `_package_check` predicate and count remains unchanged; the report includes the original body hash and equality after the UTF-8 I/O adjustment. No public macro, geometry check, Undo sequence or history behavior is edited. The existing retained `Gui.getMainWindow()` reference remains in the outer autopilot. With the Windows build's compiled Qt binding route, it is an explicit launcher detail rather than a claim that every unmodified third-party launcher has been tested.

The saved public Types report retains the warning text frozen into v0.5.0. The new summary reports this run separately and does not rewrite archived wording.

## IFC dependency runtime

The pinned FreeCAD source route uses LibPack 3.1.1.3 and embedded Python 3.12.10 x64. The separate official Windows `py311` distribution uses a different Python minor version. Its binary modules cannot be substituted into this build.

`build/ifc-windows.lock.json` pins the Windows Python 3.12 IfcOpenShell 0.8.4 wheel, Shapely 2.1.2, Lark 1.3.1, isodate 0.7.2, python-dateutil 2.9.0.post0, typing-extensions 4.15.0 and six 1.17.0. These are isolated extraction targets, with SHA-256 and size checked before extraction. No system pip install or Qt runtime is added. NumPy 1.26.4 is provided by the pinned FreeCAD LibPack; the probe records its actual version/path and refuses a replacement in the IFC target.

LibPack already contains IfcOpenShell 0.8.1.post1 and Shapely 2.1.0. The pinned FreeCAD `InterpreterSingleton::addPythonPath` appends the supported `--python-path` value. Consequently the launcher also prepends the verified isolated IFC directory before import. It fails if an incompatible IFC/Shapely module has already been loaded; it never unloads or patches a live native module. The host copy is retained.

The preflight imports IFC geometry support in the actual built FreeCADCmd process, verifies Python 3.12 x64, creates an IFC4 file object, and attests the loaded IFC wrapper. The later native and GUI suites perform the full IFC serialization/readback assertions. `--download-only` is available for retrieving/verifying Windows wheels on another OS, but produces `prepared_only` and cannot satisfy runtime acceptance.

## Limits of this gate

Passing this suite establishes the recorded automated GUI workflow only. It does not replace the separate original crash sequence, the 19-process native suite, manual Windows installation/upgrade/recovery checks, physical A3 print measurement, or import into an independently identified BIM application. The suite therefore always keeps `release_ready: false`; the top-level collector combines the applicable gates and keeps remaining manual items explicit.

## Primary sources

- [IfcOpenShell Python installation](https://docs.ifcopenshell.org/ifcopenshell-python/installation.html): choose the OS, Python minor version and architecture together.
- [IfcOpenShell 0.8.4 release metadata](https://pypi.org/pypi/ifcopenshell/0.8.4/json)
- [Shapely 2.1.2 release metadata](https://pypi.org/pypi/shapely/2.1.2/json)
- [Lark 1.3.1 release metadata](https://pypi.org/pypi/lark/1.3.1/json)
- [isodate 0.7.2 release metadata](https://pypi.org/pypi/isodate/0.7.2/json)
- [python-dateutil 2.9.0.post0 metadata](https://pypi.org/pypi/python-dateutil/2.9.0.post0/json)
- [typing-extensions 4.15.0 metadata](https://pypi.org/pypi/typing-extensions/4.15.0/json)
- [six 1.17.0 metadata](https://pypi.org/pypi/six/1.17.0/json)
- [Pinned FreeCAD Interpreter.cpp](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/src/Base/Interpreter.cpp): `addPythonPath` and `runFile` determine the outer launcher's path plumbing.

Wheel hashes and URLs were retrieved from PyPI release JSON on 2026-10-23. Those metadata checks are distinct from Windows execution.
