# SPDX-License-Identifier: GPL-3.0-or-later
"""Small executable BIM contract, not a geometry kernel or final file format.

All lengths are SI metres. A straight wall's reference line is its local X axis;
material lies on local +Y. Quantities describe individual rectangular walls,
without junction unions. Non-overlapping rectangular hosted doors subtract one
opening each. Frozen records and read-only mappings guard the transaction API.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import csv
import json
import math
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4
from .io import atomic_path


class ModelError(ValueError):
    """Invalid or unsupported reference-model edit."""


@dataclass(frozen=True)
class Level:
    id: str
    name: str
    elevation: float


@dataclass(frozen=True)
class WallType:
    id: str
    name: str
    thickness: float


@dataclass(frozen=True)
class Wall:
    id: str
    name: str
    type_id: str
    base_level_id: str
    start: tuple[float, float]
    end: tuple[float, float]
    height: float = 3.0
    base_offset: float = 0.0
    top_level_id: str | None = None
    top_offset: float = 0.0


@dataclass(frozen=True)
class Door:
    id: str
    name: str
    host_id: str
    offset: float
    width: float
    height: float
    sill: float = 0.0


def _number(value, label, *, positive=False, nonnegative=False):
    try:
        finite = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ModelError(f"{label} must be a finite number")
    if positive and value <= 0:
        raise ModelError(f"{label} must be positive")
    if nonnegative and value < 0:
        raise ModelError(f"{label} must be non-negative")


class BuildingDocument:
    SCHEMA_VERSION = 1

    def __init__(self, name="3117 Reference Model", document_id=None):
        self._name = name
        self._id = str(uuid4()) if document_id is None else document_id
        self._levels, self._types, self._walls, self._doors = {}, {}, {}, {}
        self._undo, self._redo = [], []
        self._active = False
        self.revision = 0

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    @property
    def levels(self):
        return MappingProxyType(self._levels)

    @property
    def wall_types(self):
        return MappingProxyType(self._types)

    @property
    def walls(self):
        return MappingProxyType(self._walls)

    @property
    def doors(self):
        return MappingProxyType(self._doors)

    def _snapshot(self):
        return tuple(dict(group) for group in self._groups())

    def _groups(self):
        return self._levels, self._types, self._walls, self._doors

    def _restore(self, state):
        self._levels, self._types, self._walls, self._doors = (dict(x) for x in state)

    def _require_edit(self):
        if not self._active:
            raise ModelError("Use 'with document.transaction(label):' for edits")

    @contextmanager
    def transaction(self, label):
        if self._active:
            raise ModelError("Nested transactions are not supported")
        before = self._snapshot()
        self._active = True
        try:
            yield self
            self.validate()
            if before != self._snapshot():
                self._undo.append((str(label), before))
                self._redo.clear()
                self.revision += 1
        except BaseException:
            self._restore(before)
            raise
        finally:
            self._active = False

    def undo(self):
        if self._active:
            raise ModelError("Cannot undo during a transaction")
        if not self._undo:
            return False
        label, state = self._undo.pop()
        self._redo.append((label, self._snapshot()))
        self._restore(state)
        self.revision += 1
        return True

    def redo(self):
        if self._active:
            raise ModelError("Cannot redo during a transaction")
        if not self._redo:
            return False
        label, state = self._redo.pop()
        self._undo.append((label, self._snapshot()))
        self._restore(state)
        self.revision += 1
        return True

    def _add(self, group, cls, **kwargs):
        self._require_edit()
        item = cls(id=str(uuid4()), **kwargs)
        group[item.id] = item
        return item.id

    def add_level(self, name, elevation):
        return self._add(self._levels, Level, name=name, elevation=elevation)

    def add_wall_type(self, name, thickness):
        return self._add(self._types, WallType, name=name, thickness=thickness)

    def add_wall(self, name, type_id, base_level_id, start, end, **kwargs):
        return self._add(self._walls, Wall, name=name, type_id=type_id,
                         base_level_id=base_level_id, start=tuple(start), end=tuple(end), **kwargs)

    def add_door(self, name, host_id, offset, width, height, sill=0.0):
        return self._add(self._doors, Door, name=name, host_id=host_id,
                         offset=offset, width=width, height=height, sill=sill)

    def update(self, element_id, **changes):
        self._require_edit()
        if "id" in changes:
            raise ModelError("Element identity cannot change")
        for key in ("start", "end"):
            if key in changes:
                changes[key] = tuple(changes[key])
        for group in self._groups():
            if element_id in group:
                try:
                    group[element_id] = replace(group[element_id], **changes)
                except TypeError as exc:
                    raise ModelError(str(exc)) from exc
                return
        raise ModelError(f"Unknown element: {element_id}")

    def remove(self, element_id):
        self._require_edit()
        if any(x.host_id == element_id for x in self._doors.values()):
            raise ModelError("Delete hosted doors explicitly before deleting their wall")
        if any(element_id in (w.type_id, w.base_level_id, w.top_level_id) for w in self._walls.values()):
            raise ModelError("Element is referenced by a wall")
        for group in self._groups():
            if element_id in group:
                del group[element_id]
                return
        raise ModelError(f"Unknown element: {element_id}")

    def wall_dimensions(self, wall):
        length = math.dist(wall.start, wall.end)
        base = self._levels[wall.base_level_id].elevation + wall.base_offset
        height = (self._levels[wall.top_level_id].elevation + wall.top_offset - base
                  if wall.top_level_id else wall.height)
        return length, self._types[wall.type_id].thickness, height, base

    def validate(self):
        ids = [self.id]
        if not isinstance(self.name, str) or not self.name.strip():
            raise ModelError("Document name is required")
        for group in self._groups():
            for key, item in group.items():
                if key != item.id:
                    raise ModelError("Element key/identity mismatch")
                if not isinstance(item.name, str) or not item.name.strip():
                    raise ModelError("Element names are required")
                ids.append(item.id)
        try:
            for value in ids:
                if str(UUID(value)) != value:
                    raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ModelError("IDs must be canonical UUIDs") from exc
        if len(set(ids)) != len(ids):
            raise ModelError("Duplicate element identity")
        for level in self._levels.values():
            _number(level.elevation, "Level elevation")
        for typ in self._types.values():
            _number(typ.thickness, "Wall thickness", positive=True)
        for wall in self._walls.values():
            if wall.type_id not in self._types or wall.base_level_id not in self._levels:
                raise ModelError("Wall requires a valid type and base level")
            if wall.top_level_id is not None and wall.top_level_id not in self._levels:
                raise ModelError("Wall top level does not exist")
            for point in (wall.start, wall.end):
                if len(point) != 2:
                    raise ModelError("Wall points require two coordinates")
                for value in point:
                    _number(value, "Wall coordinate")
            _number(wall.height, "Wall height", positive=True)
            _number(wall.base_offset, "Base offset")
            _number(wall.top_offset, "Top offset")
            length, thickness, height, base = self.wall_dimensions(wall)
            _number(length, "Wall length", positive=True)
            _number(height, "Effective wall height", positive=True)
            _number(base, "Effective wall base")
            _number(length * height, "Derived wall area", positive=True)
            _number(length * height * thickness, "Derived wall volume", positive=True)
            if length < 1e-6 or height < 1e-6:
                raise ModelError("Wall must have a positive length and effective height")
        by_host = {}
        for door in self._doors.values():
            if door.host_id not in self._walls:
                raise ModelError("Door host wall does not exist")
            _number(door.width, "Door width", positive=True)
            _number(door.height, "Door height", positive=True)
            _number(door.offset, "Door offset", nonnegative=True)
            _number(door.sill, "Door sill", nonnegative=True)
            length, _, height, _ = self.wall_dimensions(self._walls[door.host_id])
            if door.offset + door.width > length + 1e-9 or door.sill + door.height > height + 1e-9:
                raise ModelError("Door opening must fit inside its host wall")
            for other in by_host.get(door.host_id, []):
                if (max(door.offset, other.offset) < min(door.offset + door.width, other.offset + other.width)
                    and max(door.sill, other.sill) < min(door.sill + door.height, other.sill + other.height)):
                    raise ModelError("Overlapping openings are not supported")
            by_host.setdefault(door.host_id, []).append(door)

    def quantities(self):
        self.validate()
        rows = []
        for wall in self._walls.values():
            length, thickness, height, _ = self.wall_dimensions(wall)
            opening_area = sum(d.width * d.height for d in self._doors.values() if d.host_id == wall.id)
            area = length * height
            rows.append({"element_id": wall.id, "name": wall.name,
                         "type_name": self._types[wall.type_id].name,
                         "length_m": length, "height_m": height, "thickness_m": thickness,
                         "gross_side_area_m2": area, "net_side_area_m2": area - opening_area,
                         "gross_volume_m3": area * thickness,
                         "net_volume_m3": (area - opening_area) * thickness})
        return rows

    def to_dict(self):
        self.validate()
        return {"schema": "bim3117-reference", "schema_version": self.SCHEMA_VERSION,
                "units": "m", "document_id": self.id, "name": self.name,
                **{key: [asdict(x) for x in group.values()] for key, group in
                   zip(("levels", "wall_types", "walls", "doors"), self._groups())}}

    def save(self, path):
        content = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with atomic_path(path) as temporary:
            temporary.write_text(content, encoding="utf-8")

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ModelError("Invalid reference JSON") from exc
        required = {"schema", "schema_version", "units", "document_id", "name",
                    "levels", "wall_types", "walls", "doors"}
        if not isinstance(data, dict) or set(data) != required:
            raise ModelError("Unexpected or missing reference document fields")
        if (data.get("schema") != "bim3117-reference" or type(data.get("schema_version")) is not int
            or data.get("schema_version") != cls.SCHEMA_VERSION
            or data.get("units") != "m"):
            raise ModelError("Unsupported reference schema or units; migration required")
        if not isinstance(data["document_id"], str) or not data["document_id"]:
            raise ModelError("Stored document identity is required")
        doc = cls(data["name"], data["document_id"])
        for key, record_cls, group in zip(("levels", "wall_types", "walls", "doors"),
                                         (Level, WallType, Wall, Door), doc._groups()):
            if not isinstance(data[key], list):
                raise ModelError(f"{key} must be an array")
            for row in data[key]:
                try:
                    if not isinstance(row, dict):
                        raise TypeError("Record must be an object")
                    if record_cls is Wall:
                        row = {**row, "start": tuple(row["start"]), "end": tuple(row["end"])}
                    record = record_cls(**row)
                    if not isinstance(record.id, str):
                        raise TypeError("Record identity must be a string")
                except (TypeError, KeyError) as exc:
                    raise ModelError(f"Invalid {key} record") from exc
                if record.id in group:
                    raise ModelError("Duplicate element identity in input")
                group[record.id] = record
        doc.validate()
        return doc

    def write_schedule(self, path):
        rows = self.quantities()
        if not rows:
            raise ModelError("No walls to schedule")
        with atomic_path(path) as temporary:
            with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
