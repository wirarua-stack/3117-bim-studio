# v0.3.0 — Building Authoring

สัญญาการใช้งานและพัฒนา: Slab, Column, Beam, hosted Window และรอยต่อ Slab–Column/Beam แบบกำหนดลำดับชิ้นส่วน ผลตรวจรับที่รันจริงให้ดู [VERIFICATION.md](VERIFICATION.md) ของรุ่นที่ส่งมอบ

## ขอบเขตและพิกัด

FCStd เป็นข้อมูลหลัก ใช้ native properties ในหน่วย mm และ geometry จาก OCCT ตารางและ IFC แปลงเป็น SI วัตถุทุกชิ้นมี UUID คงเดิมและแก้ผ่าน transaction ของ document

| ชนิด | ข้อมูลที่ผู้ใช้กำหนด | รูปทรงและกฎ |
|---|---|---|
| Slab | Level, Offset, Boundary XY, Thickness, Material | ผิวบน = Level + Offset; เพิ่มความหนาลงด้านล่าง ขอบเป็น polygon ระนาบเดียวที่ไม่ตัดตัวเอง รองรับมุมเว้า ไม่มีรูภายใน |
| Column | X/Y ศูนย์กลาง, Width/Depth, Rotation, Base/Top Level, offsets, Material | เสาตั้งตรง หน้าตัดสี่เหลี่ยม หมุนรอบแกน Z; สูงจาก Base ถึง Top ที่รวม offsets แล้ว |
| Beam | Start/End XY, Level, Offset, Width/Depth, Material | คานตรงแนวนอน Width อยู่สองข้างของแนวศูนย์กลาง; ผิวบน = Level + Offset; Depth ลงด้านล่าง |
| Window | Host Wall, Offset, Width/Height, Sill | ช่องเปิดจริงและกรอบสี่ด้าน ตำแหน่งอ้างอิงแกนผนังร่วมกับ Door |

Thickness, section dimensions และ Material ของ Slab/Column/Beam เป็นค่าราย instance ในรุ่นนี้ ส่วน WallType เดิมยังแชร์ให้ Wall instances ได้ตามปกติ การทำ catalogue/type ขององค์ประกอบใหม่เป็นงานถัดไป

Window Width/Height คือขนาดช่องตัดรวมกรอบ กรอบกว้าง `min(50 mm, Width/4, Height/4)` ไม่มีบาน กระจก หรือทิศเปิด การซ้อนช่องเปิดตรวจร่วมระหว่าง Door และ Window ของผนังเดียวกัน

## รอยต่อที่รองรับ

ใช้คำสั่ง Join Slab เพื่อให้พื้นเป็นชิ้นส่วนที่เก็บเนื้อไว้ แล้วหักส่วนซ้อนออกจาก Column หรือ Beam ที่เลือก การผูกใช้ native reference list `JoinSlabs` พร้อม UUIDs และอยู่ใน transaction เดียวกับรูปทรงและผลปริมาณ

- เป้าหมายคือ Column หรือ Beam; ตัวตัดต้องเป็น Slab ใน Project เดียวกัน
- ตอนเพิ่มรอยต่อต้องมีปริมาตรซ้อนจริง
- ผลตัดต้องเหลือ solid เดียวที่มีปริมาตรบวก การตัดขาดเป็นหลายชิ้นหรือตัดหมดถูกปฏิเสธและ rollback
- การแก้ Slab ภายหลังที่ทำให้ไม่ซ้อนกันแล้วคง reference ได้ โดยค่าหักเป็นศูนย์
- Unjoin คืนเนื้อส่วนที่ถูกหักจากพื้นนั้น; Undo/Redo คืน reference และรูปทรงทั้งชุด
- ลบ Slab ที่ยังเป็น cutter ไม่ได้จนกว่าจะ Unjoin

กฎนี้ไม่ใช่ระบบ join ทั่วไปสำหรับทุกคู่ขององค์ประกอบ การทับกันของ Beam–Column, Wall–Wall หรือ Wall–Slab ยังไม่มีการหักโดยอัตโนมัติ ปริมาณต้องอ่านตามกฎรายประเภทที่ระบุ ไม่ใช้ผลบวกรวมแทน BOQ ที่ผ่านการตรวจทั้งอาคาร

## ใช้งานผ่าน Workbench

1. Create Project ให้มี Base/Top Levels แล้วสร้าง Slab โดยเลือกระดับผิวบนและความหนา ฟอร์มรับสี่เหลี่ยมหรือ XY polygon ทีละจุด
2. สร้าง Column โดยกำหนดศูนย์กลาง หน้าตัด rotation และ Base/Top Levels; สร้าง Beam โดยกำหนดปลายแกนและระดับผิวบน
3. เลือกสมาชิกกับ Slab แล้วเรียก Join Slab หรือเลือกจากฟอร์มคำสั่ง รอยต่อมีทิศทางชัดเจน: Slab เก็บเนื้อ ส่วนสมาชิกถูกตัด
4. เลือก Wall แล้ว Create Window กำหนดระยะจากจุดเริ่มผนังและ Sill จากฐานผนัง ใช้ Edit Selected ย้าย Host ได้
5. เปลี่ยน Level หรือ Thickness แล้วตรวจ geometry/quantity และใช้ Undo/Redo เพื่อคืนค่า
6. เปิด Quantities & Exchange จะมี 6 หมวดองค์ประกอบและ Coverage คลิกแถวกลับไปเลือกวัตถุต้นทาง
7. Save FCStd ปิดและเปิด FreeCAD ใหม่ก่อนทดสอบการแก้ dependency ต่อ ใช้ Run_3117_Building_Test.FCMacro เพื่อตรวจ workflow ด้วยเอกสารทดสอบ

