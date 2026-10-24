# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh-process Wall / Door restoration without importing their proxies first.

Run after freecad_architecture.main using the same installed addon profile in a
NEW FreeCAD process. This checks deserialization, executable dependencies and
native transactions; it is not a GUI or Windows acceptance test.
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

    def near(actual, expected):
        return abs(float(actual) - float(expected)) <= max(1e-6, abs(float(expected)) * 1e-9)

    try:
        source = json.loads((output / "architecture-test-report.json").read_text(encoding="utf-8"))
        check("saved architecture fixture comes from a passing native test", source["status"] == "passed")
        check("building model proxies not preregistered before FCStd open",
              "bim3117_freecad.building" not in sys.modules
              and "bim3117_freecad.model" not in sys.modules
              and "bim3117_freecad.services" not in sys.modules)
        doc = App.openDocument(str(Path(source["sample"]).resolve()))
        doc.recompute()
        from bim3117_freecad import services
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("FCStd restore imports building proxies from installed addon",
              "bim3117_freecad.building" in sys.modules
              and Path(sys.modules["bim3117_freecad.building"].__file__).resolve().is_relative_to(installed))
        project = services.get_project(doc)
        walls, types, doors = services.list_walls(project), services.list_wall_types(project), services.list_doors(project)
        check("fresh process restores one type two walls one door and two levels",
              len(types) == 1 and len(walls) == 2 and len(doors) == 1
              and len(services.list_levels(project)) == 2)
        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        check("fresh process preserves every saved native UUID", identifiers == source["element_ids"])
        names = source["element_names"]
        wall, body = doc.getObject(names["wall"]), doc.getObject(names["body"])
        wall_b, body_b = doc.getObject(names["wall_b"]), doc.getObject(names["body_b"])
        door, wall_type, upper = doc.getObject(names["door"]), doc.getObject(names["type"]), doc.getObject(names["top"])
        check("fresh process restores type level host and derived-body references",
              wall.WallType == wall_type and wall_b.WallType == wall_type
              and wall.TopLevel == upper and door.Host == wall
              and wall.Body == body and body.Wall == wall and body_b.Wall == wall_b
              and list(body.Openings) == [door] and list(body.OpeningIds) == [door.BIM3117Id]
              and all(obj.Proxy is not None for obj in doc.Objects))
        check("fresh process recomputes valid boolean wall solids",
              services.validate_document(doc, check_shapes=True)
              and near(body.Shape.Volume, 3_222_000_000) and near(body_b.Shape.Volume, 2_400_000_000))
        services.edit_level(upper, elevation_mm=3300)
        check("restored level dependency updates wall height and opening solid",
              near(body.Shape.Volume, 3_582_000_000) and near(body_b.Shape.Volume, 2_640_000_000))
        doc.undo()
        doc.recompute()
        check("fresh process native undo restores the complete cut model",
              near(body.Shape.Volume, 3_222_000_000) and near(upper.Elevation.Value, 3000))
        services.edit_wall_type(wall_type, thickness_mm=250)
        check("restored type propagation updates both wall instances",
              near(body.Shape.Volume, 4_027_500_000) and near(body_b.Shape.Volume, 3_000_000_000))
        doc.undo()
        doc.recompute()
        services.edit_door(door, width_mm=1000)
        check("restored hosted door edit cuts its new opening", near(body.Shape.Volume, 3_180_000_000))
        doc.undo()
        doc.recompute()
        check("fresh process edits retain IDs and undo restores original valid geometry",
              identifiers == {obj.Name: obj.BIM3117Id for obj in doc.Objects}
              and near(body.Shape.Volume, 3_222_000_000)
              and services.validate_document(doc, check_shapes=True))
        destination = output / "Architecture_Reopened.FCStd"
        doc.saveAs(str(destination))
        report.update(status="passed", sample=str(destination), checks_passed=len(report["checks"]),
                      element_ids=identifiers)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "architecture-reopen-test-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
