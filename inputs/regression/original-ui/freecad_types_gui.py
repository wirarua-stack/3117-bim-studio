# SPDX-License-Identifier: GPL-3.0-or-later
"""Real installed-host catalogue and editable schedule widget workflow.

Use a deferred GUI macro and a disposable output folder. The frozen v0.3
building is copied before editing. Native commands/actions are never replaced.
"""

import csv
import hashlib
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

from freecad_building_gui import GuiDriver, near, wait_until


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def installed_ui_fingerprint():
    import ui3117
    root = Path(ui3117.__file__).resolve().parent
    return {"root": str(root), "sha256": {
        path.relative_to(root).as_posix(): file_hash(path) for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in (".py", ".svg")}}


def exercise_panel_coexistence(driver, project, panel, check, report):
    """Public macro gate: readers settle, and genuine edits still reach both."""
    from bim3117_freecad import catalog, schedules
    from ui3117.exchange_dialog import panel_for_document
    driver.command("BIM3117_Quantities")
    quantities = panel_for_document(project.Document.Name)
    doc = project.Document
    try:
        settled = lambda: (not panel._dirty and not quantities._dirty and not panel._timer.isActive()
                           and not quantities.refresh_timer.isActive())
        check("coexisting Schedules and Quantities settle without a read-refresh loop", wait_until(settled, seconds=30))
        baseline = panel.source_snapshot["model_revision"]
        element_type = next(obj for obj in catalog.list_types(project, "Column") if catalog.type_dependents(obj))
        width = element_type.Width.Value
        driver.select(element_type)
        driver.command("BIM3117_EditSelected", "ElementTypeDialog", {"widthInput": width + 10})
        def agrees(revision):
            return (settled() and panel.source_snapshot["model_revision"] == revision
                    and quantities.source_snapshot["content_revision"] == revision)
        changed_revision = schedules.schedule_state(panel._schedule())["model_revision"]
        changed = changed_revision != baseline and wait_until(lambda: agrees(changed_revision), seconds=30)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        undone = wait_until(lambda: agrees(baseline), seconds=30)
        Gui.runCommand("Std_Redo")
        doc.recompute()
        redone = wait_until(lambda: agrees(changed_revision), seconds=30)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        restored = wait_until(lambda: agrees(baseline), seconds=30)
        check("both open readers follow one real type edit and native Undo/Redo", changed and undone and redone
              and restored and near(element_type.Width.Value, width))
        report["coexisting_panel_edit_roundtrip"] = {"model_revision": baseline,
            "changed_revision": changed_revision, "edit": changed, "undo": undone, "redo": redone, "restored": restored}
    finally:
        quantities.close()


