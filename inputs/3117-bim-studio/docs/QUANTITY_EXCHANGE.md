# Quantity / Exchange — v0.2.1 foundation, v0.3.0 building categories

3117 BIM Studio อ่านปริมาณและส่งออก IFC4 จาก **FreeCAD Document / FCStd ที่กำลังเปิดอยู่** เอกสาร native ยังคงเป็นข้อมูลหลักเพียงชุดเดียว CSV, metadata JSON และ IFC เป็นผลส่งออกของรุ่นข้อมูลที่ระบุ ไม่มีการเขียนผลจากไฟล์เหล่านี้กลับเข้าโมเดลอัตโนมัติ

สถานะ: development candidate สำหรับ FreeCAD 1.1.4 ผลที่รันจริงและรายการที่ยังไม่ทดสอบอยู่ใน [VERIFICATION.md](VERIFICATION.md) การตรวจบน Windows ยังคงแยกจากผล Linux

## 1. เปิดตารางและส่งออก

1. ติดตั้ง Workbench และเริ่ม FreeCAD ใหม่ตาม [INSTALL_TH.md](../packaging/INSTALL_TH.md)
2. เปิดโครงการ 3117 หรือสร้างผ่านคำสั่งของ [Building Authoring](BUILDING_AUTHORING.md) / [Wall / Door Workbench](WALL_DOOR_WORKBENCH.md)
3. เลือก **Quantities & Exchange** ในเมนูหรือ toolbar `3117 Exchange`
4. อ่านแท็บ **Walls**, **Doors**, **Slabs**, **Columns**, **Beams**, **Windows** และ **Coverage** ตารางแก้ค่าตรง ๆ ไม่ได้ คลิกแถวเพื่อเลือกวัตถุต้นทาง แล้วใช้ Edit Selected หรือ Properties ที่รองรับ
5. เปิด Auto refresh เพื่อให้ตารางปรับหลังแก้ไขหรือ Undo/Redo ระหว่าง transaction หรือเมื่อโมเดลไม่ถูกต้อง ปุ่มส่งออกจะไม่พร้อมใช้
6. กด **Export CSV** หรือ **Export IFC4** ตรวจขอบเขตและรายการที่ไม่รวม แล้วเลือกชื่อไฟล์ หากมีไฟล์ผลลัพธ์หรือ sidecar อยู่แล้ว ต้องยืนยันการแทนที่ทั้งชุดที่แสดง

คำสั่ง Export IFC4 บน toolbar เปิดหน้าต่างนี้และขั้นตอนส่งออกให้โดยตรง หน้าต่างผูกกับเอกสารต้นทางแต่ละฉบับและถอด observer เมื่อปิดหน้าต่างหรือเอกสาร

## 2. Quantity rows

### Wall: หนึ่งแถวต่อ UUID ของผนังที่สร้าง

| ข้อมูล | ความหมาย |
|---|---|
| element_id | UUID ของ Wall; ชื่อเป็นข้อมูลที่แก้ไขได้ ไม่ใช้เป็นตัวตน |
| type_id / type_name | Type ที่ Wall อ้างอิง |
| base_level / top_level | ระดับอ้างอิงของผนัง |
| length_m / height_m / thickness_m | หน่วยเมตร โดยความสูงรวม Base/Top Offset แล้ว |
| gross_side_area_m2 | พื้นที่ด้านข้างผนังหนึ่งด้านก่อนหักช่องเปิด |
| opening_side_area_m2 | ผลรวมพื้นที่ช่องเปิดสี่เหลี่ยมที่ไม่ซ้อนกัน |
| net_side_area_m2 | พื้นที่ด้านข้างสุทธิจากปริมาตร native solid หารความหนา |
| gross_volume_m3 | ปริมาตรผนังตรงก่อนหักช่องเปิด |
| opening_volume_m3 | ปริมาตรที่หักออกจากผนัง |
| net_volume_m3 | ปริมาตรของ WallBody.Shape หลังตัดช่องเปิดจริง แปลง mm³ → m³ |
| quantity_rule | รหัสกฎ `3117.uniform-wall.one-side.openings.no-joins.v1` |
| content_revision | รหัสเนื้อหาโมเดลที่ใช้สร้างแถว |

