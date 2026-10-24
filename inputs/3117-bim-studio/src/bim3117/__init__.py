# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless reference contracts; the production authoring host is FreeCAD."""
from .model import BuildingDocument, Door, Level, ModelError, Wall, WallType

__version__ = "0.0.1"
__all__ = ["BuildingDocument", "Door", "Level", "ModelError", "Wall", "WallType"]
