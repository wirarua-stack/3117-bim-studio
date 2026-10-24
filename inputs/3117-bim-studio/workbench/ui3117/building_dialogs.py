# SPDX-License-Identifier: GPL-3.0-or-later
"""Small native authoring forms; committed geometry stays in the document."""

import math

from .dialogs import (FormDialog, _line, _mm, _object_combo, _required_object,
                      _same_object, _spin)
from .qt import QtWidgets


def _level_description(obj):
    return "{}  ({:,.3f} mm)".format(obj.Label, _mm(obj.Elevation))


def _summary(name):
    label = QtWidgets.QLabel()
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _selected(combo, objects):
    index = combo.currentIndex()
    return objects[index] if 0 <= index < len(objects) else None


def _polygon_text(points):
    return "\n".join("{:g}, {:g}".format(float(point[0]), float(point[1])) for point in points)


def _parse_polygon(text):
    points = []
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        tokens = line.replace(",", " ").split()
        try:
            if len(tokens) != 2:
                raise ValueError
            point = tuple(float(token) for token in tokens)
            if not all(math.isfinite(value) for value in point):
                raise ValueError
        except ValueError:
            raise ValueError("จุดที่บรรทัด {} ต้องเป็น X, Y สองตัวเลข หน่วย mm".format(index))
        points.append(point)
    if len(points) < 3:
        raise ValueError("รูปหลายเหลี่ยมต้องมีอย่างน้อย 3 จุด · ไม่ต้องซ้ำจุดปิด")
    return points


class SlabDialog(FormDialog):
    def __init__(self, initial=None, levels=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขพื้น / Edit Slab" if editing else "3117 — สร้างพื้น / Create Slab",
            "SlabDialog", "ผิวบน = Level + Offset · ความหนาลงด้านล่าง · ขอบเขตในระนาบ XY หน่วย mm", parent)
        self.name_edit = _line("nameEdit", initial.get("name", "Slab 01"))
        self.level_combo, self._levels = _object_combo(
            "levelCombo", levels, initial.get("level"), _level_description)
        self.offset_input = _spin("offsetInput", initial.get("offset_mm", 0.0))
        self.thickness_input = _spin("thicknessInput", initial.get("thickness_mm", 150.0), 0.001)
        self.material_edit = _line("materialEdit", initial.get("material", ""))
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.setObjectName("slabProfileCombo")
        self.profile_combo.addItems(["สี่เหลี่ยม / Rectangle", "หลายเหลี่ยม XY / Polygon"])
        self.profile_stack = QtWidgets.QStackedWidget()
        self.profile_stack.setObjectName("slabProfilePages")
        rectangle = QtWidgets.QWidget()
        rectangle_form = QtWidgets.QFormLayout(rectangle)
        rectangle_form.setContentsMargins(0, 0, 0, 0)
        self.x_input = _spin("slabXInput", initial.get("x_mm", 0.0))
        self.y_input = _spin("slabYInput", initial.get("y_mm", 0.0))
        self.length_input = _spin("slabLengthInput", initial.get("length_mm", 6000.0), 0.001)
        self.width_input = _spin("slabWidthInput", initial.get("width_mm", 4000.0), 0.001)
        for label, widget in (("มุมเริ่ม X / Origin X", self.x_input), ("มุมเริ่ม Y / Origin Y", self.y_input),
                              ("ด้านตาม X / Size X", self.length_input), ("ด้านตาม Y / Size Y", self.width_input)):
            rectangle_form.addRow(label, widget)
        polygon = QtWidgets.QWidget()
        polygon_layout = QtWidgets.QVBoxLayout(polygon)
        polygon_layout.setContentsMargins(0, 0, 0, 0)
        hint = QtWidgets.QLabel("หนึ่งจุดต่อบรรทัด: X, Y · ไม่มีรูภายใน · ไม่ต้องซ้ำจุดปิด")
        hint.setWordWrap(True)
        polygon_layout.addWidget(hint)
        self.boundary_edit = QtWidgets.QPlainTextEdit()
        self.boundary_edit.setObjectName("boundaryEdit")
        self.boundary_edit.setMinimumHeight(110)
        self.boundary_edit.setMaximumHeight(160)
        polygon_layout.addWidget(self.boundary_edit)
        self.profile_stack.addWidget(rectangle)
        self.profile_stack.addWidget(polygon)
        points = initial.get("boundary_mm")
        if points is not None:
            self.boundary_edit.setPlainText(_polygon_text(points))
            self.profile_combo.setCurrentIndex(1)
            self.profile_stack.setCurrentIndex(1)
        else:
            self.boundary_edit.setPlainText(_polygon_text(self._rectangle()))
        self.geometry_summary = _summary("geometrySummary")
        for label, widget in (("ชื่อพื้น / Name", self.name_edit), ("ระดับผิวบน / Level", self.level_combo),
                              ("ระยะผิวบน / Top offset", self.offset_input),
                              ("ความหนาลง / Thickness", self.thickness_input),
                              ("วัสดุ / Material label", self.material_edit),
                              ("รูปขอบเขต / Boundary", self.profile_combo)):
            self.form.addRow(label, widget)
        self.form.addRow(self.profile_stack)
        self.form.addRow(self.geometry_summary)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        self.level_combo.currentIndexChanged.connect(self._update_summary)
        self.offset_input.valueChanged.connect(self._update_summary)
        self.thickness_input.valueChanged.connect(self._update_summary)
        self._update_summary()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _rectangle(self):
        x, y = self.x_input.value(), self.y_input.value()
        length, width = self.length_input.value(), self.width_input.value()
        return [(x, y), (x + length, y), (x + length, y + width), (x, y + width)]

    def _profile_changed(self, index):
        if index == 1:
            self.boundary_edit.setPlainText(_polygon_text(self._rectangle()))
        self.profile_stack.setCurrentIndex(index)

    def _update_summary(self, *_args):
        level = _selected(self.level_combo, self._levels)
        if level is None:
            self.geometry_summary.setText("เลือกระดับอ้างอิงผิวบน")
        else:
            top = _mm(level.Elevation) + self.offset_input.value()
            self.geometry_summary.setText("ผิวบน Z = {:,.3f} mm · ผิวล่าง Z = {:,.3f} mm".format(
                top, top - self.thickness_input.value()))

    def collect_values(self):
        return {"name": self.required_text(self.name_edit, "ชื่อพื้น"),
                "level": _required_object(self.level_combo, self._levels, "ระดับผิวบน"),
                "boundary_mm": self._rectangle() if self.profile_combo.currentIndex() == 0
                else _parse_polygon(self.boundary_edit.toPlainText()),
                "thickness_mm": self.thickness_input.value(), "offset_mm": self.offset_input.value(),
                "material": self.material_edit.text().strip()}


