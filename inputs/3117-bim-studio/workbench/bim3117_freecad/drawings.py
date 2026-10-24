# SPDX-License-Identifier: GPL-3.0-or-later
"""Native drawing definitions and read-only solid-derived documentation.

FCStd owns View/Sheet parameters, not a second editable drawing model. Model
content identity excludes these documentation objects; a separate drawing hash
tracks view settings, annotations and sheet placement. Rendering creates no
native geometry/cache objects and never writes revision stamps into the source.
"""
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID

import FreeCAD as App

from .model import (DOCUMENTATION_KINDS, FoundationError, _BaseProxy, _common,
                    _link_project, _property, grid_elevation, kind, mm, number, text)
from . import services

DRAWING_SCHEMA = 1
DRAWING_REVISION_RULE = "3117.native-documentation-definitions.sha256.v1"
DIRECTIONS = {"+X": (1.0, 0.0, 0.0), "+Y": (0.0, 1.0, 0.0),
              "-X": (-1.0, 0.0, 0.0), "-Y": (0.0, -1.0, 0.0)}
_UNCHANGED = object()


def _plain_text(value, label, required=False, limit=160):
    value = text(value, label, required=required)
    if len(value) > limit or any(ord(c) < 32 for c in value):
        raise FoundationError(f"{label} must be one line of at most {limit} characters")
    return value


def _boolean(value, label):
    if not isinstance(value, bool):
        raise FoundationError(f"{label} must be true or false")
    return value


def _scale(value):
    value = number(value, "Scale denominator", positive=True)
    if value != int(value) or not 1 <= value <= 1000:
        raise FoundationError("Scale denominator must be an integer from 1 to 1000")
    return int(value)


def _origin(value):
    try:
        values = list(value)
    except TypeError as error:
        raise FoundationError("View origin must contain three millimetre coordinates") from error
    if len(values) != 3:
        raise FoundationError("View origin must contain three millimetre coordinates")
    return tuple(number(v, "View origin") for v in values)


def _require_project(project):
    services._require(project, "Project")
    if services.get_project(project.Document) != project:
        raise FoundationError("The drawing must belong to the document's 3117 project")
    return project


def _idle(project):
    _require_project(project)
    doc = project.Document
    if (doc.HasPendingTransaction or App.getActiveTransaction() is not None
            or doc.Transacting or getattr(doc, "Restoring", False)):
        raise FoundationError("Finish or cancel the current transaction before this drawing command")
    return doc


def get_drawing_set(project):
    _require_project(project)
    groups = [obj for obj in project.Document.Objects
              if kind(obj) == "DrawingSet" and getattr(obj, "Project", None) == project]
    if len(groups) > 1:
        raise FoundationError("Only one 3117 drawing set per project is supported")
    return groups[0] if groups else None


def list_views(project):
    group = get_drawing_set(project)
    return [obj for obj in group.Group if kind(obj) == "DrawingView"] if group else []


def list_sheets(project):
    group = get_drawing_set(project)
    return [obj for obj in group.Group if kind(obj) == "DrawingSheet"] if group else []


def _unique(project, category, label, except_obj=None):
    for obj in project.Document.Objects:
        if (obj != except_obj and kind(obj) == category and getattr(obj, "Project", None) == project
                and obj.Label == label):
            raise FoundationError(f"A {category} named '{label}' already exists")


def _unique_sheet_number(project, value, except_obj=None):
    if any(obj != except_obj and obj.Number == value for obj in list_sheets(project)):
        raise FoundationError(f"Sheet number '{value}' already exists in this project")


