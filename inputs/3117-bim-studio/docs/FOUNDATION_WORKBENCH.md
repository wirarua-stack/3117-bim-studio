# v0.1.0 — Foundation Workbench

เอกสารนี้เก็บสัญญา Project/Level/Grid ที่เริ่มใน v0.1.0 และใช้ต่อใน v0.2.1 ส่วน Wall Type/Wall/Hosted Door ดู [Wall / Door Workbench](WALL_DOOR_WORKBENCH.md) และปริมาณ/IFC ดู [Quantity / Exchange](QUANTITY_EXCHANGE.md) ผลปัจจุบันดู [Verification](VERIFICATION.md)

ชุดพัฒนานี้เพิ่ม Workbench **3117 BIM Studio** ที่ทำงานใน FreeCAD จริง สำหรับตั้งต้นโครงการ ระดับ และกริด ข้อมูลโครงการอยู่ใน native FreeCAD Document และบันทึกเป็น `.FCStd` โดยใช้ transactions และ Undo/Redo ของ FreeCAD

**FreeCAD เป้าหมาย: 1.1.4 stable; ผลตรวจรับแต่ละระบบปฏิบัติการอยู่ใน [VERIFICATION.md](VERIFICATION.md)** การทดสอบ Linux ไม่แทนการตรวจรับ Windows

## เครื่องมือที่ใช้งานได้

| คำสั่ง | พฤติกรรม |
|---|---|
| Create Project | เปิดเอกสารใหม่ สร้าง Project พร้อมชื่อ เลขโครงการ และผู้จัดทำ; เลือกสร้าง L00/L01 เริ่มต้นที่ 0/3000 mm ได้ |
| Add Level | สร้างระดับด้วย elevation และขอบเขตเส้นอ้างอิง Span X/Y |
| Create Grid | สร้างกริดตรงหนึ่งแนว ขนาน X หรือ Y พร้อมวงกลมและชื่อปลายกริด; ผูกระดับและ offset ได้ |
| Edit Selected | แก้ Project, Level หรือ Grid ที่เลือก ผ่านฟอร์มเดียว; แก้หลายค่าแล้ว Undo หนึ่งครั้งคืนได้ทั้งคำสั่ง |
| Host Information | แสดงรุ่น Workbench, FreeCAD, Python, Qt และ OS ที่กำลังรัน |

ใช้ Selection, Properties, Undo, Redo, Fit All และ Save/Open ของ FreeCAD ตามปกติ Workbench ไม่เปิดเอกสารเองเมื่อเพียงสลับเข้ามา

## รูปแบบข้อมูลและหน่วย

| วัตถุ | Native type | ข้อมูลสำคัญ |
|---|---|---|
| Project | `App::DocumentObjectGroupPython` | `Label`, `ProjectNumber`, `Author`, `Group` |
| Level | `Part::FeaturePython` | `Elevation`, `SpanX`, `SpanY`, `Project` |
| Grid | `Part::FeaturePython` | `Axis`, `Position`, `Length`, `BubbleLabel`, `BubbleRadius`, `ReferenceLevel`, `ElevationOffset`, `Project` |

ทุกวัตถุมี `BIM3117Id` แบบ UUID, `BIM3117Schema`, `BIM3117Kind` และ `BIM3117Version` ที่บันทึกในไฟล์ Native properties เป็นข้อมูลหลัก; Python Proxy เก็บพฤติกรรม ไม่ใช่โมเดลอีกสำเนาหนึ่ง

ฟอร์ม 3117 และ host-service API รุ่นนี้รับระยะเป็น **มิลลิเมตร** ชื่อ argument ลงท้าย `_mm` ชัดเจน Native Properties อาจแสดง mm หรือ m ตามการจัดรูปแบบหน่วยของ FreeCAD แต่ค่าภายใน `.Value` เป็น mm ส่วน `src/bim3117` เป็น reference core เดิมที่รับ **เมตร** และเป็นคนละ package จึงไม่ควรนำตัวเลขจากสอง API มาใช้ข้ามกันโดยไม่แปลงหน่วย

Project origin รุ่นนี้เป็นพิกัดภายใน `(0,0,0)` คงที่; Z ชี้ขึ้น ยังไม่มี shared coordinates, survey transformation หรือการหมุน True North เส้น Level และ Grid เป็น datum สำหรับอ้างอิง ไม่ใช่พื้นหรือผนัง และไม่ใช้คำนวณปริมาณอาคาร

### ความหมายของกริด

- `Axis=X`: เส้นขนานแกน X, `Position` คือพิกัด Y
- `Axis=Y`: เส้นขนานแกน Y, `Position` คือพิกัด X
- ความยาวเส้นอยู่สมมาตรรอบ origin ตามทิศแกน: จาก `-Length/2` ถึง `+Length/2`
- Z ของกริด = `ReferenceLevel.Elevation + ElevationOffset`; ถ้าเลือกไม่มีระดับอย่างชัดเจน ใช้ offset จาก origin
- ชื่อในต้นไม้ (`Label`) และข้อความปลายกริด (`BubbleLabel`) แก้แยกกันได้
- `Placement` ของ datum ล็อกไว้; เปลี่ยนตำแหน่งผ่านพารามิเตอร์ที่เกี่ยวข้อง

กริดมีเฉพาะแนวตรงตั้งฉาก X/Y รุ่นนี้ยังไม่มีกริดโค้ง การหมุนกริดทั้งระบบ หรือการวาดจากเมาส์

## การแก้ไขและ transaction