class ColumnDialog(FormDialog):
    def __init__(self, initial=None, levels=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขเสา / Edit Column" if editing else "3117 — สร้างเสา / Create Column",
            "ColumnDialog", "เสาแนวดิ่ง หน้าตัดสี่เหลี่ยมวางกึ่งกลาง X/Y · หมุนหน้าตัดรอบแกน Z", parent)
        self.name_edit = _line("nameEdit", initial.get("name", "Column 01"))
        self.x_input = _spin("centerXInput", initial.get("x_mm", 0.0))
        self.y_input = _spin("centerYInput", initial.get("y_mm", 0.0))
        self.width_input = _spin("widthInput", initial.get("width_mm", 300.0), 0.001)
        self.depth_input = _spin("depthInput", initial.get("depth_mm", 300.0), 0.001)
        self.rotation_input = _spin("rotationInput", initial.get("rotation_deg", 0.0), -3600.0, 3600.0)
        self.rotation_input.setSuffix(" °")
        self.rotation_input.setSingleStep(15.0)
        self.base_combo, self._base_levels = _object_combo(
            "baseLevelCombo", levels, initial.get("base_level"), _level_description)
        self.top_combo, self._top_levels = _object_combo(
            "topLevelCombo", levels, initial.get("top_level"), _level_description)
        self.base_offset_input = _spin("baseOffsetInput", initial.get("base_offset_mm", 0.0))
        self.top_offset_input = _spin("topOffsetInput", initial.get("top_offset_mm", 0.0))
        self.material_edit = _line("materialEdit", initial.get("material", ""))
        self.geometry_summary = _summary("geometrySummary")
        for label, widget in (("ชื่อเสา / Name", self.name_edit), ("จุดกึ่งกลาง X / Center X", self.x_input),
                              ("จุดกึ่งกลาง Y / Center Y", self.y_input), ("กว้างหน้าตัด / Width", self.width_input),
                              ("ลึกหน้าตัด / Depth", self.depth_input), ("หมุนหน้าตัด / Rotation Z", self.rotation_input),
                              ("ระดับฐาน / Base level", self.base_combo), ("ระยะจากฐาน / Base offset", self.base_offset_input),
                              ("ระดับยอด / Top level", self.top_combo), ("ระยะจากยอด / Top offset", self.top_offset_input),
                              ("วัสดุ / Material label", self.material_edit)):
            self.form.addRow(label, widget)
        self.form.addRow(self.geometry_summary)
        for combo in (self.base_combo, self.top_combo):
            combo.currentIndexChanged.connect(self._update_summary)
        self.base_offset_input.valueChanged.connect(self._update_summary)
        self.top_offset_input.valueChanged.connect(self._update_summary)
        self._update_summary()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _height(self):
        base, top = _selected(self.base_combo, self._base_levels), _selected(self.top_combo, self._top_levels)
        if base is None or top is None:
            return None
        return _mm(top.Elevation) + self.top_offset_input.value() - _mm(base.Elevation) - self.base_offset_input.value()

    def _update_summary(self, *_args):
        height = self._height()
        self.geometry_summary.setText("เลือกระดับฐานและระดับยอด" if height is None
                                      else "ความสูงก่อนตัดด้วยพื้น = {:,.3f} mm".format(height))

    def collect_values(self):
        base = _required_object(self.base_combo, self._base_levels, "ระดับฐาน")
        top = _required_object(self.top_combo, self._top_levels, "ระดับยอด")
        if self._height() <= 0:
            raise ValueError("ระดับยอดรวม Offset ต้องสูงกว่าระดับฐานรวม Offset")
        return {"name": self.required_text(self.name_edit, "ชื่อเสา"), "base_level": base, "top_level": top,
                "x_mm": self.x_input.value(), "y_mm": self.y_input.value(),
                "width_mm": self.width_input.value(), "depth_mm": self.depth_input.value(),
                "rotation_deg": self.rotation_input.value(), "base_offset_mm": self.base_offset_input.value(),
                "top_offset_mm": self.top_offset_input.value(), "material": self.material_edit.text().strip()}


