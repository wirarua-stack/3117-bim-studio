# Verification record — v0.5.0 Types and Quantities

Date: **2026-10-23**. Workbench: **0.5.0 development candidate**. Native / Drawing / Schedule schema: **1**. Independent reference package: **0.0.1**.

**Release status: blocked for Pilot/production.** The tested Linux FreeCAD 1.1.4 GUI host crashes on create/delete/two-Undo/new-edit/Undo/Redo, including a native-only reproduction with ordinary Part::Feature and no addon. **Windows desktop acceptance is pending.** Passing feature, persistence, quantity, IFC and packaging evidence below does not resolve this separate history-branch gate. Read [HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md) before experimenting with the candidate.

This candidate implements native shared Types, Materials/layers, model-derived material quantities, persistent Schedules and guarded source-row editing. The user/API guide is [TYPES_AND_QUANTITIES.md](TYPES_AND_QUANTITIES.md). [TEST_ENVIRONMENT.json](TEST_ENVIRONMENT.json) records the exact evidence hashes and qualifications.

## 1. Runtime and provenance

The official FreeCAD 1.1.4 Linux x86_64 AppImage has SHA-256 `f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`; its source revision is `4fd3bf320d9566a27e60069fc8387448aaa3a094`. It uses Python 3.11.14, Qt 6.8.3 and IfcOpenShell 0.8.4. Workbench tests load the installed files from isolated user profiles. Actual GUI evidence uses Xvfb/software rendering; native production geometry remains OCCT.

Independent tests use Python 3.12.14, IfcOpenShell 0.9.0.post1 and pytest 9.1.1. The separate application review uses Blender 4.5.14 LTS, Bonsai 0.9.0-post1-py311, IfcOpenShell 0.9.0.post1 and Python 3.11.15. No alternate Qt runtime is injected into FreeCAD. Host/application binaries are not bundled.

## 2. Native regression gate

Each stage runs in a **separate installed FreeCADCmd process**. Counts are assertions inside integration suites, not independent unit tests, unique user operations or performance measurements. Successful repetitions are counted once.

| Stage | Passed checks | Evidence |
|---|---:|---|
| Install | 1 | [Report](evidence/v0.5.0/final-native/install-report.json) |
| Project / Levels / Grid | 35 | [Report](evidence/v0.5.0/final-native/foundation-test-report.json) |
| Foundation fresh restore | 9 | [Report](evidence/v0.5.0/final-native/reopen-test-report.json) |
| Wall / Door / WallBody | 63 | [Report](evidence/v0.5.0/final-native/architecture-test-report.json) |
| Architecture fresh restore | 12 | [Report](evidence/v0.5.0/final-native/architecture-reopen-test-report.json) |
| Snapshot / CSV / IFC | 47 | [Report](evidence/v0.5.0/final-native/exchange-test-report.json) |
| Exchange fresh restore | 10 | [Report](evidence/v0.5.0/final-native/exchange-reopen-test-report.json) |
| Building authoring / joins / history | 112 | [Report](evidence/v0.5.0/final-native/building-test-report.json) |
| Building fresh restore | 19 | [Report](evidence/v0.5.0/final-native/building-reopen-test-report.json) |
| OCCT drawing geometry | 31 | [Report](evidence/v0.5.0/final-native/drawing-geometry-test-report.json) |
| Native View / Sheet definitions | 70 | [Report](evidence/v0.5.0/final-native/drawings-test-report.json) |
| Drawings fresh restore | 25 | [Report](evidence/v0.5.0/final-native/drawings-reopen-test-report.json) |
| Sheet layout / SVG / publication | 33 | [Report](evidence/v0.5.0/final-native/drawing-render-test-report.json) |
| Native catalogue / propagation / preflight | 54 | [Report](evidence/v0.5.0/final-native/types-test-report.json) |
| Types fresh restore | 21 | [Report](evidence/v0.5.0/final-native/types-reopen-test-report.json) |
| Native type/material exchange | 37 | [Report](evidence/v0.5.0/final-native/types-exchange-test-report.json) |
| Type/material exchange fresh restore | 7 | [Report](evidence/v0.5.0/final-native/types-exchange-reopen-test-report.json) |
| Persistent schedules / source edit / guarded CSV | 49 | [Report](evidence/v0.5.0/final-native/schedules-test-report.json) |
| Schedules fresh restore | 16 | [Report](evidence/v0.5.0/final-native/schedules-reopen-test-report.json) |
| **Total, nineteen processes** | **651** | [Process manifest](evidence/v0.5.0/final-native/native-process-manifest.json) |

Each process exited successfully and produced its expected passed JSON report. Installed native production files remained unchanged throughout this gate. All native production Python files still match those hashes in the final candidate. After the gate, only the UI reader observer correction and Workbench README changed; the environment manifest records both old and final hashes. The final UI has its own installed-host evidence. The earlier full-workbench fingerprint is not relabelled as a final all-files run.

The source repository contains matching nineteen-stage CI report maps and the installed-host runner. No remote GitHub Actions execution is claimed.

