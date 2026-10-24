# Drawings and Sheets — v0.4.0

รุ่นนี้เพิ่ม Plan, Section, Elevation และ Sheet เป็นวัตถุถาวรใน FreeCAD Document พร้อมหน้าต่างดูแบบและส่งออก SVG/PDF ใช้รูปทรง solid หลัง openings และ joins จากโมเดลเดียวกับ Quantity/IFC ผลการทดสอบที่รันจริงอยู่ใน [VERIFICATION.md](VERIFICATION.md) และ Windows desktop ยังมีขั้นตอนตรวจรับแยกใน [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md)

## 1. เริ่มจากตัวอย่าง

1. ติดตั้ง Workbench และปิด/เปิด FreeCAD ใหม่ตาม [คู่มือติดตั้ง](../packaging/INSTALL_TH.md)
2. เปิด `examples/drawings/Drawings_Workbench.FCStd` แล้วเลือก **3117 BIM Studio**
3. ขยายกลุ่ม Drawing Set เลือก Sheet `A101` แล้วกด **Drawing Preview** หรือดับเบิลคลิก Sheet
4. ตรวจแปลน L00/L01 บน A3 แนวนอน สเกล 1:50 ใช้ล้อเมาส์ซูม ลากเพื่อเลื่อน และ Fit เพื่อดูทั้งแผ่น
5. เลือก `A201` ในรายการ Sheet เพื่อดู Section A–A และ South Elevation
6. เปลี่ยน Thickness ของ Slab หรือแก้ Level ด้วย **Edit Selected** แล้วตรวจแบบที่อัปเดต พร้อมใช้ Undo/Redo
7. กด **Export SVG** หรือ **Export PDF** เลือกไฟล์ปลายทาง และตรวจรายการไฟล์กับ metadata ก่อนยืนยันการแทนที่

PDF/SVG เป็น snapshot ณ เวลาส่งออก เมื่อโมเดลหรือข้อกำหนดแบบเปลี่ยน ต้องส่งออกใหม่ พิมพ์ PDF ด้วย **Actual size / 100%** เพื่อคงสเกลที่ประกาศ การใช้ Fit to page ในโปรแกรมพิมพ์อาจเปลี่ยนสเกลได้

## 2. สร้างมุมมองและแผ่นแบบ

เมนู **3117 BIM → Drawings & Sheets / แบบและแผ่นแบบ** มี Create Plan, Create Section, Create Elevation, Create Sheet, Drawing Preview และ Export SVG/PDF บน toolbar มีคำสั่งสร้าง View, สร้าง Sheet และเปิด Preview เพื่อลดจำนวนปุ่มที่แย่งพื้นที่ 3D

เลือก View หรือ Sheet แล้วใช้ **Edit Selected** เพื่อแก้ทั้งชุดในหนึ่ง transaction การกด Cancel หรือส่งค่าที่ไม่ผ่าน preflight ไม่สร้าง transaction และไม่ทิ้ง state ที่แก้ครึ่งหนึ่ง ใช้ **3117 Delete Selected** เมื่อต้องการลบ View/Sheet; View ที่ Sheet ยังใช้อยู่และ Level ที่ Plan ยังอ้างอิงจะมี dependency guard

| วัตถุ | ข้อกำหนด |
|---|---|
| Plan | Level, Bottom/Cut/Top offsets, scale, สวิตช์มิติ/ชื่อชิ้นส่วน/Grid |
| Section | Origin XYZ, ทิศ cardinal, Depth, scale, สวิตช์มิติ/ชื่อชิ้นส่วน/Levels |
| Elevation | Origin XYZ, ทิศ cardinal, Depth และ annotation เช่นเดียวกับ Section |
| Sheet | Number ไม่ซ้ำ, Name, Issue, Author, View ที่เรียงลำดับ 1–2 มุมมอง |

ชื่อไม่ว่างและต้องเป็นบรรทัดเดียว Scale denominator เป็นจำนวนเต็ม 1–1000 เช่น 50 หมายถึง 1:50 หนึ่ง Sheet ใช้ View เดิมซ้ำสองช่องไม่ได้ แต่ View เดียวกันใช้ในหลาย Sheet ได้ หนึ่ง Project มี Drawing Set หนึ่งกลุ่ม

## 3. พิกัดและช่วงการมอง

### Plan

พิกัดโมเดลเป็น mm มองลงตามแกน −Z; ขวาบนแผ่นเป็น +X และขึ้นบนแผ่นเป็น +Y ระดับจริงของแต่ละระนาบเท่ากับ `Level.Elevation + Offset` ต้องมี `Bottom < Cut < Top` และแต่ละช่วงห่างอย่างน้อย 0.001 mm