WallBody เป็นรูปทรงผลลัพธ์ของ Wall ไม่สร้างแถวผนังอีกหนึ่งแถว ผลรวมเป็นผลบวกรายผนัง ยังไม่หักปริมาตรที่ทับกันตามรอยต่อ และยังไม่แยกวัสดุหลายชั้นหรืองานผิว

### Door: หนึ่งแถวต่อ Door ที่อ้าง Host

แถวประตูมี UUID, Host UUID/ชื่อ, Base Level, offset/width/height/sill หน่วยเมตร พื้นที่และปริมาตรช่องเปิด ปริมาตรกรอบทั่วไป และ Count = 1

**Width/Height คือขนาดช่องตัดผนังทั้งหมด รวมพื้นที่ของกรอบ** ไม่ใช่ขนาดบานหรือช่องเดินผ่านสุทธิ รูปทรงเป็นกรอบสามด้าน ความหนาแถบกรอบคือค่าน้อยที่สุดของ 50 mm, Width/4 และ Height/4 และลึกเท่าความหนาผนัง ไม่มีบานประตู ทิศเปิด หรือ Door Type ในรุ่นนี้ ปริมาตรกรอบใช้ตรวจรูปทรงตัวอย่าง ไม่ใช่รายการสั่งซื้อวงกบหรือ BOQ ที่คิดเผื่อแล้ว

### Slab / Column / Beam / Window ใน v0.3.0

Slab มี `gross_area_m2`, `net_area_m2`, `perimeter_m`, `thickness_m`, top Level/Offset, Material และ gross/net volume พื้นไม่มีรูหรือการหักรอยต่อในรุ่นนี้ ดังนั้น gross/net area และ volume เท่ากันตามกฎที่กำหนด

Column/Beam มีหน้าตัด ระดับ offsets, gross volume, `join_deduction_m3` และ actual `net_volume_m3` พร้อม `join_slab_ids` และ `join_count` เสามี rotation/height และคานมี start/end/length การตัดหลาย Slab คิด union ของส่วนซ้อน ไม่หักซ้ำบริเวณเดียวกัน

Window ใช้ row schema แบบ Door พร้อม Host และปริมาณช่องเปิด แต่กรอบมีสี่ด้าน ไม่มีบานหรือกระจก กฎแยกเป็น `3117.overall-opening.generic-four-bar-frame.v1`

หนึ่งแถวต่อ authored UUID ในแต่ละหมวด ไม่สร้าง quantity row เพิ่มจาก cutters, IFC openings หรือ derived WallBody ดูสัญญาพิกัดใน [BUILDING_AUTHORING.md](BUILDING_AUTHORING.md)

### หน่วยและการตรวจ geometry

FreeCAD ใช้ mm / mm² / mm³; snapshot และผลส่งออกใช้ m / m² / m³ โดยแปลงด้วย 1,000 / 1,000,000 / 1,000,000,000 ตามลำดับ ไม่อ่านจำนวนสามเหลี่ยมจาก viewport เพื่อคิดปริมาณ

ก่อนสร้าง snapshot จะตรวจ native references, recompute, ตรวจ solid และเทียบ material volume/ตำแหน่งกับ solid ที่สร้างชั่วคราวจากพารามิเตอร์ รวมถึง symmetric difference เพื่อปฏิเสธรูปทรงหรือช่องเปิดที่ถูกย้ายแต่มีปริมาตรเท่าเดิม รูปทรงสำหรับตรวจไม่ถูกเพิ่มเป็น object ในเอกสาร

## 3. Model content revision

`content_revision` เป็น SHA-256 จากข้อมูล authored ที่รองรับ ได้แก่ UUID, ชื่อ, metadata โครงการ, type, levels, grids, พิกัด/offset และ host links รวมถึงรายการ coverage ของเอกสาร เรียงข้อมูลก่อน hash เพื่อให้ผลซ้ำได้หลังบันทึกและเปิดใหม่

