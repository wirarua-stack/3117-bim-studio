# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise installed commands and real modal widgets in FreeCAD GUI.

Run only on a development/test FreeCAD profile. Only documents created by this
suite are changed/closed. Existing documents are not edited. No mock FreeCAD or
Qt modules are used. `run` may be invoked by the supplied smoke-test macro.
"""
import json
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
    checks, notices = [], []
    report = {"freecad": App.Version(), "python": sys.version, "platform": platform.platform(),
              "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp), "status": "running",
              "checks": checks, "dialog_errors": notices}
    sample_doc = None
    deletion_mode = [False]
    deletion_warnings = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def near(a, b):
        return abs(a-b) < 1e-6

    def close_errors():
        modal = QtWidgets.QApplication.activeModalWidget()
        if isinstance(modal, QtWidgets.QMessageBox):
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
                return
            notices.append(modal.text())
            modal.accept()

    watchdog = QtCore.QTimer()
    watchdog.setInterval(80)
    watchdog.timeout.connect(close_errors)
    watchdog.start()

    def command(command_name, dialog_name, values, cancel=False, invalid=False):
        completed, failures = [], []
        timer = QtCore.QTimer()
        timer.setInterval(40)
        tries = [0]

        def act():
            tries[0] += 1
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None or dialog.objectName() != dialog_name:
                if tries[0] > 100:
                    timer.stop()
                    failures.append("Expected modal dialog did not open: " + dialog_name)
                    if dialog is not None:
                        dialog.reject()
                return
            timer.stop()
            try:
                for name, value in values.items():
                    widget = dialog.findChild(QtCore.QObject, name)
                    if widget is None:
                        raise AssertionError("Missing widget: " + name)
                    if isinstance(widget, QtWidgets.QLineEdit):
                        widget.setText(value)
                    elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                        widget.setValue(value)
                    elif isinstance(widget, QtWidgets.QComboBox):
                        widget.setCurrentIndex(value)
                    elif isinstance(widget, QtWidgets.QCheckBox):
                        widget.setChecked(value)
                    else:
                        raise AssertionError("Unsupported widget: " + name)
                if invalid:
                    dialog.findChild(QtWidgets.QPushButton, "acceptButton").click()
                    message = dialog.findChild(QtWidgets.QLabel, "validationMessage")
                    check("invalid form stays open with inline explanation",
                          dialog.isVisible() and bool(message.text()))
                button = "cancelButton" if cancel or invalid else "acceptButton"
                dialog.findChild(QtWidgets.QPushButton, button).click()
                completed.append(True)
            except BaseException as error:
                failures.append(str(error))
                dialog.reject()

        timer.timeout.connect(act)
        timer.start()
        Gui.runCommand(command_name)
        timer.stop()
        if failures:
            raise AssertionError(failures[0])
        if not completed:
            raise AssertionError("Command did not run its expected dialog: " + command_name)
        if notices:
            raise AssertionError("Unexpected command error: " + notices[-1])
        Gui.updateGui()

    try:
        check("installed workbench discovered", "BIM3117Workbench" in Gui.listWorkbenches())
        before = set(App.listDocuments())
        Gui.activateWorkbench("BIM3117Workbench")
        check("workbench activation does not create documents", before == set(App.listDocuments()))
        expected_commands = {"BIM3117_CreateProject", "BIM3117_AddLevel", "BIM3117_CreateGrid",
                             "BIM3117_EditSelected", "BIM3117_HostInfo"}
        check("all five commands registered", expected_commands.issubset(set(Gui.listCommands())))
        from bim3117_freecad import services

        command("BIM3117_CreateProject", "ProjectDialog", {
            "nameEdit": "3117 Foundation Demo", "projectNumberEdit": "FND-001",
            "authorEdit": "3117 BIM Studio", "initialLevelsCheck": True,
            "baseElevationInput": 0, "upperElevationInput": 3000,
        })
        doc = App.ActiveDocument
        check("create project command creates new native document", doc.Name not in original_documents)
        project = services.get_project(doc)
        lower, upper = services.list_levels(project)
        check("create project dialog commits one undo item and two levels",
              doc.UndoCount == 1 and len(project.Group) == 2 and near(upper.Elevation.Value, 3000))

        before_undo, before_count = doc.UndoCount, len(doc.Objects)
        command("BIM3117_AddLevel", "LevelDialog", {"nameEdit": ""}, invalid=True)
        check("cancelled invalid form does not change model or history",
              (doc.UndoCount, len(doc.Objects)) == (before_undo, before_count))
        command("BIM3117_AddLevel", "LevelDialog", {"nameEdit": "L02 Roof", "elevationInput": 6000})
        check("add level dialog commits one undo item", doc.UndoCount == before_undo+1)

        axes = [("A", 0, -4000, 16000), ("B", 0, 0, 16000), ("C", 0, 4000, 16000),
                ("1", 1, -6000, 12000), ("2", 1, 0, 12000), ("3", 1, 6000, 12000)]
        for label, axis, position, length in axes:
            command("BIM3117_CreateGrid", "GridDialog", {
                "nameEdit": "Grid " + label, "bubbleEdit": label, "axisCombo": axis,
                "positionInput": position, "lengthInput": length,
                "referenceLevelCombo": 1, "offsetInput": 0,
            })
        command("BIM3117_CreateGrid", "GridDialog", {
            "nameEdit": "Grid L01-A", "bubbleEdit": "A", "axisCombo": 0,
            "positionInput": -4000, "lengthInput": 16000,
            "referenceLevelCombo": 2, "offsetInput": 0,
        })
        grids = services.list_grids(project)
        dependent = grids[-1]
        check("grid dialogs create X and Y geometry with reference levels",
              len(grids) == 7 and dependent.ReferenceLevel == upper
              and near(dependent.Shape.BoundBox.ZMin, 3000)
              and all(len(grid.Shape.Edges) == 3 for grid in grids))
        check("grid labels have native GUI view providers",
              all(grid.ViewObject.Proxy.__class__.__name__ == "GridViewProvider" for grid in grids))
        upper_id = upper.BIM3117Id
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, upper.Name)
        before_undo = doc.UndoCount
        command("BIM3117_EditSelected", "LevelDialog", {
            "nameEdit": "L01 First Floor", "elevationInput": 3300, "spanXInput": 14000,
        })
        check("edit selected form commits multiple fields as one native transaction",
              doc.UndoCount == before_undo+1 and upper.Label == "L01 First Floor"
              and near(upper.Elevation.Value, 3300) and near(upper.SpanX.Value, 14000))
        check("linked grid follows level edit", near(dependent.Shape.BoundBox.ZMin, 3300))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("native Undo command restores form edit and dependent geometry",
              upper.Label == "L01" and near(upper.Elevation.Value, 3000)
              and near(dependent.Shape.BoundBox.ZMin, 3000))
        Gui.runCommand("Std_Redo")
        doc.recompute()
        check("native Redo command restores geometry without changing UUID",
              upper.BIM3117Id == upper_id and near(dependent.Shape.BoundBox.ZMin, 3300))
        check("label scene nodes track level after native Undo and Redo",
              hasattr(dependent.ViewObject.Proxy, "_labels") and
              near(dependent.ViewObject.Proxy._labels[0][0].translation.getValue()[2], 3300))

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, dependent.Name)
        command("BIM3117_EditSelected", "GridDialog", {"bubbleEdit": "A1"})
        check("grid edit preserves its preselected reference level",
              dependent.ReferenceLevel == upper and dependent.BubbleLabel == "A1")
        check("view label text follows native property",
              str(dependent.ViewObject.Proxy._labels[0][1].string.getValues()[0]) == "A1")

        # Use the native Delete command so FreeCAD must invoke the provider's
        # veto; only this suite's temporary objects are selected.
        for target, title in ((upper, "referenced level"), (project, "nonempty project")):
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(doc.Name, target.Name)
            before_delete = (len(doc.Objects), doc.UndoCount)
            warning_count = len(deletion_warnings)
            deletion_mode[0] = True
            try:
                Gui.runCommand("Std_Delete")
            finally:
                deletion_mode[0] = False
            check("native Delete veto preserves " + title,
                  len(deletion_warnings) > warning_count and
                  before_delete == (len(doc.Objects), doc.UndoCount) and
                  doc.getObject(target.Name) is not None and dependent.ReferenceLevel == upper)

        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        saved = output / "ตัวอย่าง_3117" / "Foundation_Workbench.FCStd"
        saved.parent.mkdir(parents=True, exist_ok=True)
        doc.recompute()
        doc.saveAs(str(saved))
        grid_name, upper_name = dependent.Name, upper.Name
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(saved))
        sample_doc = doc
        doc.recompute()
        check("GUI save and reopen preserves all element identities",
              identifiers == {obj.Name: obj.BIM3117Id for obj in doc.Objects})
        dependent, upper = doc.getObject(grid_name), doc.getObject(upper_name)
        check("GUI reopen restores view provider and dependency",
              dependent.ViewObject.Proxy.__class__.__name__ == "GridViewProvider"
              and dependent.ReferenceLevel == upper and near(dependent.Shape.BoundBox.ZMin, 3300))
        check("GUI reopen reconstructs label text and position",
              hasattr(dependent.ViewObject.Proxy, "_labels") and
              str(dependent.ViewObject.Proxy._labels[0][1].string.getValues()[0]) == "A1" and
              near(dependent.ViewObject.Proxy._labels[0][0].translation.getValue()[2], 3300))
        check("native document remains valid after GUI lifecycle", services.validate_document(doc, check_shapes=True))

        # Capture actual FreeCAD widgets/viewport; this is not a drawn UI mockup.
        Gui.getMainWindow().resize(1440, 1000)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, upper.Name)
        for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            tree.expandAll()
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()
        screenshot = output / "Foundation_Workbench.png"
        check("actual GUI screenshot saved", Gui.getMainWindow().grab().save(str(screenshot)))
        doc.save()
        report.update(status="passed", checks_passed=len(checks), sample=str(saved), screenshot=str(screenshot),
                      module_source=services.__file__, elements=len(doc.Objects),
                      identifiers=identifiers, deletion_warnings=deletion_warnings)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(checks))
        raise
    finally:
        watchdog.stop()
        (output / "gui-smoke-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        for name in set(App.listDocuments()) - original_documents:
            if keep_sample and sample_doc is not None and name == sample_doc.Name and report["status"] == "passed":
                continue
            App.closeDocument(name)
        if original_active and not keep_sample:
            App.setActiveDocument(original_active)
    return report