## 3. Catalogue and material contract

Material and ElementType objects have native UUIDs, names and optional unique nonempty codes. WallType is retained; Slab, Column, Beam, Door and Window can use ElementType. Type-controlled dimensions are derived read-only caches on an instance; geometry resolves its actual linked Type. Untyped legacy elements retain their editable dimensions. Detaching supported non-wall instances retains their dimensions and material description without inventing a native material assignment.

Accepted shared edits use one native transaction after full proposed-state validation. Validation evaluates every changing opening and Slab cutter together, including combinations that would only become invalid after simultaneous updates. Invalid supported proposals preserve the existing Redo branch. Native command-line tests cover ordinary Undo/Redo, identity and geometry restoration; the separately documented GUI history-branch crash remains failed.

Wall layers grow from local Y=0 towards +Y; Slab layers run from the top down. Layer thicknesses sum to total Type thickness. Material quantities intersect actual gross and net native solids with each layer band and require conservation back to the parent product. They reflect Door/Window openings and the bounded Slab/member joins already in the model. No additional persistent product or cached material-solid object is authored.

Coverage distinguishes assigned and unassigned products. Legacy free-text material descriptions do not become native assignments automatically. Material rows partition building-product quantities and must never be added to them again. The model supplies no prices, densities, waste factors, labor or complete construction BOQ. Door/Window quantities cover the implemented frames; panels and glazing are not fabricated.

## 4. Persistent schedules and source edits

ScheduleSet and Schedule are native definitions outside Project.Group. They persist their UUIDs, category, Level/Type/name filters, sorting and grouping. Rows are fresh projections of the native model rather than another editable master. Broken filter links retain their expected UUIDs and block that Schedule instead of silently broadening its scope.

Schedules support the six building categories and Material; grouping is by Type or Material within the supported category rules. Grouped rows retain every source UUID. Source counts are distinct products, while material layer-row counts are reported separately. Summation uses additive quantities only. A grouped-row edit selects one concrete source UUID and changes its supported properties through one native transaction.

The building content revision and Schedule definition revision are separate hashes. Both are checked for row edits and CSV publication. A staged edit or export is rejected if either changed. CSV uses UTF-8 BOM, spreadsheet-formula escaping, explicit units/identities and companion metadata with both revisions and payload hashes. Publication uses per-file atomic replacement and rollback for caught failures; it is not a crash-atomic multi-file transaction.

The focused schedule fixture independently checks a 3.6 m³ gross Wall, 0.378 m³ opening deduction and 3.222 m³ net Wall; a 12 m² / 2.4 m³ Slab; and 5.622 m³ assigned net material with four assigned products, six layer rows and one explicitly unassigned Door. Its 49 native and 16 fresh-process checks include stale definitions, raw deleted filters, repair, dependency guards and failed-publication preservation.

## 5. Actual GUI evidence and the failed host gate

| Current evidence | Result | Evidence |
|---|---:|---|
| Final installed UI, fresh FCStd process, isolated feature cases | **27 passed** | [Fresh GUI report](evidence/v0.5.0/types-gui-reopen-report.json) |
| Canonical model, Type/Material catalogue and Schedule presentation | **6 passed, five screenshots** | [Presentation report](evidence/v0.5.0/types-presentation-report.json) |
| Original combined material-history branch sequence | **Failed: SIGSEGV** | [Original regression](evidence/v0.5.0/host-history-branch/ui/regression-report.json) |
| Native-only FeaturePython and Part::Feature branch sequences | **Failed: SIGSEGV** | [Native blocker report](evidence/v0.5.0/host-history-branch/host-blocker-report.json) |

The final fresh feature run checks restored providers/filters, staged source edits, native type edits/Undo/Redo, material duplication/deletion/Undo, dependent deletion guards and document/observer cleanup. All 45 installed UI source/icon hashes match the final tree. The public Types macro contains 52 checks and leaves a successful sample open; its actual execution is recorded only in the post-freeze distribution companion.

A separate Workbench issue caused Schedules and Quantities to invalidate each other repeatedly when read-only captures called recompute. The observer correction preserves real-change and history refresh while ignoring redundant clean-reader recomputes. Actual simultaneous-panel tests verify that both readers settle and show the same revision after edit, Undo and Redo.

The combined create/delete/two-Undo/new-branch case is not hidden by isolated feature successes. Its original exact harness/helper, fixture and failure log are preserved. The native reproduction has no addon, custom proxy, restored file, modeless reader or second document. A 500 ms return to the main event loop after each step still crashes; an ordinary non-Python Part::Feature also crashes. The unbranched Undo/Undo/Redo/Redo control passes. No safe public-API workaround was established; Undo history was not cleared and host binaries were not patched.

The [official-source analysis](evidence/v0.5.0/host-history-branch/source-review/FREECAD_HISTORY_BRANCH_SOURCE_REVIEW.md) explains the deferred provider ownership path and checks a pinned upstream main revision. An included patch direction is explicitly **unapplied and untested**. No upstream issue has been posted. Other hosts and Windows are not inferred safe or broken from this Linux evidence.

