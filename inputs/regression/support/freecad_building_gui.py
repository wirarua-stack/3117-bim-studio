# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual installed building commands, joins, hosted windows and quantity UI.

Only disposable documents and files below output_dir are created. Every model
mutation exercised here uses a real 3117 command or native Undo/Redo action.
"""

import csv
import json
import math
from pathlib import Path
import platform
import sys
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui


def near(actual, expected, tolerance=1e-7):
    return abs(float(actual) - float(expected)) <= max(tolerance, abs(float(expected)) * 1e-8)


def wait_until(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        if predicate():
            return True
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        (getattr(loop, "exec", None) or loop.exec_)()
    return bool(predicate())


class GuiDriver:
    """Enter values into real modal widgets; do not replace command services."""

    def __init__(self, report):
        self.report = report
        self.messages = []
        self.deletion = False
        self.deletion_warnings = report.setdefault("deletion_warnings", [])
        self.errors = report.setdefault("expected_command_errors", [])
        self.watchdog = QtCore.QTimer()
        self.watchdog.setInterval(60)
        self.watchdog.timeout.connect(self._messages)
        self.watchdog.start()

    def close(self):
        self.watchdog.stop()

    def _messages(self):
        modal = QtWidgets.QApplication.activeModalWidget()
        if not isinstance(modal, QtWidgets.QMessageBox):
            return
        if self.deletion:
            if modal.objectName() == "BIM3117DeletionWarning":
                self.deletion_warnings.append(modal.text())
                modal.accept()
            else:
                button = modal.button(QtWidgets.QMessageBox.Yes)
                if button is not None:
                    button.click()
                else:
                    modal.reject()
        else:
            self.messages.append(modal.text())
            modal.accept()

    @staticmethod
    def select(*objects):
        Gui.Selection.clearSelection()
        for obj in objects:
            Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        Gui.updateGui()

    def command(self, name, dialog_name=None, values=None, cancel=False, invalid=False, expected_error=False):
        values = values or {}
        completed, failures = [], []
        message_count = len(self.messages)
        timer = QtCore.QTimer()
        timer.setInterval(35)
        attempts = [0]

        def interact():
            attempts[0] += 1
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None or dialog.objectName() != dialog_name:
                if attempts[0] > 200:
                    failures.append("Expected form did not open: " + str(dialog_name))
                    timer.stop()
                    if dialog is not None:
                        dialog.reject()
                return
            timer.stop()
            try:
                for widget_name, value in values.items():
                    widget = dialog.findChild(QtCore.QObject, widget_name)
                    if isinstance(widget, QtWidgets.QPlainTextEdit):
                        widget.setPlainText(str(value))
                    elif isinstance(widget, QtWidgets.QLineEdit):
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
                            index = next((i for i in range(widget.count())
                                          if widget.itemText(i) == label or widget.itemText(i).startswith(label + "  ")), -1)
                        if index < 0:
                            raise AssertionError("Missing combo item: " + str(value))
                        widget.setCurrentIndex(index)
                    else:
                        raise AssertionError("Missing widget: " + widget_name)
                if invalid:
                    dialog.findChild(QtWidgets.QPushButton, "acceptButton").click()
                    error = dialog.findChild(QtWidgets.QLabel, "validationMessage")
                    if not dialog.isVisible() or not error.text():
                        raise AssertionError("Invalid form did not retain an inline explanation")
                dialog.findChild(QtWidgets.QPushButton,
                                 "cancelButton" if cancel or invalid else "acceptButton").click()
                completed.append(True)
            except BaseException as error:
                failures.append(str(error))
                dialog.reject()

        if dialog_name is not None:
            timer.timeout.connect(interact)
            timer.start()
        Gui.runCommand(name)
        timer.stop()
        if failures:
            raise AssertionError(failures[0])
        if dialog_name is not None and not completed:
            raise AssertionError("Command did not complete its form: " + name)
        messages = self.messages[message_count:]
        if expected_error:
            if len(messages) != 1:
                raise AssertionError("Expected one rejected-command explanation: " + name)
            self.errors.append({"command": name, "message": messages[0]})
        elif messages:
            raise AssertionError("Unexpected command error: " + messages[0])
        Gui.updateGui()

    def native_delete(self, obj):
        self.select(obj)
        before = len(self.deletion_warnings)
        self.deletion = True
        try:
            Gui.runCommand("Std_Delete")
        finally:
            self.deletion = False
        return self.deletion_warnings[before:]

    def export_csv(self, panel, path):
        result = {"coverage": False, "file": False, "summary": "", "exclusions_acknowledged": False}
        failures = []
        timer = QtCore.QTimer()
        timer.setInterval(40)
        attempts = [0]

        def interact():
            attempts[0] += 1
            modal = QtWidgets.QApplication.activeModalWidget()
            if attempts[0] > 250:
                timer.stop()
                failures.append("CSV dialogs timed out")
                if modal is not None:
                    modal.reject()
                return
            if modal is None:
                return
            try:
                if modal.objectName() == "BIM3117ExportCoverageDialog" and not result["coverage"]:
                    result["coverage"] = True
                    result["summary"] = modal.findChild(QtWidgets.QLabel, "coverageSummary").text()
                    acknowledge = modal.findChild(QtWidgets.QCheckBox, "coverageAcknowledge")
                    proceed = modal.findChild(QtWidgets.QPushButton, "coverageContinueButton")
                    result["exclusions_acknowledged"] = acknowledge.isVisible() and not proceed.isEnabled()
                    if acknowledge.isVisible():
                        acknowledge.click()
                    proceed.click()
                elif modal.objectName() == "BIM3117ExportFileDialog" and not result["file"]:
                    result["file"] = True
                    modal.setDirectory(str(path.parent))
                    modal.selectFile(str(path))
                    entry = modal.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                    if entry is not None:
                        entry.setText(str(path))
                    QtCore.QTimer.singleShot(90, modal.accept)
            except BaseException as error:
                failures.append(str(error))
                modal.reject()

        timer.timeout.connect(interact)
        timer.start()
        before = len(self.messages)
        panel.csv_button.click()
        timer.stop()
        if failures or len(self.messages) != before:
            raise AssertionError((failures or self.messages[before:])[0])
        return result


def run(output_dir, keep_sample=False):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp),
              "checks": checks, "scope": "Actual commands and modeless quantities; synthetic two-storey frame"}
    driver = GuiDriver(report)
    doc = sample_doc = panel = None

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

    try:
        Gui.activateWorkbench("BIM3117Workbench")
        required = {"BIM3117_CreateSlab", "BIM3117_CreateColumn", "BIM3117_CreateBeam", "BIM3117_CreateWindow",
                    "BIM3117_JoinSlab", "BIM3117_UnjoinSlab", "BIM3117_Quantities"}
        check("installed building authoring commands are registered", required.issubset(set(Gui.listCommands())))
        from bim3117_freecad import services, snapshot, exchange
        from ui3117.exchange_dialog import panel_for_document

        driver.command("BIM3117_CreateProject", "ProjectDialog", {
            "nameEdit": "3117 อาคารตัวอย่างสองชั้น", "projectNumberEdit": "BUILD-030", "authorEdit": "3117 GUI QA",
            "initialLevelsCheck": True, "baseElevationInput": 0, "upperElevationInput": 3000})
        doc = sample_doc = App.ActiveDocument
        project = services.get_project(doc)
        l00, l01 = services.list_levels(project)
        driver.command("BIM3117_AddLevel", "LevelDialog", {"nameEdit": "L02", "elevationInput": 6000})
        l02 = services.list_levels(project)[-1]
        driver.command("BIM3117_CreateGrid", "GridDialog", {
            "nameEdit": "Grid A", "bubbleEdit": "A", "positionInput": 0, "referenceLevelCombo": "L00"})
        before = history()
        driver.command("BIM3117_CreateSlab", "SlabDialog", {"nameEdit": "Cancelled slab"}, cancel=True)
        driver.command("BIM3117_CreateSlab", "SlabDialog", {"slabProfileCombo": 1, "boundaryEdit": "0, 0\nwrong"}, invalid=True)
        check("cancelled and malformed polygon forms leave document history unchanged", history() == before)
        driver.command("BIM3117_CreateSlab", "SlabDialog", {
            "nameEdit": "Invalid crossing", "slabProfileCombo": 1,
            "boundaryEdit": "0, 0\n1000, 1000\n0, 1000\n1000, 0"}, expected_error=True)
        check("self-crossing polygon service rejection rolls back object and transaction", history() == before)

        slabs = []
        for index, level in enumerate((l00, l01, l02)):
            driver.command("BIM3117_CreateSlab", "SlabDialog", {
                "nameEdit": "S{:02d}".format(index), "levelCombo": level, "thicknessInput": 200,
                "slabXInput": -300, "slabYInput": -300, "slabLengthInput": 6600, "slabWidthInput": 4600,
                "materialEdit": "Concrete"})
            slabs.append(services.list_slabs(project)[-1])
        check("three rectangle slabs use top datums and downward native thickness", all(
            slab.Shape.isValid() and len(slab.Shape.Solids) == 1
            and near(slab.Shape.BoundBox.ZMax, _mm(slab.Level.Elevation))
            and near(slab.Shape.BoundBox.ZMin, _mm(slab.Level.Elevation) - 200)
            and near(slab.Shape.Volume / 1e9, 6.072) and slab.Material == "Concrete" for slab in slabs))
        driver.select(slabs[0])
        driver.command("BIM3117_EditSelected", "SlabDialog", {
            "boundaryEdit": "-300,-300\n6300,-300\n6300,4300\n3000,4300\n3000,3000\n-300,3000"})
        check("explicit concave polygon edits actual slab footprint", near(slabs[0].Shape.Volume / 1e9, 5.214))
        undo()
        check("native Undo restores rectangle boundary and slab volume", near(slabs[0].Shape.Volume / 1e9, 6.072))

        columns, beams = [], []
        corners = [(0, 0), (6000, 0), (6000, 4000), (0, 4000)]
        for storey, (base, top, slab) in enumerate(((l00, l01, slabs[1]), (l01, l02, slabs[2]))):
            for corner, (x, y) in enumerate(corners):
                driver.command("BIM3117_CreateColumn", "ColumnDialog", {
                    "nameEdit": "C{}{}".format(storey, corner), "centerXInput": x, "centerYInput": y,
                    "baseLevelCombo": base, "topLevelCombo": top, "widthInput": 300, "depthInput": 300,
                    "materialEdit": "Concrete"})
                member = services.list_columns(project)[-1]
                driver.select(member, slab)
                previous = doc.UndoCount
                driver.command("BIM3117_JoinSlab", "JoinSlabDialog")
                if not columns:
                    check("explicit column slab join commits one native transaction and one solid",
                          doc.UndoCount == previous + 1 and member.JoinSlabs == [slab]
                          and len(member.Shape.Solids) == 1 and near(member.Shape.Volume / 1e9, .252))
                columns.append(member)
            for edge in range(4):
                start, end = corners[edge], corners[(edge + 1) % 4]
                driver.command("BIM3117_CreateBeam", "BeamDialog", {
                    "nameEdit": "B{}{}".format(storey, edge), "levelCombo": top,
                    "startXInput": start[0], "startYInput": start[1], "endXInput": end[0], "endYInput": end[1],
                    "widthInput": 300, "depthInput": 450, "materialEdit": "Concrete"})
                member = services.list_beams(project)[-1]
                driver.select(member, slab)
                driver.command("BIM3117_JoinSlab", "JoinSlabDialog")
                beams.append(member)
        check("two-storey frame has eight valid joined columns and eight centered beams", len(columns) == len(beams) == 8
              and all(member.Shape.isValid() and len(member.Shape.Solids) == 1 for member in columns + beams)
              and all(near(member.Shape.Volume / 1e9, .252) for member in columns)
              and all(near(member.Shape.Volume / 1e9, .45 if index % 2 == 0 else .3) for index, member in enumerate(beams)))
        check("native building view providers persist on the correct shape objects", all(
            obj.ViewObject.Proxy.__class__.__name__ == obj.BIM3117Kind + "ViewProvider"
            for obj in slabs + columns + beams))

        driver.command("BIM3117_CreateColumn", "ColumnDialog", {
            "nameEdit": "Split rejection probe", "centerXInput": 3000, "centerYInput": 2000,
            "baseLevelCombo": l00, "topLevelCombo": l02})
        split = services.list_columns(project)[-1]
        driver.select(split, slabs[1])
        before = history()
        prior_revision = snapshot.capture(project)["content_revision"]
        driver.command("BIM3117_JoinSlab", "JoinSlabDialog", expected_error=True)
        check("join that splits a column rejects without changing references volume or history",
              history() == before and not split.JoinSlabs and near(split.Shape.Volume / 1e9, .54)
              and snapshot.capture(project)["content_revision"] == prior_revision)
        driver.select(split)
        driver.command("BIM3117_DeleteSelected")
        driver.command("BIM3117_CreateBeam", "BeamDialog", {
            "nameEdit": "Full removal probe", "levelCombo": l01, "depthInput": 100,
            "startXInput": 1000, "startYInput": 1000, "endXInput": 3000, "endYInput": 1000})
        full = services.list_beams(project)[-1]
        driver.select(full, slabs[1])
        before = history()
        prior_revision = snapshot.capture(project)["content_revision"]
        driver.command("BIM3117_JoinSlab", "JoinSlabDialog", expected_error=True)
        check("join that removes a whole beam rejects with complete rollback", history() == before
              and not full.JoinSlabs and near(full.Shape.Volume / 1e9, .06)
              and snapshot.capture(project)["content_revision"] == prior_revision)
        driver.select(full)
        driver.command("BIM3117_DeleteSelected")

        driver.command("BIM3117_CreateWallType", "WallTypeDialog", {
            "nameEdit": "W200", "thicknessInput": 200, "materialEdit": "Masonry"})
        walls = []
        for storey, (base, top) in enumerate(((l00, l01), (l01, l02))):
            driver.command("BIM3117_CreateWall", "WallDialog", {
                "nameEdit": "W{}1".format(storey), "startXInput": 150, "startYInput": 0,
                "endXInput": 5850, "endYInput": 0, "baseLevelCombo": base, "topLevelCombo": top,
                "topOffsetInput": -450})
            walls.append(services.list_walls(project)[-1])
        driver.select(walls[0])
        driver.command("BIM3117_CreateDoor", "DoorDialog", {
            "nameEdit": "D01", "doorOffsetInput": 700, "widthInput": 900, "heightInput": 2100})
        door = services.list_doors(project)[0]
        windows = []
        for storey, wall in enumerate(walls):
            driver.select(services.wall_body(wall))
            driver.command("BIM3117_CreateWindow", "WindowDialog", {
                "nameEdit": "WN{}1".format(storey), "windowOffsetInput": 2800,
                "widthInput": 1200, "heightInput": 1200, "sillInput": 900})
            windows.append(services.list_windows(project)[-1])
        window = windows[0]
        body = services.wall_body(walls[0])
        center = App.Vector(150 + 2800 + 600, 100, 900 + 600)
        frame_points = [App.Vector(2975, 100, 1500), App.Vector(4125, 100, 1500),
                        App.Vector(center.x, center.y, 925), App.Vector(center.x, center.y, 2075)]
        # The generic frame is deliberately four non-overlapping solids.
        # Compound.isInside is not a union-membership test; inspect each bar.
        frame_contains = lambda point: any(solid.isInside(point, 1e-6, True) for solid in window.Shape.Solids)
        report["window_probe"] = {"host": window.Host.Name, "expected_host": walls[0].Name,
                                  "opening_kinds": [obj.BIM3117Kind for obj in body.Openings],
                                  "frame_volume_m3": window.Shape.Volume / 1e9,
                                  "wall_volume_m3": body.Shape.Volume / 1e9,
                                  "opening_center_in_wall": body.Shape.isInside(center, 1e-6, True),
                                  "opening_center_in_frame": frame_contains(center),
                                  "four_frame_points_occupied": [frame_contains(point) for point in frame_points],
                                  "frame_solids": len(window.Shape.Solids),
                                  "base_level_mm": window.Host.BaseLevel.Elevation.Value,
                                  "host_top_offset_mm": window.Host.TopOffset.Value,
                                  "sill_mm": window.Sill.Value, "offset_mm": window.Offset.Value}
        check("hosted Window is a real cut with a four-sided frame distinct from Door", window.Host == walls[0]
              and window in body.Openings and door in body.Openings and not body.Shape.isInside(center, 1e-6, True)
              and len(window.Shape.Solids) == 4 and all(frame_contains(point) for point in frame_points)
              and not frame_contains(center)
              and near(window.Shape.Volume / 1e9, .046) and near(body.Shape.Volume / 1e9, 2.241))
        check("Window is claimed by its wall and hidden from duplicate project tree entries",
              window in walls[0].ViewObject.Proxy.claimChildren()
              and window not in project.ViewObject.Proxy.claimChildren()
              and window.ViewObject.Proxy.__class__.__name__ == "WindowViewProvider")
        driver.select(walls[0])
        Gui.runCommand("Std_ToggleVisibility")
        hidden = not window.ViewObject.Visibility and not door.ViewObject.Visibility and not body.ViewObject.Visibility
        Gui.runCommand("Std_ToggleVisibility")
        check("native wall visibility toggle includes Window Door and derived body", hidden
              and window.ViewObject.Visibility and door.ViewObject.Visibility and body.ViewObject.Visibility)

        Gui.getMainWindow().resize(1440, 1000)
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        counts = {"wall_rows": 2, "door_rows": 1, "window_rows": 2, "slab_rows": 3, "column_rows": 8, "beam_rows": 8}
        check("seven compact modeless tabs read one row per authored UUID", panel is not None and not panel.isModal()
              and panel.tabs.count() == 7 and panel.height() < Gui.getMainWindow().height() * .75
              and all(len(panel.source_snapshot[key]) == count for key, count in counts.items())
              and all(len({row["element_id"] for row in panel.source_snapshot[key]}) == count for key, count in counts.items()))
        selected_sources = []
        for table, target in ((panel.slab_table, slabs[0]), (panel.column_table, columns[0]),
                              (panel.beam_table, beams[0]), (panel.window_table, window)):
            row = next(index for index in range(table.rowCount())
                       if table.item(index, 0).data(QtCore.Qt.UserRole) == target.BIM3117Id)
            table.cellClicked.emit(row, 0)
            selected_sources.append(Gui.Selection.getSelection() == [target]
                                    and not bool(table.item(row, 0).flags() & QtCore.Qt.ItemIsEditable))
        check("all new quantity categories select native source UUIDs and remain read-only", all(selected_sources))
        exports = output / "ส่งออก_อาคาร" / panel.source_snapshot["content_revision"][:12]
        exports.mkdir(parents=True, exist_ok=True)
        csv_path = exports / "อาคาร.csv"
        before = history()
        csv_dialogs = driver.export_csv(panel, csv_path)
        result = panel.latest_exports["csv"]
        files = exchange.output_paths(csv_path, format="csv", source=panel.source_snapshot)
        check("building CSV coverage previews all categories and acknowledges Grid exclusion",
              csv_dialogs["coverage"] and csv_dialogs["file"] and csv_dialogs["exclusions_acknowledged"]
              and all(text in csv_dialogs["summary"] for text in ("Slabs: 3", "Columns: 8", "Beams: 8", "Windows: 2")))
        rows_read = {}
        for suffix, count in (("", 2), ("_doors", 1), ("_windows", 2), ("_slabs", 3), ("_columns", 8), ("_beams", 8)):
            path = csv_path.with_name(csv_path.stem + suffix + ".csv")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows_read[suffix] = list(csv.DictReader(stream))
            if len(rows_read[suffix]) != count:
                raise AssertionError("CSV category count mismatch: " + suffix)
        check("actual CSV export writes all six category payloads and metadata without history pollution",
              len(files) == len(result["files"]) == 7 and all(Path(path).is_file() for path in files)
              and history() == before and near(sum(float(row["net_volume_m3"]) for row in rows_read["_columns"]), 2.016))

        baseline_revision = panel.source_snapshot["content_revision"]
        driver.select(l01)
        driver.command("BIM3117_EditSelected", "LevelDialog", {"elevationInput": 3300})
        check("level edit refreshes linked slabs columns beams walls windows and snapshot status",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] != baseline_revision)
              and near(slabs[1].Shape.BoundBox.ZMax, 3300) and near(columns[0].Height.Value, 3300)
              and near(columns[4].Height.Value, 2700) and near(beams[0].Shape.BoundBox.ZMax, 3100)
              and near(windows[1].Shape.BoundBox.ZMin, 4200) and "Stale snapshot" in panel.export_label.text())
        undo()
        check("native Undo returns prior quantities content revision and current CSV status",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == baseline_revision)
              and "Current snapshot" in panel.export_label.text())
        redo()
        check("native Redo replays the level dependency update", wait_until(lambda: not panel._dirty)
              and near(columns[0].Height.Value, 3300) and "Stale snapshot" in panel.export_label.text())
        undo()
        wait_until(lambda: not panel._dirty)

        driver.select(columns[0])
        driver.command("BIM3117_EditSelected", "ColumnDialog", {
            "widthInput": 400, "depthInput": 250, "rotationInput": 30})
        expected_span = 400 * math.cos(math.radians(30)) + 250 * math.sin(math.radians(30))
        check("column section and rotation edit recomputes joined native solid and quantity",
              wait_until(lambda: not panel._dirty) and near(columns[0].Shape.Volume / 1e9, .28)
              and near(columns[0].Shape.BoundBox.XLength, expected_span))
        undo()
        wait_until(lambda: not panel._dirty)
        driver.select(beams[0])
        driver.command("BIM3117_EditSelected", "BeamDialog", {"widthInput": 350, "depthInput": 500})
        check("beam section edit preserves top datum and existing slab cut", wait_until(lambda: not panel._dirty)
              and near(beams[0].Shape.Volume / 1e9, .63) and near(beams[0].Shape.BoundBox.ZMax, 2800))
        undo()
        wait_until(lambda: not panel._dirty)
        driver.select(slabs[1])
        driver.command("BIM3117_EditSelected", "SlabDialog", {"thicknessInput": 250})
        check("slab thickness edit updates both joined member categories", wait_until(lambda: not panel._dirty)
              and near(columns[0].Shape.Volume / 1e9, .2475) and near(beams[0].Shape.Volume / 1e9, .36))
        undo()
        wait_until(lambda: not panel._dirty)

        driver.select(columns[0])
        driver.command("BIM3117_UnjoinSlab", "UnjoinSlabDialog", {"clearAllJoinsCheck": True})
        check("explicit clear-all unjoin restores full member volume and live quantity", wait_until(lambda: not panel._dirty)
              and not columns[0].JoinSlabs and not columns[0].JoinSlabIds and near(columns[0].Shape.Volume / 1e9, .27))
        undo()
        check("Undo restores native slab join references and deducted volume", wait_until(lambda: not panel._dirty)
              and columns[0].JoinSlabs == [slabs[1]] and near(columns[0].Shape.Volume / 1e9, .252))
        driver.select(beams[0])
        driver.command("BIM3117_UnjoinSlab", "UnjoinSlabDialog", {"joinSlabCombo": slabs[1]})
        check("specific-slab unjoin uses its native selected cutter", wait_until(lambda: not panel._dirty)
              and not beams[0].JoinSlabs and near(beams[0].Shape.Volume / 1e9, .81))
        undo()
        wait_until(lambda: not panel._dirty)

        driver.select(window)
        driver.command("BIM3117_EditSelected", "WindowDialog", {"hostWallCombo": walls[1], "windowOffsetInput": 1000})
        check("Window rehost closes old cut and opens new host while preserving identity", wait_until(lambda: not panel._dirty)
              and window.Host == walls[1] and near(services.wall_body(walls[0]).Shape.Volume / 1e9, 2.529)
              and near(services.wall_body(walls[1]).Shape.Volume / 1e9, 2.331))
        undo()
        wait_until(lambda: not panel._dirty)
        driver.select(window)
        before = history()
        prior_revision = panel.source_snapshot["content_revision"]
        driver.command("BIM3117_EditSelected", "WindowDialog", {"windowOffsetInput": 1000}, expected_error=True)
        refreshed = wait_until(lambda: not panel._dirty)
        report["overlap_rejection"] = {"before_history": before, "after_history": history(), "refreshed": refreshed,
                                       "expected_revision": prior_revision,
                                       "actual_revision": panel.source_snapshot["content_revision"],
                                       "host": window.Host.Name, "expected_host": walls[0].Name,
                                       "offset_mm": window.Offset.Value, "last_refresh_error": panel.last_error}
        check("Door and Window overlap rejection preserves the committed native model",
              refreshed and history() == before and window.Host == walls[0]
              and near(window.Offset.Value, 2800) and panel.source_snapshot["content_revision"] == prior_revision)
        before = history()
        slab_name, window_name, window_id = slabs[1].Name, window.Name, window.BIM3117Id
        slab_warning = driver.native_delete(slabs[1])
        window_warning = driver.native_delete(window)
        check("native deletion guards retain a referenced cutter and a hosted Window", bool(slab_warning)
              and bool(window_warning) and doc.getObject(slab_name) is not None and doc.getObject(window_name) is not None
              and history() == before)
        driver.select(window)
        driver.command("BIM3117_DeleteSelected")
        check("3117 Window delete removes frame and restores actual wall material", wait_until(lambda: not panel._dirty)
              and doc.getObject(window_name) is None and near(services.wall_body(walls[0]).Shape.Volume / 1e9, 2.529))
        undo()
        window = doc.getObject(window_name)
        check("native Undo restores Window UUID frame opening and quantity row", wait_until(lambda: not panel._dirty)
              and window.BIM3117Id == window_id and near(window.Shape.Volume / 1e9, .046)
              and near(services.wall_body(walls[0]).Shape.Volume / 1e9, 2.241) and panel.window_table.rowCount() == 2)

        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        level_names = (l00.Name, l01.Name, l02.Name)
        revision = panel.source_snapshot["content_revision"]
        window.ViewObject.Visibility = False
        for obj in services.list_levels(project) + services.list_grids(project):
            obj.ViewObject.Visibility = False
        saved = output / "ตัวอย่าง_อาคาร" / "Building_Authoring_Workbench.FCStd"
        saved.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(saved))
        old_panel = panel
        old_name = doc.Name
        App.closeDocument(old_name)
        # The observer defers widget teardown until the native document-delete
        # callback has returned. Wait for that event-loop cleanup before reopen.
        detached = wait_until(lambda: old_panel._closed and panel_for_document(old_name) is None)
        doc = sample_doc = App.openDocument(str(saved))
        doc.recompute()
        project = services.get_project(doc)
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        check("closing and reopening replaces the document-bound quantity observer",
              detached and panel is not old_panel and panel_for_document(doc.Name) is panel)
        check("saved building model restores matching contents and source-bound quantities",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects} == identifiers
              and panel.source_snapshot["content_revision"] == revision
              and not doc.getObject(window_name).ViewObject.Visibility
              and len(services.list_columns(project)[0].JoinSlabs) == 1)
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        view.fitAll()
        panel.tabs.setCurrentWidget(panel.column_table)
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()
        screenshot = output / "Building_Authoring_Workbench.png"
        check("actual building quantity widgets are captured", panel.grab().save(str(screenshot)))
        report.update(status="passed", checks_passed=len(checks), sample=str(saved), screenshot=str(screenshot),
                      identifiers=identifiers, content_revision=revision, counts=counts,
                      hidden_window=window_name, lower_level=level_names[0], middle_level=level_names[1], upper_level=level_names[2],
                      module_source=services.__file__, snapshot_module=snapshot.__file__,
                      csv_path=str(csv_path), csv_files=result["files"], native_objects=len(doc.Objects))
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        driver.close()
        (output / "building-gui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if panel is not None and not panel._closed and not (keep_sample and report["status"] == "passed"):
            panel.close()
        for name in set(App.listDocuments()) - original_documents:
            if keep_sample and report["status"] == "passed" and sample_doc is not None and sample_doc.Name == name:
                continue
            App.closeDocument(name)
        if original_active and not keep_sample:
            App.setActiveDocument(original_active)
    return report


def _mm(value):
    return float(getattr(value, "Value", value))
