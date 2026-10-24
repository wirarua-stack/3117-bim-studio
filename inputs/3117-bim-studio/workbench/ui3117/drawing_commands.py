# SPDX-License-Identifier: GPL-3.0-or-later
"""Native drawing commands; definitions belong to the document service."""

import FreeCADGui as Gui

from . import resource_path
from .qt import run_dialog


def _core():
    from bim3117_freecad import drawings
    return drawings


def _base():
    from . import commands
    return commands


def _selected_drawing(kind):
    try:
        obj = _base()._selected_native_object()
        return obj if getattr(obj, "BIM3117Kind", "") == kind else None
    except Exception:
        return None


def _default_origin(project):
    """Put the front elevation outside all supported authored solids."""
    bounds = []
    for obj in project.Group:
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and getattr(obj, "BIM3117Kind", "") in (
                "WallBody", "Door", "Window", "Slab", "Column", "Beam"):
            bounds.append(shape.BoundBox)
    if not bounds:
        return (0, -1000, 0), 10000
    ymin, ymax = min(b.YMin for b in bounds), max(b.YMax for b in bounds)
    xmin, xmax = min(b.XMin for b in bounds), max(b.XMax for b in bounds)
    return ((xmin + xmax) / 2, ymin - 1000, 0), ymax - ymin + 2000


class CreateDrawingViewCommand:
    view_type = None

    def GetResources(self):
        label = self.view_type or "Drawing View"
        return {"Pixmap": resource_path((self.view_type or "drawing").lower() + ".svg"),
                "MenuText": "Create {} / สร้างมุมมองแบบ".format(label),
                "ToolTip": "Define a plan, section or elevation from committed native geometry; dimensions in mm"}

    def IsActive(self):
        return _base()._has_project()

    def Activated(self):
        base = _base()
        try:
            from .drawing_dialogs import DrawingViewDialog
            project = base._require_project()
            core = _core()
            levels = base._services().list_levels(project)
            selected = base._selected_or_none()
            level = selected if selected in levels else min(levels, key=lambda o: base._mm(o.Elevation), default=None)
            origin, depth = _default_origin(project)
            view_type = self.view_type or "Plan"
            if view_type == "Section":
                origin = (origin[0], origin[1] + depth / 2, origin[2])
            dialog = DrawingViewDialog(levels=levels, initial={
                "name": base._next_name(core.list_views(project), view_type), "view_type": view_type,
                "level": level, "origin_mm": origin, "depth_mm": depth})
            if not run_dialog(dialog):
                return
            view = core.create_view(project, **dialog.values())
        except Exception as error:
            base._report_error("Create Drawing View", error)
            return
        base._focus_object(view)


class CreatePlanCommand(CreateDrawingViewCommand):
    view_type = "Plan"


class CreateSectionCommand(CreateDrawingViewCommand):
    view_type = "Section"


class CreateElevationCommand(CreateDrawingViewCommand):
    view_type = "Elevation"


class CreateDrawingSheetCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("sheet.svg"),
                "MenuText": "Create Sheet / สร้างแผ่นแบบ",
                "ToolTip": "Place one or two drawing views on a native A3 landscape sheet"}

    def IsActive(self):
        return _base()._has_project()

    def Activated(self):
        base = _base()
        try:
            from .drawing_dialogs import DrawingSheetDialog
            project, core = base._require_project(), _core()
            views, sheets = core.list_views(project), core.list_sheets(project)
            if not views:
                raise ValueError("กรุณาใช้ Create Drawing View เพื่อสร้างแปลน รูปตัด หรือรูปด้านก่อน")
            selected = [o for o in Gui.Selection.getSelection() if o in views][:2]
            number = 1
            used = {str(s.Number) for s in sheets}
            while "A{:03d}".format(number) in used:
                number += 1
            dialog = DrawingSheetDialog(views=views, initial={
                "name": base._next_name(sheets, "Drawing Sheet"), "number": "A{:03d}".format(number),
                "views": selected or views[:2], "author": str(project.Author)})
            if not run_dialog(dialog):
                return
            sheet = core.create_sheet(project, **dialog.values())
        except Exception as error:
            base._report_error("Create Sheet", error)
            return
        base._focus_object(sheet)


class DrawingPreviewCommand:
    def GetResources(self):
        return {"Pixmap": resource_path("drawing_preview.svg"),
                "MenuText": "Drawing Preview / เปิดแผ่นแบบ",
                "ToolTip": "Inspect the current model and drawing revisions, update and export SVG/PDF"}

    def IsActive(self):
        return _base()._has_project()

    def Activated(self):
        try:
            from .drawing_preview import show_sheet_preview
            project = _base()._require_project()
            sheets = _core().list_sheets(project)
            if not sheets:
                raise ValueError("กรุณาสร้างแผ่นแบบด้วย Create Sheet ก่อน")
            sheet = _selected_drawing("DrawingSheet") or sheets[0]
            return show_sheet_preview(sheet)
        except Exception as error:
            _base()._report_error("Drawing Preview", error)
            return None


class ExportDrawingPDFCommand(DrawingPreviewCommand):
    format_name = "pdf"

    def GetResources(self):
        return {"Pixmap": resource_path("drawing_export.svg"),
                "MenuText": "Export Drawing {} / ส่งออกแผ่นแบบ".format(self.format_name.upper()),
                "ToolTip": "Export the selected sheet at its authored scale, with revision and file metadata"}

    def Activated(self):
        panel = super().Activated()
        if panel is not None:
            return panel.export(self.format_name)


class ExportDrawingSVGCommand(ExportDrawingPDFCommand):
    format_name = "svg"


def edit_drawing(obj):
    from .drawing_dialogs import DrawingViewDialog, DrawingSheetDialog, view_initial, sheet_initial
    base = _base()
    core = _core()
    if obj.BIM3117Kind == "DrawingView":
        dialog = DrawingViewDialog(initial=view_initial(obj), levels=base._services().list_levels(obj.Project), editing=True)
        operation = core.edit_view
    elif obj.BIM3117Kind == "DrawingSheet":
        dialog = DrawingSheetDialog(initial=sheet_initial(obj), views=core.list_views(obj.Project), editing=True)
        operation = core.edit_sheet
    else:
        raise ValueError("เลือกมุมมองหรือแผ่นแบบที่แก้ไขได้")
    if not run_dialog(dialog):
        return False
    operation(obj, **dialog.values())
    base._focus_object(obj)
    return True


def delete_drawing(obj):
    core = _core()
    operation = core.delete_view if obj.BIM3117Kind == "DrawingView" else core.delete_sheet
    project = obj.Project
    operation(obj)
    _base()._focus_object(project)


def register():
    for name, command in (("BIM3117_CreateDrawingView", CreateDrawingViewCommand()),
                          ("BIM3117_CreatePlan", CreatePlanCommand()),
                          ("BIM3117_CreateSection", CreateSectionCommand()),
                          ("BIM3117_CreateElevation", CreateElevationCommand()),
                          ("BIM3117_CreateSheet", CreateDrawingSheetCommand()),
                          ("BIM3117_DrawingPreview", DrawingPreviewCommand()),
                          ("BIM3117_ExportDrawingPDF", ExportDrawingPDFCommand()),
                          ("BIM3117_ExportDrawingSVG", ExportDrawingSVGCommand())):
        Gui.addCommand(name, command)
