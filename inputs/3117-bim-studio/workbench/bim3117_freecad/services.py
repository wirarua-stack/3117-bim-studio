# SPDX-License-Identifier: GPL-3.0-or-later
"""FreeCAD application commands. Explicit *_mm parameters use host millimetres.

One public mutation creates one native document transaction. Callers must not
wrap these services in another transaction. Property-editor callbacks use the
host transaction and never open their own.
"""
from contextlib import contextmanager

import FreeCAD as App

from .model import (FoundationError, GridProxy, LevelProxy, ProjectProxy, NATIVE_KINDS, kind, mm,
                    number, text, validate_object)
from .building import (WallTypeProxy, WallProxy, WallBodyProxy, DoorProxy, WindowProxy,
                       hosted_doors, hosted_openings, wall_parameters, _reference,
                       validate_opening_proposal)
from .elements import (SlabProxy, ColumnProxy, BeamProxy, boundary_points,
                       gross_solid, slab_solid, join_slabs, expected_solid,
                       slab_edit_solid, member_edit_solid)

_UNCHANGED = object()
_OWNED_TRANSACTIONS = set()


def get_project(doc=None):
    doc = doc or App.ActiveDocument
    if doc is None:
        return None
    projects = [obj for obj in doc.Objects if kind(obj) == "Project"]
    if len(projects) > 1:
        raise FoundationError("This release supports one 3117 project per document")
    return projects[0] if projects else None


def _require(obj, expected, validate=True):
    if kind(obj) != expected or obj.Document is None:
        raise FoundationError(f"Select a 3117 {expected.lower()} in an open document")
    if validate:
        validate_object(obj)


def list_levels(project):
    _require(project, "Project")
    return [obj for obj in project.Group if kind(obj) == "Level"]


def list_grids(project):
    _require(project, "Project")
    return [obj for obj in project.Group if kind(obj) == "Grid"]


def _unique_name(project, object_kind, label, except_obj=None):
    if any(obj is not except_obj and kind(obj) == object_kind and obj.Label == label for obj in project.Group):
        raise FoundationError(f"A {object_kind.lower()} named '{label}' already exists in this project")


def validate_document(doc, check_shapes=False):
    """Validate semantic identity and memberships; optionally evaluate geometry."""
    ids = set()
    projects = []
    for obj in doc.Objects:
        if kind(obj) not in NATIVE_KINDS:
            continue
        validate_object(obj)
        if obj.BIM3117Id in ids:
            raise FoundationError("Duplicate persistent UUID; unsupported raw object copy")
        ids.add(obj.BIM3117Id)
        if kind(obj) == "Project":
            projects.append(obj)
            continue
        if obj not in obj.Project.Group:
            raise FoundationError(f"{obj.Label} is not in its owning project's group")
        if check_shapes and "Shape" in obj.PropertiesList and (obj.Shape.isNull() or not obj.Shape.isValid()):
            raise FoundationError(f"{obj.Label} has invalid geometry")
        if check_shapes and kind(obj) in ("Door", "Window", "WallBody", "Slab", "Column", "Beam") and (not obj.Shape.Solids or obj.Shape.Volume <= 0):
            raise FoundationError(f"{obj.Label} has no positive-volume solid geometry")
        if check_shapes and kind(obj) in ("Slab", "Column", "Beam") and len(obj.Shape.Solids) != 1:
            raise FoundationError(f"{obj.Label} must remain one connected positive-volume solid")
        if check_shapes and obj.ValidationMessage:
            raise FoundationError(f"{obj.Label}: {obj.ValidationMessage}")
    if len(projects) > 1:
        raise FoundationError("Only one 3117 project per document is supported")
    for project in projects:
        for child in project.Group:
            if kind(child) not in NATIVE_KINDS[1:] or child.Project != project:
                raise FoundationError("Project contains an unsupported child or inconsistent parent link")
        for object_kind in ("Level", "Grid", "WallType", "Wall", "Door", "Window", "Slab", "Column", "Beam", "Material", "ElementType"):
            labels = [obj.Label for obj in project.Group if kind(obj) == object_kind]
            if len(labels) != len(set(labels)):
                raise FoundationError(f"Duplicate {object_kind.lower()} names in project")
    return True


