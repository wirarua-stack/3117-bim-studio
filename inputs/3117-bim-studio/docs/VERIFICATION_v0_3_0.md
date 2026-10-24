# Verification record — v0.3.0 Building Authoring

Date: **2026-10-23**. Workbench: **0.3.0 development candidate**. Native schema: **1**. Independent reference package: **0.0.1**.

**Actual acceptance is on Linux FreeCAD 1.1.4 and Bonsai/Blender. Windows desktop acceptance remains pending.** Slab, Column, Beam, Window and explicit slab/member cuts use the existing native document, transactions, UUIDs, quantity snapshot and IFC4 pipeline. The delivered two-storey FCStd, six CSV tables and IFC share the same authored identity. The screenshots come from the actual applications.

## 1. Tested hosts and provenance

FreeCAD used the SHA-256-verified official Linux x86_64 AppImage (`f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`), build `4fd3bf320d9566a27e60069fc8387448aaa3a094`, embedded Python 3.11.14, Qt 6.8.3 and bundled IfcOpenShell 0.8.4. Tests installed the workbench into isolated FreeCAD user profiles. GUI runs used Xvfb and software rendering; production uses FreeCAD's own Qt/PySide, Coin/Pivy and OCCT.

Bonsai review ran in the actual Blender 4.5.14 LTS application, build `62c1db4208e8`, with Bonsai `0.9.0-post1-py311`, Python 3.11.15 and IfcOpenShell 0.9.0.post1. Runtime artifact hashes, environment versions and all report locations are recorded in [TEST_ENVIRONMENT.json](TEST_ENVIRONMENT.json). No application binaries are redistributed.

## 2. Final native and GUI gates

Counts below are **assertions within integration suites**, not independent unit-test counts or performance results. Repeated executions are not added together.

| Native stage, in its own FreeCADCmd process | Passed checks | Evidence |
|---|---:|---|
| Install source workbench into actual user add-on directory | 1 | [Install](evidence/v0.3.0/final-native/install-report.json) |
| Foundation Project / Levels / Grid | 35 | [Foundation](evidence/v0.3.0/final-native/foundation-test-report.json) |
| Foundation fresh headless restore | 9 | [Reopen](evidence/v0.3.0/final-native/reopen-test-report.json) |
| Existing WallType / Wall / Door / WallBody and compatibility | 63 | [Architecture](evidence/v0.3.0/final-native/architecture-test-report.json) |
| Architecture fresh headless restore | 12 | [Reopen](evidence/v0.3.0/final-native/architecture-reopen-test-report.json) |
| Existing snapshot / coverage / CSV / IFC exchange | 47 | [Exchange](evidence/v0.3.0/final-native/exchange-test-report.json) |
| Exchange fresh headless restore | 10 | [Reopen](evidence/v0.3.0/final-native/exchange-reopen-test-report.json) |
| Slab / Column / Beam / Window / cuts / history / quantities / IFC | **112** | [Building](evidence/v0.3.0/final-native/building-test-report.json) |
| Building fresh restore, edits, Undo and stable IFC IDs | **19** | [Reopen](evidence/v0.3.0/final-native/building-reopen-test-report.json) |

The nine-process gate uses one isolated profile and installed modules; fresh-process tests do not inject source workbench paths or pre-register proxies. Both process exit codes and individual JSON outcomes are required.

| Actual GUI stage | Passed checks | Evidence |
|---|---:|---|
| Building creation/edit forms, joins, quantities, native history | **35** | [Building GUI](evidence/v0.3.0/linux-building-gui-report.json) |
| Building fresh GUI restore | **12** | [GUI reopen](evidence/v0.3.0/linux-building-gui-reopen-report.json) |
| Frozen headless fixture receives GUI presentation | 14 | [Presentation](evidence/v0.3.0/linux-building-presentation-report.json) |
| Fresh GUI reopens that styled canonical file | 10 | [Presentation reopen](evidence/v0.3.0/linux-building-presentation-reopen-report.json) |
| Existing Architecture GUI | 43 | [Architecture GUI](evidence/v0.3.0/linux-architecture-gui-report.json) |
| Architecture fresh GUI restore | 16 | [Architecture reopen](evidence/v0.3.0/linux-architecture-gui-reopen-report.json) |
| Existing Exchange GUI | 41 | [Exchange GUI](evidence/v0.3.0/linux-exchange-gui-report.json) |
| Exchange fresh GUI restore | 10 | [Exchange reopen](evidence/v0.3.0/linux-exchange-gui-reopen-report.json) |

