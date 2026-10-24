# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent schedule definitions and staged source-instance edits."""

from .qt import QtWidgets
from .dialogs import FormDialog, _line, _spin, _mm, _object_combo, _same_object
from .catalog_dialogs import DIMENSIONS


SCHEDULE_CATEGORIES = ("Wall", "Door", "Slab", "Column", "Beam", "Window", "Material")


def schedule_initial(obj):
    return {"name": obj.Label, "category": str(obj.Category), "level": obj.FilterLevel,
            "element_type": obj.FilterType, "group_by": str(obj.GroupBy),
            "sort_by": str(obj.SortBy), "descending": bool(obj.Descending),
            "name_filter": str(obj.NameFilter)}


class ScheduleDefinitionDialog(FormDialog):
    def __init__(self, project, initial=None, editing=False, parent=None):
        from bim3117_freecad import services, catalog
        initial = initial or {}
        super().__init__("3117 — Edit Schedule" if editing else "3117 — Create Schedule",
                         "ScheduleDefinitionDialog",
                         "บันทึกตัวกรองและการจัดกลุ่มในเอกสาร · ปริมาณคำนวณจากโมเดล\n"
                         "Apply a persistent definition; quantity cells remain read-only.", parent)
        self._all_types = catalog.list_types(project)
        self._category_of_type = catalog.category_of_type
        self.name_edit = _line("nameEdit", initial.get("name", "Wall Schedule 01"))
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.setObjectName("scheduleCategoryCombo")
        self.category_combo.addItems(SCHEDULE_CATEGORIES)
        self.category_combo.setCurrentText(initial.get("category", "Wall"))
        self.level_combo, self._levels = _object_combo("scheduleLevelCombo", services.list_levels(project), initial.get("level"))
        self.level_combo.setItemText(0, "ทุกระดับ / All levels")
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setObjectName("scheduleTypeCombo")
        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setObjectName("scheduleGroupCombo")
        self.sort_combo = QtWidgets.QComboBox()
        self.sort_combo.setObjectName("scheduleSortCombo")
        self.sort_combo.addItems(("Name", "Type", "Level", "Material"))
        self.sort_combo.setCurrentText(initial.get("sort_by", "Name"))
        self.descending_check = QtWidgets.QCheckBox("มากไปน้อย / Descending")
        self.descending_check.setObjectName("scheduleDescendingCheck")
        self.descending_check.setChecked(bool(initial.get("descending", False)))
        self.name_filter_edit = _line("scheduleNameFilterEdit", initial.get("name_filter", ""))
        self.name_filter_edit.setPlaceholderText("Name contains…")
        for label, widget in (("ชื่อ / Name", self.name_edit), ("หมวด / Category", self.category_combo),
                              ("ระดับ / Level", self.level_combo), ("ชนิด / Type", self.type_combo),
                              ("ชื่อมีคำ / Name contains", self.name_filter_edit),
                              ("จัดกลุ่ม / Group by", self.group_combo), ("เรียง / Sort by", self.sort_combo)):
            self.form.addRow(label, widget)
        self.form.addRow(self.descending_check)
        self._sync_category(initial.get("element_type"), initial.get("group_by", "None"))
        self.category_combo.currentIndexChanged.connect(lambda *_args: self._sync_category())
        self.name_edit.selectAll()

    def _sync_category(self, selected_type=None, group=None):
        category = self.category_combo.currentText()
        if selected_type is None and hasattr(self, "_types"):
            selected_type = self._types[self.type_combo.currentIndex()]
        previous_group = group or self.group_combo.currentText() or "None"
        self._types = [None] + [obj for obj in self._all_types
                                if category == "Material" or self._category_of_type(obj) == category]
        self.type_combo.clear()
        self.type_combo.addItem("ทุกชนิด / All types")
        for obj in self._types[1:]:
            self.type_combo.addItem(obj.Label)
        self.type_combo.setCurrentIndex(next((i for i, obj in enumerate(self._types)
                                             if _same_object(obj, selected_type)), 0))
        self.group_combo.clear()
        self.group_combo.addItems(("None", "Type", "Material") if category == "Material" else ("None", "Type"))
        index = self.group_combo.findText(previous_group)
        self.group_combo.setCurrentIndex(max(0, index))

    def collect_values(self):
        return {"name": self.required_text(self.name_edit, "ชื่อตาราง"),
                "category": self.category_combo.currentText(),
                "level": self._levels[self.level_combo.currentIndex()],
                "element_type": self._types[self.type_combo.currentIndex()],
                "group_by": self.group_combo.currentText(), "sort_by": self.sort_combo.currentText(),
                "descending": self.descending_check.isChecked(),
                "name_filter": self.name_filter_edit.text().strip()}


