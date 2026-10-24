# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only, document-bound quantities and explicit snapshot exports.

This dialog owns presentation state only. Authored values, validation, quantity
rules, revision calculation and file writing all belong to the native modules.
"""

from pathlib import Path
import weakref

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets, enum_value, run_dialog


_PANELS = {}


def _enum(owner, name, group):
    return enum_value(owner, name, group)


def _modules():
    from bim3117_freecad import snapshot, exchange
    return snapshot, exchange


def _document_name(document):
    try:
        return document.Name
    except Exception:
        return None


class _DocumentObserver:
    """Only queue UI refreshes; never compute inside a native change callback."""

    def __init__(self, panel):
        self.panel = weakref.ref(panel)

    def _target(self, document):
        panel = self.panel()
        if panel is None or panel._closed or _document_name(document) != panel.document_name:
            return None
        return panel

    def _change(self, document):
        panel = self._target(document)
        if panel is not None:
            panel.mark_stale()

    def slotChangedObject(self, obj, prop):
        self._change(obj.Document)

    def slotCreatedObject(self, obj):
        self._change(obj.Document)

    def slotDeletedObject(self, obj):
        self._change(obj.Document)

    def slotChangedDocument(self, doc, prop):
        self._change(doc)

    def slotRecomputedDocument(self, doc):
        self._change(doc)

    def slotUndoDocument(self, doc):
        self._change(doc)

    def slotRedoDocument(self, doc):
        self._change(doc)

    def slotOpenTransaction(self, doc, name):
        panel = self._target(doc)
        if panel is not None:
            panel._transaction_open = True
            panel.mark_stale()

    def slotCommitTransaction(self, doc):
        panel = self._target(doc)
        if panel is not None:
            panel._transaction_open = False
            panel.mark_stale()

    def slotAbortTransaction(self, doc):
        self.slotCommitTransaction(doc)

    def slotDeletedDocument(self, doc):
        panel = self._target(doc)
        if panel is not None:
            panel._document_available = False
            panel._set_export_enabled(False)
            panel.status_label.setText("เอกสารถูกปิดแล้ว / Document closed")
            QtCore.QTimer.singleShot(0, lambda: panel.close() if not panel._closed else None)


class CoverageDialog(QtWidgets.QDialog):
    """Review exclusions before choosing output files."""

    def __init__(self, source, format_name, parent=None):
        super().__init__(parent)
        self.setObjectName("BIM3117ExportCoverageDialog")
        self.setWindowTitle("3117 — Review {} export / ตรวจขอบเขตส่งออก".format(format_name.upper()))
        self.resize(680, 420)
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("ส่งออกข้อมูลจากโมเดลรุ่น {}".format(source["content_revision"][:12]))
        layout.addWidget(title)
        coverage = source["coverage"]
        counts = coverage.get("counts", {})
        summary = QtWidgets.QLabel(
            "Walls: {}   Doors: {}   Windows: {}\nSlabs: {}   Columns: {}   Beams: {}\n"
            "Mapped: {}   Derived: {}   Reference: {}   Unsupported: {}".format(
                len(source["wall_rows"]), len(source["door_rows"]), len(source.get("window_rows", [])),
                len(source.get("slab_rows", [])), len(source.get("column_rows", [])), len(source.get("beam_rows", [])),
                counts.get("mapped", 0), counts.get("derived", 0),
                counts.get("reference", 0), counts.get("unsupported", 0)))
        summary.setObjectName("coverageSummary")
        layout.addWidget(summary)
        detail = QtWidgets.QPlainTextEdit()
        detail.setObjectName("coverageDetails")
        detail.setReadOnly(True)
        lines = ["CSV: หนึ่งแถวต่อ UUID ของ Wall / Door / Window / Slab / Column / Beam ที่มีอยู่.",
                 "WallBody เป็นรูปทรงของ Wall และไม่นับซ้ำ; แต่ละประเภทมีไฟล์ CSV ของตนเอง.",
                 "IFC4: ส่งออกเฉพาะชนิดที่มี mapping; รายการที่ข้ามอยู่ใน metadata.",
                 "ไฟล์ส่งออกเป็น snapshot; แก้โมเดลภายหลังแล้วต้องส่งออกใหม่.", ""]
        excluded = [item for item in coverage.get("items", [])
                    if item["status"] in ("reference", "unsupported")]
        for item in excluded:
            lines.append("{} [{}] — {}: {}".format(item.get("label", item["object_name"]),
                         item["kind"], item["status"], item.get("reason", "")))
        lines.extend(coverage.get("warnings", []))
        detail.setPlainText("\n".join(lines))
        layout.addWidget(detail)
        self.acknowledge = QtWidgets.QCheckBox("รับทราบรายการที่ไม่รวมในการส่งออก / Acknowledge exclusions")
        self.acknowledge.setObjectName("coverageAcknowledge")
        self.acknowledge.setVisible(bool(excluded))
        layout.addWidget(self.acknowledge)
        buttons = QtWidgets.QDialogButtonBox(
            _enum(QtWidgets.QDialogButtonBox, "Ok", "StandardButton") |
            _enum(QtWidgets.QDialogButtonBox, "Cancel", "StandardButton"))
        self.accept_button = buttons.button(_enum(QtWidgets.QDialogButtonBox, "Ok", "StandardButton"))
        self.accept_button.setText("เลือกไฟล์ / Choose files")
        self.accept_button.setObjectName("coverageContinueButton")
        self.accept_button.setEnabled(not excluded)
        buttons.button(_enum(QtWidgets.QDialogButtonBox, "Cancel", "StandardButton")).setObjectName("coverageCancelButton")
        self.acknowledge.toggled.connect(self.accept_button.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class QuantityDialog(QtWidgets.QDialog):
    WALL_COLUMNS = (
        ("name", "Wall"), ("type_name", "Type"), ("base_level", "Base"),
        ("top_level", "Top"), ("length_m", "Length (m)"), ("height_m", "Height (m)"),
        ("thickness_m", "Thickness (m)"), ("gross_side_area_m2", "Gross area (m²)"),
        ("opening_side_area_m2", "Openings (m²)"), ("net_side_area_m2", "Net area (m²)"),
        ("gross_volume_m3", "Gross (m³)"), ("opening_volume_m3", "Openings (m³)"),
        ("net_volume_m3", "Net (m³)"),
    )
    DOOR_COLUMNS = (
        ("name", "Door"), ("host_name", "Host Wall"), ("base_level", "Base"),
        ("width_m", "Opening W (m)"), ("height_m", "Opening H (m)"),
        ("offset_m", "Offset (m)"), ("sill_m", "Sill (m)"),
        ("opening_area_m2", "Opening (m²)"), ("opening_volume_m3", "Opening (m³)"),
        ("frame_volume_m3", "Frame (m³)"), ("count", "Count"),
    )
    WINDOW_COLUMNS = (("name", "Window"),) + DOOR_COLUMNS[1:]
    SLAB_COLUMNS = (
        ("name", "Slab"), ("level", "Level"), ("offset_m", "Top offset (m)"), ("top_z_m", "Top Z (m)"),
        ("thickness_m", "Thickness (m)"), ("net_area_m2", "Plan area (m²)"),
        ("perimeter_m", "Perimeter (m)"), ("net_volume_m3", "Net (m³)"), ("material", "Material"),
    )
    COLUMN_COLUMNS = (
        ("name", "Column"), ("base_level", "Base"), ("top_level", "Top"),
        ("x_m", "Center X (m)"), ("y_m", "Center Y (m)"), ("rotation_deg", "Rotation (°)"),
        ("width_m", "Width (m)"), ("depth_m", "Depth (m)"), ("height_m", "Height (m)"),
        ("gross_volume_m3", "Gross (m³)"), ("join_deduction_m3", "Slab cut (m³)"),
        ("net_volume_m3", "Net (m³)"), ("join_count", "Joins"), ("material", "Material"),
    )
    BEAM_COLUMNS = (
        ("name", "Beam"), ("level", "Level"), ("offset_m", "Top offset (m)"), ("top_z_m", "Top Z (m)"),
        ("length_m", "Length (m)"), ("width_m", "Width (m)"), ("depth_m", "Depth (m)"),
        ("gross_volume_m3", "Gross (m³)"), ("join_deduction_m3", "Slab cut (m³)"),
        ("net_volume_m3", "Net (m³)"), ("join_count", "Joins"), ("material", "Material"),
    )
    COVERAGE_COLUMNS = (
        ("label", "Object"), ("kind", "Kind"), ("status", "Coverage"),
        ("ifc_class", "IFC class"), ("reason", "Explanation"),
    )

    def __init__(self, project, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.setObjectName("BIM3117QuantityDialog")
        self.setWindowTitle("3117 — Quantities & Exchange | " + project.Label)
        self.setModal(False)
        # A resizable modeless window leaves the upper viewport usable.
        # Wider categories scroll horizontally rather than forcing a full-screen table.
        self.resize(1020, 480)
        self.document_name = project.Document.Name
        self.project_id = str(project.BIM3117Id)
        self.source_snapshot = None
        self.latest_exports = {}
        self._refreshing = False
        self._exporting = False
        self._transaction_open = False
        self._document_available = True
        self._closed = False
        self._dirty = True
        self.last_error = ""
        self._build_ui()
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(180)
        self.refresh_timer.timeout.connect(self.refresh)
        self.observer = _DocumentObserver(self)
        App.addDocumentObserver(self.observer)
        self.finished.connect(self._detach)
        self.refresh()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("QUANTITIES  /  ปริมาณจากโมเดล")
        title.setStyleSheet("font-weight: 700; font-size: 17px; color: #14304b; padding: 5px 0;")
        layout.addWidget(title)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("quantityStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.revision_label = QtWidgets.QLabel()
        self.revision_label.setObjectName("quantityRevision")
        self.revision_label.setTextInteractionFlags(_enum(QtCore.Qt, "TextSelectableByMouse", "TextInteractionFlag"))
        layout.addWidget(self.revision_label)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setObjectName("quantityTabs")
        self.wall_table = self._table("wallQuantityTable", self.WALL_COLUMNS)
        self.door_table = self._table("doorQuantityTable", self.DOOR_COLUMNS)
        self.window_table = self._table("windowQuantityTable", self.WINDOW_COLUMNS)
        self.slab_table = self._table("slabQuantityTable", self.SLAB_COLUMNS)
        self.column_table = self._table("columnQuantityTable", self.COLUMN_COLUMNS)
        self.beam_table = self._table("beamQuantityTable", self.BEAM_COLUMNS)
        self.coverage_table = self._table("exportCoverageTable", self.COVERAGE_COLUMNS)
        self._quantity_tables = (
            (self.wall_table, "wall_rows", self.WALL_COLUMNS, "Walls / ผนัง"),
            (self.door_table, "door_rows", self.DOOR_COLUMNS, "Doors / ประตู"),
            (self.slab_table, "slab_rows", self.SLAB_COLUMNS, "Slabs / พื้น"),
            (self.column_table, "column_rows", self.COLUMN_COLUMNS, "Columns / เสา"),
            (self.beam_table, "beam_rows", self.BEAM_COLUMNS, "Beams / คาน"),
            (self.window_table, "window_rows", self.WINDOW_COLUMNS, "Windows / หน้าต่าง"),
        )
        for table, _key, _columns, label in self._quantity_tables:
            self.tabs.addTab(table, label)
            table.cellClicked.connect(lambda row, column, table=table: self.select_source(table, row))
        self.tabs.addTab(self.coverage_table, "Coverage / ขอบเขต")
        layout.addWidget(self.tabs, 1)
        self.totals_label = QtWidgets.QLabel()
        self.totals_label.setObjectName("quantityTotals")
        self.totals_label.setWordWrap(True)
        layout.addWidget(self.totals_label)
        self.rule_label = QtWidgets.QLabel()
        self.rule_label.setObjectName("quantityRuleHint")
        self.rule_label.setWordWrap(True)
        self.rule_label.setStyleSheet("color: #75502c;")
        layout.addWidget(self.rule_label)
        self.tabs.currentChanged.connect(self._update_category_summary)
        self.selection_label = QtWidgets.QLabel("คลิกแถวเพื่อเลือกวัตถุต้นทาง / Click a row to select its source object")
        self.selection_label.setObjectName("quantitySelection")
        self.selection_label.setWordWrap(True)
        layout.addWidget(self.selection_label)
        row = QtWidgets.QHBoxLayout()
        self.auto_refresh = QtWidgets.QCheckBox("Auto refresh / อัปเดตอัตโนมัติ")
        self.auto_refresh.setObjectName("quantityAutoRefresh")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.toggled.connect(self._auto_changed)
        row.addWidget(self.auto_refresh)
        row.addStretch(1)
        self.refresh_button = QtWidgets.QPushButton("Refresh / อัปเดต")
        self.refresh_button.setObjectName("quantityRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        self.csv_button = QtWidgets.QPushButton("Export CSV")
        self.csv_button.setObjectName("quantityExportCSVButton")
        self.csv_button.clicked.connect(self.export_csv)
        row.addWidget(self.csv_button)
        self.ifc_button = QtWidgets.QPushButton("Export IFC4")
        self.ifc_button.setObjectName("quantityExportIFCButton")
        self.ifc_button.clicked.connect(self.export_ifc)
        row.addWidget(self.ifc_button)
        close_button = QtWidgets.QPushButton("Close / ปิด")
        close_button.setObjectName("quantityCloseButton")
        close_button.clicked.connect(self.close)
        row.addWidget(close_button)
        layout.addLayout(row)
        self.dependency_label = QtWidgets.QLabel()
        self.dependency_label.setObjectName("ifcDependencyStatus")
        self.dependency_label.setWordWrap(True)
        layout.addWidget(self.dependency_label)
        self.export_label = QtWidgets.QLabel("ยังไม่มีไฟล์ส่งออกในหน้าต่างนี้ / No export in this window")
        self.export_label.setObjectName("quantityExportStatus")
        self.export_label.setWordWrap(True)
        self.export_label.setTextInteractionFlags(_enum(QtCore.Qt, "TextSelectableByMouse", "TextInteractionFlag"))
        layout.addWidget(self.export_label)

    def _table(self, name, columns):
        table = QtWidgets.QTableWidget(0, len(columns))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels([label for _, label in columns])
        table.setEditTriggers(_enum(QtWidgets.QAbstractItemView, "NoEditTriggers", "EditTrigger"))
        table.setSelectionBehavior(_enum(QtWidgets.QAbstractItemView, "SelectRows", "SelectionBehavior"))
        table.setSelectionMode(_enum(QtWidgets.QAbstractItemView, "SingleSelection", "SelectionMode"))
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet("QHeaderView::section { background: #14304b; color: white; padding: 6px; border: none; }")
        return table

    def _project(self):
        if not self._document_available or self.document_name not in App.listDocuments():
            raise ValueError("เอกสารต้นทางถูกปิดแล้ว / Source document is closed")
        doc = App.getDocument(self.document_name)
        from bim3117_freecad import services
        project = services.get_project(doc)
        if project is None or str(project.BIM3117Id) != self.project_id:
            raise ValueError("ไม่พบโครงการต้นทาง / Source project no longer exists")
        return project

    def _auto_changed(self, enabled):
        if enabled and self._dirty:
            self.refresh_timer.start()
        elif not enabled:
            self.refresh_timer.stop()

    def _set_export_enabled(self, enabled):
        enabled = bool(enabled and not self._closed and self._document_available and not self._transaction_open)
        self.csv_button.setEnabled(enabled)
        self.ifc_button.setEnabled(enabled and bool(getattr(self, "_ifc_available", False)))

    def mark_stale(self):
        if self._closed or self._refreshing:
            return
        self._dirty = True
        self.status_label.setText("รออัปเดต / Stale — โมเดลเปลี่ยนแล้ว")
        self.status_label.setStyleSheet("color: #a05812; font-weight: 600;")
        self._set_export_enabled(False)
        self._update_export_status(pending=True)
        if self.auto_refresh.isChecked() and not self._exporting:
            self.refresh_timer.start()

    def _fill_table(self, table, rows, columns):
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows))
            for row_index, record in enumerate(rows):
                for column_index, (key, _) in enumerate(columns):
                    value = record.get(key, "")
                    rendered = "{:.4f}".format(value) if isinstance(value, float) else str(value)
                    item = QtWidgets.QTableWidgetItem(rendered)
                    item.setFlags(item.flags() & ~_enum(QtCore.Qt, "ItemIsEditable", "ItemFlag"))
                    element_id = str(record.get("element_id", record.get("object_id", "")))
                    item.setData(_enum(QtCore.Qt, "UserRole", "ItemDataRole"), element_id)
                    item.setToolTip("UUID: {}\n{}".format(element_id, record.get("quantity_rule", record.get("reason", ""))))
                    if isinstance(value, (int, float)):
                        item.setTextAlignment(_enum(QtCore.Qt, "AlignRight", "AlignmentFlag") |
                                              _enum(QtCore.Qt, "AlignVCenter", "AlignmentFlag"))
                    table.setItem(row_index, column_index, item)
            table.resizeColumnsToContents()
            # Long explanatory text remains available by tooltip and scrolling.
            for index in range(table.columnCount()):
                table.setColumnWidth(index, min(340, max(75, table.columnWidth(index))))
        finally:
            table.blockSignals(False)

    def refresh(self):
        if self._closed or self._refreshing or self._exporting:
            return False
        self.refresh_timer.stop()
        self._refreshing = True
        try:
            project = self._project()
            # Empty abort/commit paths may not emit a document transaction
            # signal. Reconcile with the native state, and poll only while an
            # active transaction prevents a safe read.
            self._transaction_open = bool(project.Document.HasPendingTransaction
                                          or App.getActiveTransaction() is not None)
            if self._transaction_open:
                self._dirty = True
                self.status_label.setText("กำลังแก้ไขโมเดล / Waiting for the current transaction")
                self._set_export_enabled(False)
                if self.auto_refresh.isChecked():
                    self.refresh_timer.start(250)
                return False
            snapshot, exchange = _modules()
            source = snapshot.capture(project)
            for table, key, columns, _label in self._quantity_tables:
                self._fill_table(table, source.get(key, []), columns)
            self._fill_table(self.coverage_table, source["coverage"]["items"], self.COVERAGE_COLUMNS)
            self.source_snapshot = source
            self._dirty = False
            self.last_error = ""
            self.status_label.setText("ข้อมูลปัจจุบัน / Current — " + " · ".join(
                "{} {}".format(len(source.get(key, [])), label.split(" / ")[0])
                for _table, key, _columns, label in self._quantity_tables))
            self.status_label.setStyleSheet("color: #245d42; font-weight: 600;")
            revision = source["content_revision"]
            self.revision_label.setText("Model revision: {}  ·  {}".format(revision[:12], source["project"]["label"]))
            self.revision_label.setToolTip(revision)
            self._update_category_summary()
            dependency = exchange.ifc_dependency_info()
            self._ifc_available = bool(dependency["available"])
            self.dependency_label.setText("IFC: " + ("IfcOpenShell " + str(dependency.get("version", ""))
                if self._ifc_available else str(dependency.get("message", "IfcOpenShell is unavailable in this FreeCAD installation"))))
            self.ifc_button.setToolTip(str(dependency.get("message", "")))
            self._set_export_enabled(True)
            self._update_export_status()
            return True
        except Exception as error:
            self.last_error = str(error) or type(error).__name__
            self._dirty = True
            self.status_label.setText("ยังส่งออกไม่ได้ / Cannot refresh: " + self.last_error)
            self.status_label.setStyleSheet("color: #a33a30; font-weight: 600;")
            self._set_export_enabled(False)
            self._update_export_status(pending=True)
            return False
        finally:
            self._refreshing = False

    def _update_category_summary(self, *_args):
        if self.source_snapshot is None:
            return
        index = self.tabs.currentIndex()
        if index >= len(self._quantity_tables):
            self.totals_label.setText("ขอบเขตการส่งออก / Export coverage")
            self.rule_label.setText("ตรวจรายการที่เป็น reference หรือ unsupported ก่อนส่งออก")
            return
        _table, key, _columns, label = self._quantity_tables[index]
        rows = self.source_snapshot.get(key, [])
        total = lambda name: sum(row.get(name, 0.0) for row in rows)
        if key == "wall_rows":
            text = "ผลรวมรายผนัง / Per-wall totals: net area {:.4f} m² · net volume {:.4f} m³".format(
                total("net_side_area_m2"), total("net_volume_m3"))
            rule = "พื้นที่ผนังคิดด้านเดียว • หักช่อง Door/Window • ไม่หักรอยต่อผนัง"
        elif key in ("door_rows", "window_rows"):
            text = "{}: {} · opening area {:.4f} m² · frame volume {:.4f} m³".format(
                label.split(" / ")[0], len(rows), total("opening_area_m2"), total("frame_volume_m3"))
            rule = "กว้าง/สูงคือช่องตัดรวมกรอบ • กรอบทั่วไป {}ด้าน ไม่มีบาน".format(4 if key == "window_rows" else 3)
        elif key == "slab_rows":
            text = "Slabs: {} · plan area {:.4f} m² · net volume {:.4f} m³".format(
                len(rows), total("net_area_m2"), total("net_volume_m3"))
            rule = "พื้นที่แปลนของขอบเขต XY • ความหนาลงจากผิวบน Level + Offset • ไม่รวมรอยต่อพื้นซ้อนกัน"
        else:
            text = "{}: {} · gross {:.4f} m³ · slab cuts {:.4f} m³ · net {:.4f} m³".format(
                label.split(" / ")[0], len(rows), total("gross_volume_m3"),
                total("join_deduction_m3"), total("net_volume_m3"))
            rule = "หักเฉพาะพื้นใน JoinSlabs ของแต่ละชิ้น • ไม่หักรอยต่อชนิดอื่นหรือคำนวณโครงสร้าง"
        self.totals_label.setText(text)
        self.rule_label.setText(rule)

    def select_source(self, table, row):
        if self._closed or row < 0 or table.item(row, 0) is None:
            return
        identifier = table.item(row, 0).data(_enum(QtCore.Qt, "UserRole", "ItemDataRole"))
        try:
            project = self._project()
            obj = next((item for item in project.Document.Objects
                        if str(getattr(item, "BIM3117Id", "")) == identifier), None)
            if obj is None:
                raise ValueError("วัตถุถูกลบหรือเปลี่ยนแล้ว กรุณา Refresh / Source object no longer exists")
            App.setActiveDocument(self.document_name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self.document_name, obj.Name)
            self.selection_label.setText("{} · UUID {}".format(obj.Label, identifier))
        except Exception as error:
            self.selection_label.setText(str(error))

    def _update_export_status(self, pending=False):
        if not self.latest_exports:
            return
        revision = self.source_snapshot["content_revision"] if self.source_snapshot is not None else None
        lines = []
        for format_name, result in sorted(self.latest_exports.items()):
            if pending:
                state = "รอตรวจเทียบ / Check pending"
            elif result["content_revision"] == revision:
                state = "ตรงกับโมเดล / Current snapshot"
            else:
                state = "ล้าสมัย — ส่งออกใหม่ / Stale snapshot"
            lines.append("{}: {} · {} · {}".format(format_name.upper(), state,
                result["content_revision"][:12], result["files"][0]))
        self.export_label.setText("\n".join(lines))

    def _choose_path(self, format_name):
        source_file = str(self.source_snapshot["source_document"].get("file", ""))
        folder = str(Path(source_file).parent) if source_file else str(Path.home())
        extension = ".csv" if format_name == "csv" else ".ifc"
        default = "3117_{}_{}{}".format("quantities" if format_name == "csv" else "model",
                                        self.source_snapshot["content_revision"][:8], extension)
        dialog = QtWidgets.QFileDialog(self, "3117 — Export " + format_name.upper(), folder)
        dialog.setObjectName("BIM3117ExportFileDialog")
        dialog.setAcceptMode(_enum(QtWidgets.QFileDialog, "AcceptSave", "AcceptMode"))
        dialog.setFileMode(_enum(QtWidgets.QFileDialog, "AnyFile", "FileMode"))
        # One explicit confirmation below covers the main file and every sidecar.
        dialog.setOption(_enum(QtWidgets.QFileDialog, "DontConfirmOverwrite", "Option"), True)
        dialog.setNameFilter("CSV (*.csv)" if format_name == "csv" else "IFC4 (*.ifc)")
        dialog.setDefaultSuffix(extension[1:])
        dialog.selectFile(default)
        if not run_dialog(dialog):
            return None
        selected = dialog.selectedFiles()
        return selected[0] if selected else None

    def _confirm_overwrite(self, paths):
        existing = [str(path) for path in paths if Path(path).exists()]
        if not existing:
            return True
        question = QtWidgets.QMessageBox(self)
        question.setObjectName("BIM3117OverwriteDialog")
        question.setWindowTitle("3117 — Replace export files / แทนที่ไฟล์")
        question.setIcon(_enum(QtWidgets.QMessageBox, "Question", "Icon"))
        question.setText("แทนที่ไฟล์ส่งออกที่มีอยู่ต่อไปนี้หรือไม่?\n\n" + "\n".join(existing))
        question.setStandardButtons(_enum(QtWidgets.QMessageBox, "Yes", "StandardButton") |
                                    _enum(QtWidgets.QMessageBox, "No", "StandardButton"))
        question.setDefaultButton(_enum(QtWidgets.QMessageBox, "No", "StandardButton"))
        runner = getattr(question, "exec", None) or question.exec_
        return runner() == _enum(QtWidgets.QMessageBox, "Yes", "StandardButton")

    def _error(self, title, error):
        self.last_error = str(error) or type(error).__name__
        App.Console.PrintError("3117 {}: {}\n".format(title, self.last_error))
        QtWidgets.QMessageBox.warning(self, "3117 — " + title, self.last_error)

    def _export(self, format_name):
        if not self.refresh():
            if self.last_error:
                self._error("Export " + format_name.upper(), self.last_error)
            return None
        if format_name == "ifc" and not self._ifc_available:
            self._error("Export IFC4", self.dependency_label.text())
            return None
        source = self.source_snapshot
        preview = CoverageDialog(source, format_name, self)
        if not run_dialog(preview):
            return None
        try:
            path = self._choose_path(format_name)
            if not path:
                return None
            _, exchange = _modules()
            paths = exchange.output_paths(path, format=format_name, source=source)
            had_existing = any(Path(item).exists() for item in paths)
            if not self._confirm_overwrite(paths):
                return None
        except Exception as error:
            self._error("Export " + format_name.upper(), error)
            return None
        self._exporting = True
        self._set_export_enabled(False)
        try:
            operation = exchange.export_csv if format_name == "csv" else exchange.export_ifc
            result = operation(self._project(), path, overwrite=had_existing,
                               expected_revision=source["content_revision"])
            self.latest_exports[format_name] = result
            self._update_export_status()
            App.Console.PrintMessage("3117 {} exported: {}\n".format(format_name.upper(), result["files"][0]))
            return result
        except Exception as error:
            self._error("Export " + format_name.upper(), error)
            return None
        finally:
            self._exporting = False
            self.refresh()

    def export_csv(self):
        return self._export("csv")

    def export_ifc(self):
        return self._export("ifc")

    def _detach(self, result=None):
        if not self._closed:
            self._closed = True
            self.refresh_timer.stop()
            App.removeDocumentObserver(self.observer)
            if _PANELS.get(self.document_name) is self:
                del _PANELS[self.document_name]
            # QDialog.reject() (Escape) only hides by default. Dispose the
            # table widgets as well as their observer when this session ends.
            self.deleteLater()

    def closeEvent(self, event):
        self._detach()
        event.accept()
        super().closeEvent(event)


def show_quantities(project):
    """Reuse one observer and dialog for each live native document."""
    name = project.Document.Name
    panel = _PANELS.get(name)
    if panel is None or panel._closed or not panel._document_available:
        if panel is not None and not panel._closed:
            panel.close()
        panel = QuantityDialog(project)
        _PANELS[name] = panel
        main = Gui.getMainWindow()
        panel.move(main.x() + max(0, (main.width() - panel.width()) // 2),
                   main.y() + max(0, main.height() - panel.height() - 65))
    else:
        panel.refresh()
    panel.show()
    panel.raise_()
    panel.activateWindow()
    return panel


def panel_for_document(document_name):
    """Return an existing presentation panel without creating/changing a model."""
    return _PANELS.get(document_name)