The [GUI manifest](evidence/v0.3.0/building-ui-verification.json) records **181 assertions across eight runs**, all 39 installed production payload hashes, seven participating GUI harness hashes and canonical presentation artifacts. The standalone GUI command fixture has 200 mm slabs and two front walls. It is distinct from the canonical 150 mm slab, eight-wall IFC example. Presentation capture used the final UI and preceded the last core history correction; its fresh-process reopen and the affected Building/Architecture/Exchange GUI suites used that final core correction.

## 3. Geometry and dependency contract

- **Slab:** one simple planar XY polygon, including concave polygons; Level + Offset is the top, Thickness extrudes down. Self-intersections, holes, duplicate/touching/backtracking edges and degenerate boundaries are rejected.
- **Column:** vertical rectangular prism, centered XY, Z rotation, Base/Top Level and offsets. Width/depth/height remain authored dimensions after joining.
- **Beam:** straight horizontal XY centerline with centered width; Level + Offset is the top and Depth extrudes down. Sloping and curved members are outside this release.
- **Window:** a real wall opening with a fixed four-bar frame. Overall width/height define the cut; sill is measured above the host wall base. Door remains a three-bar frame. There is no glazing, leaf, sash or operation model.
- **Join:** explicit Slab → Column/Beam subtraction. The slab keeps full volume; the member loses the union of selected cutters. UUID order makes repeated computation deterministic. New joins require overlap, and the result must be one connected positive solid. Split or fully removed members are rejected. A later non-overlapping cutter can remain linked with zero deduction. Unjoin restores geometry; deleting a referenced slab is blocked.

The native model remains acyclic and the only editable authority. New dimensions/materials are instance properties; existing shared WallType behavior is unchanged. Geometry can be inspected and edited through native FreeCAD objects after save/reopen. [BUILDING_AUTHORING.md](BUILDING_AUTHORING.md) specifies the API, units, links and limitations.

The 112-check Building suite covers concavity and winding, invalid bounds, explicit joins/unjoin, deletion guards, zero-overlap retained links, mixed Door/Window overlap and rehosting, real openings, actual Property edits, Undo/Redo, transient solid equivalence, spatial tampering, read-only quantities, old-file revision compatibility and independent expected volumes for all 33 exported products.

## 4. Transaction and Redo correction

Actual GUI testing exposed an important FreeCAD behavior: the first mutation in a new transaction clears an existing Redo stack; aborting that transaction does not restore Redo. Validation after mutation was therefore insufficient for rejected edits made immediately after Undo.

Door/Window create/edit/rehost, explicit join, Slab edits affecting joined members, and Column/Beam edits now validate proposed values and transient expected solids **before native mutation**. No alternate editable model, persistent preview objects or rewritten history is introduced. Native callbacks and final document validation remain in place.

The final Building suite adds 12 assertions for rejected proposals after Undo and actual replay of the retained Redo. A focused [native history report](evidence/v0.3.0/native-proposal-history-report.json) records 31 checks. In the actual Building GUI, a rejected mixed opening overlap preserved 19 Undo entries, 1 Redo entry, 32 objects, the exact content revision and the Window's host/offset. Successful commands remain one native transaction each. This evidence is scoped to the supported service proposals and exercised guards; it is not a guarantee that arbitrary raw native Property mutations preserve an earlier Redo chain.

Public test macros defer their harness until FreeCAD returns to its event loop so native Undo/Redo actions are enabled. The strict history assertions were retained.

## 5. Quantities, revisions and publication

There is one row per authored Wall, Door, Slab, Column, Beam or Window UUID. Derived WallBody objects never add quantity rows. Native mm are explicitly converted to SI. The UI has six read-only category tabs plus Coverage and follows committed document changes/Undo/Redo. Reading and exporting add no authored objects or Undo steps. Active native transactions block snapshot/export.

