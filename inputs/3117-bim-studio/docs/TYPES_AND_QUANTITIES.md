# v0.5.0 — Types and Quantities

3117 BIM Studio เก็บ Type, Material และ Schedule เป็น native objects ในไฟล์ `.FCStd` เดียวกับอาคาร การเปลี่ยน Type สร้างรูปทรงและปริมาณใหม่จากพารามิเตอร์เดียวกัน ตารางเป็นมุมมองของโมเดลที่บันทึกกฎกรอง/รวมกลุ่มได้ การแก้แถวในตารางกลับไปแก้ชิ้นส่วนต้นทางผ่าน document transaction

รุ่นนี้เป็น development candidate บน FreeCAD 1.1.4 ผลที่รันจริงและข้อจำกัดแพลตฟอร์มอยู่ใน [VERIFICATION.md](VERIFICATION.md) และ [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md) ไม่มีการรับรองความเทียบเท่า Revit

**ข้อขัดข้องที่ยังไม่ปิด:** FreeCAD 1.1.4 Linux มี native crash ในลำดับสร้าง–ลบ–Undo สองครั้ง–แก้ไขใหม่–Undo/Redo แม้ไม่ติดตั้ง Workbench เกณฑ์ history branching จึงยังไม่ผ่าน ควรทดลองกับสำเนาที่บันทึกไว้ และยังไม่ใช้ candidate นี้เป็นฐานงานจริง ดูขั้นตอนทำซ้ำและขอบเขตหลักฐานใน [HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md)

## 1. เริ่มใช้งาน

ติดตั้งด้วย `Install_3117_BIM_Studio.FCMacro` แล้วปิด/เปิด FreeCAD ใหม่ เลือก Workbench **3117 BIM Studio** เปิด `examples/types/Types_Quantities_Workbench.FCStd`

1. เปิด **Type Catalogue** ในกลุ่มเครื่องมือปริมาณ ดู Materials และ Types ที่ใช้ในโมเดล
2. เลือก Type เช่น `Column 300 x 300` แล้ว Edit การเปลี่ยนขนาดจะเปลี่ยนเสาที่อ้าง Type นี้ทั้งหมด ใช้ Undo/Redo คืนและทำซ้ำได้
3. เลือกชิ้นส่วนในโมเดล ใช้ Assign Type เพื่อกำหนดชนิดร่วม ใช้ Duplicate Type เมื่อต้องการแยกชนิดใหม่ก่อนแก้
4. เปิด **Schedules** หรือดับเบิลคลิก Schedule ในต้นไม้ เลือกตารางตาม Category, Level, Type และชื่อชิ้นส่วน
5. เลือกแถวเพื่อเลือกชิ้นส่วนจริง ใช้ Edit Row แก้ชื่อ ชนิด และค่าตำแหน่งที่เปิดให้แก้ ตารางที่รวมหลายชิ้นส่วนต้องเลือก UUID ต้นทางให้ชัดเจน
6. ส่งออก CSV พร้อม metadata จาก Schedule หรือเปิด Quantities / Exchange เพื่อส่งออกทั้งโมเดลเป็น CSV/IFC4

ค่ารูปทรงในฟอร์มใช้ **mm**; ตารางและ CSV ใช้ **m, m², m³** การส่งออกเป็น snapshot ที่มี revision ระบุ ไฟล์ CSV/IFC ไม่อัปเดตตามโมเดลโดยอัตโนมัติ

## 2. Type กับ Instance

| Category | Type เป็นผู้กำหนด | Instance เป็นผู้กำหนด |
|---|---|---|
| Wall | ความหนา หรือผลรวมชั้นวัสดุ; Material | แนวเส้น, Base/Top Level และ offsets |
| Slab | ความหนา หรือผลรวมชั้นวัสดุ; Material | polygon, Level และ top offset |
| Column | Width, Depth, Material | X/Y, rotation, Base/Top Level และ offsets |
| Beam | Width, Depth, Material | แนวเส้น, Level และ top offset |
| Door | Width, Height, Material ของกรอบทั่วไป | Wall host, offset และ sill |
| Window | Width, Height, Material ของกรอบทั่วไป | Wall host, offset และ sill |

Wall ใช้ native `WallType` เดิม ส่วนอีกห้าประเภทใช้ `ElementType` ซึ่งมี Category ชัดเจน Type ข้าม Category หรือข้าม Project ใช้แทนกันไม่ได้ วัตถุมี UUID ถาวร; ชื่อและ Code แก้ได้ โดย Code ที่ไม่ว่างต้องไม่ซ้ำภายในกลุ่ม Type หรือกลุ่ม Material ของ Project

