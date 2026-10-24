# SPDX-License-Identifier: GPL-3.0-or-later
"""Parented forms. Opening or cancelling a form never edits a model.

Numeric values use host millimetres. Services own document transactions.
"""

import math

from .qt import QtWidgets, enum_value


def _parent_window(parent):
    if parent is not None:
        return parent
    import FreeCADGui
    return FreeCADGui.getMainWindow()


def _spin(name, value, minimum=-100000000.0, maximum=100000000.0):
    widget = QtWidgets.QDoubleSpinBox()
    widget.setObjectName(name)
    widget.setDecimals(3)
    widget.setRange(minimum, maximum)
    widget.setSingleStep(100.0)
    widget.setSuffix(" mm")
    widget.setValue(float(value))
    widget.setKeyboardTracking(False)
    return widget


def _line(name, value=""):
    widget = QtWidgets.QLineEdit(str(value))
    widget.setObjectName(name)
    return widget


def _mm(value):
    return float(getattr(value, "Value", value))


def _same_object(first, second):
    if first is second:
        return True
    if first is None or second is None:
        return False
    return first.Name == second.Name and first.Document.Name == second.Document.Name


class FormDialog(QtWidgets.QDialog):
    """Common shell with inline validation and deterministic object names."""

    def __init__(self, title, object_name, introduction, parent=None):
        super().__init__(_parent_window(parent))
        self.setObjectName(object_name)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.setModal(True)
        self._values = None
        self.body_layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(introduction)
        intro.setObjectName("introductionLabel")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)
        self.form = QtWidgets.QFormLayout()
        self.body_layout.addLayout(self.form)
        self.error = QtWidgets.QLabel()
        self.error.setObjectName("validationMessage")
        self.error.setWordWrap(True)
        self.error.hide()
        self.body_layout.addWidget(self.error)
        ok = enum_value(QtWidgets.QDialogButtonBox, "Ok", "StandardButton")
        cancel = enum_value(QtWidgets.QDialogButtonBox, "Cancel", "StandardButton")
        self.buttons = QtWidgets.QDialogButtonBox(ok | cancel)
        self.buttons.setObjectName("buttonBox")
        self.buttons.button(ok).setObjectName("acceptButton")
        self.buttons.button(cancel).setObjectName("cancelButton")
        self.buttons.button(ok).setText("ตกลง / OK")
        self.buttons.button(cancel).setText("ยกเลิก / Cancel")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.body_layout.addWidget(self.buttons)

    def collect_values(self):
        raise NotImplementedError

    def accept(self):
        try:
            values = self.collect_values()
        except ValueError as error:
            self.error.setText(str(error))
            self.error.show()
            return
        self._values = values
        super().accept()

    def values(self):
        if self._values is None:
            return self.collect_values()
        return dict(self._values)

    @staticmethod
    def required_text(widget, label):
        value = widget.text().strip()
        if not value:
            widget.setFocus()
            raise ValueError("กรุณาระบุ " + label)
        return value


class ProjectDialog(FormDialog):
    def __init__(self, initial=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขโครงการ / Edit Project" if editing else
            "3117 — สร้างโครงการ / Create Project",
            "ProjectDialog",
            "แก้ไขข้อมูลโครงการที่เลือก" if editing else
            "สร้างเอกสารโครงการใหม่ ระดับเริ่มต้นแก้ไขภายหลังได้",
            parent,
        )
        self.editing = bool(editing)
        self.name_edit = _line("nameEdit", initial.get("name", "3117 BIM Project"))
        self.number_edit = _line("projectNumberEdit", initial.get("project_number", ""))
        self.author_edit = _line("authorEdit", initial.get("author", ""))
        self.form.addRow("ชื่อโครงการ / Name", self.name_edit)
        self.form.addRow("รหัสโครงการ / Number", self.number_edit)
        self.form.addRow("ผู้จัดทำ / Author", self.author_edit)
        if not editing:
            self.initial_levels_check = QtWidgets.QCheckBox("สร้างระดับเริ่มต้น L00 และ L01")
            self.initial_levels_check.setObjectName("initialLevelsCheck")
            self.initial_levels_check.setChecked(True)
            self.base_input = _spin("baseElevationInput", 0.0)
            self.upper_input = _spin("upperElevationInput", 3000.0)
            self.form.addRow(self.initial_levels_check)
            self.form.addRow("L00 · ระดับฐาน", self.base_input)
            self.form.addRow("L01 · ระดับชั้นถัดไป", self.upper_input)
            self.initial_levels_check.toggled.connect(self.base_input.setEnabled)
            self.initial_levels_check.toggled.connect(self.upper_input.setEnabled)
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def collect_values(self):
        result = {
            "name": self.required_text(self.name_edit, "ชื่อโครงการ"),
            "project_number": self.number_edit.text().strip(),
            "author": self.author_edit.text().strip(),
        }
        if not self.editing:
            if self.initial_levels_check.isChecked():
                base, upper = self.base_input.value(), self.upper_input.value()
                if upper <= base:
                    raise ValueError("ระดับ L01 ต้องสูงกว่าระดับ L00")
                result["levels"] = [("L00", base), ("L01", upper)]
            else:
                result["levels"] = []
        return result