Scalar caches, bounds and bidirectional native solid differences are checked against transient expected geometry. Equal volume alone does not establish the correct opening or placement. The schema remains 1. Empty new category arrays are omitted from the revision-hash input so old v0.2.1 files retain the previous content hash. Revision is a SHA-256 content identity, not a monotonic edit or approval counter; Undo to identical authored state restores the same hash.

CSV uses UTF-8 with BOM, numeric SI cells and safe textual labels. The Wall table, Door sidecar and metadata remain present; Slab/Column/Beam/Window sidecars are emitted when those categories are nonempty. All six CSVs in the canonical example share the source revision. If a category later becomes empty, an older sidecar can remain on disk: the current metadata's file/hash list defines the current bundle.

Publication stages all destinations, locks overlapping paths, checks consent for every payload and sidecar, rechecks source revision and validates the written IFC. Replacement is atomic per file with metadata last and rollback for caught failures. It is **not crash-atomic across the whole bundle**. The nine publication unit tests retain the failure/rollback/stale-source/lock/symlink checks. Details: [QUANTITY_EXCHANGE.md](QUANTITY_EXCHANGE.md).

## 6. IFC4 readback and actual Bonsai review

The adapter extends the existing hierarchy, UUID-derived GlobalIds and source properties with IfcSlab(FLOOR), IfcColumn, IfcBeam and IfcWindow, category quantity sets, storey containment and instance material text. Slab/member cuts are actual `IfcBooleanResult` DIFFERENCE operations in the member's local coordinates. Windows use real opening/void/fill relationships and four-bar frames. No material layers or reusable types are invented for the new categories.

The delivered canonical IFC passes **186 normal serialized-file readback checks**, including counts, identities, relationships, profiles, cutters, placements, geometry, quantities and empty opening interiors. Full EXPRESS is explicitly recorded as `not_requested` by normal export.

A validation regression revealed an axis-aligned ray grazing a triangulated face edge and falsely reporting solid material in an empty opening. The adapter now uses oriented-triangle solid-angle containment. Regression fixtures cover orthogonal walls on two storeys, genuine positive material probes, exact empty probes and a moved-opening negative case.

The exact delivered IFC was then imported through Bonsai's real application operator. The [Bonsai report](evidence/v0.3.0/bonsai-building-report.json) records **266 passed checks**, including the inspected visible GUI capture, measurements of all 33 product meshes, world bounds, 16 slab cuts, six hosted openings, Window bottom bars and the absence of Door bottom bars. Full IFC schema/EXPRESS validation produced **zero findings**. The source IFC, snapshot and canonical native report remained byte-identical. See [BONSAI_BUILDING_REVIEW.md](BONSAI_BUILDING_REVIEW.md) for the portable harness and reproduction.

Bonsai uses IfcOpenShell, so this proves another application's import and separately measured Blender meshes, not a different IFC geometry kernel or every viewer. No Revit or IFC round-trip editing claim is made.

## 7. One coherent delivered building example

[examples/building](../examples/building/README.md) contains the styled FCStd, IFC, six CSVs, metadata, snapshot and actual FreeCAD/Bonsai screenshots. Levels are 0, 3 and 6 m. It is a synthetic software fixture, not a structural design or complete building layout.

| Category | Objects | Net volume under the declared rules |
|---|---:|---:|
| Slab, 29.25 m² each, 150 mm thick | 3 | **13.1625 m³** |
| Column, 300 × 300 mm, cut by upper slab | 8 | **2.0520 m³** |
| Beam, 300 × 450 mm gross, cut by slab | 8 | **3.6000 m³** |
| Wall, after real Door/Window cuts | 8 | **17.2680 m³** |
| Door, three-bar frame solids | 2 | **0.1000 m³** |
| Window, four-bar frame solids | 4 | **0.1840 m³** |

Coverage is 38 mapped objects, 8 derived WallBodies, 4 reference Grids and 0 unsupported objects. There are 33 product quantity rows. Grids are references and are not exported to IFC. Beam–Column and Wall–Wall overlaps are not deducted; these are per-element quantities under explicit rules, not a globally clash-free BOQ.

The canonical native generation [report](evidence/v0.3.0/linux-building-report.json) has **100 checks** and is deliberately frozen because Bonsai evidence references its exact hash. The final 112-check regression generated a separate fixture with different UUIDs/revision; its results are under `final-native/`. The canonical styled FCStd was freshly reopened on the final core and verified without changing its bytes or authored identity.

