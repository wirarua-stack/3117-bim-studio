# SPDX-License-Identifier: GPL-3.0-or-later
"""Native FreeCAD commands. Services own every model transaction."""

import platform
import sys

import FreeCAD as App
import FreeCADGui as Gui

from . import __version__, resource_path
from .qt import QtCore, QtWidgets, run_dialog


def _services():
    # Separate from the headless reference-core package named bim3117.
    from bim3117_freecad import services
    return services


def _mm(value):
    return float(getattr(value, "Value", value))


def _report_error(action, error):
    message = str(error) or type(error).__name__
    App.Console.PrintError("3117 {}: {}\n".format(action, message))
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "3117 — " + action, message)


def _require_project():
    if App.ActiveDocument is None:
        raise ValueError("ยังไม่มีเอกสารโครงการ กรุณาใช้ Create Project ก่อน")
    project = _services().get_project(App.ActiveDocument)
    if project is None:
        raise ValueError("เอกสารนี้ยังไม่มีโครงการ 3117 กรุณาใช้ Create Project เพื่อเริ่มโครงการใหม่")
    return project


def _has_project():
    if App.ActiveDocument is None:
        return False
    try:
        return _services().get_project(App.ActiveDocument) is not None
    except Exception:
        return False


def _selected_native_object():
    selected = Gui.Selection.getSelection()
    if len(selected) != 1:
        raise ValueError("กรุณาเลือกองค์ประกอบของ 3117 เพียงหนึ่งรายการ")
    obj = selected[0]
    if App.ActiveDocument is None or obj.Document != App.ActiveDocument:
        raise ValueError("กรุณาเลือกองค์ประกอบในเอกสารที่กำลังใช้งาน")
    if _services().kind(obj) not in ("DrawingView", "DrawingSheet", "Material", "ElementType", "Schedule"):
        obj = _services().resolve_authoring_object(obj)
    if _services().kind(obj).lower() not in (
            "project", "level", "grid", "walltype", "wall", "door", "window", "slab", "column", "beam",
            "drawingview", "drawingsheet", "material", "elementtype", "schedule"):
        raise ValueError("รายการที่เลือกไม่ใช่องค์ประกอบที่แก้ไขได้ของ 3117")
    return obj


def _focus_object(obj, fit=False, axonometric=False):
    # Model edit already committed: view errors must not be reported as a
    # failed/rolled-back model transaction.
    try:
        App.setActiveDocument(obj.Document.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj.Document.Name, obj.Name)
        view = Gui.activeDocument().activeView()
        if axonometric:
            view.viewAxonometric()
        if fit:
            view.fitAll()
        Gui.updateGui()
    except Exception as error:
        App.Console.PrintWarning("3117 object created/edited; view refresh: {}\n".format(error))


def _next_level_defaults(project):
    levels = _services().list_levels(project)
    labels = {level.Label for level in levels}
    index = len(levels)
    while "L{:02d}".format(index) in labels:
        index += 1
    elevation = max((_mm(level.Elevation) for level in levels), default=-3000.0) + 3000.0
    return {"name": "L{:02d}".format(index), "elevation_mm": elevation}


def _letters(index):
    result = ""
    index += 1
    while index:
        index, digit = divmod(index - 1, 26)
        result = chr(65 + digit) + result
    return result


def _next_grid_defaults(project):
    services = _services()
    grids = services.list_grids(project)
    used = {str(grid.BubbleLabel) for grid in grids}
    index = 0
    while _letters(index) in used:
        index += 1
    mark = _letters(index)
    same_axis = [grid for grid in grids if str(grid.Axis) == "X"]
    position = max((_mm(grid.Position) for grid in same_axis), default=-4000.0) + 4000.0
    levels = services.list_levels(project)
    reference = min(levels, key=lambda level: _mm(level.Elevation)) if levels else None
    selected = Gui.Selection.getSelection()
    if len(selected) == 1 and selected[0] in levels:
        reference = selected[0]
    return {
        "label": "Grid " + mark, "bubble_label": mark,
        "axis": "X", "position_mm": position,
        "length_mm": 12000.0, "level": reference, "offset_mm": 0.0,
    }


def _next_name(objects, prefix):
    used = {obj.Label for obj in objects}
    index = 1
    while "{} {:02d}".format(prefix, index) in used:
        index += 1
    return "{} {:02d}".format(prefix, index)


def _selected_or_none():
    try:
        return _selected_native_object()
    except Exception:
        return None