class LevelDialog(FormDialog):
    def __init__(self, initial=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขระดับ / Edit Level" if editing else
            "3117 — เพิ่มระดับ / Add Level",
            "LevelDialog",
            "กำหนดระดับอ้างอิงและขอบเขตเส้นระดับ · หน่วยมิลลิเมตร",
            parent,
        )
        self.name_edit = _line("nameEdit", initial.get("name", "L02"))
        self.elevation_input = _spin("elevationInput", initial.get("elevation_mm", 6000.0))
        self.span_x_input = _spin("spanXInput", initial.get("span_x_mm", 12000.0), 1.0)
        self.span_y_input = _spin("spanYInput", initial.get("span_y_mm", 8000.0), 1.0)
        self.form.addRow("ชื่อระดับ / Name", self.name_edit)
        self.form.addRow("ระดับ Z / Elevation", self.elevation_input)
        self.form.addRow("ขอบเขตตาม X / Span X", self.span_x_input)
        self.form.addRow("ขอบเขตตาม Y / Span Y", self.span_y_input)
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def collect_values(self):
        return {
            "name": self.required_text(self.name_edit, "ชื่อระดับ"),
            "elevation_mm": self.elevation_input.value(),
            "span_x_mm": self.span_x_input.value(),
            "span_y_mm": self.span_y_input.value(),
        }


class GridDialog(FormDialog):
    def __init__(self, initial=None, levels=None, editing=False, parent=None):
        initial = initial or {}
        introduction = "แก้ไขเส้นกริดและระดับอ้างอิง · หน่วยมิลลิเมตร" if editing else "สร้างเส้นกริดพร้อมสัญลักษณ์หัวกริด · หน่วยมิลลิเมตร"
        if initial.get("reference_missing"):
            introduction = (
                "ระดับอ้างอิงเดิมขาดหาย กรุณาเลือกระดับใหม่ "
                "หรือเลือก No reference level และตรวจค่า Offset ก่อนกดตกลง"
            )
        super().__init__(
            "3117 — แก้ไขกริด / Edit Grid" if editing else
            "3117 — สร้างกริด / Create Grid",
            "GridDialog",
            introduction,
            parent,
        )
        self.name_edit = _line("nameEdit", initial.get("label", "Grid A"))
        self.bubble_edit = _line("bubbleEdit", initial.get("bubble_label", "A"))
        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.setObjectName("axisCombo")
        self.axis_combo.addItem("X · เส้นขนานแกน X", "X")
        self.axis_combo.addItem("Y · เส้นขนานแกน Y", "Y")
        self.axis_combo.setCurrentIndex(1 if initial.get("axis", "X") == "Y" else 0)
        self.position_input = _spin("positionInput", initial.get("position_mm", 0.0))
        self.length_input = _spin("lengthInput", initial.get("length_mm", 12000.0), 1.0)
        self.reference_combo = QtWidgets.QComboBox()
        self.reference_combo.setObjectName("referenceLevelCombo")
        self.reference_combo.addItem("ไม่ผูกระดับ / No reference level")
        self._levels = [None]
        for level in levels or []:
            self._levels.append(level)
            self.reference_combo.addItem(
                "{}  ({:,.3f} mm)".format(level.Label, _mm(level.Elevation))
            )
        reference = initial.get("level")
        for index, level in enumerate(self._levels):
            if _same_object(level, reference):
                self.reference_combo.setCurrentIndex(index)
                break
        self.offset_input = _spin("offsetInput", initial.get("offset_mm", 0.0))
        self.direction_hint = QtWidgets.QLabel()
        self.direction_hint.setObjectName("directionHint")
        self.direction_hint.setWordWrap(True)
        self.elevation_summary = QtWidgets.QLabel()
        self.elevation_summary.setObjectName("elevationSummary")
        self.form.addRow("ชื่อในรายการ / Name", self.name_edit)
        self.form.addRow("หัวกริด / Bubble label", self.bubble_edit)
        self.form.addRow("ทิศทางเส้น / Direction", self.axis_combo)
        self.form.addRow("ตำแหน่ง / Position", self.position_input)
        self.form.addRow(self.direction_hint)
        self.form.addRow("ความยาวเส้น / Length", self.length_input)
        self.form.addRow("อ้างอิงระดับ / Level", self.reference_combo)
        self.form.addRow("ระยะดิ่งจากระดับ / Offset", self.offset_input)
        self.form.addRow(self.elevation_summary)
        self.axis_combo.currentIndexChanged.connect(self._update_hints)
        self.reference_combo.currentIndexChanged.connect(self._update_hints)
        self.offset_input.valueChanged.connect(self._update_hints)
        self._update_hints()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _update_hints(self, *_args):
        if self.axis_combo.currentIndex() == 0:
            self.direction_hint.setText("เส้นขนานแกน X · Position คือระยะ Y · เส้นกึ่งกลางอยู่ที่ X = 0")
        else:
            self.direction_hint.setText("เส้นขนานแกน Y · Position คือระยะ X · เส้นกึ่งกลางอยู่ที่ Y = 0")
        level = self._levels[self.reference_combo.currentIndex()]
        elevation = (0.0 if level is None else _mm(level.Elevation)) + self.offset_input.value()
        self.elevation_summary.setText("ระดับรวม Z = {:,.3f} mm".format(elevation))

    def collect_values(self):
        return {
            "label": self.required_text(self.name_edit, "ชื่อกริด"),
            "axis": "X" if self.axis_combo.currentIndex() == 0 else "Y",
            "position_mm": self.position_input.value(),
            "length_mm": self.length_input.value(),
            "bubble_label": self.required_text(self.bubble_edit, "ข้อความหัวกริด"),
            "level": self._levels[self.reference_combo.currentIndex()],
            "offset_mm": self.offset_input.value(),
        }


