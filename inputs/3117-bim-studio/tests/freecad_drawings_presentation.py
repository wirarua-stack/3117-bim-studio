# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only actual FreeCAD views of the independently built drawing fixture.

No native file is saved. Presentation pixels are captured by the host Qt, and
the report proves the input bytes, UUIDs, two revisions and history are stable.
"""

import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _settle(milliseconds=400):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    (getattr(loop, "exec", None) or loop.exec_)()


def _file_hashes(root):
    return {path.relative_to(root).as_posix(): _sha(path)
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}


def capture(source_path, output_dir, screenshot_dir=None):
    source = Path(source_path).resolve()
    output = Path(output_dir)
    screenshots = Path(screenshot_dir) if screenshot_dir else output
    output.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(parents=True, exist_ok=True)
    source_before = _sha(source)
    original_documents = set(App.listDocuments())
    original_active = App.ActiveDocument.Name if App.ActiveDocument else None
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "qt": QtCore.qVersion(), "platform": platform.platform(), "checks": [],
              "source": str(source), "source_sha256_before": source_before,
              "scope": "Actual canonical native model/tree and sheet preview pixels; no FCStd write"}
    panel = None

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append({"name": name, "status": "passed"})

    try:
        check("drawing proxies are restored before explicit production import", "bim3117_freecad.drawings" not in sys.modules)
        doc = App.openDocument(str(source))
        doc.recompute()
        from bim3117_freecad import drawings, services, snapshot
        from bim3117_freecad.model import DOCUMENTATION_KINDS, kind
        from ui3117.drawing_preview import panel_for_document
        installed = Path(drawings.__file__).resolve().parents[1]
        source_workbench = Path(__file__).resolve().parents[1] / "workbench"
        report["installed_workbench_hashes"] = _file_hashes(installed)
        report["source_workbench_hashes"] = _file_hashes(source_workbench)
        report["module_source"] = drawings.__file__
        check("capture uses the installed addon", "/Mod/BIM3117/" in str(installed).replace("\\", "/") + "/")
        project = services.get_project(doc)
        identities = {obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")}
        base_revision = snapshot.capture(project)["content_revision"]
        sheets = sorted(drawings.list_sheets(project), key=lambda obj: str(obj.Number))
        states = {str(sheet.Number): drawings.sheet_state(sheet) for sheet in sheets}
        history = doc.UndoCount, doc.RedoCount, len(doc.Objects)
        check("canonical fixture has four views and two sheets", len(drawings.list_views(project)) == 4
              and [str(sheet.Number) for sheet in sheets] == ["A101", "A201"])
        # Headless FCStd files have no GuiDocument.xml. Attach only their host
        # presentation providers; all native parameters/geometry remain intact.
        for obj in doc.Objects:
            if kind(obj) in DOCUMENTATION_KINDS:
                drawings._style(obj)
            else:
                services._style(obj)
        check("headless source receives installed native GUI providers", all(
            getattr(obj.ViewObject.Proxy.__class__, "__module__", "") == "ui3117.viewproviders"
            for obj in doc.Objects))
        Gui.activateWorkbench("BIM3117Workbench")
        main = Gui.getMainWindow()
        main.showNormal()
        main.setGeometry(0, 0, 1500, 1000)
        Gui.Selection.clearSelection()
        for datum in services.list_levels(project) + services.list_grids(project):
            datum.ViewObject.Visibility = False
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        _settle()
        view.fitAll()
        # Keep the native drawing subtree in view alongside the source project.
        for tree in main.findChildren(QtWidgets.QTreeWidget):
            tree.expandAll()
            iterator = QtWidgets.QTreeWidgetItemIterator(tree)
            while iterator.value() is not None:
                item = iterator.value()
                labels = [item.text(column) for column in range(tree.columnCount())]
                if str(project.Label) in labels:
                    item.setExpanded(False)
                if "3117 Drawings" in labels:
                    item.setExpanded(True)
                    parent = item.parent()
                    while parent is not None:
                        parent.setExpanded(True)
                        parent = parent.parent()
                iterator += 1
        Gui.updateGui()
        _settle()
        model_image = screenshots / "Drawings_Workbench.png"
        check("canonical native model/workbench screenshot is captured", main.grab().save(str(model_image)))
        image_records = {"model": {"path": str(model_image), "sha256": _sha(model_image)}}
        for sheet in sheets:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(doc.Name, sheet.Name)
            Gui.runCommand("BIM3117_DrawingPreview")
            panel = panel_for_document(doc.Name)
            check(str(sheet.Number) + " renders its current native definition", panel is not None and not panel._dirty
                  and not panel.last_error and panel.sheet_id == str(sheet.BIM3117Id)
                  and panel.source_snapshot["model_revision"] == states[str(sheet.Number)]["model_revision"]
                  and panel.source_snapshot["drawing_revision"] == states[str(sheet.Number)]["drawing_revision"])
            panel.auto_refresh.setChecked(False)
            panel.setGeometry(80, 45, 1360, 960)
            panel.canvas.fit()
            panel.raise_()
            Gui.updateGui()
            _settle()
            image_path = screenshots / (str(sheet.Number) + "_FreeCAD_Preview.png")
            check(str(sheet.Number) + " preview screenshot is captured", panel.grab().save(str(image_path)))
            image_records[str(sheet.Number)] = {"path": str(image_path), "sha256": _sha(image_path),
                                                "model_revision": panel.source_snapshot["model_revision"],
                                                "drawing_revision": panel.source_snapshot["drawing_revision"]}
        check("presentation adds no native transaction or cache objects", history == (doc.UndoCount, doc.RedoCount, len(doc.Objects)))
        check("presentation preserves all native persistent identities", identities == {
            obj.Name: str(obj.BIM3117Id) for obj in doc.Objects if hasattr(obj, "BIM3117Id")})
        check("presentation preserves model and drawing revision identities", snapshot.capture(project)["content_revision"] == base_revision
              and states == {str(sheet.Number): drawings.sheet_state(sheet) for sheet in sheets})
        check("canonical FCStd remains byte-for-byte unchanged", _sha(source) == source_before)
        report.update(status="passed", source_sha256_after=_sha(source), images=image_records,
                      model_revision=base_revision, sheet_states=states, identifiers=identities)
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        if panel is not None and not panel._closed:
            panel.close()
        for name in set(App.listDocuments()) - original_documents:
            App.closeDocument(name)
        if original_active in App.listDocuments():
            App.setActiveDocument(original_active)
        report["checks_passed"] = len(report["checks"])
        (output / "drawings-presentation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