def _view_values(project, *, view_type, level, bottom_offset_mm, cut_offset_mm, top_offset_mm,
                 origin_mm, direction, depth_mm, scale_denominator, show_dimensions, show_tags,
                 show_grid, show_levels):
    if view_type not in ("Plan", "Section", "Elevation"):
        raise FoundationError("View type must be Plan, Section or Elevation")
    if direction not in DIRECTIONS:
        raise FoundationError("View direction must be +X, +Y, -X or -Y, looking into the model")
    if view_type == "Plan":
        if kind(level) != "Level" or level.Document != project.Document or level.Project != project:
            raise FoundationError("A Plan requires a Level in the same project")
        services._require(level, "Level")
    elif level is not None:
        raise FoundationError("Section/Elevation use an origin plane; they must not reference a Plan Level")
    bottom = number(bottom_offset_mm, "Plan bottom offset")
    cut = number(cut_offset_mm, "Plan cut offset")
    top = number(top_offset_mm, "Plan top offset")
    if cut - bottom < 0.001 or top - cut < 0.001:
        raise FoundationError("Plan range must satisfy Bottom < Cut < Top with at least 0.001 mm separation")
    origin = _origin(origin_mm)
    # Plan origin is fixed to the project's XY origin. Its height is driven by
    # Level + CutOffset; vertical views use the explicit 3D origin plane.
    if view_type == "Plan":
        origin = (0.0, 0.0, 0.0)
        direction = "+Y"
    return {"view_type": view_type, "level": level, "bottom_offset_mm": bottom,
            "cut_offset_mm": cut, "top_offset_mm": top, "origin_mm": origin,
            "direction": direction, "depth_mm": number(depth_mm, "View depth", positive=True),
            "scale_denominator": _scale(scale_denominator),
            "show_dimensions": _boolean(show_dimensions, "Show dimensions"),
            "show_tags": _boolean(show_tags, "Show tags"),
            "show_grid": _boolean(show_grid, "Show grid"),
            "show_levels": _boolean(show_levels, "Show levels")}


def _raw_view_values(view):
    return dict(view_type=str(view.ViewType), level=view.Level,
                bottom_offset_mm=mm(view, "BottomOffset"), cut_offset_mm=mm(view, "CutOffset"),
                top_offset_mm=mm(view, "TopOffset"), origin_mm=(view.Origin.x, view.Origin.y, view.Origin.z),
                direction=str(view.Direction), depth_mm=mm(view, "Depth"),
                scale_denominator=int(view.ScaleDenominator), show_dimensions=bool(view.ShowDimensions),
                show_tags=bool(view.ShowTags), show_grid=bool(view.ShowGrid), show_levels=bool(view.ShowLevels))


def _view_def(view):
    values = _raw_view_values(view)
    level = values.pop("level")
    name = values.pop("direction")
    values.update(id=str(view.BIM3117Id), name=str(view.Label), level_id=str(view.LevelId),
                  level_elevation_mm=mm(level, "Elevation") if level is not None else 0.0,
                  direction=list(DIRECTIONS[name]), direction_name=name)
    values["origin_mm"] = list(values["origin_mm"])
    return values


def _definition_hash(view):
    definition = _view_def(view)
    # Level elevation is model content, not an authored drawing override.
    definition.pop("level_elevation_mm")
    return definition


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _identity(obj):
    if kind(obj) not in ("DrawingSet", "DrawingView", "DrawingSheet") or obj.Document is None:
        raise FoundationError("Select a 3117 drawing object in an open document")
    try:
        if str(UUID(obj.BIM3117Id)) != obj.BIM3117Id:
            raise ValueError("Non-canonical UUID")
    except (ValueError, TypeError, AttributeError) as error:
        raise FoundationError("Drawing UUID is missing or invalid") from error
    if obj.BIM3117Schema != 1 or obj.DrawingSchema != DRAWING_SCHEMA:
        raise FoundationError("Unsupported drawing schema; migration is required")
    _plain_text(obj.Label, "Drawing name", required=True)
    project = getattr(obj, "Project", None)
    _require_project(project)
    if obj.Document != project.Document or obj.ProjectId != project.BIM3117Id:
        raise FoundationError("Drawing project link or identity is inconsistent")
    ids = [str(getattr(item, "BIM3117Id", "")) for item in obj.Document.Objects
           if getattr(item, "BIM3117Id", "")]
    if len(ids) != len(set(ids)):
        raise FoundationError("Duplicate persistent UUID in the document")
    _unique(project, kind(obj), obj.Label, obj)
    return project


