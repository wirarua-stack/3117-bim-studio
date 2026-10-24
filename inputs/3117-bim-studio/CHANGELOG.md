# Changelog

## 0.5.0 — Types and Quantities — 2026-10-23

Development candidate with an unresolved **native FreeCAD 1.1.4 Linux history-branch crash**. The identical sequence fails with no addon and plain Part::Feature; original regression and native controls are retained. Pilot/production readiness is blocked, and Windows acceptance remains pending. See [HOST_COMPATIBILITY.md](docs/HOST_COMPATIBILITY.md).

- Native Material and ElementType catalogue for Slab, Column, Beam, Door and Window, retaining WallType and legacy untyped instances.
- Shared dimension propagation, assign/detach/duplicate and dependency guards; simultaneous full-model geometry preflight preserves invalid-proposal Redo branches.
- Ordered Wall/Slab material layers, real OCCT gross/net partitions, native assignment coverage and additive Type/Material CSV sidecars.
- Persistent ScheduleSet/Schedule definitions outside the building group; filters, sorting, Type/Material grouping and distinct source UUID counts.
- Atomic source row edits with model/schedule freshness checks, guarded CSV publication, read-only quantity fields and host Undo/Redo.
- IFC4 shared types, material assignments and layer usage orientation validated after serialization; stable existing product IDs/geometry.
- Native lifecycle/reopen and GUI tests, nineteen-stage host runner and public Types test macro. Versioned verification records distinguish actual Linux checks from pending Windows acceptance.
- Synthetic 33-product typed example with six types, seven materials, 55 material rows, nine schedules and the four Views/two Sheets from v0.4.0.
- No arbitrary schedule formulas/columns, schedules on sheets, detailed family geometry or cost estimating in this release.
- Fixed mutual refresh looping between the Schedules and Quantities modeless readers. A reader's own recompute no longer repeatedly invalidates another clean reader; actual concurrent-panel edit/Undo/Redo behavior is tested separately from the native host crash.

## 0.4.0 — Drawings and Sheets — 2026-10-23

Development candidate. FreeCAD Document / FCStd remains the only editable authority. Linux native/GUI/PDF evidence and pending Windows desktop acceptance are recorded separately.

- Persistent DrawingSet, DrawingView and DrawingSheet with stable IDs, native links, transactions, invalid-proposal preflight, Undo/Redo and fresh-process restore.
- Plan Level + Bottom/Cut/Top, whole-product overhead clipping, actual OCCT cut loops with holes, global hidden-line projection and finite-depth cardinal Section/Elevation.
- Native joined/opened product solids remain the source; no viewport bitmap or display mesh replaces authored geometry.
- Model-derived overall dimensions, visible-source Label/UUID tags, Grid/Level markers and scale bars.
- A3 landscape sheets with one or two views at explicit scales; fit errors are reported instead of silently resizing geometry.
- Read-only host Qt preview with Fit/Pan/Zoom, document observation and separate model/drawing revisions.
- Vector SVG/PDF with Thai/Latin Sarabun, OFL notices, format-specific metadata and payload hashes; freshness checked before staging and publication.
- Drawing definitions are reference-only coverage entries and do not alter legacy building content hashes or become IFC products.
- Thirteen-stage installed-host runner, actual GUI/reopen harnesses and deferred public Drawings test macro.
- Separate canonical drawing example preserves the v0.3.0 building model identity and all previous release files.

Scope excludes curved/oblique views, manual sheet placement, arbitrary sheet templates, reference-edge dimension chains, section callout linking, detail drafting, batch multi-page publication and schedule editing.

## 0.3.0 — Building Authoring — 2026-10-23

Development candidate. Native FCStd remains authoritative. Windows interactive acceptance remains pending; actual Linux and Bonsai evidence is recorded separately.

- Native polygon Slab linked to Level, top offset and Thickness, including concave footprints and explicit boundary validation.
- Rectangular vertical Column with Base/Top Levels and rotation, and horizontal straight Beam with level-bound top/depth.
- Hosted Window with a real wall opening and four-bar frame; Door/Window overlap, rehost and deletion validation share one host contract.
- Explicit Slab priority cuts on Column/Beam, union deductions, stable cutter IDs, Unjoin and rollback for split/full-removal geometry.
- Native transaction, Undo/Redo, direct Properties validation, guarded deletion and fresh-process persistence for every new category.
- Read-only preflight of invalid opening/member/join proposals preserves an existing Redo branch; accepted edits remain one native transaction.
- Solid-angle containment checks prevent false IFC opening failures when a ray grazes an aperture edge.
- Create/edit/delete/join dialogs and persistent view providers; six quantity tabs plus Coverage.
- Conditional Slab/Column/Beam/Window CSV sidecars; IFC4 classes, Qto, material/source metadata and real boolean join geometry.
- Spatial readback checks for structural profiles, rotated/signed placements, cutters, hosted openings and native mesh bounds/volumes.
- Additive native schema 1, preserving the authored revision of an unchanged v0.2.1 sample.
- Nine-stage installed-host runner and a deferred public Building GUI test macro.
- Coherent two-storey native/CSV/IFC example with independent expected quantities.

