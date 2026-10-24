# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only installed-host CSV/IFC regression from the canonical drawing FCStd.

Call main(output_dir, source_path, baseline_dir, expected_install_root=None) in
a fresh FreeCAD process. Exports go to a unique disposable case directory.
The native source and frozen v0.3.0 baseline are never saved or modified.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
import traceback

import FreeCAD as App

MODEL_REVISION = "6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a"
SOURCE_SHA256 = "92b6cd2fc012ce1ae2815ed511bed2c676451c0a2d8c9b2caa1823eeba81882c"
BASELINE_IFC_SHA256 = "775b5a63592d05c63c14fb63d258d6a30ae45558d6d6f244cf75f387279ac609"
BASELINE_SNAPSHOT_SHA256 = "ee8435eb0bf2ba197fe8c67e97187656dd8929ef56069949532794a666a729b0"
CATEGORIES = (("wall", "IfcWall", 8, ""), ("door", "IfcDoor", 2, "_doors"),
              ("slab", "IfcSlab", 3, "_slabs"), ("column", "IfcColumn", 8, "_columns"),
              ("beam", "IfcBeam", 8, "_beams"), ("window", "IfcWindow", 4, "_windows"))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def observation(project, snapshot, drawings, kind):
    """Observe authoritative values, links, all native BReps and Undo/Redo."""
    doc = project.Document
    objects = []
    for obj in doc.Objects:
        item = {"name": obj.Name, "label": obj.Label, "kind": kind(obj),
                "id": getattr(obj, "BIM3117Id", ""),
                "group": [child.Name for child in getattr(obj, "Group", [])]}
        if "Shape" in obj.PropertiesList:
            item["brep_sha256"] = hashlib.sha256(obj.Shape.exportBrepToString().encode("utf-8")).hexdigest()
        if kind(obj) in ("DrawingSet", "DrawingView", "DrawingSheet"):
            for name in ("ProjectId", "LevelId", "DrawingSchema", "BIM3117Version", "ViewType", "Direction",
                         "BottomOffset", "CutOffset", "TopOffset", "Depth", "ScaleDenominator",
                         "ShowDimensions", "ShowTags", "ShowGrid", "ShowLevels", "Number", "Issue", "Author",
                         "Paper", "Orientation", "ViewIds", "ValidationMessage"):
                if name in obj.PropertiesList:
                    value = getattr(obj, name)
                    item[name] = float(value.Value) if hasattr(value, "Value") else value
            for name in ("Project", "Level"):
                if name in obj.PropertiesList:
                    item[name] = getattr(getattr(obj, name), "Name", None)
            if "Origin" in obj.PropertiesList:
                item["origin"] = [obj.Origin.x, obj.Origin.y, obj.Origin.z]
            if "Views" in obj.PropertiesList:
                item["views"] = [view.Name for view in obj.Views]
        objects.append(item)
    return {"authored": snapshot._authored(project), "objects": objects,
            "sheets": {sheet.Number: drawings.sheet_state(sheet) for sheet in drawings.list_sheets(project)},
            "undo_count": doc.UndoCount, "redo_count": doc.RedoCount}


