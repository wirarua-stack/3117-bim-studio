# SPDX-License-Identifier: GPL-3.0-or-later
"""Use the Qt binding supplied by the running FreeCAD process."""

from PySide import QtCore, QtGui

try:
    from PySide import QtWidgets
except ImportError:
    # Compatibility with the older PySide shim that exposed widgets in QtGui.
    QtWidgets = QtGui


def enum_value(owner, name, group):
    value = getattr(owner, name, None)
    if value is not None:
        return value
    return getattr(getattr(owner, group), name)


def run_dialog(dialog):
    runner = getattr(dialog, "exec", None)
    if runner is None:
        runner = dialog.exec_
    return runner() == enum_value(QtWidgets.QDialog, "Accepted", "DialogCode")
