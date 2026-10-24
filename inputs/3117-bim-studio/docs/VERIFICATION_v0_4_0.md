# Verification record — v0.4.0 Drawings and Sheets

Date: **2026-10-23**. Workbench: **0.4.0 development candidate**. Native model schema: **1**. Drawing schema: **1**. Independent reference package: **0.0.1**.

**Actual runtime acceptance is on Linux FreeCAD 1.1.4. Windows desktop acceptance remains pending.** This release adds persistent native Plan, Section, Elevation and Sheet definitions, actual solid-derived drawings, an interactive preview, and vector SVG/PDF publication. The two delivered sheets were exported from the delivered FCStd and independently checked for physical scale, embedded Thai fonts and vector content. Building authoring and exchange remain on the same native model.

The complete user/API guide is [DRAWINGS_AND_SHEETS.md](DRAWINGS_AND_SHEETS.md). This record separates current execution from retained evidence for earlier releases.

## 1. Tested host and provenance

The host was the SHA-256-verified official Linux x86_64 FreeCAD AppImage (`f6dc6ba676e5ac96a565ebc8d657232f94c6158e85b4352141bd1a46f6b43434`), build `4fd3bf320d9566a27e60069fc8387448aaa3a094`, embedded Python 3.11.14, Qt 6.8.3 and IfcOpenShell 0.8.4. Workbench files were installed into isolated FreeCAD user profiles. GUI evidence used Xvfb/software rendering; drawing production uses FreeCAD's own OCCT/TechDraw and Qt/PySide.

Independent unit tests used Python 3.12.14 and IfcOpenShell 0.9.0.post1. PDF inspection used PyMuPDF 1.26.6, with both pages also rendered and visually reviewed. No alternate Qt was installed into FreeCAD, and no host/application binaries are redistributed. Sarabun is loaded app-locally with its actual OFL notice and source hashes.

Runtime versions, evidence paths, hashes and qualifications are recorded in [TEST_ENVIRONMENT.json](TEST_ENVIRONMENT.json).

## 2. Native regression gate

Counts below are **assertions within integration suites**, not independent unit-test counts or performance measurements. Repeated attempts are not added to the totals.

| Native stage, each in a separate installed FreeCADCmd process | Passed checks | Evidence |
|---|---:|---|
| Install | 1 | [Install](evidence/v0.4.0/final-native/install-report.json) |
| Project / Levels / Grid | 35 | [Foundation](evidence/v0.4.0/final-native/foundation-test-report.json) |
| Foundation fresh restore | 9 | [Reopen](evidence/v0.4.0/final-native/reopen-test-report.json) |
| WallType / Wall / Door / WallBody | 63 | [Architecture](evidence/v0.4.0/final-native/architecture-test-report.json) |
| Architecture fresh restore | 12 | [Reopen](evidence/v0.4.0/final-native/architecture-reopen-test-report.json) |
| Snapshot / Coverage / CSV / IFC | 47 | [Exchange](evidence/v0.4.0/final-native/exchange-test-report.json) |
| Exchange fresh restore | 10 | [Reopen](evidence/v0.4.0/final-native/exchange-reopen-test-report.json) |
| Slab / Column / Beam / Window / explicit cuts / history | 112 | [Building](evidence/v0.4.0/final-native/building-test-report.json) |
| Building fresh restore | 19 | [Reopen](evidence/v0.4.0/final-native/building-reopen-test-report.json) |
| OCCT cuts, clipping, directions and global hidden-line geometry | 31 | [Drawing geometry](evidence/v0.4.0/final-native/drawing-geometry-test-report.json) |
| Native drawing definitions, validation, transactions and identity | 70 | [Drawings](evidence/v0.4.0/final-native/drawings-test-report.json) |
| Drawings fresh restore and history | 25 | [Reopen](evidence/v0.4.0/final-native/drawings-reopen-test-report.json) |
| Sheet layout / SVG / scale / publication and stale-source guards | 33 | [Drawing render](evidence/v0.4.0/final-native/drawing-render-test-report.json) |
| **Total across thirteen stages** | **467** | [Process manifest](evidence/v0.4.0/final-native/native-process-manifest.json) |