def _view_links(project, views, expected_ids=None):
    try:
        views = list(views)
    except TypeError as error:
        raise FoundationError("A sheet requires a list of one or two views") from error
    if not 1 <= len(views) <= 2:
        raise FoundationError("A3 landscape sheets support one or two views")
    ids = []
    for view in views:
        if (kind(view) != "DrawingView" or view.Document != project.Document
                or getattr(view, "Project", None) != project):
            raise FoundationError("Sheet views must be DrawingViews in the same project")
        validate_drawing_object(view)
        ids.append(str(view.BIM3117Id))
    if len(set(ids)) != len(ids):
        raise FoundationError("A view can appear only once on the same sheet")
    if expected_ids is not None and ids != list(expected_ids):
        raise FoundationError("A sheet view is missing or its identity/order changed; use Edit Selected to repair")
    return views


def validate_drawing_object(obj):
    project = _identity(obj)
    category = kind(obj)
    group = get_drawing_set(project)
    if category == "DrawingSet":
        if group != obj:
            raise FoundationError("Drawing set membership is inconsistent")
        if any(kind(child) not in ("DrawingView", "DrawingSheet")
               or getattr(child, "Project", None) != project for child in obj.Group):
            raise FoundationError("Drawing set contains an unsupported child or a foreign project object")
        return True
    if group is None or obj not in group.Group:
        raise FoundationError("Drawing object must belong to its project's drawing set")
    if category == "DrawingView":
        values = _view_values(project, **_raw_view_values(obj))
        expected = values["level"].BIM3117Id if values["level"] is not None else ""
        if str(obj.LevelId) != expected:
            raise FoundationError("Plan Level is missing or its identity changed; use Edit Selected to repair")
        if str(obj.ViewType) == "Plan" and obj.Origin.Length > 1e-8:
            raise FoundationError("Plan XY origin is fixed to the project origin")
    else:
        _plain_text(obj.Number, "Sheet number", required=True, limit=32)
        _plain_text(obj.Issue, "Sheet issue", limit=40)
        _plain_text(obj.Author, "Sheet author", limit=100)
        if obj.Paper != "A3" or obj.Orientation != "Landscape":
            raise FoundationError("This release supports A3 landscape sheets only")
        _unique_sheet_number(project, str(obj.Number), obj)
        _view_links(project, obj.Views, obj.ViewIds)
    return True


def _style(obj):
    if not App.GuiUp:
        return
    from ui3117 import viewproviders
    names = {"DrawingSet": "attach_drawing_set_view", "DrawingView": "attach_drawing_view",
             "DrawingSheet": "attach_drawing_sheet_view"}
    callback = getattr(viewproviders, names[kind(obj)], None)
    if callback is not None:
        callback(obj)


