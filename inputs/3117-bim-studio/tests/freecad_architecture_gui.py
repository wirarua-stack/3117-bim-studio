# SPDX-License-Identifier: GPL-3.0-or-later
"""Real installed Wall/Door commands, widgets, native solids and lifecycle.

Run in a development FreeCAD GUI profile. Only documents created here are
changed/closed. This is an integration gate, not a simulated UI or benchmark.
"""
import json
import math
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui


def run(output_dir, keep_sample=False):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    checks, messages, expected_errors, deletion_warnings = [], [], [], []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(),
              "gui_up": bool(App.GuiUp), "checks": checks,
              "expected_command_errors": expected_errors, "deletion_warnings": deletion_warnings}
    deletion_mode = [False]
    sample_doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def near(actual, expected, tolerance=1e-3):
        return abs(actual - expected) <= tolerance

    def select(obj):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        Gui.updateGui()

    def close_messages():
        modal = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(modal, QtWidgets.QMessageBox):
            return
        if deletion_mode[0]:
            if modal.objectName() == "BIM3117DeletionWarning":
                deletion_warnings.append(modal.text())
                modal.accept()
            else:
                yes = modal.button(QtWidgets.QMessageBox.Yes)
                if yes is not None:
                    yes.click()
                else:
                    modal.reject()
        else:
            messages.append(modal.text())
            modal.accept()

    watchdog = QtCore.QTimer()
    watchdog.setInterval(80)
    watchdog.timeout.connect(close_messages)
    watchdog.start()

    def command(name, dialog_name, values, cancel=False, invalid=False, expected_error=False):
        completed, failures = [], []
        message_count = len(messages)
        timer = QtCore.QTimer()
        timer.setInterval(40)
        tries = [0]

        def act():
            tries[0] += 1
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None or dialog.objectName() != dialog_name:
                if tries[0] > 100:
                    timer.stop()
                    failures.append("Expected dialog did not open: " + dialog_name)
                    if dialog is not None:
                        dialog.reject()
                return
            timer.stop()
            try:
                for object_name, value in values.items():
                    widget = dialog.findChild(QtCore.QObject, object_name)
                    if isinstance(widget, QtWidgets.QLineEdit):
                        widget.setText(value)
                    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                        widget.setValue(value)
                    elif isinstance(widget, QtWidgets.QComboBox):
                        widget.setCurrentIndex(value)
                    elif isinstance(widget, QtWidgets.QCheckBox):
                        widget.setChecked(value)
                    else:
                        raise AssertionError("Missing or unsupported widget: " + object_name)
                if invalid:
                    dialog.findChild(QtWidgets.QPushButton, "acceptButton").click()
                    error = dialog.findChild(QtWidgets.QLabel, "validationMessage")
                    if not dialog.isVisible() or not error.text():
                        raise AssertionError("Invalid form did not stay open with explanation")
                action = "cancelButton" if cancel or invalid else "acceptButton"
                dialog.findChild(QtWidgets.QPushButton, action).click()
                completed.append(True)
            except BaseException as error:
                failures.append(str(error))
                dialog.reject()

        timer.timeout.connect(act)
        timer.start()
        Gui.runCommand(name)
        timer.stop()
        if failures:
            raise AssertionError(failures[0])
        if not completed:
            raise AssertionError("Command did not complete expected dialog: " + name)
        new_messages = messages[message_count:]
        if expected_error:
            if len(new_messages) != 1:
                raise AssertionError("Expected one rejected-command message: " + name)
            expected_errors.append({"command": name, "message": new_messages[0]})
        elif new_messages:
            raise AssertionError("Unexpected command error: " + new_messages[0])
        Gui.updateGui()

    def opening_point(wall, door):
        # Independently derive a point in the opening from the authored axis.
        dx = wall.EndX.Value - wall.StartX.Value
        dy = wall.EndY.Value - wall.StartY.Value
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        along = door.Offset.Value + door.Width.Value / 2.0
        depth = wall.Thickness.Value / 2.0
        z = wall.BaseLevel.Elevation.Value + wall.BaseOffset.Value + door.Sill.Value + door.Height.Value / 2.0
        return App.Vector(wall.StartX.Value + ux * along - uy * depth,
                          wall.StartY.Value + uy * along + ux * depth, z)

    try:
        check("installed workbench discovered", "BIM3117Workbench" in Gui.listWorkbenches())
        before = set(App.listDocuments())
        Gui.activateWorkbench("BIM3117Workbench")
        check("activation does not create documents", before == set(App.listDocuments()))
        required = {"BIM3117_CreateProject", "BIM3117_CreateWallType", "BIM3117_CreateWall",
                    "BIM3117_CreateDoor", "BIM3117_EditSelected", "BIM3117_DeleteSelected"}
        check("architecture commands registered", required.issubset(set(Gui.listCommands())))
        from bim3117_freecad import services

        command("BIM3117_CreateProject", "ProjectDialog", {
            "nameEdit": "3117 Architecture Demo", "projectNumberEdit": "ARCH-002",
            "authorEdit": "3117 BIM Studio", "initialLevelsCheck": True,
            "baseElevationInput": 0, "upperElevationInput": 3000,
        })
        doc = App.ActiveDocument
        project = services.get_project(doc)
        lower, upper = services.list_levels(project)
        check("project created through GUI", doc.Name not in original_documents and doc.UndoCount == 1)
        before_state = (doc.UndoCount, len(doc.Objects))
        command("BIM3117_CreateWallType", "WallTypeDialog", {"nameEdit": ""}, invalid=True)
        check("invalid type form cancels without mutation", before_state == (doc.UndoCount, len(doc.Objects)))
        command("BIM3117_CreateWallType", "WallTypeDialog", {
            "nameEdit": "WT-200 | Uniform wall", "thicknessInput": 200, "materialEdit": "Generic masonry",
        })
        wall_type = services.list_wall_types(project)[0]
        check("type form commits shared thickness and material in one transaction",
              doc.UndoCount == before_state[0] + 1 and near(wall_type.Thickness.Value, 200)
              and wall_type.Material == "Generic masonry")

        command("BIM3117_CreateWall", "WallDialog", {
            "nameEdit": "W01 | Front wall", "startXInput": -3000, "startYInput": -2000,
            "endXInput": 3000, "endYInput": -2000,
        })
        wall_a = services.list_walls(project)[0]
        body_a = services.wall_body(wall_a)
        check("wall form creates valid level-bound solid",
              wall_a.WallType == wall_type and wall_a.BaseLevel == lower and wall_a.TopLevel == upper
              and body_a.Shape.isValid() and len(body_a.Shape.Solids) == 1
              and near(body_a.Shape.Volume, 3_600_000_000))
        command("BIM3117_CreateWall", "WallDialog", {
            "nameEdit": "W02 | Return wall", "startXInput": 3400, "startYInput": -2000,
            "endXInput": 3400, "endYInput": 2000,
        })
        wall_b = services.list_walls(project)[1]
        body_b = services.wall_body(wall_b)
        check("second wall shares type with independent axis",
              wall_b.WallType == wall_type and near(wall_b.Length.Value, 4000)
              and near(body_b.Shape.Volume, 2_400_000_000))

        select(body_a)
        command("BIM3117_CreateDoor", "DoorDialog", {
            "nameEdit": "D01 | Entrance", "doorOffsetInput": 1200, "widthInput": 900, "heightInput": 2100,
        })
        door_a = services.list_doors(project)[0]
        check("body selection resolves host and cuts a real opening",
              door_a.Host == wall_a and door_a in body_a.Openings
              and near(body_a.Shape.Volume, 3_222_000_000)
              and not body_a.Shape.isInside(opening_point(wall_a, door_a), 1e-6, True))
        wall_b.ViewObject.Visibility = False
        select(wall_b)
        command("BIM3117_CreateDoor", "DoorDialog", {
            "nameEdit": "D02 | Side access", "doorOffsetInput": 2400, "widthInput": 800, "heightInput": 2100,
        })
        door_b = services.list_doors(project)[1]
        check("door follows perpendicular host axis", door_b.Host == wall_b
              and near(body_b.Shape.Volume, 2_064_000_000)
              and not body_b.Shape.isInside(opening_point(wall_b, door_b), 1e-6, True))
        check("new door inherits hidden host visibility", not wall_b.ViewObject.Visibility
              and not body_b.ViewObject.Visibility and not door_b.ViewObject.Visibility)
        wall_b.ViewObject.Visibility = True
        check("architecture view providers are attached",
              wall_type.ViewObject.Proxy.__class__.__name__ == "WallTypeViewProvider"
              and wall_a.ViewObject.Proxy.__class__.__name__ == "WallViewProvider"
              and body_a.ViewObject.Proxy.__class__.__name__ == "WallBodyViewProvider"
              and door_a.ViewObject.Proxy.__class__.__name__ == "DoorViewProvider")
        check("new authored wall and displayed subtree have consistent visibility",
              wall_a.ViewObject.Visibility and body_a.ViewObject.Visibility and door_a.ViewObject.Visibility
              and wall_a.ViewObject.isVisible() and wall_a.ViewObject.DisplayMode == "Default"
              and wall_b.ViewObject.Visibility and body_b.ViewObject.Visibility and door_b.ViewObject.Visibility)
        select(wall_a)
        Gui.runCommand("Std_ToggleVisibility")
        check("first native Space-equivalent toggle hides wall solid and hosted door",
              not wall_a.ViewObject.Visibility and not body_a.ViewObject.Visibility
              and not door_a.ViewObject.Visibility and wall_b.ViewObject.Visibility)
        Gui.runCommand("Std_ToggleVisibility")
        check("second native Space-equivalent toggle shows wall solid and hosted door",
              wall_a.ViewObject.Visibility and body_a.ViewObject.Visibility and door_a.ViewObject.Visibility)

        ids = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        select(wall_type)
        before_undo = doc.UndoCount
        command("BIM3117_EditSelected", "WallTypeDialog", {
            "nameEdit": "WT-250 | Uniform wall", "thicknessInput": 250,
        })
        check("type edit updates both wall solids in one transaction", doc.UndoCount == before_undo + 1
              and near(body_a.Shape.Volume, 4_027_500_000) and near(body_b.Shape.Volume, 2_580_000_000))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("native Undo restores type and both cut solids", near(wall_type.Thickness.Value, 200)
              and near(body_a.Shape.Volume, 3_222_000_000) and near(body_b.Shape.Volume, 2_064_000_000))
        Gui.runCommand("Std_Redo")
        doc.recompute()
        check("native Redo restores type without changing identities",
              near(body_a.Shape.Volume, 4_027_500_000) and ids == {obj.Name: obj.BIM3117Id for obj in doc.Objects})

        select(upper)
        command("BIM3117_EditSelected", "LevelDialog", {"elevationInput": 3300})
        check("level form recomputes both walls with hosted openings", near(wall_a.Height.Value, 3300)
              and near(body_a.Shape.Volume, 4_477_500_000) and near(body_b.Shape.Volume, 2_880_000_000))
        before_invalid = (doc.UndoCount, upper.Elevation.Value, body_a.Shape.Volume, len(doc.Objects))
        command("BIM3117_EditSelected", "LevelDialog", {"elevationInput": 1000}, expected_error=True)
        check("downstream-invalid level edit rolls back complete command",
              before_invalid == (doc.UndoCount, upper.Elevation.Value, body_a.Shape.Volume, len(doc.Objects)))

        select(body_a)
        command("BIM3117_EditSelected", "WallDialog", {
            "startXInput": -3000, "startYInput": -2400, "endXInput": 1800, "endYInput": 1200,
        })
        check("editing selected solid moves authored axis, door and opening",
              near(wall_a.StartY.Value, -2400) and near(wall_a.EndX.Value, 1800)
              and near(wall_a.Length.Value, 6000) and near(body_a.Shape.Volume, 4_477_500_000)
              and not body_a.Shape.isInside(opening_point(wall_a, door_a), 1e-6, True))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("Undo restores rotated host and cut geometry", near(wall_a.StartY.Value, -2000)
              and near(wall_a.EndX.Value, 3000) and near(door_a.Shape.BoundBox.YMin, -2000))

        before_invalid = (doc.UndoCount, len(doc.Objects), body_a.Shape.Volume)
        command("BIM3117_CreateWall", "WallDialog", {
            "startXInput": 0, "startYInput": 0, "endXInput": 0, "endYInput": 0,
        }, invalid=True)
        select(wall_a)
        command("BIM3117_CreateDoor", "DoorDialog", {"widthInput": 20000}, invalid=True)
        check("invalid wall and door forms remain open until cancelled without mutation",
              before_invalid == (doc.UndoCount, len(doc.Objects), body_a.Shape.Volume))
        command("BIM3117_CreateDoor", "DoorDialog", {
            "nameEdit": "Overlapping door", "doorOffsetInput": 1200, "widthInput": 900, "heightInput": 2100,
        }, expected_error=True)
        check("overlapping opening command rejects without extra object or undo item",
              before_invalid == (doc.UndoCount, len(doc.Objects), body_a.Shape.Volume))

        select(door_a)
        command("BIM3117_EditSelected", "DoorDialog", {"hostWallCombo": 2})
        check("door rehost form heals previous wall and cuts new host",
              door_a.Host == wall_b and door_a not in body_a.Openings and door_a in body_b.Openings
              and near(body_a.Shape.Volume, 4_950_000_000) and near(body_b.Shape.Volume, 2_407_500_000))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("native Undo restores door host, opening lists and cut solids",
              door_a.Host == wall_a and door_a in body_a.Openings and door_a not in body_b.Openings
              and near(body_a.Shape.Volume, 4_477_500_000) and near(body_b.Shape.Volume, 2_880_000_000))
        check("wall tree groups derived body and hosted door", body_a in wall_a.ViewObject.Proxy.claimChildren()
              and door_a in wall_a.ViewObject.Proxy.claimChildren()
              and door_a not in wall_b.ViewObject.Proxy.claimChildren())

        for target, description in ((wall_a, "wall"), (body_a, "derived wall body"),
                                    (door_a, "hosted door"), (wall_type, "used type"), (lower, "referenced base level")):
            select(target)
            before_delete = (len(doc.Objects), doc.UndoCount)
            warning_count = len(deletion_warnings)
            target_name = target.Name
            deletion_mode[0] = True
            try:
                Gui.runCommand("Std_Delete")
            finally:
                deletion_mode[0] = False
            check("native Delete veto preserves " + description,
                  len(deletion_warnings) > warning_count and doc.getObject(target_name) is not None
                  and before_delete == (len(doc.Objects), doc.UndoCount))

        door_name, door_id = door_a.Name, door_a.BIM3117Id
        select(door_a)
        before_undo = doc.UndoCount
        Gui.runCommand("BIM3117_DeleteSelected")
        check("Delete Selected removes door and heals wall in one transaction",
              doc.getObject(door_name) is None and len(body_a.Openings) == 0
              and near(body_a.Shape.Volume, 4_950_000_000) and doc.UndoCount == before_undo + 1)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        door_a = doc.getObject(door_name)
        check("Undo deletion restores same door identity and opening",
              door_a.BIM3117Id == door_id and door_a.Host == wall_a and door_a in body_a.Openings
              and near(body_a.Shape.Volume, 4_477_500_000))
        Gui.runCommand("Std_Redo")
        doc.recompute()
        check("Redo deletion heals wall again", doc.getObject(door_name) is None
              and near(body_a.Shape.Volume, 4_950_000_000))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        door_a = doc.getObject(door_name)
        select(door_a)
        command("BIM3117_EditSelected", "DoorDialog", {"widthInput": 1000})
        check("door dimension edit updates cut and clears old redo branch",
              near(body_a.Shape.Volume, 4_425_000_000) and doc.RedoCount == 0)
        Gui.runCommand("Std_Undo")
        doc.recompute()

        for label, axis, position, length in (("A", 0, -2500, 10000), ("1", 1, -3500, 8000)):
            command("BIM3117_CreateGrid", "GridDialog", {
                "nameEdit": "Grid " + label, "bubbleEdit": label, "axisCombo": axis,
                "positionInput": position, "lengthInput": length, "referenceLevelCombo": 1,
            })
        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        check("complete architecture document validates", services.validate_document(doc, check_shapes=True))
        saved = output / "ตัวอย่าง_3117" / "Architecture_Workbench.FCStd"
        saved.parent.mkdir(parents=True, exist_ok=True)
        # View settings are presentation only; leave the cut geometry visible.
        for level in services.list_levels(project):
            level.ViewObject.Visibility = False
        doc.saveAs(str(saved))
        wall_name, body_name = wall_a.Name, body_a.Name
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(saved))
        sample_doc = doc
        doc.recompute()
        wall_a, body_a, door_a = doc.getObject(wall_name), doc.getObject(body_name), doc.getObject(door_name)
        check("GUI save and reopen preserves UUIDs and native host dependencies",
              identifiers == {obj.Name: obj.BIM3117Id for obj in doc.Objects}
              and door_a.Host == wall_a and door_a in body_a.Openings)
        check("GUI reopen restores view providers and actual hole",
              wall_a.ViewObject.Proxy.__class__.__name__ == "WallViewProvider"
              and body_a.ViewObject.Proxy.__class__.__name__ == "WallBodyViewProvider"
              and door_a.ViewObject.Proxy.__class__.__name__ == "DoorViewProvider"
              and near(body_a.Shape.Volume, 4_477_500_000)
              and not body_a.Shape.isInside(opening_point(wall_a, door_a), 1e-6, True))
        check("GUI reopen preserves visible authored wall and subtree",
              wall_a.ViewObject.Visibility and wall_a.ViewObject.isVisible()
              and body_a.ViewObject.Visibility and door_a.ViewObject.Visibility)
        check("native document valid after GUI lifecycle", services.validate_document(doc, check_shapes=True))

        # A user's separate Door visibility is not authoring state. Restoration
        # must preserve it rather than reset all children from the parent.
        door_a.ViewObject.Visibility = False
        doc.save()
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(saved))
        sample_doc = doc
        doc.recompute()
        wall_a, body_a, door_a = doc.getObject(wall_name), doc.getObject(body_name), doc.getObject(door_name)
        check("GUI reopen preserves an independently hidden door under a visible wall",
              wall_a.ViewObject.Visibility and wall_a.ViewObject.isVisible()
              and body_a.ViewObject.Visibility and not door_a.ViewObject.Visibility)
        door_a.ViewObject.Visibility = True

        Gui.getMainWindow().resize(1440, 1000)
        select(wall_a)
        for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            tree.expandAll()
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()
        screenshot = output / "Architecture_Workbench.png"
        check("actual FreeCAD GUI screenshot saved", Gui.getMainWindow().grab().save(str(screenshot)))
        doc.save()
        report.update(status="passed", checks_passed=len(checks), sample=str(saved), screenshot=str(screenshot),
                      identifiers=identifiers, module_source=services.__file__, elements=len(doc.Objects),
                      sample_wall=wall_name, sample_door=door_name,
                      wall_a_net_volume_mm3=body_a.Shape.Volume)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        watchdog.stop()
        (output / "architecture-gui-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        for name in set(App.listDocuments()) - original_documents:
            if keep_sample and report["status"] == "passed" and sample_doc is not None and name == sample_doc.Name:
                continue
            App.closeDocument(name)
        if original_active and not keep_sample:
            App.setActiveDocument(original_active)
    return report