Instance ที่อ้าง Type แสดงขนาดที่ถูกควบคุมเป็น read-only ขนาดเหล่านี้เป็นค่าที่คำนวณจาก Type และเก็บเป็น native cache เพื่อดูใน Properties; การสร้าง geometry อ่าน Type โดยตรง ไม่มี instance override ของขนาดเดียวกันซ้อนอยู่

Slab/Column/Beam/Door/Window เดิมที่ยังไม่กำหนด Type ยังคงใช้ค่ารายตัวได้ **Detach Type** จะเก็บขนาดปัจจุบันไว้ให้แก้รายตัวต่อ ส่วน Wall ต้องมี WallType เสมอ การเปลี่ยนชนิดกับการเปลี่ยนตำแหน่ง/ชื่อจาก Edit Row สามารถ commit พร้อมกันในหนึ่ง transaction

## 3. วัสดุและชั้นวัสดุ

Material เป็น native object ที่มี UUID, Name และ Code Type เลือกได้ระหว่างวัสดุเดียวทั้งชิ้น หรือ ordered material layers สำหรับ Wall/Slab

- ความหนาแต่ละชั้นต้องเป็นบวก และผลรวมเป็นความหนาของ Type
- Wall เรียงชั้นจาก local Y=0 ไปทาง +Y ตามแนวผนังเดิม ไม่ย้ายแนวอ้างอิงเมื่อเพิ่มชั้น
- Slab เรียงชั้นจากผิวบนลงล่าง ผิวบนอยู่ที่ Level + Offset ตามกฎเดิม
- Material หนึ่งรายการใช้ได้ในหลายชั้นและหลาย Type แต่ยังรักษาลำดับชั้นไว้ เช่น plaster / masonry / plaster
- ห้ามลบ Material ที่ยังถูก Type อ้าง และห้ามลบ Type ที่ยังถูก Instance หรือ Schedule filter อ้าง

ข้อความ Material ในไฟล์รุ่นเดิมไม่ถูกแปลงเป็น Material object โดยการเดาชื่อ เมื่อยังไม่กำหนด native Material ระบบรายงานชิ้นส่วนเหล่านั้นเป็น **unassigned** ใน coverage ปริมาณวัสดุจึงแสดงว่าครอบคลุมกี่ชิ้นจากทั้งหมด

### กฎปริมาณ

| ปริมาณ | กฎในรุ่นนี้ |
|---|---|
| Wall gross/net | ผนังตรง ความหนาคงที่ หักช่อง Door/Window ตาม boolean solid; ไม่มี wall-wall join deduction |
| Slab | polygon แนวราบ หนาคงที่ มี top datum; ยังไม่มี opening/sketch-hole ของ Slab |
| Column/Beam | ใช้ gross solid หัก Slab ที่ระบุใน JoinSlabs; ชิ้นส่วนต้องเหลือ connected solid เดียว |
| Door/Window | นับช่องเปิดและ generic frame แยกกัน; frame ไม่เท่ากับปริมาตรช่องเปิดหรือผลิตภัณฑ์จริงครบชิ้น |
| ชั้นวัสดุ | ตัด gross/net solid จริงกับช่วงชั้นวัสดุด้วย OCCT แล้วรวมคืนต้องได้ปริมาตรของชิ้นส่วนต้นทาง |
| วัสดุเดียว | หนึ่ง material row ต่อชิ้นส่วน ใช้ net solid รวมผลหักช่องเปิด/รอยต่อที่เกี่ยวข้องแล้ว |
| ยอดรวม | ผลรวมปริมาณรายชิ้นตามกฎ ไม่มีการหัก overlap ระหว่างทุก Category แบบอัตโนมัติ |

Material rows เป็นการแจกแจงปริมาณของ product rows จึง **ห้ามนำสองชุดมาบวกซ้ำกัน** ไม่มีราคาวัสดุ ค่าแรง เผื่อสูญเสีย ความหนาแน่น หรือน้ำหนักที่ระบบสมมติขึ้นเอง การอ้างว่าครอบคลุมวัสดุ 100% หมายถึงทุกชิ้นส่วนในโมเดลทดสอบได้รับ assignment ไม่ใช่ BOQ งานก่อสร้างที่ครบทุกกิจกรรม

ชั้นวัสดุรุ่นนี้เป็นพารามิเตอร์สำหรับ quantity และ IFC; โมเดลยังมี solid ผลลัพธ์หลักหนึ่งชุดต่อชิ้นส่วน ไม่เพิ่ม layer geometry objects ให้ผู้ใช้แก้แยก และยังไม่มี layer hatch / layer boundary drawing editor

## 4. Schedule

