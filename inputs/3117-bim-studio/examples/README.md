# Example inventory

Native production-workbench examples are in `freecad/` (Foundation and Wall/Door), `exchange/` (Quantity/IFC), `building/` (two-storey Building Authoring) and `drawings/` (four views, two A3 sheets and vector SVG/PDF). Their editable authority is the `.FCStd` file. Each folder documents its own fixture, scope and evidence.

## Independent reference fixture

`generated/room.reference.json` is a versioned headless test fixture, **not** the
production authoring file. The FreeCAD workbench uses `.FCStd`
as its editable authority. `generated/room.ifc` is an IFC4 exchange snapshot.

The model contains two levels at 0 and 3 m, one 200 mm wall type, four straight
walls on 6 x 4 m reference axes, and one hosted 900 x 2100 mm door. The door is
represented as a simple leaf and one actual `IfcOpeningElement` with void/fill
relationships. Wall direction follows local +X; material lies on local +Y.

`wall_schedule.csv` is a UTF-8 CSV with a BOM for spreadsheet compatibility.
The individual wall lengths total 20 m. Their gross volume is 12.000 m³, and
the single door subtracts 0.9 × 2.1 × 0.2 = 0.378 m³, giving 11.622 m³ net.
Walls are **not joined at corners**. The schedule sums separate wall solids;
it does not remove junction overlap and is not a certified BOQ.

From the repository root, after installing `.[ifc,test]` in a virtual environment:

```bash
python -m bim3117 demo --output examples/generated --ifc
python -m unittest discover -s tests -v
```

Running the demo creates fresh element UUIDs. Saving, loading and re-exporting
the **same** reference document preserves element identities and IFC GlobalIds.
The undo stack is intentionally an in-session facility and is not serialized.

Full IFC tests require both extras. Without IfcOpenShell, all four IFC tests are
reported as skipped; without pytest, the EXPRESS-rule test is reported as skipped.
IfcOpenShell's rule executor currently imports pytest internally.
