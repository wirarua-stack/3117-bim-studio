# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless native SVG scale, provenance and safe-publication checks.

PDF drawing and visual inspection run in the separate actual host GUI gate.
This stage does not create a QGuiApplication or install another Qt runtime.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

import FreeCAD as App

from bim3117_freecad import drawing_export, drawing_render, drawings, export_files, services, snapshot
from bim3117_freecad.model import FoundationError


def _hashes(paths):
    return {str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}


def _observation(project, sheet):
    doc = project.Document
    return {"model_revision": snapshot.capture(project)["content_revision"],
            "sheet_state": drawings.sheet_state(sheet),
            "history": [doc.UndoCount, doc.RedoCount, bool(doc.HasPendingTransaction),
                        App.getActiveTransaction()],
            "objects": [(obj.Name, obj.Label, getattr(obj, "BIM3117Id", ""),
                         hashlib.sha256(obj.Shape.exportBrepToString().encode()).hexdigest()
                         if "Shape" in obj.PropertiesList and not obj.Shape.isNull() else "")
                        for obj in doc.Objects]}


def main(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Each invocation keeps its own payloads. Reusing an evidence folder must
    # not collide with, delete or silently overwrite an earlier run's exports.
    case = Path(tempfile.mkdtemp(prefix="drawing-render-case-", dir=output))
    target = case / "drawing-render.svg"
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "case_directory": str(case), "artifact_paths": drawing_export.output_paths(target, format="svg"),
              "case_report_path": str(case / "drawing-render-test-report.json"),
              "scope": "Native SVG exact scale, associative annotations, read-only export, dual-revision freshness and caught-failure rollback"}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    def rejected(name, operation, error_type=FoundationError):
        try:
            operation()
        except error_type:
            check(name, True)
        else:
            raise AssertionError(name + ": operation was incorrectly accepted")

    def clean_publication_folder():
        return not list(case.glob("*.3117-export.lock")) and not list(case.glob(".3117-export-*"))

    try:
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("renderer and exporter load from the installed workbench",
              all(Path(module.__file__).resolve().is_relative_to(installed)
                  for module in (drawing_render, drawing_export)))
        check("SVG checks run without the FreeCAD GUI", not App.GuiUp)
        project = services.create_project("3117 ไทย & <native>", "DRAW-TEST", "3117 BIM")
        doc = project.Document
        lower, upper = services.list_levels(project)
        wall_type = services.create_wall_type(project, "W200", thickness_mm=200)
        wall = services.create_wall(project, "ผนัง & <W01>", wall_type, lower, upper,
                                    end_x_mm=6000, end_y_mm=0)
        services.create_window(project, "WIN01", wall, offset_mm=2000,
                               width_mm=1200, height_mm=1200, sill_mm=900)
        services.create_slab(project, "S00", lower,
                             [(-100, -100), (6100, -100), (6100, 4100), (-100, 4100)])
        plan = drawings.create_view(project, "แปลน & <A>", level=lower, scale_denominator=50)
        section = drawings.create_view(project, "รูปตัด A-A", view_type="Section",
                                        origin_mm=(0, 100, 0), direction="+Y", depth_mm=5000,
                                        scale_denominator=50)
        sheet = drawings.create_sheet(project, "แปลนและรูปตัด", "T101", [plan, section],
                                      issue="P01", author="3117 BIM")
        before = _observation(project, sheet)
        capture = drawings.capture_sheet(sheet)
        rendered = drawing_render.render_sheet(capture)
        root = ET.fromstring(rendered["svg"])
        check("SVG is a physical A3 landscape page",
              root.get("width") == "420mm" and root.get("height") == "297mm"
              and root.get("viewBox") == "0 0 420 297")
        check("Native Thai and XML-sensitive labels survive escaping",
              "3117 ไทย & <native>" in "".join(root.itertext())
              and "แปลน & <A>" in "".join(root.itertext()))
        for view, layout in zip(capture["views"], rendered["layout"]["views"]):
            bounds, paper = view["geometry"]["bounds_mm"], layout["geometry_paper_bounds_mm"]
            check(view["name"] + " preserves exact 1:50 geometry size in paper millimetres",
                  all(abs((paper[i + 2] - paper[i]) * 50 - (bounds[i + 2] - bounds[i])) < 1e-7
                      for i in (0, 1)))
            check(view["name"] + " dimensions reference projected bounds and native UUIDs",
                  [row["value_mm"] for row in layout["dimensions"]] == [bounds[2] - bounds[0], bounds[3] - bounds[1]]
                  and all(row["view_id"] == view["id"]
                          and set(row["source_ids"]) == {s["id"] for s in view["geometry"]["sources"]}
                          for row in layout["dimensions"]))
            check(view["name"] + " tags identify only native first-hit sources",
                  {row["source_id"] for row in layout["tags"]}
                  == {source["id"] for source in view["geometry"]["sources"] if source["taggable"]})
            bar = layout["scale_bar"]
            check(view["name"] + " scale bar measures the exact labelled model distance",
                  abs(bar["paper_length_mm"] * 50 - bar["model_length_mm"]) < 1e-7)
        check("Real window hole retains the evenodd section fill rule",
              any(path.get("fill-rule") == "evenodd" and path.get("d", "").count("M") >= 2
                  for path in root.iter("{" + drawing_export.SVG_NS + "}path")))
        geometry_svg, text_records = drawing_export._pdf_layers(rendered["svg"])
        check("PDF text uses the exact visible SVG labels without duplicate accessibility titles",
              not list(ET.fromstring(geometry_svg).iter("{" + drawing_export.SVG_NS + "}text"))
              and sum(row["text"] == "3117 ไทย & <native>" for row in text_records) == 1)
        too_large = deepcopy(capture)
        too_large["views"][0]["scale_denominator"] = 10
        rejected("Oversize requested scale is rejected rather than silently fitted",
                 lambda: drawing_render.render_sheet(too_large))
        crowded = {"name": "Annotation boundary fixture", "geometry": {"sources": [
            {"id": str(index), "name": "T" + str(index), "anchor_mm": [30, y], "taggable": True}
            for index, y in enumerate((52, 222, 222))]}}
        tag_rows = drawing_render._tags([], crowded, lambda point: point,
                                        [10, 52, 100, 170], [0, 28, 146, 220])
        check("Crowded lower tags stay inside the plot without pushing a top tag out",
              all(52 <= row["paper_text_mm"][1] - .7 <= 222 for row in tag_rows)
              and all(b["paper_text_mm"][1] - a["paper_text_mm"][1] >= 4.1 - 1e-8
                      for a, b in zip(tag_rows, tag_rows[1:])))
        check("Rendering and fit rejection leave native geometry and history unchanged",
              _observation(project, sheet) == before)

        result = drawing_export.export_sheet(sheet, target, format="svg",
                                              expected_model_revision=capture["model_revision"],
                                              expected_drawing_revision=capture["drawing_revision"])
        paths = result["files"]
        published = _hashes(paths)
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        check("Published metadata verifies the exact vector payload bytes",
              metadata["files"][0]["sha256"] == published[str(target)]
              and metadata["files"][0]["bytes"] == target.stat().st_size)
        check("Published metadata preserves both source revisions and complete annotations",
              metadata["model_revision"] == capture["model_revision"]
              and metadata["drawing_revision"] == capture["drawing_revision"]
              and metadata["layout"]["views"] == rendered["layout"]["views"])
        check("Successful SVG export preserves native identity, BRep and Undo/Redo history",
              _observation(project, sheet) == before)
        rejected("Existing payload and metadata require explicit overwrite",
                 lambda: drawing_export.export_sheet(sheet, target, format="svg"))
        check("Overwrite rejection preserves the complete prior bundle", _hashes(paths) == published)

        services.edit_level(upper, elevation_mm=3300)
        updated = drawings.capture_sheet(sheet)
        check("Level edit refreshes the associative section height by 300 mm",
              updated["model_revision"] != capture["model_revision"]
              and drawing_render.render_sheet(updated)["layout"]["views"][1]["dimensions"][1]["value_mm"]
              == rendered["layout"]["views"][1]["dimensions"][1]["value_mm"] + 300)
        rejected("Stale model revision is rejected before export staging",
                 lambda: drawing_export.export_sheet(sheet, target, format="svg", overwrite=True,
                                                       expected_model_revision=capture["model_revision"]))
        doc.undo()
        doc.recompute()
        drawings.edit_sheet(sheet, issue="P02")
        rejected("Stale drawing revision is rejected before export staging",
                 lambda: drawing_export.export_sheet(sheet, target, format="svg", overwrite=True,
                                                       expected_drawing_revision=capture["drawing_revision"]))
        doc.undo()
        doc.recompute()
        check("Both stale-preview paths preserve the prior bundle", _hashes(paths) == published)

        original_publish = drawing_export.publish_bundle
        for label, mutation in (("model", lambda: services.edit_level(upper, elevation_mm=3400)),
                                ("drawing", lambda: drawings.edit_sheet(sheet, issue="P03"))):
            def publish_with_intervening_edit(destinations, writer, overwrite=False, before_commit=None):
                def staged_writer(staged):
                    writer(staged)
                    mutation()
                return original_publish(destinations, staged_writer, overwrite=overwrite,
                                        before_commit=before_commit)
            drawing_export.publish_bundle = publish_with_intervening_edit
            try:
                rejected("A " + label + " edit after staging rejects publication at the commit boundary",
                         lambda: drawing_export.export_sheet(sheet, target, format="svg", overwrite=True))
            finally:
                drawing_export.publish_bundle = original_publish
            check("Interrupted " + label + " export keeps old payload/metadata and cleans locks",
                  _hashes(paths) == published and clean_publication_folder())
            doc.undo()
            doc.recompute()

        original_replace = export_files.os.replace
        metadata_path = Path(result["metadata_path"])
        def fail_metadata_replace(source, destination):
            if (Path(destination) == metadata_path and Path(source).name == metadata_path.name
                    and Path(source).parent.name.startswith(".3117-export-")):
                raise OSError("Injected final metadata publication failure")
            return original_replace(source, destination)
        export_files.os.replace = fail_metadata_replace
        try:
            rejected("Caught failure on final metadata replacement aborts the bundle",
                     lambda: drawing_export.export_sheet(sheet, target, format="svg", overwrite=True), OSError)
        finally:
            export_files.os.replace = original_replace
        check("Caught publication failure rolls back the already replaced payload",
              _hashes(paths) == published and clean_publication_folder())
        check("Failure probes leave native content at its original revisions",
              drawings.sheet_state(sheet) == before["sheet_state"]
              and not doc.HasPendingTransaction and App.getActiveTransaction() is None)
        report.update(status="passed", checks_passed=len(report["checks"]),
                      renderer=drawing_render.__file__, exporter=drawing_export.__file__,
                      model_revision=capture["model_revision"], drawing_revision=capture["drawing_revision"])
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(),
                      checks_passed=len(report["checks"]))
        raise
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        (case / "drawing-render-test-report.json").write_text(serialized, encoding="utf-8")
        (output / "drawing-render-test-report.json").write_text(serialized, encoding="utf-8")
    return report
