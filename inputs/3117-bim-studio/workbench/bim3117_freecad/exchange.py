# SPDX-License-Identifier: GPL-3.0-or-later
"""CSV/IFC snapshots from the live FreeCAD model, with explicit provenance.

Export does not mutate the authored document or add an Undo entry. Native
geometry is validated before staging files; metadata contains the exact source
snapshot, coverage, rules, revision and payload hashes. It is written last.
"""
import csv
import hashlib
import io
import json
import os
from pathlib import Path

from . import snapshot
from .export_files import ExportFileError, publish_bundle
from .model import FoundationError

WALL_COLUMNS = (
    "element_id", "name", "type_id", "type_name", "base_level_id", "base_level",
    "top_level_id", "top_level", "length_m", "height_m", "thickness_m",
    "gross_side_area_m2", "opening_side_area_m2", "net_side_area_m2",
    "gross_volume_m3", "opening_volume_m3", "net_volume_m3",
    "quantity_rule", "content_revision",
)
DOOR_COLUMNS = (
    "element_id", "name", "host_id", "host_name", "base_level_id", "base_level",
    "offset_m", "width_m", "height_m", "sill_m", "opening_area_m2",
    "opening_volume_m3", "frame_volume_m3", "count", "quantity_rule", "content_revision",
)
SLAB_COLUMNS = (
    "element_id", "name", "level_id", "level", "offset_m", "top_z_m", "thickness_m",
    "gross_area_m2", "net_area_m2", "perimeter_m", "gross_volume_m3", "net_volume_m3",
    "material", "count", "quantity_rule", "content_revision",
)
COLUMN_COLUMNS = (
    "element_id", "name", "base_level_id", "base_level", "top_level_id", "top_level",
    "x_m", "y_m", "rotation_deg", "width_m", "depth_m", "height_m", "base_offset_m", "top_offset_m",
    "section_area_m2", "gross_volume_m3", "join_deduction_m3", "net_volume_m3",
    "join_slab_ids", "join_count", "material", "count", "quantity_rule", "content_revision",
)
BEAM_COLUMNS = (
    "element_id", "name", "level_id", "level", "start_x_m", "start_y_m", "end_x_m", "end_y_m",
    "length_m", "width_m", "depth_m", "offset_m", "top_z_m", "section_area_m2",
    "gross_volume_m3", "join_deduction_m3", "net_volume_m3", "join_slab_ids", "join_count",
    "material", "count", "quantity_rule", "content_revision",
)
WINDOW_COLUMNS = DOOR_COLUMNS
PRODUCT_TYPE_COLUMNS = ("type_id", "type_name", "type_code", "material_id", "material_name")
TYPE_COLUMNS = (
    "type_id", "type_name", "category", "type_code", "thickness_m", "width_m", "depth_m", "height_m",
    "material_id", "material_name", "layer_count", "layers", "instance_count", "quantity_rule", "content_revision",
)
MATERIAL_COLUMNS = (
    "element_id", "name", "category", "level_id", "level", "type_id", "type_name",
    "material_id", "material_name", "material_code", "layer_index", "layer_role", "thickness_m",
    "gross_volume_m3", "deduction_volume_m3", "net_volume_m3", "deduction_rule", "quantity_rule", "content_revision",
)
ADDITIONAL_CSV = (
    ("slab_rows", "slabs", SLAB_COLUMNS), ("column_rows", "columns", COLUMN_COLUMNS),
    ("beam_rows", "beams", BEAM_COLUMNS), ("window_rows", "windows", WINDOW_COLUMNS),
    ("type_rows", "types", TYPE_COLUMNS), ("material_rows", "materials", MATERIAL_COLUMNS),
)


def _columns(captured, key, columns):
    """Add catalogue identity only for catalogue-aware snapshots.

    An untouched legacy document keeps its original six CSV schemas and bytes.
    Shared row fields are explicit blanks for untyped products in mixed models.
    """
    if "type_rows" in captured and key not in ("type_rows", "material_rows"):
        return columns + tuple(name for name in PRODUCT_TYPE_COLUMNS if name not in columns)
    return columns


def output_paths(path, format="csv", source=None):
    """Return payload and metadata paths; pass the preview snapshot for CSV.

    The legacy Wall/Door CSV pair always exists. Additional category CSVs are
    included only when that category has rows in ``source``. Without a source,
    the legacy three-path result is retained for existing callers.
    """
    if format not in ("csv", "ifc"):
        raise FoundationError("Export format must be csv or ifc")
    requested = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    if requested.suffix.lower() != "." + format:
        raise FoundationError(f"Choose a .{format} file for this export")
    if not requested.stem.strip():
        raise FoundationError("Choose a nonempty export filename")
    files = [requested]
    if format == "csv":
        files.append(requested.with_name(requested.stem + "_doors.csv"))
        for key, suffix, _ in ADDITIONAL_CSV:
            if source is not None and source.get(key):
                files.append(requested.with_name(requested.stem + "_" + suffix + ".csv"))
    files.append(requested.with_name(requested.stem + f"_{format}_metadata.json"))
    return [str(item) for item in files]


