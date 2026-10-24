# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent native Project, Level and Grid objects.

All geometric properties are native FreeCAD quantities in millimetres. No
editable duplicate state is stored in Python. Level outlines and grid axes
are datum geometry, not walls, slabs or IFC building products.
"""
import math
import sys
from uuid import UUID, uuid4

import FreeCAD as App
import Part

from . import SCHEMA_VERSION, __version__

NATIVE_KINDS = ("Project", "Level", "Grid", "WallType", "Wall", "Door", "WallBody",
                "Slab", "Column", "Beam", "Window", "Material", "ElementType")
DOCUMENTATION_KINDS = ("DrawingSet", "DrawingView", "DrawingSheet", "ScheduleSet", "Schedule")


def _service_mutation(obj):
    services = sys.modules.get("bim3117_freecad.services")
    return bool(services and obj.Document.Name in getattr(services, "_OWNED_TRANSACTIONS", ()))


class FoundationError(ValueError):
    """An invalid foundation command or unsupported native model state."""


def number(value, label, positive=False):
    """Validate a numeric millimetre DTO; do not guess units from strings."""
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise FoundationError(f"{label} must be a finite number in millimetres")
    value = float(value)
    if positive and value < 0.001:
        raise FoundationError(f"{label} must be at least 0.001 mm")
    return value


def text(value, label, required=False):
    if not isinstance(value, str):
        raise FoundationError(f"{label} must be text")
    value = value.strip()
    if required and not value:
        raise FoundationError(f"{label} is required")
    return value


def kind(obj):
    return getattr(obj, "BIM3117Kind", "") if obj is not None else ""


def mm(obj, prop):
    value = getattr(obj, prop)
    return float(value.Value if hasattr(value, "Value") else value)


def _property(obj, type_name, name, group, tooltip, default, readonly=False):
    obj.addProperty(type_name, name, group, tooltip)
    setattr(obj, name, default)
    if readonly:
        obj.setEditorMode(name, 1)


def _common(obj, object_kind):
    _property(obj, "App::PropertyString", "BIM3117Id", "3117 Identity", "Persistent element UUID", str(uuid4()), True)
    _property(obj, "App::PropertyInteger", "BIM3117Schema", "3117 Identity", "Native property schema version", SCHEMA_VERSION, True)
    _property(obj, "App::PropertyString", "BIM3117Kind", "3117 Identity", "3117 semantic category", object_kind, True)
    _property(obj, "App::PropertyString", "BIM3117Version", "3117 Identity", "Workbench version creating this object", __version__, True)
    # Output flag avoids marking the object for another recompute when reporting
    # a validation result. This remains visible and is not an authoritative input.
    obj.addProperty("App::PropertyString", "ValidationMessage", "3117 Status", "Last validation error", 8)
    obj.setEditorMode("ValidationMessage", 1)


def _link_project(obj, project):
    # The project Group owns its children. A normal reverse Link would create a
    # recompute dependency cycle. LinkHidden is serialized but omitted from the
    # dependency graph; it is a parent reference, not a driving geometric input.
    _property(obj, "App::PropertyLinkHidden", "Project", "3117 Identity", "Owning project", project, True)


def validate_object(obj):
    expected = kind(obj)
    if expected not in NATIVE_KINDS + DOCUMENTATION_KINDS:
        raise FoundationError("Object is not a 3117 element")
    if expected in DOCUMENTATION_KINDS:
        if expected in ("ScheduleSet", "Schedule"):
            from .schedules import validate_schedule_object
            validate_schedule_object(obj)
        else:
            from .drawings import validate_drawing_object
            validate_drawing_object(obj)
        return
    try:
        if str(UUID(obj.BIM3117Id)) != obj.BIM3117Id:
            raise ValueError("Non-canonical UUID")
    except (ValueError, AttributeError, TypeError) as exc:
        raise FoundationError("Element UUID is missing or invalid") from exc
    if obj.BIM3117Schema != SCHEMA_VERSION:
        raise FoundationError("Unsupported native schema; migration is required")
    if text(obj.Label, "Name", required=True) != obj.Label:
        raise FoundationError("Names must not have leading or trailing spaces")
    if expected == "Project":
        text(obj.ProjectNumber, "Project number")
        text(obj.Author, "Author")
        return
    if kind(obj.Project) != "Project" or obj.Project.Document != obj.Document:
        raise FoundationError("An element must belong to a project in the same document")
    if expected != "WallBody" and any(other != obj and kind(other) == expected and other.Label == obj.Label for other in obj.Project.Group):
        raise FoundationError(f"A {expected.lower()} named '{obj.Label}' already exists in this project")
    if expected in ("Material", "ElementType"):
        from .catalog import validate_catalog_object
        validate_catalog_object(obj)
        return
    if expected in ("WallType", "Wall", "Door", "Window", "WallBody"):
        from .building import validate_building_object
        validate_building_object(obj)
        return
    if expected in ("Slab", "Column", "Beam"):
        from .elements import validate_element_object
        validate_element_object(obj)
        return
    if obj.Placement.Base.Length > 1e-8 or abs(obj.Placement.Rotation.Angle) > 1e-10:
        raise FoundationError("Datum Placement must remain identity; edit datum parameters instead")
    if expected == "Level":
        number(mm(obj, "Elevation"), "Elevation")
        number(mm(obj, "SpanX"), "Span X", positive=True)
        number(mm(obj, "SpanY"), "Span Y", positive=True)
    else:
        if str(obj.Axis) not in ("X", "Y"):
            raise FoundationError("Grid axis must be X or Y")
        number(mm(obj, "Position"), "Grid position")
        number(mm(obj, "Length"), "Grid length", positive=True)
        number(mm(obj, "BubbleRadius"), "Grid bubble radius", positive=True)
        text(obj.BubbleLabel, "Grid bubble label", required=True)
        number(mm(obj, "ElevationOffset"), "Grid elevation offset")
        level = obj.ReferenceLevel
        if level is not None:
            if kind(level) != "Level" or level.Document != obj.Document or level.Project != obj.Project:
                raise FoundationError("Grid reference level must belong to the same project")
            if obj.ReferenceLevelId != level.BIM3117Id:
                raise FoundationError("Grid reference level identity is inconsistent; use Edit Selected to reassign it")
        elif obj.ReferenceLevelId:
            raise FoundationError("Grid reference level is missing; use Edit Selected to reassign or explicitly detach it")
        number(grid_elevation(obj), "Effective grid elevation")


def grid_elevation(obj):
    if obj.ReferenceLevel is None and getattr(obj, "ReferenceLevelId", ""):
        raise FoundationError("Grid reference level is missing")
    return (mm(obj.ReferenceLevel, "Elevation") if obj.ReferenceLevel is not None else 0.0) + mm(obj, "ElevationOffset")


def grid_endpoints(obj):
    half = mm(obj, "Length") / 2.0
    position, elevation = mm(obj, "Position"), grid_elevation(obj)
    if str(obj.Axis) == "X":
        return App.Vector(-half, position, elevation), App.Vector(half, position, elevation)
    return App.Vector(position, -half, elevation), App.Vector(position, half, elevation)


class _BaseProxy:
    """Callbacks never open transactions or call document.recompute()."""
    editable = ("Label",)
    reference_properties = {}
    list_reference_properties = ()

    def _start(self, obj):
        self._ready, self._restoring_value = False, False
        self._reference_assignment = False
        self._before = {}
        obj.Proxy = self

    def _finish(self, obj):
        self._ready = True

    def onBeforeChangeLabel(self, obj, label):
        # This dedicated FreeCAD hook can return the replacement label before
        # the setter commits it. It avoids recursive Label restoration, which
        # otherwise triggers FreeCAD's auto-numbering of an object's old name.
        if (not getattr(self, "_ready", False) or obj.Document.Transacting or _service_mutation(obj)
                or getattr(obj.Document, "Restoring", False)):
            return label
        try:
            cleaned = text(label, "Name", required=True)
            if kind(obj) not in ("Project", "WallBody") and obj.Project is not None:
                if any(other != obj and kind(other) == kind(obj) and other.Label == cleaned
                       for other in obj.Project.Group):
                    raise FoundationError(f"A {kind(obj).lower()} named '{cleaned}' already exists")
            return cleaned
        except FoundationError as error:
            App.Console.PrintError(f"3117: {error}\n")
            return obj.Label

    def onBeforeChange(self, obj, prop):
        if (not getattr(self, "_ready", False) or prop not in self.editable
                or obj.Document.Transacting or _service_mutation(obj) or getattr(obj.Document, "Restoring", False)):
            return
        value = getattr(obj, prop)
        if hasattr(value, "Value"):
            value = float(value.Value)
        elif prop == "Axis":
            value = str(value)
        elif prop == "Placement":
            value = App.Placement(value)
        elif prop == "Boundary":
            value = [App.Vector(point) for point in value]
        elif isinstance(value, list):
            value = list(value)
        self._before[prop] = value

    def onChanged(self, obj, prop):
        if (not getattr(self, "_ready", False) or getattr(self, "_restoring_value", False)
                or prop not in self.editable or obj.Document.Transacting or _service_mutation(obj)
                or getattr(obj.Document, "Restoring", False)
                or getattr(self, "_reference_assignment", False)):
            return
        previous_reference_id = None
        if prop == "LayerMaterials" and kind(obj) in ("WallType", "ElementType"):
            if len(getattr(obj, prop)) < len(self._before.get(prop, [])):
                from .catalog import invalidate_catalog_dependents
                message = "Layer material reference missing; repair the ordered layers in the catalogue"
                obj.ValidationMessage = message
                invalidate_catalog_dependents(obj, message)
                return
        if prop in self.reference_properties:
            from .building import clear_calculated_shape, invalidate_related
            if getattr(obj, prop) is None:
                message = f"{prop} is missing; reassign it with Edit Selected"
                clear_calculated_shape(obj, message)
                invalidate_related(obj, message)
                return
            # Structural references are changed atomically by services, including
            # expected IDs and the two wall bodies when a door is rehosted.
            if prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, self._before[prop])
                finally:
                    self._restoring_value = False
            App.Console.PrintError(f"3117: use Edit Selected to change {prop}\n")
            return
        if prop in self.list_reference_properties:
            # FreeCAD also updates a LinkList when a native target is deleted.
            # Keep the saved IDs so a missing cutter can never silently become
            # an unjoined gross member. Commands update both lists atomically.
            from .building import clear_calculated_shape, invalidate_related
            before = self._before.get(prop, [])
            current = list(getattr(obj, prop))
            if len(current) >= len(before) and prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, before)
                finally:
                    self._restoring_value = False
                App.Console.PrintError("3117: use Join/Unjoin Slab to change slab cutters\n")
            else:
                message = "Slab join reference missing; use Unjoin Slab to repair"
                clear_calculated_shape(obj, message)
                invalidate_related(obj, message)
            return
        if prop == "Openings":
            from .building import clear_calculated_shape
            clear_calculated_shape(obj, "Opening membership changed outside a supported opening command")
            return
        if prop == "ReferenceLevel":
            if obj.ReferenceLevel is None and obj.ReferenceLevelId:
                # Clearing can mean a deleted native target. Retain its semantic
                # identity so this cannot silently become a project-origin grid.
                # Explicit detachment is provided by the Edit Grid command.
                obj.ValidationMessage = "Reference level missing; reassign or explicitly detach with Edit Selected"
                return
            previous_reference_id = obj.ReferenceLevelId
            if kind(obj.ReferenceLevel) == "Level":
                obj.ReferenceLevelId = obj.ReferenceLevel.BIM3117Id
        try:
            from .catalog import validate_raw_edit
            validate_raw_edit(obj, prop)
            validate_object(obj)
            if kind(obj) in ("WallType", "ElementType", "Material"):
                from .catalog import preflight
                preflight(obj.Project)
                if kind(obj) == "Material" and prop == "Label":
                    # FreeCAD Label changes alone do not touch the dependency
                    # graph. Native type/material display outputs must refresh.
                    obj.touch()
            elif kind(obj) in ("Level", "Wall", "Door", "Window", "Slab", "Column", "Beam"):
                from .building import validate_affected_edit
                validate_affected_edit(obj)
        except FoundationError as error:
            # FreeCAD's onBeforeChange cannot cancel an edit. Restore an invalid
            # native Property Editor edit within the host's existing transaction;
            # service callers pre-validate and never depend on this UI safeguard.
            if prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, self._before[prop])
                    if previous_reference_id is not None:
                        obj.ReferenceLevelId = previous_reference_id
                finally:
                    self._restoring_value = False
            App.Console.PrintError(f"3117: {error}\n")

    def onDocumentRestored(self, obj):
        # All authoritative state lives in native properties. Do not regenerate
        # identities, re-add existing properties, or overwrite user view settings.
        self._before = {}
        self._restoring_value = False
        self._reference_assignment = False
        self._ready = True
        for name in ("BIM3117Id", "BIM3117Schema", "BIM3117Kind", "BIM3117Version", "Project", "ReferenceLevelId", "ValidationMessage"):
            if name in obj.PropertiesList:
                obj.setEditorMode(name, 1)
        if "Placement" in obj.PropertiesList:
            obj.setEditorMode("Placement", 1)
        for name in self.reference_properties:
            if name in obj.PropertiesList:
                obj.setEditorMode(name, 1)
                obj.setEditorMode(name + "Id", 1)
        if kind(obj) == "Wall":
            for name in ("Length", "Height", "Thickness"):
                obj.setEditorMode(name, 1)
        if kind(obj) == "WallBody":
            for name in ("Label", "Openings", "OpeningIds", "GrossVolume", "NetVolume",
                         "OpeningVolume", "GrossSideArea", "NetSideArea"):
                obj.setEditorMode(name, 1)
        for name in ("PlanArea", "Perimeter", "GrossVolume", "NetVolume", "JoinVolume", "SectionArea",
                     "JoinSlabs", "JoinSlabIds"):
            if name in obj.PropertiesList:
                obj.setEditorMode(name, 1)
        if kind(obj) in ("Column", "Beam"):
            obj.setEditorMode("Height" if kind(obj) == "Column" else "Length", 1)
        from .catalog import restore_catalog_modes
        restore_catalog_modes(obj)

    def dumps(self):
        return {"schema": SCHEMA_VERSION}

    def loads(self, state):
        self._before = {}
        self._ready = False
        self._restoring_value = False
        self._reference_assignment = False

    def __getstate__(self):
        return self.dumps()

    def __setstate__(self, state):
        self.loads(state)

    def execute(self, obj):
        try:
            from .catalog import sync_instance
            sync_instance(obj)
            validate_object(obj)
            self.build(obj)
            obj.ValidationMessage = ""
        except Exception as error:
            obj.ValidationMessage = str(error)
            if "Shape" in obj.PropertiesList:
                obj.Shape = Part.Shape()
            if kind(obj) in ("Level", "WallType", "Wall", "Door", "Window", "WallBody", "Slab", "Column", "Beam", "Material", "ElementType"):
                from .building import clear_calculated_shape, invalidate_related
                clear_calculated_shape(obj, str(error))
                invalidate_related(obj, str(error))
            raise


class ProjectProxy(_BaseProxy):
    editable = ("Label", "ProjectNumber", "Author")

    def __init__(self, obj):
        self._start(obj)
        _common(obj, "Project")
        _property(obj, "App::PropertyString", "ProjectNumber", "Project", "Project reference number", "")
        _property(obj, "App::PropertyString", "Author", "Project", "Project author or organisation", "")
        self._finish(obj)

    def build(self, obj):
        pass


class LevelProxy(_BaseProxy):
    editable = ("Label", "Elevation", "SpanX", "SpanY", "Placement")

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Level")
        _link_project(obj, project)
        _property(obj, "App::PropertyDistance", "Elevation", "Level", "Level elevation relative to project origin", 0.0)
        _property(obj, "App::PropertyLength", "SpanX", "Datum display", "Datum outline extent along X", 12000.0)
        _property(obj, "App::PropertyLength", "SpanY", "Datum display", "Datum outline extent along Y", 8000.0)
        obj.setEditorMode("Placement", 1)
        self._finish(obj)

    def build(self, obj):
        x, y, z = mm(obj, "SpanX") / 2, mm(obj, "SpanY") / 2, mm(obj, "Elevation")
        points = [App.Vector(-x, -y, z), App.Vector(x, -y, z), App.Vector(x, y, z),
                  App.Vector(-x, y, z), App.Vector(-x, -y, z)]
        obj.Shape = Part.makePolygon(points)


class GridProxy(_BaseProxy):
    editable = ("Label", "Axis", "Position", "Length", "BubbleRadius", "BubbleLabel",
                "ReferenceLevel", "ElevationOffset", "Placement")

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Grid")
        _link_project(obj, project)
        obj.addProperty("App::PropertyEnumeration", "Axis", "Grid", "Axis direction; X is parallel X, Y parallel Y")
        obj.Axis = ["X", "Y"]
        _property(obj, "App::PropertyDistance", "Position", "Grid", "Perpendicular distance from project origin", 0.0)
        _property(obj, "App::PropertyLength", "Length", "Grid", "Grid axis length, centered on project origin", 10000.0)
        _property(obj, "App::PropertyString", "BubbleLabel", "Grid", "Text identifier of this grid axis", "A")
        _property(obj, "App::PropertyLength", "BubbleRadius", "Datum display", "Radius of endpoint datum bubbles", 250.0)
        _property(obj, "App::PropertyLink", "ReferenceLevel", "Grid", "Level driving grid elevation; use Edit Selected to explicitly detach to the project origin", None)
        _property(obj, "App::PropertyString", "ReferenceLevelId", "3117 Identity", "Expected level UUID; retained if its native link is broken", "", True)
        _property(obj, "App::PropertyDistance", "ElevationOffset", "Grid", "Offset above reference level, or project origin", 0.0)
        obj.setEditorMode("Placement", 1)
        self._finish(obj)

    def build(self, obj):
        start, end = grid_endpoints(obj)
        radius = mm(obj, "BubbleRadius")
        obj.Shape = Part.makeCompound([Part.makeLine(start, end),
                                      Part.makeCircle(radius, start), Part.makeCircle(radius, end)])
