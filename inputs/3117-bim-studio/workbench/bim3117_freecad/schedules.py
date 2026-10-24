# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent schedule definitions, projected from the committed native model.

The FCStd stores filters and display rules. Rows are fresh read-only projections,
never a second model. Source edits use the catalogue's single native transaction.
Schedule definitions do not alter building content identity; publication checks
both the building and the schedule definition revision.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import UUID

import FreeCAD as App

from . import services
from .model import FoundationError, _BaseProxy, _common, _link_project, _property, kind, text

SCHEDULE_SCHEMA = 1
SCHEDULE_REVISION_RULE = "3117.native-schedule-definitions.sha256.v1"
CATEGORIES = ("Wall", "Door", "Slab", "Column", "Beam", "Window", "Material")
GROUPINGS = ("None", "Type", "Material")
SORTS = ("Name", "Type", "Level", "Material")
_UNCHANGED = object()
_TABLES = {category: category.lower() + "_rows" for category in CATEGORIES}
_FIELDS = {
    "Wall": ("name", "type_name", "level", "top_level", "length_m", "height_m", "thickness_m",
             "gross_side_area_m2", "opening_side_area_m2", "net_side_area_m2", "net_volume_m3", "count"),
    "Door": ("name", "type_name", "level", "host_name", "width_m", "height_m", "sill_m",
             "opening_area_m2", "frame_volume_m3", "count"),
    "Window": ("name", "type_name", "level", "host_name", "width_m", "height_m", "sill_m",
               "opening_area_m2", "frame_volume_m3", "count"),
    "Slab": ("name", "type_name", "level", "thickness_m", "gross_area_m2", "net_area_m2",
             "gross_volume_m3", "net_volume_m3", "count"),
    "Column": ("name", "type_name", "level", "top_level", "width_m", "depth_m", "height_m",
               "gross_volume_m3", "join_deduction_m3", "net_volume_m3", "count"),
    "Beam": ("name", "type_name", "level", "length_m", "width_m", "depth_m",
             "gross_volume_m3", "join_deduction_m3", "net_volume_m3", "count"),
    "Material": ("name", "type_name", "level", "material_name", "material_code", "layer_index",
                 "layer_role", "thickness_m", "gross_volume_m3", "deduction_volume_m3", "net_volume_m3", "count"),
}
_SUM_FIELDS = {
    "Wall": ("length_m", "gross_side_area_m2", "opening_side_area_m2", "net_side_area_m2",
             "gross_volume_m3", "opening_volume_m3", "net_volume_m3"),
    "Door": ("opening_area_m2", "opening_volume_m3", "frame_volume_m3", "net_volume_m3"),
    "Window": ("opening_area_m2", "opening_volume_m3", "frame_volume_m3", "net_volume_m3"),
    "Slab": ("gross_area_m2", "net_area_m2", "gross_volume_m3", "net_volume_m3"),
    "Column": ("gross_volume_m3", "join_deduction_m3", "net_volume_m3"),
    "Beam": ("length_m", "gross_volume_m3", "join_deduction_m3", "net_volume_m3"),
    "Material": ("gross_volume_m3", "deduction_volume_m3", "net_volume_m3"),
}


def _plain(value, label, required=False, limit=160):
    value = text(value, label, required=required)
    if len(value) > limit or any(ord(c) < 32 for c in value):
        raise FoundationError(f"{label} must be one line of at most {limit} characters")
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _require_project(project):
    services._require(project, "Project")
    if services.get_project(project.Document) != project:
        raise FoundationError("The schedule must belong to the document's 3117 project")
    return project


def _idle(project):
    _require_project(project)
    doc = project.Document
    if (doc.HasPendingTransaction or App.getActiveTransaction() is not None
            or doc.Transacting or getattr(doc, "Restoring", False)):
        raise FoundationError("Finish or cancel the current transaction before this schedule command")
    return doc


def get_schedule_set(project):
    _require_project(project)
    groups = [obj for obj in project.Document.Objects
              if kind(obj) == "ScheduleSet" and getattr(obj, "Project", None) == project]
    if len(groups) > 1:
        raise FoundationError("Only one 3117 schedule set per project is supported")
    return groups[0] if groups else None