Both real process exit codes and JSON outcomes are required. Installed production payloads are tied to source hashes, and fresh-process tests do not inject source workbench paths or pre-register native proxies. The thirteen-report CI validation block was executed locally against the final reports. No remote GitHub Actions execution is claimed.

The manifest retains the renderer-stage retry history. The first twelve successful processes were kept because their production payload remained unchanged; the renderer was rerun separately after a repeatability correction in its test harness and investigation of the managed workspace behavior described below. Retried assertions are counted once.

## 3. Drawing geometry and presentation contract

Plan uses the native Level and Bottom/Cut/Top offsets. It clips solids below the cut, obtains real OCCT cut faces including holes, and uses global hidden-line removal for visible edges. Dashed overhead geometry represents whole products above the cut within Top; the portion of a cut wall above its cut is not duplicated as an overhead wall. Section and Elevation use a finite positive Depth and cardinal directions from viewer into the model. Section fills actual cut faces; Elevation does not.

Wall geometry comes from the derived WallBody after real Door/Window openings, while tags and cut-face provenance retain the authored Wall UUID. Slabs, columns and beams include the existing explicit slab/member deductions. Geometry is not taken from a viewport screenshot or display mesh. Straight projected segments are deduplicated across the view. Curved geometry is explicitly rejected in this bounded release.

A3 landscape sheets contain one or two ordered views at their explicit scale denominators. Geometry, dimensions or tag counts that overflow the available space are rejected. The renderer does not silently change scale. Long text may be fitted within a minimum size or abbreviated, with the full source name retained in metadata and SVG titles.

Annotations include overall dimensions, visible-source Label/UUID tags, Plan grids, vertical-view levels and scale bars. A completely occluded product does not receive a visible-product tag. These are generated annotations; manual dimension chains, editable annotation masters and section-callout links are outside this release.

## 4. Persistence, transactions and two revisions

DrawingSet, DrawingView and DrawingSheet persist inside the same FCStd with stable UUIDs and native links. They live outside the authored Project group. The fixture adds seven documentation objects to the previous fifty native building/reference objects: one DrawingSet, four Views and two Sheets.

The **model revision** continues to identify the authored building content. Drawing definitions are omitted from its hash and are explicit references/omissions in quantity and IFC coverage. The **drawing revision** identifies a Sheet and its ordered View definitions. A model change and a scale/range/title change therefore have distinct provenance. Revision hashes are content identities; Undo to identical content restores the same hash.

Create/edit/delete services validate proposals before mutation and wrap each accepted command in one native transaction. Dependencies guard deletion of Views used by Sheets, Levels used by Plans and Projects with drawing definitions. Invalid supported service proposals retain existing Redo. Raw native Properties still use host validation/callback behavior; this is not a promise that arbitrary raw API corruption preserves a Redo chain.

Preview is modeless, supports fit/pan/zoom and auto/manual refresh, and creates no persistent render-cache objects or Undo entries. It marks prior session exports stale when either revision changes and blocks export of outdated or invalid content. Export captures the real native Sheet, rechecks both revisions after projection and again before publishing. An externally supplied model DTO cannot replace native authority.

## 5. Actual GUI and PDF review

| Current non-package evidence | Passed checks | Evidence |
|---|---:|---|
| Fresh GUI restore of native drawing definitions and history | 18 | [GUI reopen](evidence/v0.4.0/linux-drawings-gui-reopen-report.json) |
| Actual canonical FreeCAD model and sheet preview capture | 13 | [Presentation](evidence/v0.4.0/linux-drawings-presentation-report.json) |
| Independent two-page PDF structure, text, fonts and scale | 36 | [PDF review](evidence/v0.4.0/pdf-review-report.json) |

The final exact-ZIP companion described below records the public Drawings GUI macro and all existing public GUI macros. Its public Drawings invocation keeps the sample open for inspection and therefore skips the three close/reopen assertions used by `run(..., keep_sample=False)`; its expected count is 53, while that full harness path contains 56. Fresh GUI restore has its own 18-check evidence above. These different invocation counts are not substituted for each other.

