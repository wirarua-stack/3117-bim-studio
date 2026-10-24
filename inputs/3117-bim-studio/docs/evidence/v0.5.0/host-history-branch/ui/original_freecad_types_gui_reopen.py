# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh FreeCAD GUI process restores type, material and schedule providers."""

import json
from pathlib import Path
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from freecad_types_gui import (TypesGuiDriver, exercise_panel_coexistence, file_hash,
                               installed_ui_fingerprint, near, wait_until)


def main(output_dir):
    output = Path(output_dir)
    previous = json.loads((output / "types-gui-report.json").read_text(encoding="utf-8"))
    sample = Path(previous["sample"])
    saved_hash = file_hash(sample)
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "qt": QtCore.qVersion(), "gui_up": bool(App.GuiUp), "checks": []}
    driver = TypesGuiDriver(report)
    doc = panel = catalogue = quantities = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    def undo():
        Gui.runCommand("Std_Undo")
        doc.recompute()
        Gui.updateGui()

    try:
        # Restoration precedes production-module imports; no workbench sys.path injection.
        doc = App.openDocument(str(sample))
        doc.recompute()
        from bim3117_freecad import catalog, schedules, services, snapshot
        from ui3117 import viewproviders
        from ui3117.catalog_panel import panel_for_document as catalogue_for_document
        from ui3117.schedule_panel import panel_for_document as schedule_for_document
        project = services.get_project(doc)
        check("fresh process restores proxies from installed addon", "/Mod/BIM3117/" in catalog.__file__.replace("\\", "/"))
        check("fresh process preserves all native stable identities", previous["identifiers"] == {
            obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")})
        check("fresh process preserves model content revision", snapshot.capture(project)["content_revision"] == previous["model_revision"])
        check("fresh process preserves both schedule revisions", previous["schedule_states"] == {
            obj.Label: schedules.schedule_state(obj) for obj in schedules.list_schedules(project)})
        check("material GUI providers restore", all(isinstance(obj.ViewObject.Proxy, viewproviders.MaterialViewProvider)
              for obj in catalog.list_materials(project)))
        check("element type GUI providers restore", all(isinstance(obj.ViewObject.Proxy, viewproviders.ElementTypeViewProvider)
              for obj in catalog.list_types(project) if obj.BIM3117Kind == "ElementType"))
        group = schedules.get_schedule_set(project)
        check("schedule group tree and providers restore", isinstance(group.ViewObject.Proxy, viewproviders.ScheduleSetViewProvider)
              and set(group.ViewObject.Proxy.claimChildren()) == set(group.Group)
              and all(isinstance(obj.ViewObject.Proxy, viewproviders.ScheduleViewProvider) for obj in schedules.list_schedules(project)))
        slab_type = next(obj for obj in catalog.list_types(project, "Slab") if obj.Label == "Slab Composite 200")
        check("ordered layers restore native material references", [obj.Label for obj in slab_type.LayerMaterials] == ["Concrete", "Finish"]
              and list(slab_type.LayerThicknesses) == [160, 40])
        Gui.activateWorkbench("BIM3117Workbench")
        doc.UndoMode = 1
        history = doc.UndoCount, doc.RedoCount, len(doc.Objects)
        driver.command("BIM3117_Catalogue")
        catalogue = catalogue_for_document(doc.Name)
        schedule = next(obj for obj in schedules.list_schedules(project) if obj.Label == "Column Schedule")
        driver.select(schedule)
        driver.command("BIM3117_Schedules")
        panel = schedule_for_document(doc.Name)
        check("restored catalogue and schedule panels read current native state", catalogue and panel and not catalogue.last_error
              and not panel.last_error and not panel._dirty and panel.schedule_id == str(schedule.BIM3117Id))
        check("opening restored panels creates no model transaction or caches", history == (doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        check("fresh panel invents no remembered export status", panel.latest_export is None)
        concrete = next(obj for obj in catalog.list_materials(project) if obj.Label == "Concrete")
        catalogue.tabs.setCurrentIndex(1)
        catalogue.refresh()
        catalogue.materials_table.selectRow(catalogue._materials.index(concrete))
        before = doc.UndoCount
        driver.action(catalogue.duplicateMaterialButton.click, "DuplicateMaterialDialog", {"nameEdit": "Concrete Copy"})
        copied = next(obj for obj in catalog.list_materials(project) if obj.Label == "Concrete Copy")
        check("material duplicate GUI creates a new identity with empty code in one Undo", copied.BIM3117Id != concrete.BIM3117Id
              and not copied.Code and doc.UndoCount == before + 1)
        catalogue.refresh()
        catalogue.materials_table.selectRow(catalogue._materials.index(copied))
        catalogue.deleteMaterialButton.click()
        check("deleting a selected unused material refreshes the catalogue safely", not catalogue.last_error
              and not any(obj.Label == "Concrete Copy" for obj in catalog.list_materials(project)))
        undo()
        undo()
        catalogue.refresh()
        panel.refresh()
        check("Undo of material duplication restores the prior native material catalogue", len(catalog.list_materials(project)) == 3
              and not catalogue.last_error and snapshot.capture(project)["content_revision"] == previous["model_revision"])
        column_type = next(obj for obj in catalog.list_types(project, "Column") if obj.Label == "Column Shared")
        column = next(obj for obj in services.list_columns(project) if obj.ElementType == column_type)
        width = column_type.Width.Value
        baseline = schedules.schedule_state(schedule)
        driver.select(column_type)
        driver.command("BIM3117_EditSelected", "ElementTypeDialog", {"widthInput": width + 20})
        check("restored shared type is editable through native GUI command", near(column.Width.Value, width + 20)
              and wait_until(lambda: not panel._dirty and panel.source_snapshot["model_revision"] != baseline["model_revision"], seconds=30))
        undo()
        check("restored type Undo refreshes schedule to the same content hash", near(column.Width.Value, width)
              and wait_until(lambda: not panel._dirty and schedules.schedule_state(schedule) == baseline, seconds=30))
        driver.select(schedule)
        before_model = snapshot.capture(project)["content_revision"]
        driver.command("BIM3117_EditSelected", "ScheduleDefinitionDialog", {"scheduleNameFilterEdit": "Row Edited"})
        panel.refresh()
        check("restored schedule definition remains editable without changing model hash", schedule.NameFilter == "Row Edited"
              and len(panel.source_snapshot["rows"]) == 1 and snapshot.capture(project)["content_revision"] == before_model)
        driver.action(panel.editScheduleButton.click, "ScheduleDefinitionDialog", {"nameEdit": "Stale definition"},
                      setup=lambda _dialog: undo(), expected_error=True)
        panel.refresh()
        check("staged definition refuses a source changed while its form is open", schedule.Label == "Column Schedule"
              and not schedule.NameFilter and doc.RedoCount > 0)
        check("native Undo restores persisted schedule filters", not schedule.NameFilter and schedules.schedule_state(schedule) == baseline)
        check("native property mode remains read-only for typed dimensions", "ReadOnly" in column.getEditorMode("Width")
              and "ReadOnly" in column.getEditorMode("Depth"))
        active_name = doc.Name
        guard_doc = None
        try:
            driver.command("BIM3117_CreateProject", "ProjectDialog", {
                "nameEdit": "Schedule-only deletion guard", "initialLevelsCheck": False})
            guard_doc = App.ActiveDocument
            guard_project = services.get_project(guard_doc)
            driver.command("BIM3117_CreateSchedule", "ScheduleDefinitionDialog", {"nameEdit": "Empty Schedule"})
            check("schedules-only project has no building children", not guard_project.Group)
            warning = driver.native_delete(guard_project)
            check("native Delete protects a project with a separate ScheduleSet", bool(warning)
                  and schedules.get_schedule_set(guard_project) is not None)
            driver.select(schedules.list_schedules(guard_project)[0])
            driver.command("BIM3117_DeleteSelected")
            empty_group = schedules.get_schedule_set(guard_project)
            empty_name = empty_group.Name
            driver.native_delete(empty_group)
            check("native Delete can remove an empty ScheduleSet", guard_doc.getObject(empty_name) is None)
        finally:
            if guard_doc is not None and guard_doc.Name in App.listDocuments():
                App.closeDocument(guard_doc.Name)
            App.setActiveDocument(active_name)
        exercise_panel_coexistence(driver, project, panel, check, report)
        check("fresh-host interaction leaves saved FCStd bytes unchanged", file_hash(sample) == saved_hash)
        name = doc.Name
        App.closeDocument(name)
        doc = None
        check("document close detaches both restored panel observers", wait_until(lambda: schedule_for_document(name) is None
              and catalogue_for_document(name) is None))
        panel = catalogue = None
        report.update(status="passed", sample=str(sample), sample_sha256=saved_hash, module_source=catalog.__file__)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        driver.close()
        report["checks_passed"] = len(report["checks"])
        report["installed_ui"] = installed_ui_fingerprint()
        (output / "types-gui-reopen-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for window in (panel, catalogue, quantities):
            if window is not None and not window._closed:
                window.close()
        if doc is not None and doc.Name in App.listDocuments():
            App.closeDocument(doc.Name)
    return report