@contextmanager
def _transaction(doc, label):
    # App's active transaction detects even an empty open transaction, whereas
    # Document.HasPendingTransaction becomes true only after the first mutation.
    if (doc.Name in _OWNED_TRANSACTIONS or doc.HasPendingTransaction
            or App.getActiveTransaction() is not None):
        raise FoundationError("Finish or cancel the current native transaction before this command")
    if doc.UndoMode == 0:
        doc.UndoMode = 1
    doc.openTransaction(label)
    token = App.getActiveTransaction()
    _OWNED_TRANSACTIONS.add(doc.Name)
    try:
        yield
        validate_document(doc)
        doc.recompute()
        validate_document(doc, check_shapes=True)
        doc.commitTransaction()
    except BaseException:
        doc.abortTransaction()
        # Rebuild derived geometry from the restored parameters. Do not hide the
        # original command exception if a host cleanup also reports a problem.
        try:
            doc.recompute()
        except Exception:
            pass
        raise
    finally:
        _OWNED_TRANSACTIONS.discard(doc.Name)
        # FreeCAD leaves a global marker after some empty commit/abort paths.
        # Close only the marker owned by this command, never another command's.
        if token is not None and App.getActiveTransaction() == token:
            App.closeActiveTransaction()


def _style(obj):
    if not App.GuiUp:
        return
    view = obj.ViewObject
    if kind(obj) == "Project":
        from ui3117.viewproviders import attach_project_view
        attach_project_view(obj)
        return
    if kind(obj) in ("Material", "ElementType", "WallType", "Wall", "WallBody", "Door", "Window", "Slab", "Column", "Beam"):
        from ui3117 import viewproviders
        functions = {"Material": viewproviders.attach_material_view,
                     "ElementType": viewproviders.attach_element_type_view,
                     "WallType": viewproviders.attach_wall_type_view,
                     "Wall": viewproviders.attach_wall_view,
                     "WallBody": viewproviders.attach_wall_body_view,
                     "Door": viewproviders.attach_door_view,
                     "Window": viewproviders.attach_window_view,
                     "Slab": viewproviders.attach_slab_view,
                     "Column": viewproviders.attach_column_view,
                     "Beam": viewproviders.attach_beam_view}
        functions[kind(obj)](obj)
        if kind(obj) in ("WallBody", "Door", "Window", "Slab", "Column", "Beam"):
            view.DisplayMode = "Flat Lines"
            view.ShapeColor = {"WallBody": (0.82, 0.85, 0.88), "Door": (1.0, 0.46, 0.12),
                               "Window": (0.23, 0.65, 0.83), "Slab": (0.72, 0.76, 0.82),
                               "Column": (0.45, 0.64, 0.78), "Beam": (0.54, 0.67, 0.74)}[kind(obj)]
            view.LineColor = (0.12, 0.19, 0.27)
            view.LineWidth = 1.0
        return
    if kind(obj) == "Grid":
        from ui3117.viewproviders import attach_grid_view
        attach_grid_view(obj)
    elif kind(obj) == "Level":
        from ui3117.viewproviders import attach_level_view
        attach_level_view(obj)
    # Assigning the real Python view provider initializes the native Part view
    # modes. Selecting Wireframe before this has no valid enum in FreeCAD 1.1.4.
    view.DisplayMode = "Wireframe"
    view.LineWidth = 1.5 if kind(obj) == "Level" else 2.0
    view.LineColor = (0.38, 0.51, 0.63) if kind(obj) == "Level" else (1.0, 0.46, 0.12)


def _make_level(project, name, elevation_mm, span_x_mm, span_y_mm):
    obj = project.Document.addObject("Part::FeaturePython", "BIM3117_Level")
    LevelProxy(obj, project)
    obj.Label, obj.Elevation = name, elevation_mm
    obj.SpanX, obj.SpanY = span_x_mm, span_y_mm
    project.addObject(obj)
    _style(obj)
    return obj