PDF uses the host QSvgRenderer/QPainter/QPdfWriter. Geometry remains vector content, and text is drawn through QPainter so the delivered PDF embeds Sarabun and retains selectable Thai/Latin text. Merely rendering SVG text through QtSvg produced outlines during development; the independent PDF gate verifies the delivered result instead of assuming text embedding.

Both canonical PDFs have one page, no raster image objects, two embedded Sarabun font programs, source revision text and text contained within the paper. Their MediaBox is 1191 × 842 PDF points, approximately **420.158 × 297.039 mm**; this is Qt's integer-point rounding for nominal A3. Drawing vectors preserve exact millimetre scale independently of that small page-box rounding.

The review located actual dimension line endpoints in the final PDF, rather than trusting a scale label or metadata:

| Native extent | Scale | Expected paper extent | Observed paper extent, representative |
|---|---|---:|---:|
| 6500 mm width | 1:50 | 130 mm | 129.999997 mm |
| 4500 mm Plan height | 1:50 | 90 mm | 89.999987 mm |
| 6150 mm vertical-view height | 1:50 | 123 mm | 122.999991 mm |

All measured views met a 0.001 mm vector-coordinate tolerance. This is a file geometry test, not a physical printer calibration. Use **Actual size / 100%** when printing. Both pages and the actual FreeCAD model/preview captures were visually inspected for clipping, legibility and missing glyphs.

## 6. Canonical example and continuing exchange

[examples/drawings](../examples/drawings/README.md) contains the FCStd, both SVGs/PDFs and format-specific metadata, real GUI screenshots, independent PDF renders, source identity and publication evidence.

| Sheet | Views | Definitions |
|---|---|---|
| A101 — Floor Plans | Ground Plan / Upper Plan | L00/L01, Bottom −150, Cut 1200, Top 2800 mm, 1:50 |
| A201 — Section and Elevation | Section A–A / South Elevation | Origins (0,2000,0) / (0,−1000,0), direction +Y, depths 3000 / 6000 mm, 1:50 |

Both are A3 landscape, issue P01. Native API/form defaults for Plan are −200 / 1200 / 2700 mm; the explicit canonical ranges above differ intentionally. The example has 3 Slabs, 8 Columns, 8 Beams, 8 Walls, 2 Doors and 4 Windows, with Levels at 0/3/6 m and four Grids. Its 6500 × 4500 mm overall Plan includes the slab perimeter beyond the grid. Its 6150 mm vertical extent includes the bottom slab below L00.

- Native drawing FCStd SHA-256: `92b6cd2fc012ce1ae2815ed511bed2c676451c0a2d8c9b2caa1823eeba81882c`
- Retained building model revision: `6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a`
- A101 drawing revision: `909065e2af5789cd0b0e18560cfd641c9bca411843400c58259e460ea4a7f481`
- A201 drawing revision: `20044ae522d2f876a997413109c647d244e2469d86722dae30b0a524a94028f5`

A focused [canonical drawing/exchange regression](evidence/v0.4.0/canonical-drawings-exchange-report.json) passed **20 checks** in a fresh installed FreeCAD process. It reopens this exact FCStd and exports actual CSV/IFC. All six CSV payloads are byte-identical to the frozen v0.3.0 quantities. The seven drawing definitions remain references with no quantity/IFC role; coverage is 38 mapped, 8 derived, 11 reference and 0 unsupported. All 33 products retain their GUIDs, quantities, world placements and normalized IFC surface geometry, including openings and explicit joins. The exporter's serialized-file validation passed 186 checks. The source FCStd, native BReps, IDs, revisions and Undo/Redo remain unchanged. The portable supplemental harness is [freecad_drawings_exchange.py](../tests/freecad_drawings_exchange.py); it is separate from the thirteen-stage gate.

This is current native export evidence. The earlier Bonsai/Blender review is retained in [VERIFICATION_v0_3_0.md](VERIFICATION_v0_3_0.md); Bonsai was not rerun for v0.4.0 and its historical checks are not counted here.

