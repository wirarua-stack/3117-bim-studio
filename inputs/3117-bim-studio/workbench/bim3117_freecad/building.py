# SPDX-License-Identifier: GPL-3.0-or-later
"""Native straight walls and hosted rectangular door/window openings.

The authored Wall has no shape. Its derived WallBody depends on the Wall and
the opening objects, while each opening depends on its authored Wall. This is an
acyclic dependency graph; the hidden Wall.Body backlink is never a driver.
All input dimensions are native millimetres. OCCT solids are constructed in
world coordinates, leaving the native object Placement at identity.
"""
import math

import FreeCAD as App
import Part

from .model import (FoundationError, _BaseProxy, _common, _link_project,
                    _property, kind, mm, number, text)

BUILDING_KINDS = ("WallType", "Wall", "Door", "Window", "WallBody")
TOLERANCE_MM = 1e-7


def _reference(obj, name, expected, required=True):
    target = getattr(obj, name)
    identifier = getattr(obj, name + "Id", "")
    if target is None:
        if required or identifier:
            raise FoundationError(f"{obj.Label}: {name} is missing; reassign it with Edit Selected")
        return None
    if (kind(target) != expected or target.Document != obj.Document
            or target.Project != obj.Project):
        raise FoundationError(f"{obj.Label}: {name} must be a {expected} in the same project")
    if identifier != target.BIM3117Id:
        raise FoundationError(f"{obj.Label}: {name} identity is inconsistent; reassign it with Edit Selected")
    return target


def _add_reference(obj, name, expected, hidden=False):
    _property(obj, "App::PropertyLinkHidden" if hidden else "App::PropertyLink",
              name, "3117 References", f"{expected} reference; change through Edit Selected", None, True)
    _property(obj, "App::PropertyString", name + "Id", "3117 Identity",
              f"Expected {name} UUID; retained when its link is broken", "", True)


def _output(obj, type_name, name, tooltip):
    obj.addProperty(type_name, name, "3117 Calculated", tooltip, 8)
    obj.setEditorMode(name, 1)


def _identity_placement(obj):
    if "Placement" in obj.PropertiesList:
        if obj.Placement.Base.Length > 1e-8 or abs(obj.Placement.Rotation.Angle) > 1e-10:
            raise FoundationError("Placement must remain identity; edit the authored element parameters")


def wall_parameters(wall):
    """Return geometry inputs, without reading derived shapes or output values."""
    wall_type = _reference(wall, "WallType", "WallType")
    base = _reference(wall, "BaseLevel", "Level")
    top = _reference(wall, "TopLevel", "Level")
    from .catalog import effective_dimension
    thickness = number(effective_dimension(wall_type, "Thickness"), "Wall type thickness", positive=True)
    sx = number(mm(wall, "StartX"), "Start X")
    sy = number(mm(wall, "StartY"), "Start Y")
    ex = number(mm(wall, "EndX"), "End X")
    ey = number(mm(wall, "EndY"), "End Y")
    length = number(math.hypot(ex - sx, ey - sy), "Wall axis length", positive=True)
    z = number(mm(base, "Elevation"), "Base level elevation") + number(mm(wall, "BaseOffset"), "Base offset")
    upper = number(mm(top, "Elevation"), "Top level elevation") + number(mm(wall, "TopOffset"), "Top offset")
    height = number(upper - z, "Effective wall height", positive=True)
    return {"start_x": sx, "start_y": sy, "ux": (ex - sx) / length,
            "uy": (ey - sy) / length, "length": length, "thickness": thickness,
            "base_z": z, "height": height}


def hosted_doors(wall):
    """Actual semantic children; never infer membership from the body cache."""
    return [obj for obj in wall.Document.Objects if kind(obj) == "Door"
            and (obj.Host == wall or obj.HostId == wall.BIM3117Id)]


def hosted_openings(wall):
    """All semantic Door and Window children, including broken saved links."""
    return [obj for obj in wall.Document.Objects if kind(obj) in ("Door", "Window")
            and (obj.Host == wall or obj.HostId == wall.BIM3117Id)]