ตั้งแต่ v0.4.0 DrawingSet/View/Sheet เป็น reference/omitted ใน Coverage และถูกแยกออกจาก building hash เพื่อรักษา revision ของโมเดลเดิม ข้อกำหนดแบบใช้ `drawing_revision` แยกต่างหาก แบบที่มี reference เสียจะหยุดการเผยแพร่แบบนั้น แต่ไม่บล็อก Quantity/IFC ของอาคารที่ valid ดู [DRAWINGS_AND_SHEETS.md](DRAWINGS_AND_SHEETS.md)

- เปลี่ยนมิติ ระดับ Type, Host, ชื่อ หรือเพิ่ม/ลบวัตถุที่มีผลต่อรายการ coverage แล้ว revision เปลี่ยน
- Undo กลับเนื้อหาเดิมได้ revision เดิม จึงไม่ใช่เลขประวัติที่เพิ่มอย่างเดียว
- สี การซ่อน/แสดง กล้อง เวลา capture และชื่อเส้นทางไฟล์ไม่ทำให้ revision เปลี่ยน
- geometry ของวัตถุภายนอกที่ยังไม่รองรับไม่อยู่ใน hash; รายการชื่อ/ชนิด/ตัวตนของวัตถุนั้นอยู่ใน coverage และระบุว่าไม่รวมในการส่งออก
- revision นี้ไม่ใช่หมายเลขอนุมัติแบบ, CDE revision, digital signature หรือระบบแก้พร้อมกันหลายคน

หน้าต่างแสดงสถานะของผลส่งออกล่าสุดในหน้าต่างนั้นว่า Current หรือ Stale หลังแก้โมเดล ไม่ติดตามไฟล์ทั้งหมดบนดิสก์ย้อนหลังโดยอัตโนมัติ หลังเปิดโปรแกรมใหม่สามารถอ่าน revision ใน metadata แล้วเทียบกับ snapshot ใหม่ผ่าน API ได้

วัตถุใหม่เพิ่มข้อมูล authored และกฎของหมวดนั้นใน hash เฉพาะเมื่อมีวัตถุชนิดนั้น โมเดล v0.2.1 ที่ไม่ได้เพิ่มหมวดใหม่จึงคง content revision เดิม ส่วน row arrays ของหมวดใหม่มีอยู่เสมอ แม้เป็นรายการว่าง

## 4. ไฟล์ผลลัพธ์

| เลือกชื่อไฟล์ | ไฟล์ที่ได้ |
|---|---|
| `Project.csv` | `Project.csv` สำหรับ Walls, `Project_doors.csv` สำหรับ Doors, `Project_csv_metadata.json` |
| `Project.ifc` | `Project.ifc`, `Project_ifc_metadata.json` |
| มี Slab/Column/Beam/Window | เพิ่ม `Project_slabs.csv`, `Project_columns.csv`, `Project_beams.csv`, `Project_windows.csv` เฉพาะหมวดที่มีแถว |

ตัวอย่างครบทุกหมวดได้ CSV 6 ไฟล์และ metadata 1 ไฟล์ หากส่งออกครั้งถัดไปแล้วหมวดหนึ่งไม่มีวัตถุ ระบบไม่ลบ sidecar เก่าของหมวดนั้นเอง ให้ใช้รายการไฟล์และ hashes ใน metadata ปัจจุบันเป็นสมาชิกของชุดผลส่งออก

CSV เป็น UTF-8 พร้อม BOM เพื่อรองรับชื่อภาษาไทย ใช้ comma คั่นและจุดทศนิยม หัวคอลัมน์ระบุหน่วย ตัวเลขคงเป็นค่าตัวเลข ข้อความชื่อที่เริ่มเหมือนสูตร spreadsheet จะมี apostrophe นำหน้าเพื่อเก็บเป็นข้อความ ชื่อเดิมไม่ถูกแก้ในโมเดลและเก็บครบใน metadata

Metadata ประกอบด้วย snapshot, full content revision, หน่วย/กฎ, coverage, ผลตรวจ และ SHA-256 ของไฟล์ payload จึงตรวจได้ว่า CSV/IFC กับรายงานยังเป็นชุดเดียวกัน