def list_schedules(project):
    group = get_schedule_set(project)
    return [obj for obj in group.Group if kind(obj) == "Schedule"] if group else []


def _unique(project, category, name, except_obj=None):
    if any(obj != except_obj and kind(obj) == category and getattr(obj, "Project", None) == project
           and obj.Label == name for obj in project.Document.Objects):
        raise FoundationError(f"A {category} named '{name}' already exists")


def _identity(obj):
    if kind(obj) not in ("ScheduleSet", "Schedule") or obj.Document is None:
        raise FoundationError("Select a 3117 schedule object in an open document")
    try:
        if str(UUID(obj.BIM3117Id)) != obj.BIM3117Id:
            raise ValueError("Non-canonical UUID")
    except (ValueError, TypeError, AttributeError) as error:
        raise FoundationError("Schedule UUID is missing or invalid") from error
    if obj.BIM3117Schema != 1 or obj.ScheduleSchema != SCHEDULE_SCHEMA:
        raise FoundationError("Unsupported schedule schema; migration is required")
    if _plain(obj.Label, "Schedule name", required=True) != obj.Label:
        raise FoundationError("Schedule names must not have leading or trailing spaces")
    project = _require_project(getattr(obj, "Project", None))
    if obj.Document != project.Document or obj.ProjectId != project.BIM3117Id:
        raise FoundationError("Schedule project link or identity is inconsistent")
    ids = [str(item.BIM3117Id) for item in obj.Document.Objects if getattr(item, "BIM3117Id", "")]
    if len(ids) != len(set(ids)):
        raise FoundationError("Duplicate persistent UUID in the document")
    _unique(project, kind(obj), obj.Label, obj)
    return project


def _values(project, *, category, level, element_type, group_by, sort_by, descending, name_filter):
    if category not in CATEGORIES:
        raise FoundationError("Schedule category must be " + ", ".join(CATEGORIES))
    if group_by not in GROUPINGS:
        raise FoundationError("Group by must be None, Type or Material")
    if group_by == "Material" and category != "Material":
        raise FoundationError("Material grouping requires the Material category, which uses actual material partitions")
    if sort_by not in SORTS:
        raise FoundationError("Sort by must be Name, Type, Level or Material")
    if not isinstance(descending, bool):
        raise FoundationError("Descending must be true or false")
    if level is not None:
        if kind(level) != "Level" or level.Document != project.Document or level.Project != project:
            raise FoundationError("Schedule Level filter must belong to the same project")
        services._require(level, "Level")
    if element_type is not None:
        if (kind(element_type) not in ("WallType", "ElementType")
                or element_type.Document != project.Document or element_type.Project != project):
            raise FoundationError("Schedule Type filter must belong to the same project")
        services._require(element_type, kind(element_type))
        type_category = "Wall" if kind(element_type) == "WallType" else str(element_type.Category)
        if category != "Material" and type_category != category:
            raise FoundationError("Schedule Type filter must match its category")
    return dict(category=category, level=level, element_type=element_type, group_by=group_by,
                sort_by=sort_by, descending=descending, name_filter=_plain(name_filter, "Name filter"))


def _raw(schedule):
    return dict(category=str(schedule.Category), level=schedule.FilterLevel,
                element_type=schedule.FilterType, group_by=str(schedule.GroupBy),
                sort_by=str(schedule.SortBy), descending=bool(schedule.Descending),
                name_filter=str(schedule.NameFilter))


def _definition(schedule):
    values = _raw(schedule)
    values.pop("level")
    values.pop("element_type")
    return dict(id=str(schedule.BIM3117Id), name=str(schedule.Label),
                level_id=str(schedule.FilterLevelId), type_id=str(schedule.FilterTypeId), **values)