def make_project_dialog(**kwargs):
    return ProjectDialog(**kwargs)


def make_level_dialog(**kwargs):
    return LevelDialog(**kwargs)


def make_grid_dialog(**kwargs):
    return GridDialog(**kwargs)


def _object_combo(name, objects, selected=None, describe=None):
    """Keep actual native references; labels are presentation, never identity."""
    combo = QtWidgets.QComboBox()
    combo.setObjectName(name)
    combo.addItem("— เลือกรายการ / Select —")
    values = [None] + list(objects or [])
    for index, obj in enumerate(values[1:], start=1):
        combo.addItem(describe(obj) if describe else obj.Label)
        if _same_object(obj, selected):
            combo.setCurrentIndex(index)
    return combo, values


def _required_object(combo, values, label):
    index = combo.currentIndex()
    obj = values[index] if 0 <= index < len(values) else None
    if obj is None:
        combo.setFocus()
        raise ValueError("กรุณาเลือก " + label)
    return obj


class WallTypeDialog(FormDialog):
    def __init__(self, initial=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขชนิดผนัง / Edit Wall Type" if editing else
            "3117 — สร้างชนิดผนัง / Create Wall Type",
            "WallTypeDialog",
            "ความหนาเป็นค่าร่วมของผนังทุกแนวที่ใช้ชนิดนี้ · หน่วยมิลลิเมตร",
            parent,
        )
        self.name_edit = _line("nameEdit", initial.get("name", "WT-200"))
        self.thickness_input = _spin("thicknessInput", initial.get("thickness_mm", 200.0), 0.001)
        self.material_edit = _line("materialEdit", initial.get("material", ""))
        self.form.addRow("ชื่อชนิด / Type name", self.name_edit)
        self.form.addRow("ความหนารวม / Thickness", self.thickness_input)
        self.form.addRow("ชื่อวัสดุ / Material label", self.material_edit)
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def collect_values(self):
        return {
            "name": self.required_text(self.name_edit, "ชื่อชนิดผนัง"),
            "thickness_mm": self.thickness_input.value(),
            "material": self.material_edit.text().strip(),
        }