- รูปทรงตั้งแต่ Bottom ถึง Cut ถูก clip แล้วฉายเส้นด้วย global hidden-line removal
- หน้าตัดตรง Cut เป็น loop ของ OCCT พร้อมรูจริง ใช้การเติมแบบ even-odd จึงไม่เติมทับช่องเปิด
- เส้นประเหนือระนาบตัดใช้เฉพาะชิ้นส่วนที่ขอบล่างทั้งชิ้นอยู่เหนือ Cut และมีเนื้อภายใน Top โดย clip ที่ Top จริง ไม่เพิ่มส่วนบนของผนังที่ถูกตัดซ้ำเป็น overhead
- ชิ้นส่วนที่สัมผัส Top แบบไม่มีปริมาตรภายในช่วงไม่ถูกเพิ่มเป็น overhead

ไฟล์ตัวอย่าง L00/L01 ใช้ Bottom −150, Cut 1200 และ Top 2800 mm จึงเห็นพื้น ผนัง/เสาที่ถูกตัด ช่องเปิดหน้าต่าง และคานด้านบน ค่าเริ่มต้นของฟอร์ม/API คือ −200 / 1200 / 2700 mm ซึ่งแก้ได้ การเพิ่ม Cut ให้สูงพ้นหน้าต่างจะเปลี่ยนรูปร่างแปลนตาม solid จริง

### Section และ Elevation

Origin เป็นจุดบนระนาบด้านหน้า Direction คือ **ทิศจากผู้ดูเข้าสู่โมเดล** เลือก +X, +Y, −X หรือ −Y ได้ Depth เป็นระยะบวกจากระนาบเข้าไป โมเดลที่อยู่นอกช่วงดังกล่าวถูก clip ออก แกนขึ้นเป็น +Z เสมอ

| Direction | แกนขวาบนแบบ | แกนขึ้น |
|---|---|---|
| +Y | +X | +Z |
| −Y | −X | +Z |
| +X | −Y | +Z |
| −X | +Y | +Z |

Section เติมหน้าตัดที่ Origin ส่วน Elevation แสดงเส้นฉายโดยไม่เติมหน้าตัด การใช้ Direction กลับด้านเปลี่ยนด้านที่เห็น ไม่ใช่เพียงกลับข้อความบนรูป

ตัวอย่าง Section A–A ใช้ Origin `(0, 2000, 0)`, +Y, Depth 3000 mm ส่วน South Elevation ใช้ `(0, -1000, 0)`, +Y, Depth 6000 mm ยังไม่มีเส้นแนวตัด/หัวลูกศร A–A เชื่อมอัตโนมัติบน Plan

## 4. รูปทรงและ annotation

Geometry มาจาก native solids ของ Slab/Column/Beam/Door/Window และ `Wall.Body.Shape` ของ Wall หลังหักช่องเปิด ระบบใช้ OCCT cut และ TechDraw global projection ไม่ใช้ภาพ viewport หรือ display mesh เป็นแบบ Source UUID ของหน้าตัดและแท็กผนังยังเป็น UUID ของ authored Wall ส่วนเส้นฉายรวมไม่ได้มี UUID แยกทุก segment

ซ่อนเส้นหลังวัตถุด้านหน้าในระดับทั้งมุมมองและตัดเส้นซ้ำ ชิ้นส่วนที่ถูกบังทั้งหมดไม่มีแท็กแสร้งว่ามองเห็น ที่มาของแท็กต้องผ่านการตรวจ visible source/first hit ของ native solid

| Annotation | ความสัมพันธ์กับโมเดล | ขอบเขตรุ่นนี้ |
|---|---|---|
| Overall dimensions | คำนวณ width/height ของ projected bounds สดทุกครั้ง | mm, มิติรวมแนวนอน/แนวตั้ง; ยังไม่ใช่เครื่องมือเลือกขอบเพื่อวาง dimension chain |
| Product tags | Label ปัจจุบัน + UUID + anchor ของ source ที่มองเห็น | วางด้านขวาของช่องพร้อม leader; ไม่มี text override แยกจากโมเดล |
| Grid markers | ตำแหน่ง/Label ของ native Grids | แสดงใน Plan และ clip กับช่องมุมมอง |
| Level markers | Elevation/ชื่อของ native Levels | แสดงใน Section/Elevation; ค่าระดับเป็น m บนสัญลักษณ์ |
| Scale bar | ความยาวสัมพันธ์กับ denominator ของแต่ละ View | หน่วย m แยกจากมิติอาคาร mm ชัดเจน |

มิติของตัวอย่างกว้าง 6500 mm รวมขอบพื้น 250 mm รอบแนวโครงสร้าง ไม่ใช่ระยะกริด 6000 mm รูปด้านสูงรวม 6150 mm เพราะพื้นล่างอยู่ต่ำกว่า L00 อีก 150 mm ค่าระดับ L00/L01/L02 ยังคง 0/3/6 m

