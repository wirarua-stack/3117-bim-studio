# SPDX-License-Identifier: GPL-3.0-or-later
"""Native drawing definitions; forms never edit the document before acceptance."""

from .dialogs import FormDialog, _line, _mm, _object_combo, _required_object, _spin
from .qt import QtWidgets


VIEW_TYPES = ("Plan", "Section", "Elevation")
DIRECTIONS = ("+Y", "-Y", "+X", "-X")


def _check(name, text, value):
    widget = QtWidgets.QCheckBox(text)
    widget.setObjectName(name)
    widget.setChecked(bool(value))
    return widget


def _level_text(obj):
    return "{}  ({:,.3f} mm)".format(obj.Label, _mm(obj.Elevation))


class DrawingViewDialog(FormDialog):
    def __init__(self, initial=None, levels=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขมุมมองแบบ / Edit Drawing View" if editing else
            "3117 — สร้างมุมมองแบบ / Create Drawing View",
            "DrawingViewDialog",
            "กำหนดมุมมองจากรูปทรงในโมเดล · ระยะหน่วย mm · แบบใช้สเกลจริงเมื่อวางบน A3", parent)
        self.setMinimumWidth(520)
        self.name_edit = _line("nameEdit", initial.get("name", "Plan 01"))
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setObjectName("drawingViewTypeCombo")
        self.type_combo.addItems(["Plan / แปลน", "Section / รูปตัด", "Elevation / รูปด้าน"])
        view_type = initial.get("view_type", "Plan")
        self.type_combo.setCurrentIndex(VIEW_TYPES.index(view_type) if view_type in VIEW_TYPES else 0)
        self.form.addRow("ชื่อมุมมอง / Name", self.name_edit)
        self.form.addRow("ชนิดแบบ / View", self.type_combo)
        self.range_stack = QtWidgets.QStackedWidget()
        self.range_stack.setObjectName("drawingViewRangePages")
        plan = QtWidgets.QWidget()
        plan_form = QtWidgets.QFormLayout(plan)
        plan_form.setContentsMargins(0, 0, 0, 0)
        self.level_combo, self._levels = _object_combo("drawingLevelCombo", levels, initial.get("level"), _level_text)
        self.bottom_input = _spin("drawingBottomOffsetInput", initial.get("bottom_offset_mm", -200))
        self.cut_input = _spin("drawingCutOffsetInput", initial.get("cut_offset_mm", 1200))
        self.top_input = _spin("drawingTopOffsetInput", initial.get("top_offset_mm", 2700))
        for label, widget in (("ระดับอ้างอิง / Level", self.level_combo),
                              ("ขอบล่างจาก Level / Bottom", self.bottom_input),
                              ("ระยะตัดจาก Level / Cut", self.cut_input),
                              ("ขอบบนจาก Level / Top", self.top_input)):
            plan_form.addRow(label, widget)
        self.plan_summary = QtWidgets.QLabel()
        self.plan_summary.setObjectName("drawingPlanRangeSummary")
        self.plan_summary.setWordWrap(True)
        plan_form.addRow(self.plan_summary)
        vertical = QtWidgets.QWidget()
        vertical_form = QtWidgets.QFormLayout(vertical)
        vertical_form.setContentsMargins(0, 0, 0, 0)
        origin = initial.get("origin_mm", (0, 0, 0))
        self.origin_x = _spin("drawingOriginXInput", origin[0])
        self.origin_y = _spin("drawingOriginYInput", origin[1])
        self.origin_z = _spin("drawingOriginZInput", origin[2])
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.setObjectName("drawingDirectionCombo")
        self.direction_combo.addItems(["+Y / มองจากใต้ไปเหนือ", "-Y / มองจากเหนือไปใต้",
                                       "+X / มองจากตะวันตกไปตะวันออก", "-X / มองจากตะวันออกไปตะวันตก"])
        direction = initial.get("direction", "+Y")
        self.direction_combo.setCurrentIndex(DIRECTIONS.index(direction) if direction in DIRECTIONS else 0)
        self.depth_input = _spin("drawingDepthInput", initial.get("depth_mm", 10000), .001)
        for label, widget in (("ระนาบเริ่ม X / Origin X", self.origin_x),
                              ("ระนาบเริ่ม Y / Origin Y", self.origin_y),
                              ("จุดอ้างอิง Z / Origin Z", self.origin_z),
                              ("ทิศมองเข้าโมเดล / Look direction", self.direction_combo),
                              ("ระยะลึกจากระนาบ / Depth", self.depth_input)):
            vertical_form.addRow(label, widget)
        hint = QtWidgets.QLabel("Section ตัดที่ระนาบเริ่ม · Elevation วางระนาบนอกอาคาร\n"
                                "Depth คือระยะที่มองเข้าไปในโมเดลตามทิศที่เลือก")
        hint.setWordWrap(True)
        vertical_form.addRow(hint)
        self.range_stack.addWidget(plan)
        self.range_stack.addWidget(vertical)
        self.form.addRow(self.range_stack)
        self.scale_input = _spin("drawingScaleInput", initial.get("scale_denominator", 50), 1, 1000)
        self.scale_input.setSuffix("")
        self.scale_input.setPrefix("1 : ")
        self.scale_input.setDecimals(0)
        self.scale_input.setSingleStep(25)
        self.form.addRow("มาตราส่วน / Scale", self.scale_input)
        self.dimensions_check = _check("drawingDimensionsCheck", "มิติรวมจากขอบเขตรูปฉาย / Overall dimensions",
                                       initial.get("show_dimensions", True))
        self.tags_check = _check("drawingTagsCheck", "ป้ายชื่อองค์ประกอบ / Source labels", initial.get("show_tags", True))
        self.grid_check = _check("drawingGridCheck", "กริดอ้างอิง / Grid references", initial.get("show_grid", True))
        self.levels_check = _check("drawingLevelsCheck", "ระดับอ้างอิง / Level references", initial.get("show_levels", True))
        options = QtWidgets.QWidget()
        options_layout = QtWidgets.QGridLayout(options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        for index, widget in enumerate((self.dimensions_check, self.tags_check, self.grid_check, self.levels_check)):
            options_layout.addWidget(widget, index // 2, index % 2)
        self.form.addRow(options)
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        self.level_combo.currentIndexChanged.connect(self._update_range)
        for widget in (self.bottom_input, self.cut_input, self.top_input):
            widget.valueChanged.connect(self._update_range)
        self._type_changed()
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _type_changed(self, *_args):
        plan = self.type_combo.currentIndex() == 0
        self.range_stack.setCurrentIndex(0 if plan else 1)
        self.grid_check.setEnabled(plan)
        self.levels_check.setEnabled(not plan)
        self._update_range()
        self.adjustSize()

    def _update_range(self, *_args):
        index = self.level_combo.currentIndex()
        if 0 <= index < len(self._levels) and self._levels[index] is not None:
            base = _mm(self._levels[index].Elevation)
            self.plan_summary.setText("ระดับจริง Z: ล่าง {:,.0f} · ตัด {:,.0f} · บน {:,.0f} mm".format(
                base + self.bottom_input.value(), base + self.cut_input.value(), base + self.top_input.value()))
        else:
            self.plan_summary.setText("เลือกระดับอ้างอิงของแปลน")

    def collect_values(self):
        view_type = VIEW_TYPES[self.type_combo.currentIndex()]
        level = None
        if view_type == "Plan":
            level = _required_object(self.level_combo, self._levels, "ระดับอ้างอิง")
        if not self.bottom_input.value() < self.cut_input.value() < self.top_input.value():
            raise ValueError("ช่วงแปลนต้องเป็น Bottom < Cut < Top")
        return {"name": self.required_text(self.name_edit, "ชื่อมุมมอง"), "view_type": view_type,
                "level": level, "bottom_offset_mm": self.bottom_input.value(),
                "cut_offset_mm": self.cut_input.value(), "top_offset_mm": self.top_input.value(),
                "origin_mm": ((0, 0, 0) if view_type == "Plan" else
                              (self.origin_x.value(), self.origin_y.value(), self.origin_z.value())),
                "direction": DIRECTIONS[self.direction_combo.currentIndex()], "depth_mm": self.depth_input.value(),
                "scale_denominator": self.scale_input.value(),
                "show_dimensions": self.dimensions_check.isChecked(), "show_tags": self.tags_check.isChecked(),
                "show_grid": self.grid_check.isChecked(), "show_levels": self.levels_check.isChecked()}


class DrawingSheetDialog(FormDialog):
    def __init__(self, initial=None, views=None, editing=False, parent=None):
        initial = initial or {}
        super().__init__(
            "3117 — แก้ไขแผ่นแบบ / Edit Drawing Sheet" if editing else
            "3117 — สร้างแผ่นแบบ / Create Drawing Sheet",
            "DrawingSheetDialog",
            "A3 แนวนอน · วางได้ 1–2 มุมมอง · ใช้มาตราส่วนของแต่ละมุมมอง โดยไม่ย่อให้พอดีอัตโนมัติ", parent)
        self.setMinimumWidth(540)
        self.name_edit = _line("nameEdit", initial.get("name", "Drawing Sheet 01"))
        self.number_edit = _line("sheetNumberEdit", initial.get("number", "A001"))
        self.issue_edit = _line("sheetIssueEdit", initial.get("issue", "P01"))
        self.author_edit = _line("sheetAuthorEdit", initial.get("author", ""))
        chosen = list(initial.get("views", []))
        self.first_combo, self._first_views = _object_combo("sheetFirstViewCombo", views,
            chosen[0] if chosen else None, self._description)
        self.second_combo = QtWidgets.QComboBox()
        self.second_combo.setObjectName("sheetSecondViewCombo")
        self._second_views = [None] + list(views or [])
        self.second_combo.addItem("— หนึ่งมุมมองเต็มแผ่น / One view —")
        for view in self._second_views[1:]:
            self.second_combo.addItem(self._description(view))
        if len(chosen) > 1:
            index = next((i for i, obj in enumerate(self._second_views) if obj is not None and obj.Name == chosen[1].Name), 0)
            self.second_combo.setCurrentIndex(index)
        for label, widget in (("ชื่อแผ่นแบบ / Name", self.name_edit), ("เลขแบบ / Number", self.number_edit),
                              ("ฉบับ / Issue", self.issue_edit), ("ผู้จัดทำ / Author", self.author_edit),
                              ("มุมมองแรก / View 1", self.first_combo), ("มุมมองที่สอง / View 2", self.second_combo)):
            self.form.addRow(label, widget)
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    @staticmethod
    def _description(view):
        return "{}  ({} · 1:{:g})".format(view.Label, str(view.ViewType), _mm(view.ScaleDenominator))

    def collect_values(self):
        first = _required_object(self.first_combo, self._first_views, "มุมมองแรก")
        second = self._second_views[self.second_combo.currentIndex()]
        if second is not None and second.Name == first.Name:
            raise ValueError("เลือกมุมมองต่างกันสองมุม หรือเลือกหนึ่งมุมมองเต็มแผ่น")
        return {"name": self.required_text(self.name_edit, "ชื่อแผ่นแบบ"),
                "number": self.required_text(self.number_edit, "เลขแบบ"),
                "issue": self.issue_edit.text().strip(),
                "author": self.author_edit.text().strip(), "views": [first] + ([second] if second is not None else [])}


def view_initial(view):
    return {"name": view.Label, "view_type": str(view.ViewType), "level": view.Level,
            "bottom_offset_mm": _mm(view.BottomOffset), "cut_offset_mm": _mm(view.CutOffset),
            "top_offset_mm": _mm(view.TopOffset), "origin_mm": tuple(view.Origin),
            "direction": str(view.Direction), "depth_mm": _mm(view.Depth),
            "scale_denominator": float(view.ScaleDenominator), "show_dimensions": bool(view.ShowDimensions),
            "show_tags": bool(view.ShowTags), "show_grid": bool(view.ShowGrid), "show_levels": bool(view.ShowLevels)}


def sheet_initial(sheet):
    return {"name": sheet.Label, "number": str(sheet.Number), "issue": str(sheet.Issue),
            "author": str(sheet.Author), "views": list(sheet.Views)}