class TypesGuiDriver(GuiDriver):
    def _messages(self):
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None and modal.objectName() == "BIM3117ScheduleOverwriteDialog":
            return
        super()._messages()

    @staticmethod
    def enter(dialog, values):
        for name, value in values.items():
            widget = dialog.findChild(QtCore.QObject, name)
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QtWidgets.QDoubleSpinBox):
                widget.setValue(value)
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QtWidgets.QComboBox):
                if isinstance(value, int):
                    index = value
                else:
                    label = value.Label if hasattr(value, "Label") else str(value)
                    index = next((i for i in range(widget.count()) if widget.itemText(i) == label
                                  or widget.itemText(i).startswith(label + "  ")), -1)
                if index < 0:
                    raise AssertionError("Missing combo choice: " + str(value))
                widget.setCurrentIndex(index)
            else:
                raise AssertionError("Missing form widget: " + name)

    def action(self, callback, dialog_name=None, values=None, setup=None, cancel=False, expected_error=False):
        completed, failures = [], []
        before = len(self.messages)
        timer = QtCore.QTimer()
        timer.setInterval(35)
        attempts = [0]

        def interact():
            attempts[0] += 1
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is None or modal.objectName() != dialog_name:
                if attempts[0] > 250:
                    failures.append("Expected form did not open: " + str(dialog_name))
                    timer.stop()
                    if modal is not None:
                        modal.reject()
                return
            timer.stop()
            try:
                self.enter(modal, values or {})
                if setup:
                    setup(modal)
                modal.findChild(QtWidgets.QPushButton, "cancelButton" if cancel else "acceptButton").click()
                completed.append(True)
            except BaseException as error:
                failures.append(str(error))
                modal.reject()

        if dialog_name:
            timer.timeout.connect(interact)
            timer.start()
        callback()
        timer.stop()
        if failures:
            raise AssertionError(failures[0])
        if dialog_name and not completed:
            raise AssertionError("Form did not complete: " + dialog_name)
        messages = self.messages[before:]
        if expected_error:
            if len(messages) != 1:
                raise AssertionError("Expected one rejection, got " + repr(messages))
            self.errors.append({"command": "panel action", "message": messages[0]})
        elif messages:
            raise AssertionError("Unexpected GUI error: " + messages[0])
        Gui.updateGui()

    def export_schedule(self, panel, path, overwrite=None, cancel_file=False, before_accept=None, expected_error=False):
        state = {"file_dialog": False, "overwrite_dialog": False, "overwrite_text": ""}
        failures, attempts = [], [0]
        before = len(self.messages)
        timer = QtCore.QTimer()
        timer.setInterval(40)

        def interact():
            attempts[0] += 1
            modal = QtWidgets.QApplication.activeModalWidget()
            if attempts[0] > 300:
                timer.stop()
                failures.append("Schedule export dialogs timed out")
                if modal:
                    modal.reject()
                return
            if modal is None:
                return
            try:
                if modal.objectName() == "BIM3117ScheduleExportFileDialog" and not state["file_dialog"]:
                    state["file_dialog"] = True
                    if cancel_file:
                        modal.reject()
                    else:
                        modal.setDirectory(str(path.parent))
                        modal.selectFile(str(path))
                        entry = modal.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                        if entry:
                            entry.setText(str(path))
                        if before_accept:
                            before_accept()
                        QtCore.QTimer.singleShot(70, modal.accept)
                elif modal.objectName() == "BIM3117ScheduleOverwriteDialog":
                    state["overwrite_dialog"] = True
                    state["overwrite_text"] = modal.text()
                    if overwrite is None:
                        raise AssertionError("Unexpected overwrite confirmation")
                    modal.button(QtWidgets.QMessageBox.Yes if overwrite else QtWidgets.QMessageBox.No).click()
            except BaseException as error:
                failures.append(str(error))
                modal.reject()

        timer.timeout.connect(interact)
        timer.start()
        panel.export_button.click()
        timer.stop()
        if failures:
            raise AssertionError(failures[0])
        messages = self.messages[before:]
        if expected_error:
            if len(messages) != 1:
                raise AssertionError("Expected one stale export rejection, got " + repr(messages))
            self.errors.append({"command": "schedule export", "message": messages[0]})
        elif messages:
            raise AssertionError(messages[0])
        if not state["file_dialog"]:
            raise AssertionError("File dialog did not open: " + str(panel.last_error))
        return state


