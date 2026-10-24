# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh installed-host process verifies native exchange content identity."""
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
        return abs(float(actual) - float(expected)) <= max(1e-8, abs(float(expected)) * 1e-8)

    try:
        source = json.loads((output / "exchange-test-report.json").read_text(encoding="utf-8"))
        check("saved exchange fixture comes from a passing native integration run", source["status"] == "passed")
        check("model proxies are not preregistered before opening FCStd",
              "bim3117_freecad.model" not in sys.modules and "bim3117_freecad.building" not in sys.modules)
        doc = App.openDocument(str(Path(source["sample"]).resolve()))
        doc.recompute()
        from bim3117_freecad import exchange, services, snapshot
        project = services.get_project(doc)
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("snapshot loads from the installed addon after automatic proxy restoration",
              Path(snapshot.__file__).resolve().is_relative_to(installed)
              and services.validate_document(doc, check_shapes=True))
        current = snapshot.capture(project)
        check("fresh process preserves content revision independently of file name and capture time",
              current["content_revision"] == source["content_revision"])
        identifiers = {obj.Name: obj.BIM3117Id for obj in doc.Objects if services.kind(obj)}
        check("fresh process preserves every saved native element UUID", identifiers == source["element_ids"])
        check("fresh process quantity rows and actual net volumes match the saved multiwall fixture",
              len(current["wall_rows"]) == len(current["door_rows"]) == 3
              and all(near(row["net_volume_m3"], source["expected_net_volumes_m3"][row["element_id"]])
                      for row in current["wall_rows"]))
        top = doc.getObject(source["element_names"]["top"])
        services.edit_level(top, elevation_mm=3300)
        changed = snapshot.capture(project)
        main_id = doc.getObject(source["element_names"]["wall"]).BIM3117Id
        main_row = next(row for row in changed["wall_rows"] if row["element_id"] == main_id)
        check("restored dependency edit invalidates prior snapshot and updates net quantity",
              not snapshot.is_current(project, current) and near(main_row["net_volume_m3"], 3.582))
        doc.undo()
        doc.recompute()
        check("fresh process Undo restores original content revision", snapshot.is_current(project, current))
        output_ifc = output / "Quantity_Exchange_Reopened.ifc"
        result = exchange.export_ifc(project, output_ifc, expected_revision=current["content_revision"])
        import ifcopenshell
        previous = ifcopenshell.open(source["ifc"])
        reopened = ifcopenshell.open(str(output_ifc))
        check("IFC export after fresh FCStd restore preserves every rooted GlobalId",
              {item.GlobalId for item in previous.by_type("IfcRoot")}
              == {item.GlobalId for item in reopened.by_type("IfcRoot")})
        check("fresh IFC and metadata retain the same source content revision",
              result["content_revision"] == current["content_revision"]
              and json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))["content_revision"]
              == current["content_revision"])
        report.update(status="passed", checks_passed=len(report["checks"]),
                      content_revision=current["content_revision"], ifc=str(output_ifc), element_ids=identifiers)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(),
                      checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "exchange-reopen-test-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