# This is a bounded source editor. Polygon/Level/Host edits remain in Edit Selected.
_INSTANCE_FIELDS = {
    "Wall": (("start_x_mm", "StartX", "Start X"), ("start_y_mm", "StartY", "Start Y"),
             ("end_x_mm", "EndX", "End X"), ("end_y_mm", "EndY", "End Y"),
             ("base_offset_mm", "BaseOffset", "Base offset"), ("top_offset_mm", "TopOffset", "Top offset")),
    "Door": (("offset_mm", "Offset", "Along wall"), ("sill_mm", "Sill", "Sill")),
    "Window": (("offset_mm", "Offset", "Along wall"), ("sill_mm", "Sill", "Sill")),
    "Slab": (("offset_mm", "Offset", "Top offset"),),
    "Column": (("x_mm", "X", "X"), ("y_mm", "Y", "Y"), ("rotation_deg", "Rotation", "Rotation"),
               ("base_offset_mm", "BaseOffset", "Base offset"), ("top_offset_mm", "TopOffset", "Top offset")),
    "Beam": (("start_x_mm", "StartX", "Start X"), ("start_y_mm", "StartY", "Start Y"),
             ("end_x_mm", "EndX", "End X"), ("end_y_mm", "EndY", "End Y"),
             ("offset_mm", "Offset", "Top offset")),
}


class ScheduleRowDialog(FormDialog):
    def __init__(self, obj, parent=None):
        from bim3117_freecad import catalog
        super().__init__("3117 — Edit Schedule Source", "ScheduleRowDialog",
                         "แก้ข้อมูลต้นทางหนึ่งรายการในหนึ่ง transaction · ค่าปริมาณไม่ใช่ช่องกรอก\n"
                         "Source: {} · UUID {}".format(obj.Label, obj.BIM3117Id), parent)
        self.obj = obj
        self.category = str(obj.BIM3117Kind)
        self._original_type = catalog.assigned_type(obj)
        self._original_name = obj.Label
        self._original = {}
        self.fields = {}
        self.name_edit = _line("nameEdit", obj.Label)
        self.form.addRow("ชื่อ / Label", self.name_edit)
        self.type_combo, self._types = _object_combo(
            "rowTypeCombo", catalog.list_types(obj.Project, category=self.category), self._original_type)
        self.type_combo.setItemText(0, "แยกจากชนิด / Untyped")
        if self.category == "Wall":
            self.type_combo.setItemText(0, "เลือกชนิดผนัง / Wall type required")
        self.form.addRow("ชนิด / Type", self.type_combo)
        self.type_hint = QtWidgets.QLabel()
        self.type_hint.setObjectName("rowTypeHint")
        self.type_hint.setWordWrap(True)
        self.form.addRow(self.type_hint)
        for key, prop, label in _INSTANCE_FIELDS[self.category]:
            self._add_field(key, prop, label)
        if self.category != "Wall":
            for key, prop, _default in DIMENSIONS[self.category]:
                self._add_field(key, prop, prop, minimum=0.001)
        self.type_combo.currentIndexChanged.connect(self._sync_type)
        self._sync_type()
        self.name_edit.selectAll()

    def _add_field(self, key, prop, label, minimum=-100000000.0):
        value = _mm(getattr(self.obj, prop))
        self._original[key] = value
        field = _spin("row" + prop + "Input", value, minimum)
        if key == "rotation_deg":
            field.setSuffix(" °")
            field.setSingleStep(15)
        self.fields[key] = field
        self.form.addRow(label, field)

    def _sync_type(self, *_args):
        selected = self._types[self.type_combo.currentIndex()]
        self.type_hint.setText("ขนาดมาจากชนิด / Dimensions controlled by type" if selected is not None else
                               "ขนาดเป็นของรายการนี้ / Instance dimensions")
        if self.category == "Wall":
            return
        for key, prop, _default in DIMENSIONS[self.category]:
            self.fields[key].setEnabled(selected is None)
            self.fields[key].setValue(_mm(getattr(selected, prop)) if selected is not None else self._original[key])

    def collect_values(self):
        name = self.required_text(self.name_edit, "ชื่อรายการ")
        selected = self._types[self.type_combo.currentIndex()]
        if self.category == "Wall" and selected is None:
            raise ValueError("Wall ต้องมีชนิด / A wall requires a type")
        changes = {}
        if name != self._original_name:
            changes["name"] = name
        if not _same_object(selected, self._original_type):
            changes["element_type"] = selected
        controlled = {item[0] for item in DIMENSIONS[self.category]} if selected is not None else set()
        for key, widget in self.fields.items():
            if key not in controlled and abs(widget.value() - self._original[key]) > 1e-7:
                changes[key] = widget.value()
        if self.category == "Beam":
            for prefix in ("start", "end"):
                x_key, y_key = prefix + "_x_mm", prefix + "_y_mm"
                if x_key in changes or y_key in changes:
                    changes[prefix + "_mm"] = (changes.pop(x_key, self._original[x_key]),
                                                changes.pop(y_key, self._original[y_key]))
        return changes