def door_parameters(door, wall_inputs=None):
    from .catalog import effective_dimension
    host = _reference(door, "Host", "Wall")
    inputs = wall_parameters(host) if wall_inputs is None else wall_inputs
    category = kind(door)
    if category not in ("Door", "Window"):
        raise FoundationError("Only a Door or Window can define a wall opening")
    return _opening_values({prop: effective_dimension(door, prop) for prop in ("Offset", "Width", "Height", "Sill")},
                           inputs, door.Label, category)


def _opening_values(values, inputs, label, category):
    """Shared read-only bounds validation for saved and proposed openings."""
    offset = number(values["Offset"], category + " offset")
    width = number(values["Width"], category + " width", positive=True)
    height = number(values["Height"], category + " height", positive=True)
    sill = number(values["Sill"], category + " sill")
    if offset < 0 or sill < 0:
        raise FoundationError(f"{label}: offset and sill must be zero or positive")
    if offset + width > inputs["length"] + TOLERANCE_MM:
        raise FoundationError(f"{label}: opening extends beyond the wall axis")
    if sill + height > inputs["height"] + TOLERANCE_MM:
        raise FoundationError(f"{label}: opening extends above the wall top")
    return {"offset": offset, "width": width, "height": height, "sill": sill}


def _openings_overlap(first, second):
    x_overlap = min(first["offset"] + first["width"], second["offset"] + second["width"]) - max(first["offset"], second["offset"])
    z_overlap = min(first["sill"] + first["height"], second["sill"] + second["height"]) - max(first["sill"], second["sill"])
    return x_overlap > TOLERANCE_MM and z_overlap > TOLERANCE_MM


def validate_opening_proposal(host, label, category, values, existing=None):
    """Preflight ephemeral command values without touching native history.

    FreeCAD discards Redo as soon as a transaction first changes the document;
    aborting that transaction restores properties, but cannot restore Redo.
    These predicates are also used by the final native validation gate.
    """
    inputs = wall_parameters(host)
    proposal = _opening_values(values, inputs, label, category)
    rectangles = []
    for other in hosted_openings(host):
        if other == existing:
            continue
        current = door_parameters(other, inputs)
        if _openings_overlap(proposal, current):
            raise FoundationError(f"{label}: opening overlaps {other.Label}")
        for previous, previous_values in rectangles:
            if _openings_overlap(current, previous_values):
                raise FoundationError(f"{other.Label}: opening overlaps {previous.Label}")
        rectangles.append((other, current))
    opening_area = proposal["width"] * proposal["height"] + math.fsum(
        rectangle["width"] * rectangle["height"] for _, rectangle in rectangles)
    if inputs["length"] * inputs["height"] - opening_area <= 0:
        raise FoundationError(f"{host.Label}: openings must leave positive wall volume")


def window_parameters(window, wall_inputs=None):
    if kind(window) != "Window":
        raise FoundationError("Select a 3117 window")
    return door_parameters(window, wall_inputs)


def validate_openings(wall):
    inputs = wall_parameters(wall)
    doors = hosted_openings(wall)
    rectangles = []
    for door in doors:
        values = door_parameters(door, inputs)
        for other, previous in rectangles:
            if _openings_overlap(values, previous):
                raise FoundationError(f"{door.Label}: opening overlaps {other.Label}")
        rectangles.append((door, values))
    return inputs, rectangles


def validate_building_object(obj):
    expected = kind(obj)
    _identity_placement(obj)
    if expected == "WallType":
        from .catalog import validate_catalog_object
        validate_catalog_object(obj)
    elif expected == "Wall":
        wall_parameters(obj)
        body = _reference(obj, "Body", "WallBody")
        if body.Wall != obj or body.WallId != obj.BIM3117Id:
            raise FoundationError(f"{obj.Label}: derived wall body does not refer to its authored wall")
        bodies = [candidate for candidate in obj.Document.Objects
                  if kind(candidate) == "WallBody" and candidate.Wall == obj]
        if len(bodies) != 1 or bodies[0] != body:
            raise FoundationError(f"{obj.Label}: exactly one derived wall body is required")
        validate_openings(obj)
    elif expected in ("Door", "Window"):
        host = _reference(obj, "Host", "Wall")
        door_parameters(obj)
        validate_openings(host)
    elif expected == "WallBody":
        wall = _reference(obj, "Wall", "Wall")
        if wall.Body != obj or wall.BodyId != obj.BIM3117Id:
            raise FoundationError(f"{obj.Label}: wall body is orphaned")
        expected_doors = hosted_openings(wall)
        if (any(item is None for item in obj.Openings)
                or len(obj.Openings) != len(set(item.Name for item in obj.Openings))
                or {item.Name for item in obj.Openings} != {item.Name for item in expected_doors}
                or list(obj.OpeningIds) != [item.BIM3117Id for item in obj.Openings]):
            raise FoundationError(f"{wall.Label}: opening membership is inconsistent; use the supported Door/Window commands")
        for door in obj.Openings:
            if kind(door) not in ("Door", "Window") or door.Project != obj.Project or door.Host != wall:
                raise FoundationError(f"{wall.Label}: opening belongs to another wall or project")
        validate_openings(wall)


