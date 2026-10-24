# Verification record — Quantity / Exchange Bridge

Date: 2026-10-23. Workbench: **0.2.1 development candidate**. Independent reference package: 0.0.1.

**Actual acceptance: FreeCAD 1.1.4 and Bonsai/Blender on Linux. Windows desktop acceptance remains pending.** Native quantities, CSV and IFC4 now read the same committed FreeCAD document. The delivered IFC was opened and inspected in the actual Bonsai application. The supplied FCStd is a GUI-styled copy of that same native fixture with unchanged UUIDs and content revision.

## 1. Runtime and provenance

The official FreeCAD Linux x86_64 AppImage was SHA-256 checked before execution: `f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`. Host build: `4fd3bf320d9566a27e60069fc8387448aaa3a094`; embedded Python 3.11.14; Qt 6.8.3; bundled IfcOpenShell 0.8.4. Tests used isolated user profiles; GUI runs used Xvfb and software rendering. Production uses the host's Qt/PySide, Coin/Pivy and OCCT.

Bonsai review used Blender 4.5.14 LTS, Bonsai `0.9.0-post1-py311`, Python 3.11.15 and IfcOpenShell 0.9.0.post1 in a separate isolated application profile. Verified official archive hashes and download sources are in [BONSAI_REVIEW.md](BONSAI_REVIEW.md) and the [environment manifest](TEST_ENVIRONMENT.json). No FreeCAD, Blender, Qt, Bonsai or IfcOpenShell binaries are bundled in the workbench distribution.

## 2. Real-host integration results

These numbers are **checks/assertions within integration suites**, not independent unit-test counts or a benchmark. Repeated runs of the same suite are not added together. Reports record individual outcomes and the actual host.

| Suite | Passed checks | Evidence |
|---|---:|---|
| Installation into FreeCAD's actual user add-on directory | 1 | [Install](evidence/v0.2.1/linux-install-report.json) |
| Native snapshot, revisions, coverage, CSV and IFC4 export | **47** | [Exchange](evidence/v0.2.1/linux-exchange-report.json) |
| Fresh headless process restores and re-exports with stable IDs | **10** | [Exchange reopen](evidence/v0.2.1/linux-exchange-reopen-report.json) |
| Actual quantity forms, edits/Undo, stale states, coverage and export dialogs | **41** | [Exchange GUI](evidence/v0.2.1/linux-exchange-gui-report.json) |
| Fresh GUI restores proxies and a current quantity table | **10** | [Exchange GUI reopen](evidence/v0.2.1/linux-exchange-gui-reopen-report.json) |
| Headless-created fixture receives GUI presentation without changing model content | **14** | [Headless to GUI](evidence/v0.2.1/linux-headless-gui-report.json) |
| Fresh GUI opens that exact styled FCStd and checks identity/quantities | **10** | [Styled sample reopen](evidence/v0.2.1/linux-headless-gui-reopen-report.json) |
| Native WallType/Wall/Door/WallBody and Foundation-file compatibility regression | **63** | [Architecture](evidence/v0.2.1/linux-architecture-report.json) |
| Architecture fresh headless process | **12** | [Architecture reopen](evidence/v0.2.1/linux-architecture-reopen-report.json) |
| Architecture GUI commands, openings, visibility and transactions | **43** | [Architecture GUI](evidence/v0.2.1/linux-architecture-gui-report.json) |
| Architecture fresh GUI process | **16** | [Architecture GUI reopen](evidence/v0.2.1/linux-architecture-gui-reopen-report.json) |
| Foundation Project/Level/Grid regression | **35** | [Foundation](evidence/v0.2.1/linux-foundation-report.json) |
| Foundation fresh headless process | **9** | [Foundation reopen](evidence/v0.2.1/linux-foundation-reopen-report.json) |
| Bonsai import, real Blender meshes, metadata, opening probes and full EXPRESS | **41** | [Bonsai report](evidence/v0.2.1/bonsai-application-report.json) |
| Same Bonsai review including inspected visible GUI capture | **42 total** | [Actual screenshot](../examples/exchange/Bonsai_Native_IFC_Review.png) |

The native gate ran in **seven separate FreeCADCmd processes** with one isolated profile: install → foundation → reopen → architecture → architecture_reopen → exchange → exchange_reopen. Source workbench paths were not injected into `sys.path`; fresh-process tests restore installed proxies normally. The repeat gate's exchange reports have their own fixture UUIDs: [CI gate exchange](evidence/v0.2.1/ci-gate-exchange-test-report.json) and [CI gate reopen](evidence/v0.2.1/ci-gate-exchange-reopen-test-report.json). They do not replace the canonical fixture reviewed in Bonsai.

The [native manifest](evidence/v0.2.1/native-tested-source-manifest.json) and [GUI manifest](evidence/v0.2.1/gui-tested-source-manifest.json) hash the tested installed modules. The final narrow visibility correction was followed by the affected Architecture and Exchange GUI suites and their fresh-process checks.