ระบบล็อกทุกปลายทางที่กำลังส่งออก สร้างไฟล์ในโฟลเดอร์ชั่วคราว ตรวจผลก่อนเผยแพร่ และแทนที่ทีละไฟล์ด้วย atomic replace โดยเขียน metadata เป็นไฟล์สุดท้าย หากเกิดข้อผิดพลาดที่จับได้ระหว่างเผยแพร่ จะคืนไฟล์เดิมจาก backup หากคืนไม่สำเร็จจะแสดงโฟลเดอร์ backup และเก็บ lock ไว้ การปิด process/ไฟดับระหว่างแทนที่หลายไฟล์ยังไม่ใช่ crash-atomic transaction; ต้องเทียบ hashes ใน metadata ก่อนรับผลทั้งชุด

## 5. IFC4 mapping

| Native | IFC4 | ขอบเขต |
|---|---|---|
| Project | IfcProject + Site/Building containers | Site/Building สร้างเป็น container local ของโครงการเดียว ไม่อ้างพิกัดสำรวจ |
| Level | IfcBuildingStorey | รักษา signed elevation และใช้เป็น spatial containment |
| WallType | IfcWallType | ความหนา/ชื่อวัสดุ; material association ไม่มีการสร้างชั้นวัสดุที่ผู้ใช้ไม่ได้กำหนด |
| Wall | IfcWall | swept solid ตามแนว start → end และ +localY; Base/Top links อยู่ใน source properties |
| Door / Window opening | IfcOpeningElement | GlobalId สืบจาก authored UUID พร้อม IfcRelVoidsElement ไป Host |
| Door | IfcDoor | กรอบสามด้าน พร้อม IfcRelFillsElement และตำแหน่งที่สัมพันธ์กับ opening |
| Slab | IfcSlab(FLOOR) | Polygon extrusion ตาม top Level/Offset/Thickness |
| Column | IfcColumn | Rectangular vertical prism, rotation และ slab-priority boolean cuts |
| Beam | IfcBeam | Horizontal axis/section และ slab-priority boolean cuts |
| Window | IfcWindow | กรอบสี่ด้าน พร้อม IfcRelFillsElement และ Host placement |
| WallBody | derived | ใช้ตรวจ geometry/ปริมาณของ Wall และไม่ส่งออกเป็นผนังซ้ำ |
| Grid | reference | อยู่ใน FCStd/metadata แต่ยังไม่ส่งออก IfcGrid |
| วัตถุอื่น | unsupported | แสดงใน Coverage และไม่ส่งออกเงียบ ๆ |

Native UUID แปลงเป็น IFC GlobalId แบบคงที่ และ ID ของ container/relationships/property sets สร้างแบบ deterministic การเปลี่ยนชื่อหรือส่งออกซ้ำไม่เปลี่ยนตัวตนขององค์ประกอบเดิม

IFC ใช้ SI เมตรโดยระบุหน่วยความยาว พื้นที่ และปริมาตร พร้อม `Qto_WallBaseQuantities`, `Qto_SlabBaseQuantities`, `Qto_ColumnBaseQuantities`, `Qto_BeamBaseQuantities` และ `BIM3117_Source` สำหรับ source UUID/content revision ไฟล์ส่งออกเป็น snapshot; เปิดในโปรแกรมอื่นไม่ได้หมายความว่าจะรักษา FreeCAD transaction/history หรือ constraints ให้แก้กลับได้ครบ

## 6. Validation และ dependency

การส่งออก IFC อ่านไฟล์ที่เขียนจริงใน staging กลับก่อนแทนที่ปลายทาง ตรวจ schema, GUID, mapping counts, hierarchy, type assignment, spatial containment, placement, quantities, frame/wall/member volumes, native bounds, serialized profiles/cutters และจุดตรวจภายในช่องเปิด ถ้าไม่ผ่านจะไม่เผยแพร่ไฟล์ใหม่