class WallDialog(FormDialog):
    def __init__(self, initial=None, wall_types=None, levels=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขผนัง / Edit Wall" if editing else
            "3117 — สร้างผนัง / Create Wall",
            "WallDialog",
            "กำหนดเส้นฐานจากจุดเริ่มไปจุดปลาย · เนื้อผนังอยู่ด้านซ้ายของแนวเส้นเมื่อมองจากด้านบน · หน่วยมิลลิเมตร",
            parent,
        )
        self.name_edit = _line("nameEdit", initial.get("name", "Wall 01"))
        self.type_combo, self._types = _object_combo(
            "wallTypeCombo", wall_types, initial.get("wall_type"),
            lambda obj: "{}  ({:,.3f} mm)".format(obj.Label, _mm(obj.Thickness)),
        )
        level_description = lambda obj: "{}  ({:,.3f} mm)".format(obj.Label, _mm(obj.Elevation))
        self.base_combo, self._base_levels = _object_combo(
            "baseLevelCombo", levels, initial.get("base_level"), level_description,
        )
        self.top_combo, self._top_levels = _object_combo(
            "topLevelCombo", levels, initial.get("top_level"), level_description,
        )
        self.start_x_input = _spin("startXInput", initial.get("start_x_mm", 0.0))
        self.start_y_input = _spin("startYInput", initial.get("start_y_mm", 0.0))
        self.end_x_input = _spin("endXInput", initial.get("end_x_mm", 6000.0))
        self.end_y_input = _spin("endYInput", initial.get("end_y_mm", 0.0))
        self.base_offset_input = _spin("baseOffsetInput", initial.get("base_offset_mm", 0.0))
        self.top_offset_input = _spin("topOffsetInput", initial.get("top_offset_mm", 0.0))
        self.geometry_summary = QtWidgets.QLabel()
        self.geometry_summary.setObjectName("geometrySummary")
        self.geometry_summary.setWordWrap(True)
        self.form.addRow("ชื่อผนัง / Name", self.name_edit)
        self.form.addRow("ชนิดผนัง / Wall type", self.type_combo)
        self.form.addRow("จุดเริ่ม X / Start X", self.start_x_input)
        self.form.addRow("จุดเริ่ม Y / Start Y", self.start_y_input)
        self.form.addRow("จุดปลาย X / End X", self.end_x_input)
        self.form.addRow("จุดปลาย Y / End Y", self.end_y_input)
        self.form.addRow("ระดับฐาน / Base level", self.base_combo)
        self.form.addRow("ระยะจากฐาน / Base offset", self.base_offset_input)
        self.form.addRow("ระดับยอด / Top level", self.top_combo)
        self.form.addRow("ระยะจากยอด / Top offset", self.top_offset_input)
        self.form.addRow(self.geometry_summary)
        for combo in (self.base_combo, self.top_combo):
            combo.currentIndexChanged.connect(self._update_summary)
        for widget in (self.start_x_input, self.start_y_input, self.end_x_input,
                       self.end_y_input, self.base_offset_input, self.top_offset_input):
            widget.valueChanged.connect(self._update_summary)
        self._update_summary()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _length(self):
        return math.hypot(self.end_x_input.value() - self.start_x_input.value(),
                          self.end_y_input.value() - self.start_y_input.value())

    def _height(self):
        base = self._base_levels[self.base_combo.currentIndex()]
        top = self._top_levels[self.top_combo.currentIndex()]
        if base is None or top is None:
            return None
        return (_mm(top.Elevation) + self.top_offset_input.value()
                - _mm(base.Elevation) - self.base_offset_input.value())

    def _update_summary(self, *_args):
        height = self._height()
        height_text = "เลือกระดับฐานและยอด" if height is None else "สูง {:,.3f} mm".format(height)
        self.geometry_summary.setText("ยาว {:,.3f} mm · {}".format(self._length(), height_text))

    def collect_values(self):
        wall_type = _required_object(self.type_combo, self._types, "ชนิดผนัง / Wall type")
        base = _required_object(self.base_combo, self._base_levels, "ระดับฐาน / Base level")
        top = _required_object(self.top_combo, self._top_levels, "ระดับยอด / Top level")
        if self._length() < 0.001:
            raise ValueError("จุดเริ่มและจุดปลายต้องห่างกันอย่างน้อย 0.001 mm")
        if self._height() < 0.001:
            raise ValueError("ระดับยอดรวม Offset ต้องสูงกว่าระดับฐานรวม Offset")
        return {
            "name": self.required_text(self.name_edit, "ชื่อผนัง"),
            "wall_type": wall_type, "base_level": base, "top_level": top,
            "start_x_mm": self.start_x_input.value(), "start_y_mm": self.start_y_input.value(),
            "end_x_mm": self.end_x_input.value(), "end_y_mm": self.end_y_input.value(),
            "base_offset_mm": self.base_offset_input.value(), "top_offset_mm": self.top_offset_input.value(),
        }