def mesh_evidence(product, geom, settings):
    """Independent world-mesh fingerprint, invariant to vertex/face ordering."""
    shape = geom.create_shape(settings, product)
    flat = list(shape.geometry.verts)
    faces = list(shape.geometry.faces)
    points = [tuple(float(value) for value in flat[index:index + 3]) for index in range(0, len(flat), 3)]
    assert points and faces and len(faces) % 3 == 0
    triangles = []
    volume_terms = []
    area_terms = []
    origin = points[0]
    for index in range(0, len(faces), 3):
        vertices = [points[faces[index + j]] for j in range(3)]
        triangles.append(sorted(tuple(round(value, 9) for value in point) for point in vertices))
        a, b, c = [tuple(point[j] - origin[j] for j in range(3)) for point in vertices]
        volume_terms.append((a[0] * (b[1] * c[2] - b[2] * c[1])
                             - a[1] * (b[0] * c[2] - b[2] * c[0])
                             + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0)
        u = tuple(vertices[1][j] - vertices[0][j] for j in range(3))
        v = tuple(vertices[2][j] - vertices[0][j] for j in range(3))
        cross = (u[1]*v[2] - u[2]*v[1], u[2]*v[0] - u[0]*v[2], u[0]*v[1] - u[1]*v[0])
        area_terms.append(math.sqrt(sum(value * value for value in cross)) / 2.0)
    return {"global_id": product.GlobalId, "ifc_class": product.is_a(), "name": product.Name,
            "world_triangle_sha256_1e_9_m": value_hash(sorted(triangles)), "triangles": len(triangles),
            "bounds_m": [min(p[j] for p in points) for j in range(3)] + [max(p[j] for p in points) for j in range(3)],
            "volume_m3": abs(math.fsum(volume_terms)), "surface_area_m2": math.fsum(area_terms)}


def without_step_ids(value):
    if isinstance(value, dict):
        return {key: without_step_ids(item) for key, item in value.items() if key != "id"}
    if isinstance(value, (list, tuple)):
        return [without_step_ids(item) for item in value]
    return value


def main(output_dir, source_path, baseline_dir, expected_install_root=None):
    output, source, baseline = Path(output_dir), Path(source_path), Path(baseline_dir)
    output.mkdir(parents=True, exist_ok=True)
    case = Path(tempfile.mkdtemp(prefix="drawings-exchange-case-", dir=output))
    report = {"status": "running", "freecad": App.Version(), "python": sys.version,
              "platform": platform.platform(), "gui_up": bool(App.GuiUp), "checks": [],
              "scope": "Read-only canonical v0.4.0 drawing FCStd exported to CSV/IFC through the installed workbench; comparison with frozen v0.3.0 quantities, IDs and geometry",
              "source": str(source), "baseline": str(baseline), "case_directory": str(case),
              "windows_runtime_executed": False, "bonsai_executed": False}
    doc = None

    def check(name, condition, **details):
        if not condition:
            raise AssertionError(name + (": " + json.dumps(details, ensure_ascii=False) if details else ""))
        report["checks"].append({"name": name, "status": "passed", **details})

    try:
        source_before = file_hash(source)
        baseline_files = {p.name: file_hash(p) for p in baseline.iterdir() if p.is_file() and p.suffix.lower() != ".md"}
        check("canonical FCStd and legacy IFC/snapshot match the frozen regression inputs",
              source_before == SOURCE_SHA256
              and file_hash(baseline / "Building_Authoring_Workbench.ifc") == BASELINE_IFC_SHA256
              and file_hash(baseline / "building-snapshot.json") == BASELINE_SNAPSHOT_SHA256)
        check("fresh headless FreeCAD 1.1.4 has not preloaded drawing or building proxies",
              tuple(App.Version()[:3]) == ("1", "1", "4") and not App.GuiUp
              and "bim3117_freecad.drawings" not in sys.modules and "bim3117_freecad.elements" not in sys.modules)
        doc = App.openDocument(str(source))
        doc.recompute()
        from bim3117_freecad import __version__, drawings, exchange, ifc_native, services, snapshot
        from bim3117_freecad.model import DOCUMENTATION_KINDS, kind
        installed = (Path(App.getUserAppDataDir()) / "Mod" / "BIM3117").resolve()
        if expected_install_root is not None:
            check("native host resolves the exact frozen v0.4.0 install root", installed == Path(expected_install_root).resolve())
        receipt = json.loads((installed / "bim3117-install.json").read_text(encoding="utf-8"))
        check("all production modules and installed payload bytes match the v0.4.0 receipt",
              __version__ == receipt["version"] == "0.4.0"
              and all(Path(module.__file__).resolve().is_relative_to(installed)
                      for module in (drawings, exchange, ifc_native, services, snapshot))
              and all(file_hash(installed / name) == sha for name, sha in receipt["sha256"].items()))
        report["installed_root"] = str(installed)
        report["installed_payload_sha256"] = receipt["sha256"]
        project = services.get_project(doc)
        fixture = json.loads(source.with_name("drawings-example.json").read_text(encoding="utf-8"))
        old = json.loads((baseline / "building-snapshot.json").read_text(encoding="utf-8"))
        data = snapshot.capture(project)
        before = observation(project, snapshot, drawings, kind)
        documented = [item for item in data["coverage"]["items"] if item["kind"] in DOCUMENTATION_KINDS]
        check("all native identities restore with four Views and two Sheets at the legacy model revision",
              {obj.Name: obj.BIM3117Id for obj in doc.Objects} == fixture["element_ids"]
              and len(drawings.list_views(project)) == 4 and len(drawings.list_sheets(project)) == 2
              and data["content_revision"] == old["content_revision"] == MODEL_REVISION)
        check("seven drawing definitions remain explicit coverage references with no quantity or IFC role",
              len(documented) == 7 and all(item["status"] == "reference" and item["quantity_role"] == "none"
                                         and not item["ifc_class"] for item in documented)
              and data["coverage"]["counts"]["unsupported"] == 0,
              drawing_reference_count=len(documented), coverage_counts=data["coverage"]["counts"])
        counts = {category: len(data[category + "_rows"]) for category, _, _, _ in CATEGORIES}
        check("all 33 product quantity rows and totals equal the frozen v0.3.0 snapshot",
              sum(counts.values()) == 33 and all(counts[category] == expected for category, _, expected, _ in CATEGORIES)
              and all(data[category + "_rows"] == old[category + "_rows"] for category, _, _, _ in CATEGORIES)
              and data["totals"] == old["totals"], product_counts=counts)
        csv_result = exchange.export_csv(project, case / "Drawings_Workbench.csv", expected_revision=MODEL_REVISION)
        csv_meta = json.loads(Path(csv_result["metadata_path"]).read_text(encoding="utf-8"))
        csv_comparisons = []
        exported_ids = set()
        for category, _, expected, suffix in CATEGORIES:
            new_path = case / ("Drawings_Workbench" + suffix + ".csv")
            old_path = baseline / ("Building_Authoring_Workbench" + suffix + ".csv")
            with new_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            exported_ids.update(row["element_id"] for row in rows)
            csv_comparisons.append({"category": category, "rows": len(rows), "sha256": file_hash(new_path),
                                    "byte_identical": new_path.read_bytes() == old_path.read_bytes()})
        check("all six CSV payloads are byte-identical to frozen v0.3.0 quantities",
              len(exported_ids) == 33 and all(item["byte_identical"] for item in csv_comparisons),
              payloads=csv_comparisons)
        check("CSV metadata retains legacy revision and the seven omitted drawing references",
              csv_meta["content_revision"] == csv_meta["snapshot"]["content_revision"] == MODEL_REVISION
              and csv_meta["validation"]["status"] == "passed" and csv_meta["coverage"] == data["coverage"]
              and not exported_ids.intersection(item["object_id"] for item in documented))
        ifc_result = exchange.export_ifc(project, case / "Drawings_Workbench.ifc", expected_revision=MODEL_REVISION)
        ifc_meta = json.loads(Path(ifc_result["metadata_path"]).read_text(encoding="utf-8"))
        validation = ifc_meta["validation"]
        check("published IFC passes its staged schema, placement, opening and joined-solid readback validation",
              validation["status"] == "passed" and validation["checks_passed"] == len(validation["checks"])
              and all(item["status"] == "passed" for item in validation["checks"]),
              native_export_validation_checks=validation["checks_passed"])
        import ifcopenshell
        import ifcopenshell.geom as geom
        import ifcopenshell.util.element as element
        import ifcopenshell.util.placement as placement
        previous = ifcopenshell.open(str(baseline / "Building_Authoring_Workbench.ifc"))
        current = ifcopenshell.open(str(case / "Drawings_Workbench.ifc"))
        report["ifcopenshell_version"] = str(ifcopenshell.version)
        products = [product for _, cls, _, _ in CATEGORIES for product in current.by_type(cls)]
        ifc_counts = {cls: len(current.by_type(cls)) for _, cls, _, _ in CATEGORIES}
        check("IFC contains exactly 33 products and preserves every product/opening GlobalId",
              current.schema == "IFC4" and len(products) == 33
              and all(ifc_counts[cls] == expected for _, cls, expected, _ in CATEGORIES)
              and all({p.GlobalId for p in current.by_type(cls)} == {p.GlobalId for p in previous.by_type(cls)}
                      for cls in [item[1] for item in CATEGORIES] + ["IfcOpeningElement"]), product_counts=ifc_counts)
        root_ids = {obj.GlobalId for obj in current.by_type("IfcRoot")}
        check("drawing definitions are absent from IFC entities while their omissions remain in metadata",
              not root_ids.intersection(ifc_native.global_id(item["object_id"]) for item in documented)
              and not current.by_type("IfcAnnotation") and ifc_meta["coverage"] == data["coverage"]
              and ifc_meta["content_revision"] == ifc_meta["snapshot"]["content_revision"] == MODEL_REVISION)
        settings = geom.settings()
        settings.set("use-world-coords", True)
        geometry = []
        quantities_match = True
        placements_match = True
        source_match = True
        native_volume_match = True
        native_products = {obj.BIM3117Id: (services.wall_body(obj) if kind(obj) == "Wall" else obj)
                           for obj in doc.Objects if kind(obj) in ("Wall", "Door", "Slab", "Column", "Beam", "Window")}
        for product in sorted(products, key=lambda item: item.GlobalId):
            original = previous.by_guid(product.GlobalId)
            quantities_match = quantities_match and (without_step_ids(element.get_psets(product, qtos_only=True))
                == without_step_ids(element.get_psets(original, qtos_only=True)))
            p0, p1 = placement.get_local_placement(original.ObjectPlacement), placement.get_local_placement(product.ObjectPlacement)
            placements_match = placements_match and all(math.isclose(float(p0[i, j]), float(p1[i, j]), abs_tol=1e-9)
                                                       for i in range(4) for j in range(4))
            props = element.get_psets(product).get("BIM3117_Source", {})
            source_match = source_match and props.get("ContentRevision") == MODEL_REVISION and props.get("SourceUUID") in native_products
            a, b = mesh_evidence(original, geom, settings), mesh_evidence(product, geom, settings)
            matches = (a["world_triangle_sha256_1e_9_m"] == b["world_triangle_sha256_1e_9_m"]
                       and math.isclose(a["volume_m3"], b["volume_m3"], rel_tol=1e-8, abs_tol=1e-9)
                       and math.isclose(a["surface_area_m2"], b["surface_area_m2"], rel_tol=1e-8, abs_tol=1e-9)
                       and all(math.isclose(x, y, abs_tol=1e-9) for x, y in zip(a["bounds_m"], b["bounds_m"])))
            native = native_products[props["SourceUUID"]]
            native_volume_match = native_volume_match and math.isclose(native.Shape.Volume / 1e9, b["volume_m3"], rel_tol=1e-7, abs_tol=1e-8)
            geometry.append({**b, "source_uuid": props["SourceUUID"], "matches_frozen_v030": matches})
        check("IFC quantities and world placements match all frozen v0.3.0 products", quantities_match and placements_match)
        check("all 33 IFC world surfaces preserve the frozen opening and join geometry",
              len(geometry) == 33 and all(item["matches_frozen_v030"] for item in geometry),
              method="Normalized world-coordinate triangle fingerprints rounded to 1e-9 m, plus volume, surface area and bounds")
        check("every IFC product carries the same native source UUID/revision and matches native solid volume",
              source_match and native_volume_match)
        for metadata in (csv_meta, ifc_meta):
            check("exact payload hashes agree with completion metadata for " + metadata["format"],
                  all(file_hash(case / item["name"]) == item["sha256"]
                      and (case / item["name"]).stat().st_size == item["bytes"] for item in metadata["files"]))
        check("CSV/IFC export preserves all native BReps, drawing definitions, IDs, revisions and Undo/Redo history",
              observation(project, snapshot, drawings, kind) == before
              and snapshot.capture(project)["content_revision"] == MODEL_REVISION)
        check("canonical FCStd and all historical baseline files remain byte-identical after export",
              file_hash(source) == source_before
              and all(file_hash(baseline / name) == value for name, value in baseline_files.items()))
        artifacts = sorted(case.iterdir())
        expected = {Path(path).name for result in (csv_result, ifc_result) for path in result["files"]}
        check("publication leaves only the nine completed CSV/IFC payload and metadata files",
              len(artifacts) == 9 and {path.name for path in artifacts} == expected)
        report.update(status="passed", model_revision=MODEL_REVISION, source_sha256_before=source_before,
                      source_sha256_after=file_hash(source), baseline_sha256=baseline_files,
                      native_observation_sha256=value_hash(before), documented_references=documented,
                      csv_payload_comparison=csv_comparisons, ifc_geometry=geometry,
                      csv_result=csv_result, ifc_result=ifc_result,
                      artifact_sha256={str(path): file_hash(path) for path in artifacts})
        return report
    except BaseException as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        report["checks_passed"] = len(report["checks"])
        if doc is not None:
            App.closeDocument(doc.Name)
        (output / "drawings-exchange-test-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
