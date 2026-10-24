# SPDX-License-Identifier: GPL-3.0-or-later
"""Workbench definition in a normal module, independent of loader exec scope."""

import FreeCADGui

from . import resource_path


class BIM3117Workbench(FreeCADGui.Workbench):
    MenuText = "3117 BIM Studio"
    ToolTip = "Building BIM authoring, drawings, quantities and IFC4 exchange"
    Icon = resource_path("workbench.svg")

    def Initialize(self):
        from . import commands
        commands.register()
        foundation = [
            "BIM3117_CreateProject", "BIM3117_AddLevel",
            "BIM3117_CreateGrid",
        ]
        architecture = ["BIM3117_CreateWallType", "BIM3117_CreateWall", "BIM3117_CreateDoor", "BIM3117_CreateWindow"]
        structure = ["BIM3117_CreateSlab", "BIM3117_CreateColumn", "BIM3117_CreateBeam"]
        joins = ["BIM3117_JoinSlab", "BIM3117_UnjoinSlab"]
        edit = ["BIM3117_EditSelected", "BIM3117_DeleteSelected"]
        exchange = ["BIM3117_Quantities", "BIM3117_ExportIFC"]
        drawings = ["BIM3117_CreateDrawingView", "BIM3117_CreateSheet", "BIM3117_DrawingPreview"]
        self.appendToolbar("3117 Foundation", foundation)
        self.appendToolbar("3117 Architecture", architecture + ["Separator"] + edit + [
            "Separator", "Std_Undo", "Std_Redo", "Std_ViewFitAll",
        ])
        self.appendToolbar("3117 Quantities & Exchange", ["BIM3117_Catalogue", "BIM3117_Schedules"] + exchange)
        self.appendToolbar("3117 Structure", structure + ["Separator"] + joins)
        self.appendToolbar("3117 Drawings", drawings)
        self.appendMenu("3117 BIM", foundation + ["Separator"] + architecture + ["Separator"] + structure +
                        ["Separator"] + joins + ["Separator"] + edit + [
            "Separator", "Std_Undo", "Std_Redo",
            "Separator", *exchange, "Separator", "BIM3117_HostInfo",
        ])
        self.appendMenu(["3117 BIM", "Drawings & Sheets / แบบและแผ่นแบบ"], [
            "BIM3117_CreatePlan", "BIM3117_CreateSection", "BIM3117_CreateElevation",
            "Separator", "BIM3117_CreateSheet", "BIM3117_DrawingPreview",
            "Separator", "BIM3117_ExportDrawingSVG", "BIM3117_ExportDrawingPDF",
        ])
        self.appendMenu(["3117 BIM", "Types, Materials & Schedules / ชนิด วัสดุ ตาราง"], [
            "BIM3117_Catalogue", "BIM3117_CreateMaterial", "BIM3117_CreateType",
            "Separator", "BIM3117_AssignType", "BIM3117_DetachType",
            "Separator", "BIM3117_Schedules", "BIM3117_CreateSchedule",
        ])

    def Activated(self):
        # Workbench selection never creates a project or changes user settings.
        return

    def Deactivated(self):
        return

    def ContextMenu(self, recipient):
        if recipient in ("Tree", "View"):
            from .commands import EditSelectedCommand, DeleteSelectedCommand, _selected_native_object
            if EditSelectedCommand().IsActive():
                commands = ["BIM3117_EditSelected"]
                if DeleteSelectedCommand().IsActive():
                    commands.append("BIM3117_DeleteSelected")
                if _selected_native_object().BIM3117Kind in ("Slab", "Column", "Beam"):
                    commands += ["Separator", "BIM3117_JoinSlab", "BIM3117_UnjoinSlab"]
                if _selected_native_object().BIM3117Kind == "DrawingSheet":
                    commands += ["Separator", "BIM3117_DrawingPreview", "BIM3117_ExportDrawingPDF"]
                if _selected_native_object().BIM3117Kind in ("Wall", "Slab", "Column", "Beam", "Door", "Window"):
                    commands += ["Separator", "BIM3117_AssignType"]
                    if _selected_native_object().BIM3117Kind != "Wall":
                        commands.append("BIM3117_DetachType")
                if _selected_native_object().BIM3117Kind == "Schedule":
                    commands += ["Separator", "BIM3117_Schedules"]
                self.appendContextMenu("3117 BIM", commands)

    def GetClassName(self):
        return "Gui::PythonWorkbench"
