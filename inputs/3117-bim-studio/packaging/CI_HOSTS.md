# FreeCAD host integration: artifact pins and evidence

Pins verified against official release metadata and checksum files on **2026-10-23**. This document describes a prepared workflow; it does not record a remote CI execution. Actual results belong in [the verification record](../docs/VERIFICATION.md).

## Official host artifacts

Both jobs target [FreeCAD 1.1.4](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4). The workflow downloads the following exact assets, compares the complete SHA-256 value before execution, and fails on mismatch. The release's [official API metadata](https://api.github.com/repos/FreeCAD/FreeCAD/releases/tags/1.1.4) provides the asset names and URLs; each linked checksum file was also retrieved and compared when preparing these pins.

| Platform | Artifact and checksum source | Pinned SHA-256 |
| --- | --- | --- |
| Linux x86_64 | `FreeCAD_1.1.4-Linux-x86_64-py311.AppImage`; [official checksum](https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage-SHA256.txt) | `f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434` |
| Windows x86_64 | `FreeCAD_1.1.4-Windows-x86_64-py311.7z`; [official checksum](https://github.com/FreeCAD/FreeCAD/releases/download/1.1.4/FreeCAD_1.1.4-Windows-x86_64-py311.7z-SHA256.txt) | `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d` |

Linux uses `ubuntu-24.04`, extracts the AppImage and runs `AppRun freecadcmd`; FUSE is not required. Windows uses `windows-latest`, extracts the portable 7z with the runner's 7-Zip and locates the single `bin/FreeCADCmd.exe`. Runner images can change independently of the pinned FreeCAD archive. Record the reported OS and host runtime when evaluating a particular run.

## Pinned GitHub Actions

The official release tags and their referenced commits were resolved through GitHub's repository API. The workflow pins complete commit identifiers rather than mutable major-version tags.

| Official action release | Pinned commit |
| --- | --- |
| [actions/checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| [actions/setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0) | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| [actions/upload-artifact v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |

Independent Python 3.12 runs the standard-library installer tests and orchestrates host processes. Model tests execute in the downloaded FreeCAD's embedded Python. The child process has inherited `PYTHONHOME` and `PYTHONPATH` removed, and no alternate Qt/PySide runtime is installed.

## Nineteen-process test contract

The workflow creates an isolated profile and all directories before starting FreeCAD. This matters because upstream documents that nonexistent `FREECAD_USER_HOME`, `FREECAD_USER_DATA` and `FREECAD_USER_TEMP` directories are ignored; see [Start up and Configuration](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Start_up_and_Configuration.md). That documentation is a moving upstream page, while the release artifacts above are explicitly pinned.

All stages run `tests/run_freecad_tests.py` with the same profile and `BIM3117_QA_OUTPUT` directory. Each is a new process, with `BIM3117_QA_STAGE` set as follows:

| Stage | Required report | Purpose |
| --- | --- | --- |
| `install` | `install-report.json` | Use the real host's user data directory to install the workbench via the normal installer helper. Exit before testing. |
| `foundation` | `foundation-test-report.json` | Import the installed workbench, test native document behavior and write the `.FCStd` fixture. |
| `reopen` | `reopen-test-report.json` | Reopen in a fresh process, verify restored model proxies and persistent IDs, and exercise dependency updates/Undo. |
| `architecture` | `architecture-test-report.json` | Test native WallType/Wall/Door, actual boolean geometry, type/level/host propagation, rollback, native Properties, deletion and the old Foundation fixture. |
| `architecture_reopen` | `architecture-reopen-test-report.json` | Fresh-process restore of authored walls/doors and derived bodies, then dependency edits and Undo/Redo. |
| `exchange` | `exchange-test-report.json` | Native quantities/revisions, stale/invalid model guards, CSV and IFC readback from installed modules. |
| `exchange_reopen` | `exchange-reopen-test-report.json` | Fresh-process native restore with stable content revision, quantities and export identity. |
| `building` | `building-test-report.json` | Slab/Column/Beam/Window and bounded slab joins, rollback, mixed openings, quantities and IFC4 from the same two-storey model. |
| `building_reopen` | `building-reopen-test-report.json` | Restore all new proxies and joins in a fresh process, update the slab, Undo, and verify stable IFC GlobalIds. |
| `drawing_geometry` | `drawing-geometry-test-report.json` | Actual cut holes/joins, finite view range, cardinal frames, global occlusion and unchanged source solids. |
| `drawings` | `drawings-test-report.json` | Persistent native View/Sheet, transactions, dependency guards, legacy model hash and separate drawing revision. |
| `drawings_reopen` | `drawings-reopen-test-report.json` | Restore drawing definitions/UUIDs/links in a fresh host, recapture and verify model/view edits with Undo. |
| `drawing_render` | `drawing-render-test-report.json` | Headless vector SVG scale/layout/source provenance and stale/overwrite/publication guards. PDF is checked separately in actual host Qt GUI. |

The workbench source folder must not be inserted into `sys.path`, and proxy classes must not be preregistered to bypass FreeCAD's document restore loader. Importing the test harness from `tests/` does not replace installation of the add-on.

For every stage the gate requires a new JSON report with `status: "passed"`, a nonempty `checks` array whose entries all have `status: "passed"`, `checks_passed` equal to its length, and host process exit code zero. Every model test report must identify FreeCAD `1.1.4` and `gui_up: false`. Missing reports, timeouts, malformed reports and Python failures fail the job even if FreeCAD returns zero. Logs, reports and the native samples are retained as workflow artifacts for 14 days.

## Release status boundary

Creating this workflow does not prove either operating system passed it. Passing the Windows headless job would establish the tested document and installer-helper behavior in that runner. Interactive installation, toolbars/dialogs, selection, grid labels, native Properties editing and save/reopen on the target Windows desktop still require [WINDOWS_ACCEPTANCE.md](../docs/WINDOWS_ACCEPTANCE.md). No FreeCAD binaries downloaded by CI are included in the source-only 3117 distribution.

The exchange stages require the pinned host to provide a compatible IfcOpenShell. An unavailable dependency fails the IFC acceptance stage rather than being counted as passed. Normal CSV functionality remains independent. Full EXPRESS validation and actual Bonsai/Blender application inspection are separate recorded QA activities, not implied by this headless workflow.

| Additional stage | Required report |
|---|---|
| types | types-test-report.json |
| types_reopen | types-reopen-test-report.json |
| types_exchange | types-exchange-test-report.json |
| types_exchange_reopen | types-exchange-reopen-test-report.json |
| schedules | schedules-test-report.json |
| schedules_reopen | schedules-reopen-test-report.json |

## v0.5.0 additive host stages

After the thirteen established stages, the runner executes `types`, `types_reopen`, `types_exchange`, `types_exchange_reopen`, `schedules` and `schedules_reopen` in six fresh host processes. Each stage must produce its own passing JSON report and process exit code; an old report cannot substitute for the invocation. The fresh-reopen stages consume their preceding lifecycle sample, so preserve order and one isolated installed profile. Material and schedule publication tests must write to a stable local filesystem, not a live synchronized folder that recreates deleted lock/staging files.

The source includes Linux/Windows CI definitions; only actually executed runs constitute evidence. Native GUI tests use the host's PySide/Qt and the public macros, separately from FreeCADCmd gates.