IfcOpenShell เป็น dependency ทางเลือกจาก Python ของ FreeCAD ที่ใช้งานอยู่ หากไม่มีหรือโหลดไม่ได้ ปริมาณและ CSV ยังทำงาน พร้อมแสดงข้อความแก้ไขสำหรับ IFC ชุดติดตั้ง 3117 ไม่ลง pip, FreeCAD, IfcOpenShell หรือ Qt เพิ่มเอง

Runtime ที่ใช้ทดสอบต้องดูใน Verification; การทดสอบ full EXPRESS ใช้ตัวเลือก QA แยก เพราะ rule executor ของ upstream ต้องมี pytest ซึ่งอาจไม่มีใน FreeCAD ผลส่งออกปกติระบุ `express_rules.status = not_requested` อย่างตรงไปตรงมา การตรวจ schema อย่างเดียวไม่แทนการตรวจ geometry หรือการเปิดข้ามแอป

## 7. API สำหรับพัฒนาต่อ

รันภายใน FreeCAD ที่ติดตั้ง Workbench แล้ว:

```python
import FreeCAD as App
from bim3117_freecad import services, snapshot, exchange

project = services.get_project(App.ActiveDocument)
current = snapshot.capture(project)
print(current["content_revision"])
print(current["wall_rows"])
print(current["coverage"])

# Choose a real existing output directory. Default refuses to overwrite.
csv_result = exchange.export_csv(
    project, r"C:\BIM3117\Project.csv",
    expected_revision=current["content_revision"],
)
ifc_result = exchange.export_ifc(
    project, r"C:\BIM3117\Project.ifc",
    expected_revision=current["content_revision"],
)
print(snapshot.is_current(project, csv_result["content_revision"]))
```

`output_paths(path, format="csv", source=current)` ให้รายชื่อไฟล์ทั้งหมดตาม snapshot ที่แสดงอยู่ สำหรับตรวจการแทนที่ก่อนเรียก API ต้องส่ง `source` เมื่อต้องการรวม sidecar ของ Slab/Column/Beam/Window ที่มีข้อมูล หากไม่ส่ง `source` จะคงพฤติกรรมเดิมและให้เฉพาะ Wall/Door/metadata ส่วน IFC ใช้ `output_paths(path, format="ifc")` ได้ การส่งออกจะ recapture เอกสารสดเสมอ ไม่รับ snapshot ที่แก้ตัวเลขเองเป็น master ถ้า `expected_revision` ต่างจากปัจจุบันจะปฏิเสธให้ทบทวนผลก่อนส่งออก

ห้ามเปิด document transaction ครอบการอ่าน snapshot/export ต้องจบหรือยกเลิกคำสั่งแก้ไขก่อน การส่งออกไม่เพิ่มรายการ Undo และไม่เปลี่ยน parameters/UUID ของโมเดล

## 8. ขอบเขตถัดไป

v0.3.0 เพิ่ม Slab/Column/Beam/Window ตาม [BUILDING_AUTHORING.md](BUILDING_AUTHORING.md) และ v0.4.0 เพิ่มแบบ/แผ่นแบบตาม [DRAWINGS_AND_SHEETS.md](DRAWINGS_AND_SHEETS.md) แล้ว ส่วน arbitrary schedule columns/formulas, advanced material profiles/constituents, general join deductions, annotation/detail editor, IFC import/round-trip และหมวดอื่นยังเป็นงานต่อไป การเปิด IFC ใน Bonsai ที่บันทึกไว้เป็น cross-application evidence ของ fixture นั้น; ทั้ง exporter และ Bonsai ใช้ IfcOpenShell จึงไม่ใช่การรับรองด้วย geometry kernel อิสระ

## v0.5.0 catalogue and schedule extension

Native Type Catalogue, ordered Wall/Slab material layers and persistent Schedules are implemented in v0.5.0; see [Types and Quantities](TYPES_AND_QUANTITIES.md). This adds native material identity, controlled instance dimensions, actual solid partition quantities, assignment coverage, Type/Material CSV sidecars and IFC Type/material-layer relationships. The legacy untyped fixtures retain their content hashes and six category CSV payloads. Schedule CSV publication checks both model and schedule revisions; editing a visible source row is one native transaction. Arbitrary calculated columns, pricing and schedules on sheets remain outside scope.
