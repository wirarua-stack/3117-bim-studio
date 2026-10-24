# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh installed-host restore and publication of the drawing lifecycle sample.

No drawing proxy is imported before App.openDocument: FCStd restore must find
the installed module by itself. This suite never saves over the source sample.
"""
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Fresh-process installed drawing proxy restore, content identities, native edit/Undo/Redo and SVG publication"}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    try:
        previous = json.loads((output / "drawings-test-report.json").read_text(encoding="utf-8"))
        check("source drawing lifecycle suite passed", previous["status"] == "passed")
        sample = Path(previous["sample"])
        check("source FCStd matches its recorded file hash", _file_hash(sample) == previous["sample_sha256"])
        check("drawing proxies are not preregistered in this fresh process", "bim3117_freecad.drawings" not in sys.modules)
        doc = App.openDocument(str(sample))
        doc.UndoMode = 1
        doc.recompute()
        from bim3117_freecad import drawing_export, drawing_geometry, drawing_render, drawings, services, snapshot
        from bim3117_freecad.model import DOCUMENTATION_KINDS, kind
        from freecad_drawings import MODEL_REVISION, SOURCE_SHA256, history, observation, value_hash
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        modules = (drawings, drawing_geometry, drawing_render, drawing_export, services, snapshot)
        check("restored drawing and model modules load from the installed add-on",
              all(Path(module.__file__).resolve().is_relative_to(installed) for module in modules))
        check("all native drawing proxies restore without placeholders",
              all(getattr(obj, "Proxy", None) is not None and not isinstance(obj.Proxy, str)
                  and obj.Proxy.__class__.__module__ == "bim3117_freecad.drawings"
                  for obj in doc.Objects if kind(obj) in DOCUMENTATION_KINDS))
        check("all authored derived and drawing UUIDs survive fresh restore",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects} == previous["element_ids"])
        project = services.get_project(doc)
        views, sheets = drawings.list_views(project), drawings.list_sheets(project)
        check("four views and two sheets restore in their separate native drawing set",
              len(views) == 4 and len(sheets) == 2 and len(drawings.get_drawing_set(project).Group) == 6
              and all(obj not in project.Group for obj in views + sheets))
        check("view parameters and annotation flags survive fresh restore exactly",
              {view.BIM3117Id: drawings._view_def(view) for view in views} == previous["view_definitions"])
        check("Plan Levels restore with matching persistent reference identities",
              all(view.Level is not None and view.LevelId == view.Level.BIM3117Id
                  and view.Level.Project == project for view in views if str(view.ViewType) == "Plan")
              and all(view.Level is None and not view.LevelId for view in views if str(view.ViewType) != "Plan"))
        check("sheet view order and expected UUIDs restore together",
              all([view.BIM3117Id for view in sheet.Views] == list(sheet.ViewIds) for sheet in sheets))
        data = snapshot.capture(project)
        check("fresh-process recompute preserves the exact v0.3.0 model revision",
              data["content_revision"] == MODEL_REVISION == previous["model_revision"])
        check("all seven documentation objects remain explicit coverage references",
              sum(item["kind"] in DOCUMENTATION_KINDS and item["status"] == "reference"
                  for item in data["coverage"]["items"]) == 7
              and data["coverage"]["counts"]["unsupported"] == 0)
        check("both sheet identities survive fresh-process restoration",
              {sheet.Number: drawings.sheet_state(sheet) for sheet in sheets} == previous["sheet_states"])
        before, prior_history = observation(project), history(doc)
        geometry_hashes = {}
        for sheet in sheets:
            captured = drawings.capture_sheet(sheet)
            geometry_hashes.update({view["id"]: value_hash(view["geometry"]) for view in captured["views"]})
        check("all four cut and HLR results are deterministic across native save and reopen",
              geometry_hashes == previous["geometry_hashes"])
        check("fresh capture changes no native definition BRep object count or history",
              observation(project) == before and history(doc) == prior_history)

        plan = next(view for view in views if view.Label == "Ground Plan")
        plans = next(sheet for sheet in sheets if sheet.Number == "A101")
        old_state = drawings.sheet_state(plans)
        doc.clearUndos()
        drawings.edit_view(plan, cut_offset_mm=2500)
        edited_state = drawings.sheet_state(plans)
        check("restored view can be edited in one native transaction with stable UUID",
              doc.UndoCount == 1 and plan.BIM3117Id in previous["view_definitions"]
              and edited_state["model_revision"] == MODEL_REVISION
              and edited_state["drawing_revision"] != old_state["drawing_revision"])
        doc.undo()
        doc.recompute()
        check("Undo after fresh restore returns the exact saved drawing state", drawings.sheet_state(plans) == old_state)
        doc.redo()
        doc.recompute()
        check("Redo after fresh restore returns the edited drawing state", drawings.sheet_state(plans) == edited_state)
        doc.undo()
        doc.recompute()
        upper = next(view for view in views if view.Label == "Upper Plan")
        services.edit_level(upper.Level, elevation_mm=3100)
        moved = drawings.capture_view(upper)
        check("restored Plan remains associated with native Level elevation edits",
              moved["geometry"]["frame"]["origin_mm"][2] == 4300
              and drawings.sheet_state(plans)["drawing_revision"] == old_state["drawing_revision"]
              and drawings.sheet_state(plans)["model_revision"] != MODEL_REVISION)
        doc.undo()
        doc.recompute()
        check("Level Undo after restore returns both saved content identities", drawings.sheet_state(plans) == old_state)

        before, prior_history = observation(project), history(doc)
        exported = drawing_export.export_sheet(plans, output / "A101_Reopened.svg", format="svg", overwrite=True,
                                               expected_model_revision=old_state["model_revision"],
                                               expected_drawing_revision=old_state["drawing_revision"])
        check("fresh SVG publication preserves the exact pre-save vector payload",
              _file_hash(exported["files"][0]) == previous["svg_sha256"]["A101"])
        metadata = json.loads(Path(exported["metadata_path"]).read_text(encoding="utf-8"))
        check("fresh SVG sidecar validates native identities and the actual published bytes",
              metadata["files"][0]["sha256"] == _file_hash(exported["files"][0])
              and metadata["model_revision"] == old_state["model_revision"]
              and metadata["drawing_revision"] == old_state["drawing_revision"]
              and exported["validation"]["svg"]["status"] == "passed")
        check("fresh publication preserves the valid native Redo branch and all source objects",
              prior_history[1] > 0 and history(doc) == prior_history and observation(project) == before)
        check("restore edit Undo and export never overwrite the source sample",
              _file_hash(sample) == previous["sample_sha256"])
        check("frozen v0.3.0 input remains unchanged after both installed-host stages",
              _file_hash(previous["source"]) == SOURCE_SHA256)
        report.update(status="passed", checks_passed=len(report["checks"]), sample=str(sample),
                      sample_sha256=previous["sample_sha256"], model_revision=MODEL_REVISION,
                      sheet_states=previous["sheet_states"], geometry_hashes=geometry_hashes, svg_result=exported,
                      installed_modules={module.__name__: {"path": module.__file__, "sha256": _file_hash(module.__file__)} for module in modules})
        return report
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc(), checks_passed=len(report["checks"]))
        raise
    finally:
        (output / "drawings-reopen-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
