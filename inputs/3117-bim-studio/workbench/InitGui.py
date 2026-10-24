# SPDX-License-Identifier: GPL-3.0-or-later
"""FreeCAD's legacy loader executes this file with separate locals/globals.

Keep definitions in a regular imported module so their global names resolve.
"""
import FreeCADGui
from ui3117.workbench import BIM3117Workbench

FreeCADGui.addWorkbench(BIM3117Workbench())