def _wall_defaults(project):
    services = _services()
    types = services.list_wall_types(project)
    levels = services.list_levels(project)
    if not types:
        raise ValueError("กรุณาใช้ Create Wall Type เพื่อสร้างชนิดผนังก่อน")
    if len(levels) < 2:
        raise ValueError("กรุณาเพิ่มระดับฐานและระดับยอดด้วย Add Level ก่อนสร้างผนัง")
    ordered = sorted(levels, key=lambda level: _mm(level.Elevation))
    selected = _selected_or_none()
    wall_type = selected if selected in types else types[0]
    base = selected if selected in levels else ordered[0]
    top = next((level for level in ordered if _mm(level.Elevation) > _mm(base.Elevation)), ordered[-1])
    if top == base:
        base, top = ordered[0], ordered[-1]
    return {
        "name": _next_name(services.list_walls(project), "Wall"),
        "wall_type": wall_type, "base_level": base, "top_level": top,
        "start_x_mm": 0, "start_y_mm": 0, "end_x_mm": 6000, "end_y_mm": 0,
    }


class CreateWallTypeCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("wall_type.svg"),
                "MenuText": "Create Wall Type / สร้างชนิดผนัง",
                "ToolTip": "Create a shared wall thickness and material label"}

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .dialogs import make_wall_type_dialog
            services, project = _services(), _require_project()
            dialog = make_wall_type_dialog(initial={
                "name": _next_name(services.list_wall_types(project), "Wall Type"),
                "thickness_mm": 200.0,
            })
            if not run_dialog(dialog):
                return
            obj = services.create_wall_type(project, **dialog.values())
        except Exception as error:
            _report_error("Create Wall Type", error)
            return
        _focus_object(obj)


class CreateWallCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("wall.svg"),
                "MenuText": "Create Wall / สร้างผนัง",
                "ToolTip": "Create a straight wall from XY endpoints and Base/Top Levels"}

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .dialogs import make_wall_dialog
            services, project = _services(), _require_project()
            dialog = make_wall_dialog(initial=_wall_defaults(project),
                                      wall_types=services.list_wall_types(project),
                                      levels=services.list_levels(project))
            if not run_dialog(dialog):
                return
            obj = services.create_wall(project, **dialog.values())
        except Exception as error:
            _report_error("Create Wall", error)
            return
        _focus_object(obj, fit=True, axonometric=True)


class CreateDoorCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("door.svg"),
                "MenuText": "Create Door / สร้างประตู",
                "ToolTip": "Place a hosted rectangular door opening and simple frame in a wall"}

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .dialogs import make_door_dialog
            services, project = _services(), _require_project()
            walls = services.list_walls(project)
            if not walls:
                raise ValueError("กรุณาใช้ Create Wall เพื่อสร้างผนังเจ้าบ้านก่อน")
            selected = _selected_or_none()
            host = selected if selected in walls else walls[0]
            length, height = _mm(host.Length), _mm(host.Height)
            width = min(900.0, length / 3.0)
            dialog = make_door_dialog(walls=walls, initial={
                "name": _next_name(services.list_doors(project), "Door"), "host": host,
                "width_mm": width, "height_mm": min(2100.0, height * 0.8),
                "offset_mm": min(1000.0, max(0.0, (length - width) / 2.0)),
            })
            if not run_dialog(dialog):
                return
            obj = services.create_door(project, **dialog.values())
        except Exception as error:
            _report_error("Create Door", error)
            return
        _focus_object(obj, fit=True)


class CreateWindowCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("window.svg"),
                "MenuText": "Create Window / สร้างหน้าต่าง",
                "ToolTip": "Cut a hosted rectangular window opening with a simple four-sided frame"}

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .dialogs import make_window_dialog
            services, project = _services(), _require_project()
            walls = services.list_walls(project)
            if not walls:
                raise ValueError("กรุณาใช้ Create Wall เพื่อสร้างผนังเจ้าบ้านก่อน")
            selected = _selected_or_none()
            host = selected if selected in walls else walls[0]
            length, height = _mm(host.Length), _mm(host.Height)
            width = min(1200.0, length / 3.0)
            opening_height = min(1200.0, height * 0.5)
            dialog = make_window_dialog(walls=walls, initial={
                "name": _next_name(services.list_windows(project), "Window"), "host": host,
                "width_mm": width, "height_mm": opening_height,
                "sill_mm": min(900.0, max(0.0, height - opening_height)),
                "offset_mm": min(1000.0, max(0.0, (length - width) / 2.0)),
            })
            if not run_dialog(dialog):
                return
            obj = services.create_window(project, **dialog.values())
        except Exception as error:
            _report_error("Create Window", error)
            return
        _focus_object(obj, fit=True)


