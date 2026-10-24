# SPDX-License-Identifier: GPL-3.0-or-later
"""Real installed Quantity / Exchange widgets, refreshes and file dialogs.

Creates disposable documents and exports only below output_dir. The table,
timers, modal coverage/file/overwrite dialogs and native history all run in the
actual FreeCAD GUI. It does not mock FreeCAD or the snapshot/export services.
"""

import csv
import hashlib
import json
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


def run(output_dir, keep_sample=False):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    checks, dialogs_seen, expected_errors = [], [], []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(),
              "gui_up": bool(App.GuiUp), "checks": checks,
              "dialogs_seen": dialogs_seen, "expected_errors": expected_errors}
    panel, sample_doc = None, None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def wait_until(predicate, seconds=4):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            QtWidgets.QApplication.processEvents()
            if predicate():
                return True
            # A short event loop lets actual single-shot refresh timers mature.
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(25, loop.quit)
            runner = getattr(loop, "exec", None) or loop.exec_
            runner()
        return bool(predicate())

    def near(actual, expected):
        return abs(float(actual) - expected) < 1e-8

    def history(doc):
        return doc.UndoCount, doc.RedoCount, len(doc.Objects)

    def export_with_dialogs(action, destination, cancel=None, overwrite=False,
                            expected_error=False, mutate_before_save=None):
        result = {"coverage": False, "file": False, "overwrite": False,
                  "exclusion_guard": False, "errors": []}
        failures = []
        timer = QtCore.QTimer()
        timer.setInterval(40)
        attempts = [0]

        def interact():
            attempts[0] += 1
            modal = QtWidgets.QApplication.activeModalWidget()
            if attempts[0] > 250:
                timer.stop()
                failures.append("Export dialog interaction timed out")
                if modal is not None:
                    modal.reject()
                return
            if modal is None:
                return
            try:
                name = modal.objectName()
                if name == "BIM3117ExportCoverageDialog":
                    if result["coverage"]:
                        return
                    result["coverage"] = True
                    dialogs_seen.append("coverage")
                    acknowledge = modal.findChild(QtWidgets.QCheckBox, "coverageAcknowledge")
                    proceed = modal.findChild(QtWidgets.QPushButton, "coverageContinueButton")
                    if acknowledge.isVisible():
                        result["exclusion_guard"] = not proceed.isEnabled()
                        acknowledge.click()
                    if cancel == "coverage":
                        modal.findChild(QtWidgets.QPushButton, "coverageCancelButton").click()
                    else:
                        proceed.click()
                elif name == "BIM3117ExportFileDialog":
                    if result["file"]:
                        return
                    result["file"] = True
                    dialogs_seen.append("file")
                    if cancel == "file":
                        modal.reject()
                    else:
                        modal.setDirectory(str(Path(destination).parent))
                        modal.selectFile(str(destination))
                        # QFileSystemModel updates the directory asynchronously;
                        # enter the path in the actual edit widget, then accept
                        # on the next event turn instead of its initial name.
                        file_edit = modal.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                        if file_edit is not None:
                            file_edit.setText(str(destination))
                        def accept_file():
                            try:
                                if mutate_before_save is not None:
                                    mutate_before_save()
                                modal.accept()
                            except BaseException as error:
                                failures.append(str(error))
                                modal.reject()
                        QtCore.QTimer.singleShot(80, accept_file)
                elif name == "BIM3117OverwriteDialog":
                    if result["overwrite"]:
                        return
                    result["overwrite"] = True
                    dialogs_seen.append("overwrite")
                    button = modal.button(QtWidgets.QMessageBox.Yes if overwrite else QtWidgets.QMessageBox.No)
                    button.click()
                elif isinstance(modal, QtWidgets.QMessageBox):
                    result["errors"].append(modal.text())
                    modal.accept()
            except BaseException as error:
                failures.append(str(error))
                modal.reject()

        timer.timeout.connect(interact)
        timer.start()
        try:
            action()
        finally:
            timer.stop()
        if failures:
            raise AssertionError(failures[0])
        if expected_error:
            if not result["errors"]:
                raise AssertionError("Expected export rejection was not reported")
            expected_errors.extend(result["errors"])
        elif result["errors"]:
            raise AssertionError("Unexpected export error: " + result["errors"][0])
        return result

    try:
        Gui.activateWorkbench("BIM3117Workbench")
        check("installed quantity and IFC commands registered",
              {"BIM3117_Quantities", "BIM3117_ExportIFC"}.issubset(set(Gui.listCommands())))
        from bim3117_freecad import services, snapshot, exchange
        from ui3117.exchange_dialog import panel_for_document
        project = services.create_project("ทดสอบปริมาณและ IFC", project_number="3117-QA-021", author="3117 QA")
        doc = sample_doc = project.Document
        base, top = services.list_levels(project)
        wall_type = services.create_wall_type(project, "ผนัง W200", thickness_mm=200, material="Masonry")
        wall = services.create_wall(project, "ผนัง A", wall_type, base, top, end_x_mm=6000)
        door = services.create_door(project, "ประตู D01", wall, offset_mm=1000, width_mm=900, height_mm=2100)
        services.create_grid(project, "กริด A", axis="X", position_mm=-1500, level=base)
        baseline = snapshot.capture(project)
        baseline_revision = baseline["content_revision"]
        before = history(doc)
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        check("quantity command opens a modeless document-bound dialog",
              panel is not None and panel.isVisible() and not panel.isModal()
              and panel.document_name == doc.Name)
        check("one wall and one door row exclude the derived wall body",
              panel.wall_table.rowCount() == 1 and panel.door_table.rowCount() == 1
              and len([obj for obj in doc.Objects if services.kind(obj) == "WallBody"]) == 1)
        check("table cells are read-only and lengths explicitly use SI units",
              not bool(panel.wall_table.item(0, 0).flags() & QtCore.Qt.ItemIsEditable)
              and panel.wall_table.horizontalHeaderItem(4).text() == "Length (m)"
              and panel.wall_table.item(0, 4).text() == "6.0000")
        check("initial quantity table matches native solid net volume",
              near(panel.source_snapshot["wall_rows"][0]["net_volume_m3"], 3.222)
              and "3.2220" in panel.totals_label.text())
        check("quantity table revision matches current model content",
              panel.source_snapshot["content_revision"] == baseline_revision
              and panel.revision_label.toolTip() == baseline_revision and not panel._dirty)
        check("opening and reading quantities creates no transaction or model object", history(doc) == before)
        Gui.runCommand("BIM3117_Quantities")
        check("reopening quantity command reuses the same dialog and observer",
              panel_for_document(doc.Name) is panel and history(doc) == before)
        panel.wall_table.cellClicked.emit(0, 0)
        check("wall row selects its authored persistent object",
              len(Gui.Selection.getSelection()) == 1 and Gui.Selection.getSelection()[0] == wall
              and str(wall.BIM3117Id) in panel.selection_label.text())
        panel.tabs.setCurrentIndex(1)
        panel.door_table.cellClicked.emit(0, 0)
        check("door row selects its hosted source object", Gui.Selection.getSelection() == [door])
        check("coverage includes explicit grid exclusion and derived body role",
              any(item["kind"] == "Grid" and item["status"] == "reference"
                  for item in panel.source_snapshot["coverage"]["items"])
              and any(item["kind"] == "WallBody" and item["status"] == "derived"
                  for item in panel.source_snapshot["coverage"]["items"]))

        exports = output / "ส่งออก_ปริมาณ" / baseline_revision[:12]
        exports.mkdir(parents=True, exist_ok=True)
        csv_path, ifc_path = exports / "ทดสอบ.csv", exports / "ทดสอบ.ifc"
        cancel_path = exports / "ยกเลิก.csv"
        result = export_with_dialogs(panel.csv_button.click, cancel_path, cancel="coverage")
        check("cancel coverage preview writes nothing and preserves history",
              result["coverage"] and not result["file"] and not cancel_path.exists() and history(doc) == before)
        result = export_with_dialogs(panel.csv_button.click, cancel_path, cancel="file")
        check("cancel actual save dialog writes nothing and preserves history",
              result["file"] and not cancel_path.exists() and history(doc) == before)
        result = export_with_dialogs(panel.csv_button.click, csv_path)
        check("CSV export requires acknowledgement of excluded grid",
              result["exclusion_guard"] and result["coverage"] and result["file"])
        csv_result = panel.latest_exports["csv"]
        check("CSV command writes both row files and metadata through chosen path",
              str(csv_path) in csv_result["files"] and len(csv_result["files"]) == 3
              and all(Path(name).is_file() for name in csv_result["files"]))
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            csv_rows = list(csv.DictReader(stream))
        check("GUI-written CSV contains correct authored identity and volume",
              len(csv_rows) == 1 and csv_rows[0]["element_id"] == wall.BIM3117Id
              and near(csv_rows[0]["net_volume_m3"], 3.222))
        check("CSV success is labelled a current snapshot and does not change history",
              "Current snapshot" in panel.export_label.text() and history(doc) == before)
        csv_hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in csv_result["files"]}
        result = export_with_dialogs(panel.csv_button.click, csv_path, overwrite=False)
        check("reject overwrite preserves every existing bundle file",
              result["overwrite"] and csv_hashes == {
                  name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in csv_result["files"]})

        check("host IFC dependency available for actual GUI export", exchange.ifc_dependency_info()["available"])
        result = export_with_dialogs(lambda: Gui.runCommand("BIM3117_ExportIFC"), ifc_path)
        ifc_result = panel.latest_exports["ifc"]
        check("IFC command uses coverage and save dialogs then creates validated export",
              result["coverage"] and result["file"] and ifc_path.is_file()
              and ifc_result["content_revision"] == baseline_revision)
        import ifcopenshell
        model = ifcopenshell.open(str(ifc_path))
        check("GUI IFC readback has wall, door and real void/fill relationships",
              len(model.by_type("IfcWall")) == 1 and len(model.by_type("IfcDoor")) == 1
              and len(model.by_type("IfcRelVoidsElement")) == 1 and len(model.by_type("IfcRelFillsElement")) == 1)
        check("same stem IFC and CSV keep separate metadata sidecars",
              csv_result["metadata_path"] != ifc_result["metadata_path"]
              and Path(csv_result["metadata_path"]).exists() and Path(ifc_result["metadata_path"]).exists())
        check("both completed exports preserve native history", history(doc) == before)

        services.edit_level(top, elevation_mm=3300)
        check("model change immediately marks old table stale", panel._dirty and not panel.csv_button.isEnabled())
        check("native observer automatically refreshes after completed transaction",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] != baseline_revision)
              and near(panel.source_snapshot["wall_rows"][0]["net_volume_m3"], 3.582))
        changed_revision = panel.source_snapshot["content_revision"]
        check("old CSV and IFC snapshots visibly become stale", panel.export_label.text().count("Stale snapshot") == 2)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("native Undo restores table revision and earlier exports become current",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == baseline_revision)
              and panel.export_label.text().count("Current snapshot") == 2)
        Gui.runCommand("Std_Redo")
        doc.recompute()
        check("native Redo restores edited table and stale export indicators",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == changed_revision)
              and near(panel.source_snapshot["wall_rows"][0]["net_volume_m3"], 3.582))
        panel.auto_refresh.setChecked(False)
        services.edit_wall_type(wall_type, thickness_mm=250)
        check("manual mode retains visibly stale rows and blocks export buttons",
              panel._dirty and not panel.csv_button.isEnabled() and not panel.ifc_button.isEnabled())
        panel.refresh_button.click()
        check("explicit refresh reads new shared type and native volume",
              not panel._dirty and near(panel.source_snapshot["wall_rows"][0]["thickness_m"], 0.25)
              and near(panel.source_snapshot["wall_rows"][0]["net_volume_m3"], 4.4775))
        panel.auto_refresh.setChecked(True)
        before = history(doc)
        result = export_with_dialogs(panel.csv_button.click, csv_path, overwrite=True)
        check("explicit overwrite publishes a fresh bundle without an undo item",
              result["overwrite"] and panel.latest_exports["csv"]["content_revision"] == panel.source_snapshot["content_revision"]
              and history(doc) == before)
        check("CSV current and older IFC stale statuses are independent",
              "CSV: ตรงกับโมเดล / Current snapshot" in panel.export_label.text()
              and "IFC: ล้าสมัย" in panel.export_label.text())

        reject_path = exports / "ข้อมูลเปลี่ยนระหว่างส่งออก.csv"
        result = export_with_dialogs(panel.csv_button.click, reject_path, expected_error=True,
                                     mutate_before_save=lambda: services.edit_level(top, elevation_mm=3400))
        check("changed model between preview and save rejects stale revision before writing",
              bool(result["errors"]) and not any(Path(name).exists() for name in exchange.output_paths(reject_path, format="csv")))
        wait_until(lambda: not panel._dirty)
        # Return to the known 250 mm / 3300 mm demonstration state.
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("rejected stale export leaves the genuine model edit undoable",
              wait_until(lambda: not panel._dirty and near(top.Elevation.Value, 3300))
              and near(panel.source_snapshot["wall_rows"][0]["net_volume_m3"], 4.4775))

        doc.openTransaction("QA pending edit")
        try:
            check("open transaction suspends quantity export", not panel.refresh()
                  and not panel.csv_button.isEnabled() and not panel.ifc_button.isEnabled())
        finally:
            doc.abortTransaction()
            if App.getActiveTransaction() is not None:
                App.closeActiveTransaction()
        check("aborted empty transaction allows automatic refresh", wait_until(lambda: not panel._dirty))

        # Escape/reject must release the observer just like the Close button.
        panel.reject()
        check("Escape-style rejection detaches observer and removes panel registry",
              panel._closed and panel_for_document(doc.Name) is None)
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        check("quantity dialog reopens cleanly after rejection", panel is not None and not panel._closed and not panel._dirty)
        saved = output / "ตัวอย่าง_3117" / "Quantity_Exchange_Workbench.FCStd"
        saved.parent.mkdir(parents=True, exist_ok=True)
        for level in services.list_levels(project):
            level.ViewObject.Visibility = False
        doc.saveAs(str(saved))
        panel.refresh()
        expected_revision = panel.source_snapshot["content_revision"]
        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        names = {"wall": wall.Name, "door": door.Name}
        old_name = doc.Name
        old_panel = panel
        App.closeDocument(old_name)
        check("closing document closes quantity window and stops observer",
              wait_until(lambda: old_panel._closed) and panel_for_document(old_name) is None)
        doc = sample_doc = App.openDocument(str(saved))
        doc.recompute()
        project = services.get_project(doc)
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        check("save/reopen restores identical content revision and source UUID rows",
              panel.source_snapshot["content_revision"] == expected_revision
              and panel.source_snapshot["wall_rows"][0]["element_id"] == identifiers[names["wall"]]
              and panel.source_snapshot["door_rows"][0]["element_id"] == identifiers[names["door"]])
        Gui.getMainWindow().resize(1440, 1000)
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        panel.tabs.setCurrentIndex(0)
        panel.resize(1240, 600)
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()
        screenshot = output / "Quantity_Exchange_Workbench.png"
        check("actual quantity dialog screenshot saved", panel.grab().save(str(screenshot)))
        report.update(status="passed", checks_passed=len(checks), sample=str(saved), screenshot=str(screenshot),
                      identifiers=identifiers, sample_wall=names["wall"], sample_door=names["door"],
                      content_revision=expected_revision, net_volume_m3=4.4775,
                      csv_path=str(csv_path), ifc_path=str(ifc_path),
                      snapshot_module=snapshot.__file__, exchange_module=exchange.__file__)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "exchange-gui-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if panel is not None and not panel._closed and not (keep_sample and report["status"] == "passed"):
            panel.close()
        for name in set(App.listDocuments()) - original_documents:
            if keep_sample and report["status"] == "passed" and sample_doc is not None and name == sample_doc.Name:
                continue
            App.closeDocument(name)
        if original_active and not keep_sample:
            App.setActiveDocument(original_active)
    return report
