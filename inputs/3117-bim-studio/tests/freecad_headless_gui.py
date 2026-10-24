# SPDX-License-Identifier: GPL-3.0-or-later
"""Attach GUI providers to a headless-saved native model without changing it.

The native fixture is read-only input. Presentation is saved to a separate GUI
copy; its authored content revision and identities must remain identical.
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


def run(source_path, output_dir):
    source = Path(source_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "qt": QtCore.qVersion(), "checks": checks,
              "scope": "Headless-created FCStd receives GUI providers; source file is never overwritten"}
    doc, panel = None, None
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append({"name": name, "status": "passed"})

    def node_count(node):
        children = getattr(node, "getNumChildren", None)
        return 1 + (sum(node_count(node.getChild(index)) for index in range(children()))
                    if callable(children) else 0)

    def settle_view():
        # Standard view commands animate on this host. Read the completed
        # orientation rather than the previous frame when composing a view.
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(650, loop.quit)
        (getattr(loop, "exec", None) or loop.exec_)()

    try:
        with zipfile.ZipFile(source) as archive:
            check("source fixture was saved without a GUI document", "GuiDocument.xml" not in archive.namelist())
        doc = App.openDocument(str(source))
        doc.recompute()
        from bim3117_freecad import services, snapshot
        from ui3117.exchange_dialog import show_quantities
        project = services.get_project(doc)
        baseline = snapshot.capture(project)
        ids = {obj.Name: obj.BIM3117Id for obj in doc.Objects}
        before_history = (doc.UndoCount, doc.RedoCount, len(doc.Objects))
        walls = services.list_walls(project)
        before_modes = {wall.Name: {
            "property_type": wall.ViewObject.getTypeIdOfProperty("DisplayMode"),
            "enumeration": wall.ViewObject.getEnumerationsOfProperty("DisplayMode"),
        } for wall in walls}
        check("headless wall enumeration is initially missing its scripted Default mode",
              all("Default" not in value["enumeration"] for value in before_modes.values()))
        for obj in doc.Objects:
            services._style(obj)
        check("native DisplayMode property type is preserved while missing values initialize",
              all(wall.ViewObject.getTypeIdOfProperty("DisplayMode") == before_modes[wall.Name]["property_type"]
                  and wall.ViewObject.DisplayMode == "Default"
                  and "Default" in wall.ViewObject.getEnumerationsOfProperty("DisplayMode") for wall in walls))
        check("styled headless walls and children are actually visible",
              all(wall.ViewObject.Visibility and wall.ViewObject.isVisible()
                  and services.wall_body(wall).ViewObject.Visibility for wall in walls)
              and all(door.ViewObject.Visibility for door in services.list_doors(project)))
        check("styled headless wall presentation claims its derived body and doors",
              all(services.wall_body(wall) in wall.ViewObject.Proxy.claimChildren()
                  and all(door in wall.ViewObject.Proxy.claimChildren()
                          for door in services.list_doors(project) if door.Host == wall) for wall in walls))
        target = walls[0]
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, target.Name)
        Gui.runCommand("Std_ToggleVisibility")
        check("first native visibility toggle hides newly attached wall and children",
              not target.ViewObject.Visibility and not target.ViewObject.isVisible()
              and not services.wall_body(target).ViewObject.Visibility
              and all(not door.ViewObject.Visibility for door in services.list_doors(project) if door.Host == target))
        Gui.runCommand("Std_ToggleVisibility")
        check("second native visibility toggle shows newly attached wall and children",
              target.ViewObject.Visibility and target.ViewObject.isVisible()
              and services.wall_body(target).ViewObject.Visibility
              and all(door.ViewObject.Visibility for door in services.list_doors(project) if door.Host == target))
        before_nodes = node_count(target.ViewObject.RootNode)
        target.ViewObject.Proxy.finishRestoring()
        target.ViewObject.Proxy.finishRestoring()
        check("repeated attach after headless restore does not duplicate Coin nodes",
              node_count(target.ViewObject.RootNode) == before_nodes and target.ViewObject.isVisible())
        Gui.activateWorkbench("BIM3117Workbench")
        panel = show_quantities(project)
        check("headless model quantity table preserves authored revision and rows",
              panel.source_snapshot["content_revision"] == baseline["content_revision"]
              and panel.wall_table.rowCount() == len(baseline["wall_rows"])
              and panel.door_table.rowCount() == len(baseline["door_rows"]))
        check("presentation attachment leaves identities and native history unchanged",
              ids == {obj.Name: obj.BIM3117Id for obj in doc.Objects}
              and before_history == (doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        for obj in services.list_levels(project) + services.list_grids(project):
            obj.ViewObject.Visibility = False
        copy_path = output / "native-example" / "Quantity_Exchange_Workbench.FCStd"
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        doc.saveAs(str(copy_path))
        panel.close()
        panel = None
        App.closeDocument(doc.Name)
        doc = App.openDocument(str(copy_path))
        doc.recompute()
        project = services.get_project(doc)
        check("separate GUI copy restores scripted wall modes automatically",
              all(wall.ViewObject.Proxy.__class__.__name__ == "WallViewProvider"
                  and wall.ViewObject.DisplayMode == "Default" and wall.ViewObject.isVisible()
                  for wall in services.list_walls(project)))
        panel = show_quantities(project)
        check("GUI copy reopens with the original model revision and identities",
              panel.source_snapshot["content_revision"] == baseline["content_revision"]
              and ids == {obj.Name: obj.BIM3117Id for obj in doc.Objects})

        main = Gui.getMainWindow()
        main.showNormal()
        main.setGeometry(0, 0, 1440, 1000)
        for tree in main.findChildren(QtWidgets.QTreeWidget):
            tree.expandAll()
        Gui.Selection.clearSelection()
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        settle_view()
        view.setCameraOrientation(App.Rotation(App.Vector(0, 0, 1), 180).multiply(view.getCameraOrientation()).Q)
        settle_view()
        view.fitAll()
        # Persist a normal fitted camera in the separate deliverable. The
        # temporary upward layout below only makes room for the screenshot.
        doc.save()
        camera = view.getCameraNode()
        camera.height.setValue(float(camera.height.getValue()) * 1.8)
        camera.position.setValue(camera.position.getValue() + camera.orientation.getValue().multVec(
            coin.SbVec3f(0, -float(camera.height.getValue()) * 0.20, 0)))
        panel.setGeometry(10, 590, 1420, 400)
        panel.tabs.setCurrentIndex(0)
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(500, loop.quit)
        (getattr(loop, "exec", None) or loop.exec_)()
        screenshot = output / "Quantity_Exchange_Fixture_GUI.png"
        table_image = output / "Quantity_Exchange_Fixture_Table.png"
        check("actual verified fixture GUI and table screenshots saved",
              QtWidgets.QApplication.primaryScreen().grabWindow(0).save(str(screenshot))
              and panel.grab().save(str(table_image)))
        check("headless source FCStd remains byte-for-byte unchanged",
              hashlib.sha256(source.read_bytes()).hexdigest() == source_hash)
        report.update(status="passed", checks_passed=len(checks), source=str(source), source_sha256=source_hash,
                      gui_copy=str(copy_path), content_revision=baseline["content_revision"],
                      gui_copy_sha256=hashlib.sha256(copy_path.read_bytes()).hexdigest(),
                      screenshot=str(screenshot), table_screenshot=str(table_image), wall_rows=baseline["wall_rows"],
                      before_wall_modes=before_modes, identifiers=ids)
    except BaseException as error:
        report.update(status="failed", checks_passed=len(checks), error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        (output / "headless-gui-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if panel is not None and not panel._closed:
            panel.close()
        if doc is not None:
            App.closeDocument(doc.Name)
    return report