def validate_schedule_object(obj):
    project = _identity(obj)
    group = get_schedule_set(project)
    if obj in project.Group:
        raise FoundationError("Schedule definitions must stay outside the building Project group")
    if kind(obj) == "ScheduleSet":
        if group != obj:
            raise FoundationError("Schedule set membership is inconsistent")
        if any(kind(child) != "Schedule" or getattr(child, "Project", None) != project for child in obj.Group):
            raise FoundationError("Schedule set contains an unsupported or foreign child")
        return True
    if group is None or obj not in group.Group:
        raise FoundationError("Schedule must belong to its project's schedule set")
    values = _values(project, **_raw(obj))
    for value, prop in ((values["level"], "FilterLevelId"), (values["element_type"], "FilterTypeId")):
        expected = str(value.BIM3117Id) if value is not None else ""
        if str(getattr(obj, prop)) != expected:
            raise FoundationError("Schedule filter reference is missing or its identity changed; edit the schedule to repair")
    return True


def _style(obj):
    if not App.GuiUp:
        return
    from ui3117 import viewproviders
    name = "attach_schedule_set_view" if kind(obj) == "ScheduleSet" else "attach_schedule_view"
    callback = getattr(viewproviders, name, None)
    if callback is not None:
        callback(obj)


class _ScheduleProxy(_BaseProxy):
    def onBeforeChangeLabel(self, obj, label):
        if (not getattr(self, "_ready", False) or obj.Document.Transacting
                or obj.Document.Name in services._OWNED_TRANSACTIONS or getattr(obj.Document, "Restoring", False)):
            return label
        try:
            label = _plain(label, "Schedule name", required=True)
            _unique(obj.Project, kind(obj), label, obj)
            return label
        except FoundationError as error:
            App.Console.PrintError(f"3117: {error}\n")
            return obj.Label

    def onChanged(self, obj, prop):
        if (not getattr(self, "_ready", False) or getattr(self, "_restoring_value", False)
                or prop not in self.editable or obj.Document.Transacting
                or obj.Document.Name in services._OWNED_TRANSACTIONS
                or getattr(obj.Document, "Restoring", False)):
            return
        if prop in ("FilterLevel", "FilterType"):
            if getattr(obj, prop) is None:
                obj.ValidationMessage = f"{prop} reference missing; edit the schedule to repair"
                return
            if prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, self._before[prop])
                finally:
                    self._restoring_value = False
            App.Console.PrintError(f"3117: use Edit Schedule to change {prop}\n")
            return
        try:
            validate_schedule_object(obj)
        except FoundationError as error:
            if prop in self._before:
                self._restoring_value = True
                try:
                    setattr(obj, prop, self._before[prop])
                finally:
                    self._restoring_value = False
            App.Console.PrintError(f"3117: {error}\n")

    def execute(self, obj):
        try:
            validate_schedule_object(obj)
            obj.ValidationMessage = ""
        except Exception as error:
            obj.ValidationMessage = str(error)

    def onDocumentRestored(self, obj):
        super().onDocumentRestored(obj)
        for prop in ("ScheduleSchema", "ProjectId", "FilterLevel", "FilterLevelId", "FilterType", "FilterTypeId"):
            if prop in obj.PropertiesList:
                obj.setEditorMode(prop, 1)
        _style(obj)

    def build(self, obj):
        pass


def _common_schedule(obj, category, project):
    _common(obj, category)
    _link_project(obj, project)
    _property(obj, "App::PropertyString", "ProjectId", "3117 Identity", "Expected project UUID", project.BIM3117Id, True)
    _property(obj, "App::PropertyInteger", "ScheduleSchema", "3117 Identity", "Schedule definition schema", SCHEDULE_SCHEMA, True)


class ScheduleSetProxy(_ScheduleProxy):
    editable = ("Label",)

    def __init__(self, obj, project):
        self._start(obj)
        _common_schedule(obj, "ScheduleSet", project)
        self._finish(obj)


class ScheduleProxy(_ScheduleProxy):
    editable = ("Label", "Category", "FilterLevel", "FilterType", "GroupBy", "SortBy", "Descending", "NameFilter")

    def __init__(self, obj, project):
        self._start(obj)
        _common_schedule(obj, "Schedule", project)
        for prop, options in (("Category", CATEGORIES), ("GroupBy", GROUPINGS), ("SortBy", SORTS)):
            obj.addProperty("App::PropertyEnumeration", prop, "Schedule", prop)
            setattr(obj, prop, list(options))
        for prop in ("FilterLevel", "FilterType"):
            _property(obj, "App::PropertyLink", prop, "Schedule", "Optional source filter; use Edit Schedule", None, True)
            _property(obj, "App::PropertyString", prop + "Id", "3117 Identity", "Expected filter UUID", "", True)
        _property(obj, "App::PropertyBool", "Descending", "Schedule", "Reverse the selected stable sort", False)
        _property(obj, "App::PropertyString", "NameFilter", "Schedule", "Case-insensitive substring of source element name", "")
        self._finish(obj)


