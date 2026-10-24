# Windows build for the reviewed FreeCAD history fix

**Status: automation prepared; no Windows compilation or Windows acceptance result is recorded in this kit.** The downloaded SDK archive has been checked as data on Linux. Its presence, a passing syntax check, or a completed download does not establish that FreeCAD builds or runs on Windows.

The build starts from FreeCAD **1.1.4**, upstream commit `4fd3bf320d9566a27e60069fc8387448aaa3a094`. The patched variant applies the reviewed three-line insertion in `src/Gui/Document.cpp`; all other source files must remain byte-identical. There are separate unpatched and patched source/build directories. The acceptance controller runs the baseline before testing the patched build.

## Why this Windows dependency set

The Windows CI files in the pinned upstream source select **Visual Studio 2022 / MSVC v143**, **CMake 3.31.6** and **LibPack 3.1.1.3**. This kit follows that build dependency route with a reduced module set covering the complete 3117 test suite. The LibPack release specifies Python **3.12.10**, Qt/PySide **6.8.3** and OpenCASCADE **7.8.1**.

This is a custom Windows source build. Its Python version differs from the official FreeCAD 1.1.4 `py311` portable release. The unpatched/patched comparison uses the same source revision, SDK, compiler, configuration and options; only the reviewed source insertion differs. Do not label this route as a reproduction of the official binary's packaging recipe.

Primary sources:

- [Pinned FreeCAD Windows workflow](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/.github/workflows/sub_buildWindows.yml)
- [Pinned LibPack selector](https://github.com/FreeCAD/FreeCAD/blob/4fd3bf320d9566a27e60069fc8387448aaa3a094/.github/workflows/actions/windows/getLibpack/action.yml)
- [LibPack 3.1.1.3 release](https://github.com/FreeCAD/FreeCAD-LibPack/releases/tag/3.1.1.3)
- [Kitware's CMake 3.31.6 checksums](https://github.com/Kitware/CMake/releases/download/v3.31.6/cmake-3.31.6-SHA-256.txt)

The exact pins and source-file checksums are in `build/windows-build.lock.json`. `build/primary-input-evidence.json` records the actual SDK download hash and a read-only archive index.

## Requirements on the Windows machine

- Native Windows x64 with an interactive desktop for the subsequent GUI acceptance phase. Wine and offscreen preparation do not qualify as Windows acceptance.
- Existing Visual Studio 2022 C++ x64 build tools (MSVC v143) and a Windows SDK. The scripts do not install or update Visual Studio.
- Existing PowerShell 7.4 or newer, 64-bit Python 3.12 or newer for orchestration, and 7-Zip. The FreeCAD process uses the LibPack's own Python and Qt runtime.
- An isolated local directory, preferably a short path such as `C:\3117Acceptance\run-01`. Thai paths are exercised by the test profiles and model/export fixtures.
- At least **30 GiB free** before the first build. The shared LibPack contains about **6.68 GB** of extracted data; its `bin` subtree alone is about **2.62 GB**. Each separate build copies runtime dependencies and produces object files/PDBs. The second build requires at least 12 GiB remaining. These are conservative preparation gates, not a measured final Windows disk requirement.

A standard hosted runner with insufficient disk space will fail the preflight. The scripts do not remove unrelated programs or data to create space, and they do not select a paid runner. Use a Windows machine or an existing authorized runner with sufficient capacity.

### Hosted runner preparation

The workflow runs `scripts/Prepare-WindowsRunner.ps1` before compilation. It measures both C: and the volume containing `RUNNER_TEMP`, prefers a writable C: volume with at least 30 GiB available, and otherwise uses the measured eligible runner-temp volume. The selected root is a short, unique `<drive>:\b3117\<run-id>-<attempt>-<nonce>` path exported through `GITHUB_ENV`. The script leaves that root absent for the acceptance controller, and removes only its own one-byte write probe.

Its JSON evidence stays in `RUNNER_TEMP` and is included in the workflow's always-upload step, including when no drive qualifies. The evidence also records native Windows session ID, window-station visibility, monitor count and virtual-screen geometry. These observations are informational: a noninteractive desktop does not prevent compilation, and the later FreeCAD/Qt GUI checks still determine whether GUI acceptance can run. The original 30 GiB first-build and 12 GiB second-build guards remain in force.

## Build entrypoints

The acceptance controller normally invokes these commands. They can also be run directly from the kit directory:

```powershell
pwsh -NoProfile -File .\build\Build-FreeCAD.ps1 `
  -WorkRoot C:\3117Acceptance\run-01 -Variant Unpatched -Jobs 2 -PythonExe python

# Run the preserved baseline regression sequence before the next command.
pwsh -NoProfile -File .\build\Build-FreeCAD.ps1 `
  -WorkRoot C:\3117Acceptance\run-01 -Variant Patched -Jobs 2 -PythonExe python
```

Use `-SevenZipExe 'C:\Program Files\7-Zip\7z.exe'` if 7-Zip is not discoverable. The script refuses to overwrite an existing variant attempt; a failed attempt remains available with its logs. Choose a new work root for a rerun. A lock-only check uses `-VerifyLocks`; its result is explicitly `locks_verified_only` and never counts as a build or runtime pass.

The build downloads the pinned source archive, GSL submodule archive, CMake ZIP and LibPack archive. Each complete archive is checked against its size and SHA-256 before extraction or execution. CMake is unpacked locally and is not added to the user's system PATH. Environment changes are restricted to child commands.

## SDK checksum provenance

The official LibPack release API lists one asset, `LibPack-1.1.0-v3.1.1.3-Release.7z`, **948,616,324 bytes**, asset ID `248987223`. The API returns `digest: null`; the release does not provide a checksum sidecar. This kit therefore pins the hash computed from the complete public release download on 2026-10-23:

```text
3565842b2f2c464d891d37f1ce8467f2cd0b3dd758a6dfacc7acfeff290b67d4
```

This is an observed artifact hash, not an upstream-published signature or checksum. It prevents silent replacement in later runs. The complete SDK is not included in the kit. The Windows build also records the complete extracted SDK file hashes and checks those bytes again before the second build.

## Build and provenance checks

The build uses Release, C++20, bounded MSBuild concurrency, PDB output, the host LibPack, and **compiled PySide/Shiboken bindings enabled**. After configuration the script reads the generated Release `FreeCADGui.vcxproj` and requires both `HAVE_PYSIDE6` and `HAVE_SHIBOKEN6`. After compilation it uses the observed Visual Studio `dumpbin` to require imports of both binding DLLs. A cached CMake option saying `ON` is insufficient if the generated build omitted the bindings.

The module set includes Material, Part, PartDesign, Sketcher, Spreadsheet, Draft, Import, Measure, TechDraw, Show and Test. Built-in BIM, Assembly, FEM, CAM, Mesh and unrelated workbenches are disabled; the frozen 3117 workbench is installed and tested separately. The GSL submodule is supplied from its pinned archive. External fmt comes from the verified LibPack, and implicit FetchContent downloads are disabled.

The script records the actual Visual Studio compiler and linker paths/hashes, full toolset version, Windows SDK version, CMake binary/hash, configuration/options, source and patch identities, all commands/logs, and produced EXE/DLL/PYD hashes. It checks that every required binary is an AMD64 PE file. The same dependency signature must appear in both A/B manifests.

Output files:

| Path relative to WorkRoot | Meaning |
|---|---|
| `unpatched/host-manifest.json` | Exact baseline build identity, created only after successful build checks |
| `patched/host-manifest.json` | Exact patched build identity, created only after successful build checks |
| `<variant>/build-status.json` | Build result or failure reason; never a Windows acceptance result |
| `<variant>/source-integrity.json` | Full source hashes before/after the reviewed patch |
| `<variant>/logs/` | Configure, compile, patch, compiler and binding import evidence |
| `_build_shared/libpack-extraction.json` | Exact extracted SDK dependency inventory shared by A/B |

Both manifests retain `release_ready: false` and `windows_acceptance: not_executed_by_build_script`. The separate regression/native/public-GUI controller must consume the actual build manifests and produce fresh results. Physical print-scale checks, target-machine interaction and external BIM application review still require their own evidence.

## Retaining the exact accepted runtime

The GitHub Actions workflow does **not** treat a successful compilation as a distributable binary. Only after `Start-WindowsAcceptance.ps1` exits successfully and `WINDOWS_ACCEPTANCE.json` says `status: passed` with `windows_automated_acceptance_passed: true`, the workflow seals the same patched build tree used by the tests. It hashes every file under the runtime allowlist `bin`, `data`, `doc`, `Ext`, `lib` and `Mod`, binds that inventory to the patched `host-manifest.json`, the acceptance report and the GitHub commit/run identity, and writes `accepted-runtime-seal/accepted-runtime-manifest.json`.

The success-only artifact `3117-accepted-patched-runtime-<run>-<attempt>` retains those exact runtime directories plus the verified isolated IFC runtime and frozen public Workbench ZIP. It uses the files in-place from `hosts/patched/build`; it does not rebuild, strip, clean or substitute binaries after testing. This artifact is retained for trial-packaging work only and does not set `release_ready: true`. A later portable/installer stage must re-check its SHA-256 manifest after download and relocation and must keep the manual Windows desktop checklist separate.

## Known execution limits of this handoff

The Windows script has not yet been run on a Windows machine. MSVC configuration, generated project layout, PE loading, GUI behavior and full source compilation remain to be verified there. The local checks cover input/patch integrity, Python and PowerShell syntax and selected fail-closed guards; they do not replace the requested Windows build, crash sequence, Undo/Redo, save/reopen or the 3117 suites.
