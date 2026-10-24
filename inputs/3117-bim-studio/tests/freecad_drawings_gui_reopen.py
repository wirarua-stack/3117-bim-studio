# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh installed-host restore of drawing proxies before explicit imports."""

import json
from pathlib import Path
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from freecad_drawings_gui import DrawingGuiDriver, exercise_project_deletion_guards, file_hash, wait_until


def main(output_dir):
    output = Path(output_dir)
    previous = json.loads((output / "drawings-gui-report.json").read_text(encoding="utf-8"))
    sample = Path(previous["sample"])
    before_file = file_hash(sample)
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp), "checks": checks}
    driver = DrawingGuiDriver(report)
    doc = panel = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def undo():
        Gui.runCommand("Std_Undo")
        doc.recompute()
        Gui.updateGui()

    try:
        # Restore first. Proxy persistence must locate the installed modules
        # without the test importing production code or editing sys.path.
        doc = App.openDocument(str(sample))
        doc.recompute()
        from bim3117_freecad import drawings, services, snapshot
        from ui3117 import viewproviders
        from ui3117.drawing_preview import panel_for_document
        check("restored native proxy module is installed", "/Mod/BIM3117/" in drawings.__file__.replace("\\", "/"))
        project = services.get_project(doc)
        check("fresh process preserves all model and drawing UUIDs", previous["identifiers"] == {
            obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")})
        check("fresh process preserves model content revision", snapshot.capture(project)["content_revision"] == previous["model_revision"])
        check("fresh process preserves both sheet revisions", previous["sheet_states"] == {
            sheet.Number: drawings.sheet_state(sheet) for sheet in drawings.list_sheets(project)})
        group = drawings.get_drawing_set(project)
        check("drawing set GUI tree restores from installed proxy", isinstance(group.ViewObject.Proxy, viewproviders.DrawingSetViewProvider)
              and set(group.ViewObject.Proxy.claimChildren()) == set(group.Group))
        check("all view and sheet GUI providers restore", all(isinstance(view.ViewObject.Proxy, viewproviders.DrawingViewProvider)
              for view in drawings.list_views(project)) and all(isinstance(sheet.ViewObject.Proxy, viewproviders.DrawingSheetViewProvider)
              for sheet in drawings.list_sheets(project)))

        Gui.activateWorkbench("BIM3117Workbench")
        doc.UndoMode = 1
        plans = next(s for s in drawings.list_sheets(project) if s.Number == "A001")
        ground = next(v for v in drawings.list_views(project) if v.Label == "Ground Plan")
        baseline = drawings.sheet_state(plans)
        history = doc.UndoCount, doc.RedoCount, len(doc.Objects)
        driver.select(plans)
        driver.command("BIM3117_DrawingPreview")
        panel = panel_for_document(doc.Name)
        check("fresh GUI renders sheet from current native geometry", panel is not None and panel.isVisible()
              and not panel._dirty and not panel.last_error and panel.canvas.renderer.isValid())
        check("opening a restored preview adds no transaction/cache objects", history == (doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        check("fresh preview does not invent a remembered export status", not panel.latest_exports)

        panel.auto_refresh.setChecked(False)
        driver.select(ground)
        driver.command("BIM3117_EditSelected", "DrawingViewDialog", {"drawingScaleInput": 100})
        panel.refresh_button.click()
        changed = drawings.sheet_state(plans)
        check("restored definition remains editable through installed command", ground.ScaleDenominator == 100
              and not panel._dirty and changed["model_revision"] == baseline["model_revision"]
              and changed["drawing_revision"] != baseline["drawing_revision"])
        undo()
        panel.refresh_button.click()
        check("restored view supports native Undo", drawings.sheet_state(plans) == baseline and ground.ScaleDenominator == 50)

        upper_level = ground.Level
        panel.auto_refresh.setChecked(True)
        driver.select(upper_level)
        current_elevation = upper_level.Elevation.Value
        driver.command("BIM3117_EditSelected", "LevelDialog", {"elevationInput": current_elevation - 100})
        check("observer automatically refreshes a changed native model", wait_until(
            lambda: not panel._dirty and panel.source_snapshot["model_revision"] != baseline["model_revision"], seconds=30))
        undo()
        check("automatic refresh follows native model Undo", wait_until(
            lambda: not panel._dirty and panel.source_snapshot["model_revision"] == baseline["model_revision"], seconds=30))
        exercise_project_deletion_guards(driver, check)
        check("fresh host exercise leaves saved FCStd bytes unchanged", file_hash(sample) == before_file)
        name = doc.Name
        App.closeDocument(name)
        doc = None
        check("fresh-host close detaches document observer", wait_until(lambda: panel_for_document(name) is None))
        panel = None
        report.update(status="passed", sample=str(sample), sample_sha256=before_file,
                      module_source=drawings.__file__, model_revision=baseline["model_revision"])
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        driver.close()
        report["checks_passed"] = len(checks)
        (output / "drawings-gui-reopen-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if panel is not None and not panel._closed:
            panel.close()
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
    return report