def _assign(obj, values):
    for key, prop in (("category", "Category"), ("group_by", "GroupBy"), ("sort_by", "SortBy"),
                      ("descending", "Descending"), ("name_filter", "NameFilter")):
        setattr(obj, prop, values[key])
    for key, prop in (("level", "FilterLevel"), ("element_type", "FilterType")):
        value = values[key]
        setattr(obj, prop, value)
        setattr(obj, prop + "Id", str(value.BIM3117Id) if value is not None else "")


def create_schedule(project, name, category="Wall", level=None, element_type=None,
                    group_by="None", sort_by="Name", descending=False, name_filter=""):
    doc = _idle(project)
    name = _plain(name, "Schedule name", required=True)
    _unique(project, "Schedule", name)
    values = _values(project, category=category, level=level, element_type=element_type,
                     group_by=group_by, sort_by=sort_by, descending=descending, name_filter=name_filter)
    with services._transaction(doc, "3117 Create schedule"):
        group = get_schedule_set(project)
        if group is None:
            group = doc.addObject("App::DocumentObjectGroupPython", "BIM3117_Schedules")
            ScheduleSetProxy(group, project)
            group.Label = "3117 Schedules"
            _style(group)
        obj = doc.addObject("App::FeaturePython", "BIM3117_Schedule")
        ScheduleProxy(obj, project)
        obj.Label = name
        _assign(obj, values)
        group.addObject(obj)
        _style(obj)
        validate_schedule_object(obj)
    return obj


def edit_schedule(schedule, name=None, category=None, level=_UNCHANGED, element_type=_UNCHANGED,
                  group_by=None, sort_by=None, descending=None, name_filter=None):
    if kind(schedule) != "Schedule":
        raise FoundationError("Select a 3117 Schedule")
    project = _identity(schedule)
    doc = _idle(project)
    values = _raw(schedule)
    for key, value in (("category", category), ("group_by", group_by), ("sort_by", sort_by),
                       ("descending", descending), ("name_filter", name_filter)):
        if value is not None:
            values[key] = value
    for key, value, prop in (("level", level, "FilterLevelId"), ("element_type", element_type, "FilterTypeId")):
        if value is not _UNCHANGED:
            values[key] = value
        elif values[key] is None and getattr(schedule, prop):
            raise FoundationError("Repair or explicitly detach the missing schedule filter before editing")
    values = _values(project, **values)
    label = str(schedule.Label) if name is None else _plain(name, "Schedule name", required=True)
    _unique(project, "Schedule", label, schedule)
    with services._transaction(doc, "3117 Edit schedule"):
        schedule.Label = label
        _assign(schedule, values)
        validate_schedule_object(schedule)
    return schedule


def delete_schedule(schedule):
    if kind(schedule) != "Schedule":
        raise FoundationError("Select a 3117 Schedule")
    project = _identity(schedule)
    doc = _idle(project)
    group, name = get_schedule_set(project), schedule.Name
    with services._transaction(doc, "3117 Delete schedule"):
        if group is not None:
            group.removeObject(schedule)
        doc.removeObject(name)


def schedule_state(schedule):
    if kind(schedule) != "Schedule":
        raise FoundationError("Select a 3117 Schedule")
    validate_schedule_object(schedule)
    from . import snapshot
    project = schedule.Project
    snapshot._ready(project, recompute=False)
    return {"model_revision": snapshot._revision(snapshot._authored(project), snapshot._coverage(project.Document)),
            "schedule_revision": _hash({"rule": SCHEDULE_REVISION_RULE, "definition": _definition(schedule)})}