class _DrawingProxy(_BaseProxy):
    """Native callbacks validate definitions without building persistent caches."""
    reference_names = ()

    def onBeforeChangeLabel(self, obj, label):
        if (not getattr(self, "_ready", False) or obj.Document.Transacting
                or obj.Document.Name in services._OWNED_TRANSACTIONS or getattr(obj.Document, "Restoring", False)):
            return label
        try:
            cleaned = _plain_text(label, "Drawing name", required=True)
            _unique(obj.Project, kind(obj), cleaned, obj)
            return cleaned
        except FoundationError as error:
            App.Console.PrintError(f"3117: {error}\n")
            return obj.Label

    def onBeforeChange(self, obj, prop):
        super().onBeforeChange(obj, prop)
        if prop == "Origin" and prop in getattr(self, "_before", {}):
            self._before[prop] = App.Vector(obj.Origin)

    def onChanged(self, obj, prop):
        if (not getattr(self, "_ready", False) or getattr(self, "_restoring_value", False)
                or prop not in self.editable or obj.Document.Transacting
                or obj.Document.Name in services._OWNED_TRANSACTIONS
                or getattr(obj.Document, "Restoring", False)):
            return
        if prop in self.reference_names:
            current = getattr(obj, prop)
            prior = self._before.get(prop)
            # Native target deletion must retain expected IDs and show a broken
            # reference. Never silently make a missing view/level optional.
            if current is None or (isinstance(current, list) and prior is not None and len(current) < len(prior)):
                obj.ValidationMessage = f"{prop} reference missing; use Edit Selected to repair"
                return
            if prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, prior)
                finally:
                    self._restoring_value = False
            App.Console.PrintError(f"3117: use Edit Selected to change {prop}\n")
            return
        try:
            validate_drawing_object(obj)
        except FoundationError as error:
            if prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, self._before[prop])
                finally:
                    self._restoring_value = False
            App.Console.PrintError(f"3117: {error}\n")

    def execute(self, obj):
        # A broken drawing definition must block that drawing's publication, not
        # stop editing or exporting an otherwise valid building model.
        try:
            validate_drawing_object(obj)
            obj.ValidationMessage = ""
        except Exception as error:
            obj.ValidationMessage = str(error)

    def onDocumentRestored(self, obj):
        super().onDocumentRestored(obj)
        for name in ("DrawingSchema", "ProjectId", "LevelId", "Views", "ViewIds", "Paper", "Orientation"):
            if name in obj.PropertiesList:
                obj.setEditorMode(name, 1)
        if "Level" in obj.PropertiesList:
            obj.setEditorMode("Level", 1)
        _style(obj)

    def build(self, obj):
        pass


def _drawing_common(obj, category, project):
    _common(obj, category)
    _link_project(obj, project)
    _property(obj, "App::PropertyString", "ProjectId", "3117 Identity", "Expected owning project UUID", project.BIM3117Id, True)
    _property(obj, "App::PropertyInteger", "DrawingSchema", "3117 Identity", "Drawing definition schema", DRAWING_SCHEMA, True)


class DrawingSetProxy(_DrawingProxy):
    editable = ("Label",)

    def __init__(self, obj, project):
        self._start(obj)
        _drawing_common(obj, "DrawingSet", project)
        self._finish(obj)


class DrawingViewProxy(_DrawingProxy):
    editable = ("Label", "ViewType", "Level", "BottomOffset", "CutOffset", "TopOffset", "Origin",
                "Direction", "Depth", "ScaleDenominator", "ShowDimensions", "ShowTags", "ShowGrid", "ShowLevels")
    reference_names = ("Level",)

    def __init__(self, obj, project):
        self._start(obj)
        _drawing_common(obj, "DrawingView", project)
        obj.addProperty("App::PropertyEnumeration", "ViewType", "Drawing", "Orthographic drawing type")
        obj.ViewType = ["Plan", "Section", "Elevation"]
        _property(obj, "App::PropertyLink", "Level", "Plan range", "Plan reference Level; change with Edit Selected", None, True)
        _property(obj, "App::PropertyString", "LevelId", "3117 Identity", "Expected Plan Level UUID", "", True)
        for name, default in (("BottomOffset", -200.0), ("CutOffset", 1200.0), ("TopOffset", 2700.0)):
            _property(obj, "App::PropertyDistance", name, "Plan range", "Offset above Plan Level in mm", default)
        _property(obj, "App::PropertyVector", "Origin", "Vertical view", "Plane origin; direction points from viewer into model", App.Vector(0, 0, 0))
        obj.addProperty("App::PropertyEnumeration", "Direction", "Vertical view", "Direction from viewer into the model")
        obj.Direction = list(DIRECTIONS)
        obj.Direction = "+Y"
        _property(obj, "App::PropertyLength", "Depth", "Vertical view", "Clipping depth behind the origin plane", 10000.0)
        _property(obj, "App::PropertyInteger", "ScaleDenominator", "Drawing", "Explicit scale 1:N; never silently fitted", 50)
        for name in ("ShowDimensions", "ShowTags", "ShowGrid", "ShowLevels"):
            _property(obj, "App::PropertyBool", name, "Annotations", "Derived associative annotation; no manual numeric override", True)
        self._finish(obj)