def create_project(name, project_number="", author="", levels=None, document=None):
    name = text(name, "Project name", required=True)
    project_number, author = text(project_number, "Project number"), text(author, "Author")
    levels = [("L00", 0.0), ("L01", 3000.0)] if levels is None else list(levels)
    levels = [(text(label, "Level name", required=True), number(elevation, "Level elevation"))
              for label, elevation in levels]
    if len({label for label, _ in levels}) != len(levels):
        raise FoundationError("Default level names must be unique")
    if document is not None and get_project(document) is not None:
        raise FoundationError("This document already has a 3117 project")
    doc = document if document is not None else App.newDocument("BIM3117")
    try:
        with _transaction(doc, "3117 Create project"):
            project = doc.addObject("App::DocumentObjectGroupPython", "BIM3117_Project")
            ProjectProxy(project)
            project.Label, project.ProjectNumber, project.Author = name, project_number, author
            if document is None:
                doc.Label = name
            _style(project)
            for label, elevation in levels:
                _make_level(project, label, elevation, 12000.0, 8000.0)
        return project
    except BaseException:
        if document is None:
            App.closeDocument(doc.Name)
        raise


def add_level(project, name, elevation_mm, span_x_mm=12000.0, span_y_mm=8000.0):
    _require(project, "Project")
    name = text(name, "Level name", required=True)
    elevation_mm = number(elevation_mm, "Level elevation")
    span_x_mm = number(span_x_mm, "Span X", positive=True)
    span_y_mm = number(span_y_mm, "Span Y", positive=True)
    _unique_name(project, "Level", name)
    with _transaction(project.Document, "3117 Add level"):
        obj = _make_level(project, name, elevation_mm, span_x_mm, span_y_mm)
    return obj


def _validate_grid_level(project, level):
    if level is not None:
        _require(level, "Level")
        if level.Project != project:
            raise FoundationError("Reference level must belong to this project")


def _set_grid_reference(grid, level):
    grid.Proxy._reference_assignment = True
    try:
        grid.ReferenceLevel = level
        grid.ReferenceLevelId = level.BIM3117Id if level is not None else ""
    finally:
        grid.Proxy._reference_assignment = False


def level_dependents(level):
    _require(level, "Level")
    return [obj for obj in level.Document.Objects
            if (kind(obj) == "Grid" and (obj.ReferenceLevel == level or obj.ReferenceLevelId == level.BIM3117Id))
            or (kind(obj) in ("Wall", "Column") and level.BIM3117Id in (obj.BaseLevelId, obj.TopLevelId))
            or (kind(obj) in ("Slab", "Beam") and obj.LevelId == level.BIM3117Id)
            or (kind(obj) == "DrawingView" and obj.LevelId == level.BIM3117Id)
            or (kind(obj) == "Schedule" and (getattr(obj, "FilterLevel", None) == level
                                               or getattr(obj, "FilterLevelId", "") == level.BIM3117Id))]


def can_delete_level(level):
    return not level_dependents(level)


def delete_level(level):
    """Delete an unreferenced level only; explicitly reassign its elements first."""
    _require(level, "Level")
    dependents = level_dependents(level)
    if dependents:
        labels = ", ".join(obj.Label for obj in dependents)
        raise FoundationError(f"Level is referenced by: {labels}. Reassign or detach them first.")
    document, project, name = level.Document, level.Project, level.Name
    with _transaction(document, "3117 Delete level"):
        project.removeObject(level)
        document.removeObject(name)


def create_grid(project, label, axis="X", position_mm=0.0, length_mm=10000.0,
                bubble_label=None, level=None, offset_mm=0.0):
    _require(project, "Project")
    label = text(label, "Grid name", required=True)
    bubble_label = text(label if bubble_label is None else bubble_label, "Grid bubble label", required=True)
    if axis not in ("X", "Y"):
        raise FoundationError("Grid axis must be X or Y")
    position_mm, length_mm = number(position_mm, "Grid position"), number(length_mm, "Grid length", positive=True)
    offset_mm = number(offset_mm, "Grid elevation offset")
    _validate_grid_level(project, level)
    _unique_name(project, "Grid", label)
    with _transaction(project.Document, "3117 Add grid"):
        obj = project.Document.addObject("Part::FeaturePython", "BIM3117_Grid")
        GridProxy(obj, project)
        obj.Label, obj.Axis, obj.Position, obj.Length = label, axis, position_mm, length_mm
        obj.BubbleLabel, obj.ElevationOffset = bubble_label, offset_mm
        _set_grid_reference(obj, level)
        project.addObject(obj)
        _style(obj)
    return obj


def edit_project(project, name=None, project_number=None, author=None):
    _require(project, "Project")
    values = {}
    for field, value, required in (("Label", name, True), ("ProjectNumber", project_number, False), ("Author", author, False)):
        if value is not None:
            values[field] = text(value, field, required=required)
    with _transaction(project.Document, "3117 Edit project"):
        for field, value in values.items():
            setattr(project, field, value)
        # Document.Label is the container/file title and is not native-undoable.
        # Project.Label is the editable project name owned by this transaction.
    return project


