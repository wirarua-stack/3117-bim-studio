# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, document-bound panel shell using only FreeCAD's Qt runtime."""

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets, enum_value
from .exchange_dialog import _DocumentObserver


class _ModelPanelObserver(_DocumentObserver):
    def slotRecomputedDocument(self, document):
        # Snapshot readers recompute an already clean document. Treating that
        # notification as an edit makes two modeless readers refresh each other
        # indefinitely. Real object changes, transactions and Undo/Redo already
        # mark the panel dirty; only finish an existing invalidation here.
        panel = self._target(document)
        if panel is not None and panel._dirty:
            panel.mark_stale()


def readonly_table(name, columns):
    table = QtWidgets.QTableWidget(0, len(columns))
    table.setObjectName(name)
    table.setHorizontalHeaderLabels(columns)
    table.setEditTriggers(enum_value(QtWidgets.QAbstractItemView, "NoEditTriggers", "EditTrigger"))
    table.setSelectionBehavior(enum_value(QtWidgets.QAbstractItemView, "SelectRows", "SelectionBehavior"))
    table.setSelectionMode(enum_value(QtWidgets.QAbstractItemView, "SingleSelection", "SelectionMode"))
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    table.horizontalHeader().setStretchLastSection(True)
    return table


def fill_table(table, rows):
    table.blockSignals(True)
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = QtWidgets.QTableWidgetItem(str(value))
            table.setItem(row, column, item)
    table.resizeColumnsToContents()
    table.blockSignals(False)


class ModelPanel(QtWidgets.QDialog):
    def __init__(self, project, object_name, title, panels):
        super().__init__(Gui.getMainWindow())
        self.setObjectName(object_name)
        self.setWindowTitle(title)
        self.setModal(False)
        self.document_name = project.Document.Name
        self.project_id = str(project.BIM3117Id)
        self._panels = panels
        self._closed = False
        self._document_available = True
        self._transaction_open = False
        self._refreshing = False
        self._editing = False
        self._dirty = True
        self.last_error = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.refresh)
        self._observer = _ModelPanelObserver(self)
        App.addDocumentObserver(self._observer)
        self.finished.connect(self._detach)

    def _project(self):
        from bim3117_freecad import services
        if not self._document_available or self._closed:
            raise ValueError("Document closed")
        doc = App.getDocument(self.document_name)
        project = services.get_project(doc)
        if project is None or str(project.BIM3117Id) != self.project_id:
            raise ValueError("โครงการเดิมไม่อยู่ในเอกสารแล้ว / Project no longer exists")
        return project

    def mark_stale(self):
        if self._closed or self._refreshing:
            return
        self._dirty = True
        self._set_export_enabled(False)
        self.status_label.setText("ข้อมูลเปลี่ยนแล้ว / Refresh pending…")
        if not self._transaction_open and not self._editing:
            self._timer.start()

    def _set_export_enabled(self, enabled):
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(bool(enabled and not self._transaction_open and self._document_available))

    def _fail(self, action, error):
        from .commands import _report_error
        self.last_error = str(error)
        self.status_label.setText(str(error))
        _report_error(action, error)

    def _detach(self, *_args):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        App.removeDocumentObserver(self._observer)
        if self._panels.get(self.document_name) is self:
            self._panels.pop(self.document_name, None)
        self.deleteLater()

    def closeEvent(self, event):
        self._detach()
        event.accept()
        super().closeEvent(event)


def show_panel(panel, panels):
    panels[panel.document_name] = panel
    panel.show()
    panel.raise_()
    panel.activateWindow()
    return panel