class DrawingSheetProxy(_DrawingProxy):
    editable = ("Label", "Number", "Issue", "Author", "Views")
    reference_names = ("Views",)

    def __init__(self, obj, project):
        self._start(obj)
        _drawing_common(obj, "DrawingSheet", project)
        for name in ("Number", "Issue", "Author"):
            _property(obj, "App::PropertyString", name, "Sheet", "Sheet title block field", "")
        _property(obj, "App::PropertyString", "Paper", "Sheet", "Paper size", "A3", True)
        _property(obj, "App::PropertyString", "Orientation", "Sheet", "Paper orientation", "Landscape", True)
        _property(obj, "App::PropertyLinkList", "Views", "Sheet", "One or two views in left-to-right order; use Edit Selected", [], True)
        _property(obj, "App::PropertyStringList", "ViewIds", "3117 Identity", "Expected view UUIDs, retained when links are broken", [], True)
        self._finish(obj)


def _make_set(project):
    group = get_drawing_set(project)
    if group is None:
        group = project.Document.addObject("App::DocumentObjectGroupPython", "BIM3117_Drawings")
        DrawingSetProxy(group, project)
        group.Label = "3117 Drawings"
        _style(group)
    return group


def _assign_view(view, values):
    view.ViewType = values["view_type"]
    view.Level = values["level"]
    view.LevelId = values["level"].BIM3117Id if values["level"] is not None else ""
    view.Origin = App.Vector(*values["origin_mm"])
    view.Direction = values["direction"]
    for key, prop in (("bottom_offset_mm", "BottomOffset"), ("cut_offset_mm", "CutOffset"),
                      ("top_offset_mm", "TopOffset"), ("depth_mm", "Depth"),
                      ("scale_denominator", "ScaleDenominator"), ("show_dimensions", "ShowDimensions"),
                      ("show_tags", "ShowTags"), ("show_grid", "ShowGrid"), ("show_levels", "ShowLevels")):
        setattr(view, prop, values[key])


def create_view(project, name, view_type="Plan", level=None, bottom_offset_mm=-200.0,
                cut_offset_mm=1200.0, top_offset_mm=2700.0, origin_mm=(0.0, 0.0, 0.0),
                direction="+Y", depth_mm=10000.0, scale_denominator=50, show_dimensions=True,
                show_tags=True, show_grid=True, show_levels=True):
    doc = _idle(project)
    name = _plain_text(name, "View name", required=True)
    _unique(project, "DrawingView", name)
    values = _view_values(project, view_type=view_type, level=level, bottom_offset_mm=bottom_offset_mm,
                          cut_offset_mm=cut_offset_mm, top_offset_mm=top_offset_mm, origin_mm=origin_mm,
                          direction=direction, depth_mm=depth_mm, scale_denominator=scale_denominator,
                          show_dimensions=show_dimensions, show_tags=show_tags, show_grid=show_grid,
                          show_levels=show_levels)
    with services._transaction(doc, "3117 Create drawing view"):
        group = _make_set(project)
        view = doc.addObject("App::FeaturePython", "BIM3117_DrawingView")
        DrawingViewProxy(view, project)
        view.Label = name
        _assign_view(view, values)
        group.addObject(view)
        _style(view)
        validate_drawing_object(view)
    return view


def edit_view(view, name=None, view_type=None, level=_UNCHANGED, bottom_offset_mm=None,
              cut_offset_mm=None, top_offset_mm=None, origin_mm=None, direction=None, depth_mm=None,
              scale_denominator=None, show_dimensions=None, show_tags=None, show_grid=None, show_levels=None):
    if kind(view) != "DrawingView":
        raise FoundationError("Select a 3117 DrawingView")
    project = _identity(view)
    doc = _idle(project)
    label = _plain_text(view.Label if name is None else name, "View name", required=True)
    _unique(project, "DrawingView", label, view)
    values = _raw_view_values(view)
    for key, value in (("view_type", view_type), ("bottom_offset_mm", bottom_offset_mm),
                       ("cut_offset_mm", cut_offset_mm), ("top_offset_mm", top_offset_mm),
                       ("origin_mm", origin_mm), ("direction", direction), ("depth_mm", depth_mm),
                       ("scale_denominator", scale_denominator), ("show_dimensions", show_dimensions),
                       ("show_tags", show_tags), ("show_grid", show_grid), ("show_levels", show_levels)):
        if value is not None:
            values[key] = value
    if level is not _UNCHANGED:
        values["level"] = level
    if values["view_type"] != "Plan":
        values["level"] = None
    values = _view_values(project, **values)
    with services._transaction(doc, "3117 Edit drawing view"):
        view.Label = label
        _assign_view(view, values)
        validate_drawing_object(view)
    return view


