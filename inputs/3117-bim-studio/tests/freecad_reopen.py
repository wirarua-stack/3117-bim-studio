# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh-process FCStd restoration check without preregistering proxy classes.

Call main(output_dir) in a NEW FreeCAD Python process after the foundation test.
The workbench must have been installed normally, but no native model or
service module is imported before FreeCAD opens the saved document.
"""
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": []}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    try:
        foundation = json.loads((output / "foundation-test-report.json").read_text(encoding="utf-8"))
        source_path = foundation["sample"]
        check("proxy class not preregistered", "bim3117_freecad.model" not in sys.modules
              and "bim3117_freecad.services" not in sys.modules)
        doc = App.openDocument(str(Path(source_path).resolve()))
        check("FCStd restoration imports proxy module automatically", "bim3117_freecad.model" in sys.modules)
        doc.recompute()
        from bim3117_freecad import services
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("proxy module comes from installed addon",
              Path(sys.modules["bim3117_freecad.model"].__file__).resolve().is_relative_to(installed))
        project = services.get_project(doc)
        levels, grids = services.list_levels(project), services.list_grids(project)
        check("fresh process restores hierarchy", len(levels) == 2 and len(grids) == 1)
        grid = grids[0]
        level = grid.ReferenceLevel
        saved_ids = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        check("fresh process UUIDs match saved fixture identities", saved_ids == foundation["element_ids"])
        check("fresh process restores native links and executable proxies", level in levels
              and grid.Project == project and grid.Proxy.__class__.__module__ == "bim3117_freecad.model"
              and level.Proxy.__class__.__module__ == "bim3117_freecad.model"
              and all(obj.Proxy is not None and obj.Proxy.__class__.__module__ == "bim3117_freecad.model" for obj in doc.Objects))
        expected = level.Elevation.Value + 750 + grid.ElevationOffset.Value
        services.edit_level(level, elevation_mm=level.Elevation.Value + 750)
        check("fresh process edit recomputes dependent grid", abs(grid.Shape.BoundBox.ZMin - expected) < 1e-6)
        check("fresh process edit retains element UUIDs", saved_ids == {obj.Name: obj.BIM3117Id for obj in doc.Objects})
        doc.undo()
        doc.recompute()
        check("fresh process native undo restores dependent grid", abs(grid.Shape.BoundBox.ZMin - (expected - 750)) < 1e-6)
        destination = output / "Foundation_Reopened.FCStd"
        doc.saveAs(str(destination))
        report.update(status="passed", sample=str(destination), checks_passed=len(report["checks"]))
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "reopen-test-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
