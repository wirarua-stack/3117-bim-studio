# 3117 BIM Studio v0.5.0 — Types and Quantities

**Development candidate; Pilot/production gate blocked.** FreeCAD 1.1.4 Linux crashes on a create/delete/two-Undo/new-edit/Undo/Redo branch, also reproduced without this workbench using a plain Part::Feature. See [Host compatibility](../docs/HOST_COMPATIBILITY.md). Feature-test passes do not resolve this host gate; Windows remains untested. Use saved copies/test documents.

Install through the distribution macros and restart FreeCAD. Uses the host Python/Qt runtime. Project/Levels/Grid/WallType/Wall/Door/Slab/Column/Beam/Window remain native FCStd data. DrawingSet/View/Sheet add persistent drawing definitions with native transactions. Actual OCCT cuts/global projection produce Plan, Section and Elevation; one or two explicit-scale views fit on A3. SVG/PDF retain both model and drawing revisions. Explicit slab cuts affect joined Column/Beam geometry and quantities. CSV/IFC remain read-only building snapshots with revision and coverage.

- [Installation](../packaging/INSTALL_TH.md)
- [Types and Quantities](../docs/TYPES_AND_QUANTITIES.md)
- [Drawings and Sheets](../docs/DRAWINGS_AND_SHEETS.md)
- [Building Authoring](../docs/BUILDING_AUTHORING.md)
- [Quantity / IFC workflow](../docs/QUANTITY_EXCHANGE.md)
- [Wall / Door workflow](../docs/WALL_DOOR_WORKBENCH.md)
- [Actual verification and Windows boundary](../docs/VERIFICATION.md)

IfcOpenShell is optional in the host; no runtime dependencies are installed automatically. Source workbench package with unmodified OFL-licensed Sarabun fonts: no FreeCAD, Qt or IfcOpenShell binaries. Fonts load only into the application.
