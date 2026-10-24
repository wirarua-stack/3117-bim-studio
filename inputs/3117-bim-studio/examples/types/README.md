# Types and Quantities example — v0.5.0

**Development candidate:** FreeCAD 1.1.4 Linux มี native crash ในลำดับสร้าง–ลบ–Undo สองครั้ง–แก้ไขใหม่–Undo/Redo ซึ่งทำซ้ำได้โดยไม่มี 3117 เกณฑ์ Pilot/production ยังไม่ผ่าน และ Windows ยังรอตรวจรับ ทดลองกับสำเนาที่บันทึกไว้ รายละเอียดและ repro อยู่ใน `docs/HOST_COMPATIBILITY.md` ของ FreeCAD ZIP / Source ZIP รุ่นเดียวกัน

ตัวอย่างอาคารสองชั้นสังเคราะห์สำหรับ 3117 BIM Studio บน FreeCAD 1.1.4 เพิ่ม Type Catalogue, วัสดุและ Schedule ลงในสำเนา `Drawings_Workbench.FCStd` รุ่น v0.4.0 โดยคง UUID และขอบเขต solids ของชิ้นส่วนเดิม 33 ชิ้น

- `Types_Quantities_Workbench.FCStd`: ข้อมูลหลักที่เปิดแก้ไขได้ พร้อม 6 Types, 7 Materials, 9 Schedules, 4 Drawing Views และ 2 Sheets
- `Types_Quantities_Workbench.ifc` และ `_ifc_metadata.json`: IFC4 snapshot จาก native revision ที่ระบุ พร้อมชนิด/วัสดุ/ชั้นวัสดุจริง
- `Types_Quantities_Workbench.csv`, `_doors`, `_slabs`, `_columns`, `_beams`, `_windows`, `_types`, `_materials`: CSV ทั้งโมเดล พร้อม `_csv_metadata.json`
- `Wall_Schedule.csv` และ Schedule CSV อื่นรวม 9 ชุด: ตารางตาม Category และ Material breakdown พร้อม `_schedule_metadata.json` ของแต่ละชุด
- `types-snapshot.json`: snapshot อ้างอิงที่อ่านจาก FCStd; ไม่ใช้เป็น editable master
- `types-example.json`: แหล่งที่มา, hashes, UUIDs และผลตรวจ geometry ที่คงเดิม
- `build_example.py`: สร้างตัวอย่างใหม่ใน FreeCAD จาก frozen v0.4.0 source; ไม่เขียนทับ destination ที่มีอยู่

ติดตั้ง Workbench รุ่น v0.5.0 แล้วปิด/เปิด FreeCAD ก่อนเปิด FCStd ใช้ Type Catalogue แก้ชนิดร่วม และ Schedules เลือกตาราง/ชิ้นส่วนหรือ Edit Row การเปลี่ยน Type แก้ขนาดของสมาชิกทั้งหมด; ใช้ Duplicate Type เมื่อต้องการชนิดใหม่และ Undo/Redo เพื่อตรวจย้อนกลับ

Wall 200 ประกอบด้วย Plaster 15 + Masonry 170 + Plaster 15 mm เรียงไปทาง local +Y; Slab 150 เป็น Floor finish 10 + Screed 40 + Concrete 100 mm เรียงจากบนลงล่าง Column 300×300 และ Beam 300×450 ใช้ Concrete; Door/Window ใช้วัสดุของ generic frames ตามโมเดล ไม่ใช่ผลิตภัณฑ์ประตู/หน้าต่างที่มีรายละเอียดครบ

มี **55 material rows** ที่แจกแจงจาก **33 products** และ native material assignment ครบทั้ง 33 ชิ้น Material rows หักช่องเปิด/รอยต่อจาก solids แล้ว ไม่บวกซ้ำกับ product quantities; ไม่มีราคาหรือเผื่อสูญเสีย สิ่งนี้เป็นตัวอย่างทดสอบ ไม่ใช่ BOQ หรือแบบก่อสร้างที่รับรองแล้ว

Drawing definitions เดิมยังเปิด preview/export ได้ แต่ PDF/SVG ในโฟลเดอร์ `examples/drawings` เป็น output รุ่น v0.4.0 ที่มี model revision เดิม การส่งแบบของโมเดล typed รุ่นนี้ให้ export ใหม่จาก FCStd ปัจจุบัน

คู่มือ: [Types and Quantities](../../docs/TYPES_AND_QUANTITIES.md) · หลักฐานปัจจุบัน: [Verification](../../docs/VERIFICATION.md) · ขอบเขตแบบ: [Drawings and Sheets](../../docs/DRAWINGS_AND_SHEETS.md)
