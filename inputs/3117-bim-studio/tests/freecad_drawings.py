# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed-host lifecycle acceptance for native drawing definitions.

The frozen v0.3.0 native building is the input. Every mutation is confined to
the opened document and the disposable output sample; the source is never
saved. The companion fresh-process suite restores this sample independently.
"""
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

import FreeCAD as App

from bim3117_freecad import drawing_export, drawing_geometry, drawing_render, drawings, services, snapshot
from bim3117_freecad.model import DOCUMENTATION_KINDS, FoundationError, kind

SOURCE_SHA256 = "9a0e2efc3613747b2806ead5ecd61b6b74d757a229ca9ebc5e649afe28e68995"
MODEL_REVISION = "6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a"
SVG_NS = "{http://www.w3.org/2000/svg}"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def history(doc):
    return doc.UndoCount, doc.RedoCount, len(doc.Objects)


def observation(project):
    """Observe authoritative definitions, native identities and BReps directly."""
    objects = []
    for obj in project.Document.Objects:
        values = {"name": obj.Name, "label": obj.Label, "kind": kind(obj), "id": obj.BIM3117Id,
                  "group": [item.Name for item in getattr(obj, "Group", [])]}
        if "Shape" in obj.PropertiesList:
            values["brep"] = hashlib.sha256(obj.Shape.exportBrepToString().encode("utf-8")).hexdigest()
        if kind(obj) in DOCUMENTATION_KINDS:
            values["project"] = getattr(getattr(obj, "Project", None), "Name", None)
            for prop in ("ProjectId", "DrawingSchema", "BIM3117Schema", "BIM3117Version", "LevelId",
                         "ViewType", "Direction", "BottomOffset", "CutOffset", "TopOffset", "Depth",
                         "ScaleDenominator", "ShowDimensions", "ShowTags", "ShowGrid", "ShowLevels",
                         "Number", "Issue", "Author", "Paper", "Orientation", "ViewIds"):
                if prop in obj.PropertiesList:
                    value = getattr(obj, prop)
                    values[prop] = float(value.Value) if hasattr(value, "Value") else value
            if "Level" in obj.PropertiesList:
                values["level"] = getattr(obj.Level, "Name", None)
            if "Origin" in obj.PropertiesList:
                values["origin"] = [obj.Origin.x, obj.Origin.y, obj.Origin.z]
            if "Views" in obj.PropertiesList:
                values["views"] = [view.Name for view in obj.Views]
        objects.append(values)
    return {"authored": snapshot._authored(project), "objects": objects}


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    repository = Path(__file__).resolve().parents[1]
    source = repository / "examples/building/Building_Authoring_Workbench.FCStd"
    sample = output / "Drawings_Workbench.FCStd"
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Installed native View/Sheet transactions, source revisions, OCCT capture and SVG publication"}
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
            check(name, history(doc) == before and observation(project) == observed,
                  rejection=str(error))
        else:
            raise AssertionError(name + ": operation was accepted")

    def undo():
        doc.undo()
        doc.recompute()

    def redo():
        doc.redo()
        doc.recompute()

    def raw_delete(obj, label):
        doc.openTransaction(label)
        token = App.getActiveTransaction()
        try:
            doc.removeObject(obj.Name)
            doc.recompute()
            doc.commitTransaction()
        except BaseException:
            doc.abortTransaction()
            raise
        finally:
            if token is not None and App.getActiveTransaction() == token:
                App.closeActiveTransaction()

    try:
        if sample.resolve() in {source.resolve(), (repository / "examples/drawings/Drawings_Workbench.FCStd").resolve()}:
            raise ValueError("Use a disposable test output directory, not a canonical example folder")
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        modules = (drawings, drawing_geometry, drawing_render, drawing_export, services, snapshot)
        check("drawing and model modules load from the installed add-on",
              all(Path(module.__file__).resolve().is_relative_to(installed) for module in modules))
        check("the frozen v0.3.0 source has its recorded SHA256", file_hash(source) == SOURCE_SHA256)
        doc = App.openDocument(str(source))
        doc.UndoMode = 1
        doc.recompute()
        project = services.get_project(doc)
        baseline = snapshot.capture(project)
        initial_ids = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        initial_count = len(doc.Objects)
        check("unchanged v0.3.0 building keeps its exact legacy model revision",
              baseline["content_revision"] == MODEL_REVISION)
        check("legacy fixture has 33 supported products and no unsupported objects",
              sum(len(baseline[key]) for key in ("wall_rows", "door_rows", "window_rows", "slab_rows", "column_rows", "beam_rows")) == 33
              and baseline["coverage"]["counts"]["unsupported"] == 0)
        levels = {level.Label: level for level in services.list_levels(project)}
        lower, upper_level = levels["L00"], levels["L01"]
        doc.clearUndos()
        ground = drawings.create_view(project, "Ground Plan", level=lower,
                                      bottom_offset_mm=-150, cut_offset_mm=1200, top_offset_mm=2800)
        ground_name, ground_id = ground.Name, ground.BIM3117Id
        check("first view and drawing set are one native transaction",
              doc.UndoCount == 1 and len(doc.Objects) == initial_count + 2)
        check("drawing definitions stay outside the native building Project group",
              drawings.get_drawing_set(project) not in project.Group and ground not in project.Group
              and ground in drawings.get_drawing_set(project).Group)
        undo()
        check("Undo removes the first view and its new drawing set",
              len(doc.Objects) == initial_count and drawings.get_drawing_set(project) is None)
        redo()
        ground = doc.getObject(ground_name)
        check("Redo restores the authored view UUID and Level reference",
              ground.BIM3117Id == ground_id and ground.Level == lower and ground.LevelId == lower.BIM3117Id)

        before = doc.UndoCount
        single = drawings.create_sheet(project, "Single-view QA", "QA-001", [ground], author="3117 QA")
        check("one-view sheet creation is one native transaction",
              doc.UndoCount == before + 1 and single.ViewIds == [ground_id])
        first_state = drawings.sheet_state(single)
        native_before, history_before = observation(project), history(doc)
        single_capture = drawings.capture_sheet(single)
        first_geometry = single_capture["views"][0]["geometry"]
        check("one-view capture contains actual cut and projected native geometry",
              len(single_capture["views"]) == 1 and first_geometry["cut_faces"] and first_geometry["visible_paths"])
        check("capture includes all native Levels and Grids as datum references",
              len(single_capture["views"][0]["levels"]) == 3 and len(single_capture["views"][0]["grids"]) == 4)
        check("native capture changes no authored definition BRep history or object count",
              observation(project) == native_before and history(doc) == history_before)
        before = doc.UndoCount
        drawings.edit_view(ground, cut_offset_mm=2500)
        edited_state = drawings.sheet_state(single)
        check("view edit is one transaction and changes only the drawing revision",
              doc.UndoCount == before + 1 and edited_state["model_revision"] == MODEL_REVISION
              and edited_state["drawing_revision"] != first_state["drawing_revision"])
        check("raising the Plan cut above openings updates the actual cut geometry",
              drawings.capture_view(ground)["geometry"]["cut_faces"] != first_geometry["cut_faces"])
        undo()
        check("view Undo restores the exact definition revision and cut geometry",
              drawings.sheet_state(single) == first_state
              and drawings.capture_view(ground)["geometry"] == first_geometry and doc.RedoCount > 0)
        reject("invalid Plan range preserves the existing Redo branch",
               lambda: drawings.edit_view(ground, cut_offset_mm=-300))
        reject("sub-tolerance Plan range preserves the existing Redo branch",
               lambda: drawings.edit_view(ground, top_offset_mm=1200.00000001))
        reject("non-integer drawing scale is rejected before changing history",
               lambda: drawings.edit_view(ground, scale_denominator=50.5))
        reject("non-boolean annotation flag is rejected before changing history",
               lambda: drawings.edit_view(ground, show_tags=1))
        reject("Plan without a native Level is rejected before changing history",
               lambda: drawings.create_view(project, "Missing Level"))
        reject("unsupported vertical direction is rejected before changing history",
               lambda: drawings.create_view(project, "Diagonal", view_type="Section", direction="diagonal"))
        reject("deleting a placed view preserves the existing Redo branch", lambda: drawings.delete_view(ground))
        reject("deleting a referenced Plan Level preserves the existing Redo branch", lambda: services.delete_level(lower))
        reject("a caller-supplied snapshot cannot become the drawing master",
               lambda: drawings.capture_sheet(single, project_snapshot=single_capture))
        redo()
        check("the preserved native Redo still applies its valid drawing edit",
              drawings.sheet_state(single) == edited_state and ground.CutOffset.Value == 2500)
        undo()

        before = doc.UndoCount
        upper = drawings.create_view(project, "Upper Plan", level=upper_level,
                                     bottom_offset_mm=-150, cut_offset_mm=1200, top_offset_mm=2800)
        section = drawings.create_view(project, "Section A-A", view_type="Section",
                                       origin_mm=(0, 2000, 0), direction="+Y", depth_mm=3000)
        elevation = drawings.create_view(project, "South Elevation", view_type="Elevation",
                                         origin_mm=(0, -1000, 0), direction="+Y", depth_mm=6000)
        check("all three native view types author one transaction per command",
              doc.UndoCount == before + 3 and len(drawings.list_views(project)) == 4
              and section.Level is None and elevation.Level is None)
        plans = drawings.create_sheet(project, "Floor Plans", "A101", [ground, upper], issue="P01", author="3117 BIM")
        vertical = drawings.create_sheet(project, "Section and Elevation", "A201", [section, elevation], issue="P01", author="3117 BIM")
        reject("duplicate sheet number is rejected before opening a transaction",
               lambda: drawings.create_sheet(project, "Duplicate", "A101", [ground]))
        reject("duplicate view placement is rejected before opening a transaction",
               lambda: drawings.edit_sheet(plans, views=[ground, ground]))
        reject("three-view A3 sheet is rejected before opening a transaction",
               lambda: drawings.create_sheet(project, "Too many", "A301", [ground, section, elevation]))
        one_name, one_id = single.Name, single.BIM3117Id
        before = doc.UndoCount
        drawings.delete_sheet(single)
        check("sheet deletion is one transaction and preserves its model views",
              doc.UndoCount == before + 1 and doc.getObject(one_name) is None and len(drawings.list_views(project)) == 4)
        undo()
        check("sheet deletion Undo restores the original UUID and placed-view order",
              doc.getObject(one_name).BIM3117Id == one_id and doc.getObject(one_name).ViewIds == [ground_id])
        redo()
        unused = drawings.create_view(project, "Unused QA view", view_type="Elevation")
        unused_name, unused_id = unused.Name, unused.BIM3117Id
        before = doc.UndoCount
        drawings.delete_view(unused)
        check("unplaced view deletion is one native transaction",
              doc.UndoCount == before + 1 and doc.getObject(unused_name) is None)
        undo()
        check("view deletion Undo restores its persistent identity", doc.getObject(unused_name).BIM3117Id == unused_id)
        redo()

        final_sheets = (plans, vertical)
        states = {sheet.Number: drawings.sheet_state(sheet) for sheet in final_sheets}
        data = snapshot.capture(project)
        documented = [item for item in data["coverage"]["items"] if item["kind"] in DOCUMENTATION_KINDS]
        check("all seven drawing definitions are explicit coverage references with no quantity or IFC role",
              len(documented) == 7 and all(item["status"] == "reference" and item["quantity_role"] == "none"
                                         and not item["ifc_class"] for item in documented)
              and data["coverage"]["counts"]["unsupported"] == 0)
        check("drawing authoring preserves legacy quantity rows and exact model revision",
              data["content_revision"] == MODEL_REVISION
              and all(data[key] == baseline[key] for key in ("wall_rows", "door_rows", "window_rows", "slab_rows", "column_rows", "beam_rows")))
        before = doc.UndoCount
        drawings.edit_sheet(plans, issue="P02")
        check("sheet edit is one transaction and changes only its own drawing identity",
              doc.UndoCount == before + 1 and drawings.sheet_state(plans)["drawing_revision"] != states["A101"]["drawing_revision"]
              and drawings.sheet_state(plans)["model_revision"] == MODEL_REVISION
              and drawings.sheet_state(vertical) == states["A201"])
        undo()
        check("sheet edit Undo restores both independent revision identities", drawings.sheet_state(plans) == states["A101"])
        drawings.edit_view(ground, show_dimensions=False, show_tags=False, show_grid=False)
        flags = drawings.capture_view(ground)
        check("native annotation controls are carried into the derived view capture",
              not flags["show_dimensions"] and not flags["show_tags"] and not flags["show_grid"]
              and drawings.sheet_state(plans)["model_revision"] == MODEL_REVISION)
        undo()

        slab = next(obj for obj in services.list_slabs(project) if obj.Level == upper_level)
        vertical_before = drawings.capture_view(section)["geometry"]
        services.edit_slab(slab, thickness_mm=200)
        changed_model_state = drawings.sheet_state(vertical)
        check("model edit changes model identity while preserving drawing definition identity",
              changed_model_state["model_revision"] != MODEL_REVISION
              and changed_model_state["drawing_revision"] == states["A201"]["drawing_revision"])
        check("model edit changes the solid-derived section including joined members",
              drawings.capture_view(section)["geometry"] != vertical_before)
        undo()
        check("model Undo restores both revisions and exact section geometry",
              drawings.sheet_state(vertical) == states["A201"]
              and drawings.capture_view(section)["geometry"] == vertical_before)
        services.edit_level(upper_level, elevation_mm=3100)
        moved_plan = drawings.capture_view(upper)
        check("Plan effective cut plane follows its edited native Level without a drawing override",
              moved_plan["definition"]["level_elevation_mm"] == 3100
              and moved_plan["geometry"]["frame"]["origin_mm"][2] == 4300
              and drawings.sheet_state(plans)["drawing_revision"] == states["A101"]["drawing_revision"])
        undo()
        check("Level Undo restores the legacy model revision", snapshot.capture(project)["content_revision"] == MODEL_REVISION)

        # Direct native deletion is an independently requested host operation.
        # Missing identities must remain detectable and repairable through services.
        raw_delete(ground, "QA native delete placed view")
        check("native view deletion retains the missing expected UUID on the sheet",
              ground_id in plans.ViewIds and len(plans.Views) == 1 and bool(plans.ValidationMessage))
        reject("a broken placed-view link blocks only its drawing capture", lambda: drawings.capture_sheet(plans))
        check("a broken drawing link does not block the valid building snapshot",
              snapshot.capture(project)["content_revision"] == MODEL_REVISION)
        before = doc.UndoCount
        drawings.edit_sheet(plans, views=[upper])
        check("explicit sheet repair is one transaction and captures the selected surviving view",
              doc.UndoCount == before + 1 and plans.ViewIds == [upper.BIM3117Id]
              and len(drawings.capture_sheet(plans)["views"]) == 1)
        undo()
        reject("Undo of link repair restores the detectable broken reference", lambda: drawings.capture_sheet(plans))
        undo()
        ground = doc.getObject(ground_name)
        check("Undo of native view deletion restores original UUID links and drawing revision",
              ground.BIM3117Id == ground_id and plans.ViewIds == [ground_id, upper.BIM3117Id]
              and drawings.sheet_state(plans) == states["A101"])
        orphan_level = services.add_level(project, "QA drawing-only Level", 9000)
        orphan_plan = drawings.create_view(project, "QA Level reference", level=orphan_level)
        missing_level_id = orphan_level.BIM3117Id
        raw_delete(orphan_level, "QA native delete drawing-only Level")
        check("native Level deletion retains the broken Plan reference identity",
              orphan_plan.Level is None and orphan_plan.LevelId == missing_level_id)
        reject("a Plan with a missing Level cannot silently use project origin", lambda: drawings.capture_view(orphan_plan))
        before = doc.UndoCount
        drawings.edit_view(orphan_plan, level=lower)
        check("explicit Plan Level repair is one transaction and updates both native link and UUID",
              doc.UndoCount == before + 1 and orphan_plan.Level == lower
              and orphan_plan.LevelId == lower.BIM3117Id and drawings.capture_view(orphan_plan)["geometry"]["visible_paths"])
        drawings.delete_view(orphan_plan)
        check("repair and deletion tests leave the canonical building and drawing inventory unchanged",
              len(drawings.list_views(project)) == 4 and len(drawings.list_sheets(project)) == 2
              and snapshot.capture(project)["content_revision"] == MODEL_REVISION
              and all(drawings.sheet_state(sheet) == states[sheet.Number] for sheet in final_sheets))

        doc.openTransaction("QA unfinished drawing command")
        token = App.getActiveTransaction()
        try:
            reject("drawing capture rejects even an empty unfinished native transaction", lambda: drawings.capture_sheet(plans))
            reject("drawing authoring rejects an unfinished native transaction", lambda: drawings.edit_sheet(plans, issue="P03"))
        finally:
            doc.abortTransaction()
            if token is not None and App.getActiveTransaction() == token:
                App.closeActiveTransaction()
        captures, rendered, exports = {}, {}, {}
        native_before, history_before = observation(project), history(doc)
        for sheet in final_sheets:
            capture = drawings.capture_sheet(sheet)
            result = drawing_render.render_sheet(capture)
            root = ET.fromstring(result["svg"])
            metadata = json.loads(root.find(SVG_NS + "metadata").text)
            check(sheet.Number + " is a two-view vector A3 SVG with both native revisions",
                  len(capture["views"]) == 2 and root.get("width") == "420mm" and root.get("height") == "297mm"
                  and not list(root.iter(SVG_NS + "image"))
                  and metadata["model_revision"] == MODEL_REVISION
                  and metadata["drawing_revision"] == states[sheet.Number]["drawing_revision"])
            check(sheet.Number + " preserves the explicit 1:50 scale in both paper dimensions",
                  all(view["scale_denominator"] == 50
                      and abs((view["geometry_paper_bounds_mm"][2] - view["geometry_paper_bounds_mm"][0]) * 50
                              - (view["geometry_bounds_mm"][2] - view["geometry_bounds_mm"][0])) < 1e-6
                      and abs((view["geometry_paper_bounds_mm"][3] - view["geometry_paper_bounds_mm"][1]) * 50
                              - (view["geometry_bounds_mm"][3] - view["geometry_bounds_mm"][1])) < 1e-6
                      for view in result["layout"]["views"]))
            captures[sheet.Number], rendered[sheet.Number] = capture, result
            (output / (sheet.Number + "-capture.json")).write_text(json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            exports[sheet.Number] = drawing_export.export_sheet(sheet, output / (sheet.Number + ".svg"), format="svg", overwrite=True,
                                                               expected_model_revision=MODEL_REVISION,
                                                               expected_drawing_revision=states[sheet.Number]["drawing_revision"])
            exported = exports[sheet.Number]
            sidecar = json.loads(Path(exported["metadata_path"]).read_text(encoding="utf-8"))
            check(sheet.Number + " SVG publication metadata verifies payload hash and both source revisions",
                  sidecar["files"][0]["sha256"] == file_hash(exported["files"][0])
                  and sidecar["model_revision"] == MODEL_REVISION
                  and sidecar["drawing_revision"] == states[sheet.Number]["drawing_revision"])
        check("capture rendering and SVG publication preserve all native definitions BReps and history",
              observation(project) == native_before and history(doc) == history_before)
        check("Section has actual cut faces and Elevation has none",
              captures["A201"]["views"][0]["geometry"]["cut_faces"]
              and not captures["A201"]["views"][1]["geometry"]["cut_faces"])
        reject("existing SVG bundle is not overwritten without explicit permission",
               lambda: drawing_export.export_sheet(plans, output / "A101.svg", format="svg"))
        drawings.edit_sheet(plans, issue="P02")
        with tempfile.TemporaryDirectory(prefix="drawing-stale-", dir=output) as temporary:
            rejected_path = Path(temporary) / "Rejected.svg"
            reject("stale preview drawing revision blocks publication before files are staged",
                   lambda: drawing_export.export_sheet(plans, rejected_path, format="svg",
                                                        expected_model_revision=MODEL_REVISION,
                                                        expected_drawing_revision=states["A101"]["drawing_revision"]))
            check("stale preview rejection publishes no payload or sidecar", not list(Path(temporary).iterdir()))
        undo()
        check("stale-preview exercise restores the canonical P01 definition", drawings.sheet_state(plans) == states["A101"])

        views = drawings.list_views(project)
        check("all legacy authored and derived UUIDs survive drawing authoring",
              all(doc.getObject(name).BIM3117Id == identifier for name, identifier in initial_ids.items()))
        doc.saveAs(str(sample))
        check("final sample still has the exact frozen building model identity",
              snapshot.capture(project)["content_revision"] == MODEL_REVISION)
        check("all work leaves the frozen v0.3.0 source bytes unchanged", file_hash(source) == SOURCE_SHA256)
        report.update(status="passed", checks_passed=len(report["checks"]), sample=str(sample.resolve()),
                      sample_sha256=file_hash(sample), source=str(source), source_sha256=SOURCE_SHA256,
                      model_revision=MODEL_REVISION, element_ids={obj.Name: obj.BIM3117Id for obj in doc.Objects},
                      view_definitions={view.BIM3117Id: drawings._view_def(view) for view in views},
                      sheet_states={sheet.Number: drawings.sheet_state(sheet) for sheet in final_sheets},
                      geometry_hashes={view["id"]: value_hash(view["geometry"])
                                       for capture in captures.values() for view in capture["views"]},
                      svg_sha256={number: file_hash(result["files"][0]) for number, result in exports.items()},
                      exports=exports,
                      installed_modules={module.__name__: {"path": module.__file__, "sha256": file_hash(module.__file__)} for module in modules})
        return report
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "drawings-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
