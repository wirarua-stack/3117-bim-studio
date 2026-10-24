# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture actual canonical model/catalogue/schedule windows without saving changes."""

import hashlib
import json
from pathlib import Path
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui
try:
    from PySide import QtWidgets
except ImportError:
    QtWidgets = QtGui

from freecad_building_gui import wait_until
from freecad_types_gui import installed_ui_fingerprint


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture(sample_path, output_dir):
    sample, output = Path(sample_path), Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    before = _hash(sample)
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp), "checks": checks,
              "sample": str(sample), "sample_sha256": before}
    doc = panel = catalogue = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def screenshot(name):
        Gui.updateGui()
        wait_until(lambda: False, seconds=0.15)
        path = output / name
        bounds = Gui.getMainWindow().frameGeometry()
        if not QtWidgets.QApplication.primaryScreen().grabWindow(
                0, bounds.x(), bounds.y(), bounds.width(), bounds.height()).save(str(path)):
            raise AssertionError("Could not capture real host window")
        return str(path)

    try:
        doc = App.openDocument(str(sample))
        doc.recompute()
        Gui.activateWorkbench("BIM3117Workbench")
        from bim3117_freecad import catalog, schedules, services, snapshot
        from ui3117.catalog_panel import show_catalogue
        from ui3117.schedule_panel import show_schedules
        project = services.get_project(doc)
        history = doc.UndoCount, doc.RedoCount, len(doc.Objects)
        revision = snapshot.capture(project)["content_revision"]
        main = Gui.getMainWindow()
        main.showNormal()
        main.resize(1440, 1000)
        main.move(60, 40)
        Gui.Selection.clearSelection()
        # Datums extend well beyond the authored building. Hide only their
        # transient GUI presentation so the actual source solids remain legible;
        # the canonical FCStd is never saved by this harness.
        datums = services.list_levels(project) + services.list_grids(project)
        for datum in datums:
            datum.ViewObject.Visibility = False
        report["transient_hidden_datums"] = [str(obj.BIM3117Id) for obj in datums]
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.updateGui()
        wait_until(lambda: False, seconds=0.15)
        Gui.activeDocument().activeView().fitAll()
        screenshots = [screenshot("types-model-gui.png")]
        catalogue = show_catalogue(project)
        catalogue.resize(1120, 440)
        catalogue.move(main.x() + 180, main.y() + 500)
        catalogue.refresh()
        check("canonical catalogue reads all types and materials", not catalogue.last_error
              and len(catalogue._types) == len(catalog.list_types(project))
              and len(catalogue._materials) == len(catalog.list_materials(project)))
        layered = next((obj for obj in catalogue._types if catalog.layer_definitions(obj)), None)
        if layered:
            catalogue.types_table.selectRow(catalogue._types.index(layered))
        screenshots.append(screenshot("types-catalogue-gui.png"))
        catalogue.tabs.setCurrentIndex(1)
        screenshots.append(screenshot("types-materials-gui.png"))
        catalogue.close()
        catalogue = None
        candidates = schedules.list_schedules(project)
        material_schedule = next((obj for obj in candidates if str(obj.Category) == "Material" and str(obj.GroupBy) == "Material"), None)
        if material_schedule is None:
            raise AssertionError("Canonical sample needs a Material schedule grouped by Material")
        panel = show_schedules(project, material_schedule)
        panel.resize(1160, 480)
        panel.move(main.x() + 155, main.y() + 460)
        panel.refresh()
        check("canonical grouped material schedule is current", not panel.last_error and not panel._dirty
              and panel.source_snapshot["rows"] and panel.source_snapshot["model_revision"] == revision)
        check("material assignment coverage is visible", bool(panel.coverage_label.text())
              and "Assigned native materials" in panel.coverage_label.text())
        screenshots.append(screenshot("types-material-schedule-gui.png"))
        product_schedule = next((obj for obj in candidates if str(obj.Category) != "Material" and str(obj.GroupBy) == "None"), None)
        if product_schedule:
            panel.schedule_id = str(product_schedule.BIM3117Id)
            panel.refresh()
            if panel.table.rowCount():
                panel.table.selectRow(0)
            screenshots.append(screenshot("types-source-schedule-gui.png"))
        check("presentation creates no native objects or history entries", history == (doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        check("presentation preserves model content revision", snapshot.capture(project)["content_revision"] == revision)
        check("canonical saved FCStd bytes remain unchanged", _hash(sample) == before)
        report.update(status="passed", model_revision=revision, screenshots=screenshots,
                      screenshot_sha256={Path(path).name: _hash(path) for path in screenshots},
                      material_coverage=panel.source_snapshot.get("coverage", {}).get("material", {}))
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        for window in (panel, catalogue):
            if window is not None and not window._closed:
                window.close()
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
        report["checks_passed"] = len(checks)
        report["installed_ui"] = installed_ui_fingerprint()
        (output / "types-presentation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