def edit_level(level, name=None, elevation_mm=None, span_x_mm=None, span_y_mm=None):
    _require(level, "Level")
    values = {}
    if name is not None:
        values["Label"] = text(name, "Level name", required=True)
        _unique_name(level.Project, "Level", values["Label"], except_obj=level)
    for field, value, positive in (("Elevation", elevation_mm, False), ("SpanX", span_x_mm, True), ("SpanY", span_y_mm, True)):
        if value is not None:
            values[field] = number(value, field, positive=positive)
    with _transaction(level.Document, "3117 Edit level"):
        for field, value in values.items():
            setattr(level, field, value)
    return level


def edit_grid(grid, label=None, axis=None, position_mm=None, length_mm=None,
              bubble_label=None, level=_UNCHANGED, offset_mm=None):
    # An explicit reference edit is also the recovery path for a broken native
    # link after unsupported raw document mutations.
    _require(grid, "Grid", validate=level is _UNCHANGED)
    values = {}
    if label is not None:
        values["Label"] = text(label, "Grid name", required=True)
        _unique_name(grid.Project, "Grid", values["Label"], except_obj=grid)
    if axis is not None:
        if axis not in ("X", "Y"):
            raise FoundationError("Grid axis must be X or Y")
        values["Axis"] = axis
    for field, value, positive in (("Position", position_mm, False), ("Length", length_mm, True), ("ElevationOffset", offset_mm, False)):
        if value is not None:
            values[field] = number(value, field, positive=positive)
    if bubble_label is not None:
        values["BubbleLabel"] = text(bubble_label, "Grid bubble label", required=True)
    if level is not _UNCHANGED:
        _validate_grid_level(grid.Project, level)
        values["ReferenceLevel"] = level
    with _transaction(grid.Document, "3117 Edit grid"):
        if "ReferenceLevel" in values:
            _set_grid_reference(grid, values.pop("ReferenceLevel"))
        for field, value in values.items():
            setattr(grid, field, value)
    return grid


def _list_kind(project, expected):
    _require(project, "Project")
    return [obj for obj in project.Group if kind(obj) == expected]


def list_wall_types(project):
    return _list_kind(project, "WallType")


def list_walls(project):
    return _list_kind(project, "Wall")


def list_doors(project):
    return _list_kind(project, "Door")


def list_windows(project):
    return _list_kind(project, "Window")


def list_slabs(project):
    return _list_kind(project, "Slab")


def list_columns(project):
    return _list_kind(project, "Column")


def list_beams(project):
    return _list_kind(project, "Beam")


def resolve_authoring_object(obj):
    """Map selectable derived wall solids back to their authored wall instance."""
    if kind(obj) == "WallBody":
        wall = obj.Wall
        if kind(wall) != "Wall" or wall.Body != obj or obj.WallId != wall.BIM3117Id:
            raise FoundationError("Selected wall body has a missing or inconsistent authored wall")
        return wall
    if kind(obj) not in NATIVE_KINDS:
        raise FoundationError("Select a 3117 element")
    return obj


def wall_body(wall):
    _require(wall, "Wall")
    return wall.Body


def _require_in_project(obj, expected, project):
    _require(obj, expected)
    if obj.Project != project or obj.Document != project.Document:
        raise FoundationError(f"The {expected} must belong to this project")


def _set_reference(obj, prop, target):
    setattr(obj, prop, target)
    setattr(obj, prop + "Id", target.BIM3117Id if target is not None else "")


def _sync_openings(wall):
    if wall is None or wall.Body is None:
        return
    doors = [obj for obj in wall.Document.Objects if kind(obj) in ("Door", "Window") and obj.Host == wall]
    wall.Body.Openings = doors
    wall.Body.OpeningIds = [door.BIM3117Id for door in doors]


def _preflight_opening(project, category, label, host, values, existing=None):
    target = _reference(existing, "Host", "Wall") if host is _UNCHANGED else host
    _require(target, "Wall", validate=False)
    if target.Project != project or target.Document != project.Document:
        raise FoundationError("The Wall must belong to this project")
    proposed = {prop: values[prop] if prop in values else mm(existing, prop)
                for prop in ("Offset", "Width", "Height", "Sill")}
    validate_opening_proposal(target, label, category, proposed, existing)