def _building_defaults(project, object_kind):
    services = _services()
    levels = sorted(services.list_levels(project), key=lambda obj: _mm(obj.Elevation))
    if not levels:
        raise ValueError("กรุณาเพิ่มระดับอ้างอิงด้วย Add Level ก่อน")
    selected = _selected_or_none()
    name = _next_name(getattr(services, "list_" + object_kind.lower() + "s")(project), object_kind)
    if object_kind == "Column":
        if len(levels) < 2:
            raise ValueError("เสาต้องมีระดับฐานและระดับยอด กรุณาเพิ่มระดับด้วย Add Level")
        base = selected if selected in levels else levels[0]
        top = next((level for level in levels if _mm(level.Elevation) > _mm(base.Elevation)), None)
        if top is None:
            base, top = levels[-2], levels[-1]
        return {"name": name, "base_level": base, "top_level": top}
    level = selected if selected in levels else levels[min(1, len(levels) - 1)]
    return {"name": name, "level": level}


def _building_dialog(object_kind, project, initial, editing=False):
    from . import building_dialogs
    factory = getattr(building_dialogs, "make_" + object_kind.lower() + "_dialog")
    return factory(initial=initial, levels=_services().list_levels(project), editing=editing)


class _CreateBuildingCommand:
    object_kind = ""
    label_th = ""
    tooltip = ""

    def GetResources(self):
        return {"Pixmap": resource_path(self.object_kind.lower() + ".svg"),
                "MenuText": "Create {} / สร้าง{}".format(self.object_kind, self.label_th),
                "ToolTip": self.tooltip}

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            services, project = _services(), _require_project()
            dialog = _building_dialog(self.object_kind, project, _building_defaults(project, self.object_kind))
            if not run_dialog(dialog):
                return
            obj = getattr(services, "create_" + self.object_kind.lower())(project, **dialog.values())
        except Exception as error:
            _report_error("Create " + self.object_kind, error)
            return
        _focus_object(obj, fit=True, axonometric=True)


class CreateSlabCommand(_CreateBuildingCommand):
    object_kind, label_th = "Slab", "พื้น"
    tooltip = "Create an XY polygon slab; top is Level + Offset and thickness extends down"


class CreateColumnCommand(_CreateBuildingCommand):
    object_kind, label_th = "Column", "เสา"
    tooltip = "Create a vertical rectangular column centered at XY with Base/Top Levels"


class CreateBeamCommand(_CreateBuildingCommand):
    object_kind, label_th = "Beam", "คาน"
    tooltip = "Create a horizontal beam centered on an XY axis; depth extends down from its top level"


class JoinSlabCommand:
    unjoin = False

    def GetResources(self):
        return {"Pixmap": resource_path("unjoin.svg" if self.unjoin else "join.svg"),
                "MenuText": "Unjoin Slab / ยกเลิกตัดด้วยพื้น" if self.unjoin else "Join Slab / ตัดด้วยพื้น",
                "ToolTip": "Remove one slab cut from a column or beam" if self.unjoin else
                "Cut a column or beam with one slab; the target must remain one solid"}

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .building_dialogs import make_join_slab_dialog
            services, project = _services(), _require_project()
            members = services.list_columns(project) + services.list_beams(project)
            if self.unjoin:
                members = [member for member in members if member.JoinSlabs or member.JoinSlabIds]
            slabs = services.list_slabs(project)
            if not members or (not slabs and not self.unjoin):
                raise ValueError("ยังไม่มีเสาหรือคานที่ตัดด้วยพื้น" if self.unjoin else
                                 "ต้องมีพื้นและเสาหรือคานในโครงการก่อนใช้ Join Slab")
            selected = [services.resolve_authoring_object(obj) for obj in Gui.Selection.getSelection()
                        if obj.Document == project.Document]
            member = next((obj for obj in selected if obj in members), members[0])
            slab = next((obj for obj in selected if obj in slabs), None)
            dialog = make_join_slab_dialog(members=members, slabs=slabs, unjoin=self.unjoin,
                                           initial={"member": member, "slab": slab})
            if not run_dialog(dialog):
                return
            values = dialog.values()
            operation = services.unjoin_slab if self.unjoin else services.join_slab
            operation(values["member"], values["slab"])
            member = values["member"]
        except Exception as error:
            _report_error("Unjoin Slab" if self.unjoin else "Join Slab", error)
            return
        _focus_object(member)