หนึ่ง service command เปิด transaction ของเอกสารหนึ่งครั้ง เขียนค่าที่ผ่าน validation, recompute, ตรวจ geometry แล้ว commit หากเกิดข้อผิดพลาดหลังเริ่มเปลี่ยนข้อมูล จะ abort ทั้งคำสั่ง

Properties editor ของ FreeCAD เป็นผู้ถือ transaction ของการแก้ property โดยตรง Callback ของวัตถุไม่เปิด transaction ซ้อนและไม่เรียก recompute เอง ค่าตัวเลขที่ไม่เป็นจำนวนจำกัดและช่วงแสดง datum ที่ไม่เป็นบวกจะถูกปฏิเสธ

ตัวอย่าง: สร้าง Grid ที่ผูกกับ L01 แล้วเปลี่ยน L01 จาก 3000 เป็น 3300 mm กริดจะเปลี่ยน Z ตาม เมื่อ Undo ทั้ง Level และรูปทรงกริดต้องกลับเป็นค่าเดิม การเปลี่ยน Label ไม่เปลี่ยน UUID

Project Label เป็นชื่อองค์ประกอบโครงการ ส่วนชื่อแท็บเอกสาร/ชื่อไฟล์เป็นข้อมูลของ FreeCAD แยกกัน การแก้ Project ไม่เปลี่ยนชื่อไฟล์โดยอัตโนมัติ

## การลบและความสัมพันธ์

การลบ Level ที่มี Grid อ้างอิงต้องถูกปฏิเสธใน GUI ให้ใช้ Edit Selected ของ Grid เพื่อเลือก Level ใหม่หรือเลือกไม่มีระดับโดยตั้งใจเสียก่อน Project ที่ยังมีองค์ประกอบต้องจัดการลูกให้ครบก่อนลบ ไม่มี cascade delete อัตโนมัติในรุ่นนี้

โค้ด integration ควรใช้ service API ที่ประกาศ การเรียก `doc.removeObject` หรือเขียน native metadata โดยตรงจาก Python เป็นการข้ามคำสั่งที่รองรับ ไม่ใช่ช่องทางปกติสำหรับ authoring

การจัดสมาชิกกลุ่มใช้คำสั่ง Foundation ในรุ่นนี้ ยังไม่รองรับการย้ายสมาชิกโดยลากต้นไม้หรือการ copy native object ดิบ การตรวจเอกสารจะปฏิเสธ membership ที่ขัดแย้งหรือ UUID ซ้ำ หาก native link ของกริดถูกล้างโดยไม่ได้ตั้งใจ ระบบเก็บ UUID ของระดับที่คาดไว้และแสดง invalid geometry ให้ใช้ Edit Selected เพื่อเลือกระดับใหม่หรือเลือกไม่มีระดับอย่างชัดเจน

## API สำหรับพัฒนาต่อ

เรียกภายใน FreeCAD ที่ติดตั้ง Workbench แล้ว ตัวอย่างนี้สร้างเอกสารใหม่ จึงไม่เขียนทับเอกสารที่เปิดอยู่

```python
from bim3117_freecad import services

project = services.create_project("My Building", project_number="P-001")
l00, l01 = services.list_levels(project)
grid = services.create_grid(
    project, "Grid A", axis="X", position_mm=-4000,
    length_mm=16000, bubble_label="A", level=l01,
)
services.edit_level(l01, elevation_mm=3300)
project.Document.undo()
project.Document.recompute()
services.validate_document(project.Document, check_shapes=True)
```

อย่าครอบ mutating services ด้วย `doc.openTransaction` อีกชั้น หากมี transaction เปิดอยู่ คำสั่งจะขอให้จบหรือยกเลิก transaction เดิมก่อน ไม่แย่ง commit คำสั่งจากเครื่องมืออื่น

## การติดตั้งและตรวจรับ

ใช้ [คู่มือติดตั้ง](../packaging/INSTALL_TH.md) จาก ZIP ที่แตกแล้ว รัน `Install_3117_BIM_Studio.FCMacro` ภายใน FreeCAD แล้วปิด/เปิด FreeCAD ทุกหน้าต่าง การวาง source path ไว้ใน `sys.path` อย่างเดียวไม่แทนการติดตั้ง add-on ที่ FreeCAD ยอมรับสำหรับการกู้คืน Python Proxy จากไฟล์

รัน `Run_3117_Smoke_Test.FCMacro` เพื่อทดสอบคำสั่งจริงผ่านฟอร์ม สร้างไฟล์ตัวอย่างและรายงาน JSON โดยไม่แก้โครงการเดิม จากนั้นปิดโปรแกรมทั้งหมด เปิดตัวอย่างใหม่ เปลี่ยน L01 และลอง Undo/Redo เพื่อพิสูจน์ fresh-process reopen บนเครื่องเป้าหมาย

Checklist Windows ขั้นสุดท้ายและช่องบันทึก environment อยู่ใน [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md) ผลที่ยังไม่ทำต้องระบุ pending ไม่เปลี่ยนเป็น passed จากผล Linux

## ลำดับต่อจาก Foundation

v0.2.0 เชื่อม Wall type/instance กับ Level เดิมใน `.FCStd` และเพิ่ม hosted Door/ช่องเปิดจริงตาม [Wall / Door Workbench](WALL_DOOR_WORKBENCH.md) แล้ว v0.2.1 เพิ่ม native quantity rows, CSV และ IFC4 จาก document เดียวกันตาม [Quantity / Exchange](QUANTITY_EXCHANGE.md) ส่วน building categories เพิ่มเติม แบบ และ schedule editor เป็นงานถัดไป
