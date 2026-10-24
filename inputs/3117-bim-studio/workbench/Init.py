# SPDX-License-Identifier: GPL-3.0-or-later
"""3117 BIM Studio: headless bootstrap without document or GUI mutations.

Native model services are imported only by commands or by FreeCAD when it
restores a saved FeaturePython object. Importing this module does not create
a project, load a second Qt runtime, or change user preferences.
"""