def create_wall_type(project, name, thickness_mm=200.0, material=""):
    _require(project, "Project")
    name = text(name, "Wall type name", required=True)
    thickness_mm = number(thickness_mm, "Wall type thickness", positive=True)
    material = text(material, "Material")
    _unique_name(project, "WallType", name)
    with _transaction(project.Document, "3117 Create wall type"):
        obj = project.Document.addObject("App::FeaturePython", "BIM3117_WallType")
        WallTypeProxy(obj, project)
        obj.Label, obj.Thickness, obj.Material = name, thickness_mm, material
        project.addObject(obj)
        _style(obj)
    return obj


def edit_wall_type(wall_type, name=None, thickness_mm=None, material=None):
    from .catalog import (_type_proposal, _material_link, layer_definitions, preflight,
                          _write_type, _sync_project_instances, effective_material)
    _require(wall_type, "WallType")
    native_material, layers = _material_link(wall_type), layer_definitions(wall_type)
    proposal = _type_proposal(wall_type.Project, wall_type.Label if name is None else name,
                             "Wall", {"Thickness": thickness_mm}, native_material, layers,
                             getattr(wall_type, "Code", ""), wall_type)
    if material is not None:
        material = text(material, "Material")
        if (native_material is not None or layers) and material != effective_material(wall_type):
            raise FoundationError("Material is controlled by the native type assignment; use the catalogue")
    preflight(wall_type.Project, type_overrides={wall_type.BIM3117Id: proposal})
    with _transaction(wall_type.Document, "3117 Edit wall type"):
        _write_type(wall_type, proposal)
        if material is not None and native_material is None and not layers:
            wall_type.Material = material
        _sync_project_instances(wall_type.Project)
    return wall_type


def create_wall(project, name, wall_type, base_level, top_level,
                start_x_mm=0.0, start_y_mm=0.0, end_x_mm=6000.0, end_y_mm=0.0,
                base_offset_mm=0.0, top_offset_mm=0.0):
    _require(project, "Project")
    name = text(name, "Wall name", required=True)
    _unique_name(project, "Wall", name)
    for target, expected in ((wall_type, "WallType"), (base_level, "Level"), (top_level, "Level")):
        _require_in_project(target, expected, project)
    values = {prop: number(value, prop) for prop, value in
              (("StartX", start_x_mm), ("StartY", start_y_mm), ("EndX", end_x_mm),
               ("EndY", end_y_mm), ("BaseOffset", base_offset_mm), ("TopOffset", top_offset_mm))}
    with _transaction(project.Document, "3117 Create wall"):
        wall = project.Document.addObject("App::FeaturePython", "BIM3117_Wall")
        WallProxy(wall, project)
        wall.Label = name
        for prop, target in (("WallType", wall_type), ("BaseLevel", base_level), ("TopLevel", top_level)):
            _set_reference(wall, prop, target)
        for prop, value in values.items():
            setattr(wall, prop, value)
        body = project.Document.addObject("Part::FeaturePython", "BIM3117_WallBody")
        WallBodyProxy(body, project)
        body.Label = name + " · Solid"
        _set_reference(body, "Wall", wall)
        _set_reference(wall, "Body", body)
        project.addObject(wall)
        project.addObject(body)
        _style(wall)
        _style(body)
    return wall


def edit_wall(wall, name=None, wall_type=_UNCHANGED, base_level=_UNCHANGED, top_level=_UNCHANGED,
              start_x_mm=None, start_y_mm=None, end_x_mm=None, end_y_mm=None,
              base_offset_mm=None, top_offset_mm=None):
    from .catalog import edit_instance
    changes = {key: value for key, value in locals().copy().items()
               if key not in ("wall", "edit_instance") and value is not _UNCHANGED
               and (value is not None or key in ("host", "level", "base_level", "top_level", "wall_type"))}
    return edit_instance(wall, changes)