def run(output_dir, keep_sample=False):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "examples/building/Building_Authoring_Workbench.FCStd"
    source_hash = file_hash(source)
    sample = output / "Types_Quantities_Workbench.FCStd"
    sample.write_bytes(source.read_bytes())
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp),
              "checks": checks, "scope": "Installed actual catalogue, layers, type fanout, schedule source edits and CSV"}
    driver = TypesGuiDriver(report)
    doc = catalogue = panel = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def history():
        return doc.UndoCount, doc.RedoCount, len(doc.Objects)

    def undo():
        Gui.runCommand("Std_Undo")
        doc.recompute()
        Gui.updateGui()

    def redo():
        Gui.runCommand("Std_Redo")
        doc.recompute()
        Gui.updateGui()

    def choose_type(obj):
        catalogue.category_combo.setCurrentText("All")
        catalogue.refresh()
        index = next(i for i, value in enumerate(catalogue._types) if value.BIM3117Id == obj.BIM3117Id)
        catalogue.types_table.selectRow(index)

    def choose_row(obj):
        panel.refresh()
        index = next(i for i, value in enumerate(panel.source_snapshot["rows"])
                     if str(obj.BIM3117Id) in value["element_ids"])
        panel.table.selectRow(index)

    try:
        Gui.activateWorkbench("BIM3117Workbench")
        from bim3117_freecad import catalog, schedules, services, snapshot
        from ui3117 import viewproviders
        from ui3117.catalog_panel import panel_for_document as catalogue_for_document
        from ui3117.schedule_panel import panel_for_document as schedule_for_document
        required = {"BIM3117_Catalogue", "BIM3117_CreateMaterial", "BIM3117_CreateType", "BIM3117_AssignType",
                    "BIM3117_DetachType", "BIM3117_Schedules", "BIM3117_CreateSchedule"}
        check("all type/material/schedule commands register", required.issubset(set(Gui.listCommands())))
        check("production catalogue imports from installed addon", "/Mod/BIM3117/" in catalog.__file__.replace("\\", "/"))
        doc = App.openDocument(str(sample))
        doc.recompute()
        doc.UndoMode = 1
        project = services.get_project(doc)
        doc.saveAs(str(sample))
        columns = services.list_columns(project)
        slabs = services.list_slabs(project)
        beams = services.list_beams(project)
        doors = services.list_doors(project)
        windows = services.list_windows(project)
        walls = services.list_walls(project)
        original_revision = snapshot.capture(project)["content_revision"]
        before = history()
        driver.command("BIM3117_CreateMaterial", "MaterialDialog", {"nameEdit": "Cancelled"}, cancel=True)
        check("cancelling material form changes neither objects nor history", history() == before and not catalog.list_materials(project))
        for name, code in (("Concrete", "CON"), ("Finish", "FIN"), ("Metal", "MET")):
            driver.command("BIM3117_CreateMaterial", "MaterialDialog", {"nameEdit": name, "codeEdit": code})
        concrete, finish, metal = [next(obj for obj in catalog.list_materials(project) if obj.Label == name)
                                   for name in ("Concrete", "Finish", "Metal")]
        check("material creation has native identities and providers", len(catalog.list_materials(project)) == 3
              and isinstance(concrete.ViewObject.Proxy, viewproviders.MaterialViewProvider))
        before = history()
        driver.command("BIM3117_Catalogue")
        catalogue = catalogue_for_document(doc.Name)
        check("modeless catalogue opens without a model transaction", catalogue is not None and catalogue.isVisible()
              and catalogue.last_error is None and history() == before)
        driver.command("BIM3117_Catalogue")
        check("repeated Catalogue command reuses one observer/panel", catalogue_for_document(doc.Name) is catalogue)

        def layers(dialog):
            dialog.findChild(QtWidgets.QCheckBox, "useLayersCheck").setChecked(True)
            dialog.findChild(QtWidgets.QPushButton, "addLayerButton").click()
            dialog.findChild(QtWidgets.QPushButton, "addLayerButton").click()
            table = dialog.findChild(QtWidgets.QTableWidget, "typeLayersTable")
            for row, material, thickness, role in ((0, concrete, 160, "Structure"), (1, finish, 40, "Finish")):
                combo = table.cellWidget(row, 0)
                combo.setCurrentIndex(combo.findText(material.Label))
                table.cellWidget(row, 1).setValue(thickness)
                table.cellWidget(row, 2).setText(role)
            check("layer sum is a disabled total in the type form", near(dialog.dimensions["thickness_mm"].value(), 200)
                  and not dialog.dimensions["thickness_mm"].isEnabled())
            dialog.layers_table.selectRow(1)
            dialog.findChild(QtWidgets.QPushButton, "moveLayerUpButton").click()
            dialog.findChild(QtWidgets.QPushButton, "moveLayerDownButton").click()
        driver.action(catalogue.newTypeButton.click, "ElementTypeDialog", {
            "nameEdit": "Slab Composite 200", "typeCategoryCombo": "Slab", "codeEdit": "SL200"}, setup=layers)
        slab_type = next(obj for obj in catalog.list_types(project, "Slab") if obj.Label == "Slab Composite 200")
        check("ordered native layers persist their selected materials and thicknesses", slab_type.LayerMaterials == [concrete, finish]
              and list(slab_type.LayerThicknesses) == [160, 40] and near(slab_type.Thickness.Value, 200))
        types = {"Slab": slab_type}
        firsts = {"Column": columns[0], "Beam": beams[0], "Door": doors[0], "Window": windows[0]}
        for category, obj in firsts.items():
            values = {"typeCategoryCombo": category, "nameEdit": category + " Shared", "typeMaterialCombo": metal}
            for prop in (("Width", "Height") if category in ("Door", "Window") else ("Width", "Depth")):
                values[prop.lower() + "Input"] = getattr(obj, prop).Value
            driver.command("BIM3117_CreateType", "ElementTypeDialog", values)
            types[category] = next(item for item in catalog.list_types(project, category) if item.Label == category + " Shared")
        check("all five new typed categories use native ElementType providers", all(
            isinstance(obj.ViewObject.Proxy, viewproviders.ElementTypeViewProvider) for obj in types.values()))
        choose_type(types["Column"])
        driver.select(columns[0], columns[1])
        before = doc.UndoCount
        catalogue.assignTypeButton.click()
        check("catalogue assigns multiple selected instances in one Undo", all(obj.ElementType == types["Column"] for obj in columns[:2])
              and doc.UndoCount == before + 1)
        check("catalogue row selection preserves the model selection", set(Gui.Selection.getSelection()) == set(columns[:2]))
        for category, objects in (("Slab", slabs), ("Beam", beams), ("Door", doors), ("Window", windows)):
            driver.select(*objects)
            driver.command("BIM3117_AssignType", "AssignTypeDialog", {"assignTypeCombo": types[category]})
        check("all five categories retain native type references", all(obj.ElementType == types[category]
              for category, objects in (("Slab", slabs), ("Beam", beams), ("Door", doors), ("Window", windows)) for obj in objects))

        driver.select(columns[0])
        before = history()
        observed = {}
        def inspect_locked(dialog):
            observed["locked"] = (not dialog.findChild(QtWidgets.QDoubleSpinBox, "widthInput").isEnabled()
                                  and not dialog.findChild(QtWidgets.QDoubleSpinBox, "depthInput").isEnabled()
                                  and not dialog.findChild(QtWidgets.QLineEdit, "materialEdit").isEnabled()
                                  and bool(dialog.findChild(QtWidgets.QLabel, "assignedTypeLabel").text()))
        driver.action(lambda: Gui.runCommand("BIM3117_EditSelected"), "ColumnDialog", setup=inspect_locked, cancel=True)
        check("typed instance edit form displays type and locks shared dimensions/material", observed.get("locked") and history() == before)
        choose_type(types["Column"])
        width = types["Column"].Width.Value
        before = doc.UndoCount
        driver.action(catalogue.editTypeButton.click, "ElementTypeDialog", {"widthInput": width + 50})
        check("type edit updates both instances and solids in one transaction", all(near(obj.Width.Value, width + 50) for obj in columns[:2])
              and doc.UndoCount == before + 1 and all(obj.Shape.isValid() for obj in columns[:2]))
        undo()
        check("one native Undo restores type and all dependent instances", all(near(obj.Width.Value, width) for obj in columns[:2]))
        redo()
        check("native Redo restores shared type fanout", all(near(obj.Width.Value, width + 50) for obj in columns[:2]))

        driver.select(types["Door"])
        door_width = types["Door"].Width.Value
        driver.command("BIM3117_EditSelected", "ElementTypeDialog", {"widthInput": door_width + 50})
        undo()
        before, revision = history(), snapshot.capture(project)["content_revision"]
        driver.select(types["Door"])
        driver.command("BIM3117_EditSelected", "ElementTypeDialog", {"widthInput": 90000}, expected_error=True)
        check("invalid shared opening edit preserves state and existing Redo", history() == before
              and snapshot.capture(project)["content_revision"] == revision and doc.RedoCount > 0)
        redo()
        check("Redo remains usable after rejected type edit", near(doors[0].Width.Value, door_width + 50))
        undo()

        driver.select(columns[0])
        before = doc.UndoCount
        driver.command("BIM3117_DetachType")
        check("detach retains current dimensions in one transaction", columns[0].ElementType is None
              and near(columns[0].Width.Value, width + 50) and doc.UndoCount == before + 1)
        undo()
        check("Undo restores the detached type link", columns[0].ElementType == types["Column"])
        choose_type(types["Column"])
        driver.action(catalogue.duplicateTypeButton.click, "DuplicateTypeDialog", {"nameEdit": "Column Alternative"})
        alternative = next(obj for obj in catalog.list_types(project, "Column") if obj.Label == "Column Alternative")
        check("duplicate type has an independent UUID and shared material", alternative.BIM3117Id != types["Column"].BIM3117Id
              and alternative.MaterialRef == metal and near(alternative.Width.Value, width + 50))
        driver.select(alternative)
        driver.command("BIM3117_EditSelected", "ElementTypeDialog", {"widthInput": width + 100})
        check("editing a duplicate does not alter the original type", near(types["Column"].Width.Value, width + 50))

        warning = driver.native_delete(concrete)
        check("native material deletion guards referenced layers", bool(warning) and concrete in catalog.list_materials(project))
        warning = driver.native_delete(types["Column"])
        check("native type deletion guards active instances", bool(warning) and types["Column"] in catalog.list_types(project))

        before, model_revision = history(), snapshot.capture(project)["content_revision"]
        driver.command("BIM3117_CreateSchedule", "ScheduleDefinitionDialog", {
            "nameEdit": "Column Schedule", "scheduleCategoryCombo": "Column", "scheduleSortCombo": "Name"})
        column_schedule = next(obj for obj in schedules.list_schedules(project) if obj.Label == "Column Schedule")
        check("schedule creates native definition outside Project.Group in one Undo", column_schedule not in project.Group
              and doc.UndoCount == before[0] + 1 and schedules.get_schedule_set(project) not in project.Group)
        check("schedule creation preserves building content revision", snapshot.capture(project)["content_revision"] == model_revision)
        check("native Schedule providers are attached", isinstance(column_schedule.ViewObject.Proxy, viewproviders.ScheduleViewProvider)
              and isinstance(schedules.get_schedule_set(project).ViewObject.Proxy, viewproviders.ScheduleSetViewProvider))
        before = history()
        driver.command("BIM3117_Schedules")
        panel = schedule_for_document(doc.Name)
        check("modeless schedule opens from native definitions without new history", panel and panel.isVisible()
              and not panel.last_error and history() == before and len(panel.source_snapshot["rows"]) == len(columns))
        driver.command("BIM3117_Schedules")
        check("reopening Schedules reuses one observer and table", schedule_for_document(doc.Name) is panel)
        check("all quantity cells are read-only", panel.table.editTriggers() == QtWidgets.QAbstractItemView.NoEditTriggers)
        choose_row(columns[0])
        panel.selectScheduleSourceButton.click()
        check("schedule source selection resolves actual UUID object", Gui.Selection.getSelection() == [columns[0]])
        before, old_name, old_x = doc.UndoCount, columns[0].Label, columns[0].X.Value
        driver.action(panel.editScheduleRowButton.click, "ScheduleRowDialog", {
            "nameEdit": "Column Row Edited", "rowTypeCombo": alternative, "rowXInput": old_x + 10})
        check("schedule source Label Type and position apply in one transaction", columns[0].Label == "Column Row Edited"
              and columns[0].ElementType == alternative and near(columns[0].X.Value, old_x + 10)
              and near(columns[0].Width.Value, width + 100) and doc.UndoCount == before + 1)
        undo()
        panel.refresh()
        check("one Undo restores all source row fields", columns[0].Label == old_name and columns[0].ElementType == types["Column"]
              and near(columns[0].X.Value, old_x) and near(columns[0].Width.Value, width + 50))
        redo()
        panel.refresh()
        check("Redo replays the source row edit", columns[0].Label == "Column Row Edited" and columns[0].ElementType == alternative)

        choose_row(columns[0])
        before = history()
        driver.action(panel.editScheduleRowButton.click, "ScheduleRowDialog", {"nameEdit": "Cancelled row"}, cancel=True)
        check("cancelling a staged schedule edit creates no history", history() == before and columns[0].Label == "Column Row Edited")
        choose_row(columns[0])
        def stale_row(_dialog):
            undo()
        driver.action(panel.editScheduleRowButton.click, "ScheduleRowDialog", {"nameEdit": "Stale row"}, setup=stale_row, expected_error=True)
        check("source changes during a staged row edit are rejected", columns[0].Label == old_name and doc.RedoCount > 0)
        redo()
        panel.refresh()

        driver.action(panel.editScheduleButton.click, "ScheduleDefinitionDialog", {
            "scheduleTypeCombo": types["Column"], "scheduleGroupCombo": "Type"})
        check("definition filtering/grouping is persisted and source counts are distinct", column_schedule.FilterType == types["Column"]
              and str(column_schedule.GroupBy) == "Type" and len(panel.source_snapshot["rows"]) == 1
              and panel.source_snapshot["totals"]["source_element_count"] == 1)
        panel.table.selectRow(0)
        check("grouped aggregate rows cannot be edited as quantities", not panel.editScheduleRowButton.isEnabled())
        warning = driver.native_delete(types["Column"])
        check("type deletion guard includes schedule filters", bool(warning) and column_schedule.FilterType == types["Column"])
        driver.action(panel.editScheduleButton.click, "ScheduleDefinitionDialog", {
            "scheduleTypeCombo": 0, "scheduleGroupCombo": "None"})

        output_csv = output / "Column_Schedule.csv"
        before = history()
        state = driver.export_schedule(panel, output_csv)
        metadata_path = output / "Column_Schedule_schedule_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        rows = list(csv.DictReader(output_csv.open(encoding="utf-8-sig", newline="")))
        check("real schedule export dialog writes CSV plus both-revision metadata", state["file_dialog"] and len(rows) == len(columns)
              and metadata["model_revision"] == panel.source_snapshot["model_revision"]
              and metadata["schedule_revision"] == panel.source_snapshot["schedule_revision"] and history() == before)
        check("CSV includes explicit source UUIDs and SI columns", all(row["element_ids"] for row in rows)
              and "net_volume_m3" in rows[0] and "Current snapshot" in panel.export_label.text())
        hashes = file_hash(output_csv), file_hash(metadata_path)
        state = driver.export_schedule(panel, output_csv, overwrite=False)
        check("overwrite confirmation covers CSV and metadata; decline preserves both", state["overwrite_dialog"]
              and output_csv.name in state["overwrite_text"] and metadata_path.name in state["overwrite_text"]
              and hashes == (file_hash(output_csv), file_hash(metadata_path)))
        cancelled = output / "Cancelled_Schedule.csv"
        driver.export_schedule(panel, cancelled, cancel_file=True)
        check("cancelling schedule file chooser publishes nothing", not cancelled.exists())
        stale_file = output / "Stale_Schedule.csv"
        driver.export_schedule(panel, stale_file, before_accept=undo, expected_error=True)
        check("model or definition changes during file selection block stale publication", not stale_file.exists()
              and not Path(str(stale_file.with_suffix("")) + "_schedule_metadata.json").exists())
        redo()
        panel.refresh()
        driver.export_schedule(panel, output_csv, overwrite=True)
        check("explicit overwrite publishes a current schedule snapshot", "Current snapshot" in panel.export_label.text())

        driver.command("BIM3117_CreateSchedule", "ScheduleDefinitionDialog", {
            "nameEdit": "Material Volumes", "scheduleCategoryCombo": "Material", "scheduleGroupCombo": "Material",
            "scheduleSortCombo": "Material"})
        material_schedule = next(obj for obj in schedules.list_schedules(project) if obj.Label == "Material Volumes")
        panel.schedule_id = str(material_schedule.BIM3117Id)
        panel.refresh()
        check("material schedule groups actual layer volumes", not panel.last_error and panel.source_snapshot["rows"]
              and str(material_schedule.GroupBy) == "Material" and all("net_volume_m3" in row for row in panel.source_snapshot["rows"]))
        material_sources = {identity for row in panel.source_snapshot["rows"] for identity in row["element_ids"]}
        check("material schedule counts each source UUID once in totals", panel.source_snapshot["totals"]["source_element_count"] == len(material_sources))

        Gui.getMainWindow().resize(1440, 1000)
        catalogue.close()
        catalogue = None
        panel.resize(1100, 440)
        panel.move(170, 510)
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        Gui.updateGui()
        wait_until(lambda: not panel._dirty)
        schedule_shot = output / "schedules-gui.png"
        QtWidgets.QApplication.primaryScreen().grabWindow(0).save(str(schedule_shot))
        panel.hide()
        driver.command("BIM3117_Catalogue")
        catalogue = catalogue_for_document(doc.Name)
        catalogue.resize(1040, 400)
        catalogue.move(200, 540)
        choose_type(slab_type)
        Gui.updateGui()
        catalogue_shot = output / "catalogue-gui.png"
        QtWidgets.QApplication.primaryScreen().grabWindow(0).save(str(catalogue_shot))
        check("captured actual host catalogue and schedules screenshots", catalogue_shot.stat().st_size > 10000 and schedule_shot.stat().st_size > 10000)
        catalogue.close()
        catalogue = None
        panel.show()
        panel.schedule_id = str(column_schedule.BIM3117Id)
        panel.refresh()
        exercise_panel_coexistence(driver, project, panel, check, report)
        model_revision = snapshot.capture(project)["content_revision"]
        doc.save()
        identifiers = {obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")}
        states = {obj.Label: schedules.schedule_state(obj) for obj in schedules.list_schedules(project)}
        report.update(sample=str(sample), sample_sha256=file_hash(sample), source_sha256=source_hash,
                      model_revision=model_revision, identifiers=identifiers, schedule_states=states,
                      screenshots=[str(catalogue_shot), str(schedule_shot)],
                      module_source=catalog.__file__, initial_model_revision=original_revision)
        check("historical building fixture remains byte-identical", file_hash(source) == source_hash)
        name = doc.Name
        App.closeDocument(name)
        doc = None
        check("closing document detaches schedule observer and modeless panel", wait_until(lambda: schedule_for_document(name) is None))
        panel = None
        if keep_sample:
            doc = App.openDocument(str(sample))
            doc.recompute()
            Gui.activeDocument().activeView().viewAxonometric()
            Gui.activeDocument().activeView().fitAll()
            Gui.updateGui()
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        driver.close()
        report["checks_passed"] = len(checks)
        report["installed_ui"] = installed_ui_fingerprint()
        (output / "types-gui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for window in (catalogue, panel):
            if window is not None and not window._closed:
                window.close()
        if doc is not None and doc.Name in App.listDocuments() and (not keep_sample or report["status"] != "passed"):
            App.closeDocument(doc.Name)
    return report