def ifc_dependency_info():
    try:
        from . import ifc_native
        return ifc_native.dependency_info()
    except (ImportError, OSError) as error:
        return {"available": False, "version": "", "message":
                "IfcOpenShell is unavailable in this FreeCAD runtime. CSV export remains available. "
                "Use the separately installed, tested FreeCAD 1.1.4 distribution or install a compatible "
                "IfcOpenShell using FreeCAD's supported dependency mechanism. " + str(error)}


def _capture(project, expected_revision):
    current = snapshot.capture(project)
    if expected_revision is not None and current["content_revision"] != expected_revision:
        raise FoundationError("The model changed since the export preview; refresh quantities and export again")
    return current


def _check_current(project, expected):
    if snapshot.capture(project)["content_revision"] != expected:
        raise FoundationError("The model changed during export; no new files were published")


def _csv_value(value):
    # A model name is text, even if its first character resembles a spreadsheet
    # formula. Numeric columns remain numbers, including negative elevations.
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if isinstance(value, str):
        trimmed = value.lstrip()
        if value.startswith(("\t", "\r", "\n")) or (trimmed and trimmed[0] in "=+-@"):
            return "'" + value
    return value


def _csv_bytes(rows, columns):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: _csv_value(row[name]) for name in columns})
    # UTF-8 BOM is deliberate: Thai names open correctly in common spreadsheet
    # applications. Full original labels are retained in the metadata snapshot.
    return stream.getvalue().encode("utf-8-sig")


def _metadata(captured, format, paths, payload_paths, validation):
    return {"export_schema": 1, "format": format, "content_revision": captured["content_revision"],
            "source": "FreeCAD native document / FCStd", "editable_master": False,
            "snapshot": captured, "coverage": captured["coverage"], "validation": validation,
            "files": [{"name": destination.name, "bytes": temporary.stat().st_size,
                       "sha256": hashlib.sha256(temporary.read_bytes()).hexdigest()}
                      for destination, temporary in zip(paths[:-1], payload_paths)],
            "csv": {"encoding": "UTF-8 BOM", "delimiter": ",", "decimal": ".",
                    "wall_columns": list(_columns(captured, "wall_rows", WALL_COLUMNS)),
                    "door_columns": list(_columns(captured, "door_rows", DOOR_COLUMNS)),
                    "additional_columns": {suffix: list(_columns(captured, key, columns)) for key, suffix, columns in ADDITIONAL_CSV
                                           if captured.get(key)},
                    "text_policy": "Formula-like text cells have a leading apostrophe; original strings are in snapshot."}
                    if format == "csv" else None,
            "publication": "Payloads replaced individually; this metadata is the final completion marker. Verify hashes before use.",
            "freshness": "Compare content_revision with a new native snapshot; this file does not update when the model changes."}


def _result(captured, format, paths, validation):
    return {"content_revision": captured["content_revision"], "files": [str(path) for path in paths],
            "metadata_path": str(paths[-1]), "format": format,
            "coverage": captured["coverage"], "validation": validation}


def export_csv(project, path, overwrite=False, expected_revision=None):
    captured = _capture(project, expected_revision)
    paths = [Path(item) for item in output_paths(path, "csv", source=captured)]
    tables = [(captured["wall_rows"], _columns(captured, "wall_rows", WALL_COLUMNS)),
              (captured["door_rows"], _columns(captured, "door_rows", DOOR_COLUMNS))]
    tables.extend((captured[key], _columns(captured, key, columns)) for key, _, columns in ADDITIONAL_CSV if captured.get(key))
    validation = {"status": "passed", "native_geometry": "validated", "units": "m / m2 / m3",
                  "wall_rows": len(captured["wall_rows"]), "door_rows": len(captured["door_rows"]),
                  **{key: len(captured.get(key, [])) for key, _, _ in ADDITIONAL_CSV}}

    def writer(staged):
        for path, (rows, columns) in zip(staged[:-1], tables):
            path.write_bytes(_csv_bytes(rows, columns))
        metadata = _metadata(captured, "csv", paths, staged[:-1], validation)
        staged[-1].write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    try:
        publish_bundle(paths, writer, overwrite=overwrite,
                       before_commit=lambda: _check_current(project, captured["content_revision"]))
    except ExportFileError as error:
        raise FoundationError(str(error)) from error
    return _result(captured, "csv", paths, validation)


def export_ifc(project, path, overwrite=False, expected_revision=None):
    captured = _capture(project, expected_revision)
    paths = [Path(item) for item in output_paths(path, "ifc")]
    dependency = ifc_dependency_info()
    if not dependency["available"]:
        raise FoundationError(dependency["message"])
    from . import ifc_native
    import ifcopenshell
    model = ifc_native.build_ifc(captured)
    validation = {}

    def writer(staged):
        # Validation reads the actual staged IFC, before replacing any existing
        # user output. No IFC is declared successful solely because it serialized.
        model.write(str(staged[0]))
        readback = ifcopenshell.open(str(staged[0]))
        validation.update(ifc_native.validate_ifc(readback, captured))
        if validation.get("status") != "passed":
            raise FoundationError("IFC readback validation failed; no new files were published")
        metadata = _metadata(captured, "ifc", paths, staged[:-1], validation)
        staged[-1].write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    try:
        publish_bundle(paths, writer, overwrite=overwrite,
                       before_commit=lambda: _check_current(project, captured["content_revision"]))
    except ExportFileError as error:
        raise FoundationError(str(error)) from error
    return _result(captured, "ifc", paths, validation)
