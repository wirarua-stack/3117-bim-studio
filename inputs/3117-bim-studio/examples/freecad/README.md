# Native FreeCAD examples

## Architecture — v0.2.0

`Architecture_Workbench.FCStd` was created with the installed 3117 command dialogs in FreeCAD 1.1.4 on Linux. `Architecture_Workbench.png` is an actual captured FreeCAD window.

The final example contains Project, two Levels (0 and 3300 mm), two labelled grids, one shared Wall Type (250 mm), two walls (6000 and 4000 mm long), two derived WallBody solids and two hosted doors. The openings are 900 × 2100 and 800 × 2100 mm; these are overall cut sizes including the generic display frame. Final individual net wall volumes are 4.4775 and 2.8800 m³. The two walls are unjoined.

Install v0.2.0, restart FreeCAD, then open the file. Select a wall solid and use **Edit Selected** to change its axis or levels. Select the shared Wall Type and edit Thickness to update both instances. Edit a Door to change its opening or host. Use **3117 Delete Selected** to delete a Door and heal its wall, then native Undo to restore both. Selecting the authored Wall in the tree and pressing Space hides/shows its solid and hosted doors.

See [Wall/Door guide](../../docs/WALL_DOOR_WORKBENCH.md) and [verification record](../../docs/VERIFICATION.md) for units, exact scope and evidence.

## Foundation — preserved v0.1.0 fixture

`Foundation_Workbench.FCStd` and `Foundation_Workbench.png` preserve the earlier Foundation sample: one Project, three Levels (L00 0 mm, L01 3300 mm, L02 6000 mm) and seven labelled grid axes, including one linked to L01. Its original file and UUIDs are unchanged so the v0.2 suite can test backward compatibility against a genuine older document.

Open it with the installed workbench, select L01 and change its elevation with **Edit Selected**. The linked grid follows; native Undo/Redo returns both the parameters and geometry.

Reference JSON/CSV/IFC fixtures in the other example directories are separate from these native documents. Windows acceptance remains pending; see [Windows acceptance](../../docs/WINDOWS_ACCEPTANCE.md).
