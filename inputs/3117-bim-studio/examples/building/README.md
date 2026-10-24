# Building Authoring — โมเดลตัวอย่าง v0.3.0

ชุดนี้เป็นอาคารสังเคราะห์สองชั้นสำหรับตรวจ Slab/Column/Beam/Window, รอยต่อที่กำหนด, native quantities และ IFC4 ติดตั้ง 3117 BIM Studio v0.3.0 แล้ว restart FreeCAD ก่อนเปิด `.FCStd`

## ไฟล์ในชุด

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| Building_Authoring_Workbench.FCStd | โมเดล native พร้อมการแสดงผลใน GUI; ข้อมูลหลักที่ใช้แก้ไข |
| Building_Authoring_Workbench.ifc | IFC4 จาก UUID/revision เดียวกัน เปิดตรวจใน Bonsai แล้ว |
| Building_Authoring_Workbench.csv | Wall quantity rows |
| *_doors / *_slabs / *_columns / *_beams / *_windows.csv | ตารางหมวดอื่น หน่วย SI |
| *_csv_metadata.json / *_ifc_metadata.json | Snapshot, coverage, rules, readback results และ payload hashes |
| building-snapshot.json | ข้อมูลอ่านออกจาก native model; ไม่ใช่ไฟล์ master สำหรับแก้โมเดล |
| Building_Authoring_Workbench.png | ภาพ FreeCAD จริงพร้อมตารางปริมาณ |
| Bonsai_Building_Authoring.png | ภาพจากการเปิด IFC ใน Bonsai จริง |

## พิกัดและปริมาณตรวจได้

Levels อยู่ที่ 0 / 3000 / 6000 mm พื้นแต่ละแผ่นมีขอบจาก (-250,-250) ถึง (6250,4250) mm ขนาด 6.5 × 4.5 m, หนา 150 mm ลงจากระดับผิวบน

| หมวด | จำนวน | ปริมาตรสุทธิรวม (m³) | กฎ |
|---|---:|---:|---|
| Slab | 3 | 13.1625 | 29.25 m² × 0.15 m ต่อแผ่น; ไม่มีการหักสมาชิก |
| Column | 8 | 2.0520 | 0.30 × 0.30 × (3.00−0.15) m ต่อเสา หลังตัดด้วยพื้นยอด |
| Beam | 8 | 3.6000 | คานยาว 6 m จำนวน4 และ4 m จำนวน4; 0.30 × (0.45−0.15) m หลังตัดพื้น |
| Wall | 8 | 17.2680 | หนา0.20 m, สูง2.55 m; หักช่องประตู/หน้าต่างจริง |
| Door frame | 2 | 0.1000 | กรอบสามด้าน ช่องรวม0.90 × 2.10 m |
| Window frame | 4 | 0.1840 | กรอบสี่ด้าน ช่องรวม1.20 × 1.20 m, sill0.90 m |

Slab เก็บเนื้อเต็มและตัดส่วนที่ซ้อนกับ Column/Beam ที่อ้างอิงมัน การทับ Beam–Column, Wall–Wall หรือ Wall–Slab ยังไม่ถูกหักโดยอัตโนมัติ จึงอ่านผลรวมรายหมวดตามกฎที่ระบุ ตัวอย่างไม่มีการคำนวณกำลังรับน้ำหนัก บันไดหรือการออกแบบรายละเอียดงานก่อสร้าง

## ทดลองแก้แล้วตรวจผล

1. เลือก S01 เปลี่ยน Thickness จาก150เป็น200 mm ผิวบนยังที่3.00 m แต่ท้องพื้นย้ายจาก2.85เป็น2.80 m
2. Beam/Column ชั้นล่างที่ Join กับ S01 คำนวณรูปทรงและ Net Volume ใหม่ แล้วใช้ Undo/Redo คืน/ทำซ้ำ
3. เลือก Window แล้วแก้ Offset หรือ Host ช่องเดิมถูกปิดและช่องใหม่ถูกสร้างใน transaction เดียว ระบบปฏิเสธการซ้อน Door/Window
4. เปิด Quantities & Exchange เลือกแถวกลับไปยังวัตถุ ส่ง CSV/IFC และตรวจ content revision
5. Save เป็นชื่อใหม่ ปิดและเปิด FreeCAD ใหม่ แล้วแก้ระดับ/ความหนาต่อ

Content revision ของชุดที่ส่งมอบ:

`6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a`

IFC SHA-256:

`775b5a63592d05c63c14fb63d258d6a30ae45558d6d6f244cf75f387279ac609`

สี การซ่อนแสดง กล้อง และตำแหน่งไฟล์ไม่เปลี่ยน authored revision จึงจัดการแสดงผลของ FCStd ได้โดยคง identity เดียวกับ CSV/IFC อ่านผลจริงใน [Verification](../../docs/VERIFICATION.md) และ [Bonsai review](../../docs/BONSAI_BUILDING_REVIEW.md)
