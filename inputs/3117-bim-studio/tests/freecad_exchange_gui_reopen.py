# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh-process native quantity dialog restore and Undo evidence."""

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


def main(output_dir):
    output = Path(output_dir)
    source = json.loads((output / "exchange-gui-report.json").read_text(encoding="utf-8"))
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "checks": checks}
    doc, panel = None, None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def settled(predicate):
        end = time.monotonic() + 4
        while time.monotonic() < end:
            QtWidgets.QApplication.processEvents()
            if predicate():
                return True
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(25, loop.quit)
            (getattr(loop, "exec", None) or loop.exec_)()
        return bool(predicate())

    try:
        check("source GUI suite passed", source["status"] == "passed")
        check("native proxies not preregistered before restore", "bim3117_freecad.building" not in sys.modules)
        doc = App.openDocument(source["sample"])
        doc.recompute()
        from bim3117_freecad import services
        from ui3117.exchange_dialog import panel_for_document
        project = services.get_project(doc)
        check("fresh process restores native identities", source["identifiers"] == {
            obj.Name: obj.BIM3117Id for obj in doc.Objects})
        Gui.activateWorkbench("BIM3117Workbench")
        before = (doc.UndoCount, doc.RedoCount, len(doc.Objects))
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        check("fresh dialog computes saved content revision", panel.source_snapshot["content_revision"] == source["content_revision"])
        check("fresh table rows and net quantities match source document",
              panel.wall_table.rowCount() == 1 and panel.door_table.rowCount() == 1
              and abs(panel.source_snapshot["wall_rows"][0]["net_volume_m3"] - source["net_volume_m3"]) < 1e-8)
        check("fresh quantity read does not create native history or objects",
              before == (doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        wall = doc.getObject(source["sample_wall"])
        services.edit_level(wall.TopLevel, elevation_mm=3500)
        check("fresh observer updates level-dependent native quantities",
              settled(lambda: not panel._dirty and panel.source_snapshot["content_revision"] != source["content_revision"])
              and abs(panel.source_snapshot["wall_rows"][0]["net_volume_m3"] - 4.7775) < 1e-8)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("fresh observer follows Undo back to saved revision and volume",
              settled(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == source["content_revision"])
              and abs(panel.source_snapshot["wall_rows"][0]["net_volume_m3"] - source["net_volume_m3"]) < 1e-8)
        panel.wall_table.cellClicked.emit(0, 0)
        check("fresh table selection resolves persistent native wall", Gui.Selection.getSelection() == [wall])
        panel.close()
        check("fresh dialog closes without leaking its observer", panel._closed and panel_for_document(doc.Name) is None)
        report.update(status="passed", checks_passed=len(checks))
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "exchange-gui-reopen-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if panel is not None and not panel._closed:
            panel.close()
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
