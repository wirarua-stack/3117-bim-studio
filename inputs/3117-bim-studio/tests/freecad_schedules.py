# SPDX-License-Identifier: GPL-3.0-or-later
"""Native schedules: independent quantities, source editing and publication."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App

from bim3117_freecad import catalog, schedules, services, snapshot
from bim3117_freecad.model import FoundationError, kind


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def history(doc):
    return doc.UndoCount, doc.RedoCount, len(doc.Objects)


def observation(project):
    return {"authored": snapshot._authored(project),
            "definitions": {obj.BIM3117Id: schedules._definition(obj) for obj in schedules.list_schedules(project)},
            "geometry": {obj.BIM3117Id: obj.Shape.exportBrepToString() for obj in project.Group if "Shape" in obj.PropertiesList}}


def close(actual, expected):
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    sample = output / "Schedules_Lifecycle.FCStd"
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Installed native schedule definitions, analytic quantity fixture, atomic row edits and guarded CSV publication"}
    doc = None

    def check(name, condition, **details):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed", **details})

    def reject(name, operation):
        before, observed = history(doc), observation(project)
        try:
            operation()
        except FoundationError as error:
            check(name, history(doc) == before and observation(project) == observed, rejection=str(error))
        else:
            raise AssertionError(name + ": command accepted")

    def undo():
        doc.undo()
        doc.recompute()

    def redo():
        doc.redo()
        doc.recompute()

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("schedule services load from the installed add-on",
              all(Path(module.__file__).resolve().is_relative_to(installed)
                  for module in (schedules, catalog, services, snapshot)))
        project = services.create_project("Schedule quantity fixture", levels=[("L00", 0), ("L01", 3000)])
        doc = project.Document
        lower, upper = services.list_levels(project)
        concrete = catalog.create_material(project, "Concrete", code="CONC")
        finish = catalog.create_material(project, "Finish", code="FIN")
        wall_type = services.create_wall_type(project, "Wall 200", 200)
        catalog.edit_type(wall_type, material=concrete)
        first_wall = services.create_wall(project, "Wall A", wall_type, lower, upper, end_x_mm=4000)
        second_wall = services.create_wall(project, "Wall B", wall_type, lower, upper,
                                           start_y_mm=5000, end_x_mm=2000, end_y_mm=5000)
        services.create_door(project, "Door A", first_wall, offset_mm=500, width_mm=900, height_mm=2100)
        slab_type = catalog.create_type(project, "Slab 200", "Slab", code="SL200", layers=[
            {"material": finish, "thickness_mm": 50, "role": "finish"},
            {"material": concrete, "thickness_mm": 150, "role": "structure"}])
        slab1 = services.create_slab(project, "Slab A", lower, [(0, 0), (2000, 0), (2000, 3000), (0, 3000)], 200)
        slab2 = services.create_slab(project, "Slab B", lower, [(4000, 0), (6000, 0), (6000, 3000), (4000, 3000)], 200)
        catalog.assign_types([slab1, slab2], slab_type)
        baseline = snapshot.capture(project)
        base_revision = baseline["content_revision"]
        count = len(doc.Objects)
        doc.clearUndos()
        walls = schedules.create_schedule(project, "Walls", "Wall")
        wall_name, wall_id = walls.Name, walls.BIM3117Id
        check("first schedule and native set are created in one transaction", doc.UndoCount == 1 and len(doc.Objects) == count + 2)
        check("schedule definitions are native siblings outside the building Project",
              walls not in project.Group and schedules.get_schedule_set(project) not in project.Group
              and walls in schedules.get_schedule_set(project).Group)
        undo()
        check("Undo removes the first schedule and its newly created set", len(doc.Objects) == count and schedules.get_schedule_set(project) is None)
        redo()
        walls = doc.getObject(wall_name)
        check("Redo restores stable schedule identity", walls.BIM3117Id == wall_id)
        slabs = schedules.create_schedule(project, "Slabs", "Slab", level=lower, element_type=slab_type)
        materials = schedules.create_schedule(project, "Materials", "Material")
        wall_data = schedules.capture_schedule(walls)
        check("schedule-only objects leave the building content revision unchanged", wall_data["model_revision"] == base_revision)
        check("independent wall schedule gross opening and net quantities agree",
              len(wall_data["rows"]) == 2 and close(wall_data["totals"]["gross_volume_m3"], 3.6)
              and close(wall_data["totals"]["opening_volume_m3"], 0.378)
              and close(wall_data["totals"]["net_volume_m3"], 3.222))
        slab_data = schedules.capture_schedule(slabs)
        check("Level and Type filters retain two independently dimensioned native slabs",
              len(slab_data["rows"]) == 2 and close(slab_data["totals"]["net_area_m2"], 12)
              and close(slab_data["totals"]["net_volume_m3"], 2.4))
        material_data = schedules.capture_schedule(materials)
        check("material rows count unique source products separately from their layers",
              len(material_data["rows"]) == 6 and material_data["totals"]["source_element_count"] == 4
              and material_data["totals"]["source_row_count"] == 6
              and close(material_data["totals"]["net_volume_m3"], 5.622))
        check("material coverage explicitly exposes the unassigned generic door frame",
              material_data["coverage"]["material"]["unassigned_product_count"] == 1
              and material_data["coverage"]["material"]["complete"] is False)
        before, prior = observation(project), history(doc)
        for _ in range(2):
            schedules.capture_schedule(slabs)
            schedules.capture_schedule(materials)
        check("read-only capture preserves source BReps object count and Undo history",
              observation(project) == before and history(doc) == prior)
        ungrouped_revision = schedules.schedule_state(materials)
        schedules.edit_schedule(materials, group_by="Material", sort_by="Material")
        grouped = schedules.capture_schedule(materials)
        check("grouping edits only the schedule revision in one native history step",
              doc.UndoCount == prior[0] + 1 and grouped["model_revision"] == base_revision
              and grouped["schedule_revision"] != ungrouped_revision["schedule_revision"])
        concrete_row = next(row for row in grouped["rows"] if row["material_id"] == concrete.BIM3117Id)
        finish_row = next(row for row in grouped["rows"] if row["material_id"] == finish.BIM3117Id)
        check("material groups preserve analytic volumes and distinct source identities",
              len(grouped["rows"]) == 2 and close(concrete_row["net_volume_m3"], 5.022)
              and close(finish_row["net_volume_m3"], .6) and concrete_row["count"] == 4 and finish_row["count"] == 2)
        check("grouped columns never sum thickness or section dimensions",
              not {"thickness_m", "width_m", "height_m", "depth_m"}.intersection(column["key"] for column in grouped["columns"]))
        undo()
        check("Undo restores the exact ungrouped schedule identity", schedules.schedule_state(materials) == ungrouped_revision)
        redo()
        schedules.edit_schedule(slabs, group_by="Type")
        slab_group = schedules.capture_schedule(slabs)
        check("Type grouping retains both explicit editable source UUIDs", len(slab_group["rows"]) == 1
              and slab_group["rows"][0]["element_ids"] == sorted([slab1.BIM3117Id, slab2.BIM3117Id])
              and slab_group["rows"][0]["count"] == 2)
        schedules.edit_schedule(slabs, name_filter="sLaB a", group_by="None")
        filtered = schedules.capture_schedule(slabs)
        check("name filter is case-insensitive on source names before grouping",
              [row["element_ids"] for row in filtered["rows"]] == [[slab1.BIM3117Id]])
        schedules.edit_schedule(slabs, name_filter="missing")
        empty = schedules.capture_schedule(slabs)
        check("empty schedules have explicit zero totals and stable columns", not empty["rows"]
              and empty["totals"]["net_volume_m3"] == 0 and empty["columns"] == filtered["columns"])
        undo()
        check("fixture retains a real Redo branch for invalid proposal tests", doc.RedoCount > 0)
        reject("incompatible Type filter is rejected before native mutation", lambda: schedules.edit_schedule(slabs, element_type=wall_type))
        reject("ambiguous whole-product Material grouping is rejected", lambda: schedules.edit_schedule(slabs, group_by="Material"))
        reject("invalid schedule names preserve the Redo branch", lambda: schedules.edit_schedule(slabs, name="bad\nname"))
        reject("duplicate schedule names are rejected", lambda: schedules.create_schedule(project, "Walls"))
        reject("computed quantities cannot be written back as authored inputs",
               lambda: schedules.edit_row(slabs, slab1.BIM3117Id, {"net_volume_m3": 100}))
        reject("hidden filtered rows cannot be edited through stale row identity",
               lambda: schedules.edit_row(slabs, slab2.BIM3117Id, {"offset_mm": 100}))
        reject("typed dimensions cannot be overridden through a schedule row",
               lambda: schedules.edit_row(slabs, slab1.BIM3117Id, {"thickness_mm": 500}))
        reject("caller-supplied JSON cannot become the schedule's authority",
               lambda: schedules.capture_schedule(slabs, project_snapshot={"rows": []}))
        state = schedules.schedule_state(slabs)
        old_id, old_count = slab1.BIM3117Id, doc.UndoCount
        schedules.edit_row(slabs, old_id, {"name": "Slab A revised", "offset_mm": 100},
                           expected_model_revision=state["model_revision"], expected_schedule_revision=state["schedule_revision"])
        check("source label and placement commit together in one native transaction",
              doc.UndoCount == old_count + 1 and slab1.Label == "Slab A revised"
              and slab1.Offset.Value == 100 and slab1.BIM3117Id == old_id and close(slab1.Shape.BoundBox.ZMax, 100))
        reject("stale model revision blocks row edits before mutation",
               lambda: schedules.edit_row(slabs, old_id, {"offset_mm": 200},
                                          expected_model_revision=state["model_revision"], expected_schedule_revision=state["schedule_revision"]))
        undo()
        check("Undo restores both original source values and original model revision",
              slab1.Label == "Slab A" and slab1.Offset.Value == 0 and schedules.schedule_state(slabs) == state)
        redo()
        check("Redo restores the edited source solid", slab1.Label == "Slab A revised" and slab1.Offset.Value == 100)
        undo()
        schedules.edit_schedule(slabs, descending=True)
        reject("stale definition revision blocks edits with an otherwise current building",
               lambda: schedules.edit_row(slabs, old_id, {"offset_mm": 200},
                                          expected_model_revision=state["model_revision"], expected_schedule_revision=state["schedule_revision"]))
        undo()
        stale = schedules.schedule_state(walls)
        services.edit_wall(first_wall, name="=WALL-A")
        target = output / "Walls.csv"
        before, prior = observation(project), history(doc)
        result = schedules.export_schedule(walls, target, overwrite=True)
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        table = list(csv.DictReader(io.StringIO(target.read_text(encoding="utf-8-sig"))))
        check("schedule CSV uses UTF-8 BOM and neutralizes formula-like labels",
              target.read_bytes().startswith(b"\xef\xbb\xbf") and any(row["name"] == "'=WALL-A" for row in table))
        check("CSV metadata retains original labels source identities and exact payload hash",
              any(row["name"] == "=WALL-A" for row in metadata["snapshot"]["rows"])
              and metadata["files"][0]["sha256"] == file_hash(target)
              and all(row["element_ids"] for row in table) and metadata["model_revision"] == result["model_revision"])
        check("publication creates no source changes or history entries", history(doc) == prior and observation(project) == before)
        previous_bytes = [Path(path).read_bytes() for path in result["files"]]
        reject("schedule publication never silently overwrites existing files", lambda: schedules.export_schedule(walls, target))
        reject("stale preview cannot publish a new schedule bundle",
               lambda: schedules.export_schedule(walls, output / "Stale.csv", expected_model_revision=stale["model_revision"],
                                                  expected_schedule_revision=stale["schedule_revision"]))
        check("rejected publication leaves existing bytes intact and no stale new files",
              previous_bytes == [Path(path).read_bytes() for path in result["files"]]
              and not any(Path(path).exists() for path in schedules.output_paths(output / "Stale.csv")))
        # A source callback changes the schedule after CSV staging. The shared
        # publisher must reject it before touching either existing destination.
        from bim3117_freecad import exchange
        old_writer = exchange._csv_bytes

        def changed_writer(rows, columns):
            payload = old_writer(rows, columns)
            schedules.edit_schedule(walls, descending=not bool(walls.Descending))
            return payload

        exchange._csv_bytes = changed_writer
        try:
            try:
                schedules.export_schedule(walls, target, overwrite=True)
            except FoundationError:
                check("mid-publication definition changes preserve both old destination files",
                      previous_bytes == [Path(path).read_bytes() for path in result["files"]])
            else:
                raise AssertionError("Stale publication accepted")
        finally:
            exchange._csv_bytes = old_writer
        undo()
        undo()  # restore source label, leaving its valid Redo branch
        check("read/export tests restore the original analytic model", snapshot.capture(project)["content_revision"] == base_revision)
        spare = catalog.create_type(project, "Unused Slab", "Slab", thickness_mm=250)
        spare_level = services.add_level(project, "Unused Level", 9000)
        linked = schedules.create_schedule(project, "Spare filter", "Slab", level=spare_level, element_type=spare)
        reject("Type deletion respects schedule filter dependencies", lambda: catalog.delete_type(spare))
        reject("Level deletion respects schedule filter dependencies", lambda: services.delete_level(spare_level))
        spare_id = spare.BIM3117Id
        doc.openTransaction("QA raw delete referenced type")
        token = App.getActiveTransaction()
        doc.removeObject(spare.Name)
        doc.recompute()
        doc.commitTransaction()
        if token is not None and App.getActiveTransaction() == token:
            App.closeActiveTransaction()
        check("raw native deletion retains the expected filter UUID and reports a broken reference",
              linked.FilterType is None and linked.FilterTypeId == spare_id and bool(linked.ValidationMessage))
        reject("broken schedule cannot be captured as an unfiltered table", lambda: schedules.capture_schedule(linked))
        check("a broken documentation filter does not prevent valid building quantities",
              len(snapshot.capture(project)["slab_rows"]) == 2)
        schedules.edit_schedule(linked, element_type=None)
        check("explicit filter detachment repairs the schedule without inventing a reference",
              not linked.FilterTypeId and schedules.capture_schedule(linked)["rows"] == [])
        linked_name, linked_id = linked.Name, linked.BIM3117Id
        schedules.delete_schedule(linked)
        check("schedule deletion removes only its native definition", doc.getObject(linked_name) is None and len(project.Group) > 0)
        undo()
        linked = doc.getObject(linked_name)
        check("Undo schedule deletion restores identity and references", linked.BIM3117Id == linked_id and linked.FilterLevel == spare_level)
        schedules.delete_schedule(linked)
        services.delete_level(spare_level)
        check("filtered level can be deleted after its last schedule reference is removed", all(obj.Label != "Unused Level" for obj in services.list_levels(project)))
        services.validate_document(doc, check_shapes=True)
        final = snapshot.capture(project)
        doc.saveAs(str(sample))
        states = {obj.BIM3117Id: schedules.schedule_state(obj) for obj in schedules.list_schedules(project)}
        contents = {obj.BIM3117Id: schedules.capture_schedule(obj) for obj in schedules.list_schedules(project)}
        report.update(status="passed", checks_passed=len(report["checks"]), sample=str(sample), sample_sha256=file_hash(sample),
                      model_revision=final["content_revision"], schedule_states=states,
                      definitions={obj.BIM3117Id: schedules._definition(obj) for obj in schedules.list_schedules(project)},
                      element_ids={obj.Name: obj.BIM3117Id for obj in doc.Objects},
                      schedule_rows={identity: data["rows"] for identity, data in contents.items()},
                      schedule_totals={identity: data["totals"] for identity, data in contents.items()},
                      installed_modules={module.__name__: {"path": module.__file__, "sha256": file_hash(module.__file__)}
                                         for module in (schedules, catalog, services, snapshot)})
        return report
    except BaseException as error:
        report.update(status="failed", checks_passed=len(report["checks"]), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "schedules-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