`ScheduleSet` และ `Schedule` เก็บอยู่ใน FCStd เป็นกลุ่มแยกจาก `Project.Group` คล้าย DrawingSet ตารางไม่เป็น IFC building product และไม่เปลี่ยน building content hash การเพิ่มหรือแก้กฎตารางเปลี่ยนเฉพาะ `schedule_revision`

| ตัวเลือก | ขอบเขต |
|---|---|
| Category | Wall, Door, Slab, Column, Beam, Window, Material |
| Level | Base Level ของ Wall/Door/Window/Column; Level ของ Slab/Beam |
| Type | Type UUID ที่อยู่ใน Project และตรง Category; Material schedule เลือก Type ได้ทุก Category |
| Name filter | ค้น substring ของชื่อชิ้นส่วนต้นทาง ไม่แยกตัวพิมพ์เล็ก/ใหญ่ กรองก่อนรวมกลุ่ม |
| Group by | None, Type หรือ Material; Material grouping ใช้กับ Material category เท่านั้น |
| Sort | Name, Type, Level, Material; ascending/descending และใช้ UUID เป็นลำดับเสริม |
| Count | จำนวน UUID ของชิ้นส่วนต้นทางที่ไม่ซ้ำ; จำนวน material layer rows รายงานแยก |

ตารางรวมเฉพาะค่าที่บวกกันได้ เช่นพื้นที่/ปริมาตร ไม่รวมความหนา ความกว้าง หรือความสูงให้กลายเป็นขนาด Type ใหม่ กลุ่ม Material เดียวกันอาจมีชิ้นส่วนหลายประเภท; ชิ้นส่วนที่มีหลาย Material ปรากฏในหลายกลุ่มได้ ยอดจำนวนผลิตภัณฑ์รวมจึงนับ UUID ที่ไม่ซ้ำอีกครั้ง

**Edit Row** แก้ข้อมูลต้นทาง โดยเลือก Type และค่ารายตัวที่เกี่ยวข้อง ช่อง Level, Host และ Slab boundary ที่ซับซ้อนใช้ Edit Selected ของชิ้นส่วนตามเดิม ค่าปริมาณรวมเป็น read-only และ API ปฏิเสธชื่อพารามิเตอร์คำนวณ เช่น `net_volume_m3`

ผล preview/capture คำนวณทั้ง model revision และ schedule revision จากข้อมูลปัจจุบัน เมื่อโมเดลหรือกฎตารางเปลี่ยน หน้าต่างต้อง refresh ก่อนแก้แถวหรือส่งออก การลบ reference ผ่าน Python/native command โดยข้าม service จะไม่ล้าง expected UUID ทิ้ง: Schedule ที่เสีย reference ถูกปิดการ capture/export จนกว่าจะ reassign หรือ detach อย่างชัดเจน แต่โมเดลอาคารที่ถูกต้องยังคำนวณ/ส่งออกได้

## 5. Transaction และความถูกต้องของการเปลี่ยน Type

บริการแก้ไขตรวจ proposal ก่อนเปิด transaction โดยคำนวณ transient OCCT solids ของ **ทั้ง proposed state** แล้วจึง commit การแก้ที่ผ่านเป็นหนึ่ง transaction

ตัวอย่างที่ต้องตรวจพร้อมกันคือ Door/Window หลายชิ้นใช้ Type เดียวกันแล้วขยายจนทับกัน หรือ Slab หลายชิ้นเปลี่ยน Type พร้อมกันจนการรวม cutter ตัด Column หมด การตรวจทีละชิ้นโดยอาศัยขนาดเก่าของชิ้นอื่นไม่เพียงพอ รุ่นนี้มี native acceptance กรณีเหล่านี้ รวมการตรวจว่าข้อเสนอที่ผิดไม่เปลี่ยน source/Undo/Redo

ไฟล์ `.FCStd` เป็นข้อมูลหลักเพียงชุดเดียว การ preview, capture, CSV/IFC export ไม่เพิ่ม object/caches ที่แก้ไขได้ ไม่เพิ่ม Undo entry และไม่เขียน revision stamp ลงในโมเดล

## 6. CSV และ IFC

CSV ทั้งโมเดลคงคู่ Wall/Door และ sidecars ของ Category ที่มีข้อมูล เพิ่ม `_types.csv` และ `_materials.csv` เมื่อมีข้อมูลใหม่ Material rows ระบุ UUID ของชิ้นส่วน, Type, Material, Level, ลำดับ/บทบาทชั้น, gross/deduction/net volume และกฎที่ใช้ ตัวอย่างเดิมที่ไม่มี catalogue features ยังคง hash และ CSV payload เดิมตาม regression fixture

