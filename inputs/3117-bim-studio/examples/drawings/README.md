# Drawings and Sheets example — v0.4.0

โมเดลตัวอย่างสังเคราะห์สำหรับตรวจ Workbench 3117 ใน FreeCAD 1.1.4 หลังติดตั้งและ restart ให้เปิด `Drawings_Workbench.FCStd` ขยาย **3117 Drawings** แล้วดับเบิลคลิก Sheet หรือตามเมนู **Drawing Preview**

| Sheet | View ซ้าย | View ขวา | กระดาษ / สเกล |
|---|---|---|---|
| A101 — Floor Plans | Ground Plan / L00 | Upper Plan / L01 | A3 แนวนอน, ทั้งสอง View 1:50 |
| A201 — Section and Elevation | Section A–A, +Y จาก Y=2000 | South Elevation, +Y จาก Y=−1000 | A3 แนวนอน, ทั้งสอง View 1:50 |

Plan ใช้ Bottom −150 / Cut 1200 / Top 2800 mm จาก Level ส่วน Section มี Depth 3000 mm และ Elevation มี Depth 6000 mm ค่าเหล่านี้เก็บใน native View และแก้ด้วย **Edit Selected** ได้

## ไฟล์หลัก

- `Drawings_Workbench.FCStd`: editable native model และ 4 View / 2 Sheet definitions
- `3117_A101.pdf`, `3117_A201.pdf`: เวกเตอร์ PDF หนึ่งแผ่นต่อไฟล์ พร้อมฟอนต์ไทย/ละตินที่ฝังไว้
- `3117_A101.svg`, `3117_A201.svg`: self-contained vector sheets พร้อม Sarabun/OFL
- `*_pdf_metadata.json`, `*_svg_metadata.json`: source IDs, model/drawing revisions, layout, กฎ annotation และ payload hashes
- `drawings-example.json`: identity/provenance ของโมเดลตัวอย่าง
- `drawings-export-report.json`: ผลตรวจ publication ของทั้งสอง Sheet
- `Drawings_Workbench.png`, `A101_FreeCAD_Preview.png`, `A201_FreeCAD_Preview.png`: ภาพจากโปรแกรม FreeCAD จริง
- `build_example.py`: สคริปต์สำหรับสร้างตัวอย่างใหม่จาก frozen Building fixture ผ่าน installed Workbench; ไม่ใช้สร้างทับตัวอย่าง canonical โดยเงียบ

Native source ใช้โมเดล Building Authoring เดิม: Levels 0/3/6 m, 3 Slabs, 8 Columns, 8 Beams, 8 Walls, 2 Doors, 4 Windows และ 4 Grids Drawing definitions อยู่แยกจาก authored Project group การเพิ่มแบบคง model revision เดิม:

`6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a`

มิติรวมใน Plan เท่ากับ 6500 × 4500 mm รวมขอบพื้นนอกแนวกริด ส่วนรูปตัด/รูปด้านสูง 6150 mm รวมพื้นล่างที่ยื่นลง 150 mm ที่สเกล 1:50 ความกว้างบนกระดาษเท่ากับ 130 mm พิมพ์ PDF ที่ **Actual size / 100%**

แก้ Thickness หรือ Level แล้วตรวจ Preview กับ Undo/Redo ก่อนส่งออกใหม่ Model revision เปลี่ยนตามโมเดล ส่วน Drawing revision เปลี่ยนตาม Scale/View range/Sheet definition PDF/SVG ที่ส่งออกไว้เป็น snapshot และไม่เปลี่ยนตามเอง

ชื่อชิ้นส่วนอ่านจาก Label/UUID ของ native object และมิติเป็นค่ารวมอัตโนมัติ รุ่นนี้ยังไม่มี annotation editor, dimension chain, section callout บน Plan หรือ schedule editor ตัวอย่างนี้ไม่ใช่แบบที่ผ่านการตรวจรับเพื่อก่อสร้าง

คู่มือ/API: [Drawings and Sheets](../../docs/DRAWINGS_AND_SHEETS.md) · ผลที่รันจริงและข้อจำกัด: [Verification](../../docs/VERIFICATION.md) · ฐานโมเดลอาคาร: [Building example](../building/README.md)
