# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only material volumes partitioned from the authoritative native solids.

Layers are transverse bands of an existing product, never additional authored
products. Wall order follows local +Y; Slab order runs from its top downward.
No density, cost, global overlap deduction or unassigned material is inferred.
"""
import math

import FreeCAD as App
import Part

from .building import _box, wall_parameters
from .model import FoundationError, kind, mm

MATERIAL_RULE = "3117.material.native-solid-partition.v1"
TYPE_RULE = "3117.native-type-catalogue.v1"
DIMENSIONS = {"Wall": ("Thickness",), "Slab": ("Thickness",),
              "Column": ("Width", "Depth"), "Beam": ("Width", "Depth"),
              "Door": ("Width", "Height"), "Window": ("Width", "Height")}
PRODUCT_KINDS = tuple(DIMENSIONS)


def instance_type(obj):
    return getattr(obj, "WallType", None) if kind(obj) == "Wall" else getattr(obj, "ElementType", None)


def active(project):
    """Keep legacy export inventories unchanged until catalogue data is used."""
    return any(kind(obj) in ("Material", "ElementType") or
               (kind(obj) == "WallType" and any((getattr(obj, "Code", ""),
                    getattr(obj, "MaterialRefId", ""), getattr(obj, "LayerMaterialIds", []))))
               for obj in project.Group)


def type_fields(obj, si=True):
    """Optional additions to a legacy WallType, or all ElementType details."""
    category = "Wall" if kind(obj) == "WallType" else str(obj.Category)
    data = {}
    if kind(obj) == "ElementType":
        data.update(category=category, code=str(getattr(obj, "Code", "")))
        for prop in DIMENSIONS[category]:
            data[prop.lower() + ("_m" if si else "_mm")] = mm(obj, prop) / (1000.0 if si else 1.0)
    elif getattr(obj, "Code", ""):
        data["code"] = str(obj.Code)
    if getattr(obj, "MaterialRefId", ""):
        data["material_id"] = str(obj.MaterialRefId)
    ids = list(getattr(obj, "LayerMaterialIds", []))
    if ids:
        if any(len(values) != len(ids) for values in (obj.LayerMaterials, obj.LayerThicknesses, obj.LayerRoles)):
            raise FoundationError(obj.Label + ": material layer arrays have different lengths")
        data["layers"] = [{"material_id": str(identifier),
                           "thickness_m" if si else "thickness_mm": float(thickness) / (1000.0 if si else 1.0),
                           "role": str(role)}
                          for identifier, thickness, role in zip(ids, obj.LayerThicknesses, obj.LayerRoles)]
        if len(data["layers"]) != len(ids):
            raise FoundationError(obj.Label + ": material layer arrays have different lengths")
    return data


def type_rows(project, revision):
    from . import catalog
    products = [obj for obj in project.Group if kind(obj) in PRODUCT_KINDS]
    materials = {obj.BIM3117Id: obj for obj in project.Group if kind(obj) == "Material"}
    rows = []
    for typ in sorted((obj for obj in project.Group if kind(obj) in ("WallType", "ElementType")),
                      key=lambda obj: obj.BIM3117Id):
        data = catalog.type_definition(typ)
        layers = data.get("layers", [])
        row = {"type_id": typ.BIM3117Id, "type_name": typ.Label,
               "category": data["category"], "type_code": data.get("code", ""),
               "material_id": data.get("material_id", ""),
               "material_name": materials[data["material_id"]].Label if data.get("material_id") else "",
               "layer_count": len(layers),
               "instance_count": sum(instance_type(obj) == typ for obj in products),
               "quantity_rule": TYPE_RULE, "content_revision": revision}
        for prop in ("thickness", "width", "depth", "height"):
            row[prop + "_m"] = data[prop + "_mm"] / 1000.0 if prop + "_mm" in data else ""
        row["layers"] = [{"material_id": item["material_id"], "material_name": materials[item["material_id"]].Label,
                          "thickness_m": item["thickness_mm"] / 1000.0, "role": item["role"]}
                         for item in layers]
        rows.append(row)
    return rows


def row_type_fields(obj):
    """Common optional schedule columns, including deliberately blank values."""
    from . import catalog
    typ = instance_type(obj)
    if typ is None:
        return {"type_id": "", "type_name": "", "type_code": "", "material_id": "", "material_name": ""}
    data = catalog.type_definition(typ)
    return {"type_id": typ.BIM3117Id, "type_name": typ.Label, "type_code": data.get("code", ""),
            "material_id": data.get("material_id", ""),
            "material_name": typ.MaterialRef.Label if getattr(typ, "MaterialRef", None) else ""}


def _volume(shape, label):
    value = float(shape.Volume) / 1e9
    if not math.isfinite(value) or value < -1e-10:
        raise FoundationError(label + ": invalid material partition volume")
    return max(0.0, value)


def _same(actual, expected, label):
    if not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-9):
        raise FoundationError(label + ": material partitions do not conserve the native solid volume")


def capture(project, revision):
    """Return assigned material rows and explicit assignment coverage."""
    from . import catalog, elements, services
    products = sorted((obj for obj in project.Group if kind(obj) in PRODUCT_KINDS),
                      key=lambda obj: obj.BIM3117Id)
    rows, omissions, assigned = [], [], set()
    for obj in products:
        category, typ = kind(obj), instance_type(obj)
        data = catalog.type_definition(typ) if typ is not None else {}
        layer_data = data.get("layers", [])
        material = getattr(typ, "MaterialRef", None) if typ is not None else None
        if not layer_data and material is None:
            omissions.append({"element_id": obj.BIM3117Id, "name": obj.Label, "category": category,
                              "reason": "No native material assignment; legacy material text is not converted or quantified automatically."})
            continue
        if category == "Wall":
            values = wall_parameters(obj)
            gross = _box(values, 0, 0, 0, values["length"], values["thickness"], values["height"])
            net = services.wall_body(obj).Shape
            level = obj.BaseLevel
            deduction_kind = "openings"
        elif category in ("Slab", "Column", "Beam"):
            gross, net = elements.gross_solid(obj), obj.Shape
            level = obj.Level if category in ("Slab", "Beam") else obj.BaseLevel
            deduction_kind = "slab-priority joins" if category in ("Column", "Beam") else "none"
        else:
            gross = net = obj.Shape
            level = obj.Host.BaseLevel
            deduction_kind = "none; generic frame solid, not the wall opening"
        if layer_data:
            materials = list(typ.LayerMaterials)
            pieces = []
            offset = 0.0
            for index, layer in enumerate(layer_data):
                thickness = float(layer["thickness_mm"])
                if category == "Wall":
                    band = _box(values, 0, offset, 0, values["length"], thickness, values["height"])
                elif category == "Slab":
                    bounds = gross.BoundBox
                    top = elements.slab_parameters(obj)["top_z"]
                    band = Part.makeBox(bounds.XLength + 2.0, bounds.YLength + 2.0, thickness,
                                        App.Vector(bounds.XMin - 1.0, bounds.YMin - 1.0, top - offset - thickness))
                else:
                    raise FoundationError(obj.Label + ": layers are supported only for Walls and Slabs")
                pieces.append((materials[index], index + 1, layer["role"], thickness / 1000.0,
                               gross.common(band), net.common(band)))
                offset += thickness
        else:
            pieces = [(material, 0, "homogeneous", "", gross, net)]
        element_rows = []
        for material_obj, index, role, thickness_m, gross_part, net_part in pieces:
            gross_volume, net_volume = _volume(gross_part, obj.Label), _volume(net_part, obj.Label)
            if net_volume > gross_volume and not math.isclose(net_volume, gross_volume, rel_tol=1e-8, abs_tol=1e-9):
                raise FoundationError(obj.Label + ": material net volume exceeds gross volume")
            definition = catalog.material_definition(material_obj)
            element_rows.append({"element_id": obj.BIM3117Id, "object_name": obj.Name,
                                 "name": obj.Label, "category": category,
                                 "level_id": level.BIM3117Id, "level": level.Label,
                                 "type_id": typ.BIM3117Id, "type_name": typ.Label,
                                 "material_id": definition["id"], "material_name": definition["name"],
                                 "material_code": definition.get("code", ""),
                                 "layer_index": index, "layer_role": role, "thickness_m": thickness_m,
                                 "gross_volume_m3": gross_volume,
                                 "deduction_volume_m3": max(0.0, gross_volume - net_volume),
                                 "net_volume_m3": net_volume, "deduction_rule": deduction_kind,
                                 "quantity_rule": MATERIAL_RULE, "content_revision": revision})
        _same(math.fsum(row["gross_volume_m3"] for row in element_rows), _volume(gross, obj.Label), obj.Label)
        _same(math.fsum(row["net_volume_m3"] for row in element_rows), _volume(net, obj.Label), obj.Label)
        rows.extend(element_rows)
        assigned.add(obj.BIM3117Id)
    totals = {"row_count": len(rows), "assigned_product_count": len(assigned), "product_count": len(products),
              "unassigned_product_count": len(omissions), "unassigned_products": omissions,
              "gross_volume_m3": math.fsum(row["gross_volume_m3"] for row in rows),
              "deduction_volume_m3": math.fsum(row["deduction_volume_m3"] for row in rows),
              "net_volume_m3": math.fsum(row["net_volume_m3"] for row in rows),
              "complete": len(assigned) == len(products),
              "rule": MATERIAL_RULE,
              "scope": "Only native material assignments are quantified. Layer rows partition products and must not be added again to product quantities. No costs, densities or global overlap deductions are inferred."}
    return rows, totals