รูปทรงที่รองรับในรุ่นนี้เป็น polyhedral ของผลิตภัณฑ์ 3117 ปัจจุบัน หากพบเส้นโค้งจะปฏิเสธพร้อมคำอธิบาย ไม่แปลงเป็นเส้นหลายท่อนโดยเงียบ ไม่มี hatch ตาม material layers, door swing symbol, glass/panel detailing หรือ 2D detail drafting

## 5. Layout, สเกล และฟอนต์

A3 แนวนอน 420 × 297 mm มีกรอบ 10 mm และ title block หนึ่ง View อยู่กลางพื้นที่ สอง View แบ่งสองช่องตามลำดับใน Sheet แต่ละ View กำหนดสเกลของตัวเอง หากรูปทรง/มิติหรือจำนวนแถวแท็กเกินพื้นที่ พรีวิว/ส่งออกจะปฏิเสธและให้แก้ denominator/annotation/รายการ View ไม่มีการลดสเกลลับหลังผู้ใช้ ข้อความยาวอาจลดขนาดภายในเกณฑ์หรือตัดแสดงพร้อมเครื่องหมายย่อ โดยเก็บชื่อเต็มไว้ใน metadata และ SVG title

SVG ใช้พิกัดกระดาษเป็น mm และ `viewBox="0 0 420 297"` เช่น ความยาว 6500 mm ที่ 1:50 ต้องเป็น 130 mm บนกระดาษ PDF วาดเวกเตอร์ด้วย QtSvg/QPdfWriter ของ FreeCAD ไม่ใช้ภาพ bitmap ของ viewport

Sarabun Regular/Bold ทำให้ชื่อภาษาไทยและละตินในแบบใช้ฟอนต์เดียวกัน ฟอนต์โหลดเฉพาะแอปจากไฟล์ที่แนบพร้อม [OFL notice](../workbench/bim3117_freecad/fonts/OFL.txt) และ [source/checksums](../workbench/bim3117_freecad/fonts/SOURCE.json) ไม่ต้องติดตั้ง Qt หรือฟอนต์ในระบบเพิ่ม SVG มีข้อมูลฟอนต์และข้อความ license อยู่ภายใน ส่วน PDF ฝังฟอนต์ที่ใช้บนหน้า การเปิด SVG ใน renderer อื่นยังควรตรวจรูปแบบข้อความของโปรแกรมนั้น

## 6. Native persistence และ revision สองชุด

`DrawingSet`, `DrawingView`, `DrawingSheet` เป็น native Python features พร้อม stable UUID อยู่ใน document เดียวกับ Project แต่ไม่อยู่ใน `Project.Group` เพื่อไม่ปะปนกับ authored building inventory Sheet link ไป View และ Plan link ไป Level เป็น dependency graph ทางเดียว

การบันทึก `.FCStd` เก็บข้อกำหนดแบบและความสัมพันธ์ หลังเปิดใน FreeCAD process ใหม่ proxy จะ restore และอ่านโมเดลใหม่ ภาพ SVG ใน Preview เป็น state ชั่วคราว ไม่สร้าง render-cache objects หรือ transaction เพิ่ม

| Revision | คิดจาก | ตัวอย่างที่ทำให้เปลี่ยน |
|---|---|---|
| `model_revision` | native authored model + building coverage ตาม snapshot เดิม | เปลี่ยน Level, Thickness, Label ของผลิตภัณฑ์, opening หรือ joins |
| `drawing_revision` | Sheet definition และ ordered referenced View definitions | เปลี่ยน Scale, Cut/Top/Bottom, Direction, Sheet Name/Issue, สวิตช์ annotation |

การเพิ่มหรือเปลี่ยน Drawing definitions ไม่เปลี่ยน hash ของโมเดลอาคารเดิม การ Undo กลับเนื้อหาเดิมให้ hash เดิม ไม่ใช่เลข history ที่เพิ่มขึ้นเสมอ `Level.Elevation` ไม่รวมใน drawing hash ซ้ำ เพราะ model hash รับผิดชอบอยู่แล้ว

Preview แสดง revision ทั้งสอง ตรวจ document events และอัปเดตหลัง transaction จบ ขณะกำลังแก้หรือมีปัญหาจะปิด export ของภาพเก่า เมื่อไฟล์ที่ส่งออกใน session เดียวกันมี revision ไม่ตรง จะแสดงว่า Stale ไฟล์นอก session ต้องตรวจ metadata กับ capture ปัจจุบันเอง

Drawing definitions ปรากฏเป็น reference/omitted ใน quantity/IFC Coverage ไม่มี IfcDrawing/IfcProduct แทน Sheet หากแบบมี reference เสีย จะบล็อกการเผยแพร่แบบนั้น แต่ยังส่ง Quantity/IFC ของอาคารที่ถูกต้องได้

