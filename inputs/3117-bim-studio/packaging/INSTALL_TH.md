# ติดตั้ง 3117 BIM Studio v0.5.0 — Types and Quantities

ชุดนี้เพิ่ม Workbench **3117 BIM Studio** ลงใน FreeCAD ที่ติดตั้งอยู่แล้ว ใช้ Python และ Qt ของ FreeCAD จึงไม่ต้องติดตั้ง Python, pip, Git หรือสิทธิผู้ดูแลระบบเพิ่มเติมสำหรับส่วน 3117

**รุ่นเป้าหมาย: FreeCAD 1.1.4 stable บน Windows 64-bit** ตรวจสอบจากประกาศต้นทางวันที่ 28 กันยายน 2026 การระบุรุ่นเป้าหมายไม่ใช่การรับรองผลทดสอบบน Windows; ดูผลที่รันจริงในเอกสาร Verification ของรุ่นที่ส่งมอบ

**ชุดพัฒนานี้ยังมี release blocker:** พบ native Undo/Redo crash บน FreeCAD 1.1.4 Linux จากการสร้าง–ลบ–Undo สองครั้ง–แก้ไขใหม่–Undo/Redo โดยเกิดกับวัตถุมาตรฐานที่ไม่มี 3117 ด้วย อาจสูญเสียงานที่ยังไม่บันทึก ทดลองกับสำเนาหรือเอกสารทดสอบเท่านั้น และอ่าน [HOST_COMPATIBILITY.md](../docs/HOST_COMPATIBILITY.md) ก่อนติดตั้ง การติดตั้ง/ผ่าน macro ฟังก์ชันบางชุดไม่ใช่การปิดข้อขัดข้องนี้; Windows ยังรอตรวจรับ

## 1. เตรียมเครื่อง

