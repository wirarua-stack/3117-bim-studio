# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent native materials, shared element types and atomic instance edits.

The FCStd properties remain the only authoring authority. Proposed changes are
validated using transient OCCT solids and value dictionaries before a document
transaction is opened. Shared types may change several cutters or openings at
once; every proposal is evaluated against the same complete proposed state.
"""
import math

import FreeCAD as App

from .model import (FoundationError, _BaseProxy, _common, _link_project,
                    _property, kind, mm, number, text, validate_object)

_UNCHANGED = object()
CATEGORIES = ("Wall", "Slab", "Column", "Beam", "Door", "Window")
INSTANCE_KINDS = CATEGORIES
TYPE_KINDS = ("WallType", "ElementType")
DIMENSIONS = {"Wall": ("Thickness",), "Slab": ("Thickness",),
              "Column": ("Width", "Depth"), "Beam": ("Width", "Depth"),
              "Door": ("Width", "Height"), "Window": ("Width", "Height")}
DIMENSION_KEYS = {"Thickness": "thickness_mm", "Width": "width_mm",
                  "Depth": "depth_mm", "Height": "height_mm"}
DEFAULTS = {"Wall": (200.0,), "Slab": (150.0,), "Column": (300.0, 300.0),
            "Beam": (300.0, 450.0), "Door": (900.0, 2100.0),
            "Window": (1200.0, 1200.0)}
CATALOG_PROPERTIES = ("Code", "MaterialRef", "MaterialRefId", "LayerMaterials",
                      "LayerMaterialIds", "LayerThicknesses", "LayerRoles")
LAYER_PROPERTIES = ("LayerMaterials", "LayerMaterialIds", "LayerThicknesses", "LayerRoles")


def category_of_type(type_obj):
    if kind(type_obj) == "WallType":
        return "Wall"
    if kind(type_obj) == "ElementType" and str(type_obj.Category) in CATEGORIES[1:]:
        return str(type_obj.Category)
    raise FoundationError("Select a 3117 WallType or ElementType")


def _require_project_member(obj, expected, project):
    if (kind(obj) != expected or obj.Document != project.Document
            or getattr(obj, "Project", None) != project or obj not in project.Group):
        raise FoundationError(f"{expected} must belong to the same project")
    validate_object(obj)
    return obj


def material_definition(material):
    if kind(material) != "Material":
        raise FoundationError("Select a 3117 material")
    validate_object(material)
    return {"id": material.BIM3117Id, "name": material.Label, "code": material.Code}


def _unique_code(project, code, type_kind, except_obj=None):
    if not code:
        return
    kinds = ("Material",) if type_kind == "Material" else TYPE_KINDS
    if any(obj != except_obj and kind(obj) in kinds and getattr(obj, "Code", "") == code
           for obj in project.Group):
        raise FoundationError(f"A {'material' if type_kind == 'Material' else 'type'} with code '{code}' already exists")


def _material_link(type_obj):
    material = getattr(type_obj, "MaterialRef", None)
    identifier = getattr(type_obj, "MaterialRefId", "")
    if material is None:
        if identifier:
            raise FoundationError(f"{type_obj.Label}: native material is missing; reassign it in the catalogue")
        return None
    _require_project_member(material, "Material", type_obj.Project)
    if identifier != material.BIM3117Id:
        raise FoundationError(f"{type_obj.Label}: material identity is inconsistent")
    return material


def layer_definitions(type_obj):
    """Return ordered layer DTOs with native Material references for editing."""
    category = category_of_type(type_obj)
    materials = list(getattr(type_obj, "LayerMaterials", []))
    identifiers = list(getattr(type_obj, "LayerMaterialIds", []))
    thicknesses = list(getattr(type_obj, "LayerThicknesses", []))
    roles = list(getattr(type_obj, "LayerRoles", []))
    if len({len(materials), len(identifiers), len(thicknesses), len(roles)}) != 1:
        raise FoundationError(f"{type_obj.Label}: material layer references are missing or inconsistent")
    if materials and category not in ("Wall", "Slab"):
        raise FoundationError("Only Wall and Slab types support ordered material layers")
    result = []
    for material, identifier, thickness, role in zip(materials, identifiers, thicknesses, roles):
        _require_project_member(material, "Material", type_obj.Project)
        if identifier != material.BIM3117Id:
            raise FoundationError(f"{type_obj.Label}: layer material identity is inconsistent")
        result.append({"material": material,
                       "thickness_mm": number(thickness, "Layer thickness", positive=True),
                       "role": text(role, "Layer role")})
    return result


def validate_catalog_object(obj):
    if kind(obj) == "Material":
        code = text(obj.Code, "Material code")
        if code != obj.Code:
            raise FoundationError("Material code must not have leading or trailing spaces")
        _unique_code(obj.Project, code, "Material", obj)
        return
    category = category_of_type(obj)
    code = text(getattr(obj, "Code", ""), "Type code")
    if code != getattr(obj, "Code", ""):
        raise FoundationError("Type code must not have leading or trailing spaces")
    _unique_code(obj.Project, code, "ElementType", obj)
    material, layers = _material_link(obj), layer_definitions(obj)
    if material is not None and layers:
        raise FoundationError("A type must use either one homogeneous material or ordered layers")
    for prop in DIMENSIONS[category]:
        number(mm(obj, prop), category + " " + prop.lower(), positive=True)
    if layers and abs(mm(obj, "Thickness") - math.fsum(layer["thickness_mm"] for layer in layers)) > 1e-7:
        raise FoundationError("Layered type thickness is the sum of its ordered layers")
    text(getattr(obj, "Material", ""), "Material")


def type_definition(type_obj):
    validate_object(type_obj)
    category = category_of_type(type_obj)
    material = _material_link(type_obj)
    result = {"id": type_obj.BIM3117Id, "name": type_obj.Label,
              "code": getattr(type_obj, "Code", ""), "category": category}
    result.update({DIMENSION_KEYS[prop]: mm(type_obj, prop) for prop in DIMENSIONS[category]})
    result["material_id"] = material.BIM3117Id if material is not None else ""
    result["layers"] = [{"material_id": layer["material"].BIM3117Id,
                         "thickness_mm": layer["thickness_mm"], "role": layer["role"]}
                        for layer in layer_definitions(type_obj)]
    return result


def instance_type(obj):
    category = kind(obj)
    if category not in INSTANCE_KINDS:
        raise FoundationError("Only building products can be assigned a catalogue type")
    prop = "WallType" if category == "Wall" else "ElementType"
    target, identifier = getattr(obj, prop, None), getattr(obj, prop + "Id", "")
    if target is None:
        if category == "Wall" or identifier:
            raise FoundationError(f"{obj.Label}: {prop} is missing; assign or explicitly detach its type")
        return None
    expected = "WallType" if category == "Wall" else "ElementType"
    _require_project_member(target, expected, obj.Project)
    if identifier != target.BIM3117Id or category_of_type(target) != category:
        raise FoundationError(f"{obj.Label}: assigned type category or identity is inconsistent")
    return target


assigned_type = instance_type


def controlled_properties(obj):
    if kind(obj) in TYPE_KINDS:
        return tuple(DIMENSIONS[category_of_type(obj)]) + ("Material",)
    if kind(obj) not in INSTANCE_KINDS or instance_type(obj) is None:
        return ()
    return tuple(DIMENSIONS[kind(obj)]) + ("Material",)


def effective_dimension(obj, prop):
    if kind(obj) in TYPE_KINDS:
        validate_catalog_object(obj)
        return mm(obj, prop)
    if kind(obj) in INSTANCE_KINDS and prop in DIMENSIONS[kind(obj)]:
        target = instance_type(obj)
        if target is not None:
            return mm(target, prop)
    return mm(obj, prop)


def _type_material_text(type_obj, material=_UNCHANGED, layers=_UNCHANGED):
    material = _material_link(type_obj) if material is _UNCHANGED else material
    layers = layer_definitions(type_obj) if layers is _UNCHANGED else layers
    if material is not None:
        return material.Label
    if layers:
        return " / ".join(layer["material"].Label for layer in layers)
    return getattr(type_obj, "Material", "") if kind(type_obj) == "WallType" else ""


def effective_material(obj):
    if kind(obj) in TYPE_KINDS:
        return _type_material_text(obj)
    if kind(obj) in INSTANCE_KINDS:
        target = instance_type(obj)
        if target is not None:
            return _type_material_text(target)
    return getattr(obj, "Material", "")


def _add_catalog_properties(obj):
    from .building import _add_reference
    if "Code" not in obj.PropertiesList:
        _property(obj, "App::PropertyString", "Code", "Type catalogue", "Optional catalogue code", "")
    if "MaterialRef" not in obj.PropertiesList:
        _add_reference(obj, "MaterialRef", "Material")
    for prop, native_type, tooltip in (
            ("LayerMaterials", "App::PropertyLinkList", "Ordered native materials; use the catalogue"),
            ("LayerMaterialIds", "App::PropertyStringList", "Expected layer material UUIDs"),
            ("LayerThicknesses", "App::PropertyFloatList", "Ordered layer thicknesses in millimetres"),
            ("LayerRoles", "App::PropertyStringList", "Ordered layer function labels")):
        if prop not in obj.PropertiesList:
            _property(obj, native_type, prop, "Material layers", tooltip, [], True)


def initialize_instance(obj):
    """Add optional type links only to newly created or explicitly typed objects."""
    if kind(obj) not in CATEGORIES[1:]:
        return
    from .building import _add_reference
    if "ElementType" not in obj.PropertiesList:
        _add_reference(obj, "ElementType", "ElementType")
    if "Material" not in obj.PropertiesList:
        _property(obj, "App::PropertyString", "Material", "Material", "Material resolved from the assigned type", "")


def _mode(obj, prop, derived):
    if prop not in obj.PropertiesList:
        return
    obj.setEditorMode(prop, 1 if derived else 0)
    # A derived cache must not re-touch its owner while execute() updates it.
    obj.setPropertyStatus(prop, "Output" if derived else "-Output")


def restore_catalog_modes(obj):
    category = kind(obj)
    if category in CATEGORIES[1:]:
        assigned = getattr(obj, "ElementType", None) is not None or bool(getattr(obj, "ElementTypeId", ""))
        for prop in DIMENSIONS[category] + ("Material",):
            _mode(obj, prop, assigned)
        for prop in ("ElementType", "ElementTypeId"):
            if prop in obj.PropertiesList:
                obj.setEditorMode(prop, 1)
    elif category in TYPE_KINDS:
        for prop in ("MaterialRef", "MaterialRefId") + LAYER_PROPERTIES:
            if prop in obj.PropertiesList:
                obj.setEditorMode(prop, 1)
        if "Category" in obj.PropertiesList:
            obj.setEditorMode("Category", 1)
        if category_of_type(obj) in ("Wall", "Slab"):
            _mode(obj, "Thickness", bool(getattr(obj, "LayerMaterialIds", [])))
        _mode(obj, "Material", category == "ElementType" or bool(getattr(obj, "MaterialRefId", "") or getattr(obj, "LayerMaterialIds", [])))


def sync_instance(obj):
    if kind(obj) not in CATEGORIES[1:]:
        return
    target = instance_type(obj)
    restore_catalog_modes(obj)
    if target is None:
        return
    proxy = obj.Proxy
    previous = getattr(proxy, "_restoring_value", False)
    proxy._restoring_value = True
    try:
        for prop in DIMENSIONS[kind(obj)]:
            value = effective_dimension(obj, prop)
            if mm(obj, prop) != value:
                setattr(obj, prop, value)
        if obj.Material != effective_material(obj):
            obj.Material = effective_material(obj)
    finally:
        proxy._restoring_value = previous


def sync_type(obj):
    if kind(obj) not in TYPE_KINDS:
        return
    restore_catalog_modes(obj)
    material, layers = _material_link(obj), layer_definitions(obj)
    if material is not None or layers or kind(obj) == "ElementType":
        value = _type_material_text(obj, material, layers)
        if obj.Material != value:
            previous = getattr(obj.Proxy, "_restoring_value", False)
            obj.Proxy._restoring_value = True
            try:
                obj.Material = value
            finally:
                obj.Proxy._restoring_value = previous


def validate_raw_edit(obj, prop):
    """Additional Property Editor guard; supported services bypass callbacks."""
    category = kind(obj)
    if category in TYPE_KINDS:
        if prop in LAYER_PROPERTIES or prop == "Category":
            raise FoundationError("Edit material layers and type category through the catalogue")
        if prop == "Material" and (category == "ElementType" or getattr(obj, "MaterialRefId", "") or getattr(obj, "LayerMaterialIds", [])):
            raise FoundationError("Material is derived from the native material assignment")
    elif category in CATEGORIES[1:] and prop in DIMENSIONS[category] + ("Material",):
        target = instance_type(obj)
        if target is not None:
            expected = effective_material(obj) if prop == "Material" else effective_dimension(obj, prop)
            actual = getattr(obj, prop) if prop == "Material" else mm(obj, prop)
            if actual != expected:
                raise FoundationError(f"{prop} is controlled by shared type '{target.Label}'; edit the type or detach it")


class MaterialProxy(_BaseProxy):
    editable = ("Label", "Code")

    def __init__(self, obj, project):
        self._start(obj)
        _common(obj, "Material")
        _link_project(obj, project)
        _property(obj, "App::PropertyString", "Code", "Material catalogue", "Optional unique material code", "")
        self._finish(obj)

    def build(self, obj):
        pass


class ElementTypeProxy(_BaseProxy):
    editable = ("Label", "Code", "Category", "Thickness", "Width", "Depth", "Height", "Material",
                "MaterialRef", "LayerMaterials", "LayerMaterialIds", "LayerThicknesses", "LayerRoles")
    reference_properties = {"MaterialRef": "Material"}

    def __init__(self, obj, project, category):
        self._start(obj)
        _common(obj, "ElementType")
        _link_project(obj, project)
        obj.addProperty("App::PropertyEnumeration", "Category", "Type catalogue", "Immutable product category")
        obj.Category = list(CATEGORIES[1:])
        obj.Category = category
        obj.setEditorMode("Category", 1)
        for prop, default in zip(DIMENSIONS[category], DEFAULTS[category]):
            _property(obj, "App::PropertyLength", prop, "Type dimensions", "Shared " + prop.lower(), default)
        _property(obj, "App::PropertyString", "Material", "Type catalogue", "Calculated native material description", "", True)
        _add_catalog_properties(obj)
        self._finish(obj)

    def build(self, obj):
        sync_type(obj)


def list_materials(project):
    from .services import _require
    _require(project, "Project")
    return [obj for obj in project.Group if kind(obj) == "Material"]


def list_types(project, category=None):
    from .services import _require
    _require(project, "Project")
    if category is not None and category not in CATEGORIES:
        raise FoundationError("Unsupported type category")
    return [obj for obj in project.Group if kind(obj) in TYPE_KINDS
            and (category is None or category_of_type(obj) == category)]


def material_dependents(material):
    if kind(material) != "Material":
        raise FoundationError("Select a 3117 material")
    return [obj for obj in material.Document.Objects if kind(obj) in TYPE_KINDS
            and (getattr(obj, "MaterialRef", None) == material
                 or getattr(obj, "MaterialRefId", "") == material.BIM3117Id
                 or material in getattr(obj, "LayerMaterials", [])
                 or material.BIM3117Id in getattr(obj, "LayerMaterialIds", []))]


def type_dependents(type_obj):
    category_of_type(type_obj)
    identifier = type_obj.BIM3117Id
    result = []
    for obj in type_obj.Document.Objects:
        if kind(obj) in INSTANCE_KINDS:
            prop = "WallType" if kind(obj) == "Wall" else "ElementType"
            if getattr(obj, prop, None) == type_obj or getattr(obj, prop + "Id", "") == identifier:
                result.append(obj)
        elif kind(obj) == "Schedule" and (getattr(obj, "FilterType", None) == type_obj
                                          or getattr(obj, "FilterTypeId", "") == identifier):
            result.append(obj)
    return result


def invalidate_catalog_dependents(obj, message):
    from .building import clear_calculated_shape, invalidate_related
    types = material_dependents(obj) if kind(obj) == "Material" else [obj]
    for type_obj in types:
        type_obj.ValidationMessage = message
        for product in type_dependents(type_obj):
            if kind(product) in INSTANCE_KINDS:
                clear_calculated_shape(product, message)
                invalidate_related(product, message)


def create_material(project, name, code=""):
    from .services import _require, _unique_name, _transaction, _style
    _require(project, "Project")
    name, code = text(name, "Material name", required=True), text(code, "Material code")
    _unique_name(project, "Material", name)
    _unique_code(project, code, "Material")
    with _transaction(project.Document, "3117 Create material"):
        obj = project.Document.addObject("App::FeaturePython", "BIM3117_Material")
        MaterialProxy(obj, project)
        obj.Label, obj.Code = name, code
        project.addObject(obj)
        _style(obj)
    return obj


def edit_material(material, name=None, code=None):
    from .services import _require, _unique_name, _transaction
    _require(material, "Material")
    name = material.Label if name is None else text(name, "Material name", required=True)
    code = material.Code if code is None else text(code, "Material code")
    _unique_name(material.Project, "Material", name, material)
    _unique_code(material.Project, code, "Material", material)
    preflight(material.Project)
    with _transaction(material.Document, "3117 Edit material"):
        material.Label, material.Code = name, code
        for type_obj in material_dependents(material):
            sync_type(type_obj)
        _sync_project_instances(material.Project)
    return material


def duplicate_material(material, name):
    """Copy a material identity as a new catalogue entry with an empty code."""
    from .services import _require
    _require(material, "Material")
    return create_material(material.Project, name, code="")


def delete_material(material):
    from .services import _require, _transaction
    _require(material, "Material", validate=False)
    dependents = material_dependents(material)
    if dependents:
        raise FoundationError("Material is used by: " + ", ".join(obj.Label for obj in dependents))
    document, project, name = material.Document, material.Project, material.Name
    with _transaction(document, "3117 Delete material"):
        project.removeObject(material)
        document.removeObject(name)


def _validated_layers(project, category, layers):
    if layers is None:
        return []
    if isinstance(layers, (str, bytes, dict)):
        raise FoundationError("Layers must be an ordered sequence of material/thickness/role records")
    try:
        layers = list(layers)
    except TypeError as error:
        raise FoundationError("Layers must be an ordered sequence") from error
    if layers and category not in ("Wall", "Slab"):
        raise FoundationError("Only Wall and Slab types support ordered material layers")
    result = []
    for layer in layers:
        if not isinstance(layer, dict) or set(layer) - {"material", "thickness_mm", "role"}:
            raise FoundationError("Each layer must contain material, thickness_mm and optional role")
        material = _require_project_member(layer.get("material"), "Material", project)
        result.append({"material": material,
                       "thickness_mm": number(layer.get("thickness_mm"), "Layer thickness", positive=True),
                       "role": text(layer.get("role", ""), "Layer role")})
    return result


def _type_proposal(project, name, category, dimensions, material, layers, code, current=None):
    from .services import _unique_name
    if category not in CATEGORIES:
        raise FoundationError("Unsupported type category")
    name, code = text(name, "Type name", required=True), text(code, "Type code")
    _unique_name(project, "WallType" if category == "Wall" else "ElementType", name, current)
    _unique_code(project, code, "ElementType", current)
    if material is not None:
        _require_project_member(material, "Material", project)
    layers = _validated_layers(project, category, layers)
    if material is not None and layers:
        raise FoundationError("Choose either a homogeneous material or ordered layers")
    values = {}
    for prop in ("Thickness", "Width", "Depth", "Height"):
        supplied = dimensions.get(prop)
        if prop not in DIMENSIONS[category]:
            if supplied is not None:
                raise FoundationError(f"{category} types do not have a {prop.lower()} dimension")
            continue
        if supplied is None:
            supplied = mm(current, prop) if current is not None else DEFAULTS[category][DIMENSIONS[category].index(prop)]
        values[prop] = number(supplied, category + " " + prop.lower(), positive=True)
    if layers:
        total = number(math.fsum(layer["thickness_mm"] for layer in layers), "Total layer thickness", positive=True)
        if dimensions.get("Thickness") is not None and abs(values["Thickness"] - total) > 1e-7:
            raise FoundationError("Thickness must equal the sum of the material layers")
        values["Thickness"] = total
    return {"name": name, "category": category, "code": code, "dimensions": values,
            "material": material, "layers": layers}


def _write_type(obj, proposal, clear_legacy=False):
    _add_catalog_properties(obj)
    obj.Label, obj.Code = proposal["name"], proposal["code"]
    for prop, value in proposal["dimensions"].items():
        setattr(obj, prop, value)
    material, layers = proposal["material"], proposal["layers"]
    obj.MaterialRef = material
    obj.MaterialRefId = material.BIM3117Id if material is not None else ""
    obj.LayerMaterials = [layer["material"] for layer in layers]
    obj.LayerMaterialIds = [layer["material"].BIM3117Id for layer in layers]
    obj.LayerThicknesses = [layer["thickness_mm"] for layer in layers]
    obj.LayerRoles = [layer["role"] for layer in layers]
    if clear_legacy:
        obj.Material = ""
    sync_type(obj)


def create_type(project, name, category, thickness_mm=None, width_mm=None, depth_mm=None,
                height_mm=None, material=None, layers=None, code=""):
    from .services import _require, _transaction, _style
    from .building import WallTypeProxy
    _require(project, "Project")
    dimensions = dict(Thickness=thickness_mm, Width=width_mm, Depth=depth_mm, Height=height_mm)
    proposal = _type_proposal(project, name, category, dimensions, material, layers, code)
    with _transaction(project.Document, "3117 Create type"):
        native_kind = "WallType" if category == "Wall" else "ElementType"
        obj = project.Document.addObject("App::FeaturePython", "BIM3117_" + native_kind)
        if category == "Wall":
            WallTypeProxy(obj, project)
        else:
            ElementTypeProxy(obj, project, category)
        _write_type(obj, proposal)
        project.addObject(obj)
        _style(obj)
    return obj


def edit_type(type_obj, name=None, thickness_mm=None, width_mm=None, depth_mm=None,
              height_mm=None, material=_UNCHANGED, layers=_UNCHANGED, code=None):
    from .services import _transaction
    category = category_of_type(type_obj)
    # Explicit edits can repair missing material references, while dimensions and
    # unmodified layers are still read and checked from their native definitions.
    current_material = _material_link(type_obj) if material is _UNCHANGED else material
    current_layers = layer_definitions(type_obj) if layers is _UNCHANGED else layers
    proposal = _type_proposal(type_obj.Project, type_obj.Label if name is None else name, category,
                             dict(Thickness=thickness_mm, Width=width_mm, Depth=depth_mm, Height=height_mm),
                             current_material, current_layers, getattr(type_obj, "Code", "") if code is None else code,
                             type_obj)
    preflight(type_obj.Project, type_overrides={type_obj.BIM3117Id: proposal})
    clear_legacy = (material is not _UNCHANGED or layers is not _UNCHANGED) and bool(
        getattr(type_obj, "MaterialRefId", "") or getattr(type_obj, "LayerMaterialIds", []))
    with _transaction(type_obj.Document, "3117 Edit type"):
        _write_type(type_obj, proposal, clear_legacy=clear_legacy)
        _sync_project_instances(type_obj.Project)
    return type_obj


def duplicate_type(type_obj, name):
    from .services import _transaction, _style
    from .building import WallTypeProxy
    validate_object(type_obj)
    category = category_of_type(type_obj)
    dimensions = {prop: mm(type_obj, prop) for prop in DIMENSIONS[category]}
    proposal = _type_proposal(type_obj.Project, name, category, dimensions, _material_link(type_obj),
                             layer_definitions(type_obj), "")
    # A duplicate receives a new UUID and deliberately has no duplicate code.
    with _transaction(type_obj.Document, "3117 Duplicate type"):
        obj = type_obj.Document.addObject("App::FeaturePython", "BIM3117_" + kind(type_obj))
        if category == "Wall":
            WallTypeProxy(obj, type_obj.Project)
            obj.Material = type_obj.Material
        else:
            ElementTypeProxy(obj, type_obj.Project, category)
        _write_type(obj, proposal)
        type_obj.Project.addObject(obj)
        _style(obj)
    return obj


def delete_type(type_obj):
    from .services import _transaction
    category_of_type(type_obj)
    dependents = type_dependents(type_obj)
    if dependents:
        raise FoundationError("Type is used by: " + ", ".join(obj.Label for obj in dependents))
    document, project, name = type_obj.Document, type_obj.Project, type_obj.Name
    with _transaction(document, "3117 Delete type"):
        project.removeObject(type_obj)
        document.removeObject(name)


def _sync_project_instances(project):
    for obj in project.Group:
        if kind(obj) in CATEGORIES[1:]:
            sync_instance(obj)
            if kind(obj) in ("Door", "Window") and getattr(obj, "Host", None) is not None and obj.Host.ValidationMessage:
                obj.Host.touch()


def _resolved_product(obj, plan, type_overrides):
    """Resolve one product in a complete proposal without mutating its cache."""
    values, references = dict(plan.get("values", {})), dict(plan.get("references", {}))
    category = kind(obj)
    if "element_type" in plan:
        target = plan["element_type"]
    else:
        prop = "WallType" if category == "Wall" else "ElementType"
        target, identifier = getattr(obj, prop, None), getattr(obj, prop + "Id", "")
        if target is None and (identifier or category == "Wall"):
            raise FoundationError(f"{obj.Label}: {prop} is missing")
        if target is not None and (identifier != target.BIM3117Id or target.Project != obj.Project
                                   or target.Document != obj.Document or category_of_type(target) != category):
            raise FoundationError(f"{obj.Label}: assigned type category or identity is inconsistent")
    if target is not None:
        proposal = type_overrides.get(target.BIM3117Id)
        if proposal is None:
            validate_object(target)
            dimensions = {prop: mm(target, prop) for prop in DIMENSIONS[category]}
            material = effective_material(target)
        else:
            dimensions = proposal["dimensions"]
            material = _type_material_text(target, proposal["material"], proposal["layers"])
        values.update(dimensions)
        values["Material"] = material
    return values, references, target


def preflight(project, type_overrides=None, product_overrides=None):
    """Validate all products against one transient proposed state.

    No native objects, properties, history or temporary documents are created.
    Building every cutter first is essential: sequential single-instance checks
    can accept a change whose combined cutter union removes a member entirely.
    Hosted openings likewise use all proposed dimensions in the same pass.
    """
    from .building import (_reference, _identity_placement, _opening_values, _openings_overlap,
                           _box, _valid_solid)
    from .elements import (slab_edit_solid, gross_solid, join_slabs, _cut_member, _single_solid)
    import Part
    type_overrides, product_overrides = type_overrides or {}, product_overrides or {}
    products = [obj for obj in project.Group if kind(obj) in INSTANCE_KINDS]
    resolved = {}
    for obj in products:
        _identity_placement(obj)
        resolved[obj.BIM3117Id] = _resolved_product(obj, product_overrides.get(obj.BIM3117Id, {}), type_overrides)
    try:
        cutters = {}
        for obj in products:
            if kind(obj) == "Slab":
                values, references, _ = resolved[obj.BIM3117Id]
                cutters[obj.BIM3117Id] = slab_edit_solid(obj, values, references.get("Level"))
        for obj in products:
            if kind(obj) in ("Column", "Beam"):
                values, references, _ = resolved[obj.BIM3117Id]
                gross = gross_solid(obj, values, references)
                _single_solid(_cut_member(gross, join_slabs(obj), cutters), values.get("Label", obj.Label))
        walls = {}
        for obj in products:
            if kind(obj) != "Wall":
                continue
            values, references, target = resolved[obj.BIM3117Id]
            if target is None:
                raise FoundationError("Walls require a WallType")
            def value(prop):
                return values[prop] if prop in values else mm(obj, prop)
            base = references.get("BaseLevel") or _reference(obj, "BaseLevel", "Level")
            top = references.get("TopLevel") or _reference(obj, "TopLevel", "Level")
            sx, sy, ex, ey = (number(value(prop), prop) for prop in ("StartX", "StartY", "EndX", "EndY"))
            length = number(math.hypot(ex - sx, ey - sy), "Wall axis length", positive=True)
            base_z = number(mm(base, "Elevation"), "Base level elevation") + number(value("BaseOffset"), "Base offset")
            top_z = number(mm(top, "Elevation"), "Top level elevation") + number(value("TopOffset"), "Top offset")
            inputs = {"start_x": sx, "start_y": sy, "ux": (ex-sx)/length, "uy": (ey-sy)/length,
                      "length": length, "thickness": number(values["Thickness"], "Wall thickness", positive=True),
                      "base_z": base_z, "height": number(top_z-base_z, "Effective wall height", positive=True)}
            walls[obj.BIM3117Id] = (obj, inputs, [])
        for obj in products:
            if kind(obj) not in ("Door", "Window"):
                continue
            values, references, _ = resolved[obj.BIM3117Id]
            host = references.get("Host") or _reference(obj, "Host", "Wall")
            if host.BIM3117Id not in walls:
                raise FoundationError(f"{obj.Label}: host is outside the project")
            _, inputs, rectangles = walls[host.BIM3117Id]
            opening = _opening_values({prop: values[prop] if prop in values else mm(obj, prop)
                                       for prop in ("Offset", "Width", "Height", "Sill")},
                                      inputs, values.get("Label", obj.Label), kind(obj))
            for other, previous in rectangles:
                if _openings_overlap(opening, previous):
                    raise FoundationError(f"{obj.Label}: opening overlaps {other.Label}")
            rectangles.append((obj, opening))
            # Frames are unchanged from the existing generic Door/Window model.
            width, height = opening["width"], opening["height"]
            frame = min(50.0, width/4.0, height/4.0)
            offset, sill, depth = opening["offset"], opening["sill"], inputs["thickness"]
            parts = [_box(inputs, offset, 0, sill, frame, depth, height),
                     _box(inputs, offset+width-frame, 0, sill, frame, depth, height),
                     _box(inputs, offset+frame, 0, sill+height-frame, width-2*frame, depth, frame)]
            if kind(obj) == "Window":
                parts.append(_box(inputs, offset+frame, 0, sill, width-2*frame, depth, frame))
            _valid_solid(Part.makeCompound(parts), obj.Label)
        for wall, inputs, rectangles in walls.values():
            net_area = inputs["length"]*inputs["height"] - math.fsum(p["width"]*p["height"] for _, p in rectangles)
            if not math.isfinite(net_area) or net_area <= 0:
                raise FoundationError(f"{wall.Label}: openings must leave positive wall volume")
            shape = _box(inputs, 0, 0, 0, inputs["length"], inputs["thickness"], inputs["height"])
            pad = max(0.001, inputs["thickness"]*1e-6)
            for _, p in rectangles:
                shape = shape.cut(_box(inputs, p["offset"], -pad, p["sill"],
                                       p["width"], inputs["thickness"]+2*pad, p["height"]))
            _valid_solid(shape, wall.Label)
            expected_volume = net_area*inputs["thickness"]
            if abs(shape.Volume-expected_volume) > max(0.001, expected_volume*1e-8):
                raise FoundationError(f"{wall.Label}: proposed wall solid and opening quantities disagree")
    except FoundationError:
        raise
    except Exception as error:
        raise FoundationError(f"OCCT could not build the complete proposed model ({error})") from error
    return True


_NUMERIC_KEYS = {"start_x_mm": "StartX", "start_y_mm": "StartY", "end_x_mm": "EndX",
                 "end_y_mm": "EndY", "base_offset_mm": "BaseOffset", "top_offset_mm": "TopOffset",
                 "offset_mm": "Offset", "width_mm": "Width", "height_mm": "Height", "sill_mm": "Sill",
                 "thickness_mm": "Thickness", "depth_mm": "Depth", "x_mm": "X", "y_mm": "Y",
                 "rotation_deg": "Rotation"}
_REFERENCE_KEYS = {"base_level": "BaseLevel", "top_level": "TopLevel", "level": "Level", "host": "Host"}
_ALLOWED = {
    "Wall": {"name", "element_type", "wall_type", "base_level", "top_level", "start_x_mm", "start_y_mm",
             "end_x_mm", "end_y_mm", "base_offset_mm", "top_offset_mm"},
    "Slab": {"name", "element_type", "level", "boundary_mm", "thickness_mm", "offset_mm", "material"},
    "Column": {"name", "element_type", "base_level", "top_level", "x_mm", "y_mm", "width_mm", "depth_mm",
               "rotation_deg", "base_offset_mm", "top_offset_mm", "material"},
    "Beam": {"name", "element_type", "level", "start_mm", "end_mm", "width_mm", "depth_mm", "offset_mm", "material"},
    "Door": {"name", "element_type", "host", "offset_mm", "width_mm", "height_mm", "sill_mm"},
    "Window": {"name", "element_type", "host", "offset_mm", "width_mm", "height_mm", "sill_mm"},
}


def _prepare_instance(obj, changes):
    from .services import _require, _unique_name, _xy
    from .elements import boundary_points
    category = kind(obj)
    if category not in INSTANCE_KINDS:
        raise FoundationError("Select a supported building product")
    _require(obj, category, validate=False)
    if not isinstance(changes, dict):
        raise FoundationError("Instance changes must be a field/value dictionary")
    if set(changes) - _ALLOWED[category]:
        raise FoundationError("Unsupported instance edit fields: " + ", ".join(sorted(set(changes or {}) - _ALLOWED[category])))
    values, references = {}, {}
    plan = {"values": values, "references": references}
    changes = dict(changes)
    if "wall_type" in changes:
        if "element_type" in changes and changes["wall_type"] != changes["element_type"]:
            raise FoundationError("Choose one WallType for this wall")
        changes["element_type"] = changes.pop("wall_type")
    if "element_type" in changes:
        target = changes["element_type"]
        if target is None and category == "Wall":
            raise FoundationError("A wall always requires a WallType; assign another type")
        if target is not None:
            _require_project_member(target, "WallType" if category == "Wall" else "ElementType", obj.Project)
            if category_of_type(target) != category:
                raise FoundationError(f"A {category} needs a {category} type")
        else:
            # Detachment makes today's effective values authored instance values.
            # A missing target can be detached using the last persisted caches.
            try:
                previous = instance_type(obj)
            except FoundationError:
                previous = None
            for prop in DIMENSIONS[category]:
                values[prop] = effective_dimension(obj, prop) if previous is not None else mm(obj, prop)
            values["Material"] = effective_material(obj) if previous is not None else getattr(obj, "Material", "")
        plan["element_type"] = target
    else:
        target = instance_type(obj)
    for key, value in changes.items():
        if key == "element_type":
            continue
        if value is None:
            if key in _REFERENCE_KEYS:
                raise FoundationError(f"{key} is required; choose a reference in the same project")
            continue
        if key == "name":
            values["Label"] = text(value, category + " name", required=True)
            _unique_name(obj.Project, category, values["Label"], obj)
        elif key in _NUMERIC_KEYS:
            prop = _NUMERIC_KEYS[key]
            values[prop] = number(value, prop, positive=prop in ("Width", "Depth", "Height", "Thickness"))
        elif key in _REFERENCE_KEYS:
            prop = _REFERENCE_KEYS[key]
            references[prop] = _require_project_member(value, "Wall" if prop == "Host" else "Level", obj.Project)
        elif key == "material":
            values["Material"] = text(value, "Material")
        elif key == "boundary_mm":
            values["Boundary"] = [App.Vector(x, y, 0) for x, y in boundary_points(value)]
        elif key in ("start_mm", "end_mm"):
            prefix = "Start" if key == "start_mm" else "End"
            values[prefix+"X"], values[prefix+"Y"] = _xy(value, key)
    if target is not None and category != "Wall":
        for prop in DIMENSIONS[category] + ("Material",):
            if prop in values:
                expected = effective_material(target) if prop == "Material" else mm(target, prop)
                supplied = values[prop]
                equal = supplied == expected if prop == "Material" else abs(supplied-expected) <= 1e-7
                if not equal:
                    raise FoundationError(f"{prop} is controlled by shared type '{target.Label}'; edit or detach the type")
                del values[prop]
    return plan


def _apply_instance(obj, plan):
    from .services import _set_reference
    if "element_type" in plan:
        if kind(obj) == "Wall":
            _set_reference(obj, "WallType", plan["element_type"])
        else:
            initialize_instance(obj)
            target = plan["element_type"]
            obj.ElementType = target
            obj.ElementTypeId = target.BIM3117Id if target is not None else ""
            restore_catalog_modes(obj)
    for prop, target in plan["references"].items():
        _set_reference(obj, prop, target)
    for prop, value in plan["values"].items():
        setattr(obj, prop, value)
    if kind(obj) == "Wall" and getattr(obj, "Body", None) is not None:
        obj.Body.Label = obj.Label + " · Solid"
    if kind(obj) in ("Door", "Window") and getattr(obj, "Host", None) is not None:
        # A broken opening link also clears its upstream Wall's calculated
        # dimensions/status. The acyclic graph does not otherwise recompute
        # that upstream object when an opening alone is explicitly repaired.
        obj.Host.touch()
    sync_instance(obj)


def edit_instance(obj, changes):
    """Combine Label, type and eligible instance fields in one native edit."""
    from .services import _transaction, _sync_openings
    plan = _prepare_instance(obj, changes)
    preflight(obj.Project, product_overrides={obj.BIM3117Id: plan})
    old_host = getattr(obj, "Host", None)
    with _transaction(obj.Document, "3117 Edit " + kind(obj).lower()):
        _apply_instance(obj, plan)
        if kind(obj) in ("Door", "Window"):
            _sync_openings(old_host)
            if obj.Host != old_host:
                _sync_openings(obj.Host)
    return obj


def assign_types(objects, type_or_None):
    """Assign/detach a selection atomically, preflighting every changed product."""
    from .services import _transaction
    objects = list(objects)
    if not objects:
        raise FoundationError("Select at least one building product")
    if any(kind(obj) not in INSTANCE_KINDS for obj in objects):
        raise FoundationError("Select supported building products for type assignment")
    if len({obj.Name for obj in objects}) != len(objects):
        raise FoundationError("The assignment selection contains duplicate objects")
    project, document = objects[0].Project, objects[0].Document
    if any(obj.Project != project or obj.Document != document for obj in objects):
        raise FoundationError("Assign Type supports objects in one project")
    plans = {obj.BIM3117Id: _prepare_instance(obj, {"element_type": type_or_None}) for obj in objects}
    preflight(project, product_overrides=plans)
    with _transaction(document, "3117 Assign type" if type_or_None is not None else "3117 Detach type"):
        for obj in objects:
            _apply_instance(obj, plans[obj.BIM3117Id])
    return objects


def assign_type(obj, type_or_None):
    assign_types([obj], type_or_None)
    return obj