class BeamDialog(FormDialog):
    def __init__(self, initial=None, levels=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขคาน / Edit Beam" if editing else "3117 — สร้างคาน / Create Beam",
            "BeamDialog", "คานแนวราบตามเส้นกึ่งกลาง XY · กว้างแบ่งสองข้าง · ลึกลงจากผิวบน Level + Offset", parent)
        start, end = initial.get("start_mm", (0, 0)), initial.get("end_mm", (6000, 0))
        self.name_edit = _line("nameEdit", initial.get("name", "Beam 01"))
        self.start_x_input = _spin("startXInput", start[0])
        self.start_y_input = _spin("startYInput", start[1])
        self.end_x_input = _spin("endXInput", end[0])
        self.end_y_input = _spin("endYInput", end[1])
        self.width_input = _spin("widthInput", initial.get("width_mm", 300.0), 0.001)
        self.depth_input = _spin("depthInput", initial.get("depth_mm", 450.0), 0.001)
        self.level_combo, self._levels = _object_combo("levelCombo", levels, initial.get("level"), _level_description)
        self.offset_input = _spin("offsetInput", initial.get("offset_mm", 0.0))
        self.material_edit = _line("materialEdit", initial.get("material", ""))
        self.geometry_summary = _summary("geometrySummary")
        for label, widget in (("ชื่อคาน / Name", self.name_edit), ("จุดเริ่ม X / Start X", self.start_x_input),
                              ("จุดเริ่ม Y / Start Y", self.start_y_input), ("จุดปลาย X / End X", self.end_x_input),
                              ("จุดปลาย Y / End Y", self.end_y_input), ("กว้างหน้าตัด / Width", self.width_input),
                              ("ลึกลง / Depth", self.depth_input), ("ระดับผิวบน / Level", self.level_combo),
                              ("ระยะผิวบน / Top offset", self.offset_input), ("วัสดุ / Material label", self.material_edit)):
            self.form.addRow(label, widget)
        self.form.addRow(self.geometry_summary)
        self.level_combo.currentIndexChanged.connect(self._update_summary)
        for widget in (self.start_x_input, self.start_y_input, self.end_x_input, self.end_y_input,
                       self.offset_input, self.depth_input):
            widget.valueChanged.connect(self._update_summary)
        self._update_summary()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _length(self):
        return math.hypot(self.end_x_input.value() - self.start_x_input.value(),
                          self.end_y_input.value() - self.start_y_input.value())

    def _update_summary(self, *_args):
        level = _selected(self.level_combo, self._levels)
        if level is None:
            self.geometry_summary.setText("เลือกระดับอ้างอิงผิวบนคาน")
        else:
            top = _mm(level.Elevation) + self.offset_input.value()
            self.geometry_summary.setText("ยาว {:,.3f} mm · ผิวบน Z {:,.3f} · ผิวล่าง Z {:,.3f} mm".format(
                self._length(), top, top - self.depth_input.value()))

    def collect_values(self):
        if self._length() <= 1e-6:
            raise ValueError("จุดเริ่มและจุดปลายคานต้องอยู่คนละตำแหน่ง")
        return {"name": self.required_text(self.name_edit, "ชื่อคาน"),
                "level": _required_object(self.level_combo, self._levels, "ระดับผิวบนคาน"),
                "start_mm": (self.start_x_input.value(), self.start_y_input.value()),
                "end_mm": (self.end_x_input.value(), self.end_y_input.value()),
                "width_mm": self.width_input.value(), "depth_mm": self.depth_input.value(),
                "offset_mm": self.offset_input.value(), "material": self.material_edit.text().strip()}


