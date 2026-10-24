# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproducible headless-to-GUI presentation of the native building fixture.

Call capture(source_path, output_dir), then fresh_reopen(output_dir) in a new
FreeCAD GUI process. The input FCStd is read-only. Only a separate presentation
copy is saved; screenshots are actual host pixels, without image modification.
"""

import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback
import zipfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from pivy import coin


ROW_KEYS = ("wall_rows", "door_rows", "slab_rows", "column_rows", "beam_rows", "window_rows")


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _report(scope):
    return {"status": "running", "freecad": App.Version(), "python": sys.version,
            "platform": platform.platform(), "qt": QtCore.qVersion(),
            "scope": scope, "checks": []}


def _check(report, name, condition):
    if not condition:
        raise AssertionError(name)
    report["checks"].append({"name": name, "status": "passed"})


def _settle(milliseconds=650):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    (getattr(loop, "exec", None) or loop.exec_)()


def _ids(doc):
    return {obj.Name: obj.BIM3117Id for obj in doc.Objects}


def _history(doc):
    return (doc.UndoCount, doc.RedoCount, len(doc.Objects))


def _node_count(node):
    children = getattr(node, "getNumChildren", None)
    return 1 + (sum(_node_count(node.getChild(index)) for index in range(children()))
                if callable(children) else 0)


def _rows_match(actual, expected):
    return all(actual[key] == expected[key] for key in ROW_KEYS)


def capture(source_path, output_dir):
    """Style a headless FCStd and capture its real GUI without changing design."""
    source = Path(source_path).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report = _report("Headless building fixture to a separate native GUI presentation copy")
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    source_hash = _hash(source)
    panel = None

    try:
        with zipfile.ZipFile(source) as archive:
            _check(report, "input fixture was saved by the headless host",
                   "GuiDocument.xml" not in archive.namelist())
        _check(report, "native and view classes are not manually preregistered",
               "bim3117_freecad.building" not in sys.modules and "ui3117.viewproviders" not in sys.modules)
        doc = App.openDocument(str(source))
        doc.recompute()
        from bim3117_freecad import services, snapshot
        from ui3117.exchange_dialog import panel_for_document

        project = services.get_project(doc)
        baseline = snapshot.capture(project)
        identifiers = _ids(doc)
        before = _history(doc)
        walls = services.list_walls(project)
        windows = services.list_windows(project)
        structure = services.list_slabs(project) + services.list_columns(project) + services.list_beams(project)
        _check(report, "headless input contains all six authored building categories",
               all(baseline[key] for key in ROW_KEYS))
        modes = {wall.Name: {"property_type": wall.ViewObject.getTypeIdOfProperty("DisplayMode"),
                            "values": wall.ViewObject.getEnumerationsOfProperty("DisplayMode")}
                 for wall in walls}
        for obj in doc.Objects:
            services._style(obj)
        _check(report, "headless native objects receive persistent view providers and valid solids",
               all(obj.ViewObject.Proxy.__class__.__name__ == obj.BIM3117Kind + "ViewProvider"
                   and obj.Shape.isValid()
                   and len(obj.Shape.Solids) == (4 if obj.BIM3117Kind == "Window" else 1)
                   and obj.ViewObject.Visibility for obj in structure + windows))
        _check(report, "scripted wall display mode initializes without replacing its native property type",
               all(wall.ViewObject.getTypeIdOfProperty("DisplayMode") == modes[wall.Name]["property_type"]
                   and wall.ViewObject.DisplayMode == "Default" and wall.ViewObject.isVisible()
                   and services.wall_body(wall).ViewObject.Visibility for wall in walls))
        _check(report, "headless walls claim each derived body and hosted opening only once",
               all(services.wall_body(wall) in wall.ViewObject.Proxy.claimChildren()
                   and all(opening in wall.ViewObject.Proxy.claimChildren()
                           and opening not in project.ViewObject.Proxy.claimChildren()
                           for opening in services.hosted_openings(wall)) for wall in walls))

        target = windows[0].Host
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, target.Name)
        Gui.runCommand("Std_ToggleVisibility")
        hidden = not target.ViewObject.isVisible() and not services.wall_body(target).ViewObject.Visibility
        hidden = hidden and all(not obj.ViewObject.Visibility for obj in services.hosted_openings(target))
        Gui.runCommand("Std_ToggleVisibility")
        _check(report, "native visibility toggles newly attached Wall Body Door and Window together",
               hidden and target.ViewObject.isVisible() and services.wall_body(target).ViewObject.Visibility
               and all(obj.ViewObject.Visibility for obj in services.hosted_openings(target)))
        before_nodes = _node_count(target.ViewObject.RootNode)
        target.ViewObject.Proxy.finishRestoring()
        target.ViewObject.Proxy.finishRestoring()
        _check(report, "repeated restore attachment does not duplicate native display nodes",
               before_nodes == _node_count(target.ViewObject.RootNode) and target.ViewObject.isVisible())
        Gui.activateWorkbench("BIM3117Workbench")
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        _check(report, "actual quantity command reads the canonical six categories and content revision",
               panel is not None and panel.source_snapshot["content_revision"] == baseline["content_revision"]
               and _rows_match(panel.source_snapshot, baseline)
               and all(table.rowCount() == len(baseline[key])
                       for table, key, _columns, _label in panel._quantity_tables))
        _check(report, "presentation attachment leaves native history identities and authored content unchanged",
               _history(doc) == before and _ids(doc) == identifiers
               and snapshot.capture(project)["content_revision"] == baseline["content_revision"])

        for obj in services.list_levels(project) + services.list_grids(project):
            obj.ViewObject.Visibility = False
        main = Gui.getMainWindow()
        main.showNormal()
        main.setGeometry(0, 0, 1440, 1000)
        Gui.Selection.clearSelection()
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        _settle()
        view.fitAll()
        _settle(350)
        copy_path = output / "canonical" / "Building_Authoring_Workbench.FCStd"
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        _check(report, "presentation destination is separate from the original fixture", copy_path.resolve() != source)
        doc.saveAs(str(copy_path))
        with zipfile.ZipFile(copy_path) as archive:
            _check(report, "separate native copy persists its GUI presentation", "GuiDocument.xml" in archive.namelist())

        # The saved copy keeps an ordinary fitted camera. This temporary layout
        # only moves the model above the actual modeless quantity window.
        camera = view.getCameraNode()
        camera.height.setValue(float(camera.height.getValue()) * 1.95)
        camera.position.setValue(camera.position.getValue() + camera.orientation.getValue().multVec(
            coin.SbVec3f(0, -float(camera.height.getValue()) * 0.21, 0)))
        panel.setGeometry(10, 585, 1420, 405)
        panel.tabs.setCurrentIndex(2)
        panel.raise_()
        Gui.updateGui()
        _settle(500)
        screenshot = output / "Building_Authoring_Fixture_GUI.png"
        table_image = output / "Building_Authoring_Fixture_Table.png"
        _check(report, "actual FreeCAD model and quantity screenshots are saved",
               QtWidgets.QApplication.primaryScreen().grabWindow(0).save(str(screenshot))
               and panel.grab().save(str(table_image)))
        _check(report, "source bytes and native content remain unchanged after the presentation save",
               _hash(source) == source_hash and _ids(doc) == identifiers
               and snapshot.capture(project)["content_revision"] == baseline["content_revision"]
               and _rows_match(snapshot.capture(project), baseline))
        report.update(status="passed", checks_passed=len(report["checks"]), source=str(source),
                      source_sha256=source_hash, gui_copy=str(copy_path), gui_copy_sha256=_hash(copy_path),
                      content_revision=baseline["content_revision"], identifiers=identifiers,
                      quantities={key: baseline[key] for key in ROW_KEYS}, totals=baseline["totals"],
                      counts={key: len(baseline[key]) for key in ROW_KEYS}, before_wall_modes=modes,
                      screenshot=str(screenshot), table_screenshot=str(table_image), module_source=services.__file__)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(report["checks"]), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        if panel is not None and not panel._closed:
            panel.close()
        for name in set(App.listDocuments()) - original_documents:
            App.closeDocument(name)
        if original_active:
            App.setActiveDocument(original_active)
        (output / "building-presentation-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def fresh_reopen(output_dir):
    """Verify automatic proxy restoration and native edit/Undo in a new GUI."""
    output = Path(output_dir)
    previous = json.loads((output / "building-presentation-report.json").read_text(encoding="utf-8"))
    report = _report("Fresh GUI restoration and edit/Undo of the separate canonical presentation copy")
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    panel = driver = None

    try:
        _check(report, "presentation capture passed and its native copy matches the recorded hash",
               previous["status"] == "passed" and _hash(previous["gui_copy"]) == previous["gui_copy_sha256"])
        _check(report, "fresh host has not preregistered native and view classes",
               "bim3117_freecad.building" not in sys.modules and "ui3117.viewproviders" not in sys.modules)
        doc = App.openDocument(previous["gui_copy"])
        doc.recompute()
        from bim3117_freecad import services, snapshot
        from ui3117.exchange_dialog import panel_for_document
        from freecad_building_gui import GuiDriver, near, wait_until
        driver = GuiDriver(report)
        project = services.get_project(doc)
        _check(report, "every native and view proxy restores from the installed workbench automatically",
               all(obj.Proxy.__class__.__module__.startswith("bim3117_freecad.")
                   and obj.ViewObject.Proxy.__class__.__module__ == "ui3117.viewproviders" for obj in doc.Objects))
        baseline = snapshot.capture(project)
        _check(report, "presentation save preserved every UUID revision quantity row and total",
               _ids(doc) == previous["identifiers"]
               and baseline["content_revision"] == previous["content_revision"]
               and _rows_match(baseline, previous["quantities"]) and baseline["totals"] == previous["totals"])
        walls = services.list_walls(project)
        windows = services.list_windows(project)
        members = services.list_columns(project) + services.list_beams(project)
        _check(report, "saved member joins and visible wall bodies and opening frames restore",
               all(obj.JoinSlabIds == [slab.BIM3117Id for slab in obj.JoinSlabs]
                   and obj.Shape.isValid() and len(obj.Shape.Solids) == 1 for obj in members)
               and all(wall.ViewObject.DisplayMode == "Default" and wall.ViewObject.isVisible()
                       and services.wall_body(wall).ViewObject.Visibility for wall in walls)
               and all(obj.Shape.isValid() and len(obj.Shape.Solids) == 4 and obj.ViewObject.Visibility
                       for obj in windows))
        window = windows[0]
        wall = window.Host
        window.ViewObject.Visibility = False
        wall.ViewObject.Proxy.finishRestoring()
        independent_hidden = not window.ViewObject.Visibility and wall.ViewObject.Visibility
        driver.select(wall)
        Gui.runCommand("Std_ToggleVisibility")
        subtree_hidden = all(not obj.ViewObject.Visibility for obj in services.hosted_openings(wall))
        Gui.runCommand("Std_ToggleVisibility")
        _check(report, "restored Window visibility remains independent until native host toggle",
               independent_hidden and subtree_hidden and window.ViewObject.Visibility
               and services.wall_body(wall).ViewObject.Visibility)
        Gui.activateWorkbench("BIM3117Workbench")
        before = _history(doc)
        Gui.runCommand("BIM3117_Quantities")
        panel = panel_for_document(doc.Name)
        _check(report, "fresh quantity command reproduces all rows without native history changes",
               panel is not None and _rows_match(panel.source_snapshot, previous["quantities"])
               and _history(doc) == before and not panel.latest_exports)
        column = services.list_columns(project)[0]
        original_width = column.Width.Value
        original_volume = column.Shape.Volume
        driver.select(column)
        driver.command("BIM3117_EditSelected", "ColumnDialog", {"widthInput": original_width + 40})
        changed_revision = snapshot.capture(project)["content_revision"]
        _check(report, "actual column edit after headless-to-GUI restore recomputes slab cuts and live quantities",
               wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == changed_revision)
               and changed_revision != previous["content_revision"] and column.Shape.Volume > original_volume
               and column.Shape.isValid() and len(column.Shape.Solids) == 1 and len(column.JoinSlabs) == 1)
        Gui.runCommand("Std_Undo")
        doc.recompute()
        _check(report, "native Undo restores the exact canonical revision UUIDs quantities and member solid",
               wait_until(lambda: not panel._dirty and panel.source_snapshot["content_revision"] == previous["content_revision"])
               and near(column.Width.Value, original_width) and near(column.Shape.Volume, original_volume)
               and _rows_match(panel.source_snapshot, previous["quantities"]) and _ids(doc) == previous["identifiers"])
        _check(report, "verification never rewrites either the headless original or styled copy",
               _hash(previous["source"]) == previous["source_sha256"]
               and _hash(previous["gui_copy"]) == previous["gui_copy_sha256"])
        report.update(status="passed", checks_passed=len(report["checks"]), gui_copy=previous["gui_copy"],
                      content_revision=previous["content_revision"], module_source=services.__file__)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(report["checks"]), error=str(error), traceback=traceback.format_exc())
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
        (output / "building-presentation-reopen-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
