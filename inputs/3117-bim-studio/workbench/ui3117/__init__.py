# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight resource paths for the native FreeCAD UI."""

from pathlib import Path

from bim3117_freecad import __version__


def resource_path(name):
    """Return a deployed resource path without relying on InitGui.__file__."""
    return str(Path(__file__).resolve().parent / "icons" / name)
