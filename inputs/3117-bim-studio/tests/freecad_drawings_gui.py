# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual installed drawing commands and modeless SVG/PDF preview.

The frozen v0.3 building is copied before editing. All authoring goes through
real modal widgets and native Undo/Redo; no service or dialog is substituted.
Run from a deferred FreeCAD GUI macro, with a disposable output directory.
"""

import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback
import xml.etree.ElementTree as ET

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


class DrawingGuiDriver(GuiDriver):
    def _messages(self):
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None and modal.objectName() == "BIM3117DrawingOverwriteDialog":
            return
        super()._messages()

    def export_drawing(self, panel, path, format_name, overwrite=None, cancel_file=False):
        result = {"file_dialog": False, "overwrite_dialog": False, "overwrite_text": ""}
        failures, attempts = [], [0]
        timer = QtCore.QTimer()
        timer.setInterval(40)

        def interact():
            attempts[0] += 1
            modal = QtWidgets.QApplication.activeModalWidget()
            if attempts[0] > 300:
                timer.stop()
                failures.append("Drawing export dialogs timed out")
                if modal is not None:
                    modal.reject()
                return
            if modal is None:
                return
            try:
                if modal.objectName() == "BIM3117DrawingExportFileDialog" and not result["file_dialog"]:
                    result["file_dialog"] = True
                    if cancel_file:
                        modal.reject()
                    else:
                        modal.setDirectory(str(path.parent))
                        modal.selectFile(str(path))
                        entry = modal.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                        if entry is not None:
                            entry.setText(str(path))
                        QtCore.QTimer.singleShot(90, modal.accept)
                elif modal.objectName() == "BIM3117DrawingOverwriteDialog":
                    if overwrite is None:
                        failures.append("Unexpected overwrite question for a new destination")
                        modal.reject()
                    else:
                        result["overwrite_dialog"] = True
                        result["overwrite_text"] = modal.text()
                        modal.button(QtWidgets.QMessageBox.Yes if overwrite else QtWidgets.QMessageBox.No).click()
            except BaseException as error:
                failures.append(str(error))
                modal.reject()

        timer.timeout.connect(interact)
        timer.start()
        before = len(self.messages)
        (panel.pdf_button if format_name == "pdf" else panel.svg_button).click()
        timer.stop()
        if failures or len(self.messages) != before:
            raise AssertionError((failures or self.messages[before:])[0])
        if not result["file_dialog"]:
            raise AssertionError("The drawing export file dialog did not open: " + panel.last_error)
        return result


def exercise_project_deletion_guards(driver, check):
    """Exercise the reference guard in a separate disposable native project."""
    from bim3117_freecad import drawings, services
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    guard_doc = None
    try:
        driver.command("BIM3117_CreateProject", "ProjectDialog", {
            "nameEdit": "Drawing reference deletion check", "initialLevelsCheck": False})
        guard_doc = App.ActiveDocument
        guard_project = services.get_project(guard_doc)
        driver.command("BIM3117_CreateSection", "DrawingViewDialog", {"nameEdit": "Empty Model Section"})
        guard_view = drawings.list_views(guard_project)[0]
        driver.select(guard_view)
        driver.command("BIM3117_CreateSheet", "DrawingSheetDialog", {
            "nameEdit": "Guard Sheet", "sheetSecondViewCombo": 0})
        guard_sheet = drawings.list_sheets(guard_project)[0]
        guard_project_name = guard_project.Name
        check("documentation-only project has no model children", not guard_project.Group)
        warnings = driver.native_delete(guard_project)
        check("native Delete protects a documentation-only Project", bool(warnings)
              and guard_doc.getObject(guard_project_name) is not None
              and guard_sheet.Project == guard_project and guard_view.Project == guard_project)
        driver.select(guard_sheet)
        driver.command("BIM3117_DeleteSelected")
        driver.select(guard_view)
        driver.command("BIM3117_DeleteSelected")
        empty_group = drawings.get_drawing_set(guard_project)
        empty_group_name = empty_group.Name
        driver.native_delete(empty_group)
        check("empty drawing set can be removed through native Delete", guard_doc.getObject(empty_group_name) is None)
    finally:
        if guard_doc is not None and guard_doc.Name in App.listDocuments():
            App.closeDocument(guard_doc.Name)
        if original_active in App.listDocuments():
            App.setActiveDocument(original_active)


def run(output_dir, keep_sample=False):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    sample_folder = output / "ตัวอย่าง_แบบ"
    sample_folder.mkdir(parents=True, exist_ok=True)
    sample = sample_folder / "Drawings_Workbench.FCStd"
    source = Path(__file__).resolve().parents[1] / "examples/building/Building_Authoring_Workbench.FCStd"
    frozen_hash = file_hash(source)
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp),
              "scope": "Actual drawing forms, modeless preview, SVG/PDF export and native Undo/Redo",
              "checks": checks, "frozen_source_sha256": frozen_hash}
    driver = DrawingGuiDriver(report)
    doc = panel = None

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
        commands = {"BIM3117_CreateDrawingView", "BIM3117_CreatePlan", "BIM3117_CreateSection",
                    "BIM3117_CreateElevation", "BIM3117_CreateSheet", "BIM3117_DrawingPreview",
                    "BIM3117_ExportDrawingSVG", "BIM3117_ExportDrawingPDF"}
        check("all installed drawing commands are registered", commands.issubset(set(Gui.listCommands())))
        from bim3117_freecad import drawings, snapshot, services
        from ui3117.drawing_preview import panel_for_document
        from ui3117 import viewproviders
        check("native drawing module imports from installed addon", "/Mod/BIM3117/" in drawings.__file__.replace("\\", "/"))

        doc = App.openDocument(str(source))
        doc.saveAs(str(sample))
        App.setActiveDocument(doc.Name)
        doc.UndoMode = 1
        doc.recompute()
        project = services.get_project(doc)
        levels = services.list_levels(project)
        l00, l01 = sorted(levels, key=lambda obj: float(obj.Elevation.Value))[:2]
        base_revision = snapshot.capture(project)["content_revision"]
        base_objects = len(doc.Objects)
        before = history()
        driver.select(l00)
        driver.command("BIM3117_CreatePlan", "DrawingViewDialog", {"nameEdit": "Cancelled Plan"}, cancel=True)
        driver.command("BIM3117_CreatePlan", "DrawingViewDialog", {
            "drawingBottomOffsetInput": 1500, "drawingCutOffsetInput": 1200}, invalid=True)
        check("cancelled and invalid view forms leave document/history unchanged", history() == before)

        driver.command("BIM3117_CreatePlan", "DrawingViewDialog", {"nameEdit": "Ground Plan", "drawingLevelCombo": l00})
        ground = next(v for v in drawings.list_views(project) if v.Label == "Ground Plan")
        ground_id, ground_name = str(ground.BIM3117Id), ground.Name
        check("Plan and drawing set are created in one document transaction", doc.UndoCount == before[0] + 1
              and ground.Level == l00 and ground.Origin.Length == 0 and len(doc.Objects) == base_objects + 2)
        check("native drawing tree stays outside editable model group", drawings.get_drawing_set(project) not in project.Group
              and ground not in project.Group and snapshot.capture(project)["content_revision"] == base_revision)
        undo()
        check("native Undo removes first view and its newly created group", len(doc.Objects) == base_objects
              and not drawings.list_views(project) and drawings.get_drawing_set(project) is None)
        redo()
        ground = doc.getObject(ground_name)
        check("native Redo restores view identity and GUI provider", str(ground.BIM3117Id) == ground_id
              and isinstance(ground.ViewObject.Proxy, viewproviders.DrawingViewProvider))

        driver.select(l01)
        driver.command("BIM3117_CreateDrawingView", "DrawingViewDialog", {"nameEdit": "Upper Plan", "drawingLevelCombo": l01})
        upper = next(v for v in drawings.list_views(project) if v.Label == "Upper Plan")
        driver.command("BIM3117_CreateSection", "DrawingViewDialog", {
            "nameEdit": "Section A-A", "drawingOriginXInput": 3000, "drawingOriginYInput": 2000,
            "drawingOriginZInput": 0, "drawingDepthInput": 3000, "drawingDirectionCombo": 0})
        section = next(v for v in drawings.list_views(project) if v.Label == "Section A-A")
        driver.command("BIM3117_CreateElevation", "DrawingViewDialog", {
            "nameEdit": "South Elevation", "drawingOriginXInput": 3000, "drawingOriginYInput": -1000,
            "drawingOriginZInput": 0, "drawingDepthInput": 6000, "drawingDirectionCombo": 0})
        elevation = next(v for v in drawings.list_views(project) if v.Label == "South Elevation")
        check("Plan, Section and Elevation widgets author native definitions", len(drawings.list_views(project)) == 4
              and upper.Level == l01 and section.Level is None and section.Origin.y == 2000
              and str(section.Direction) == "+Y" and elevation.Origin.y == -1000)

        driver.select(ground, upper)
        before = history()
        driver.command("BIM3117_CreateSheet", "DrawingSheetDialog", cancel=True)
        driver.command("BIM3117_CreateSheet", "DrawingSheetDialog", {
            "sheetFirstViewCombo": ground, "sheetSecondViewCombo": ground}, invalid=True)
        check("cancelled/duplicate-view sheet forms leave history unchanged", history() == before)
        driver.command("BIM3117_CreateSheet", "DrawingSheetDialog", {
            "nameEdit": "Floor Plans", "sheetNumberEdit": "A001", "sheetAuthorEdit": "3117 GUI QA",
            "sheetFirstViewCombo": ground, "sheetSecondViewCombo": upper})
        plans = next(s for s in drawings.list_sheets(project) if s.Number == "A001")
        driver.select(section, elevation)
        driver.command("BIM3117_CreateSheet", "DrawingSheetDialog", {
            "nameEdit": "Section and Elevation", "sheetNumberEdit": "A002", "sheetAuthorEdit": "3117 GUI QA",
            "sheetFirstViewCombo": section, "sheetSecondViewCombo": elevation})
        vertical = next(s for s in drawings.list_sheets(project) if s.Number == "A002")
        check("two A3 sheets store ordered persistent view references", len(drawings.list_sheets(project)) == 2
              and plans.ViewIds == [ground.BIM3117Id, upper.BIM3117Id]
              and vertical.ViewIds == [section.BIM3117Id, elevation.BIM3117Id]
              and plans.Paper == "A3" and plans.Orientation == "Landscape")
        check("drawing definitions preserve native model revision", snapshot.capture(project)["content_revision"] == base_revision)

        driver.select(plans)
        before = history()
        driver.command("BIM3117_DrawingPreview")
        panel = panel_for_document(doc.Name)
        check("actual modeless SVG preview opens current", panel is not None and panel.isVisible() and not panel.isModal()
              and not panel._dirty and panel.canvas.renderer.isValid() and not panel.last_error)
        check("preview is read only and identifies both revisions", history() == before
              and panel.source_snapshot["model_revision"] == base_revision
              and all(value[:12] in panel.revision_label.text() for value in drawings.sheet_state(plans).values()))
        first_state = drawings.sheet_state(plans)
        panel.sheet_combo.setCurrentIndex(1)
        check("sheet selector renders vertical views", panel.sheet_id == str(vertical.BIM3117Id)
              and not panel._dirty and len(panel.source_snapshot["views"]) == 2
              and [v["view_type"] for v in panel.source_snapshot["views"]] == ["Section", "Elevation"])
        panel.findChild(QtWidgets.QPushButton, "drawingZoomInButton").click()
        check("preview zoom changes only presentation", panel.canvas.zoom > 1 and history() == before)
        panel.findChild(QtWidgets.QPushButton, "drawingFitButton").click()
        check("Fit restores paper view", near(panel.canvas.zoom, 1) and panel.canvas.pan.isNull())

        exports = {}
        for sheet in (vertical, plans):
            index = next(i for i in range(panel.sheet_combo.count())
                         if str(panel.sheet_combo.itemData(i)) == str(sheet.BIM3117Id))
            panel.sheet_combo.setCurrentIndex(index)
            if panel._dirty:
                panel.refresh_button.click()
            check(sheet.Number + " preview fits its explicit 1:50 scales", not panel._dirty and not panel.last_error)
            for format_name in ("svg", "pdf"):
                destination = sample_folder / ("3117_" + sheet.Number + "." + format_name)
                result = driver.export_drawing(panel, destination, format_name,
                                               overwrite=True if destination.exists() else None)
                exported = panel.latest_exports[(str(sheet.BIM3117Id), format_name)]
                metadata = json.loads(Path(exported["metadata_path"]).read_text(encoding="utf-8"))
                check(sheet.Number + " " + format_name.upper() + " publishes payload and matching provenance", result["file_dialog"]
                      and destination.exists() and metadata["files"][0]["sha256"] == file_hash(destination)
                      and metadata["model_revision"] == base_revision
                      and metadata["drawing_revision"] == drawings.sheet_state(sheet)["drawing_revision"])
                if format_name == "svg":
                    root = ET.fromstring(destination.read_text(encoding="utf-8"))
                    check(sheet.Number + " SVG preserves A3 physical units", root.get("width") == "420mm"
                          and root.get("height") == "297mm" and root.get("viewBox") == "0 0 420 297")
                else:
                    check(sheet.Number + " PDF passes host structural readback", destination.read_bytes().startswith(b"%PDF-")
                          and metadata["validation"]["pdf"]["page_count"] == 1)
                exports[sheet.Number + "_" + format_name] = exported
        check("both formats and two sheets leave source history unchanged", history() == before)
        check("latest session exports show current status", "Current snapshot" in panel.export_label.text())
        destination = sample_folder / "3117_A001.svg"
        bundle = exports["A001_svg"]["files"]
        prior_files = {path: file_hash(path) for path in bundle}
        result = driver.export_drawing(panel, destination, "svg", overwrite=False)
        check("overwrite refusal preserves both payload and sidecar", result["overwrite_dialog"]
              and all(Path(path).name in result["overwrite_text"] for path in bundle)
              and all(file_hash(path) == digest for path, digest in prior_files.items()) and history() == before)
        result = driver.export_drawing(panel, destination, "svg", cancel_file=True)
        check("cancelled export preserves source and existing bundle", result["file_dialog"]
              and history() == before and all(file_hash(path) == digest for path, digest in prior_files.items()))
        result = driver.export_drawing(panel, destination, "svg", overwrite=True)
        check("explicit overwrite republishes the full verified bundle", result["overwrite_dialog"]
              and json.loads(Path(bundle[1]).read_text(encoding="utf-8"))["files"][0]["sha256"] == file_hash(bundle[0]))

        panel.sheet_combo.setCurrentIndex(next(i for i in range(panel.sheet_combo.count())
            if str(panel.sheet_combo.itemData(i)) == str(vertical.BIM3117Id)))
        panel.auto_refresh.setChecked(False)
        old_svg = panel.canvas.svg_text
        old_geometry = json.dumps([view["geometry"] for view in panel.source_snapshot["views"]], sort_keys=True)
        driver.select(l01)
        before_edit = history()
        driver.command("BIM3117_EditSelected", "LevelDialog", {"elevationInput": 3200})
        check("model edit marks retained preview stale and disables publication", panel._dirty
              and "Stale" in panel.status_label.text() and not panel.pdf_button.isEnabled()
              and panel.canvas.svg_text == old_svg and doc.UndoCount == before_edit[0] + 1)
        panel.refresh_button.click()
        changed_state = drawings.sheet_state(plans)
        new_geometry = json.dumps([view["geometry"] for view in panel.source_snapshot["views"]], sort_keys=True)
        check("Update Drawing recomputes geometry and changes only the model hash", not panel._dirty
              and changed_state["model_revision"] != first_state["model_revision"]
              and changed_state["drawing_revision"] == first_state["drawing_revision"]
              and new_geometry != old_geometry and panel.canvas.svg_text != old_svg
              and "Stale snapshot" in panel.export_label.text())
        undo()
        panel.refresh_button.click()
        panel.sheet_combo.setCurrentIndex(next(i for i in range(panel.sheet_combo.count())
            if str(panel.sheet_combo.itemData(i)) == str(plans.BIM3117Id)))
        check("model Undo returns preview and previous exports to current", drawings.sheet_state(plans) == first_state
              and not panel._dirty and "Current snapshot" in panel.export_label.text())
        redo()
        panel.refresh_button.click()
        check("model Redo refreshes changed geometry", drawings.sheet_state(plans) == changed_state and not panel._dirty)
        undo()
        panel.refresh_button.click()

        driver.select(ground)
        before_edit = history()
        driver.command("BIM3117_EditSelected", "DrawingViewDialog", {"drawingScaleInput": 100})
        panel.refresh_button.click()
        scale_state = drawings.sheet_state(plans)
        check("Edit Selected updates drawing scale in one transaction", ground.ScaleDenominator == 100
              and doc.UndoCount == before_edit[0] + 1 and not panel._dirty)
        check("drawing edit changes only documentation hash", scale_state["model_revision"] == first_state["model_revision"]
              and scale_state["drawing_revision"] != first_state["drawing_revision"])
        undo()
        panel.refresh_button.click()
        check("drawing Undo restores original scale and both hashes", ground.ScaleDenominator == 50
              and drawings.sheet_state(plans) == first_state)
        redo()
        panel.refresh_button.click()
        check("drawing Redo restores the authored scale", ground.ScaleDenominator == 100
              and drawings.sheet_state(plans) == scale_state)
        undo()
        panel.refresh_button.click()

        driver.select(plans)
        before_edit = history()
        driver.command("BIM3117_EditSelected", "DrawingSheetDialog", {"sheetIssueEdit": "P02"})
        panel.refresh_button.click()
        check("Edit Selected edits title block and drawing revision transactionally", plans.Issue == "P02"
              and doc.UndoCount == before_edit[0] + 1 and drawings.sheet_state(plans)["model_revision"] == base_revision
              and drawings.sheet_state(plans)["drawing_revision"] != first_state["drawing_revision"])
        undo()
        panel.refresh_button.click()

        driver.select(ground)
        before = history()
        driver.command("BIM3117_DeleteSelected", expected_error=True)
        check("used view deletion is rejected before mutation", history() == before and ground in drawings.list_views(project))
        warnings = driver.native_delete(ground)
        check("native Delete explains the checked drawing command", bool(warnings) and doc.getObject(ground_name) is not None)
        driver.select(vertical)
        vertical_id, vertical_name = str(vertical.BIM3117Id), vertical.Name
        driver.command("BIM3117_DeleteSelected")
        check("Delete Selected removes only selected sheet", len(drawings.list_sheets(project)) == 1
              and len(drawings.list_views(project)) == 4)
        undo()
        vertical = doc.getObject(vertical_name)
        check("sheet Undo restores identity and ordered view references", str(vertical.BIM3117Id) == vertical_id
              and vertical.ViewIds == [section.BIM3117Id, elevation.BIM3117Id])
        panel.refresh_button.click()
        check("drawing preview does not create generated geometry objects", len(doc.Objects) == base_objects + 7)
        check("final model and drawing identities equal published source", drawings.sheet_state(plans) == first_state)

        identities = {obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")}
        states = {sheet.Number: drawings.sheet_state(sheet) for sheet in drawings.list_sheets(project)}
        doc.recompute()
        doc.save()
        panel.refresh_button.click()
        panel.auto_refresh.setChecked(True)
        panel.hide()
        Gui.Selection.clearSelection()
        Gui.getMainWindow().resize(1500, 1000)
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        Gui.updateGui()
        model_screenshot = output / "Drawings_Model_Workbench.png"
        check("actual source model/workbench screenshot is saved", Gui.getMainWindow().grab().save(str(model_screenshot)))
        panel.show()
        panel.resize(1260, 910)
        panel.canvas.fit()
        panel.raise_()
        Gui.updateGui()
        wait_until(lambda: not panel._dirty, seconds=10)
        screenshot = output / "Drawings_Workbench.png"
        check("actual drawing preview screenshot is saved", panel.grab().save(str(screenshot)))
        panel.sheet_combo.setCurrentIndex(next(i for i in range(panel.sheet_combo.count())
            if str(panel.sheet_combo.itemData(i)) == str(vertical.BIM3117Id)))
        Gui.updateGui()
        vertical_screenshot = output / "Drawings_Section_Elevation.png"
        check("actual section/elevation preview screenshot is saved", not panel._dirty
              and panel.grab().save(str(vertical_screenshot)))
        panel.sheet_combo.setCurrentIndex(next(i for i in range(panel.sheet_combo.count())
            if str(panel.sheet_combo.itemData(i)) == str(plans.BIM3117Id)))
        report.update(sample=str(sample), screenshot=str(screenshot), model_screenshot=str(model_screenshot),
                      vertical_screenshot=str(vertical_screenshot), identifiers=identities,
                      model_revision=base_revision, sheet_states=states, exports=exports,
                      module_source=drawings.__file__, sample_sha256=file_hash(sample),
                      view_names=[v.Label for v in drawings.list_views(project)],
                      sheet_numbers=[s.Number for s in drawings.list_sheets(project)],
                      before_model_edit=first_state, after_model_edit=changed_state, after_drawing_edit=scale_state,
                      model_geometry_before=hashlib.sha256(old_geometry.encode("utf-8")).hexdigest(),
                      model_geometry_after=hashlib.sha256(new_geometry.encode("utf-8")).hexdigest(),
                      svg_geometry_changed=new_geometry != old_geometry)
        if not keep_sample:
            closed_name = doc.Name
            App.closeDocument(closed_name)
            check("document close detaches the preview observer", wait_until(lambda: panel_for_document(closed_name) is None))
            panel = None
            doc = App.openDocument(str(sample))
            doc.recompute()
            project = services.get_project(doc)
            check("saved native drawing definitions reopen with unchanged identities", identities == {
                obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")})
            check("saved drawing links and revisions survive reopen", states == {
                sheet.Number: drawings.sheet_state(sheet) for sheet in drawings.list_sheets(project)})
        exercise_project_deletion_guards(driver, check)
        check("frozen v0.3 building fixture remains byte-for-byte unchanged", file_hash(source) == frozen_hash)
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        driver.close()
        report["checks_passed"] = len(checks)
        (output / "drawings-gui-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not keep_sample or report["status"] != "passed":
            if panel is not None and not panel._closed:
                panel.close()
            for name in set(App.listDocuments()) - original_documents:
                App.closeDocument(name)
            if original_active in App.listDocuments():
                App.setActiveDocument(original_active)
    return report
