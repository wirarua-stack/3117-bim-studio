# SPDX-License-Identifier: GPL-3.0-or-later
"""Four unjoined wall reference axes, 6 x 4 metres, height 3 metres."""
from .model import BuildingDocument


def create_demo():
    document = BuildingDocument("3117 BIM reference - 6 x 4 m")
    with document.transaction("Create reference room"):
        ground = document.add_level("L00", 0.0)
        upper = document.add_level("L01", 3.0)
        typ = document.add_wall_type("W200", 0.2)
        corners = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
        walls = [document.add_wall(f"Wall {i + 1}", typ, ground, start,
                                   corners[(i + 1) % 4], top_level_id=upper)
                 for i, start in enumerate(corners)]
        document.add_door("D900", walls[0], offset=1.0, width=0.9, height=2.1)
    return document