class JoinSlabDialog(FormDialog):
    def __init__(self, members, slabs, initial=None, unjoin=False, parent=None):
        initial = initial or {}
        self.unjoin = bool(unjoin)
        super().__init__(
            "3117 — ยกเลิกตัดด้วยพื้น / Unjoin Slab" if unjoin else "3117 — ตัดด้วยพื้น / Join Slab",
            "UnjoinSlabDialog" if unjoin else "JoinSlabDialog",
            "คืนเนื้อเสาหรือคานที่เคยตัดด้วยพื้นหนึ่งรายการ" if unjoin else
            "พื้นเป็นตัวตัด เสา/คานต้องเหลือเนื้อเดียว · ไม่ใช่การรวมพื้นเข้ากับโครงสร้างทุกชนิด", parent)
        self.member_combo, self._members = _object_combo(
            "joinMemberCombo", members, initial.get("member"),
            lambda obj: "{}  [{}]".format(obj.Label, obj.BIM3117Kind))
        self.slab_combo = QtWidgets.QComboBox()
        self.slab_combo.setObjectName("joinSlabCombo")
        self._all_slabs = list(slabs)
        self._slabs = []
        self._initial_slab = initial.get("slab")
        self.join_summary = _summary("joinSummary")
        self.form.addRow("เสาหรือคาน / Target", self.member_combo)
        self.form.addRow("พื้นตัวตัด / Slab", self.slab_combo)
        self.clear_all = QtWidgets.QCheckBox("ยกเลิกการตัดด้วยพื้นทั้งหมด / Remove all slab joins")
        self.clear_all.setObjectName("clearAllJoinsCheck")
        self.clear_all.setVisible(self.unjoin)
        if self.unjoin:
            self.form.addRow(self.clear_all)
            self.clear_all.toggled.connect(lambda enabled: self.slab_combo.setEnabled(not enabled))
        self.form.addRow(self.join_summary)
        self.member_combo.currentIndexChanged.connect(self._update_slabs)
        self._update_slabs()

    def _update_slabs(self, *_args):
        member = _selected(self.member_combo, self._members)
        existing = [obj for obj in getattr(member, "JoinSlabs", []) if obj is not None] if member is not None else []
        candidates = existing if self.unjoin else [slab for slab in self._all_slabs if slab not in existing]
        self.slab_combo.clear()
        self.slab_combo.addItem("— เลือกพื้น / Select slab —")
        self._slabs = [None] + candidates
        selected_index = 0
        for index, slab in enumerate(candidates, start=1):
            self.slab_combo.addItem(slab.Label)
            if _same_object(slab, self._initial_slab):
                selected_index = index
        if selected_index == 0 and len(candidates) == 1:
            selected_index = 1
        self.slab_combo.setCurrentIndex(selected_index)
        text = "พื้นที่ตัดอยู่ / Existing joins: " + (", ".join(slab.Label for slab in existing) or "—")
        if member is not None and getattr(member, "JoinSlabIds", []) and not existing:
            text += "\nอ้างอิงพื้นขาดหาย ใช้ Remove all slab joins เพื่อยกเลิกการอ้างอิงเดิม"
        self.join_summary.setText(text)

    def collect_values(self):
        return {"member": _required_object(self.member_combo, self._members, "เสาหรือคาน"),
                "slab": None if self.unjoin and self.clear_all.isChecked() else
                _required_object(self.slab_combo, self._slabs, "พื้นตัวตัด")}


def make_slab_dialog(**kwargs):
    return SlabDialog(**kwargs)


def make_column_dialog(**kwargs):
    return ColumnDialog(**kwargs)


def make_beam_dialog(**kwargs):
    return BeamDialog(**kwargs)


def make_join_slab_dialog(**kwargs):
    return JoinSlabDialog(**kwargs)