class DoorDialog(FormDialog):
    def __init__(self, initial=None, walls=None, editing=False, parent=None, opening_kind="Door"):
        initial = initial or {}
        window = opening_kind == "Window"
        self._name_label = "ชื่อหน้าต่าง" if window else "ชื่อประตู"
        category = "หน้าต่าง" if window else "ประตู"
        super().__init__(
            "3117 — {}{} / {} {}".format("แก้ไข" if editing else "สร้าง", category,
                                          "Edit" if editing else "Create", opening_kind),
            opening_kind + "Dialog",
            "ระยะ Offset วัดจากจุดเริ่มผนังถึงขอบช่องเปิด · กว้าง/สูงเป็นขนาดช่องเปิดรวม · หน่วยมิลลิเมตร"
            + (" · กรอบทั่วไปสี่ด้าน ไม่มีบานกระจก" if window else ""),
            parent,
        )
        self.name_edit = _line("nameEdit", initial.get("name", opening_kind + " 01"))
        self.host_combo, self._hosts = _object_combo("hostWallCombo", walls, initial.get("host"))
        self.offset_input = _spin(opening_kind.lower() + "OffsetInput", initial.get("offset_mm", 1000.0), 0.0)
        self.width_input = _spin("widthInput", initial.get("width_mm", 1200.0 if window else 900.0), 0.001)
        self.height_input = _spin("heightInput", initial.get("height_mm", 1200.0 if window else 2100.0), 0.001)
        self.sill_input = _spin("sillInput", initial.get("sill_mm", 900.0 if window else 0.0), 0.0)
        self.host_summary = QtWidgets.QLabel()
        self.host_summary.setObjectName("hostSummary")
        self.host_summary.setWordWrap(True)
        self.form.addRow(self._name_label + " / Name", self.name_edit)
        self.form.addRow("ผนังเจ้าบ้าน / Host wall", self.host_combo)
        self.form.addRow("ระยะตามผนัง / Offset", self.offset_input)
        self.form.addRow("กว้างช่องเปิด / Width", self.width_input)
        self.form.addRow("สูงช่องเปิด / Height", self.height_input)
        self.form.addRow("ยกจากฐานผนัง / Sill", self.sill_input)
        self.form.addRow(self.host_summary)
        self.host_combo.currentIndexChanged.connect(self._update_summary)
        self._update_summary()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _update_summary(self, *_args):
        host = self._hosts[self.host_combo.currentIndex()]
        if host is None:
            self.host_summary.setText("เลือกผนังที่จะเจาะช่องเปิด")
        else:
            self.host_summary.setText("ผนังยาว {:,.3f} mm · สูง {:,.3f} mm · หนา {:,.3f} mm".format(
                _mm(host.Length), _mm(host.Height), _mm(host.Thickness),
            ))

    def collect_values(self):
        host = _required_object(self.host_combo, self._hosts, "ผนังเจ้าบ้าน / Host wall")
        if self.offset_input.value() + self.width_input.value() > _mm(host.Length) + 1e-6:
            raise ValueError("ระยะ Offset รวมความกว้างช่องเปิดเกินความยาวผนัง")
        if self.sill_input.value() + self.height_input.value() > _mm(host.Height) + 1e-6:
            raise ValueError("ระยะ Sill รวมความสูงช่องเปิดเกินความสูงผนัง")
        return {
            "name": self.required_text(self.name_edit, self._name_label), "host": host,
            "offset_mm": self.offset_input.value(), "width_mm": self.width_input.value(),
            "height_mm": self.height_input.value(), "sill_mm": self.sill_input.value(),
        }


def make_wall_type_dialog(**kwargs):
    return WallTypeDialog(**kwargs)


def make_wall_dialog(**kwargs):
    return WallDialog(**kwargs)


def make_door_dialog(**kwargs):
    return DoorDialog(**kwargs)


def make_window_dialog(**kwargs):
    return DoorDialog(opening_kind="Window", **kwargs)
