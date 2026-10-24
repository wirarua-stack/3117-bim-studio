# Verification record — Walls and Hosted Doors

Date: 2026-10-23. Workbench: **0.2.0 development candidate**. Independent reference package: 0.0.1.

**Actual runtime: FreeCAD 1.1.4 on Linux. Windows desktop acceptance: pending.**

The official Linux x86_64 AppImage was SHA-256 checked before execution. Host build: `4fd3bf320d9566a27e60069fc8387448aaa3a094`; embedded Python 3.11.14; Qt 6.8.3. GUI tests used an isolated user profile, Xvfb and software rendering. The workbench uses the host's Qt/PySide and Coin/Pivy; no second UI runtime or geometry engine was installed into FreeCAD.

## 1. Current native and GUI results

Counts below are **assertions/checks within real-host integration suites**, not counts of independent unit tests or a performance benchmark. Reports contain each assertion and the actual runtime.

| Suite | Result | Evidence |
|---|---:|---|
| Install into the user add-on directory returned by FreeCAD | 1 passed | [Install report](evidence/v0.2.0/linux-install-report.json) |
| Native WallType/Wall/Door/WallBody, actual boolean cuts, type/level/host edits, rollback, native Properties, deletion, Undo/Redo and v0.1 compatibility | **63 passed** | [Architecture report](evidence/v0.2.0/linux-architecture-report.json) |
| Fresh headless process restores the installed model proxies, IDs and dependencies, then edits and uses Undo | **12 passed** | [Architecture reopen report](evidence/v0.2.0/linux-architecture-reopen-report.json) |
| Actual command forms, selecting/editing a wall through its solid, hosted opening changes, rejected edits, native Delete veto, controlled deletion and visibility | **43 passed** | [Architecture GUI report](evidence/v0.2.0/linux-architecture-gui-report.json) |
| Fresh GUI process restores model/view proxies, geometry, labels, visibility and dependency edits; repeated attach does not duplicate scene nodes | **16 passed** | [Architecture GUI reopen report](evidence/v0.2.0/linux-architecture-gui-reopen-report.json) |
| Foundation Project/Level/Grid regression | **35 passed** | [Foundation report](evidence/v0.2.0/linux-foundation-report.json) |
| Foundation fresh headless process | **9 passed** | [Foundation reopen report](evidence/v0.2.0/linux-reopen-report.json) |
| Foundation installed GUI commands, labels, history, save/reopen and deletion guards | **24 passed** | [Foundation GUI report](evidence/v0.2.0/linux-foundation-gui-report.json) |
| Foundation fresh GUI process restores proxies and grid labels | **9 passed** | [Foundation GUI reopen report](evidence/v0.2.0/linux-foundation-gui-reopen-report.json) |
| Actual installation macro dialogs, receipt and retained upgrade backup | **4 passed** | [Installer GUI report](evidence/v0.2.0/linux-installer-gui-report.json) |

Native host tests ran as five separate processes using the same isolated profile: install → foundation → reopen → architecture → architecture_reopen. The source workbench directory was not injected into `sys.path`. Fresh-process suites open their saved native file before preregistering proxy classes, so the restore loader must import the installed add-on normally.

The [native implementation manifest](evidence/v0.2.0/native-tested-source-manifest.json) matches all current model/service modules to the tested installation. The [GUI implementation manifest](evidence/v0.2.0/tested-implementation-manifest.json) records the installed implementation hashes and test harness hashes. Foundation GUI regressions ran before the final correction restricted to the new Wall/Body/Door visibility providers; the affected Wall/Door GUI suites and installer were then rerun successfully.

Earlier v0.1 reports remain in the parent evidence directory as historical evidence. They are not substituted for the current reports linked above.

## 2. Geometry and numeric verification

The native suite creates a uniform straight wall **6000 × 3000 × 200 mm** and a rectangular overall wall-cut opening **900 × 2100 mm**. Door Width/Height define that overall cut, including the area occupied by the generic display frame; they are not a leaf or clear-passage size.

| Quantity | Independently expected value | Verified observation |
|---|---:|---|
| Gross side area | 18.000 m² | Native calculated output |
| Opening side area | 1.890 m² | Opening definition |
| Net side area | 16.110 m² | Native calculated output |
| Gross volume | 3.600 m³ | OCCT uncut solid |
| Opening deduction | 0.378 m³ | Difference of actual solids |
| Net volume | **3.222 m³** | Actual cut Shape.Volume |
| Net volume after top level becomes 3300 mm | **3.582 m³** | Recomputed actual cut Shape.Volume |

Independent small-solid intersection probes verify that the opening is empty through the wall thickness, while jamb-side and head material remain. The suite also checks diagonal and reversed axes, signed basement elevations and offsets, moving a wall with its door/frame, shared-type propagation, assigning a different type to only one instance, resizing/rehosting a door, multiple openings and invalid overlap/bounds rejection.

These are per-wall quantities for straight uniform solids. There are no wall joins, material-layer deductions, finish rules, cost calculations, or aggregate building BOQ claims. A `WallBody` is derived geometry for one authored Wall and must not be counted as an additional wall.

## 3. Transaction and visibility findings

Services validate the complete final state in one native transaction. Parameter callbacks do not open nested transactions. Invalid downstream changes such as lowering the top level below a hosted door roll back the level and all dependent solids. Door rehosting heals the former wall and cuts the destination wall atomically; controlled deletion and Undo/Redo preserve stable identities.