def validate_affected_edit(obj):
    """Reject invalid native numeric Property Editor edits before recomputation.

    The command service suppresses this immediate guard because a command may
    change several inputs at once. Its whole-document gate validates the final
    state and rolls back the transaction instead.
    """
    expected = kind(obj)
    if expected == "Level":
        walls = [wall for wall in obj.Document.Objects if kind(wall) == "Wall"
                 and (wall.BaseLevel == obj or wall.TopLevel == obj)]
    elif expected == "WallType":
        walls = [wall for wall in obj.Document.Objects if kind(wall) == "Wall" and wall.WallType == obj]
    elif expected == "Wall":
        walls = [obj]
    elif expected in ("Door", "Window"):
        walls = [obj.Host] if obj.Host is not None else []
    else:
        walls = []
    for wall in walls:
        validate_openings(wall)
    if expected in ("Level", "Slab", "Column", "Beam"):
        from .elements import validate_affected_elements
        validate_affected_elements(obj)


def _box(inputs, x, y, z, length, depth, height):
    """A prism in wall-local coordinates, encoded as world-coordinate geometry."""
    ux, uy = inputs["ux"], inputs["uy"]
    nx, ny = -uy, ux

    def point(a, b):
        return App.Vector(inputs["start_x"] + ux * a + nx * b,
                          inputs["start_y"] + uy * a + ny * b,
                          inputs["base_z"] + z)

    corners = [point(x, y), point(x + length, y), point(x + length, y + depth),
               point(x, y + depth), point(x, y)]
    return Part.Face(Part.makePolygon(corners)).extrude(App.Vector(0, 0, height))


def opening_solid(door, padded=False):
    inputs = wall_parameters(_reference(door, "Host", "Wall"))
    values = door_parameters(door, inputs)
    padding = max(0.001, inputs["thickness"] * 1e-6) if padded else 0.0
    return _box(inputs, values["offset"], -padding, values["sill"],
                values["width"], inputs["thickness"] + 2 * padding, values["height"])


def window_frame_solid(window):
    """Four non-overlapping generic frame bars; no glazing or sash geometry."""
    inputs = wall_parameters(_reference(window, "Host", "Wall"))
    values = window_parameters(window, inputs)
    x, z, w, h = values["offset"], values["sill"], values["width"], values["height"]
    frame, depth = min(50.0, w / 4.0, h / 4.0), inputs["thickness"]
    parts = [_box(inputs, x, 0, z, frame, depth, h),
             _box(inputs, x + w - frame, 0, z, frame, depth, h),
             _box(inputs, x + frame, 0, z, w - 2 * frame, depth, frame),
             _box(inputs, x + frame, 0, z + h - frame, w - 2 * frame, depth, frame)]
    shape = Part.makeCompound(parts)
    _valid_solid(shape, window.Label)
    return shape


def _valid_solid(shape, label):
    if shape.isNull() or not shape.isValid() or not shape.Solids or shape.Volume <= 0:
        raise FoundationError(f"{label}: OCCT did not produce valid positive-volume solid geometry")


def clear_calculated_shape(obj, reason):
    if "Shape" in obj.PropertiesList:
        obj.Shape = Part.Shape()
    outputs = {"Wall": ("Length", "Height", "Thickness"),
               "WallBody": ("GrossVolume", "NetVolume", "OpeningVolume", "GrossSideArea", "NetSideArea"),
               "Slab": ("PlanArea", "Perimeter", "GrossVolume", "NetVolume"),
               "Column": ("Height", "SectionArea", "GrossVolume", "NetVolume", "JoinVolume"),
               "Beam": ("Length", "SectionArea", "GrossVolume", "NetVolume", "JoinVolume")}
    for name in outputs.get(kind(obj), ()):
        setattr(obj, name, 0.0)
    obj.ValidationMessage = reason