The earlier canonical building/exchange data and six delivered v0.3.0/v0.2.1 ZIPs remain byte-identical. The new native fixture adds documentation to a copy of the building model. It is a synthetic software example, not a construction-approved design or a globally clash-free quantity model.

## 7. Publication and managed workspace finding

SVG/PDF exports use the shared publication pipeline: validate destinations, acquire exclusive locks, stage payloads, check both source revisions, replace files individually and publish metadata last. Caught failures roll back previous files. This is **per-file atomic replacement with caught-failure rollback**, not crash-atomic publication of an entire bundle. Metadata hashes define the current bundle; do not infer completeness from one payload file alone.

During release testing, the managed workspace restored some temporary files after the exporter had deleted them. The [publication environment probe](evidence/v0.4.0/publication-environment-probe.json) records direct filesystem event and cross-process observations. Production code and installed hashes were held fixed. Subsequent native publication tests ran in a task-specific `/tmp` directory, and the final renderer suite required actual lock/staging cleanup for both successful and rejected exports. The final process manifest records the exact output location and prior attempts; the affected workspace attempts are not represented as passes.

The canonical SVG/PDF payload hashes and metadata were validated before removing only the identified temporary remnants. The [canonical export report](../examples/drawings/drawings-export-report.json) records that cleanup and the separate successful installed-host repeat. No generic filesystem or Windows guarantee is inferred from this environment diagnosis.

## 8. Independent tests, source gate and exact distribution

| Independent Python suite | Result |
|---|---:|
| Reference model | 17 passed |
| Reference IFC | 4 passed |
| Native IFC adapter | 17 passed |
| Export publication | 9 passed |
| Installer | 8 passed |
| **Combined** | **55 passed, 0 skipped** |

The [unit report](evidence/v0.4.0/unit-test-report.json) is from the current source. Older host-version adapter/EXPRESS tests are historical evidence only; they are not silently relabelled as current runs.

The [final source gate](evidence/v0.4.0/final-source-gates.json) checks Python/macros, package/schema versions, all three embedded CI Python blocks, the actual thirteen-report gate, relative documentation links, installed production hashes, font/OFL hashes, canonical native definitions and export metadata, archive payload closure, and preservation of old releases. The source-only package contains the workbench, installation/test macros, guides, tests and examples.

The external companion **`3117_BIM_Studio_v0_4_0_Release_Verification.json`**, delivered beside the ZIPs, is authoritative for exact distribution results. It records the frozen FreeCAD ZIP hash, complete payload manifest, the actual public installer and five public test macros in separate GUI processes, installed file hashes and observed outcomes. Keeping the companion outside the archives preserves the exact tested ZIP bytes. Each ZIP has its own `MANIFEST.json`; the external SHA-256 file identifies the final deliverables.

## 9. Remaining acceptance and scope

- **Windows:** scripts, Thai installation guide, public macros and [Windows acceptance checklist](WINDOWS_ACCEPTANCE.md) are provided. No Windows desktop, FreeCAD.exe or PowerShell acceptance run was executed here.
- **GitHub:** source and Linux/Windows workflows are prepared locally. No remote repository was created/pushed and no remote Actions result is claimed.
- **Drawing limits:** polyhedral products, cardinal directions, finite depth, A3 landscape, one or two views, automatic overall dimensions/tags/datums. No arbitrary oblique camera, curved drawing geometry, crop polygon, manual viewport placement, custom templates, dimension chains, section-callout linking, manual 2D detail editor or multi-page batch publisher.
- **Building/exchange limits:** existing bounded geometry/join semantics remain. No native IFC import/round-trip editing, RVT/RFA, general automatic joins, structural analysis or complete Revit parity.
- **Further acceptance:** production-scale performance, printers, power-loss recovery and other unrecorded host/viewer combinations remain untested.

The next roadmap milestone is **v0.5.0 — Types and Quantities**, continuing with shared types/material definitions and editable schedules on the same native transaction, revision and quantity foundation.