A test initially assumed that a new transaction always increases `UndoCount`. The actual isolated host's history was already at its 20-entry capacity: deletion correctly healed the wall and replaced the oldest undo entry while the count remained 20. The independent deletion scenario now clears only its disposable test document history before asserting one new entry. User preferences and production history behavior were not changed. The report records the prior count, and all deletion Undo/Redo geometry and identity checks remain strict.

Actual GUI inspection found that a shapeless authored Wall had `Visibility=True` while the native view reported `isVisible()=False`, because it had no display mode. The final provider registers an empty native Coin display mode, allowing the first Space-key-equivalent toggle to hide its body and doors correctly. Newly created doors inherit a hidden host's visibility; reopening preserves independently hidden door states. Repeated attach is explicitly tested for duplicate scene nodes.

Final GUI logs contain only deliberately triggered invalid-edit/overlap messages and deletion-policy warnings. Native tests intentionally exercise invalid numeric values and raw missing-reference deletion. Those diagnostic messages are expected; their assertions verify rollback or cleared invalid geometry.

## 4. Native examples and backward compatibility

The [Architecture native sample](../examples/freecad/Architecture_Workbench.FCStd) and [actual FreeCAD screenshot](../examples/freecad/Architecture_Workbench.png) come from the installed GUI command suite. The final demonstration state has:

- One Project, two Levels at 0 and 3300 mm and two labelled Grid axes.
- One shared 250 mm uniform Wall Type.
- Two independent walls, 6000 mm and 4000 mm long.
- Two hosted openings, 900 × 2100 mm and 800 × 2100 mm.
- Net wall volumes **4.4775 m³** and **2.8800 m³** after the type and level edits.

The two demonstration walls are independent and unjoined. The smaller 3.222 m³ acceptance fixture above is tested separately; it is not the final screenshot state's quantity.

The original [Foundation v0.1 sample](../examples/freecad/Foundation_Workbench.FCStd) remains unchanged. The current native suite independently reads its saved UUIDs from `Document.xml`, opens it with v0.2, verifies all IDs and original creation versions, and tests a linked Level/Grid edit and Undo. This proves the tested Foundation compatibility case, not a general migration system.

Save/reopen uses Thai directory names. Compatible model/view code must remain installed because `.FCStd` stores native properties and proxy references rather than the complete add-on source.

## 5. Installer and reference-core regression

| Independent Python suite | Result | Scope |
|---|---:|---|
| Installer unit tests | **8 passed** | First install, upgrade, backup, failed promotion recovery, uninstall/restore, ownership/links/lock/path controls |
| Reference model unit tests | **17 passed** | Separate metre-based rules, fixture persistence and in-memory history |
| Reference IFC integration tests | **4 passed** | IFC4 validation, relationships/units, boolean geometry and stable IDs in the independent fixture exporter |
| Combined reference suite | **21 passed, 0 skipped** | Python 3.12.14, IfcOpenShell 0.9.0.post1 |

See [unit-test evidence](evidence/v0.2.0/unit-test-report.json) and [environment manifest](TEST_ENVIRONMENT.json). The IfcOpenShell EXPRESS executor emitted an upstream ResourceWarning for an unclosed source file; validation completed and passed. These reference tests do not establish native Workbench IFC export or cross-application interoperability.

Python source/macros and prepared workflow Python blocks were parsed successfully. The updated five-report CI JSON gate was executed locally against the final native reports and exit-code records. This checks the gate logic with real local evidence; it is not a remote GitHub execution.

## 6. Windows, GitHub and remaining scope

- **No Windows executable, Windows desktop session or PowerShell runner was executed.** Windows remains pending under [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md).
- The source-only installer targets a separately installed FreeCAD 1.1.4. Its Windows path comes from the host; FreeCAD/Qt binaries are not bundled.
- Linux/Windows GitHub Actions definitions and official artifact checksum pins are prepared. **No remote repository was created or pushed, and no remote workflow was run.**
- Unimplemented: mouse drawing/snapping, wall joins, material layers, Door Type/Family/leaf/handing/swing, other building categories, native quantity rows/CSV, live schedules, drawing views/sheets and native IFC export.
- Unexecuted: separate-application IFC review, production-size performance, crash recovery, arbitrary schema migration and multiuser authoring.

The current results establish the declared Wall/Door authoring slice on the tested Linux host; they do not establish full BIM/Revit parity or production readiness.

## 7. Reproduce

Install the supplied workbench and restart FreeCAD. Execute `Run_3117_Architecture_Test.FCMacro` from the extracted package for actual Wall/Door GUI checks; `Run_3117_Smoke_Test.FCMacro` exercises Foundation. Each creates its own documents and writes reports to the directory shown in its final dialog without editing existing user model documents.

In a new GUI process, call `freecad_architecture_gui_reopen.main(report_directory)` after the Architecture GUI suite. The Foundation counterpart is `freecad_gui_reopen.main(report_directory)`.

For headless verification, invoke `tests/run_freecad_tests.py` in separate FreeCADCmd processes with `BIM3117_QA_STAGE=install|foundation|reopen|architecture|architecture_reopen` and one `BIM3117_QA_OUTPUT` directory/profile. The downloaded-host launch contract is in `.github/workflows/freecad-host.yml` in the source repository; [CI_HOSTS.md](../packaging/CI_HOSTS.md) is included in the installer package.

Independent reference regression:

```bash
python -m pip install -e ".[ifc,test]"
python -m unittest discover -s tests -v
```
