# SPDX-License-Identifier: GPL-3.0-or-later
"""Staged native catalogue forms; all dimensions use host millimetres."""

from .qt import QtWidgets, enum_value
from .dialogs import FormDialog, _line, _spin, _mm, _object_combo, _same_object


CATEGORIES = ("Wall", "Slab", "Column", "Beam", "Door", "Window")
DIMENSIONS = {
    "Wall": (("thickness_mm", "Thickness", 200.0),),
    "Slab": (("thickness_mm", "Thickness", 150.0),),
    "Column": (("width_mm", "Width", 300.0), ("depth_mm", "Depth", 300.0)),
    "Beam": (("width_mm", "Width", 300.0), ("depth_mm", "Depth", 450.0)),
    "Door": (("width_mm", "Width", 900.0), ("height_mm", "Height", 2100.0)),
    "Window": (("width_mm", "Width", 1200.0), ("height_mm", "Height", 1200.0)),
}


class MaterialDialog(FormDialog):
    def __init__(self, initial=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__("3117 — Edit Material" if editing else "3117 — Create Material",
                         "MaterialDialog", "วัสดุร่วมของโครงการ / Shared project material", parent)
        self.name_edit = _line("nameEdit", initial.get("name", "Material 01"))
        self.code_edit = _line("codeEdit", initial.get("code", ""))
        self.form.addRow("ชื่อ / Name", self.name_edit)
        self.form.addRow("รหัส / Code", self.code_edit)
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def collect_values(self):
        return {"name": self.required_text(self.name_edit, "ชื่อวัสดุ"),
                "code": self.code_edit.text().strip()}


class TypeDialog(FormDialog):
    """A type owns dimensions and either one material or ordered layers."""

    def __init__(self, initial=None, materials=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__("3117 — Edit Type" if editing else "3117 — Create Type",
                         "ElementTypeDialog",
                         "ขนาดชนิดมีผลกับทุกรายการที่อ้างอิง · หน่วย mm\n"
                         "Type changes update every assigned instance in one transaction.", parent)
        self.editing = bool(editing)
        self.materials = list(materials or [])
        self.name_edit = _line("nameEdit", initial.get("name", "Type 01"))
        self.code_edit = _line("codeEdit", initial.get("code", ""))
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.setObjectName("typeCategoryCombo")
        self.category_combo.addItems(CATEGORIES)
        self.category_combo.setCurrentIndex(max(0, CATEGORIES.index(initial.get("category", "Slab"))))
        self.category_combo.setEnabled(not editing)
        self.form.addRow("ชื่อ / Name", self.name_edit)
        self.form.addRow("รหัส / Code", self.code_edit)
        self.form.addRow("หมวด / Category", self.category_combo)
        self.dimensions = {}
        self.dimension_labels = {}
        category_defaults = {key: value for key, _label, value in DIMENSIONS[initial.get("category", "Slab")]}
        for key, label, default in (("thickness_mm", "Thickness", 150.0),
                                    ("width_mm", "Width", 300.0),
                                    ("depth_mm", "Depth", 450.0),
                                    ("height_mm", "Height", 2100.0)):
            field = _spin(label.lower() + "Input", initial.get(key, category_defaults.get(key, default)), 0.001)
            caption = QtWidgets.QLabel(label + " / mm")
            self.dimensions[key] = field
            self.dimension_labels[key] = caption
            self.form.addRow(caption, field)
        self.material_combo, self._material_values = _object_combo(
            "typeMaterialCombo", self.materials, initial.get("material"),
            describe=lambda obj: "{}{}".format(obj.Label, "  · " + str(obj.Code) if obj.Code else ""))
        self.material_combo.setItemText(0, "ไม่กำหนด / Unspecified")
        self.form.addRow("วัสดุ / Material", self.material_combo)
        self.layers_check = QtWidgets.QCheckBox("ชั้นวัสดุเรียงลำดับ / Ordered material layers")
        self.layers_check.setObjectName("useLayersCheck")
        self.layers_check.setChecked(bool(initial.get("layers")))
        self.form.addRow(self.layers_check)
        self.layers_table = QtWidgets.QTableWidget(0, 3)
        self.layers_table.setObjectName("typeLayersTable")
        self.layers_table.setHorizontalHeaderLabels(["Material", "Thickness / mm", "Role"])
        self.layers_table.setSelectionBehavior(enum_value(QtWidgets.QAbstractItemView, "SelectRows", "SelectionBehavior"))
        self.layers_table.setSelectionMode(enum_value(QtWidgets.QAbstractItemView, "SingleSelection", "SelectionMode"))
        self.layers_table.setMinimumHeight(145)
        self.layers_table.horizontalHeader().setStretchLastSection(True)
        self.layers_hint = QtWidgets.QLabel("Wall: local +Y · Slab: from top down. Total thickness is the layer sum.")
        self.layers_hint.setWordWrap(True)
        self.layers_box = QtWidgets.QWidget()
        layer_layout = QtWidgets.QVBoxLayout(self.layers_box)
        layer_layout.setContentsMargins(0, 0, 0, 0)
        layer_layout.addWidget(self.layers_hint)
        layer_layout.addWidget(self.layers_table)
        row = QtWidgets.QHBoxLayout()
        for label, name, slot in (("+ Layer", "addLayerButton", self.add_layer),
                                  ("− Remove", "removeLayerButton", self.remove_layer),
                                  ("↑", "moveLayerUpButton", lambda: self.move_layer(-1)),
                                  ("↓", "moveLayerDownButton", lambda: self.move_layer(1))):
            button = QtWidgets.QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch()
        layer_layout.addLayout(row)
        self.body_layout.insertWidget(2, self.layers_box)
        for layer in initial.get("layers", []):
            self.add_layer(layer)
        self.category_combo.currentIndexChanged.connect(self._category_changed)
        self.layers_check.toggled.connect(self._sync_fields)
        self._sync_fields()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _category_changed(self, _index):
        category = self.category_combo.currentText()
        for key, _label, default in DIMENSIONS[category]:
            self.dimensions[key].setValue(default)
        if category not in ("Wall", "Slab"):
            self.layers_check.setChecked(False)
        self._sync_fields()

    def _sync_fields(self, *_args):
        category = self.category_combo.currentText()
        keys = {item[0] for item in DIMENSIONS[category]}
        layered = category in ("Wall", "Slab") and self.layers_check.isChecked()
        self.layers_check.setVisible(category in ("Wall", "Slab"))
        for key, widget in self.dimensions.items():
            widget.setVisible(key in keys)
            self.dimension_labels[key].setVisible(key in keys)
            widget.setEnabled(not (key == "thickness_mm" and layered))
        self.material_combo.setEnabled(not layered)
        self.layers_box.setVisible(layered)
        if layered:
            self._update_total()
        self.adjustSize()

    def add_layer(self, layer=None):
        # clicked(bool) is not a layer payload.
        layer = layer if isinstance(layer, dict) else {}
        row = self.layers_table.rowCount()
        self.layers_table.insertRow(row)
        combo, values = _object_combo("layerMaterialCombo", self.materials, layer.get("material"))
        combo._native_materials = values
        thickness = _spin("layerThicknessInput", layer.get("thickness_mm", 50.0), 0.001)
        thickness.setSingleStep(10)
        thickness.valueChanged.connect(self._update_total)
        role = _line("layerRoleEdit", layer.get("role", ""))
        self.layers_table.setCellWidget(row, 0, combo)
        self.layers_table.setCellWidget(row, 1, thickness)
        self.layers_table.setCellWidget(row, 2, role)
        self.layers_table.selectRow(row)
        self._update_total()

    def _layers(self, validate=True):
        layers = []
        for row in range(self.layers_table.rowCount()):
            combo = self.layers_table.cellWidget(row, 0)
            material = combo._native_materials[combo.currentIndex()]
            if validate and material is None:
                raise ValueError("กรุณาเลือกวัสดุในชั้นที่ {} / Select each layer material".format(row + 1))
            layers.append({"material": material,
                           "thickness_mm": self.layers_table.cellWidget(row, 1).value(),
                           "role": self.layers_table.cellWidget(row, 2).text().strip()})
        return layers

    def _update_total(self, *_args):
        if self.layers_check.isChecked():
            self.dimensions["thickness_mm"].setValue(sum(layer["thickness_mm"] for layer in self._layers(False)))

    def remove_layer(self):
        row = self.layers_table.currentRow()
        if row >= 0:
            self.layers_table.removeRow(row)
            self._update_total()

    def move_layer(self, direction):
        row = self.layers_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.layers_table.rowCount():
            return
        layers = self._layers(False)
        layers[row], layers[target] = layers[target], layers[row]
        self.layers_table.setRowCount(0)
        for layer in layers:
            self.add_layer(layer)
        self.layers_table.selectRow(target)

    def collect_values(self):
        category = self.category_combo.currentText()
        values = {"name": self.required_text(self.name_edit, "ชื่อชนิด"), "code": self.code_edit.text().strip()}
        if not self.editing:
            values["category"] = category
        values.update({key: self.dimensions[key].value() for key, _label, _default in DIMENSIONS[category]})
        if category in ("Wall", "Slab") and self.layers_check.isChecked():
            values["layers"] = self._layers()
            if not values["layers"]:
                raise ValueError("กรุณาเพิ่มอย่างน้อยหนึ่งชั้นวัสดุ / Add at least one layer")
            values["material"] = None
            values["thickness_mm"] = sum(layer["thickness_mm"] for layer in values["layers"])
        else:
            values["material"] = self._material_values[self.material_combo.currentIndex()]
            values["layers"] = []
        return values


class DuplicateTypeDialog(FormDialog):
    def __init__(self, source, parent=None):
        super().__init__("3117 — Duplicate Type", "DuplicateTypeDialog",
                         "สำเนาสร้าง UUID ใหม่ และคงวัสดุ/ชั้นวัสดุเดิม / New type identity", parent)
        self.name_edit = _line("nameEdit", source.Label + " Copy")
        self.form.addRow("ชื่อใหม่ / Name", self.name_edit)
        self.name_edit.selectAll()

    def collect_values(self):
        return {"name": self.required_text(self.name_edit, "ชื่อชนิดใหม่")}


class DuplicateMaterialDialog(FormDialog):
    def __init__(self, source, parent=None):
        super().__init__("3117 — Duplicate Material", "DuplicateMaterialDialog",
                         "วัสดุสำเนามี UUID ใหม่และรหัสว่าง / New material identity with an empty code", parent)
        self.name_edit = _line("nameEdit", source.Label + " Copy")
        self.form.addRow("ชื่อใหม่ / Name", self.name_edit)
        self.name_edit.selectAll()

    def collect_values(self):
        return {"name": self.required_text(self.name_edit, "ชื่อวัสดุใหม่")}


class AssignTypeDialog(FormDialog):
    def __init__(self, objects, types, current=None, parent=None):
        super().__init__("3117 — Assign Type", "AssignTypeDialog",
                         "เปลี่ยนชนิดของ {} รายการในหนึ่ง transaction / {} selected instances"
                         .format(len(objects), len(objects)), parent)
        self.type_combo, self._types = _object_combo("assignTypeCombo", types, current)
        self.type_combo.setItemText(0, "เลือกชนิด / Select type")
        self.form.addRow("ชนิด / Type", self.type_combo)

    def collect_values(self):
        selected = self._types[self.type_combo.currentIndex()]
        if selected is None:
            raise ValueError("กรุณาเลือกชนิด / Select a type")
        return {"element_type": selected}


def type_initial(obj):
    from bim3117_freecad import catalog
    values = {"name": obj.Label, "code": str(getattr(obj, "Code", "")),
              "category": catalog.category_of_type(obj),
              "material": getattr(obj, "MaterialRef", None),
              "layers": catalog.layer_definitions(obj)}
    for key, label, _default in DIMENSIONS[values["category"]]:
        values[key] = _mm(getattr(obj, label))
    return values


def lock_instance_type_fields(dialog, obj):
    """Keep legacy forms, but never submit dimensions controlled by a type."""
    from bim3117_freecad import catalog
    element_type = catalog.assigned_type(obj)
    if element_type is None:
        return
    label = QtWidgets.QLabel("Type: {} · แก้ขนาดร่วมผ่าน Catalogue / Shared dimensions".format(element_type.Label))
    label.setObjectName("assignedTypeLabel")
    label.setWordWrap(True)
    dialog.body_layout.insertWidget(1, label)
    controlled = set(catalog.controlled_properties(obj))
    mapping = {"Thickness": ("thicknessInput", "thickness_mm"),
               "Width": ("widthInput", "width_mm"), "Depth": ("depthInput", "depth_mm"),
               "Height": ("heightInput", "height_mm"), "Material": ("materialEdit", "material")}
    omitted = set()
    for prop, (widget_name, key) in mapping.items():
        if prop in controlled:
            widget = dialog.findChild(QtWidgets.QWidget, widget_name)
            if widget is not None:
                widget.setEnabled(False)
                widget.setToolTip("Controlled by type: " + element_type.Label)
            omitted.add(key)
    original = dialog.collect_values
    dialog.collect_values = lambda: {key: value for key, value in original().items() if key not in omitted}
