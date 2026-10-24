# SPDX-License-Identifier: GPL-3.0-or-later
"""Real-host integration checks. Run with FreeCAD's Python, not ordinary CPython.

Entry point: main(output_dir). Writes a native FCStd sample and a JSON report.
This tests host document behavior; it does not certify Windows or GUI behavior.
"""
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App
from bim3117_freecad import services
from bim3117_freecad.model import FoundationError, grid_endpoints


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    doc = None
    report = {"freecad": App.Version(), "python": sys.version, "platform": platform.platform(),
              "gui_up": bool(App.GuiUp), "checks": checks, "status": "running"}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def near(actual, expected):
        return abs(actual - expected) < 1e-6

    try:
        project = services.create_project("3117 Foundation Test", "FND-001", "3117 BIM")
        doc = project.Document
        levels = services.list_levels(project)
        lower, upper = levels
        check("native project and two levels", len(levels) == 2 and project.TypeId == "App::DocumentObjectGroupPython")
        check("native dimensional properties", upper.getTypeIdOfProperty("Elevation") == "App::PropertyDistance"
              and upper.getTypeIdOfProperty("SpanX") == "App::PropertyLength")
        check("project backlink and membership", upper.Project == project and upper in project.Group)
        check("level datum elevation and extents", near(upper.Shape.BoundBox.ZMin, 3000)
              and near(upper.Shape.BoundBox.XLength, 12000) and near(upper.Shape.BoundBox.YLength, 8000))
        check("project creation is one undo item", doc.UndoCount == 1)
        title = doc.Label
        services.edit_project(project, name="Renamed project")
        check("project rename leaves non-transactional document title unchanged",
              project.Label == "Renamed project" and doc.Label == title)
        doc.undo()
        doc.recompute()
        check("project rename undo restores exact project name", project.Label == "3117 Foundation Test" and doc.Label == title)

        grid = services.create_grid(project, "Grid A", axis="X", position_mm=2500,
                                    length_mm=10000, bubble_label="A", level=upper, offset_mm=250)
        grid_name, grid_id = grid.Name, grid.BIM3117Id
        start, end = grid_endpoints(grid)
        check("grid geometry, label and elevation", near(start.x, -5000) and near(end.x, 5000)
              and near(start.y, 2500) and near(start.z, 3250) and grid.BubbleLabel == "A"
              and len(grid.Shape.Edges) == 3)
        check("grid create adds one undo item", doc.UndoCount == 2)
        doc.undo()
        doc.recompute()
        check("undo grid creation removes object and membership", doc.getObject(grid_name) is None and len(project.Group) == 2)
        doc.redo()
        doc.recompute()
        grid = doc.getObject(grid_name)
        check("redo restores grid identity and links", grid is not None and grid.BIM3117Id == grid_id
              and grid.ReferenceLevel == upper and grid.Project == project)

        basement = services.add_level(project, "B01", -3000)
        basement_grid = services.create_grid(project, "Basement grid", level=basement, offset_mm=250)
        check("negative basement elevation drives datum and grid", near(basement.Shape.BoundBox.ZMin, -3000)
              and near(basement_grid.Shape.BoundBox.ZMin, -2750))
        services.edit_level(basement, elevation_mm=-3300)
        check("basement edit recomputes linked grid below origin", near(basement_grid.Shape.BoundBox.ZMin, -3050))
        doc.undo()  # basement elevation
        doc.undo()  # basement grid
        doc.undo()  # basement level
        doc.recompute()
        had_redo_branch = doc.RedoCount >= 3

        before_undo = doc.UndoCount
        services.edit_level(upper, name="L01 First Floor", elevation_mm=3300, span_x_mm=14000)
        check("undo followed by new edit clears redo branch", had_redo_branch and doc.RedoCount == 0)
        check("one edit transaction changes all parameters", doc.UndoCount == before_undo + 1
              and upper.Label == "L01 First Floor" and near(upper.Elevation.Value, 3300)
              and near(upper.SpanX.Value, 14000))
        check("level dependency recomputes grid", near(grid.Shape.BoundBox.ZMin, 3550))
        doc.undo()
        doc.recompute()
        check("undo restores level and dependent grid geometry", upper.Label == "L01"
              and near(upper.Elevation.Value, 3000) and near(upper.SpanX.Value, 12000)
              and near(grid.Shape.BoundBox.ZMin, 3250))
        doc.redo()
        doc.recompute()
        check("redo restores dependent geometry", near(grid.Shape.BoundBox.ZMin, 3550))

        before = (doc.UndoCount, upper.Elevation.Value, len(doc.Objects))
        for bad in (float("nan"), float("inf"), True):
            try:
                services.edit_level(upper, elevation_mm=bad)
            except FoundationError:
                pass
            else:
                raise AssertionError("Invalid numeric edit was accepted")
        check("invalid numeric commands preserve model and history",
              before == (doc.UndoCount, upper.Elevation.Value, len(doc.Objects)))

        # The Property Editor owns the native transaction. Its callback restores
        # an invalid value and does not open another transaction.
        doc.openTransaction("Native property edit")
        upper.Elevation = 3600
        upper.SpanX = 0
        name_before_invalid_edit = upper.Label
        upper.Label = ""
        doc.recompute()
        doc.commitTransaction()
        check("native property edit keeps one transaction and rejects zero span",
              doc.UndoCount == before[0] + 1 and near(upper.Elevation.Value, 3600)
              and near(upper.SpanX.Value, 14000) and near(grid.Shape.BoundBox.ZMin, 3850))
        check("invalid native blank label preserves exact name", upper.Label == name_before_invalid_edit)

        # Simulate a validation/geometry gate failure after an object was added.
        # The rollback must remove the new object and its parent membership.
        original_validator = services.validate_document
        object_names = {obj.Name for obj in doc.Objects}
        group_names = [obj.Name for obj in project.Group]
        undo_before = doc.UndoCount
        def fail_gate(*args, **kwargs):
            raise RuntimeError("Injected post-mutation validation failure")
        services.validate_document = fail_gate
        try:
            try:
                services.add_level(project, "Must roll back", 9000)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Expected injected command failure")
        finally:
            services.validate_document = original_validator
        check("post-mutation failure rolls back object, membership and undo item",
              {obj.Name for obj in doc.Objects} == object_names
              and [obj.Name for obj in project.Group] == group_names and doc.UndoCount == undo_before)
        check("failed command closes owned transaction", App.getActiveTransaction() is None and not doc.HasPendingTransaction)

        doc.openTransaction("External transaction")
        try:
            try:
                services.add_level(project, "Must not nest", 6000)
            except FoundationError:
                pass
            else:
                raise AssertionError("A nested native transaction was accepted")
            check("service does not steal external empty transaction", App.getActiveTransaction()[0] == "External transaction")
        finally:
            doc.abortTransaction()
            App.closeActiveTransaction()

        expected_level_id = upper.BIM3117Id
        delete_before = (doc.UndoCount, len(doc.Objects), grid.Shape.BoundBox.ZMin)
        try:
            services.delete_level(upper)
        except FoundationError:
            pass
        else:
            raise AssertionError("Referenced level deletion was accepted")
        check("supported level deletion rejects dependencies without mutation",
              not services.can_delete_level(upper) and services.level_dependents(upper) == [grid]
              and delete_before == (doc.UndoCount, len(doc.Objects), grid.Shape.BoundBox.ZMin))
        upper_name = upper.Name
        doc.openTransaction("Unsupported raw level deletion probe")
        doc.removeObject(upper_name)
        doc.recompute()
        try:
            services.validate_document(doc, check_shapes=True)
        except FoundationError:
            invalid_missing_link = True
        else:
            invalid_missing_link = False
        check("raw native deletion retains expected identity and exposes invalid state",
              invalid_missing_link and grid.ReferenceLevel is None
              and grid.ReferenceLevelId == expected_level_id and grid.Shape.isNull())
        doc.abortTransaction()
        App.closeActiveTransaction()
        doc.recompute()
        upper = doc.getObject(upper_name)
        check("aborting raw deletion restores link and dependent geometry",
              grid.ReferenceLevel == upper and grid.ReferenceLevelId == expected_level_id
              and near(grid.Shape.BoundBox.ZMin, delete_before[2]))

        services.edit_grid(grid, level=None)
        check("explicit detach intentionally uses project origin", grid.ReferenceLevel is None
              and grid.ReferenceLevelId == "" and near(grid.Shape.BoundBox.ZMin, grid.ElevationOffset.Value))
        doc.undo()
        doc.recompute()
        check("undo explicit detach restores expected level identity", grid.ReferenceLevel == upper
              and grid.ReferenceLevelId == expected_level_id)

        services.edit_grid(grid, axis="Y", position_mm=-2000, length_mm=8000,
                           bubble_label="1", offset_mm=100)
        check("grid edit switches axis and retains stable identity", near(grid_endpoints(grid)[0].x, -2000)
              and near(grid_endpoints(grid)[0].y, -4000) and grid.BIM3117Id == grid_id)
        check("native model validates with no dependency cycles", services.validate_document(doc, check_shapes=True))
        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        check("all element IDs are unique", len(set(identifiers.values())) == len(identifiers))
        saved = output / "save_ภาษาไทย" / "Foundation.FCStd"
        saved.parent.mkdir(parents=True, exist_ok=True)
        doc.recompute()
        doc.saveAs(str(saved))
        doc_name = doc.Name
        App.closeDocument(doc_name)
        doc = App.openDocument(str(saved))
        doc.recompute()
        project = services.get_project(doc)
        grid = doc.getObject(grid_name)
        upper = grid.ReferenceLevel
        check("FCStd reopen preserves UUIDs", identifiers == {obj.Name: obj.BIM3117Id for obj in doc.Objects})
        check("FCStd reopen preserves membership, reference and proxy",
              grid.Project == project and grid in project.Group and services.kind(upper) == "Level"
              and grid.Proxy.__class__.__module__ == "bim3117_freecad.model")
        services.edit_level(upper, elevation_mm=4000)
        check("restored proxy recomputes level dependency", near(grid.Shape.BoundBox.ZMin, 4100))
        doc.save()
        report.update(status="passed", sample=str(saved), element_ids=identifiers,
                      elements=len(doc.Objects), checks_passed=len(checks))
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(checks))
        raise
    finally:
        (output / "foundation-test-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report


if __name__ == "__main__":
    destination = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bim3117-foundation-tests"
    print(json.dumps(main(destination), indent=2, ensure_ascii=False))