Schedule CSV มีไฟล์ `<name>_schedule_metadata.json` ระบุ definition, rows, source UUIDs, หน่วย, coverage, สอง revisions และ SHA256 ของ payload ใช้ UTF-8 BOM เพื่ออ่านชื่อไทย และเติม apostrophe ให้ข้อความที่อาจถูกโปรแกรมตารางคำนวณตีความเป็น formula; metadata เก็บข้อความต้นฉบับ

การเผยแพร่ไฟล์ใช้ staged files, freshness check ก่อน commit, per-file atomic replacement และ rollback เมื่อจับความผิดพลาดได้ Metadata เขียนเป็น completion marker สุดท้าย ไม่อ้างว่าชุดหลายไฟล์ crash-atomic ต้องตรวจ SHA256 เมื่อนำไปใช้

IFC4 ส่งออกชนิดจริงครบ `IfcWallType`, `IfcSlabType`, `IfcColumnType`, `IfcBeamType`, `IfcDoorType`, `IfcWindowType` และความสัมพันธ์กับ occurrence; native Material ส่งออกเป็น `IfcMaterial` พร้อม identity/source properties ชั้นวัสดุเป็น LayerSet ของ Type และ LayerSetUsage ของแต่ละ occurrence ตามสัญญา IFC/IfcOpenShell [S1][S2]

การกำหนดของ exporter ในโครงการนี้: Wall ใช้ AXIS2/POSITIVE/offset 0; Slab ใช้ AXIS3/NEGATIVE/offset เท่าความหนารวม เพื่อสอดคล้องกับ IFC placement ที่อยู่ผิวล่างและ native layer order จากผิวบนลงล่าง หน่วยทั้งหมดใน IFC เป็น SI วัตถุที่เดิมมีอยู่คง GlobalId และ geometry เมื่อ Type ที่เพิ่มมีขนาดเท่าเดิม

## 7. API ที่ใช้งานได้

ตัวอย่างต่อไปนี้รันใน FreeCAD ที่ติดตั้ง Workbench แล้ว ไม่ติดตั้ง PySide/Qt ซ้อนเข้าไปใน host:

```python
from bim3117_freecad import catalog, schedules, services

project = services.get_project()
concrete = catalog.create_material(project, "Concrete", code="CONC")
finish = catalog.create_material(project, "Finish", code="FIN")
slab_type = catalog.create_type(project, "Slab 150", "Slab", code="S150", layers=[
    {"material": finish, "thickness_mm": 10, "role": "finish"},
    {"material": concrete, "thickness_mm": 140, "role": "structure"},
])
catalog.assign_types(services.list_slabs(project), slab_type)
table = schedules.create_schedule(project, "Slabs by Type", "Slab", group_by="Type")
preview = schedules.capture_schedule(table)
schedules.export_schedule(
    table, r"C:\BIM\Slabs.csv",
    expected_model_revision=preview["model_revision"],
    expected_schedule_revision=preview["schedule_revision"],
)
```

`catalog.edit_type`, `duplicate_type`, `assign_type(s)`, `edit_instance`, `delete_type` และ Material CRUD ใช้ transaction ของตัวเอง ห้ามครอบ public mutation ด้วย transaction อีกชั้น `schedules.edit_row` รับ UUID ต้นทาง, changes dictionary และสอง expected revisions; `edit_schedule` รับ native link สำหรับ Level/Type และใช้ `None` เพื่อ detach ตัวกรองอย่างชัดเจน

## 8. หลักฐานและขอบเขตที่ยังเปิดอยู่

Native lifecycle/reopen, geometry/quantity fixture, actual GUI, serialized IFC readback และ external import รายงานแยกกันใน [Verification](VERIFICATION.md) ใช้ `Run_3117_Types_Test.FCMacro` เพื่อทดสอบ workflow บนเครื่องเป้าหมาย และเก็บ Windows acceptance ก่อนประกาศ Windows-ready

ยังไม่รวม family editor/formulas, custom arbitrary schedule columns, calculated fields, schedule placement on sheets, pricing/cost database, multilayer join priorities, wall-wall joins, curved/sloped geometry, roof/stair tools, MEP, structural analysis, .rvt/.rfa, multiuser authoring หรือการนำ IFC กลับเป็น native editable catalogue แบบครบวงจร งานถัดไปคือ v0.9.0 Pilot ตาม [Roadmap](ROADMAP.md)

### แหล่งข้อมูลเทคนิค

- [S1 — buildingSMART IFC4: IfcMaterialLayerSetUsage](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/FINAL/HTML/link/ifcmateriallayersetusage.htm): ความสัมพันธ์ระหว่าง layer order, location และ orientation ของ occurrence
- [S2 — IfcOpenShell material.assign_material](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/material/assign_material/index.html): Type/occurrence material assignment, layer-set usage และหน้าที่รักษาความสอดคล้องของ geometry กับความหนารวม