def create_door(project, name, host, offset_mm=1000.0, width_mm=900.0, height_mm=2100.0, sill_mm=0.0):
    _require(project, "Project")
    _require_in_project(host, "Wall", project)
    name = text(name, "Door name", required=True)
    _unique_name(project, "Door", name)
    values = {prop: number(value, prop, positive=positive) for prop, value, positive in
              (("Offset", offset_mm, False), ("Width", width_mm, True), ("Height", height_mm, True), ("Sill", sill_mm, False))}
    _preflight_opening(project, "Door", name, host, values)
    with _transaction(project.Document, "3117 Create door"):
        door = project.Document.addObject("Part::FeaturePython", "BIM3117_Door")
        DoorProxy(door, project)
        door.Label = name
        _set_reference(door, "Host", host)
        for prop, value in values.items():
            setattr(door, prop, value)
        project.addObject(door)
        _sync_openings(host)
        _style(door)
    return door


def edit_door(door, name=None, host=_UNCHANGED, offset_mm=None, width_mm=None, height_mm=None, sill_mm=None):
    from .catalog import edit_instance
    changes = {key: value for key, value in locals().copy().items()
               if key not in ("door", "edit_instance") and value is not _UNCHANGED
               and (value is not None or key in ("host", "level", "base_level", "top_level", "wall_type"))}
    return edit_instance(door, changes)


def wall_type_dependents(wall_type):
    from .catalog import type_dependents
    return type_dependents(wall_type)


def wall_dependents(wall):
    _require(wall, "Wall", validate=False)
    return hosted_openings(wall)


def can_delete_wall_type(wall_type):
    return not wall_type_dependents(wall_type)


def can_delete_wall(wall):
    return not wall_dependents(wall)


def delete_wall_type(wall_type):
    from .catalog import delete_type
    return delete_type(wall_type)


def delete_wall(wall):
    _require(wall, "Wall", validate=False)
    dependents = wall_dependents(wall)
    if dependents:
        raise FoundationError("Wall hosts openings: " + ", ".join(door.Label for door in dependents) + ". Delete or rehost them first.")
    document, project, name = wall.Document, wall.Project, wall.Name
    bodies = [obj for obj in document.Objects if kind(obj) == "WallBody"
              and (obj.Wall == wall or obj.WallId == wall.BIM3117Id)]
    if len(bodies) > 1:
        raise FoundationError("Wall has multiple derived bodies; repair the unsupported model state first")
    with _transaction(document, "3117 Delete wall"):
        for body in bodies:
            project.removeObject(body)
            document.removeObject(body.Name)
        project.removeObject(wall)
        document.removeObject(name)


def delete_door(door):
    _require(door, "Door", validate=False)
    document, project, name = door.Document, door.Project, door.Name
    hosts = [obj for obj in document.Objects if kind(obj) == "Wall"
             and (obj == door.Host or obj.BIM3117Id == door.HostId)]
    with _transaction(document, "3117 Delete door"):
        project.removeObject(door)
        document.removeObject(name)
        for host in hosts:
            _sync_openings(host)


def create_window(project, name, host, offset_mm=1000.0, width_mm=1200.0,
                  height_mm=1200.0, sill_mm=900.0):
    _require(project, "Project")
    _require_in_project(host, "Wall", project)
    name = text(name, "Window name", required=True)
    _unique_name(project, "Window", name)
    values = {prop: number(value, prop, positive=positive) for prop, value, positive in
              (("Offset", offset_mm, False), ("Width", width_mm, True),
               ("Height", height_mm, True), ("Sill", sill_mm, False))}
    _preflight_opening(project, "Window", name, host, values)
    with _transaction(project.Document, "3117 Create window"):
        window = project.Document.addObject("Part::FeaturePython", "BIM3117_Window")
        WindowProxy(window, project)
        window.Label = name
        _set_reference(window, "Host", host)
        for prop, value in values.items():
            setattr(window, prop, value)
        project.addObject(window)
        _sync_openings(host)
        _style(window)
    return window


def edit_window(window, name=None, host=_UNCHANGED, offset_mm=None, width_mm=None,
                height_mm=None, sill_mm=None):
    from .catalog import edit_instance
    changes = {key: value for key, value in locals().copy().items()
               if key not in ("window", "edit_instance") and value is not _UNCHANGED
               and (value is not None or key in ("host", "level", "base_level", "top_level", "wall_type"))}
    return edit_instance(window, changes)


def delete_window(window):
    _require(window, "Window", validate=False)
    document, project, name = window.Document, window.Project, window.Name
    hosts = [obj for obj in document.Objects if kind(obj) == "Wall"
             and (obj == window.Host or obj.BIM3117Id == window.HostId)]
    with _transaction(document, "3117 Delete window"):
        project.removeObject(window)
        document.removeObject(name)
        for host in hosts:
            _sync_openings(host)


