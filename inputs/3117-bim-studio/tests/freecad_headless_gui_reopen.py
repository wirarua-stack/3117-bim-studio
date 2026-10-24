# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh GUI process opens the presentation copy of the native IFC fixture."""

import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore


def main(output_dir):
    output = Path(output_dir)
    source = json.loads((output / "headless-gui-report.json").read_text(encoding="utf8"))
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "checks": checks}
    doc, panel = None, None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    try:
        check("source headless-to-GUI test passed", source["status"] == "passed")
        check("native and view proxies not preregistered", "bim3117_freecad.building" not in sys.modules
              and "ui3117.viewproviders" not in sys.modules)
        check("GUI copy matches the reported file hash", hashlib.sha256(Path(source["gui_copy"]).read_bytes()).hexdigest()
              == source["gui_copy_sha256"])
        doc = App.openDocument(source["gui_copy"])
        doc.recompute()
        from bim3117_freecad import services, snapshot
        from ui3117.exchange_dialog import show_quantities
        project = services.get_project(doc)
        check("all native and view proxies restore automatically", all(
            obj.Proxy.__class__.__module__.startswith("bim3117_freecad.")
            and obj.ViewObject.Proxy.__class__.__module__ == "ui3117.viewproviders" for obj in doc.Objects))
        check("all original persistent identities survive the GUI presentation save", source["identifiers"] == {
            obj.Name: obj.BIM3117Id for obj in doc.Objects})
        check("fresh GUI copy has visible authored wall modes, solids and doors", all(
            wall.ViewObject.DisplayMode == "Default" and wall.ViewObject.isVisible()
            and services.wall_body(wall).ViewObject.Visibility for wall in services.list_walls(project))
            and all(door.ViewObject.Visibility for door in services.list_doors(project)))
        check("fresh GUI revision exactly matches tested native IFC/CSV revision",
              snapshot.capture(project)["content_revision"] == source["content_revision"])
        Gui.activateWorkbench("BIM3117Workbench")
        before = (doc.UndoCount, doc.RedoCount, len(doc.Objects))
        panel = show_quantities(project)
        check("fresh GUI quantity rows reproduce all three native walls and doors",
              panel.wall_table.rowCount() == 3 and panel.door_table.rowCount() == 3
              and panel.source_snapshot["wall_rows"] == source["wall_rows"])
        check("fresh GUI quantity read preserves native history and model", before == (
            doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        check("original headless source remains unchanged", hashlib.sha256(Path(source["source"]).read_bytes()).hexdigest()
              == source["source_sha256"])
        report.update(status="passed", checks_passed=len(checks), gui_copy=source["gui_copy"],
                      content_revision=source["content_revision"])
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "headless-gui-reopen-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8")
        if panel is not None and not panel._closed:
            panel.close()
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
