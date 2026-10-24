# SPDX-License-Identifier: GPL-3.0-or-later
"""Open the building GUI sample in a fresh FreeCAD process before model imports."""

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
    previous = json.loads((output / "building-gui-report.json").read_text(encoding="utf-8"))
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "checks": checks}
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    doc = panel = driver = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    try:
        # FCStd restores native model/view proxy classes from the installed add-on.
        # Do not pre-register production classes through a source-tree import.
        doc = App.openDocument(previous["sample"])
        doc.recompute()
        from bim3117_freecad import services, snapshot
        from ui3117.exchange_dialog import panel_for_document
        from freecad_building_gui import GuiDriver, near, wait_until
        driver = GuiDriver(report)
        project = services.get_project(doc)
        check("fresh process restores every native UUID before quantity commands",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects} == previous["identifiers"])
        source = snapshot.capture(project)
        check("fresh process captures the identical authored content revision and six category counts",
              source["content_revision"] == previous["content_revision"]
              and all(len(source[key]) == count for key, count in previous["counts"].items()))
        members = services.list_slabs(project) + services.list_columns(project) + services.list_beams(project)
        windows = services.list_windows(project)
        check("new native objects restore valid solids and persistent view providers", all(
            obj.Shape.isValid() and len(obj.Shape.Solids) == (4 if obj.BIM3117Kind == "Window" else 1)
            and obj.ViewObject.Proxy.__class__.__name__ == obj.BIM3117Kind + "ViewProvider"
            for obj in members + windows))
        check("native slab join references persist with valid live cutters", all(
            len(obj.JoinSlabs) == 1 and obj.JoinSlabs[0].BIM3117Kind == "Slab"
            and len(obj.JoinSlabIds) == 1 for obj in services.list_columns(project) + services.list_beams(project)))
        window = doc.getObject(previous["hidden_window"])
        wall, body = window.Host, services.wall_body(window.Host)
        check("independently hidden Window remains hidden under its visible host after fresh restore",
              not window.ViewObject.Visibility and wall.ViewObject.Visibility and body.ViewObject.Visibility
              and window in wall.ViewObject.Proxy.claimChildren() and window not in project.ViewObject.Proxy.claimChildren())
        driver.select(wall)
        Gui.runCommand("Std_ToggleVisibility")
        hidden = not body.ViewObject.Visibility and all(not obj.ViewObject.Visibility for obj in services.list_windows(project) if obj.Host == wall)
        Gui.runCommand("Std_ToggleVisibility")
        check("freshly restored wall visibility toggles its hosted Window subtree", hidden
              and body.ViewObject.Visibility and window.ViewObject.Visibility)

        Gui.activateWorkbench("BIM3117Workbench")
        before = (doc.UndoCount, doc.RedoCount, len(doc.Objects))
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        check("fresh quantity command reads native data without creating history or restoring stale export sessions",
              panel is not None and not panel._dirty and not panel.latest_exports
              and panel.source_snapshot["content_revision"] == previous["content_revision"]
              and (doc.UndoCount, doc.RedoCount, len(doc.Objects)) == before)
        row = next(index for index in range(panel.window_table.rowCount())
                   if panel.window_table.item(index, 0).data(QtCore.Qt.UserRole) == window.BIM3117Id)
        panel.window_table.cellClicked.emit(row, 0)
        check("fresh Window quantity row selects the persistent native object", Gui.Selection.getSelection() == [window])
        middle = doc.getObject(previous["middle_level"])
        columns = services.list_columns(project)
        original_height = columns[0].Height.Value
        driver.select(middle)
        driver.command("BIM3117_EditSelected", "LevelDialog", {"elevationInput": 3300})
        check("GUI level edit after fresh restore recomputes member cuts and live tables",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] != previous["content_revision"])
              and near(columns[0].Height.Value, original_height + 300)
              and columns[0].Shape.isValid() and len(columns[0].Shape.Solids) == 1)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        check("fresh native Undo returns the saved content revision and original member geometry",
              wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == previous["content_revision"])
              and near(columns[0].Height.Value, original_height))
        Gui.runCommand("Std_Redo")
        doc.recompute()
        check("fresh native Redo restores the same linked level change", wait_until(lambda: not panel._dirty)
              and near(columns[0].Height.Value, original_height + 300))
        Gui.runCommand("Std_Undo")
        doc.recompute()
        wait_until(lambda: not panel._dirty)
        old_panel, name = panel, doc.Name
        App.closeDocument(name)
        doc = None
        check("closing restored model releases its quantity observer and panel", wait_until(lambda: old_panel._closed)
              and panel_for_document(name) is None)
        report.update(status="passed", checks_passed=len(checks), content_revision=previous["content_revision"],
                      sample=previous["sample"], module_source=services.__file__)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        if driver is not None:
            driver.close()
        if panel is not None and not panel._closed:
            panel.close()
        for name in set(App.listDocuments()) - original_documents:
            App.closeDocument(name)
        if original_active:
            App.setActiveDocument(original_active)
        (output / "building-gui-reopen-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
