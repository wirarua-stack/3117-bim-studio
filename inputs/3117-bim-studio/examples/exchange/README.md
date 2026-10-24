# ตัวอย่าง v0.2.1 — Quantity / Exchange Bridge

ชุดนี้เป็นโมเดลสังเคราะห์สำหรับตรวจการสร้างปริมาณและส่ง IFC จาก FreeCAD native document ไม่ใช่โมเดลลูกค้า

## เปิดและตรวจ

1. ติดตั้ง Workbench v0.2.1 แล้ว restart FreeCAD
2. เปิด [Quantity_Exchange_Workbench.FCStd](Quantity_Exchange_Workbench.FCStd)
3. เปิด Quantities & Exchange จะมี 3 Walls / 3 Doors ตรวจค่ากับ CSV ด้านล่าง
4. เปิด [Quantity_Exchange_Workbench.ifc](Quantity_Exchange_Workbench.ifc) ในโปรแกรมอ่าน IFC ที่รองรับ IFC4 ผลที่ทดสอบจริงคือ Bonsai ใน Blender บน Linux
5. แก้โมเดลแล้วส่งออกไปชื่อใหม่ ผลส่งออกเดิมเป็น snapshot ของ content revision ด้านล่าง

## ไฟล์ในชุดเดียวกัน

- [Wall CSV](Quantity_Exchange_Workbench.csv)
- [Door CSV](Quantity_Exchange_Workbench_doors.csv)
- [CSV metadata](Quantity_Exchange_Workbench_csv_metadata.json)
- [IFC metadata](Quantity_Exchange_Workbench_ifc_metadata.json)
- [Captured native snapshot](exchange-snapshot.json) — ผลอ่านของการทดสอบ ไม่ใช่ข้อมูลหลักสำหรับแก้ไข
- [Actual Bonsai screenshot](Bonsai_Native_IFC_Review.png)
- [Actual FreeCAD quantities screenshot](Quantity_Exchange_Fixture_GUI.png)

Content revision:

`31b79c638cc70358bb6d8fa92005a1922ca7fd248332650582ce19d636da6cf0`

IFC SHA-256 ที่ตรวจด้วย Bonsai และจัดส่งตรงกัน:

`a62ab703c0170ba9134d0c81ae0ba7932ab04d6ff7da6e44fc6fb01a005aac25`

## ตัวเลขตรวจรับ

ทุกผนังใช้ Type W200 หนา 0.20m ระดับ B01=-3.00m, L00=0.00m, L01=3.00m

| Wall | แนว/ตำแหน่ง | ความยาว (m) | สูงจริง (m) | ช่องเปิด W×H (m) | Net volume (m³) |
|---|---|---:|---:|---|---:|
| W201 | (0,0) → (6,0), Base L00 | 6.000 | 3.000 | 0.90×2.10 | 3.222 |
| Diagonal basement | (0,6) → (3,10), Base B01+0.10; Top L00-0.20 | 5.000 | 2.700 | 0.80×2.00, sill0.10 | 2.380 |
| Reversed wall | (6,4) → (2,4), Base L00 | 4.000 | 3.000 | 0.80×2.10 | 2.064 |
| **ผลบวกรายผนัง** | ไม่หักรอยต่อหรือการทับกันระหว่างผนัง | | | | **7.666** |

พื้นที่ผนังด้านเดียวรวมก่อนหักช่องเปิด 43.500m² หลังหักช่องเปิด 38.330m² จำนวนประตู3กรอบ Width/Height เป็นช่องตัดรวมกรอบ ไม่มีบาน/ทิศเปิด

Grid A ถูกระบุเป็น reference ใน coverage และไม่ส่งออก IfcGrid ส่วน WallBody ทั้ง3เป็น derived geometry ไม่นับเป็นผนังเพิ่ม

FCStd เป็นข้อมูลหลักสำหรับแก้ไข Snapshot JSON/CSV/IFC ไม่ได้เชื่อมแก้กลับอัตโนมัติ การเพิ่มสี/มุมกล้อง/view providers ในสำเนา GUI ไม่เปลี่ยน UUID หรือ content revision ของโมเดล

[วิธีใช้งานและขอบเขต](../../docs/QUANTITY_EXCHANGE.md) · [Verification](../../docs/VERIFICATION.md) · [Bonsai review](../../docs/BONSAI_REVIEW.md)