def invalidate_related(obj, reason):
    """Clear dependent display solids when unsupported native edits break links."""
    expected = kind(obj)
    if expected in ("Material", "ElementType"):
        from .catalog import invalidate_catalog_dependents
        invalidate_catalog_dependents(obj, reason)
        return
    if expected == "Level":
        walls = [wall for wall in obj.Document.Objects if kind(wall) == "Wall"
                 and obj.BIM3117Id in (wall.BaseLevelId, wall.TopLevelId)]
    elif expected == "WallType":
        walls = [wall for wall in obj.Document.Objects if kind(wall) == "Wall"
                 and wall.WallTypeId == obj.BIM3117Id]
    elif expected == "Wall":
        walls = [obj]
    elif expected in ("Door", "Window"):
        walls = [wall for wall in obj.Document.Objects if kind(wall) == "Wall"
                 and wall.BIM3117Id == obj.HostId]
    else:
        walls = []
    for wall in walls:
        clear_calculated_shape(wall, reason)
        for candidate in obj.Document.Objects:
            if ((kind(candidate) in ("Door", "Window") and candidate.HostId == wall.BIM3117Id)
                    or (kind(candidate) == "WallBody" and candidate.WallId == wall.BIM3117Id)):
                clear_calculated_shape(candidate, reason)
    if expected in ("Level", "Slab", "Column", "Beam"):
        from .elements import invalidate_element_dependents
        invalidate_element_dependents(obj, reason)


class WallTypeProxy(_BaseProxy):
    editable = ("Label", "Thickness", "Material", "Code", "MaterialRef", "LayerMaterials",
                "LayerMaterialIds", "LayerThicknesses", "LayerRoles")
    reference_properties = {"MaterialRef": "Material"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "WallType")
        _link_project(obj, project)
        _property(obj, "App::PropertyLength", "Thickness", "Wall Type", "Uniform wall thickness", 200.0)
        _property(obj, "App::PropertyString", "Material", "Wall Type", "Legacy text or native material description", "")
        from .catalog import _add_catalog_properties
        _add_catalog_properties(obj)
        self._finish(obj)

    def build(self, obj):
        from .catalog import sync_type
        sync_type(obj)