## 7. Publication และ metadata

ส่งออกหนึ่งแผ่นได้สองชนิด:

- `A101.pdf` + `A101_pdf_metadata.json`
- `A101.svg` + `A101_svg_metadata.json`

Metadata มี source document, model/drawing hashes, native IDs, view definitions, projected geometry/provenance, layout/annotation policy, validation และ SHA-256/ขนาดของ payload ผลส่งออกไม่ใช่ editable model master

Exporter capture สดและตรวจ expected hashes ก่อนเริ่ม จากนั้นตรวจทั้งสอง hashes อีกครั้งก่อน publish หากโมเดลหรือแบบเปลี่ยนระหว่างทางจะไม่เผยแพร่ไฟล์ใหม่ ระบบใช้ publisher ฐานเดียวกับ CSV/IFC: ล็อกปลายทาง, atomic replace **รายไฟล์**, metadata เป็น completion marker ตัวท้าย และคืนไฟล์เก่าเมื่อจับ failure ได้ ไม่รับรอง crash-atomic พร้อมกันทั้ง bundle ตรวจ payload hash ก่อนใช้ผลจากการส่งออกที่ถูกขัดจังหวะ

PDF readback ภายในตรวจ header/trailer, จำนวนหน้า, A3 MediaBox, ไม่มี raster image objects และมี embedded font program การ render ตรวจหน้ากระดาษจริงและตรวจสเกลเป็น release gate เพิ่มเติม ไม่อ้างว่า readback นี้เป็น PDF conformance validator ทั่วไป

## 8. Python API ใน FreeCAD

ตัวอย่างนี้ใช้ Project/Level ที่มีอยู่แล้วใน active document และบันทึกทุกคำสั่งเปลี่ยนแปลงผ่าน native transactions:

```python
import FreeCAD as App
from bim3117_freecad import services, drawings, drawing_export

project = next(o for o in App.ActiveDocument.Objects
               if getattr(o, "BIM3117Kind", "") == "Project")
level = services.list_levels(project)[0]
plan = drawings.create_view(
    project, "API Demo Plan", view_type="Plan", level=level,
    bottom_offset_mm=-200, cut_offset_mm=1200, top_offset_mm=2700,
    scale_denominator=50)
sheet = drawings.create_sheet(
    project, "API Demo Sheet", "API-001", [plan], issue="P01",
    author="3117 BIM Management")
captured = drawings.capture_sheet(sheet)
drawing_export.export_sheet(
    sheet, "/absolute/output/API-001.pdf", format="pdf", overwrite=False,
    expected_model_revision=captured["model_revision"],
    expected_drawing_revision=captured["drawing_revision"])
```

PDF API ต้องมี host Qt GUI application; ใช้งานจาก FreeCAD GUI ตามปกติ SVG/native definition ใช้ใน FreeCADCmd ได้ `capture_sheet` ไม่ยอมรับ DTO ภายนอกแทน native snapshot ผู้เรียกต้องส่ง Sheet จริง `sheet_state(sheet)` อ่าน revision โดยไม่ทำ projection; `capture_view(view)` ให้ geometry ของ View สำหรับ inspection แต่ publication ต้องผ่าน `capture_sheet` และ exporter ที่มีการตรวจ state หลัง projection

API อื่น: `edit_view`, `edit_sheet`, `delete_view`, `delete_sheet`, `list_views`, `list_sheets`, `get_drawing_set`, `view_dependents`, `validate_drawing_object` Invalid proposals ตรวจล่วงหน้าก่อนเริ่ม transaction เพื่อรักษา Redo ที่ค้างอยู่; การแก้ raw Properties ของ host ใช้ callback/rollback ของ host และไม่อ้างว่า native editor ทุกเส้นทางรักษา Redo ได้เหมือน service preflight

## 9. ขอบเขตที่ยังเป็นงานถัดไป

ยังไม่มี arbitrary camera/oblique section, curved geometry drawing, crop polygons, custom sheet sizes/templates, manual viewport placement, chained/reference-edge dimensions, editable annotation text master, symbol/detail libraries, section-callout linking, multi-page batch publisher, schedule placement on sheets หรือ TechDraw DrawPage editing โดยตรง Native definitions ของ 3117 ใช้ OCCT/TechDraw เป็น geometry engine และ host Qt เป็น sheet renderer

อัปเดต v0.5.0: [Types and Quantities](TYPES_AND_QUANTITIES.md) เพิ่มแล้วตามขอบเขตของรุ่นนี้: catalogue ของชนิดใหม่, material layers, schedules และกฎปริมาณ โดยคง model authority/transactions/revision เดิม ดู [ROADMAP.md](ROADMAP.md)
