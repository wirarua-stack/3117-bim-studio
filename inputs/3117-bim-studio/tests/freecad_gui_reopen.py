# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh-process GUI restoration gate, run after freecad_gui_smoke.run()."""
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
    source = json.loads((output / "gui-smoke-report.json").read_text(encoding="utf-8"))
    checks = []
    report = {"status": "running", "checks": checks, "checks_passed": 0,
              "freecad": App.Version(), "platform": platform.platform(),
              "python": sys.version, "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp)}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def near(a, b):
        return abs(a-b) < 1e-6

    try:
        check("source GUI suite passed", source["status"] == "passed")
        # Import no model or view-provider classes before FreeCAD opens the file.
        doc = App.openDocument(source["sample"])
        doc.recompute()
        from bim3117_freecad import services
        project = services.get_project(doc)
        check("all model proxies restored in fresh GUI process",
              all(obj.Proxy.__class__.__module__ == "bim3117_freecad.model" for obj in doc.Objects))
        check("all view proxies restored in fresh GUI process",
              all(obj.ViewObject.Proxy.__class__.__module__ == "ui3117.viewproviders" for obj in doc.Objects))
        check("fresh GUI reopen preserves original identities",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects} == source["identifiers"])
        grids = services.list_grids(project)
        check("all grid labels have reconstructed Coin scene nodes",
              all(hasattr(grid.ViewObject.Proxy, "_labels") and
                  str(grid.ViewObject.Proxy._labels[0][1].string.getValues()[0]) == grid.BubbleLabel
                  for grid in grids))
        grid = next(grid for grid in grids if grid.BubbleLabel == "A1")
        level = grid.ReferenceLevel
        check("reference level and geometry restored", near(level.Elevation.Value, 3300)
              and near(grid.Shape.BoundBox.ZMin, 3300))
        services.edit_level(level, elevation_mm=3600)
        check("fresh-process native edit recomputes geometry and text position",
              near(grid.Shape.BoundBox.ZMin, 3600) and
              near(grid.ViewObject.Proxy._labels[0][0].translation.getValue()[2], 3600))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("fresh-process native Undo restores geometry and text position",
              near(level.Elevation.Value, 3300) and near(grid.Shape.BoundBox.ZMin, 3300) and
              near(grid.ViewObject.Proxy._labels[0][0].translation.getValue()[2], 3300))
        check("document validates after fresh GUI lifecycle", services.validate_document(doc, check_shapes=True))
        report.update(status="passed", checks_passed=len(checks), module_source=services.__file__)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(checks))
        raise
    finally:
        (output / "gui-reopen-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