class WallProxy(_BaseProxy):
    editable = ("Label", "StartX", "StartY", "EndX", "EndY", "BaseOffset", "TopOffset",
                "WallType", "BaseLevel", "TopLevel", "Body")
    reference_properties = {"WallType": "WallType", "BaseLevel": "Level", "TopLevel": "Level", "Body": "WallBody"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Wall")
        _link_project(obj, project)
        for prop, expected in (("WallType", "WallType"), ("BaseLevel", "Level"), ("TopLevel", "Level")):
            _add_reference(obj, prop, expected)
        _add_reference(obj, "Body", "WallBody", hidden=True)
        for prop, value in (("StartX", 0.0), ("StartY", 0.0), ("EndX", 6000.0),
                            ("EndY", 0.0), ("BaseOffset", 0.0), ("TopOffset", 0.0)):
            _property(obj, "App::PropertyDistance", prop, "Wall Instance", "Millimetres relative to project coordinates/level", value)
        for prop in ("Length", "Height", "Thickness"):
            _output(obj, "App::PropertyLength", prop, "Calculated from the axis, type and level references")
        self._finish(obj)

    def build(self, obj):
        values = wall_parameters(obj)
        obj.Length, obj.Height, obj.Thickness = values["length"], values["height"], values["thickness"]


class DoorProxy(_BaseProxy):
    editable = ("Label", "Host", "Offset", "Width", "Height", "Sill", "Placement", "ElementType", "Material")
    reference_properties = {"Host": "Wall", "ElementType": "ElementType"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Door")
        _link_project(obj, project)
        _add_reference(obj, "Host", "Wall")
        _property(obj, "App::PropertyDistance", "Offset", "Door Instance", "Distance from wall start to opening's first jamb", 1000.0)
        _property(obj, "App::PropertyLength", "Width", "Door Instance", "Overall opening width; the frame is a generic representation", 900.0)
        _property(obj, "App::PropertyLength", "Height", "Door Instance", "Overall opening height", 2100.0)
        _property(obj, "App::PropertyDistance", "Sill", "Door Instance", "Opening sill above the effective wall base", 0.0)
        from .catalog import initialize_instance
        initialize_instance(obj)
        obj.setEditorMode("Placement", 1)
        self._finish(obj)

    def build(self, obj):
        inputs = wall_parameters(obj.Host)
        door = door_parameters(obj, inputs)
        frame = min(50.0, door["width"] / 4.0, door["height"] / 4.0)
        depth = inputs["thickness"]
        parts = [
            _box(inputs, door["offset"], 0, door["sill"], frame, depth, door["height"] - frame),
            _box(inputs, door["offset"] + door["width"] - frame, 0, door["sill"], frame, depth, door["height"] - frame),
            _box(inputs, door["offset"], 0, door["sill"] + door["height"] - frame, door["width"], depth, frame),
        ]
        shape = Part.makeCompound(parts)
        _valid_solid(shape, obj.Label)
        obj.Shape = shape


class WindowProxy(_BaseProxy):
    editable = ("Label", "Host", "Offset", "Width", "Height", "Sill", "Placement", "ElementType", "Material")
    reference_properties = {"Host": "Wall", "ElementType": "ElementType"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Window")
        _link_project(obj, project)
        _add_reference(obj, "Host", "Wall")
        _property(obj, "App::PropertyDistance", "Offset", "Window Instance", "Distance from wall start to opening's first jamb", 1000.0)
        _property(obj, "App::PropertyLength", "Width", "Window Instance", "Overall opening width; generic four-bar frame", 1200.0)
        _property(obj, "App::PropertyLength", "Height", "Window Instance", "Overall opening height", 1200.0)
        _property(obj, "App::PropertyDistance", "Sill", "Window Instance", "Opening sill above the effective wall base", 900.0)
        from .catalog import initialize_instance
        initialize_instance(obj)
        obj.setEditorMode("Placement", 1)
        self._finish(obj)

    def build(self, obj):
        obj.Shape = window_frame_solid(obj)


class WallBodyProxy(_BaseProxy):
    editable = ("Placement", "Wall", "Openings")
    reference_properties = {"Wall": "Wall"}

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "WallBody")
        _link_project(obj, project)
        _add_reference(obj, "Wall", "Wall")
        _property(obj, "App::PropertyLinkList", "Openings", "3117 References", "Managed hosted Door/Window openings; change with authoring commands", [], True)
        _property(obj, "App::PropertyStringList", "OpeningIds", "3117 Identity", "Expected hosted opening UUIDs", [], True)
        for prop in ("GrossVolume", "NetVolume", "OpeningVolume"):
            _output(obj, "App::PropertyVolume", prop, "Derived solid volume; native unit mm^3")
        for prop in ("GrossSideArea", "NetSideArea"):
            _output(obj, "App::PropertyArea", prop, "One wall side, excluding joins and material layers; native unit mm^2")
        obj.setEditorMode("Placement", 1)
        obj.setEditorMode("Label", 1)
        self._finish(obj)

    def build(self, obj):
        values, rectangles = validate_openings(obj.Wall)
        shape = _box(values, 0, 0, 0, values["length"], values["thickness"], values["height"])
        gross_volume = shape.Volume
        gross_area = values["length"] * values["height"]
        expected_opening_area = 0.0
        for door, rectangle in rectangles:
            shape = shape.cut(opening_solid(door, padded=True))
            expected_opening_area += rectangle["width"] * rectangle["height"]
        shape = shape.removeSplitter()
        _valid_solid(shape, obj.Wall.Label)
        expected_volume = (gross_area - expected_opening_area) * values["thickness"]
        if abs(shape.Volume - expected_volume) > max(0.001, gross_volume * 1e-8):
            raise FoundationError(f"{obj.Wall.Label}: cut solid volume does not agree with its opening definitions")
        obj.Shape = shape
        obj.GrossVolume, obj.NetVolume = gross_volume, shape.Volume
        obj.OpeningVolume = gross_volume - shape.Volume
        obj.GrossSideArea, obj.NetSideArea = gross_area, shape.Volume / values["thickness"]