class UnjoinSlabCommand(JoinSlabCommand):
    unjoin = True


class DeleteSelectedCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("delete.svg"),
                "MenuText": "Delete Selected / ลบรายการที่เลือก",
                "ToolTip": "Delete a supported element after checking hosts, levels and slab joins; Undo restores it"}

    def IsActive(self):
        try:
            return _services().kind(_selected_native_object()) in (
                "Door", "Window", "Wall", "WallType", "Level", "Slab", "Column", "Beam", "DrawingView", "DrawingSheet",
                "Material", "ElementType", "Schedule")
        except Exception:
            return False

    def Activated(self):
        try:
            obj = _selected_native_object()
            services = _services()
            object_kind = services.kind(obj)
            if object_kind in ("DrawingView", "DrawingSheet"):
                from .drawing_commands import delete_drawing
                delete_drawing(obj)
                return
            if object_kind in ("Material", "ElementType", "WallType"):
                from bim3117_freecad import catalog
                operation = catalog.delete_material if object_kind == "Material" else catalog.delete_type
                project = obj.Project
                operation(obj)
                _focus_object(project)
                return
            if object_kind == "Schedule":
                from bim3117_freecad import schedules
                project = obj.Project
                schedules.delete_schedule(obj)
                _focus_object(project)
                return
            operations = {"Door": services.delete_door, "Wall": services.delete_wall,
                          "Window": services.delete_window, "Slab": services.delete_slab,
                          "Column": services.delete_column, "Beam": services.delete_beam,
                          "WallType": services.delete_wall_type, "Level": services.delete_level}
            if object_kind not in operations:
                raise ValueError("กรุณาเลือกองค์ประกอบอาคาร หรือชนิด/ระดับที่ไม่มีการอ้างอิง")
            project = obj.Project
            operations[object_kind](obj)
        except Exception as error:
            _report_error("Delete Selected", error)
            return
        _focus_object(project)


class CreateProjectCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("project.svg"),
            "MenuText": "Create Project / สร้างโครงการ",
            "ToolTip": "Create a new 3117 project with optional L00 and L01 levels",
        }

    def IsActive(self):
        return True

    def Activated(self):
        try:
            from .dialogs import make_project_dialog
            dialog = make_project_dialog()
            if not run_dialog(dialog):
                return
            project = _services().create_project(**dialog.values())
        except Exception as error:
            _report_error("Create Project", error)
            return
        _focus_object(project, fit=True, axonometric=True)
        App.Console.PrintMessage("3117 project created: {}\n".format(project.Label))


class AddLevelCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("level.svg"),
            "MenuText": "Add Level / เพิ่มระดับ",
            "ToolTip": "Add a level to the active 3117 project; dimensions are in millimetres",
        }

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .dialogs import make_level_dialog
            project = _require_project()
            dialog = make_level_dialog(initial=_next_level_defaults(project))
            if not run_dialog(dialog):
                return
            level = _services().add_level(project, **dialog.values())
        except Exception as error:
            _report_error("Add Level", error)
            return
        _focus_object(level, fit=True)


class CreateGridCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("grid.svg"),
            "MenuText": "Create Grid / สร้างกริด",
            "ToolTip": "Create a labelled grid line and optionally link its elevation to a level",
        }

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .dialogs import make_grid_dialog
            project = _require_project()
            dialog = make_grid_dialog(
                initial=_next_grid_defaults(project), levels=_services().list_levels(project),
            )
            if not run_dialog(dialog):
                return
            grid = _services().create_grid(project, **dialog.values())
        except Exception as error:
            _report_error("Create Grid", error)
            return
        _focus_object(grid, fit=True)


class EditSelectedCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("edit.svg"),
            "MenuText": "Edit Selected / แก้ไขรายการที่เลือก",
            "ToolTip": "Edit a selected 3117 element; selecting a wall solid edits its wall parameters",
        }

    def IsActive(self):
        try:
            _selected_native_object()
            return True
        except Exception:
            return False

    def Activated(self):
        try:
            from .dialogs import (make_project_dialog, make_level_dialog, make_grid_dialog,
                                  make_wall_type_dialog, make_wall_dialog, make_door_dialog, make_window_dialog)
            obj = _selected_native_object()
            services = _services()
            kind = services.kind(obj).lower()
            if kind in ("drawingview", "drawingsheet"):
                from .drawing_commands import edit_drawing
                edit_drawing(obj)
                return
            elif kind in ("material", "elementtype") or (kind == "walltype" and (
                    getattr(obj, "MaterialRef", None) is not None or getattr(obj, "LayerMaterials", []))):
                from .catalog_panel import edit_catalog_object
                edit_catalog_object(obj)
                return
            elif kind == "schedule":
                from .schedule_panel import edit_schedule
                edit_schedule(obj)
                return
            elif kind == "project":
                dialog = make_project_dialog(editing=True, initial={
                    "name": obj.Label, "project_number": str(obj.ProjectNumber),
                    "author": str(obj.Author),
                })
                operation = services.edit_project
            elif kind == "level":
                dialog = make_level_dialog(editing=True, initial={
                    "name": obj.Label, "elevation_mm": _mm(obj.Elevation),
                    "span_x_mm": _mm(obj.SpanX), "span_y_mm": _mm(obj.SpanY),
                })
                operation = services.edit_level
            elif kind == "grid":
                project = _require_project()
                dialog = make_grid_dialog(editing=True, levels=services.list_levels(project), initial={
                    "label": obj.Label, "axis": str(obj.Axis),
                    "position_mm": _mm(obj.Position), "length_mm": _mm(obj.Length),
                    "bubble_label": str(obj.BubbleLabel), "level": obj.ReferenceLevel,
                    "offset_mm": _mm(obj.ElevationOffset),
                    "reference_missing": obj.ReferenceLevel is None and bool(getattr(obj, "ReferenceLevelId", "")),
                })
                operation = services.edit_grid
            elif kind == "walltype":
                dialog = make_wall_type_dialog(editing=True, initial={
                    "name": obj.Label, "thickness_mm": _mm(obj.Thickness), "material": str(obj.Material),
                })
                operation = services.edit_wall_type
            elif kind == "wall":
                dialog = make_wall_dialog(editing=True,
                    wall_types=services.list_wall_types(obj.Project), levels=services.list_levels(obj.Project),
                    initial={"name": obj.Label, "wall_type": obj.WallType,
                             "base_level": obj.BaseLevel, "top_level": obj.TopLevel,
                             "start_x_mm": _mm(obj.StartX), "start_y_mm": _mm(obj.StartY),
                             "end_x_mm": _mm(obj.EndX), "end_y_mm": _mm(obj.EndY),
                             "base_offset_mm": _mm(obj.BaseOffset), "top_offset_mm": _mm(obj.TopOffset)})
                operation = services.edit_wall
            elif kind in ("door", "window"):
                factory = make_window_dialog if kind == "window" else make_door_dialog
                dialog = factory(editing=True, walls=services.list_walls(obj.Project), initial={
                    "name": obj.Label, "host": obj.Host, "offset_mm": _mm(obj.Offset),
                    "width_mm": _mm(obj.Width), "height_mm": _mm(obj.Height), "sill_mm": _mm(obj.Sill),
                })
                operation = services.edit_window if kind == "window" else services.edit_door
            elif kind == "slab":
                dialog = _building_dialog("Slab", obj.Project, {
                    "name": obj.Label, "level": obj.Level, "boundary_mm": [(v.x, v.y) for v in obj.Boundary],
                    "thickness_mm": _mm(obj.Thickness), "offset_mm": _mm(obj.Offset),
                    "material": str(obj.Material)}, editing=True)
                operation = services.edit_slab
            elif kind == "column":
                dialog = _building_dialog("Column", obj.Project, {
                    "name": obj.Label, "x_mm": _mm(obj.X), "y_mm": _mm(obj.Y),
                    "width_mm": _mm(obj.Width), "depth_mm": _mm(obj.Depth), "rotation_deg": _mm(obj.Rotation),
                    "base_level": obj.BaseLevel, "top_level": obj.TopLevel,
                    "base_offset_mm": _mm(obj.BaseOffset), "top_offset_mm": _mm(obj.TopOffset),
                    "material": str(obj.Material)}, editing=True)
                operation = services.edit_column
            elif kind == "beam":
                dialog = _building_dialog("Beam", obj.Project, {
                    "name": obj.Label, "level": obj.Level,
                    "start_mm": (_mm(obj.StartX), _mm(obj.StartY)),
                    "end_mm": (_mm(obj.EndX), _mm(obj.EndY)),
                    "width_mm": _mm(obj.Width), "depth_mm": _mm(obj.Depth),
                    "offset_mm": _mm(obj.Offset), "material": str(obj.Material)}, editing=True)
                operation = services.edit_beam
            else:
                raise ValueError("ยังไม่มีแบบฟอร์มแก้ไของค์ประกอบชนิดนี้")
            if kind in ("door", "window", "slab", "column", "beam"):
                from .catalog_dialogs import lock_instance_type_fields
                lock_instance_type_fields(dialog, obj)
            if not run_dialog(dialog):
                return
            operation(obj, **dialog.values())
        except Exception as error:
            _report_error("Edit Selected", error)
            return
        _focus_object(obj, fit=kind in ("level", "grid", "wall", "door", "window", "slab", "column", "beam"))


class QuantitiesCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("quantities.svg"),
            "MenuText": "Quantities / ตารางปริมาณ",
            "ToolTip": "Inspect current building quantities, select source objects and export CSV",
        }

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .exchange_dialog import show_quantities
            show_quantities(_require_project())
        except Exception as error:
            _report_error("Quantities", error)


class ExportIFCCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("export_ifc.svg"),
            "MenuText": "Export IFC4 / ส่งออก IFC4",
            "ToolTip": "Review export coverage and write IFC4 from the current native model",
        }

    def IsActive(self):
        return _has_project()

    def Activated(self):
        try:
            from .exchange_dialog import show_quantities
            panel = show_quantities(_require_project())
            panel.export_ifc()
        except Exception as error:
            _report_error("Export IFC4", error)


class HostInfoCommand:
    def GetResources(self):
        return {
            "Pixmap": resource_path("info.svg"),
            "MenuText": "Host Information / ข้อมูลโปรแกรม",
            "ToolTip": "Show the running FreeCAD, Python and Qt versions",
        }

    def IsActive(self):
        return True

    def Activated(self):
        try:
            text = (
                "3117 BIM Studio {}\n"
                "FreeCAD: {}\nPython: {}\nQt: {}\nOS: {}\n\n"
                "Project · Level · Grid · Wall Type · Wall · Door · Window\n"
                "Slab · Column · Beam · explicit Slab joins\n"
                "Native quantities · CSV · IFC4 exchange\n"
                "Plan · Section · Elevation · A3 Sheets · SVG / PDF\n"
                "Shared types · Materials / Layers · Editable source schedules\n"
                "Save projects as .FCStd. Use native Undo / Redo."
            ).format(
                __version__, ".".join(str(value) for value in App.Version()),
                sys.version.split()[0], QtCore.qVersion(), platform.platform(),
            )
            App.Console.PrintMessage(text + "\n")
            QtWidgets.QMessageBox.information(Gui.getMainWindow(), "3117 BIM Studio", text)
        except Exception as error:
            _report_error("Host Information", error)


def register():
    for name, command in (
        ("BIM3117_CreateProject", CreateProjectCommand()),
        ("BIM3117_AddLevel", AddLevelCommand()),
        ("BIM3117_CreateGrid", CreateGridCommand()),
        ("BIM3117_CreateWallType", CreateWallTypeCommand()),
        ("BIM3117_CreateWall", CreateWallCommand()),
        ("BIM3117_CreateDoor", CreateDoorCommand()),
        ("BIM3117_CreateWindow", CreateWindowCommand()),
        ("BIM3117_CreateSlab", CreateSlabCommand()),
        ("BIM3117_CreateColumn", CreateColumnCommand()),
        ("BIM3117_CreateBeam", CreateBeamCommand()),
        ("BIM3117_JoinSlab", JoinSlabCommand()),
        ("BIM3117_UnjoinSlab", UnjoinSlabCommand()),
        ("BIM3117_EditSelected", EditSelectedCommand()),
        ("BIM3117_DeleteSelected", DeleteSelectedCommand()),
        ("BIM3117_Quantities", QuantitiesCommand()),
        ("BIM3117_ExportIFC", ExportIFCCommand()),
        ("BIM3117_HostInfo", HostInfoCommand()),
    ):
        Gui.addCommand(name, command)
    from . import drawing_commands
    drawing_commands.register()
    from . import catalog_commands
    catalog_commands.register()
