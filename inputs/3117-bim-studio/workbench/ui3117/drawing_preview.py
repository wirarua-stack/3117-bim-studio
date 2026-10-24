# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only SVG sheet preview bound to one native FreeCAD document.

The renderer and exporter own drawing geometry and publication. This window
stores only disposable presentation state, never an editable model or cache.
"""

from pathlib import Path
import weakref

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtSvg

from .qt import QtCore, QtGui, QtWidgets, enum_value, run_dialog


_PANELS = {}


def _modules():
    from bim3117_freecad import drawings, drawing_render, drawing_export
    return drawings, drawing_render, drawing_export


def _name(document):
    try:
        return document.Name
    except Exception:
        return None


class _DrawingObserver:
    def __init__(self, panel):
        self.panel = weakref.ref(panel)

    def _target(self, doc):
        panel = self.panel()
        return panel if panel is not None and not panel._closed and _name(doc) == panel.document_name else None

    def _change(self, doc):
        panel = self._target(doc)
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


class SheetCanvas(QtWidgets.QWidget):
    """Host Qt SVG rendering with view-only pan/zoom and a true paper aspect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drawingPreviewCanvas")
        self.setMinimumSize(480, 330)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.renderer = QtSvg.QSvgRenderer(self)
        self.svg_text = ""
        self.zoom = 1.0
        self.pan = QtCore.QPointF(0, 0)
        self._drag_origin = None
        self.setToolTip("ล้อเมาส์: ขยาย/ย่อ · ลาก: เลื่อนแผ่นแบบ · Fit: พอดีหน้าต่าง")

    def set_svg(self, text):
        if not self.renderer.load(QtCore.QByteArray(str(text).encode("utf-8"))) or not self.renderer.isValid():
            raise ValueError("รูปแผ่นแบบ SVG ไม่สมบูรณ์ / Invalid sheet SVG")
        self.svg_text = str(text)
        self.update()

    def clear(self):
        self.svg_text = ""
        self.update()

    def fit(self):
        self.zoom = 1.0
        self.pan = QtCore.QPointF(0, 0)
        self.update()

    def zoom_by(self, factor):
        self.zoom = max(.3, min(6.0, self.zoom * factor))
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#e3e8ec"))
        if not self.svg_text:
            painter.setPen(QtGui.QColor("#526473"))
            painter.drawText(self.rect(), enum_value(QtCore.Qt, "AlignCenter", "AlignmentFlag"),
                             "เลือกแผ่นแบบแล้วกด Update / Select a sheet and update")
            return
        box = self.renderer.viewBoxF()
        if box.width() <= 0 or box.height() <= 0:
            return
        factor = min(max(1, self.width() - 32) / box.width(), max(1, self.height() - 32) / box.height()) * self.zoom
        width, height = box.width() * factor, box.height() * factor
        target = QtCore.QRectF((self.width() - width) / 2 + self.pan.x(),
                              (self.height() - height) / 2 + self.pan.y(), width, height)
        painter.setRenderHint(enum_value(QtGui.QPainter, "Antialiasing", "RenderHint"), True)
        painter.fillRect(target, QtGui.QColor("white"))
        self.renderer.render(painter, target)
        painter.setPen(QtGui.QPen(QtGui.QColor("#b6c1ca"), 1))
        painter.drawRect(target)

    def wheelEvent(self, event):
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == enum_value(QtCore.Qt, "LeftButton", "MouseButton"):
            self._drag_origin = event.position() if hasattr(event, "position") else event.localPos()
            self.setCursor(enum_value(QtCore.Qt, "ClosedHandCursor", "CursorShape"))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            position = event.position() if hasattr(event, "position") else event.localPos()
            self.pan += position - self._drag_origin
            self._drag_origin = position
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_origin is not None:
            self._drag_origin = None
            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class DrawingPreviewDialog(QtWidgets.QDialog):
    def __init__(self, sheet, parent=None):
        super().__init__(parent or Gui.getMainWindow())
        self.setObjectName("BIM3117DrawingPreview")
        self.setWindowTitle("3117 — Drawings & Sheets / แบบและแผ่นแบบ")
        self.setModal(False)
        self.resize(1080, 800)
        self.document_name = sheet.Document.Name
        self.project_id = str(sheet.Project.BIM3117Id)
        self.sheet_id = str(sheet.BIM3117Id)
        self.source_snapshot = None
        self.rendered = None
        self.latest_exports = {}
        self.last_error = ""
        self._document_available = True
        self._transaction_open = False
        self._refreshing = self._exporting = self._closed = False
        self._dirty = True
        self._build_ui()
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(300)
        self.refresh_timer.timeout.connect(self.refresh)
        self.observer = _DrawingObserver(self)
        App.addDocumentObserver(self.observer)
        self.finished.connect(self._detach)
        self.refresh()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("DRAWINGS  /  แบบจากโมเดล")
        title.setStyleSheet("font-weight: 700; font-size: 17px; color: #14304b; padding: 4px 0;")
        header.addWidget(title)
        header.addStretch(1)
        self.sheet_combo = QtWidgets.QComboBox()
        self.sheet_combo.setObjectName("drawingSheetCombo")
        self.sheet_combo.setMinimumWidth(320)
        self.sheet_combo.currentIndexChanged.connect(self._sheet_changed)
        header.addWidget(self.sheet_combo)
        layout.addLayout(header)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setObjectName("drawingStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.revision_label = QtWidgets.QLabel()
        self.revision_label.setObjectName("drawingRevision")
        self.revision_label.setWordWrap(True)
        self.revision_label.setTextInteractionFlags(enum_value(QtCore.Qt, "TextSelectableByMouse", "TextInteractionFlag"))
        layout.addWidget(self.revision_label)
        self.canvas = SheetCanvas()
        layout.addWidget(self.canvas, 1)
        self.view_summary = QtWidgets.QLabel()
        self.view_summary.setObjectName("drawingViewSummary")
        self.view_summary.setWordWrap(True)
        layout.addWidget(self.view_summary)
        buttons = QtWidgets.QHBoxLayout()
        self.auto_refresh = QtWidgets.QCheckBox("Auto update / อัปเดตอัตโนมัติ")
        self.auto_refresh.setObjectName("drawingAutoRefresh")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.toggled.connect(self._auto_changed)
        buttons.addWidget(self.auto_refresh)
        for text, name, operation in (("−", "drawingZoomOutButton", lambda: self.canvas.zoom_by(1 / 1.2)),
                                       ("Fit / พอดี", "drawingFitButton", self.canvas.fit),
                                       ("+", "drawingZoomInButton", lambda: self.canvas.zoom_by(1.2))):
            button = QtWidgets.QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(operation)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.refresh_button = QtWidgets.QPushButton("Update Drawing / อัปเดตแบบ")
        self.refresh_button.setObjectName("drawingRefreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self.refresh_button)
        self.svg_button = QtWidgets.QPushButton("Export SVG")
        self.svg_button.setObjectName("drawingExportSVGButton")
        self.svg_button.clicked.connect(lambda: self.export("svg"))
        buttons.addWidget(self.svg_button)
        self.pdf_button = QtWidgets.QPushButton("Export PDF")
        self.pdf_button.setObjectName("drawingExportPDFButton")
        self.pdf_button.clicked.connect(lambda: self.export("pdf"))
        buttons.addWidget(self.pdf_button)
        close = QtWidgets.QPushButton("Close / ปิด")
        close.setObjectName("drawingCloseButton")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.export_label = QtWidgets.QLabel("ยังไม่มีไฟล์ส่งออกในหน้าต่างนี้ / No export in this window")
        self.export_label.setObjectName("drawingExportStatus")
        self.export_label.setWordWrap(True)
        self.export_label.setTextInteractionFlags(enum_value(QtCore.Qt, "TextSelectableByMouse", "TextInteractionFlag"))
        layout.addWidget(self.export_label)

    def _project(self):
        if not self._document_available or self.document_name not in App.listDocuments():
            raise ValueError("เอกสารต้นทางถูกปิดแล้ว / Source document is closed")
        from bim3117_freecad import services
        project = services.get_project(App.getDocument(self.document_name))
        if project is None or str(project.BIM3117Id) != self.project_id:
            raise ValueError("ไม่พบโครงการต้นทาง / Source project no longer exists")
        return project

    def _sheet(self):
        project = self._project()
        drawings, _, _ = _modules()
        sheet = next((s for s in drawings.list_sheets(project) if str(s.BIM3117Id) == self.sheet_id), None)
        if sheet is None:
            raise ValueError("ไม่พบแผ่นแบบต้นทาง / Source sheet no longer exists")
        return sheet

    def _sync_sheets(self):
        drawings, _, _ = _modules()
        sheets = drawings.list_sheets(self._project())
        if not any(str(s.BIM3117Id) == self.sheet_id for s in sheets):
            self.sheet_id = str(sheets[0].BIM3117Id) if sheets else ""
        self.sheet_combo.blockSignals(True)
        try:
            self.sheet_combo.clear()
            for sheet in sheets:
                self.sheet_combo.addItem("{} · {}".format(sheet.Number, sheet.Label), str(sheet.BIM3117Id))
            index = next((i for i, s in enumerate(sheets) if str(s.BIM3117Id) == self.sheet_id), -1)
            self.sheet_combo.setCurrentIndex(index)
        finally:
            self.sheet_combo.blockSignals(False)

    def select_sheet(self, sheet):
        if sheet.Document.Name != self.document_name or str(sheet.Project.BIM3117Id) != self.project_id:
            raise ValueError("เลือกแผ่นแบบในเอกสารเดียวกัน / Select a sheet in this document")
        self.sheet_id = str(sheet.BIM3117Id)
        self.canvas.fit()
        self.mark_stale()
        self.refresh()

    def _sheet_changed(self, index):
        if index < 0:
            return
        self.sheet_id = str(self.sheet_combo.itemData(index))
        self.canvas.fit()
        self.mark_stale()
        self.refresh()

    def _auto_changed(self, enabled):
        if enabled and self._dirty:
            self.refresh_timer.start()
        elif not enabled:
            self.refresh_timer.stop()

    def _set_export_enabled(self, enabled):
        enabled = bool(enabled and not self._closed and self._document_available and not self._transaction_open)
        self.pdf_button.setEnabled(enabled)
        self.svg_button.setEnabled(enabled)

    def mark_stale(self):
        if self._closed or self._refreshing:
            return
        self._dirty = True
        self.status_label.setText("รออัปเดต / Stale — โมเดลหรือข้อกำหนดแบบเปลี่ยนแล้ว")
        self.status_label.setStyleSheet("color: #a05812; font-weight: 600;")
        self._set_export_enabled(False)
        self._update_export_status(pending=True)
        if self.auto_refresh.isChecked() and not self._exporting:
            self.refresh_timer.start()

    def refresh(self):
        if self._closed or self._refreshing or self._exporting:
            return False
        self.refresh_timer.stop()
        self._refreshing = True
        try:
            project = self._project()
            self._transaction_open = bool(project.Document.HasPendingTransaction or App.getActiveTransaction() is not None)
            if self._transaction_open:
                self._dirty = True
                self.status_label.setText("กำลังแก้ไขโมเดล / Waiting for the current transaction")
                self._set_export_enabled(False)
                if self.auto_refresh.isChecked():
                    self.refresh_timer.start(250)
                return False
            self._sync_sheets()
            sheet = self._sheet()
            drawings, renderer, _ = _modules()
            source = drawings.capture_sheet(sheet)
            rendered = renderer.render_sheet(source)
            self.canvas.set_svg(rendered["svg"])
            self.source_snapshot = source
            self.rendered = rendered
            self._dirty = False
            self.last_error = ""
            self.status_label.setText("แบบปัจจุบัน / Current — {} · {} · A3 landscape".format(sheet.Number, sheet.Label))
            self.status_label.setStyleSheet("color: #245d42; font-weight: 600;")
            self.revision_label.setText("Model: {}  ·  Drawing: {}".format(
                source["model_revision"][:12], source["drawing_revision"][:12]))
            self.revision_label.setToolTip("Model: {}\nDrawing: {}".format(source["model_revision"], source["drawing_revision"]))
            self.view_summary.setText("  |  ".join("{} · {} · 1:{:g}".format(v.Label, v.ViewType, float(v.ScaleDenominator))
                                                   for v in sheet.Views))
            self._set_export_enabled(True)
            self._update_export_status()
            return True
        except Exception as error:
            self.last_error = str(error) or type(error).__name__
            self._dirty = True
            self.status_label.setText("ยังสร้างแบบไม่ได้ / Cannot update: " + self.last_error)
            self.status_label.setStyleSheet("color: #a33a30; font-weight: 600;")
            self._set_export_enabled(False)
            self._update_export_status(pending=True)
            return False
        finally:
            self._refreshing = False

    def _update_export_status(self, pending=False):
        if not self.latest_exports:
            return
        source = self.source_snapshot
        lines = []
        for key, result in sorted(self.latest_exports.items()):
            if key[0] != self.sheet_id:
                continue
            if pending:
                state = "รอตรวจเทียบ / Check pending"
            elif source and (result["model_revision"], result["drawing_revision"]) == (
                    source["model_revision"], source["drawing_revision"]):
                state = "ตรงกับแบบปัจจุบัน / Current snapshot"
            else:
                state = "ล้าสมัย — ส่งออกใหม่ / Stale snapshot"
            lines.append("{}: {} · {}".format(key[1].upper(), state, result["files"][0]))
        self.export_label.setText("\n".join(lines) or "ยังไม่มีไฟล์ส่งออกสำหรับแผ่นนี้ / No export for this sheet")

    def _choose_path(self, format_name):
        sheet = self._sheet()
        source_file = str(sheet.Document.FileName)
        folder = str(Path(source_file).parent) if source_file else str(Path.home())
        dialog = QtWidgets.QFileDialog(self, "3117 — Export Drawing " + format_name.upper(), folder)
        dialog.setObjectName("BIM3117DrawingExportFileDialog")
        dialog.setAcceptMode(enum_value(QtWidgets.QFileDialog, "AcceptSave", "AcceptMode"))
        dialog.setFileMode(enum_value(QtWidgets.QFileDialog, "AnyFile", "FileMode"))
        dialog.setOption(enum_value(QtWidgets.QFileDialog, "DontConfirmOverwrite", "Option"), True)
        dialog.setNameFilter("{} (*.{})".format(format_name.upper(), format_name))
        dialog.setDefaultSuffix(format_name)
        # Sheet numbers are labels and can contain Windows path punctuation.
        # Keep the suggested basename local; the user still chooses the path.
        number = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(sheet.Number)).strip("_") or "Sheet"
        dialog.selectFile("3117_{}_{}.{}".format(number, self.source_snapshot["drawing_revision"][:8], format_name))
        if not run_dialog(dialog):
            return None
        files = dialog.selectedFiles()
        return files[0] if files else None

    def _confirm_overwrite(self, paths):
        existing = [str(p) for p in paths if Path(p).exists()]
        if not existing:
            return True
        dialog = QtWidgets.QMessageBox(self)
        dialog.setObjectName("BIM3117DrawingOverwriteDialog")
        dialog.setWindowTitle("3117 — Replace drawing files / แทนที่ไฟล์แบบ")
        dialog.setText("แทนที่ไฟล์ส่งออกที่มีอยู่ต่อไปนี้หรือไม่?\n\n" + "\n".join(existing))
        dialog.setStandardButtons(enum_value(QtWidgets.QMessageBox, "Yes", "StandardButton") |
                                  enum_value(QtWidgets.QMessageBox, "No", "StandardButton"))
        dialog.setDefaultButton(enum_value(QtWidgets.QMessageBox, "No", "StandardButton"))
        runner = getattr(dialog, "exec", None) or dialog.exec_
        return runner() == enum_value(QtWidgets.QMessageBox, "Yes", "StandardButton")

    def _error(self, title, error):
        self.last_error = str(error) or type(error).__name__
        App.Console.PrintError("3117 {}: {}\n".format(title, self.last_error))
        QtWidgets.QMessageBox.warning(self, "3117 — " + title, self.last_error)

    def export(self, format_name):
        if format_name not in ("svg", "pdf"):
            raise ValueError("Supported drawing exports: SVG, PDF")
        if not self.refresh():
            if self.last_error:
                self._error("Export Drawing " + format_name.upper(), self.last_error)
            return None
        source = self.source_snapshot
        try:
            path = self._choose_path(format_name)
            if not path:
                return None
            _, _, exporter = _modules()
            paths = exporter.output_paths(path, format=format_name)
            overwrite = any(Path(p).exists() for p in paths)
            if not self._confirm_overwrite(paths):
                return None
        except Exception as error:
            self._error("Export Drawing " + format_name.upper(), error)
            return None
        self._exporting = True
        self._set_export_enabled(False)
        try:
            sheet = self._sheet()
            result = exporter.export_sheet(sheet, path, format=format_name, overwrite=overwrite,
                expected_model_revision=source["model_revision"], expected_drawing_revision=source["drawing_revision"])
            self.latest_exports[(self.sheet_id, format_name)] = result
            self._update_export_status()
            App.Console.PrintMessage("3117 Drawing {} exported: {}\n".format(format_name.upper(), result["files"][0]))
            return result
        except Exception as error:
            self._error("Export Drawing " + format_name.upper(), error)
            return None
        finally:
            self._exporting = False
            self.refresh()

    def _detach(self, result=None):
        if not self._closed:
            self._closed = True
            self.refresh_timer.stop()
            App.removeDocumentObserver(self.observer)
            if _PANELS.get(self.document_name) is self:
                del _PANELS[self.document_name]
            self.deleteLater()

    def closeEvent(self, event):
        self._detach()
        event.accept()
        super().closeEvent(event)


def show_sheet_preview(sheet):
    name = sheet.Document.Name
    panel = _PANELS.get(name)
    if panel is None or panel._closed or not panel._document_available:
        if panel is not None and not panel._closed:
            panel.close()
        panel = DrawingPreviewDialog(sheet)
        _PANELS[name] = panel
        main = Gui.getMainWindow()
        panel.move(main.x() + max(0, (main.width() - panel.width()) // 2),
                   main.y() + max(0, (main.height() - panel.height()) // 2))
    else:
        panel.select_sheet(sheet)
    panel.show()
    panel.raise_()
    panel.activateWindow()
    return panel


def panel_for_document(document_name):
    return _PANELS.get(document_name)