def create_sheet(project, name, number, views, issue="P01", author=""):
    doc = _idle(project)
    name = _plain_text(name, "Sheet name", required=True)
    number = _plain_text(number, "Sheet number", required=True, limit=32)
    issue = _plain_text(issue, "Sheet issue", limit=40)
    author = _plain_text(author, "Sheet author", limit=100)
    _unique(project, "DrawingSheet", name)
    _unique_sheet_number(project, number)
    views = _view_links(project, views)
    with services._transaction(doc, "3117 Create drawing sheet"):
        group = _make_set(project)
        sheet = doc.addObject("App::FeaturePython", "BIM3117_DrawingSheet")
        DrawingSheetProxy(sheet, project)
        sheet.Label, sheet.Number, sheet.Issue, sheet.Author = name, number, issue, author
        sheet.Views, sheet.ViewIds = views, [view.BIM3117Id for view in views]
        group.addObject(sheet)
        _style(sheet)
        validate_drawing_object(sheet)
    return sheet


def edit_sheet(sheet, name=None, number=None, views=None, issue=None, author=None):
    if kind(sheet) != "DrawingSheet":
        raise FoundationError("Select a 3117 DrawingSheet")
    project = _identity(sheet)
    doc = _idle(project)
    label = _plain_text(sheet.Label if name is None else name, "Sheet name", required=True)
    number = _plain_text(sheet.Number if number is None else number, "Sheet number", required=True, limit=32)
    issue = _plain_text(sheet.Issue if issue is None else issue, "Sheet issue", limit=40)
    author = _plain_text(sheet.Author if author is None else author, "Sheet author", limit=100)
    _unique(project, "DrawingSheet", label, sheet)
    _unique_sheet_number(project, number, sheet)
    selected = _view_links(project, sheet.Views if views is None else views,
                           sheet.ViewIds if views is None else None)
    with services._transaction(doc, "3117 Edit drawing sheet"):
        sheet.Label, sheet.Number, sheet.Issue, sheet.Author = label, number, issue, author
        sheet.Views, sheet.ViewIds = selected, [view.BIM3117Id for view in selected]
        validate_drawing_object(sheet)
    return sheet


def view_dependents(view):
    project = _identity(view)
    return [sheet for sheet in list_sheets(project)
            if view in sheet.Views or view.BIM3117Id in sheet.ViewIds]


def delete_view(view):
    if kind(view) != "DrawingView":
        raise FoundationError("Select a 3117 DrawingView")
    project = _identity(view)
    doc = _idle(project)
    dependents = view_dependents(view)
    if dependents:
        raise FoundationError("View is placed on sheets: " + ", ".join(item.Label for item in dependents))
    group, name = get_drawing_set(project), view.Name
    with services._transaction(doc, "3117 Delete drawing view"):
        group.removeObject(view)
        doc.removeObject(name)


def delete_sheet(sheet):
    if kind(sheet) != "DrawingSheet":
        raise FoundationError("Select a 3117 DrawingSheet")
    project = _identity(sheet)
    doc = _idle(project)
    group, name = get_drawing_set(project), sheet.Name
    with services._transaction(doc, "3117 Delete drawing sheet"):
        group.removeObject(sheet)
        doc.removeObject(name)


