# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent grid labels using FreeCAD's bundled Coin runtime.

Geometry remains the native Part shape. Unpickable camera-facing text is
presentation only and is rebuilt from native Grid properties on reopen.
"""

from . import resource_path


def _deletion_warning(message):
    import FreeCAD as App
    App.Console.PrintWarning("3117: " + message + "\n")
    if not App.GuiUp:
        return
    import FreeCADGui as Gui
    from .qt import QtCore, QtWidgets, enum_value
    dialog = QtWidgets.QMessageBox(Gui.getMainWindow())
    dialog.setObjectName("BIM3117DeletionWarning")
    dialog.setWindowTitle("3117 — ยังลบรายการนี้ไม่ได้")
    dialog.setIcon(enum_value(QtWidgets.QMessageBox, "Warning", "Icon"))
    dialog.setTextFormat(enum_value(QtCore.Qt, "PlainText", "TextFormat"))
    dialog.setText(message)
    dialog.setStandardButtons(enum_value(QtWidgets.QMessageBox, "Ok", "StandardButton"))
    runner = getattr(dialog, "exec", None) or dialog.exec_
    runner()


def _names(objects):
    values = [obj.Label for obj in objects]
    return ", ".join(values[:8]) + (" … (+{})".format(len(values) - 8) if len(values) > 8 else "")


class _PersistentViewProvider:
    """Native objects retain all data; this proxy persists behavior only."""

    def __init__(self, view_object):
        view_object.Proxy = self
        # Some host paths already initialized a native provider before Proxy
        # is assigned; they do not invoke attach again for the Python proxy.
        if not hasattr(self, "_view"):
            self.attach(view_object)

    def attach(self, view_object):
        self._view = view_object

    def onChanged(self, view_object, _prop):
        if not hasattr(self, "_view"):
            self.attach(view_object)

    def finishRestoring(self, view_object=None):
        # FreeCAD 1.1 calls this hook without arguments; attach has already
        # supplied the native view object during restoration.
        if view_object is None:
            view_object = getattr(self, "_view", None)
        if view_object is not None:
            self.attach(view_object)

    def dumps(self):
        return None

    def loads(self, _state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, _state):
        return None


class ProjectViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("project.svg")

    def claimChildren(self):
        if not hasattr(self, "_view"):
            return []
        children = list(self._view.Object.Group)
        # The authored Wall owns only a presentation subtree. Its derived
        # body and hosted doors still belong to the project in the document.
        return [obj for obj in children if not (
            (getattr(obj, "BIM3117Kind", "") == "WallBody" and getattr(obj, "Wall", None) in children
             and getattr(obj.Wall, "BIM3117Kind", "") == "Wall")
            or (getattr(obj, "BIM3117Kind", "") in ("Door", "Window") and getattr(obj, "Host", None) in children
                and getattr(obj.Host, "BIM3117Kind", "") == "Wall")
        )]

    def onDelete(self, view_object, _subelements):
        project = view_object.Object
        children = list(project.Group)
        # Drawing definitions live in a separate native tree so their presence
        # cannot be inferred from Project.Group alone.
        children.extend(obj for obj in project.Document.Objects
                        if getattr(obj, "BIM3117Kind", "") in ("DrawingSet", "ScheduleSet")
                        and getattr(obj, "Project", None) == project)
        if children:
            _deletion_warning(
                "โครงการยังมีรายการอยู่ภายใน: {}\n\n"
                "กรุณาลบรายการภายในก่อนลบโครงการ "
                "และเปลี่ยนการอ้างอิง Level, Type และ Host ที่ยังใช้งานอยู่ก่อน"
                .format(_names(children))
            )
            return False
        return True


class LevelViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("level.svg")

    def onDelete(self, view_object, _subelements):
        from bim3117_freecad import services
        try:
            dependents = services.level_dependents(view_object.Object)
        except Exception as error:
            _deletion_warning("ยังตรวจสอบการอ้างอิงระดับไม่ได้: " + str(error))
            return False
        if dependents:
            _deletion_warning(
                "ระดับนี้ยังถูกอ้างอิงโดย: {}\n\n"
                "กรุณาใช้ Edit Selected เพื่อเปลี่ยนระดับอ้างอิงของกริดหรือองค์ประกอบอาคาร "
                "ก่อนลบระดับ"
                .format(_names(dependents))
            )
            return False
        return True


class GridViewProvider:
    def __init__(self, view_object):
        view_object.Proxy = self
        self._ensure_attached(view_object)

    def _ensure_attached(self, view_object):
        if getattr(self, "_attaching", False):
            return False
        try:
            if (hasattr(self, "_labels") and hasattr(self, "_switch")
                    and view_object.RootNode.findChild(self._switch) >= 0):
                self._view = view_object
                return True
        except (AttributeError, RuntimeError):
            pass
        self.attach(view_object)
        return hasattr(self, "_labels")

    def attach(self, view_object):
        if getattr(self, "_attaching", False):
            return
        # Avoid duplicate label nodes if FreeCAD calls attach after our explicit
        # setup, or if an existing proxy is reattached during Undo/Redo.
        if hasattr(self, "_labels") and hasattr(self, "_switch"):
            try:
                if view_object.RootNode.findChild(self._switch) >= 0:
                    self._view = view_object
                    self._sync(view_object.Object)
                    return
            except (AttributeError, RuntimeError):
                pass
        from pivy import coin
        self._attaching = True
        self._view = view_object
        self._coin = coin
        self._valid = False
        self._switch = coin.SoSwitch()
        self._root = coin.SoSeparator()
        self._switch.addChild(self._root)
        pick_style = coin.SoPickStyle()
        pick_style.style = coin.SoPickStyle.UNPICKABLE
        self._root.addChild(pick_style)
        self._color = coin.SoBaseColor()
        self._root.addChild(self._color)
        font = coin.SoFont()
        font.name = "sans"
        font.size = 14
        self._root.addChild(font)
        self._labels = []
        for _index in range(2):
            separator = coin.SoSeparator()
            transform = coin.SoTranslation()
            label = coin.SoText2()
            label.justification = coin.SoText2.CENTER
            separator.addChild(transform)
            separator.addChild(label)
            self._root.addChild(separator)
            self._labels.append((transform, label))
        view_object.RootNode.addChild(self._switch)
        self._attaching = False
        self._sync(view_object.Object)
        self.onChanged(view_object, "Visibility")
        self.onChanged(view_object, "LineColor")

    def _sync(self, obj):
        if not hasattr(self, "_labels"):
            return
        required = ("Length", "Position", "Axis", "BubbleLabel", "ElevationOffset", "ReferenceLevel")
        if not all(hasattr(obj, key) for key in required):
            self._valid = False
            self._set_visibility()
            return
        try:
            from bim3117_freecad.model import validate_object, grid_endpoints
            validate_object(obj)
            if obj.Shape.isNull():
                raise ValueError("Grid geometry is not available")
            centres = [(point.x, point.y, point.z) for point in grid_endpoints(obj)]
        except Exception:
            # An unresolved reference must not leave apparently valid labels
            # floating at offset-only elevation while native geometry is empty.
            self._valid = False
            self._set_visibility()
            return
        self._valid = True
        for (translation, label), centre in zip(self._labels, centres):
            translation.translation.setValue(*centre)
            label.string = str(obj.BubbleLabel)
        self._set_visibility()

    def _set_visibility(self):
        self._switch.whichChild = (
            self._coin.SO_SWITCH_ALL if self._valid and self._view.Visibility
            else self._coin.SO_SWITCH_NONE
        )

    def updateData(self, obj, prop):
        view_object = getattr(obj, "ViewObject", None)
        if view_object is None or not self._ensure_attached(view_object):
            return
        if prop in ("Shape", "Length", "Position", "Axis", "BubbleLabel",
                    "ReferenceLevel", "ReferenceLevelId", "ElevationOffset", "ValidationMessage"):
            self._sync(obj)

    def onChanged(self, view_object, prop):
        if not self._ensure_attached(view_object):
            return
        if prop == "Visibility":
            self._set_visibility()
        elif prop == "LineColor":
            rgb = tuple(view_object.LineColor)[:3]
            self._color.rgb.setValue(*rgb)

    def finishRestoring(self, view_object=None):
        if view_object is None:
            view_object = getattr(self, "_view", None)
        if view_object is not None and self._ensure_attached(view_object):
            self._sync(view_object.Object)

    def getIcon(self):
        return resource_path("grid.svg")

    def dumps(self):
        return None

    def loads(self, _state):
        return None

    def __getstate__(self):
        return None

    def __setstate__(self, _state):
        return None


def attach_grid_view(grid):
    """GUI services call on creation; FCStd restores the proxy on reopen."""
    if not hasattr(grid, "ViewObject") or grid.ViewObject is None:
        return None
    if isinstance(grid.ViewObject.Proxy, GridViewProvider):
        return grid.ViewObject.Proxy
    return GridViewProvider(grid.ViewObject)


def attach_level_view(level):
    if not hasattr(level, "ViewObject") or level.ViewObject is None:
        return None
    if isinstance(level.ViewObject.Proxy, LevelViewProvider):
        return level.ViewObject.Proxy
    return LevelViewProvider(level.ViewObject)


def attach_project_view(project):
    if not hasattr(project, "ViewObject") or project.ViewObject is None:
        return None
    if isinstance(project.ViewObject.Proxy, ProjectViewProvider):
        return project.ViewObject.Proxy
    return ProjectViewProvider(project.ViewObject)


class WallTypeViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("wall_type.svg")

    def onDelete(self, view_object, _subelements):
        from bim3117_freecad import catalog
        try:
            dependents = catalog.type_dependents(view_object.Object)
        except Exception as error:
            _deletion_warning("ยังตรวจสอบผนังที่ใช้ชนิดนี้ไม่ได้: " + str(error))
            return False
        if dependents:
            _deletion_warning("ชนิดนี้ยังถูกอ้างอิงโดย: {}\n\nกรุณาเปลี่ยน Type หรือตัวกรอง Schedule ก่อนลบชนิด".format(
                _names(dependents)))
            return False
        return True


class MaterialViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("material.svg")

    def doubleClicked(self, view_object):
        from .catalog_panel import edit_catalog_object
        from .commands import _report_error
        try:
            edit_catalog_object(view_object.Object)
        except Exception as error:
            _report_error("Edit Material", error)
        return True

    def onDelete(self, view_object, _subelements):
        from bim3117_freecad import catalog
        try:
            dependents = catalog.material_dependents(view_object.Object)
        except Exception as error:
            _deletion_warning("ยังตรวจสอบการอ้างอิงวัสดุไม่ได้: " + str(error))
            return False
        if dependents:
            _deletion_warning("วัสดุนี้ยังถูกอ้างอิงโดย: {}\n\nเปลี่ยนวัสดุของชนิดก่อนลบ".format(_names(dependents)))
            return False
        return True


class ElementTypeViewProvider(WallTypeViewProvider):
    def getIcon(self):
        return resource_path("catalogue.svg")

    def doubleClicked(self, view_object):
        from .catalog_panel import edit_catalog_object
        from .commands import _report_error
        try:
            edit_catalog_object(view_object.Object)
        except Exception as error:
            _report_error("Edit Type", error)
        return True


class ScheduleSetViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("schedule.svg")

    def claimChildren(self):
        return list(self._view.Object.Group) if hasattr(self, "_view") else []

    def onDelete(self, view_object, _subelements):
        if view_object.Object.Group:
            _deletion_warning("กรุณาลบตารางภายในก่อน / Delete the schedules in this set first")
            return False
        return True


class ScheduleViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("schedule.svg")

    def doubleClicked(self, view_object):
        from .schedule_panel import show_schedules
        from .commands import _report_error
        try:
            obj = view_object.Object
            show_schedules(obj.Project, obj)
        except Exception as error:
            _report_error("Schedule", error)
        return True

    def onDelete(self, view_object, _subelements):
        _deletion_warning("ใช้ 3117 BIM → Delete Selected เพื่อลบตารางในหนึ่ง Undo")
        return False


class WallViewProvider(_PersistentViewProvider):
    def __init__(self, view_object):
        super().__init__(view_object)
        # App::FeaturePython has no shape and starts hidden in FreeCAD. The
        # authored wall controls its displayed subtree, so a newly created
        # wall must begin visible like its solid. Restoration uses attach /
        # finishRestoring and must preserve the saved per-object view states.
        doc = view_object.Object.Document
        if doc is not None and not getattr(doc, "Restoring", False):
            # A headless-created FCStd first receives its native GUI provider
            # before this Python proxy is attached. Its DisplayMode property
            # can therefore still have the initial empty enumeration even
            # though listDisplayModes() already reports our registered mode.
            # Initialize values of the existing native PropertyEnumeration;
            # do not replace the property or disturb an already valid mode.
            if "Default" not in view_object.getEnumerationsOfProperty("DisplayMode"):
                view_object.DisplayMode = list(view_object.listDisplayModes())
            view_object.DisplayMode = "Default"
            view_object.Visibility = True

    def attach(self, view_object):
        super().attach(view_object)
        from pivy import coin
        # A shapeless FeaturePython still needs a native display mode for
        # isVisible()/Space to agree with its Visibility property. The host's
        # ArchAxisSystem uses this same empty-mode container mechanism.
        # Repeated attach/finishRestoring must not register duplicate nodes.
        node = getattr(self, "_mode_node", None)
        if node is not None:
            search = coin.SoSearchAction()
            search.setNode(node)
            search.setSearchingAll(True)
            search.apply(view_object.RootNode)
            if search.getPath() is not None:
                return
        self._mode_node = coin.SoSeparator()
        view_object.addDisplayMode(self._mode_node, "Default")

    def getDisplayModes(self, _view_object):
        return ["Default"]

    def getDefaultDisplayMode(self):
        return "Default"

    def setDisplayMode(self, mode):
        return mode

    def getIcon(self):
        return resource_path("wall.svg")

    def claimChildren(self):
        if not hasattr(self, "_view"):
            return []
        wall = self._view.Object
        body = getattr(wall, "Body", None)
        children = [body] if (getattr(body, "BIM3117Kind", "") == "WallBody"
                              and getattr(body, "Wall", None) == wall) else []
        doc = wall.Document
        if doc is not None:
            children.extend(obj for obj in doc.Objects if getattr(obj, "BIM3117Kind", "") in ("Door", "Window")
                            and getattr(obj, "Host", None) == wall)
        return children

    def onChanged(self, view_object, prop):
        super().onChanged(view_object, prop)
        doc = view_object.Object.Document
        if prop != "Visibility" or doc is None or getattr(doc, "Restoring", False) or doc.Transacting:
            return
        for child in self.claimChildren():
            if child.ViewObject is not None:
                child.ViewObject.Visibility = view_object.Visibility

    def onDelete(self, view_object, _subelements):
        _deletion_warning(
            "กรุณาใช้ 3117 BIM → Delete Selected เพื่อลบผนังพร้อมรูปทรงในหนึ่ง Undo\n\n"
            "หากยังมีประตูหรือหน้าต่างอยู่ ให้ลบหรือย้ายช่องเปิดก่อนลบผนัง"
        )
        return False


class WallBodyViewProvider(_PersistentViewProvider):
    def __init__(self, view_object):
        super().__init__(view_object)
        _inherit_initial_visibility(view_object, "Wall")

    def getIcon(self):
        return resource_path("wall.svg")

    def onDelete(self, view_object, _subelements):
        _deletion_warning(
            "รูปทรงนี้คำนวณจากผนังและช่องเปิด\n\n"
            "ใช้ Edit Selected เพื่อแก้ผนัง หรือ 3117 BIM → Delete Selected เพื่อลบผนัง"
        )
        return False


class DoorViewProvider(_PersistentViewProvider):
    def __init__(self, view_object):
        super().__init__(view_object)
        _inherit_initial_visibility(view_object, "Host")

    def getIcon(self):
        return resource_path("door.svg")

    def onDelete(self, view_object, _subelements):
        _deletion_warning(
            "กรุณาใช้ 3117 BIM → Delete Selected เพื่อลบประตูและคืนเนื้อผนัง\n\n"
            "Undo จะคืนทั้งประตูและช่องเปิดพร้อมกัน"
        )
        return False


class WindowViewProvider(DoorViewProvider):
    def getIcon(self):
        return resource_path("window.svg")

    def onDelete(self, view_object, _subelements):
        _deletion_warning(
            "กรุณาใช้ 3117 BIM → Delete Selected เพื่อลบหน้าต่างและคืนเนื้อผนัง\n\n"
            "Undo จะคืนทั้งหน้าต่างและช่องเปิดพร้อมกัน"
        )
        return False


class SlabViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("slab.svg")

    def onDelete(self, view_object, _subelements):
        from bim3117_freecad import services
        try:
            dependents = services.slab_dependents(view_object.Object)
        except Exception as error:
            _deletion_warning("ยังตรวจสอบการอ้างอิงพื้นไม่ได้: " + str(error))
            return False
        if dependents:
            _deletion_warning("พื้นนี้ใช้ตัดองค์ประกอบอยู่: {}\n\nใช้ Unjoin Slab ก่อนลบพื้น".format(_names(dependents)))
            return False
        return True


class ColumnViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("column.svg")


class BeamViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("beam.svg")


class DrawingSetViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("drawing.svg")

    def claimChildren(self):
        return list(self._view.Object.Group) if hasattr(self, "_view") else []

    def onDelete(self, view_object, _subelements):
        if not view_object.Object.Group:
            return True
        _deletion_warning("ชุดแบบยังเป็นส่วนหนึ่งของโครงการ\nใช้ 3117 Delete Selected เพื่อลบแผ่นแบบและมุมมองแต่ละรายการ")
        return False


class DrawingViewProvider(_PersistentViewProvider):
    def getIcon(self):
        view = getattr(self, "_view", None)
        kind = str(getattr(view.Object, "ViewType", "Plan")) if view is not None else "Plan"
        return resource_path(kind.lower() + ".svg")

    def doubleClicked(self, view_object):
        import FreeCADGui as Gui
        from .drawing_commands import edit_drawing
        from .commands import _report_error
        try:
            edit_drawing(view_object.Object)
        except Exception as error:
            _report_error("Edit Drawing View", error)
        return True

    def onDelete(self, view_object, _subelements):
        _deletion_warning("ใช้ 3117 BIM → Delete Selected เพื่อลบมุมมอง\nระบบจะตรวจแผ่นแบบที่ยังอ้างอิงก่อนลบ")
        return False


class DrawingSheetViewProvider(_PersistentViewProvider):
    def getIcon(self):
        return resource_path("sheet.svg")

    def doubleClicked(self, view_object):
        from .drawing_preview import show_sheet_preview
        from .commands import _report_error
        try:
            show_sheet_preview(view_object.Object)
        except Exception as error:
            _report_error("Drawing Preview", error)
        return True

    def onDelete(self, view_object, _subelements):
        _deletion_warning("ใช้ 3117 BIM → Delete Selected เพื่อลบแผ่นแบบ\nUndo จะคืนแผ่นแบบและการอ้างอิงมุมมอง")
        return False


def _inherit_initial_visibility(view_object, host_property):
    obj = view_object.Object
    doc = obj.Document
    if doc is None or getattr(doc, "Restoring", False):
        return
    host = getattr(obj, host_property, None)
    host_view = getattr(host, "ViewObject", None)
    if host_view is not None:
        view_object.Visibility = host_view.Visibility


def _attach_view(obj, provider):
    view = getattr(obj, "ViewObject", None)
    if view is None:
        return None
    if isinstance(view.Proxy, provider):
        return view.Proxy
    return provider(view)


def attach_wall_type_view(obj):
    return _attach_view(obj, WallTypeViewProvider)


def attach_wall_view(obj):
    return _attach_view(obj, WallViewProvider)


def attach_wall_body_view(obj):
    return _attach_view(obj, WallBodyViewProvider)


def attach_door_view(obj):
    return _attach_view(obj, DoorViewProvider)


def attach_window_view(obj):
    return _attach_view(obj, WindowViewProvider)


def attach_slab_view(obj):
    return _attach_view(obj, SlabViewProvider)


def attach_column_view(obj):
    return _attach_view(obj, ColumnViewProvider)


def attach_beam_view(obj):
    return _attach_view(obj, BeamViewProvider)


def attach_drawing_set_view(obj):
    return _attach_view(obj, DrawingSetViewProvider)


def attach_drawing_view(obj):
    return _attach_view(obj, DrawingViewProvider)


def attach_drawing_sheet_view(obj):
    return _attach_view(obj, DrawingSheetViewProvider)


def attach_material_view(obj):
    return _attach_view(obj, MaterialViewProvider)


def attach_element_type_view(obj):
    return _attach_view(obj, ElementTypeViewProvider)


def attach_schedule_set_view(obj):
    return _attach_view(obj, ScheduleSetViewProvider)


def attach_schedule_view(obj):
    return _attach_view(obj, ScheduleViewProvider)
