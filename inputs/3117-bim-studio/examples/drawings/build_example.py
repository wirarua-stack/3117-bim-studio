# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the drawing fixture in FreeCAD with the installed 3117 workbench.

The frozen Building Authoring FCStd is read, never saved over. No geometry is
rebuilt from a reference JSON file. Call build(new_destination) in FreeCAD's
Python console, or execute this file in FreeCADCmd to create the default sample.
An existing destination is never overwritten by this fixture builder.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import FreeCAD as App

from bim3117_freecad import drawings, services, snapshot

SOURCE_SHA256 = "9a0e2efc3613747b2806ead5ecd61b6b74d757a229ca9ebc5e649afe28e68995"
MODEL_REVISION = "6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a"


def add_definitions(project):
    """Add the four explicit 1:50 views and two A3 landscape sheets."""
    levels = {level.Label: level for level in services.list_levels(project)}
    ground = drawings.create_view(project, "Ground Plan", level=levels["L00"],
                                  bottom_offset_mm=-150, cut_offset_mm=1200,
                                  top_offset_mm=2800, scale_denominator=50)
    upper = drawings.create_view(project, "Upper Plan", level=levels["L01"],
                                 bottom_offset_mm=-150, cut_offset_mm=1200,
                                 top_offset_mm=2800, scale_denominator=50)
    section = drawings.create_view(project, "Section A-A", view_type="Section",
                                   origin_mm=(0, 2000, 0), direction="+Y", depth_mm=3000,
                                   scale_denominator=50)
    elevation = drawings.create_view(project, "South Elevation", view_type="Elevation",
                                     origin_mm=(0, -1000, 0), direction="+Y", depth_mm=6000,
                                     scale_denominator=50)
    plans = drawings.create_sheet(project, "Floor Plans", "A101", [ground, upper],
                                  issue="P01", author="3117 BIM")
    vertical = drawings.create_sheet(project, "Section and Elevation", "A201", [section, elevation],
                                     issue="P01", author="3117 BIM")
    return [ground, upper, section, elevation], [plans, vertical]


def build(destination=None):
    source = Path(__file__).resolve().parents[1] / "building" / "Building_Authoring_Workbench.FCStd"
    destination = (Path(destination) if destination is not None else
                   Path(__file__).resolve().parent / "Drawings_Workbench.FCStd").resolve()
    metadata_path = destination.with_name("drawings-example.json")
    if destination.exists():
        raise FileExistsError("The fixture destination already exists: " + str(destination))
    if metadata_path.exists():
        raise FileExistsError("The fixture metadata destination already exists: " + str(metadata_path))
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("The frozen v0.3.0 building fixture has changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = tempfile.TemporaryDirectory(prefix="3117-drawing-fixture-")
    doc = None
    try:
        # A distinct physical copy also avoids reusing a source document that
        # a user already has open in the FreeCAD GUI.
        copied_source = Path(staging.name) / source.name
        shutil.copy2(source, copied_source)
        doc = App.openDocument(str(copied_source))
        doc.UndoMode = 1
        project = services.get_project(doc)
        if snapshot.capture(project)["content_revision"] != MODEL_REVISION:
            raise ValueError("The frozen building model revision is incompatible")
        views, sheets = add_definitions(project)
        if snapshot.capture(project)["content_revision"] != MODEL_REVISION:
            raise ValueError("Drawing definitions unexpectedly changed the building model revision")
        doc.saveAs(str(destination))
        result = {"schema": 1, "fixture": "Synthetic two-storey native drawing example",
                  "file": destination.name, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                  "source_file": "../building/Building_Authoring_Workbench.FCStd",
                  "source_sha256": SOURCE_SHA256, "model_revision": MODEL_REVISION,
                  "freecad": App.Version(),
                  "views": [{"id": view.BIM3117Id, "object_name": view.Name,
                             "name": view.Label, "definition": drawings._view_def(view)} for view in views],
                  "sheets": [{"id": sheet.BIM3117Id, "object_name": sheet.Name,
                              "name": sheet.Label, "number": sheet.Number,
                              "view_ids": list(sheet.ViewIds), **drawings.sheet_state(sheet)} for sheet in sheets],
                  "element_ids": {obj.Name: obj.BIM3117Id for obj in doc.Objects}}
        if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise ValueError("The frozen building source was unexpectedly modified")
        metadata_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if doc is not None:
            App.closeDocument(doc.Name)
        staging.cleanup()


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