def _column(key):
    unit = "m3" if key.endswith("_m3") else "m2" if key.endswith("_m2") else "m" if key.endswith("_m") else ""
    label = key[:-(len(unit) + 1)] if unit else key
    return {"key": key, "label": label.replace("_", " ").capitalize(), "unit": unit}


def _source_rows(source, definition):
    category = definition["category"]
    rows = []
    for original in source.get(_TABLES[category], []):
        row = dict(original)
        row["category"] = row.get("category", category)
        row["level_id"] = row.get("level_id", row.get("base_level_id", ""))
        row["level"] = row.get("level", row.get("base_level", ""))
        row["type_id"] = row.get("type_id", "")
        row["type_name"] = row.get("type_name", "") or "Instance-defined"
        row["type_code"] = row.get("type_code", "")
        row["material_id"] = row.get("material_id", "")
        row["material_name"] = row.get("material_name", "") or row.get("material", "")
        if definition["level_id"] and row["level_id"] != definition["level_id"]:
            continue
        if definition["type_id"] and row["type_id"] != definition["type_id"]:
            continue
        if definition["name_filter"].casefold() not in row["name"].casefold():
            continue
        if category in ("Door", "Window"):
            row["net_volume_m3"] = row["frame_volume_m3"]
        row["count"] = 1
        row["element_ids"] = [row["element_id"]]
        row["row_id"] = (row["element_id"] + ":" + str(row["layer_index"]) + ":" + row["material_id"]
                         if category == "Material" else row["element_id"])
        rows.append(row)
    return rows


def _summed(rows, category):
    return {key: math.fsum(row[key] for row in rows) for key in _SUM_FIELDS[category]}


def _grouped(rows, definition):
    grouping = definition["group_by"]
    if grouping == "None":
        return rows
    category = definition["category"]
    key = "type_id" if grouping == "Type" else "material_id"
    name_key = "type_name" if grouping == "Type" else "material_name"
    groups = {}
    for row in rows:
        groups.setdefault(row[key], []).append(row)
    result = []
    for identity, children in groups.items():
        ids = sorted({row["element_id"] for row in children})
        row = {"row_id": "group:" + _hash([category, grouping, identity]), "element_ids": ids,
               "name": children[0][name_key], "category": category, "count": len(ids),
               "source_row_count": len(children), **_summed(children, category)}
        for field in ("type_id", "type_name", "type_code", "level_id", "level", "material_id", "material_name"):
            values = sorted({str(item[field]) for item in children}, key=lambda v: (v.casefold(), v))
            row[field] = values[0] if len(values) == 1 else ("Multiple" if field.endswith("_id") else "; ".join(values))
        result.append(row)
    return result


def capture_schedule(schedule, project_snapshot=None):
    if project_snapshot is not None:
        raise FoundationError("Schedule capture requires the live document, not a caller-supplied snapshot")
    state = schedule_state(schedule)
    from . import snapshot
    source = snapshot.capture(schedule.Project)
    definition = _definition(schedule)
    selected = _source_rows(source, definition)
    rows = _grouped(selected, definition)
    key = {"Name": "name", "Type": "type_name", "Level": "level", "Material": "material_name"}[definition["sort_by"]]
    rows = sorted(rows, key=lambda row: (str(row[key]).casefold(), str(row["name"]).casefold(), row["row_id"]),
                  reverse=definition["descending"])
    category = definition["category"]
    fields = _FIELDS[category] if definition["group_by"] == "None" else ("name", "count") + _SUM_FIELDS[category]
    coverage = {"building": source["coverage"], "material": source.get("material_totals", {}),
                "scope": "Filtered source rows; material quantities include only products with assigned native materials.",
                "quantity_rules": sorted({row["quantity_rule"] for row in selected}),
                "deduction_rules": sorted({row["deduction_rule"] for row in selected if "deduction_rule" in row})}
    totals = {"source_element_count": len({row["element_id"] for row in selected}),
              "source_row_count": len(selected), "display_row_count": len(rows), **_summed(selected, category)}
    result = {"schema": SCHEDULE_SCHEMA, **state, "definition": definition,
              "columns": [_column(field) for field in fields], "rows": rows, "totals": totals,
              "coverage": coverage, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": {"project_id": str(schedule.Project.BIM3117Id), "project_name": str(schedule.Project.Label),
                         "document": str(schedule.Document.Name), "path": str(schedule.Document.FileName),
                         "editable_master": "FreeCAD Document / FCStd", "native_length_unit": "mm",
                         "quantity_units": "m / m2 / m3", "name_filter": "Case-insensitive substring of source element name",
                         "level_filter": "Base Level for Wall/Door/Window/Column; Level for Slab/Beam",
                         "count_rule": "Distinct parent element UUIDs; material layer row counts are separate",
                         "total_rule": "Sum independent product quantities; not the spatial union of different products"}}
    if source["content_revision"] != state["model_revision"] or schedule_state(schedule) != state:
        raise FoundationError("Model or schedule changed during capture; refresh and try again")
    return result