def _sheet_definition(sheet):
    return {"id": str(sheet.BIM3117Id), "name": str(sheet.Label), "number": str(sheet.Number),
            "issue": str(sheet.Issue), "author": str(sheet.Author), "paper": str(sheet.Paper),
            "orientation": str(sheet.Orientation), "view_ids": list(sheet.ViewIds)}


def sheet_state(sheet):
    """Read the two content identities without HLR or an authored transaction."""
    validate_drawing_object(sheet)
    if kind(sheet) != "DrawingSheet":
        raise FoundationError("Select a 3117 DrawingSheet")
    from . import snapshot
    project = sheet.Project
    snapshot._ready(project, recompute=False)
    model_revision = snapshot._revision(snapshot._authored(project), snapshot._coverage(project.Document))
    drawing_revision = _hash({"rule": DRAWING_REVISION_RULE, "sheet": _sheet_definition(sheet),
                              "views": [_definition_hash(view) for view in sheet.Views]})
    return {"model_revision": model_revision, "drawing_revision": drawing_revision}


def _datum_rows(project):
    return ({"levels": [{"id": str(obj.BIM3117Id), "name": str(obj.Label),
                          "elevation_mm": mm(obj, "Elevation")} for obj in services.list_levels(project)],
             "grids": [{"id": str(obj.BIM3117Id), "name": str(obj.Label), "label": str(obj.BubbleLabel),
                         "axis": str(obj.Axis), "position_mm": mm(obj, "Position"),
                         "length_mm": mm(obj, "Length"), "elevation_mm": grid_elevation(obj)}
                        for obj in services.list_grids(project)]})


def _captured_view(view, source):
    from .drawing_geometry import build_view_geometry
    definition = _view_def(view)
    return {"id": str(view.BIM3117Id), "name": str(view.Label), "view_type": str(view.ViewType),
            "scale_denominator": int(view.ScaleDenominator), "definition": definition,
            "geometry": build_view_geometry(view.Project, definition),
            "show_dimensions": bool(view.ShowDimensions), "show_tags": bool(view.ShowTags),
            "show_grid": bool(view.ShowGrid), "show_levels": bool(view.ShowLevels),
            "model_revision": source["content_revision"], **_datum_rows(view.Project)}


def capture_view(view):
    validate_drawing_object(view)
    if kind(view) != "DrawingView":
        raise FoundationError("Select a 3117 DrawingView")
    from . import snapshot
    source = snapshot.capture(view.Project)
    result = _captured_view(view, source)
    result.update(schema=DRAWING_SCHEMA, drawing_revision=_hash({"rule": DRAWING_REVISION_RULE,
                                                                "view": _definition_hash(view)}))
    return result


def capture_sheet(sheet, project_snapshot=None):
    """Capture current definitions and native solids; never trust an editable DTO.

    ``project_snapshot`` exists for signature compatibility only and is rejected:
    final publication must always read the live authoritative document.
    """
    if project_snapshot is not None:
        raise FoundationError("Drawing capture requires the live document, not a caller-supplied snapshot")
    validate_drawing_object(sheet)
    if kind(sheet) != "DrawingSheet":
        raise FoundationError("Select a 3117 DrawingSheet")
    from . import snapshot
    source = snapshot.capture(sheet.Project)
    state = sheet_state(sheet)
    if state["model_revision"] != source["content_revision"]:
        raise FoundationError("Model changed while capturing the drawing; refresh and try again")
    project = sheet.Project
    result = {"schema": DRAWING_SCHEMA, "sheet": _sheet_definition(sheet),
              "project": {"id": str(project.BIM3117Id), "name": str(project.Label),
                          "number": str(project.ProjectNumber), "author": str(project.Author)},
              **state, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "views": [_captured_view(view, source) for view in sheet.Views],
              "coverage": source["coverage"],
              "source": {"document": str(project.Document.Name), "label": str(project.Document.Label),
                         "path": str(project.Document.FileName), "editable_master": "FreeCAD Document / FCStd",
                         "native_length_unit": "mm", "paper_length_unit": "mm"}}
    if sheet_state(sheet) != state:
        raise FoundationError("Model or drawing changed during projection; refresh and try again")
    return result
