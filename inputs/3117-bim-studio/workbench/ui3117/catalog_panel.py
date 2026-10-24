# SPDX-License-Identifier: GPL-3.0-or-later
"""Project catalogue; table selection does not replace model selection."""

import FreeCADGui as Gui

from .qt import QtWidgets, run_dialog
from .model_panels import ModelPanel, readonly_table, fill_table, show_panel
from .catalog_dialogs import (CATEGORIES, DIMENSIONS, MaterialDialog, TypeDialog,
                              DuplicateTypeDialog, DuplicateMaterialDialog, type_initial)


_PANELS = {}


def _catalog():
    from bim3117_freecad import catalog
    return catalog


def _identity(obj):
    # A selected object can have been removed by Delete or native Undo.
    try:
        return str(obj.BIM3117Id) if obj is not None else None
    except (AttributeError, ReferenceError, RuntimeError):
        return None


def edit_catalog_object(obj, parent=None):
    catalog = _catalog()
    if obj.BIM3117Kind == "Material":
        dialog = MaterialDialog({"name": obj.Label, "code": str(obj.Code)}, True, parent)
        operation = catalog.edit_material
    else:
        dialog = TypeDialog(type_initial(obj), catalog.list_materials(obj.Project), True, parent)
        operation = catalog.edit_type
    if run_dialog(dialog):
        operation(obj, **dialog.values())
        return True
    return False


def selected_instances(project):
    from bim3117_freecad import services
    result = []
    for obj in Gui.Selection.getSelection():
        if obj.Document != project.Document:
            raise ValueError("กรุณาเลือกชิ้นส่วนในเอกสารนี้ / Select instances in this document")
        obj = services.resolve_authoring_object(obj)
        if services.kind(obj) not in CATEGORIES:
            raise ValueError("กรุณาเลือกชิ้นส่วนอาคาร / Select building instances")
        if str(obj.Project.BIM3117Id) != str(project.BIM3117Id):
            raise ValueError("Selection belongs to a different project")
        if obj not in result:
            result.append(obj)
    if not result:
        raise ValueError("เลือกชิ้นส่วนในโมเดลก่อน / Select one or more model instances first")
    return result