def _new_element(project, expected, proxy, name, values, references):
    _require(project, "Project")
    name = text(name, expected + " name", required=True)
    _unique_name(project, expected, name)
    for target in references.values():
        _require_in_project(target, "Level", project)
    with _transaction(project.Document, "3117 Create " + expected.lower()):
        obj = project.Document.addObject("Part::FeaturePython", "BIM3117_" + expected)
        proxy(obj, project)
        obj.Label = name
        for prop, target in references.items():
            _set_reference(obj, prop, target)
        for prop, value in values.items():
            setattr(obj, prop, value)
        project.addObject(obj)
        _style(obj)
    return obj


def _edit_element(obj, expected, name, values, references):
    # Commands also provide an explicit recovery path for missing Level links.
    _require(obj, expected, validate=False)
    if name is not None:
        values["Label"] = text(name, expected + " name", required=True)
        _unique_name(obj.Project, expected, values["Label"], except_obj=obj)
    for target in references.values():
        _require_in_project(target, "Level", obj.Project)
    if expected == "Slab":
        proposed_shape = slab_edit_solid(obj, values, references.get("Level"))
        for member in slab_dependents(obj):
            expected_solid(member, slab_overrides={obj.BIM3117Id: proposed_shape})
    elif expected in ("Column", "Beam"):
        member_edit_solid(obj, values, references)
    with _transaction(obj.Document, "3117 Edit " + expected.lower()):
        for prop, target in references.items():
            _set_reference(obj, prop, target)
        for prop, value in values.items():
            setattr(obj, prop, value)
    return obj


def _numeric_values(items):
    return {prop: number(value, prop, positive=positive)
            for prop, value, positive in items if value is not None}


def _xy(value, label):
    if isinstance(value, (str, bytes)):
        raise FoundationError(label + " must contain exactly X and Y in millimetres")
    try:
        coords = tuple(value)
    except TypeError as error:
        raise FoundationError(label + " must contain exactly X and Y in millimetres") from error
    if len(coords) != 2:
        raise FoundationError(label + " must contain exactly X and Y in millimetres")
    return number(coords[0], label + " X"), number(coords[1], label + " Y")


def create_slab(project, name, level, boundary_mm, thickness_mm=150.0, offset_mm=0.0, material=""):
    points = boundary_points(boundary_mm)
    values = {"Boundary": [App.Vector(x, y, 0) for x, y in points],
              "Thickness": number(thickness_mm, "Slab thickness", positive=True),
              "Offset": number(offset_mm, "Slab top offset"), "Material": text(material, "Material")}
    return _new_element(project, "Slab", SlabProxy, name, values, {"Level": level})


def edit_slab(slab, name=None, level=_UNCHANGED, boundary_mm=None,
              thickness_mm=None, offset_mm=None, material=None):
    from .catalog import edit_instance
    changes = {key: value for key, value in locals().copy().items()
               if key not in ("slab", "edit_instance") and value is not _UNCHANGED
               and (value is not None or key in ("host", "level", "base_level", "top_level", "wall_type"))}
    return edit_instance(slab, changes)


def create_column(project, name, base_level, top_level, x_mm=0.0, y_mm=0.0,
                  width_mm=300.0, depth_mm=300.0, rotation_deg=0.0,
                  base_offset_mm=0.0, top_offset_mm=0.0, material=""):
    values = {prop: number(value, prop, positive=positive) for prop, value, positive in
              (("X", x_mm, False), ("Y", y_mm, False), ("Width", width_mm, True),
               ("Depth", depth_mm, True), ("Rotation", rotation_deg, False),
               ("BaseOffset", base_offset_mm, False), ("TopOffset", top_offset_mm, False))}
    values["Material"] = text(material, "Material")
    return _new_element(project, "Column", ColumnProxy, name, values,
                        {"BaseLevel": base_level, "TopLevel": top_level})


