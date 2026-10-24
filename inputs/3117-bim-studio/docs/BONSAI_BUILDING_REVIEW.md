# Bonsai application review — v0.3.0 Building Authoring

Date: 2026-10-23. The actual native-exported IFC was imported into the visible Bonsai/Blender application. **266 checks passed: 265 application/geometry/metadata/EXPRESS assertions plus one inspected GUI capture.** Full IFC4 schema and EXPRESS validation produced zero findings.

[Application report](evidence/v0.3.0/bonsai-building-report.json) · [Process report](evidence/v0.3.0/bonsai-process-report.json) · [Actual screenshot](../examples/building/Bonsai_Building_Authoring.png)

Bonsai uses IfcOpenShell itself. This is evidence from another application with independent Blender mesh measurements and direct ray casts; it does not establish an independent IFC kernel, Revit interoperability or Windows acceptance.

## Fixture and identity

The review used [Building_Authoring_Workbench.ifc](../examples/building/Building_Authoring_Workbench.ifc), [building-snapshot.json](../examples/building/building-snapshot.json) and [the canonical native test report](evidence/v0.3.0/linux-building-report.json).

- IFC SHA-256: `775b5a63592d05c63c14fb63d258d6a30ae45558d6d6f244cf75f387279ac609`
- Content revision: `6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a`
- 33 authored products: 3 Slabs, 8 Columns, 8 Beams, 8 Walls, 2 Doors, 4 Windows.
- 6 hosted Openings with void/fill relationships, 3 Storeys at 0/3/6 m, one WallType.
- 16 explicit Slab-priority cuts on members. Other intersections are not deducted.
- The IFC bytes were unchanged by application import and inspection.

## Measured geometry

| Category | Independent expected total (m³) | Actual Blender triangle total (m³) |
|---|---:|---:|
| Slab | 13.162500 | 13.1625057533 |
| Column after Slab cuts | 2.052000 | 2.0520013175 |
| Beam after Slab cuts | 3.600000 | 3.6000015020 |
| Wall after openings | 17.268000 | 17.2680016269 |
| Generic Door frames | 0.100000 | 0.0999999207 |
| Generic Window frames | 0.184000 | 0.1840001465 |

Every per-element volume and category total passed `max(2e-6, abs(expected) × 2e-6)` m³ tolerance. Volumes use a translated origin and double-precision accumulated triangle determinants; Blender's actual mesh coordinates remain unchanged. The largest per-element absolute difference was approximately 2.79 × 10⁻⁶ m³. Check counts are assertions for this fixture, not performance benchmarks or independent unit tests.

The harness checks native UUIDs/IFC GlobalIds, revision, storeys, type and Qto associations, source material descriptions, and transformed world bounds. Direct Blender mesh ray casts confirm empty wall openings, solid frame bars, empty slab-cut member zones and solid member material below the cuts. Windows have a lower frame bar; Door frames have none.

## Runtime and capture

| Component | Actual runtime |
|---|---|
| Export host | FreeCAD 1.1.4, Python 3.11.14, IfcOpenShell 0.8.4 |
| Reviewing application | Blender 4.5.14 LTS, build 62c1db4208e8 |
| Extension | Bonsai 0.9.0-post1-py311 |
| IFC runtime | IfcOpenShell 0.9.0.post1, Python 3.11.15 |
| Platform | Linux x86_64, isolated preferences/cache, Xvfb visible GUI, software OpenGL |
| Capture | Actual X11 framebuffer, 1600 × 1100, opened and visually inspected |

The delivered PNG shows the complete two-storey scene, openings/frames, IFC4 project details and the 33-element count. It was accepted after image inspection, not merely after finding a nonempty PNG. Blender and the task-owned Xvfb process exited successfully. Archive provenance for the unchanged host/application binaries is recorded in [the previous Bonsai runtime record](BONSAI_REVIEW.md); no binaries are redistributed.

## Reproduce

The shipped [tests/bonsai_building_review.py](../tests/bonsai_building_review.py) was executed directly for this review. It clears the current Blender scene, so use a newly started disposable review profile with Bonsai installed/enabled. Source paths below are relative to the repository root; replace the Blender path with the actual binary.

```bash
/path/to/blender --window-geometry 0 0 1600 1100 \
  --python tests/bonsai_building_review.py -- \
  --ifc examples/building/Building_Authoring_Workbench.ifc \
  --snapshot examples/building/building-snapshot.json \
  --native-report docs/evidence/v0.3.0/linux-building-report.json \
  --output out/bonsai-building-review \
  --gui-hold-seconds 0
```

Use a fresh output directory. A GUI run initially records `geometry_passed_capture_pending`. Capture the visible application, open and inspect that exact image, record its hash and observed details, then promote the report only if the visual requirement passes. Background mode can establish import/geometry assertions but cannot replace that step. See [BONSAI_REVIEW.md](BONSAI_REVIEW.md) for isolated-profile setup and the capture procedure.