class CataloguePanel(ModelPanel):
    def __init__(self, project):
        super().__init__(project, "BIM3117CataloguePanel", "3117 — Types & Materials / ชนิดและวัสดุ", _PANELS)
        self.resize(850, 460)
        self._types = []
        self._materials = []
        layout = QtWidgets.QVBoxLayout(self)
        help_label = QtWidgets.QLabel("กำหนดชนิดร่วม แล้วเลือกชิ้นส่วนในโมเดลเพื่อ Assign · การเปลี่ยนชนิดทำในหนึ่ง Undo")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setObjectName("catalogTabs")
        layout.addWidget(self.tabs)
        types_tab = QtWidgets.QWidget()
        type_layout = QtWidgets.QVBoxLayout(types_tab)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Category"))
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.setObjectName("catalogCategoryCombo")
        self.category_combo.addItems(("All",) + CATEGORIES)
        self.category_combo.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.category_combo)
        row.addStretch()
        type_layout.addLayout(row)
        self.types_table = readonly_table("catalogTypesTable", ["Name", "Category", "Code", "Dimensions / mm", "Material / Layers", "Instances"])
        self.types_table.itemSelectionChanged.connect(self._update_buttons)
        self.types_table.itemDoubleClicked.connect(lambda *_args: self.edit_type())
        type_layout.addWidget(self.types_table)
        buttons = QtWidgets.QHBoxLayout()
        for label, name, slot in (("+ Type", "newTypeButton", self.create_type),
                                  ("Edit", "editTypeButton", self.edit_type),
                                  ("Duplicate", "duplicateTypeButton", self.duplicate_type),
                                  ("Delete", "deleteTypeButton", self.delete_type),
                                  ("Assign to model selection", "assignTypeButton", self.assign_type),
                                  ("Detach selected instances", "detachTypeButton", self.detach_type)):
            button = QtWidgets.QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button)
            setattr(self, name, button)
        type_layout.addLayout(buttons)
        self.tabs.addTab(types_tab, "Types / ชนิด")
        material_tab = QtWidgets.QWidget()
        material_layout = QtWidgets.QVBoxLayout(material_tab)
        self.materials_table = readonly_table("catalogMaterialsTable", ["Name", "Code", "Used by"])
        self.materials_table.itemSelectionChanged.connect(self._update_buttons)
        self.materials_table.itemDoubleClicked.connect(lambda *_args: self.edit_material())
        material_layout.addWidget(self.materials_table)
        buttons = QtWidgets.QHBoxLayout()
        for label, name, slot in (("+ Material", "newMaterialButton", self.create_material),
                                  ("Edit", "editMaterialButton", self.edit_material),
                                  ("Duplicate", "duplicateMaterialButton", self.duplicate_material),
                                  ("Delete", "deleteMaterialButton", self.delete_material)):
            button = QtWidgets.QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button)
            setattr(self, name, button)
        buttons.addStretch()
        material_layout.addLayout(buttons)
        self.tabs.addTab(material_tab, "Materials / วัสดุ")
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("catalogStatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch()
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.setObjectName("refreshCatalogueButton")
        refresh.clicked.connect(self.refresh)
        footer.addWidget(refresh)
        close = QtWidgets.QPushButton("Close")
        close.setObjectName("closeCatalogueButton")
        close.clicked.connect(self.close)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.refresh()

    def _selected(self, material=False):
        table, objects = (self.materials_table, self._materials) if material else (self.types_table, self._types)
        row = table.currentRow()
        return objects[row] if 0 <= row < len(objects) else None

    def _update_buttons(self):
        has_type = self._selected() is not None
        has_material = self._selected(True) is not None
        for name in ("editTypeButton", "duplicateTypeButton", "deleteTypeButton", "assignTypeButton"):
            getattr(self, name).setEnabled(has_type)
        for name in ("editMaterialButton", "duplicateMaterialButton", "deleteMaterialButton"):
            getattr(self, name).setEnabled(has_material)

    def refresh(self, *_args):
        if self._closed or self._transaction_open or self._editing:
            return
        self._refreshing = True
        try:
            catalog, project = _catalog(), self._project()
            selected_type, selected_material = self._selected(), self._selected(True)
            selected_type_id = _identity(selected_type)
            selected_material_id = _identity(selected_material)
            category = self.category_combo.currentText()
            self._types = catalog.list_types(project, category=None if category == "All" else category)
            self._materials = catalog.list_materials(project)
            rows = []
            for obj in self._types:
                info = type_initial(obj)
                dims = " × ".join("{:g}".format(info[key]) for key, _label, _default in DIMENSIONS[info["category"]])
                layers = info["layers"]
                material = " / ".join(layer["material"].Label for layer in layers) if layers else (
                    info["material"].Label if info["material"] else str(getattr(obj, "Material", "")) or "—")
                dependents = [child for child in catalog.type_dependents(obj) if child.BIM3117Kind in CATEGORIES]
                rows.append([obj.Label, info["category"], info["code"], dims, material, len(dependents)])
            fill_table(self.types_table, rows)
            fill_table(self.materials_table, [[obj.Label, str(obj.Code), len(catalog.material_dependents(obj))]
                                              for obj in self._materials])
            for table, objects, identity in ((self.types_table, self._types, selected_type_id),
                                             (self.materials_table, self._materials, selected_material_id)):
                match = next((index for index, obj in enumerate(objects) if obj.BIM3117Id == identity), None)
                if match is not None:
                    table.selectRow(match)
            self._update_buttons()
            self._dirty = False
            self.last_error = None
            self.status_label.setText("{} types · {} materials · Native document is the source".format(len(self._types), len(self._materials)))
        except Exception as error:
            self.last_error = str(error)
            self.status_label.setText(str(error))
        finally:
            self._refreshing = False

    def _action(self, title, operation):
        self._editing = True
        try:
            operation()
        except Exception as error:
            self._fail(title, error)
        finally:
            self._editing = False
            self.refresh()

    def create_type(self):
        def action():
            from .commands import _next_name
            project, catalog = self._project(), _catalog()
            category = self.category_combo.currentText()
            if category == "All":
                category = "Slab"
            dialog = TypeDialog({"name": _next_name(catalog.list_types(project), category + " Type"),
                                 "category": category}, catalog.list_materials(project), parent=self)
            if run_dialog(dialog):
                catalog.create_type(project, **dialog.values())
        self._action("Create Type", action)

    def edit_type(self):
        obj = self._selected()
        if obj is not None:
            self._action("Edit Type", lambda: edit_catalog_object(obj, self))

    def duplicate_type(self):
        obj = self._selected()
        if obj is None:
            return
        def action():
            dialog = DuplicateTypeDialog(obj, self)
            if run_dialog(dialog):
                _catalog().duplicate_type(obj, **dialog.values())
        self._action("Duplicate Type", action)

    def delete_type(self):
        obj = self._selected()
        if obj is not None:
            self._action("Delete Type", lambda: _catalog().delete_type(obj))

    def assign_type(self):
        element_type = self._selected()
        if element_type is not None:
            self._action("Assign Type", lambda: _catalog().assign_types(selected_instances(self._project()), element_type))

    def detach_type(self):
        self._action("Detach Type", lambda: _catalog().assign_types(selected_instances(self._project()), None))

    def create_material(self):
        def action():
            from .commands import _next_name
            project, catalog = self._project(), _catalog()
            dialog = MaterialDialog({"name": _next_name(catalog.list_materials(project), "Material")}, parent=self)
            if run_dialog(dialog):
                catalog.create_material(project, **dialog.values())
        self._action("Create Material", action)

    def edit_material(self):
        obj = self._selected(True)
        if obj is not None:
            self._action("Edit Material", lambda: edit_catalog_object(obj, self))

    def delete_material(self):
        obj = self._selected(True)
        if obj is not None:
            self._action("Delete Material", lambda: _catalog().delete_material(obj))

    def duplicate_material(self):
        obj = self._selected(True)
        if obj is None:
            return
        def action():
            dialog = DuplicateMaterialDialog(obj, self)
            if run_dialog(dialog):
                _catalog().duplicate_material(obj, **dialog.values())
        self._action("Duplicate Material", action)


def show_catalogue(project):
    panel = _PANELS.get(project.Document.Name)
    if panel is None or panel._closed:
        panel = CataloguePanel(project)
    return show_panel(panel, _PANELS)


def panel_for_document(name):
    return _PANELS.get(name)