- Content revision: `6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a`
- Canonical IFC SHA-256: `775b5a63592d05c63c14fb63d258d6a30ae45558d6d6f244cf75f387279ac609`
- Styled FCStd SHA-256: `9a0e2efc3613747b2806ead5ecd61b6b74d757a229ca9ebc5e649afe28e68995`
- Original headless FCStd SHA-256: `a784c6303a5fb09eaae7cbe1a2a4f3854ccb7384ae9327c089aff11a7bc9897e`

The previous `examples/exchange` files and v0.2.1 deliverables were preserved. Their history is in [VERIFICATION_v0_2_1.md](VERIFICATION_v0_2_1.md).

## 8. Unit tests, local CI and exact distribution

| Independent Python suite | Result |
|---|---:|
| Reference model | 17 passed |
| Reference IFC | 4 passed |
| Native IFC adapter | 17 passed |
| Export publication | 9 passed |
| Installer | 8 passed |
| **Combined** | **55 passed, 0 skipped** |

The [combined report](evidence/v0.3.0/unit-test-report.json) used Python 3.12.14 and IfcOpenShell 0.9.0.post1. The 17 adapter tests also passed under host Python 3.11.14/IfcOpenShell 0.8.4, zero skips, with pytest available only through an isolated QA path: [host report](evidence/v0.3.0/host084-unit-report.json). Its synthetic adapter fixture passed 42 validation checks including full EXPRESS. The host/isolated reports additionally reproduce an earlier regression snapshot with 187 checks; that different revision is not substituted for the canonical 186-check IFC or its Bonsai review. The isolated 26-test adapter/publication rerun is a subset of the combined 55 and is not counted again.

Python/macros, XML version, three embedded CI Python blocks, relative documentation links, installed payload hashes and canonical payload/hash consistency are checked by the [final source gate](evidence/v0.3.0/final-source-gates.json). The nine-report CI validation block is executed locally against actual reports and exit codes. Linux/Windows workflows are prepared; no remote GitHub Actions run occurred.

The external companion **`3117_BIM_Studio_v0_3_0_Release_Verification.json`**, delivered next to the ZIPs, is authoritative for exact distribution results. It records the frozen ZIP hash, payload manifest, public installer and all four public test macros in fresh FreeCAD processes. Recording it outside the archive preserves the exact tested bytes. `MANIFEST.json` inside each ZIP hashes its payloads; the external checksum manifest identifies final archives and direct examples. This source record does not substitute earlier profile runs for the exact-package gate.

## 9. Reproduce and remaining scope

Extract the FreeCAD ZIP, run `Install_3117_BIM_Studio.FCMacro`, restart FreeCAD and activate **3117 BIM Studio**. Open `examples/building/Building_Authoring_Workbench.FCStd` or run `Run_3117_Building_Test.FCMacro` to exercise the actual UI on disposable test documents. Architecture, Exchange and Foundation macros remain available. See [INSTALL_TH.md](../packaging/INSTALL_TH.md).

Headless stages use `tests/run_freecad_tests.py` in separate FreeCADCmd processes, one isolated profile and one output directory, with `BIM3117_QA_STAGE=install|foundation|reopen|architecture|architecture_reopen|exchange|exchange_reopen|building|building_reopen`. See [CI_HOSTS.md](../packaging/CI_HOSTS.md). Fresh-process GUI harnesses use the preceding report directory and the installed workbench.

- **Windows acceptance is pending.** No Windows desktop, executable or PowerShell runner was executed. The expanded [Windows acceptance checklist](WINDOWS_ACCEPTANCE.md) must be completed on Windows before claiming support has passed.
- **GitHub work is local.** No remote repository was created/pushed and no remote Actions result is claimed.
- Outside v0.3.0: automatic general joins, sloping/curved members, Slab holes, roofs/stairs, additional shared types/families, glazing/leaf/swing behavior, mouse drawing/snapping, drawing views/sheets, full editable schedules, native IFC import, RVT/RFA and collaborative authoring.
- Untested: production-scale performance, power-loss recovery, arbitrary migrations and IFC applications other than the recorded Bonsai case.

This is a source-only development candidate with explicit geometry and exchange scope. It does not claim complete Revit parity or general production readiness.
