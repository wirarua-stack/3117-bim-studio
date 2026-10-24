# Architecture decision records

Status of all decisions: proposed baseline for implementation; v0.0.1 is a scaffold.

## ADR 001 FreeCAD workbench first

Use a 3117 workbench on a supported, user-installed FreeCAD build. Reuse document, geometry and drawing facilities. Avoid a deep upstream fork for the initial MVP. Alternatives evaluated: Bonsai/Blender native IFC, standalone Python/Qt/OCC, and browser authoring. Select one host after the 2–3 week integration spike; do not combine multiple editable hosts in MVP.

## ADR 002 One authoring authority

Production authoring authority is `.FCStd`. Native persistent properties retain UUID/type/level/host metadata. IFC is a revision snapshot; imported IFC is a linked reference initially. The Python JSON in this repository is a reference fixture only. A future native-IFC authority requires a new ADR, migration and acceptance results.

## ADR 003 Units and identity

Core rules/DTOs use SI metres. The FreeCAD boundary explicitly converts millimetres, square millimetres and cubic millimetres. Persist UUIDs; derive or map IFC GlobalIds consistently. Labels, mesh indices and IFC STEP numbers are not stable identities.

## ADR 004 Scope before breadth

First integrate a one-room workflow with wall, hosted door/opening, slab, plan, quantity schedule, save/reopen, Undo/Redo and IFC. Expand to a 2-storey building after this passes. MEP, advanced families, multiuser authoring and AI follow separate gates.

## ADR 005 Code license

New scaffold code uses GPL-3.0-or-later. Dependencies and asset libraries retain their own licenses. No upstream binary is bundled in this archive. Inventory the exact dependency versions and notices before making an installer.

## ADR 006 Runtime and CI

The reference core was tested with Python 3.12.14 and optional IfcOpenShell 0.9.0.post1. The proposed host baseline is not yet selected. GitHub workflow uses the official actions/checkout and actions/setup-python major v7 as observed in their upstream READMEs on 2026-10-23; workflows remain unexecuted remotely until repository publication. Pin commit SHAs and record transitive dependencies as part of the release process.