ฟอร์มใช้ mm ส่วนตาราง/CSV/IFC ใช้ SI ตามชื่อคอลัมน์ การแก้หนึ่งคำสั่งใช้หนึ่ง transaction; หาก dependent geometry ไม่ผ่านจะ rollback ทั้งชุด

Door/Window proposals, Slab/Column/Beam edits และ Join Slab ตรวจ bounds/overlap/proposed cuts ก่อนแก้ native properties จึงรักษา Redo branch เมื่อปฏิเสธค่าที่ตรวจได้เหล่านี้ การตรวจใช้ค่าชั่วคราวและ transient solids เท่านั้น ไม่สร้าง document อีกชุด Callback และ document validation ยังคงตรวจหลังแก้ด้วย

`Unjoin Slab` แบบล้างทั้งหมด (`unjoin_slab(member, None)`) ใช้แก้ cutter reference ที่ขาดได้ เมื่อมีวัตถุอื่นใน document ไม่ถูกต้องด้วยให้ Undo การลบต้นเหตุ เพราะ transaction gate ตรวจทั้ง document

## ปริมาณและ IFC

| ชนิด | ค่าปริมาณหลัก | IFC4 |
|---|---|---|
| Slab | gross_area_m2, net_area_m2, perimeter_m, thickness_m, gross_volume_m3, net_volume_m3 | IfcSlab, PredefinedType=FLOOR |
| Column | section_area_m2, height_m, gross_volume_m3, join_deduction_m3, net_volume_m3 | IfcColumn |
| Beam | length_m, section_area_m2, gross_volume_m3, join_deduction_m3, net_volume_m3 | IfcBeam |
| Window | opening_area_m2, opening_volume_m3, frame_volume_m3, host_id | IfcWindow + IfcOpeningElement + void/fill relations |

Column/Beam เก็บ cutter IDs, offsets และกฎรอยต่อใน source properties และใช้ boolean DIFFERENCE สำหรับรูปทรงส่งออก Qto และ actual mesh volume/bounds ต้องตรงกับ native solid ส่วน Slab ไม่ถูกหักด้วยสมาชิกที่มันตัด

## API

```python
from bim3117_freecad import services

slab = services.create_slab(
    project, "S01", level,
    boundary_mm=[(0, 0), (6000, 0), (6000, 4000), (0, 4000)],
    thickness_mm=150, offset_mm=0, material="Concrete")

column = services.create_column(
    project, "C01", base_level, top_level,
    x_mm=1000, y_mm=1000, width_mm=300, depth_mm=400,
    rotation_deg=0, base_offset_mm=0, top_offset_mm=0,
    material="Concrete")

beam = services.create_beam(
    project, "B01", level,
    start_mm=(0, 2000), end_mm=(6000, 2000),
    width_mm=300, depth_mm=450, offset_mm=0, material="Concrete")

window = services.create_window(
    project, "W01", wall,
    offset_mm=3000, width_mm=1200, height_mm=1200, sill_mm=900)

services.join_slab(beam, slab)
services.unjoin_slab(beam, slab)
```

คำสั่ง edit/list/delete ใช้ชื่อสอดคล้องกับชนิด เช่น `edit_slab`, `list_columns`, `delete_window` และใช้ service transaction เช่นเดียวกับ Wall/Door เดิม ควรเรียก API ผ่าน host FreeCAD ที่ติดตั้ง Workbench แล้ว

## เกณฑ์ตรวจรับของรุ่น

1. สร้าง แก้ ลบ ยกเลิก และ Undo/Redo ขององค์ประกอบใหม่ได้ด้วย native transaction
2. ปรับ Level/Thickness/section แล้ว geometry และ quantity rows อัปเดต โดย invalid downstream state rollback ทั้งชุด
3. ขอบพื้นไม่ถูกต้อง ช่องเปิดซ้อนกัน รอยต่อที่ตัดชิ้นส่วนขาด และ missing references ถูกตรวจพบ
4. ตารางหนึ่งแถวต่อ authored UUID ใช้หน่วยและกฎชัดเจน ไม่เพิ่มรายการจาก derived geometry
5. IFC4 ส่งออก Slab/Column/Beam/Window พร้อมตำแหน่ง storey ช่องเปิด และรอยต่อที่ทำให้รูปทรง/ปริมาตรตรงกับ native solid
6. เปิด FCStd ใน process ใหม่ได้โดย UUID, references, geometry และ revision ตรงกัน
7. เปิด IFC ตัวอย่างใน Bonsai แล้วตรวจรูปทรงและปริมาตรจริง แยกจากการ readback ใน exporter
8. ทดสอบผ่าน GUI และชุด macro จาก ZIP ที่ส่งมอบ โดยระบุ OS/runtime ตามที่รันจริง

ขอบเขตถัดไป: พื้นที่มีรู, คานเอียง, หน้าตัดเพิ่มเติม, catalogue ของชนิด, รอยต่อแบบอื่น และ roof/stair templates แบบ/แผ่นแบบเบื้องต้นเพิ่มแล้วใน v0.4.0 ตาม [DRAWINGS_AND_SHEETS.md](DRAWINGS_AND_SHEETS.md) ยังไม่รวมการวิเคราะห์หรือออกแบบกำลังรับน้ำหนักโครงสร้าง
