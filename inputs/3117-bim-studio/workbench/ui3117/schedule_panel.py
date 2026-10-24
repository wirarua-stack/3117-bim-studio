# SPDX-License-Identifier: GPL-3.0-or-later
"""Schedules remain projections of native objects, never editable quantity copies."""

from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtWidgets, enum_value, run_dialog
from .model_panels import ModelPanel, readonly_table, fill_table, show_panel
from .schedule_dialogs import ScheduleDefinitionDialog, ScheduleRowDialog, schedule_initial


_PANELS = {}


def _core():
    from bim3117_freecad import schedules
    return schedules


def edit_schedule(obj, parent=None):
    before = _core().schedule_state(obj)
    dialog = ScheduleDefinitionDialog(obj.Project, schedule_initial(obj), True, parent)
    if run_dialog(dialog):
        if _core().schedule_state(obj) != before:
            raise ValueError("โมเดลหรือตารางเปลี่ยนระหว่างแก้ไข / Source changed; reopen the definition editor")
        _core().edit_schedule(obj, **dialog.values())
        return True
    return False


class SchedulePanel(ModelPanel):
    def __init__(self, project, schedule=None):
        super().__init__(project, "BIM3117SchedulePanel", "3117 — Schedules / ตารางปริมาณ", _PANELS)
        self.resize(940, 500)
        self.schedule_id = str(schedule.BIM3117Id) if schedule is not None else None
        self._schedules = []
        self.source_snapshot = None
        self.latest_export = None
        layout = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Schedule"))
        self.schedule_combo = QtWidgets.QComboBox()
        self.schedule_combo.setObjectName("scheduleCombo")
        self.schedule_combo.setMinimumWidth(240)
        self.schedule_combo.currentIndexChanged.connect(self._selected_schedule)
        row.addWidget(self.schedule_combo, 1)
        for label, name, slot in (("+ Schedule", "newScheduleButton", self.create_schedule),
                                  ("Edit definition", "editScheduleButton", self.edit_definition),
                                  ("Delete", "deleteScheduleButton", self.delete_schedule)):
            button = QtWidgets.QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            row.addWidget(button)
            setattr(self, name, button)
        layout.addLayout(row)
        self.definition_label = QtWidgets.QLabel()
        self.definition_label.setObjectName("scheduleDefinitionLabel")
        self.definition_label.setWordWrap(True)
        layout.addWidget(self.definition_label)
        self.table = readonly_table("scheduleTable", [])
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(lambda *_args: self.edit_row())
        layout.addWidget(self.table, 1)
        self.totals_label = QtWidgets.QLabel()
        self.totals_label.setObjectName("scheduleTotalsLabel")
        self.totals_label.setWordWrap(True)
        layout.addWidget(self.totals_label)
        self.coverage_label = QtWidgets.QLabel()
        self.coverage_label.setObjectName("scheduleCoverageLabel")
        self.coverage_label.setWordWrap(True)
        layout.addWidget(self.coverage_label)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("scheduleStatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.export_label = QtWidgets.QLabel("CSV export includes a metadata file with both revisions.")
        self.export_label.setObjectName("scheduleExportLabel")
        self.export_label.setWordWrap(True)
        layout.addWidget(self.export_label)
        footer = QtWidgets.QHBoxLayout()
        for label, name, slot in (("Select source", "selectScheduleSourceButton", self.select_source),
                                  ("Edit source row", "editScheduleRowButton", self.edit_row),
                                  ("Refresh", "refreshScheduleButton", self.refresh),
                                  ("Export CSV", "exportScheduleCSVButton", self.export_csv),
                                  ("Close", "closeScheduleButton", self.close)):
            button = QtWidgets.QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            footer.addWidget(button)
            setattr(self, name, button)
        self.export_button = self.exportScheduleCSVButton
        layout.addLayout(footer)
        self.refresh()

    def _schedule(self):
        return next((obj for obj in _core().list_schedules(self._project())
                     if str(obj.BIM3117Id) == self.schedule_id), None)

    def _selected_schedule(self, index):
        if not 0 <= index < len(self._schedules):
            return
        self.schedule_id = str(self._schedules[index].BIM3117Id)
        self.source_snapshot = None
        self.refresh()

    def _row(self):
        index = self.table.currentRow()
        rows = self.source_snapshot.get("rows", []) if self.source_snapshot else []
        return rows[index] if 0 <= index < len(rows) else None

    def _update_buttons(self):
        row = self._row()
        has_schedule = self.source_snapshot is not None
        fresh = has_schedule and not self._dirty and not self._transaction_open
        self.editScheduleButton.setEnabled(has_schedule)
        self.deleteScheduleButton.setEnabled(has_schedule)
        self.selectScheduleSourceButton.setEnabled(bool(row and row.get("element_ids")))
        self.editScheduleRowButton.setEnabled(bool(fresh and row and len(row.get("element_ids", [])) == 1
            and self.source_snapshot.get("definition", {}).get("group_by", "None") == "None"))
        self._set_export_enabled(fresh)

    def mark_stale(self):
        super().mark_stale()
        if hasattr(self, "editScheduleRowButton"):
            self.editScheduleRowButton.setEnabled(False)
        self._update_export_status(pending=True)

    def refresh(self, *_args):
        if self._closed or self._transaction_open or self._editing:
            return False
        self._refreshing = True
        try:
            core, project = _core(), self._project()
            selected_row_id = (self._row() or {}).get("row_id")
            self._schedules = core.list_schedules(project)
            self.schedule_combo.blockSignals(True)
            self.schedule_combo.clear()
            for obj in self._schedules:
                self.schedule_combo.addItem(obj.Label)
            index = next((index for index, obj in enumerate(self._schedules)
                          if str(obj.BIM3117Id) == self.schedule_id), 0 if self._schedules else -1)
            self.schedule_combo.setCurrentIndex(index)
            self.schedule_combo.blockSignals(False)
            self.schedule_id = str(self._schedules[index].BIM3117Id) if index >= 0 else None
            if index < 0:
                self.source_snapshot = None
                self.table.setRowCount(0)
                self.table.setColumnCount(0)
                self.definition_label.setText("สร้างตารางเพื่อเลือกหมวด ตัวกรอง และการจัดกลุ่ม / Create a schedule to begin")
                self.totals_label.clear()
                self.coverage_label.clear()
                self.status_label.setText("No schedule definitions in this document")
                self._dirty = False
                self._update_buttons()
                return True
            schedule = self._schedules[index]
            source = core.capture_schedule(schedule)
            self.source_snapshot = source
            columns = source["columns"]
            self.table.setColumnCount(len(columns))
            self.table.setHorizontalHeaderLabels([str(item["label"]) + (" / " + str(item["unit"]) if item.get("unit") else "") for item in columns])
            def display(value):
                if value is None:
                    return "—"
                if isinstance(value, float):
                    return "{:.6f}".format(value).rstrip("0").rstrip(".")
                if isinstance(value, list):
                    return ", ".join(str(item) for item in value)
                return str(value)
            fill_table(self.table, [[display(row.get(col["key"])) for col in columns] for row in source["rows"]])
            for row_index, row in enumerate(source["rows"]):
                if row.get("row_id") == selected_row_id:
                    self.table.selectRow(row_index)
            self.definition_label.setText("{} · Level: {} · Type: {} · Group: {} · Sort: {}{}{}".format(
                schedule.Category, schedule.FilterLevel.Label if schedule.FilterLevel else "All",
                schedule.FilterType.Label if schedule.FilterType else "All", schedule.GroupBy,
                schedule.SortBy, " ↓" if schedule.Descending else " ↑",
                " · Name: " + str(schedule.NameFilter) if schedule.NameFilter else ""))
            totals = source.get("totals", {})
            self.totals_label.setText("{} rows · {}".format(len(source["rows"]), " · ".join(
                "{}: {}".format(key.replace("_", " "), display(value)) for key, value in totals.items()
                if isinstance(value, (int, float)))))
            material_coverage = source.get("coverage", {}).get("material", {})
            if str(schedule.Category) == "Material":
                self.coverage_label.setText(
                    "Assigned native materials: {}/{} products · Unassigned: {}. "
                    "Layers partition each product volume; do not add these totals to product quantities."
                    .format(material_coverage.get("assigned_product_count", 0), material_coverage.get("product_count", 0),
                            material_coverage.get("unassigned_product_count", 0)))
            else:
                self.coverage_label.setText("One source UUID per ungrouped row · Totals sum product quantities; overlapping products are not unioned.")
            self.coverage_label.setToolTip("\n".join(source.get("coverage", {}).get("quantity_rules", [])))
            self.status_label.setText("Current · Model {} · Schedule {} · Quantities are read-only".format(
                source["model_revision"][:12], source["schedule_revision"][:12]))
            self._dirty = False
            self.last_error = None
            self._update_buttons()
            self._update_export_status()
            return True
        except Exception as error:
            self.last_error = str(error)
            self.status_label.setText("Cannot refresh: " + str(error))
            self._dirty = True
            self._set_export_enabled(False)
            self.editScheduleRowButton.setEnabled(False)
            return False
        finally:
            self._refreshing = False

    def _action(self, title, action):
        self._editing = True
        try:
            return action()
        except Exception as error:
            self._fail(title, error)
            return None
        finally:
            self._editing = False
            self.refresh()

    def create_schedule(self):
        def action():
            from .commands import _next_name
            project = self._project()
            dialog = ScheduleDefinitionDialog(project, {"name": _next_name(_core().list_schedules(project), "Schedule")}, parent=self)
            if run_dialog(dialog):
                obj = _core().create_schedule(project, **dialog.values())
                self.schedule_id = str(obj.BIM3117Id)
        return self._action("Create Schedule", action)

    def edit_definition(self):
        obj = self._schedule()
        if obj is not None:
            return self._action("Edit Schedule", lambda: edit_schedule(obj, self))

    def delete_schedule(self):
        obj = self._schedule()
        if obj is not None:
            return self._action("Delete Schedule", lambda: _core().delete_schedule(obj))

    def _source_objects(self, row):
        objects = {str(getattr(obj, "BIM3117Id", "")): obj for obj in self._project().Document.Objects}
        values = [objects.get(str(identity)) for identity in row.get("element_ids", [])]
        if not values or any(obj is None for obj in values):
            raise ValueError("Source changed; refresh the schedule")
        return values

    def select_source(self):
        row = self._row()
        if not row:
            return
        try:
            objects = self._source_objects(row)
            App.setActiveDocument(self.document_name)
            Gui.Selection.clearSelection()
            for obj in objects:
                Gui.Selection.addSelection(self.document_name, obj.Name)
            self.status_label.setText("Selected: " + ", ".join(obj.Label for obj in objects))
        except Exception as error:
            self._fail("Select Schedule Source", error)

    def edit_row(self):
        row, source = self._row(), self.source_snapshot
        if row is None or source is None or self._dirty:
            return
        if len(row.get("element_ids", [])) != 1 or source["definition"]["group_by"] != "None":
            self.status_label.setText("เลือกตารางแบบไม่จัดกลุ่มเพื่อแก้ต้นทาง / Edit a source in an ungrouped schedule")
            return
        def action():
            obj = self._source_objects(row)[0]
            dialog = ScheduleRowDialog(obj, self)
            if run_dialog(dialog):
                changes = dialog.values()
                if changes:
                    _core().edit_row(self._schedule(), str(obj.BIM3117Id), changes,
                                     expected_model_revision=source["model_revision"],
                                     expected_schedule_revision=source["schedule_revision"])
        return self._action("Edit Schedule Source", action)

    def _update_export_status(self, pending=False):
        if not self.latest_export or not hasattr(self, "export_label"):
            return
        result, current = self.latest_export, self.source_snapshot
        if pending:
            state = "Check pending"
        elif current is not None and all(result.get(key) == current[key] for key in ("model_revision", "schedule_revision")):
            state = "Current snapshot"
        else:
            state = "Stale snapshot — export again"
        files = result.get("files", [])
        self.export_label.setText("CSV · {} · {}".format(state, files[0] if files else ""))

    def _choose_path(self):
        project = self._project()
        filename = str(project.Document.FileName or "")
        folder = str(Path(filename).parent) if filename else str(Path.home())
        dialog = QtWidgets.QFileDialog(self, "3117 — Export Schedule CSV", folder)
        dialog.setObjectName("BIM3117ScheduleExportFileDialog")
        dialog.setAcceptMode(enum_value(QtWidgets.QFileDialog, "AcceptSave", "AcceptMode"))
        dialog.setFileMode(enum_value(QtWidgets.QFileDialog, "AnyFile", "FileMode"))
        dialog.setOption(enum_value(QtWidgets.QFileDialog, "DontConfirmOverwrite", "Option"), True)
        dialog.setNameFilter("CSV (*.csv)")
        dialog.setDefaultSuffix("csv")
        dialog.selectFile("3117_schedule_" + self.source_snapshot["schedule_revision"][:8] + ".csv")
        if not run_dialog(dialog):
            return None
        paths = dialog.selectedFiles()
        return paths[0] if paths else None

    def _confirm_overwrite(self, paths):
        existing = [str(path) for path in paths if Path(path).exists()]
        if not existing:
            return True
        dialog = QtWidgets.QMessageBox(self)
        dialog.setObjectName("BIM3117ScheduleOverwriteDialog")
        dialog.setWindowTitle("3117 — Replace schedule export files")
        dialog.setText("แทนที่ไฟล์เหล่านี้หรือไม่? / Replace these files?\n\n" + "\n".join(existing))
        yes = enum_value(QtWidgets.QMessageBox, "Yes", "StandardButton")
        no = enum_value(QtWidgets.QMessageBox, "No", "StandardButton")
        dialog.setStandardButtons(yes | no)
        dialog.setDefaultButton(no)
        runner = getattr(dialog, "exec", None) or dialog.exec_
        return runner() == yes

    def export_csv(self):
        if not self.refresh() or self.source_snapshot is None:
            return None
        source, schedule = self.source_snapshot, self._schedule()
        def action():
            path = self._choose_path()
            if not path:
                return None
            paths = _core().output_paths(path)
            had_existing = any(Path(item).exists() for item in paths)
            if not self._confirm_overwrite(paths):
                return None
            result = _core().export_schedule(schedule, path, overwrite=had_existing,
                expected_model_revision=source["model_revision"], expected_schedule_revision=source["schedule_revision"])
            self.latest_export = result
            return result
        return self._action("Export Schedule CSV", action)


def show_schedules(project, schedule=None):
    panel = _PANELS.get(project.Document.Name)
    if panel is None or panel._closed:
        panel = SchedulePanel(project, schedule)
    elif schedule is not None:
        panel.schedule_id = str(schedule.BIM3117Id)
        panel.refresh()
    return show_panel(panel, _PANELS)


def panel_for_document(name):
    return _PANELS.get(name)