Types GUI feature reports therefore contain `host_history_branch_gate: failed_native_host` and `overall_release_ready: false`. The crashing process has no completed-check count. Do not treat the raw unfinished progress JSON or an older report in the same output directory as a pass.

## 6. Canonical example and independent exchange

[examples/types](../examples/types/README.md) contains the native model, IFC, eight category/type/material CSV payloads, nine Schedule CSVs, their metadata, native snapshot, creation report and actual GUI screenshots. It has **79 objects**, including **33 products, 6 Types, 7 Materials, 55 material rows, 9 Schedules, 4 Views and 2 Sheets**.

The builder passed **41 checks**. All 57 original v0.4.0 UUIDs are retained. All 33 existing product solids preserve their bidirectional geometric difference below 0.001 mm³. View/Sheet definitions and drawing revisions remain unchanged. The new catalogue changes the building content revision as expected. Historical PDF/SVGs retain their original building revision; export drawings anew from the typed FCStd when current metadata is needed.

| Identity | Value |
|---|---|
| Native FCStd SHA-256 | `ab308e5e7b20acfa2738e7cb21d24e519fa4b65d8ad8b55f81e6931c75bd6843` |
| Model content revision | `b1d7558505e38e8eab14517490e580a875eba1bb7b5503b72d140c259384c804` |
| IFC SHA-256 | `5069ee9e77bf618be30020537b1287b4c7137b5989c69961f35f1b73896aa031` |

All 33 products have explicit native material assignment in this synthetic example. Its material gross volume is **40.1825 m³**, deduction **3.816 m³**, and net **36.3665 m³**. Assignment coverage is complete for this modeled scope, not for every construction trade. Wall net volume is 17.268 m³; Slabs 13.1625 m³; Columns 2.052 m³; Beams 3.6 m³; Door frames 0.1 m³; Window frames 0.184 m³.

IFC uses real type relationships, seven native materials, ordered layer sets and occurrence usages. Wall usage is AXIS2/POSITIVE/offset 0. Slab usage is AXIS3/NEGATIVE with offset equal to total thickness because the unchanged IFC prism is represented from its bottom. Serialized readback checks verify types, layers, orientation, material rows and source identities. The canonical export passed **352 readback assertions**.

The actual Bonsai GUI import passed **216 checks with zero EXPRESS findings**. It verifies 33 imported mesh products, six Types, seven Materials, two layer sets, eleven layer usages and the 55 native material rows; volumes, bounds and opening/join probes match the frozen native geometry. This is a separate application import using IfcOpenShell, not proof of an independent geometry kernel, every IFC viewer or bidirectional editing. See [BONSAI_TYPES_REVIEW.md](BONSAI_TYPES_REVIEW.md), [report](evidence/v0.5.0/bonsai/bonsai-types-report.json), and [actual screenshot](../examples/types/Bonsai_Types_Quantities.png).

Legacy catalogue-free fixtures retain their building revisions and all six category CSV payloads byte-for-byte. The previous v0.4.0/v0.3.0/v0.2.1 release archives and canonical source files remain unchanged.

## 7. Independent unit tests and delivery verification

The independent test gate passed **59 tests and 51 reported subtests, with zero skips**. This covers reference rules, IFC adapters, publication rollback and installer behavior. [Unit evidence](evidence/v0.5.0/independent-tests.json). The 21 independent adapter tests are included in that total and are not added again. In the host IfcOpenShell 0.8.4 interpreter, 18 adapter tests passed and three optional full-EXPRESS tests were skipped because pytest is absent; [host evidence](evidence/v0.5.0/host-adapter-unit-report.json). Full EXPRESS is exercised by the independent adapter and actual Bonsai review.

The final distribution companion, `3117_BIM_Studio_v0_5_0_Release_Verification.json`, is generated **after archive freeze**. It records CRC/manifest/hash checks, installation through the actual packaged public macro into an isolated Unicode-path profile, and six public feature macros in fresh GUI processes. Keeping that result outside the archives preserves their exact tested bytes. This source record does not pre-claim the companion result or turn packaging success into release readiness.

Mutable publication tests run under /tmp because v0.4.0 independently demonstrated external managed-workspace synchronization restoring deleted staging files and locks. The production publication implementation was not changed to accommodate that environment artifact. Historical evidence remains under its original version.

## 8. Remaining scope and next work

The immediate next gate is the native history-branch defect and a verified host fix, followed by Windows installation/upgrade, migration/recovery and Pilot workflows. Candidate files are supplied for review and controlled experiments; a process crash can lose unsaved state.

Family formulas, arbitrary calculated Schedule columns, schedules placed on sheets, multilayer join priorities, wall-wall joins, curved/sloped authoring, roofs/stairs, MEP, structural calculation, RVT/RFA and multiuser authoring remain outside the implemented scope. Current feature evidence does not imply those capabilities.