def _expected(state, model_revision=None, schedule_revision=None):
    if ((model_revision is not None and state["model_revision"] != model_revision)
            or (schedule_revision is not None and state["schedule_revision"] != schedule_revision)):
        raise FoundationError("Model or schedule changed since the preview; refresh the schedule and try again")


def edit_row(schedule, element_id, changes, expected_model_revision=None, expected_schedule_revision=None):
    captured = capture_schedule(schedule)
    _expected(captured, expected_model_revision, expected_schedule_revision)
    if not isinstance(element_id, str) or element_id not in {i for row in captured["rows"] for i in row["element_ids"]}:
        raise FoundationError("Choose a source element visible in this schedule")
    candidates = [obj for obj in schedule.Project.Group if getattr(obj, "BIM3117Id", None) == element_id]
    if len(candidates) != 1 or kind(candidates[0]) not in CATEGORIES[:-1]:
        raise FoundationError("Schedule source is missing or ambiguous; refresh the schedule")
    from . import catalog
    return catalog.edit_instance(candidates[0], changes)


def output_paths(path):
    requested = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    if requested.suffix.lower() != ".csv" or not requested.stem.strip():
        raise FoundationError("Choose a nonempty .csv filename for this schedule")
    return [str(requested), str(requested.with_name(requested.stem + "_schedule_metadata.json"))]


def export_schedule(schedule, path, overwrite=False, expected_model_revision=None, expected_schedule_revision=None):
    captured = capture_schedule(schedule)
    _expected(captured, expected_model_revision, expected_schedule_revision)
    from .exchange import _csv_bytes
    from .export_files import ExportFileError, publish_bundle
    paths = [Path(value) for value in output_paths(path)]
    columns = ("row_id", "element_ids") + tuple(column["key"] for column in captured["columns"])
    rows = [{**row, "element_ids": "|".join(row["element_ids"])} for row in captured["rows"]]

    def writer(staged):
        staged[0].write_bytes(_csv_bytes(rows, columns))
        metadata = {"export_schema": SCHEDULE_SCHEMA, "format": "schedule_csv", "editable_master": False,
                    "model_revision": captured["model_revision"], "schedule_revision": captured["schedule_revision"],
                    "snapshot": captured, "files": [{"name": paths[0].name, "bytes": staged[0].stat().st_size,
                                                      "sha256": hashlib.sha256(staged[0].read_bytes()).hexdigest()}],
                    "csv": {"encoding": "UTF-8 BOM", "delimiter": ",", "decimal": ".", "columns": columns,
                            "text_policy": "Formula-like text cells have a leading apostrophe; original strings are in snapshot."},
                    "publication": "Files replaced individually; metadata is the final completion marker. Verify hashes before use.",
                    "freshness": "Compare both revisions with the current native schedule; this file does not update automatically."}
        staged[1].write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    try:
        publish_bundle(paths, writer, overwrite=overwrite,
                       before_commit=lambda: _expected(schedule_state(schedule), captured["model_revision"], captured["schedule_revision"]))
    except ExportFileError as error:
        raise FoundationError(str(error)) from error
    return {"files": [str(value) for value in paths], "metadata_path": str(paths[-1]),
            "model_revision": captured["model_revision"], "schedule_revision": captured["schedule_revision"],
            "validation": {"status": "passed", "source_rows": captured["totals"]["source_row_count"],
                           "display_rows": len(captured["rows"]), "units": "m / m2 / m3"}}