Scope excludes slab holes, sloped beams, arbitrary sections, general joins, panes/sashes, new shared type catalogues and structural analysis. Roof/stair templates remain subsequent work.

## 0.2.1 — Quantity / Exchange Bridge — 2026-10-23

Development candidate. Native FCStd remains the authoring authority. Windows acceptance pending; see the current verification record for actual Linux / external-application evidence.

- Read-only native SI Wall/Door quantity rows, content-based revisions, coverage inventory and source UUID selection.
- Modeless quantity UI with debounced native observers, Undo/Redo freshness and explicit current/stale export status.
- UTF-8 BOM Wall/Door CSV plus provenance, rules, snapshot and payload hashes.
- Native IFC4 hierarchy, types, material description, swept solids, hosted openings/generic door frames, stable IDs and Qto.
- Actual IFC file readback schema/semantic/placement/geometry validation before publication; optional full EXPRESS QA.
- Native spatial solid checks reject equal-volume displaced geometry; all output paths are locked to prevent overlapping bundles.
- Per-file atomic publication with metadata last and rollback on caught failures; no crash-atomic multi-file claim.
- Seven-stage native host harness, real GUI harness and user-run Exchange test macro.
- Restored native Wall display-mode enumeration when adding GUI presentation to a headless-created file; IDs, quantities and history remain unchanged.
- Deferred public test-macro entry points until FreeCAD returns to its event loop, so native Undo/Redo remains testable from the shipped macros.
- One coherent three-wall native/CSV/IFC example with actual FreeCAD/Bonsai screenshots and separate Bonsai application/EXPRESS evidence.

## 0.2.0 — Walls and Hosted Doors — 2026-10-23

Development candidate. FreeCAD 1.1.4 baseline. Windows desktop acceptance remains pending; see the versioned verification record for actual host runs.

- Native WallType with shared thickness/material metadata and typed Wall instances linked to Base/Top Levels and offsets.
- Straight wall axes in any XY direction, with explicit start/end coordinates in millimetres.
- Hosted Door instances with offset, width, height and sill; real OCCT boolean openings and a simple door frame representation.
- Acyclic Wall parameters → Door → WallBody geometry, with native dependency updates from type and levels.
- Create/edit/delete forms, selection of a wall through its body, persistent view providers and dependency-aware deletion guards.
- Native transaction, Undo/Redo and rollback for wall/type/level/door edits, rehosting and deletion.
- Derived per-wall gross/net area and volume properties for subsequent quantity workflows.
- Native and GUI Wall/Door harnesses, fresh-process reopen checks, Foundation compatibility fixture and a dedicated GUI smoke macro.
- Extended source-only packaging and five-stage Linux/Windows headless CI contract.

Scope is uniform straight walls and rectangular non-overlapping openings. This release does not add wall joins, layered materials, drawing views, live schedules, CSV or IFC export from native Wall/Door objects. The earlier reference core remains independent.

## 0.1.0 — Foundation Workbench — 2026-10-23

Development candidate. Target FreeCAD 1.1.4. Windows desktop acceptance remains pending.

- Native Project, Level and Grid objects with persistent UUID/schema properties in `.FCStd`.
- Project, level, grid and edit dialogs; toolbar/menu; native selection, Undo/Redo and Fit All.
- Level-driven grid geometry and persistent endpoint labels using the host Coin runtime.
- One document transaction per command, validation, rollback and native redo-branch handling.
- Safe referenced-level deletion policy and explicit missing-reference repair/detachment.
- Persistent model/view proxies, Unicode-path save/reopen and fresh-process host tests.
- User-level installer, update backup, restore/uninstall macros and GUI smoke-test macro.
- Reproducible source ZIP builder and pinned Linux/Windows native-host GitHub Actions workflow.

This release does not add native walls, doors, drawings, schedules or IFC export from the workbench. The earlier reference core and IFC fixture remain separate.

## 0.0.1 — 2026-10-23

- Initial product blueprint, architecture decisions, roadmap and acceptance plan.
- Headless reference core and optional IFC4 export fixture.
- FreeCAD workbench bootstrap for the next integration milestone.
- GitHub contribution, CI and issue templates.

This version is a development scaffold. It is not a complete BIM authoring application or a Windows installer.