Foundation GUI 24/9 and installer GUI 4 reports stored under v0.2.0 are **historical**. See [the preserved v0.2.0 record](VERIFICATION_v0_2_0.md). Any public-macro runs from the final v0.2.1 ZIP are recorded separately in the external release-verification companion described below, with the exact archive hash; prior reports are not relabelled as new results.

## 3. Quantities, revisions and geometry

Snapshots contain one row per authored Wall/Door UUID. Derived WallBody objects supply geometry but never add quantity rows. Native millimetres are converted explicitly to metres, m² and m³. Net wall volume comes from the actual cut `WallBody.Shape.Volume`.

The 6000 × 3000 × 200 mm wall with a 900 × 2100 mm overall opening gives 3.600 m³ gross, 0.378 m³ deduction and **3.222 m³ net**. Raising its top level to 3300 mm gives **3.582 m³**; Undo restores geometry and the original content hash. The suite restores baseline before publishing the canonical example.

| Risk | Verified behavior |
|---|---|
| Reading midway through an edit | Active/pending native transactions block snapshot/export. |
| Polluting history while reading | Quantities, exports and GUI refresh create no authored objects or extra Undo entries. |
| Same names or renaming | UUIDs identify rows, links and IFC GlobalIds. |
| Plausible dimensions with stale shapes | Scalar caches, bounds and bidirectional solid differences are checked against transient expected OCCT solids. |
| Shifted solid or moved hole with unchanged volume | Spatial verification rejects the inconsistent shape; equal volume alone is insufficient. |
| Invalid authored references | Duplicate IDs, missing links, unsupported project children and invalid definitions are rejected. |
| Objects outside supported export scope | Coverage explicitly lists mapped, derived, reference and unsupported entries. |
| Source changes during export | Revision checks and final recapture reject publication from stale content. |

Revision is a **SHA-256 content identity**, not a monotonic edit counter or CDE approval revision. Undo to the identical authored state can return the same hash. Capture time, source path, view styling and floating derived caches are excluded. Authored properties, IDs, links and coverage inventory are included. Unsupported foreign geometry is neither exported nor tracked as supported model geometry.

## 4. CSV and file publication

CSV uses UTF-8 with BOM, SI column suffixes, numeric cells and separate Wall/Door tables. Formula-like text labels are protected in CSV while metadata retains their original text. CSV and IFC have separate metadata sidecar names.

Export locks cover **every destination**, including sidecars. Existing files require explicit overwrite consent; links and directories are rejected. Outputs are staged, the source revision is checked again, and IFC is reopened and validated before success.

Publication is atomic **per file**, with backups and rollback on caught failures. Metadata is published last with payload hashes. Nine unit tests cover order, stale-source rejection, sidecar consent, writer failure, partial replacement, rollback, overlapping locks, owned locks and symlinks. This is not a crash-atomic multi-file transaction: a process/OS failure may leave recovery files. If restoration itself fails, backups/locks are retained and their location reported. No power-loss recovery claim is made.

## 5. IFC4 and actual Bonsai review

The native adapter writes Project/Site/Building/Storey hierarchy, shared IfcWallType, wall solids, base-level containment, IfcOpeningElement/RelVoidsElement, generic IfcDoor frames/RelFillsElement, stable GlobalIds, source UUID/revision properties and wall quantities. Material text is associated with the type; layers are not invented. Diagonal/reversed axes, negative levels and offsets are tested.

The canonical written-file readback passed **37 checks** for schema, identities, counts, relationships, placements, geometry, quantities and opening interiors. Normal export explicitly records full EXPRESS as `not_requested`; it does not silently claim that separate gate passed.

The same IFC bytes were then imported through Bonsai's real application operator. Blender triangle measurements and ray probes verified imported solids, frames and empty openings. Full schema/EXPRESS validation in that runtime produced **zero findings**. The 42-check report includes 41 application/geometry/schema checks plus a separately inspected visible capture. An initial black image was rejected; the delivered PNG shows the actual application framebuffer.

Bonsai uses IfcOpenShell. This establishes another application's import with separately measured Blender geometry, not every viewer or a different IFC geometry kernel. Revit, IFC import back into 3117, round-trip editing and georeferenced exchange remain outside this evidence.

## 6. One coherent delivered example

[examples/exchange](../examples/exchange/README.md) contains FCStd, IFC, both CSVs, both metadata files, snapshot and actual FreeCAD/Bonsai screenshots. The GUI-styled FCStd preserves authored UUIDs and revision; the original headless source was left byte-identical.

| Wall | Length | Height | Thickness | Opening | Net volume |
|---|---:|---:|---:|---|---:|
| W201, horizontal | 6.000 m | 3.000 m | 0.200 m | 0.90 × 2.10 m | **3.222 m³** |
| Diagonal basement | 5.000 m | 2.700 m | 0.200 m | 0.80 × 2.00 m; sill 0.10 m | **2.380 m³** |
| Reversed wall | 4.000 m | 3.000 m | 0.200 m | 0.80 × 2.10 m | **2.064 m³** |
| **Per-wall sum** | | | | **3 doors** | **7.666 m³** |

