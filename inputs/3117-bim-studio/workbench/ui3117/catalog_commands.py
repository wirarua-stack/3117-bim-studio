# SPDX-License-Identifier: GPL-3.0-or-later
"""Catalogue and schedule commands delegate model writes to native services."""

import FreeCADGui as Gui
from . import resource_path
from .qt import run_dialog


def _base():
    from . import commands
    return commands


class CatalogueCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("catalogue.svg"), "MenuText": "Types & Materials / ชนิดและวัสดุ",
                "ToolTip": "Manage shared types, materials and ordered wall/slab layers"}

    def IsActive(self):
        return _base()._has_project()

    def Activated(self):
        try:
            from .catalog_panel import show_catalogue
            show_catalogue(_base()._require_project())
        except Exception as error:
            _base()._report_error("Types & Materials", error)


class CreateMaterialCommand(CatalogueCommand):
    def GetResources(self):
        return {"Pixmap": resource_path("material.svg"), "MenuText": "Create Material / สร้างวัสดุ",
                "ToolTip": "Create a shared native project material with a stable UUID"}

    def Activated(self):
        base = _base()
        try:
            from bim3117_freecad import catalog
            from .catalog_dialogs import MaterialDialog
            project = base._require_project()
            dialog = MaterialDialog({"name": base._next_name(catalog.list_materials(project), "Material")})
            if not run_dialog(dialog):
                return
            obj = catalog.create_material(project, **dialog.values())
        except Exception as error:
            base._report_error("Create Material", error)
            return
        base._focus_object(obj)


class CreateTypeCommand(CatalogueCommand):
    def GetResources(self):
        return {"Pixmap": resource_path("catalogue.svg"), "MenuText": "Create Type / สร้างชนิด",
                "ToolTip": "Create a shared Wall, Slab, Column, Beam, Door or Window type"}

    def Activated(self):
        base = _base()
        try:
            from bim3117_freecad import catalog
            from .catalog_dialogs import TypeDialog
            project = base._require_project()
            dialog = TypeDialog({"name": base._next_name(catalog.list_types(project), "Type"), "category": "Slab"},
                                catalog.list_materials(project))
            if not run_dialog(dialog):
                return
            obj = catalog.create_type(project, **dialog.values())
        except Exception as error:
            base._report_error("Create Type", error)
            return
        base._focus_object(obj)


class AssignTypeCommand(CatalogueCommand):
    def GetResources(self):
        return {"Pixmap": resource_path("catalogue.svg"), "MenuText": "Assign / Change Type",
                "ToolTip": "Assign one compatible type to selected model instances in one transaction"}

    def Activated(self):
        base = _base()
        try:
            from bim3117_freecad import catalog
            from .catalog_dialogs import AssignTypeDialog
            from .catalog_panel import selected_instances
            project = base._require_project()
            objects = selected_instances(project)
            categories = {obj.BIM3117Kind for obj in objects}
            if len(categories) != 1:
                raise ValueError("เลือกชิ้นส่วนหมวดเดียวกัน / Select instances of one category")
            types = catalog.list_types(project, category=next(iter(categories)))
            if not types:
                raise ValueError("สร้างชนิดใน Catalogue ก่อน / Create a compatible type first")
            dialog = AssignTypeDialog(objects, types, catalog.assigned_type(objects[0]))
            if run_dialog(dialog):
                catalog.assign_types(objects, dialog.values()["element_type"])
        except Exception as error:
            base._report_error("Assign Type", error)


class DetachTypeCommand(CatalogueCommand):
    def GetResources(self):
        return {"Pixmap": resource_path("unjoin.svg"), "MenuText": "Detach Type / แยกจากชนิด",
                "ToolTip": "Detach selected non-wall instances and retain their current dimensions"}

    def Activated(self):
        try:
            from bim3117_freecad import catalog
            from .catalog_panel import selected_instances
            catalog.assign_types(selected_instances(_base()._require_project()), None)
        except Exception as error:
            _base()._report_error("Detach Type", error)


class SchedulesCommand(CatalogueCommand):
    def GetResources(self):
        return {"Pixmap": resource_path("schedule.svg"), "MenuText": "Schedules / ตารางปริมาณที่บันทึกไว้",
                "ToolTip": "Filter and group native quantities; edit source rows and export guarded CSV"}

    def Activated(self):
        try:
            from .schedule_panel import show_schedules
            obj = _base()._selected_or_none()
            show_schedules(_base()._require_project(), obj if getattr(obj, "BIM3117Kind", "") == "Schedule" else None)
        except Exception as error:
            _base()._report_error("Schedules", error)


class CreateScheduleCommand(CatalogueCommand):
    def GetResources(self):
        return {"Pixmap": resource_path("schedule.svg"), "MenuText": "Create Schedule / สร้างตารางปริมาณ",
                "ToolTip": "Save a schedule definition outside the authored building model"}

    def Activated(self):
        base = _base()
        try:
            from bim3117_freecad import schedules
            from .schedule_dialogs import ScheduleDefinitionDialog
            project = base._require_project()
            dialog = ScheduleDefinitionDialog(project, {"name": base._next_name(schedules.list_schedules(project), "Schedule")})
            if not run_dialog(dialog):
                return
            obj = schedules.create_schedule(project, **dialog.values())
        except Exception as error:
            base._report_error("Create Schedule", error)
            return
        base._focus_object(obj)


def register():
    for name, command in (("BIM3117_Catalogue", CatalogueCommand()),
                          ("BIM3117_CreateMaterial", CreateMaterialCommand()),
                          ("BIM3117_CreateType", CreateTypeCommand()),
                          ("BIM3117_AssignType", AssignTypeCommand()),
                          ("BIM3117_DetachType", DetachTypeCommand()),
                          ("BIM3117_Schedules", SchedulesCommand()),
                          ("BIM3117_CreateSchedule", CreateScheduleCommand())):
        Gui.addCommand(name, command)