def edit_column(column, name=None, base_level=_UNCHANGED, top_level=_UNCHANGED,
                x_mm=None, y_mm=None, width_mm=None, depth_mm=None, rotation_deg=None,
                base_offset_mm=None, top_offset_mm=None, material=None):
    from .catalog import edit_instance
    changes = {key: value for key, value in locals().copy().items()
               if key not in ("column", "edit_instance") and value is not _UNCHANGED
               and (value is not None or key in ("host", "level", "base_level", "top_level", "wall_type"))}
    return edit_instance(column, changes)


def create_beam(project, name, level, start_mm=(0.0, 0.0), end_mm=(6000.0, 0.0),
                width_mm=300.0, depth_mm=450.0, offset_mm=0.0, material=""):
    sx, sy = _xy(start_mm, "Beam start")
    ex, ey = _xy(end_mm, "Beam end")
    values = {"StartX": sx, "StartY": sy, "EndX": ex, "EndY": ey,
              "Width": number(width_mm, "Beam width", positive=True),
              "Depth": number(depth_mm, "Beam depth", positive=True),
              "Offset": number(offset_mm, "Beam top offset"), "Material": text(material, "Material")}
    return _new_element(project, "Beam", BeamProxy, name, values, {"Level": level})


def edit_beam(beam, name=None, level=_UNCHANGED, start_mm=None, end_mm=None,
              width_mm=None, depth_mm=None, offset_mm=None, material=None):
    from .catalog import edit_instance
    changes = {key: value for key, value in locals().copy().items()
               if key not in ("beam", "edit_instance") and value is not _UNCHANGED
               and (value is not None or key in ("host", "level", "base_level", "top_level", "wall_type"))}
    return edit_instance(beam, changes)


def slab_dependents(slab):
    _require(slab, "Slab", validate=False)
    return [obj for obj in slab.Document.Objects if kind(obj) in ("Column", "Beam")
            and (slab in obj.JoinSlabs or slab.BIM3117Id in obj.JoinSlabIds)]


def can_delete_slab(slab):
    return not slab_dependents(slab)


def _delete_element(obj, expected):
    _require(obj, expected, validate=False)
    document, project, name = obj.Document, obj.Project, obj.Name
    with _transaction(document, "3117 Delete " + expected.lower()):
        project.removeObject(obj)
        document.removeObject(name)


def delete_slab(slab):
    dependents = slab_dependents(slab)
    if dependents:
        raise FoundationError("Slab cuts members: " + ", ".join(obj.Label for obj in dependents)
                              + ". Unjoin them first.")
    _delete_element(slab, "Slab")


def delete_column(column):
    _delete_element(column, "Column")


def delete_beam(beam):
    _delete_element(beam, "Beam")


def _require_join_member(member, validate=True):
    if kind(member) not in ("Column", "Beam"):
        raise FoundationError("Slab-priority joins support only Column or Beam targets")
    _require(member, kind(member), validate=validate)


def join_slab(member, slab):
    """Apply an explicit slab-priority cut; initial overlap is required."""
    _require_join_member(member)
    _require_in_project(slab, "Slab", member.Project)
    slabs = join_slabs(member)
    if slab in slabs:
        raise FoundationError("This Slab is already assigned to the member")
    gross = gross_solid(member)
    overlap = gross.common(slab_solid(slab)).Volume
    if overlap <= max(1e-9, gross.Volume * 1e-12):
        raise FoundationError("Slab and member must have positive solid overlap when creating a join")
    expected_solid(member, extra_slabs=(slab,))
    with _transaction(member.Document, "3117 Join slab"):
        member.JoinSlabs = slabs + [slab]
        member.JoinSlabIds = [item.BIM3117Id for item in member.JoinSlabs]
    return member


def unjoin_slab(member, slab=None):
    """Remove one cutter, or all cutters when omitted (also repairs lost links)."""
    _require_join_member(member, validate=False)
    if slab is not None:
        _require(slab, "Slab", validate=False)
        if slab.Document != member.Document or slab.Project != member.Project:
            raise FoundationError("The Slab must belong to the same project")
        if slab.BIM3117Id not in member.JoinSlabIds and slab not in member.JoinSlabs:
            raise FoundationError("This Slab is not assigned to the member")
        slabs = [item for item in member.JoinSlabs if item != slab]
        identifiers = [identifier for identifier in member.JoinSlabIds if identifier != slab.BIM3117Id]
    else:
        slabs, identifiers = [], []
    with _transaction(member.Document, "3117 Unjoin slab"):
        member.JoinSlabs, member.JoinSlabIds = slabs, identifiers
    return member