Levels: B01 = -3 m, L00 = 0 m, L01 = 3 m. Single-side gross area totals 43.500 m² and net area 38.330 m². Coverage contains 11 mapped, 3 derived, 1 reference and 0 unsupported entries. Grid A is explicitly omitted from IFC; bodies do not duplicate walls. Coverage is therefore not labelled complete.

Content revision: `31b79c638cc70358bb6d8fa92005a1922ca7fd248332650582ce19d636da6cf0`

IFC SHA-256: `a62ab703c0170ba9134d0c81ae0ba7932ab04d6ff7da6e44fc6fb01a005aac25`

These are independent straight uniform walls, with no join/overlap deduction, layer BOQ or pricing. Door Width/Height describe the overall cut including the three-sided frame, not a leaf or clear passage. FCStd remains the editable authority; JSON/CSV/IFC are outputs.

The GUI command harness intentionally makes an older IFC followed by a newer CSV/model to test stale warnings. Its one-wall output is **not** the synchronized three-wall example delivered here.

## 7. GUI corrections

An empty aborted FreeCAD transaction can omit the observer event originally expected by the table. Refresh now reconciles actual pending/global transaction state and polls only while a transaction is active. The table recovers without modifying history; observers are removed when it or its document closes.

A headless-saved Wall can restore with a native DisplayMode enumeration missing scripted `Default`. The narrow fix initializes the existing enumeration from registered modes before selecting Default, preserving the native property type and normal GUI path. Targeted checks cover first hide/show, child visibility, repeated attach without duplicate Coin nodes, unchanged IDs/revision/history and fresh reopen of the delivered styled copy.

Testing the actual public Exchange macro from a fresh profile exposed a separate entry-point issue: FreeCAD disables the native Undo action while the macro is synchronously executing. The model correctly remained at its edited state, and the strict native Undo assertion caught this. Public test macros defer their harness invocation until control returns to the host event loop. The native Undo assertions remain unchanged; the external package report records the affected entry-point checks on the final ZIP.

## 8. Unit tests, local CI gate and distribution evidence

| Independent Python suite | Result |
|---|---:|
| Reference model | 17 passed |
| Reference IFC | 4 passed |
| Native IFC adapter | 9 passed |
| Export publication | 9 passed |
| Installer | 8 passed |
| **Combined** | **47 passed, 0 skipped** |

The [combined unit run](evidence/v0.2.1/unit-test-report.json) used Python 3.12.14 and IfcOpenShell 0.9.0.post1. The nine native adapter tests also passed under host Python/IfcOpenShell 0.8.4, with no skips: [host adapter result](evidence/v0.2.1/ifc-host-adapter-unit-report.json). Its synthetic fixture passed 19 validation checks including full EXPRESS using pytest from an isolated QA path. That synthetic fixture is separate from the native demonstration.

All repository Python/macros and three embedded workflow Python blocks were syntax-checked. The seven-report CI gate was executed locally against actual report files and process exit codes: [source gate report](evidence/v0.2.1/final-source-gates.json). Linux/Windows workflows are prepared; **no remote GitHub workflow ran**.

The companion `3117_BIM_Studio_v0_2_1_Release_Verification.json`, delivered next to the ZIPs, records installation and public Exchange macro execution from the exact distribution ZIP and its hash. It is outside the tested archive so recording results cannot alter tested bytes. `MANIFEST.json` inside the installer ZIP hashes all payloads; the companion SHA-256 file identifies final archives and direct examples.

## 9. Reproduce and remaining scope

Run the extracted `Install_3117_BIM_Studio.FCMacro`, restart FreeCAD and activate **3117 BIM Studio**. `Run_3117_Exchange_Test.FCMacro` exercises the actual quantity/export UI and shows its report directory. It creates disposable test documents, without editing existing user models. Architecture and Foundation macros remain available. Fresh-process GUI harnesses run in a newly started FreeCAD process against the preceding report directory.

For headless tests, use `tests/run_freecad_tests.py` in separate FreeCADCmd processes with `BIM3117_QA_STAGE=install|foundation|reopen|architecture|architecture_reopen|exchange|exchange_reopen`, one isolated profile and one `BIM3117_QA_OUTPUT` directory. See [CI_HOSTS.md](../packaging/CI_HOSTS.md). [BONSAI_REVIEW.md](BONSAI_REVIEW.md) gives portable application review and the separate screenshot inspection requirement.

- **Windows remains unexecuted.** No Windows desktop, executable or PowerShell runner was used. Complete [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md) on Windows before claiming a pass.
- **GitHub is prepared locally.** No remote repository was created/pushed and no remote Actions result is claimed.
- Unimplemented: mouse drawing/snapping, wall joins/layers, Door Type/Family/leaf/handing/swing, additional categories, drawing views/sheets, full editable schedules, native IFC import, RVT/RFA and multiuser authoring.
- Untested: production-size performance, OS crash recovery, arbitrary migrations and IFC applications other than the recorded Bonsai case.

This release establishes the declared native model → quantities → CSV/IFC workflow on the tested Linux runtimes. It remains a development candidate without a claim of complete BIM/Revit parity or general production readiness.
