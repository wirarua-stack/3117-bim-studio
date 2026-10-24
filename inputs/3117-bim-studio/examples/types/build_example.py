# SPDX-License-Identifier: GPL-3.0-or-later
"""Create a synthetic typed/material/schedule example from the frozen FCStd.

Run inside FreeCAD with the installed 3117 workbench. The frozen source is
copied and never overwritten; destination must be a new .FCStd file. Output
CSV/IFC/schedules are derived from this same native document revision.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import FreeCAD as App

from bim3117_freecad import catalog, drawings, exchange, schedules, services, snapshot
from bim3117_freecad.model import kind

SOURCE_SHA256 = "92b6cd2fc012ce1ae2815ed511bed2c676451c0a2d8c9b2caa1823eeba81882c"
SOURCE_REVISION = "6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def add_catalogue(project):
    definitions = [("Concrete", "CONC"), ("Masonry", "MASONRY"), ("Plaster", "PLASTER"),
                   ("Floor finish", "FINISH"), ("Screed", "SCREED"),
                   ("Timber frame", "TIMBER"), ("Aluminium frame", "ALU")]
    materials = {code: catalog.create_material(project, name, code=code) for name, code in definitions}
    wall_type = services.list_wall_types(project)[0]
    catalog.edit_type(wall_type, name="Wall 200 layered", code="W200", layers=[
        {"material": materials["PLASTER"], "thickness_mm": 15, "role": "finish"},
        {"material": materials["MASONRY"], "thickness_mm": 170, "role": "core"},
        {"material": materials["PLASTER"], "thickness_mm": 15, "role": "finish"}])
    types = {"Wall": wall_type}
    types["Slab"] = catalog.create_type(project, "Slab 150 layered", "Slab", code="S150", layers=[
        {"material": materials["FINISH"], "thickness_mm": 10, "role": "finish"},
        {"material": materials["SCREED"], "thickness_mm": 40, "role": "substrate"},
        {"material": materials["CONC"], "thickness_mm": 100, "role": "structure"}])
    types["Column"] = catalog.create_type(project, "Column 300 x 300", "Column", code="C300",
                                           width_mm=300, depth_mm=300, material=materials["CONC"])
    types["Beam"] = catalog.create_type(project, "Beam 300 x 450", "Beam", code="B300450",
                                         width_mm=300, depth_mm=450, material=materials["CONC"])
    types["Door"] = catalog.create_type(project, "Door 900 x 2100", "Door", code="D09021",
                                         width_mm=900, height_mm=2100, material=materials["TIMBER"])
    types["Window"] = catalog.create_type(project, "Window 1200 x 1200", "Window", code="WN1212",
                                           width_mm=1200, height_mm=1200, material=materials["ALU"])
    for category in ("Slab", "Column", "Beam", "Door", "Window"):
        catalog.assign_types([obj for obj in project.Group if kind(obj) == category], types[category])
    return materials, types


def add_schedules(project):
    result = [schedules.create_schedule(project, category + " Schedule", category, sort_by="Level")
              for category in ("Wall", "Slab", "Column", "Beam", "Door", "Window")]
    result.append(schedules.create_schedule(project, "Walls by Type", "Wall", group_by="Type"))
    result.append(schedules.create_schedule(project, "Material Details", "Material", sort_by="Material"))
    result.append(schedules.create_schedule(project, "Materials by Material", "Material", group_by="Material", sort_by="Material"))
    return result


def build(destination=None):
    source = Path(__file__).resolve().parents[1] / "drawings" / "Drawings_Workbench.FCStd"
    destination = (Path(destination) if destination is not None else
                   Path(__file__).resolve().parent / "Types_Quantities_Workbench.FCStd").resolve()
    if destination.suffix.lower() != ".fcstd":
        raise ValueError("Choose a new .FCStd destination")
    metadata_path = destination.with_name("types-example.json")
    if destination.exists() or metadata_path.exists():
        raise FileExistsError("Choose a new fixture destination; existing examples are never overwritten")
    if sha(source) != SOURCE_SHA256:
        raise ValueError("The frozen v0.4.0 drawing fixture has changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = None
    staging = tempfile.TemporaryDirectory(prefix="3117-types-fixture-")
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    try:
        copied = Path(staging.name) / source.name
        shutil.copy2(source, copied)
        doc = App.openDocument(str(copied))
        doc.UndoMode = 1
        doc.recompute()
        project = services.get_project(doc)
        original = snapshot.capture(project)
        check("frozen v0.4.0 source model revision matches", original["content_revision"] == SOURCE_REVISION)
        original_ids = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        original_shapes = {obj.Name: obj.Shape.copy() for obj in project.Group
                           if kind(obj) in ("WallBody", "Slab", "Column", "Beam", "Door", "Window")}
        original_sheets = {obj.BIM3117Id: drawings.sheet_state(obj)["drawing_revision"] for obj in drawings.list_sheets(project)}
        materials, types = add_catalogue(project)
        tables = add_schedules(project)
        captured = snapshot.capture(project)
        check("all original native UUIDs are retained", all(doc.getObject(name).BIM3117Id == value for name, value in original_ids.items()))
        for name, shape in original_shapes.items():
            current = doc.getObject(name).Shape
            check(name + " retains its exact native solid envelope",
                  shape.cut(current).Volume < 1e-3 and current.cut(shape).Volume < 1e-3)
        check("the same 33 products are mapped exactly once", sum(len(captured[name + "_rows"])
              for name in ("wall", "slab", "column", "beam", "door", "window")) == 33)
        check("catalogue has six types and seven explicit materials", len(captured["type_rows"]) == 6 and len(materials) == 7)
        check("all products have native material coverage and 55 partition rows", captured["material_totals"]["complete"]
              and captured["material_totals"]["assigned_product_count"] == 33 and len(captured["material_rows"]) == 55)
        check("all four Views and two Sheets retain their existing definitions",
              len(drawings.list_views(project)) == 4 and len(drawings.list_sheets(project)) == 2
              and {obj.BIM3117Id: drawings.sheet_state(obj)["drawing_revision"] for obj in drawings.list_sheets(project)} == original_sheets)
        check("all nine schedules share the same current model revision", len(tables) == 9
              and all(schedules.schedule_state(obj)["model_revision"] == captured["content_revision"] for obj in tables))
        doc.saveAs(str(destination))
        captured = snapshot.capture(project)
        csv_result = exchange.export_csv(project, destination.with_suffix(".csv"), expected_revision=captured["content_revision"])
        ifc_result = exchange.export_ifc(project, destination.with_suffix(".ifc"), expected_revision=captured["content_revision"])
        schedule_results = []
        for obj in tables:
            state = schedules.schedule_state(obj)
            schedule_results.append(schedules.export_schedule(obj, destination.parent / (obj.Label.replace(" ", "_") + ".csv"),
                                    expected_model_revision=state["model_revision"], expected_schedule_revision=state["schedule_revision"]))
        snapshot_path = destination.with_name("types-snapshot.json")
        snapshot_path.write_text(json.dumps(captured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        check("source FCStd stays byte-for-byte unchanged", sha(source) == SOURCE_SHA256)
        result = {"schema": 1, "status": "passed", "checks": checks, "checks_passed": len(checks),
                  "fixture": "Synthetic two-storey native Types and Quantities example", "freecad": App.Version(),
                  "file": destination.name, "sha256": sha(destination), "source_file": "../drawings/Drawings_Workbench.FCStd",
                  "source_sha256": SOURCE_SHA256, "source_model_revision": SOURCE_REVISION,
                  "content_revision": captured["content_revision"], "snapshot_sha256": sha(snapshot_path),
                  "element_ids": {obj.Name: obj.BIM3117Id for obj in doc.Objects},
                  "types": [catalog.type_definition(obj) for obj in types.values()],
                  "materials": [catalog.material_definition(obj) for obj in materials.values()],
                  "schedule_states": {obj.BIM3117Id: schedules.schedule_state(obj) for obj in tables},
                  "csv_result": csv_result, "ifc_result": ifc_result, "schedule_results": schedule_results,
                  "scope": "Synthetic catalogue choices; product geometry is unchanged. Material rows partition product volumes; they are not additional products or construction cost estimates."}
        metadata_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
        staging.cleanup()


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