1. ดาวน์โหลด FreeCAD จาก [เว็บไซต์ทางการ](https://www.freecad.org/downloads.php) หรือ [release 1.1.4](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4) แล้วติดตั้ง/เปิดตามคำแนะนำของ FreeCAD ชุด 3117 นี้ไม่ได้รวม FreeCAD หรือ Qt มาด้วย
2. คลิกขวา ZIP ของ 3117 แล้วเลือก **Extract All / แยกทั้งหมด** เก็บทุกไฟล์ไว้ด้วยกัน เช่นใน Documents อย่าเปิด macro จากหน้าต่าง ZIP โดยตรง
3. เปิดโฟลเดอร์ที่แตกแล้ว ต้องพบ `Install_3117_BIM_Studio.FCMacro`, `Manage_3117_BIM_Studio.FCMacro`, `workbench`, `packaging`, `LICENSE` และไฟล์นี้
4. บันทึกและปิดเอกสารโมเดลทั้งหมด รวมทั้งปิด FreeCAD หน้าต่างอื่น ให้เหลือหน้าต่างที่ใช้รันตัวติดตั้ง

## 2. ติดตั้งด้วยเมนู FreeCAD

1. ใน FreeCAD เลือก **File → Open** แล้วเปิด `Install_3117_BIM_Studio.FCMacro` จากโฟลเดอร์ที่แตก ZIP หากไม่เห็นไฟล์ ให้เลือกชนิดไฟล์ Macro หรือ All files
2. เมื่อเห็นโค้ดในแท็บ macro ให้เลือก **Macro → Execute macro** หรือปุ่ม Execute macro บนแถบเครื่องมือ ไม่ต้องแก้ข้อความโค้ด
3. ถ้าถามหาโฟลเดอร์ ให้เลือกโฟลเดอร์ชุดติดตั้งที่มี `workbench` และ `packaging` อยู่ข้างใน วิธีนี้ใช้เมื่อ FreeCAD ไม่ส่งตำแหน่ง macro ให้ตัวช่วยโดยอัตโนมัติ
4. ตรวจชื่อรุ่นและตำแหน่งปลายทางในหน้าต่าง แล้วกด **Yes**
5. เมื่อแจ้งว่าติดตั้งไฟล์สำเร็จ ให้ปิด FreeCAD ทุกหน้าต่าง แล้วเปิดใหม่
6. เลือก **3117 BIM Studio** จากรายการ Workbench

ตัวติดตั้งใช้ตำแหน่งจริงจาก `FreeCAD.getUserAppDataDir()` และเพิ่ม `Mod/BIM3117` ให้เอง จึงไม่ต้องเดา AppData ของเครื่อง ไม่เขียนลง Program Files และไม่เปลี่ยน workbench อื่น

หากเปิดด้วย File → Open ไม่ได้ ให้ใช้ **Macro → Macros...** ตั้ง `User macros location` ชั่วคราวเป็นโฟลเดอร์ชุดติดตั้ง เลือก macro แล้วกด **Execute** จากนั้นคืนค่าตำแหน่ง macro เดิมของคุณได้

## 3. ทดลองหลังเปิดใหม่

1. เรียก **Host Information / ข้อมูลโปรแกรม** และเก็บข้อมูล FreeCAD/ระบบปฏิบัติการสำหรับรายงานผล
2. เรียก **Create Project** เพื่อสร้างโครงการทดสอบใหม่
3. ทดลอง **Add Level**, **Create Grid** และ **Edit Selected** ตามขอบเขต Foundation Workbench
4. เรียก **Create Wall Type** ตั้งชื่อ `W200` และ Thickness = `200` mm
5. เรียก **Create Wall** เลือก W200, Base Level = L00, Top Level = L01, Start X/Y = `0 / 0`, End X/Y = `6000 / 0`, offsets = `0`
6. เลือกผนังแล้วเรียก **Create Door** ตั้ง Offset = `1200`, Width = `900`, Height = `2100`, Sill = `0` mm จะเกิดกรอบประตูและช่องเปิดที่ตัดเนื้อผนังจริง Width/Height ในรุ่นนี้คือขนาดช่องตัดรวมกรอบ ไม่ใช่ขนาดบานหรือช่องผ่านสุทธิ
7. เปลี่ยน L01 เป็น `3300` mm ด้วย Edit Selected แล้วใช้ Undo/Redo ตรวจว่าผนังและช่องเปิดสัมพันธ์กัน
8. บันทึกด้วย **File → Save As** เป็น `.FCStd` ในโฟลเดอร์งานของคุณ แล้วปิดโปรแกรมทั้งหมดและเปิดกลับ
9. ตรวจว่าระดับ กริด ผนัง ประตู ค่า Properties และ UUID ของวัตถุยังอยู่ ทดลองแก้ Wall Type และ Undo/Redo หลังเปิดกลับ

รุ่นนี้รองรับผนังตรงหนาสม่ำเสมอและช่องเปิดสี่เหลี่ยมที่ไม่ซ้อนกัน รวม Plan/Section/Elevation และ Sheet A3 ตามขอบเขตด้านล่าง ยังไม่รวม wall-wall joins และการอ่าน/แก้ไฟล์ RVT/RFA ส่งออก IFC4 จาก native model ได้ผ่าน Quantities & Exchange เมื่อ host มี IfcOpenShell ที่เข้ากัน ส่วน reference core ยังคงเป็น package แยก

ใช้ **`Run_3117_Types_Test.FCMacro`** เพื่อตรวจ Catalogue/Materials/Schedules และ `Run_3117_Smoke_Test.FCMacro` เพื่อตรวจ Foundation, `Run_3117_Architecture_Test.FCMacro` เพื่อตรวจ Wall/Door, `Run_3117_Exchange_Test.FCMacro` เพื่อตรวจปริมาณ/CSV/IFC, `Run_3117_Building_Test.FCMacro` เพื่อตรวจองค์ประกอบ/รอยต่อ และ **`Run_3117_Drawings_Test.FCMacro`** เพื่อตรวจแบบ/แผ่นแบบ ผ่านหน้าต่างจริง ชุดทดสอบสร้างเอกสารตัวอย่างใหม่ รายงานและภาพอยู่ใน `BIM3117_Test_Reports` ภายใน user data directory ของ FreeCAD พร้อมแสดงตำแหน่งเมื่อจบ อ่านข้อความผลทดสอบก่อนสรุปว่าผ่าน; การติดตั้งสำเร็จเพียงอย่างเดียวไม่ใช่ผลทดสอบโมเดล

ตัวอย่างสำเร็จอยู่ที่ `examples/freecad/Architecture_Workbench.FCStd` เปิดหลังติดตั้งและ restart แล้วเท่านั้น รายละเอียดพารามิเตอร์และกฎพิกัดอยู่ใน `docs/WALL_DOOR_WORKBENCH.md`

### ทดลอง Building Authoring

เริ่มจาก `examples/building/Building_Authoring_Workbench.FCStd` เพื่อดูอาคารสองชั้นครบหมวด หรือทดลองเองในโครงการใหม่:

1. เรียก **Create Slab** เลือก L01, Thickness `150` mm, Offset `0` และขอบสี่เหลี่ยม 6000 × 4000 mm ผิวบนอยู่ Z=3000 และท้องพื้นอยู่ Z=2850 mm
2. เรียก **Create Column** เลือก L00 → L01 กำหนดศูนย์กลาง `1000 / 1000`, หน้าตัด `300 / 300` mm
3. เรียก **Create Beam** เลือก L01 แนว `0 / 2000` → `6000 / 2000`, Width `300`, Depth `450` mm
4. ใช้ **Join Slab** ผูกคานหรือเสากับพื้น รอยต่อหักเนื้อจากสมาชิกโดยพื้นคงเต็ม กด Undo/Redo แล้วตรวจ reference และ Net Volume
5. เปลี่ยน Thickness เป็น `200` mm แล้วตรวจว่าท้องพื้นต่ำลงและปริมาตรสุทธิสมาชิกเปลี่ยน ใช้ **Unjoin Slab** เพื่อคืนสมาชิกเต็ม
6. เลือก Wall แล้ว **Create Window** กำหนด Offset/Width/Height/Sill ให้ไม่ซ้อน Door จะเกิดช่องเปิดจริงและกรอบสี่ด้าน
7. Save/ปิดทุกหน้าต่าง/เปิด FCStd กลับ แล้วทดลองแก้ระดับหรือความหนาและ Undo ต่อ

Slab รองรับ polygon เว้าแต่ไม่มีรู, Column เป็นเสาตั้งตรงสี่เหลี่ยม และ Beam อยู่แนวนอน รอยต่อจำกัดเฉพาะ Slab ตัด Column/Beam ต้องเหลือ solid เดียว; ไม่ตัดขาดหรือตัดหมด Window ไม่มีบาน/กระจก อ่านพิกัดและกฎปริมาณใน [BUILDING_AUTHORING.md](../docs/BUILDING_AUTHORING.md)

### ทดลองปริมาณและ IFC

เปิด **Quantities & Exchange** หลังสร้างโมเดลจะมีแท็บ Walls, Doors, Slabs, Columns, Beams, Windows และ Coverage คลิกแถวเพื่อเลือกวัตถุต้นทาง กด Export CSV หรือ Export IFC4 ตรวจรายการที่ไม่รวมและเลือกปลายทาง ไฟล์ metadata ข้างผลส่งออกมี UUID, content revision, กฎ/หน่วย, coverage และ hashes เมื่อแก้โมเดล ผลส่งออกเก่าจะแสดง Stale ในหน้าต่างนี้และต้องส่งออกใหม่

ตัวอย่างสองชั้นครบชุดอยู่ใน `examples/building/` และตัวอย่าง Wall/Door รุ่นก่อนอยู่ใน `examples/exchange/` พร้อม native FCStd, IFC และ CSV จากโมเดลเดียวกัน รายละเอียดอยู่ใน `docs/QUANTITY_EXCHANGE.md` หากไม่มี IfcOpenShell ใน runtime ของ FreeCAD ปริมาณและ CSV ยังใช้ได้ โดย IFC จะแสดงคำอธิบาย dependency ชุด 3117 ไม่ติดตั้ง pip หรือ Qt เพิ่มเอง

### ทดลองแบบและแผ่นแบบ

เปิด `examples/drawings/Drawings_Workbench.FCStd` เลือก Sheet A101 ใน Drawing Set แล้วกด Drawing Preview หรือดับเบิลคลิก Sheet ดูแปลน L00/L01 สเกล 1:50 บน A3 แนวนอน จากนั้นเลือก A201 เพื่อดูรูปตัด/รูปด้าน ใช้ล้อเมาส์ซูม ลากเพื่อเลื่อน และ Fit เพื่อดูทั้งแผ่น

เลือก View แล้ว Edit Selected เพื่อเปลี่ยน Cut/Top/Bottom หรือ Scale; เลือก Slab/Level เพื่อเปลี่ยนโมเดล แล้วตรวจการอัปเดตของแบบพร้อม Undo/Redo กด Export PDF/SVG เพื่อส่งแผ่นปัจจุบันและ metadata หากแบบไม่พอดีต้องเปลี่ยนสเกลหรือ View ด้วยตนเอง โปรแกรมไม่ลดสเกลเอง พิมพ์ PDF ด้วย Actual size / 100% ดู [DRAWINGS_AND_SHEETS.md](../docs/DRAWINGS_AND_SHEETS.md) สำหรับขอบเขตและ API

## 4. อัปเดตรุ่นและคืนรุ่นเดิม

แตก ZIP รุ่นใหม่ในโฟลเดอร์แยก แล้วรัน Install macro ตามเดิม ตัวช่วยจะย้ายชุดเดิมที่มี installation identity ของ 3117 ไปเก็บใน `BIM3117_Backups` ซึ่งอยู่ข้างโฟลเดอร์ Mod และติดตั้งรุ่นใหม่แทน สำรองอยู่นอก Mod เพื่อไม่ให้ FreeCAD โหลด workbench ซ้ำ

v0.5.0 เพิ่ม Material/ElementType และ Schedule schema 1 บน native schema 1 ไฟล์ที่เพิ่มข้อมูลเหล่านี้ต้องใช้ v0.5.0 หรือรุ่นที่เข้ากัน ส่วน DrawingSet/View/Sheet ต้องใช้ v0.4.0 ขึ้นไป และ Slab/Column/Beam/Window ต้องใช้ v0.3.0 ขึ้นไป การ Restore Workbench เป็นรุ่นก่อนหน้าไม่ใช่การ downgrade ข้อมูลในไฟล์ `.FCStd`; เก็บสำเนาไฟล์โครงการก่อนทดลองคืนรุ่น

เมื่อต้องการคืนรุ่น:

1. บันทึกและปิดโมเดลทั้งหมด
2. เปิด `Manage_3117_BIM_Studio.FCMacro` จากชุดติดตั้ง แล้ว Execute
3. เลือก **คืนรุ่นจากสำรอง / Restore backup** แล้วเลือกรุ่นที่ต้องการ
4. รุ่นปัจจุบันจะถูกเก็บสำรองอีกชุด จากนั้นปิดและเปิด FreeCAD ใหม่

**กรณีเคยคัดลอก v0.0.1 ด้วยมือ:** ถ้าโฟลเดอร์ `Mod/BIM3117` ไม่มี installation identity ตัวช่วยจะหยุดเพื่อไม่ทับไฟล์ที่ไม่ทราบเจ้าของ ให้ปิด FreeCAD แล้วย้ายโฟลเดอร์เดิมไปเก็บในโฟลเดอร์สำรองนอก `Mod` ด้วยตนเองก่อนติดตั้งรุ่นนี้ อย่าเพียงเปลี่ยนชื่อโฟลเดอร์ภายใน Mod เพราะ FreeCAD อาจยังโหลดโค้ดชุดเดิม

## 5. ถอนการติดตั้ง

เปิดและ Execute `Manage_3117_BIM_Studio.FCMacro` เลือก **ถอนการติดตั้งและเก็บสำรอง / Uninstall** จากนั้นปิดและเปิด FreeCAD ใหม่

ตัวช่วยย้ายเฉพาะ workbench 3117 ที่ยืนยัน identity ได้ออกจาก Mod ไปไว้ในสำรอง ไม่ลบไฟล์โครงการหรือสำรอง หากต้องกลับมาใช้ ให้ใช้ Restore backup ไฟล์ `.FCStd` ที่มีวัตถุ 3117 ต้องมี workbench รุ่นที่เข้ากันเพื่อแก้ไขและคำนวณซ้ำ

## 6. เมื่อพบปัญหา

| อาการ | วิธีดำเนินการ |
| --- | --- |
| ไม่พบ Workbench หลังติดตั้ง | ปิด FreeCAD ทุกหน้าต่างแล้วเปิดใหม่ ดู **View → Panels → Report view** และบันทึกข้อความผิดพลาด |
| ถามหาโฟลเดอร์ชุดติดตั้ง | เลือกโฟลเดอร์ที่แตก ZIP แล้ว ซึ่งมี workbench และ packaging ห้ามเลือกไฟล์ ZIP หรือเลือก workbench ชั้นใน |
| แจ้ง folder is not owned | เก็บโฟลเดอร์เดิมนอก Mod ก่อนตามข้อ 4 ตัวช่วยจะไม่เขียนทับโฟลเดอร์ที่ยืนยัน identity ไม่ได้ |
| แจ้ง linked paths | ชุดติดตั้งหรือปลายทางเป็น symlink/junction ให้แตกชุดติดตั้งในโฟลเดอร์ปกติ; ไม่เปลี่ยนการตั้งค่าระบบอัตโนมัติ |
| แจ้ง another installer / lock | ปิดตัวติดตั้งและ FreeCAD หน้าต่างอื่น หากยืนยันว่าไม่มีตัวติดตั้งทำงานแล้ว ให้ตรวจไฟล์ `BIM3117-install.lock` ใน user data directory ก่อนลบเฉพาะ lock ที่ค้างแล้วลองใหม่ |
| สิทธิ์เขียนไม่พอหรือไฟล์ถูกล็อก | ตรวจว่าเปิด FreeCAD ด้วยบัญชีผู้ใช้ปกติและปิดเอกสาร/หน้าต่างอื่น ไม่ต้องเปลี่ยนสิทธิ์ทั้ง AppData หรือ Program Files |
| IFC unavailable | ใช้ FreeCAD baseline ที่มี IfcOpenShell เข้ากัน อ่านข้อความ dependency ใน Quantities & Exchange; ไม่ติดตั้ง PySide/Qt อีกชุดทับ host |
| Drawing does not fit | เพิ่ม Scale denominator เช่น 50 เป็น 100, ใช้หนึ่ง View ต่อ Sheet หรือปิดแท็ก/มิติที่ไม่ต้องการตามคำอธิบาย; ตรวจ layout ใหม่ก่อนส่งออก |
| Drawing source changed / Stale | จบคำสั่งแก้ไข กด Update และตรวจ model/drawing revisions ก่อนส่งออกใหม่ |
| Join ทำให้สมาชิกหาย/ขาด | ลดขอบเขตตัวตัดหรือใช้ Unjoin; รุ่นนี้ต้องเหลือ solid เดียวที่มีปริมาตรบวก |
| Export stale / model changed | จบหรือยกเลิกคำสั่งแก้ไข กด Refresh แล้วทบทวน Coverage ก่อนส่งออกใหม่ |
| Export lock | ตรวจว่ามี export อื่นทำงานหรือ process เดิมหยุดค้าง ตรวจ payload hashes/metadata และ backup ก่อนลบ lock ที่ค้าง |
| รุ่น FreeCAD ไม่ใช่ 1.1.4 | บันทึก build ที่ใช้ ผลทดสอบของรุ่นหนึ่งไม่รับรองรุ่นอื่นโดยอัตโนมัติ |

แหล่งข้อมูล: [FreeCAD 1.1.4 released](https://blog.freecad.org/2026/09/28/freecad-1-1-4-released/), [การรัน macro](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/How_to_install_macros.md), [Python scripting tutorial](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Python_scripting_tutorial.md) ตรวจสอบ 2026-10-23; repository เอกสารเก่าเป็น archived จึงต้องตรวจเมนูใน host ที่ใช้งานจริงด้วย

## Types, Materials และ Schedules

เปิด `examples/types/Types_Quantities_Workbench.FCStd` แล้วใช้ **Type Catalogue** และ **Schedules** ในกลุ่มเครื่องมือปริมาณ ตัวอย่างมี 33 products, 6 Types, 7 Materials และ 9 Schedules เลือก Type แล้ว Edit เพื่อเปลี่ยนทุกสมาชิกหรือ Duplicate เพื่อแยกชนิดใหม่; ขนาดที่ถูก Type ควบคุมจะ read-only ที่ Instance ส่วนวัสดุ/ชั้นวัสดุแก้ผ่าน Catalogue

เลือก Schedule แล้ว Refresh, Filter หรือ Group ใช้ Select Source เพื่อเลือกชิ้นส่วนตาม UUID และ Edit Row เพื่อแก้ข้อมูลต้นทาง ค่าปริมาณคำนวณเป็น read-only และการแก้แถว/Export ต้องตรงกับทั้ง model revision และ schedule revision ปริมาณวัสดุเป็นการแบ่งปริมาณชิ้นส่วน ไม่บวกซ้ำกับ product totals รายละเอียดอยู่ใน [Types and Quantities](../docs/TYPES_AND_QUANTITIES.md)

ไฟล์ที่เพิ่ม native Material/ElementType/Schedule ต้องใช้ v0.5.0 หรือรุ่นที่เข้ากัน รุ่นใหม่เปิดไฟล์เก่าได้ตาม fixture ที่ทดสอบ แต่การย้อนติดตั้ง Workbench เก่าไม่ใช่การ downgrade schema ของ FCStd Windows installation/GUI ยังต้องตรวจตาม [Windows acceptance](../docs/WINDOWS_ACCEPTANCE.md)
