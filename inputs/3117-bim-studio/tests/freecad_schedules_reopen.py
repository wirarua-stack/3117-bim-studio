# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh installed FreeCAD process restores schedules and edits their sources."""
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App


def main(output_dir):
    output = Path(output_dir)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Fresh installed-process schedule and catalogue restore, quantities, native source edit and CSV"}
    doc = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    try:
        previous = json.loads((output / "schedules-test-report.json").read_text(encoding="utf-8"))
        check("source lifecycle suite passed", previous["status"] == "passed")
        check("schedule proxy module is not preregistered in this fresh process", "bim3117_freecad.schedules" not in sys.modules)
        doc = App.openDocument(previous["sample"])
        doc.UndoMode = 1
        doc.recompute()
        from bim3117_freecad import catalog, schedules, services, snapshot
        from bim3117_freecad.model import kind
        from freecad_schedules import close, file_hash, history, observation
        check("lifecycle FCStd matches its recorded file hash", file_hash(previous["sample"]) == previous["sample_sha256"])
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        check("restored proxies load from the installed workbench",
              all(Path(module.__file__).resolve().is_relative_to(installed) for module in (catalog, schedules)))
        project = services.get_project(doc)
        check("all source and schedule UUIDs survive native restoration",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects} == previous["element_ids"])
        check("schedule set and definitions restore as native Python proxies",
              all(obj.Proxy.__class__.__module__ == "bim3117_freecad.schedules"
                  for obj in doc.Objects if kind(obj) in ("ScheduleSet", "Schedule")))
        native_schedules = schedules.list_schedules(project)
        check("persistent filters grouping and order restore exactly",
              {obj.BIM3117Id: schedules._definition(obj) for obj in native_schedules} == previous["definitions"])
        check("both model and schedule identities survive save and fresh reopen",
              {obj.BIM3117Id: schedules.schedule_state(obj) for obj in native_schedules} == previous["schedule_states"]
              and snapshot.capture(project)["content_revision"] == previous["model_revision"])
        before, prior = observation(project), history(doc)
        captured = {obj.BIM3117Id: schedules.capture_schedule(obj) for obj in native_schedules}
        check("fresh native capture reproduces every row source UUID and quantity",
              {identity: data["rows"] for identity, data in captured.items()} == previous["schedule_rows"]
              and {identity: data["totals"] for identity, data in captured.items()} == previous["schedule_totals"])
        check("fresh capture is read-only", observation(project) == before and history(doc) == prior)
        slabs = next(obj for obj in native_schedules if obj.Label == "Slabs")
        slab = next(obj for obj in project.Group if kind(obj) == "Slab" and obj.Label == "Slab A")
        state = schedules.schedule_state(slabs)
        doc.clearUndos()
        schedules.edit_row(slabs, slab.BIM3117Id, {"name": "Slab A restored edit", "offset_mm": 250},
                           expected_model_revision=state["model_revision"], expected_schedule_revision=state["schedule_revision"])
        check("restored row edits change the source label and solid in one transaction",
              doc.UndoCount == 1 and slab.Label == "Slab A restored edit" and close(slab.Shape.BoundBox.ZMax, 250))
        doc.undo()
        doc.recompute()
        check("restored Undo returns both saved content identities", schedules.schedule_state(slabs) == state and slab.Label == "Slab A")
        doc.redo()
        doc.recompute()
        check("restored Redo reproduces the edited solid", close(slab.Shape.BoundBox.ZMax, 250))
        doc.undo()
        doc.recompute()
        before, prior = observation(project), history(doc)
        result = schedules.export_schedule(slabs, output / "Slabs_Reopened.csv", overwrite=True,
                                           expected_model_revision=state["model_revision"], expected_schedule_revision=state["schedule_revision"])
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        check("restored publication records both revisions and the exact payload bytes",
              metadata["files"][0]["sha256"] == file_hash(result["files"][0])
              and metadata["model_revision"] == state["model_revision"]
              and metadata["schedule_revision"] == state["schedule_revision"])
        check("restored publication preserves its valid Redo branch", prior[1] > 0 and prior == history(doc) and before == observation(project))
        check("fresh-process edits never overwrite the saved lifecycle example", file_hash(previous["sample"]) == previous["sample_sha256"])
        report.update(status="passed", checks_passed=len(report["checks"]), sample=previous["sample"],
                      sample_sha256=previous["sample_sha256"], schedule_states=previous["schedule_states"],
                      installed_modules={module.__name__: {"path": module.__file__, "sha256": file_hash(module.__file__)}
                                         for module in (schedules, catalog, services, snapshot)})
        return report
    except BaseException as error:
        report.update(status="failed", checks_passed=len(report["checks"]), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "schedules-reopen-test-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if doc is not None:
            App.closeDocument(doc.Name)
