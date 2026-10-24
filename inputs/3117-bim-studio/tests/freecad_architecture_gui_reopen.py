# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh FreeCAD GUI process gate for the saved Wall/Door sample.

Run after freecad_architecture_gui.run() in a new installed host process.
Proxy classes are not preregistered by this harness before opening the FCStd.
"""
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
    source = json.loads((output / "architecture-gui-report.json").read_text(encoding="utf-8"))
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(),
              "gui_up": bool(App.GuiUp), "checks": checks}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def near(a, b):
        return abs(a - b) <= 1e-3

    try:
        check("source GUI suite passed", source["status"] == "passed")
        check("view proxies not preregistered", "ui3117.viewproviders" not in sys.modules)
        doc = App.openDocument(source["sample"])
        doc.recompute()
        from bim3117_freecad import services
        project = services.get_project(doc)
        wall = doc.getObject(source["sample_wall"])
        door = doc.getObject(source["sample_door"])
        body = services.wall_body(wall)
        check("all native proxies restore automatically",
              all(obj.Proxy is not None and obj.Proxy.__class__.__module__.startswith("bim3117_freecad.")
                  for obj in doc.Objects))
        check("all view proxies restore automatically",
              all(obj.ViewObject.Proxy is not None
                  and obj.ViewObject.Proxy.__class__.__module__ == "ui3117.viewproviders" for obj in doc.Objects))
        check("fresh GUI restores stable identities",
              source["identifiers"] == {obj.Name: obj.BIM3117Id for obj in doc.Objects})
        check("fresh GUI restores wall type, levels, door host and body links",
              wall.WallType in services.list_wall_types(project) and wall.BaseLevel in services.list_levels(project)
              and wall.TopLevel in services.list_levels(project) and door.Host == wall
              and body.Wall == wall and door in body.Openings)
        check("fresh GUI restores cut solid and frame geometry",
              body.Shape.isValid() and near(body.Shape.Volume, source["wall_a_net_volume_mm3"])
              and not door.Shape.isNull() and door.Shape.isValid())
        check("fresh GUI restores wall presentation subtree",
              body in wall.ViewObject.Proxy.claimChildren() and door in wall.ViewObject.Proxy.claimChildren())
        check("fresh GUI preserves authored wall and subtree visibility",
              wall.ViewObject.Visibility and wall.ViewObject.isVisible()
              and wall.ViewObject.DisplayMode == "Default"
              and body.ViewObject.Visibility and door.ViewObject.Visibility)
        def scene_count(node):
            children = getattr(node, "getNumChildren", None)
            return 1 + (sum(scene_count(node.getChild(index)) for index in range(children()))
                        if callable(children) else 0)
        before_nodes = scene_count(wall.ViewObject.RootNode)
        wall.ViewObject.Proxy.finishRestoring()
        wall.ViewObject.Proxy.finishRestoring()
        check("repeated restored view attach does not duplicate display nodes",
              scene_count(wall.ViewObject.RootNode) == before_nodes and wall.ViewObject.isVisible())
        grids = services.list_grids(project)
        check("existing grid labels restore alongside architecture",
              len(grids) == 2 and all(hasattr(grid.ViewObject.Proxy, "_labels") and
                  str(grid.ViewObject.Proxy._labels[0][1].string.getValues()[0]) == grid.BubbleLabel for grid in grids))
        initial_volume = body.Shape.Volume
        upper = wall.TopLevel
        original_elevation = upper.Elevation.Value
        services.edit_level(upper, elevation_mm=original_elevation + 500)
        check("fresh GUI level edit recomputes cut body",
              near(body.Shape.Volume, initial_volume + wall.Length.Value * wall.Thickness.Value * 500))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("fresh GUI native Undo restores cut body and level",
              near(body.Shape.Volume, initial_volume) and near(upper.Elevation.Value, original_elevation))
        original_thickness = wall.WallType.Thickness.Value
        services.edit_wall_type(wall.WallType, thickness_mm=300)
        check("fresh GUI type edit propagates both wall instances",
              all(near(item.Thickness.Value, 300) for item in services.list_walls(project))
              and near(body.Shape.Volume, initial_volume * 300 / original_thickness))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("fresh GUI type Undo restores shapes without identity changes",
              near(body.Shape.Volume, initial_volume) and
              source["identifiers"] == {obj.Name: obj.BIM3117Id for obj in doc.Objects})
        check("document validates after fresh GUI edits", services.validate_document(doc, check_shapes=True))
        report.update(status="passed", checks_passed=len(checks), module_source=services.__file__)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "architecture-gui-reopen-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
