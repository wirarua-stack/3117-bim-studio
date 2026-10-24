# 3117 BIM Studio — สถาปัตยกรรมโปรแกรม

สถานะ: ข้อเสนอสำหรับ MVP และข้อตกลงการพัฒนา จากโครงโครงการ v0.0.1  
วันที่: 23 ตุลาคม 2569 (2026-10-23)

**อัปเดต v0.2.0:** native Project/Level/Grid ต่อด้วย WallType, Wall, Door และ derived WallBody ใน `workbench/bim3117_freecad` และ `workbench/ui3117` ดูสัญญาที่ใช้งานจริงใน [Foundation Workbench](FOUNDATION_WORKBENCH.md), [Wall / Door Workbench](WALL_DOOR_WORKBENCH.md) และผลทดสอบใน [Verification](VERIFICATION.md) ตาราง v0.0.1 ด้านล่างเป็นฐานเปรียบเทียบเดิม; views/schedule editor ยังเป็นแผน MVP ส่วน native IFC adapter เพิ่มใน v0.2.1 ตาม ADR ถัดไป

**ADR v0.2.0 — dependency ของช่องเปิด:** Wall เป็น native parameter object ที่อ้าง type/levels; Door มี normal Host link ไป Wall; WallBody เป็น derived solid ที่อ้าง Wall และรายการ Door แบบ normal links ส่วน Wall → Body ใช้ hidden backlink จึงไม่มี recompute cycle ข้อมูล authored ไม่มีสำเนาอีกชุด และ downstream quantity/export ต้องนับ Wall ครั้งเดียว โดยใช้ Body เป็นแหล่งรูปทรง

**ADR v0.2.1 — Quantity / Exchange:** snapshot.py อ่าน native document ที่จบ transaction และผ่าน semantic/solid validation แล้วสร้าง SI rows หนึ่งแถวต่อ Wall/Door UUID Content revision เป็น SHA-256 ของ authored content + coverage inventory และคืนค่าเดิมเมื่อ Undo กลับเนื้อหาเดิม ไม่เพิ่ม history counter ในเอกสาร export_ifc/export_csv recapture และตรวจ expected revision ก่อนเขียน payload/metadata โดย .FCStd ยังเป็นข้อมูลหลัก IFC adapter ใช้ swept solids, stable GlobalIds, type/containment/void/fill relations และตรวจไฟล์ที่เขียนจริงก่อนเผยแพร่ รายละเอียดปัจจุบันอยู่ใน [QUANTITY_EXCHANGE.md](QUANTITY_EXCHANGE.md) ข้อเสนอ MVP ที่ยังไม่ทำในส่วนล่างไม่ใช้แทนผลทดสอบจริง

**ADR v0.3.0 — Building Authoring:** `elements.py` เพิ่ม Slab/Column/Beam จาก native authored properties โดยไม่ใช้ cached shape เป็นข้อมูลออกแบบ Slab/Beam ใช้ Level + Offset เป็น top datum และ extrusion ลงล่าง; Column ใช้ Base/Top Levels รอยต่อเป็น Slab → Column/Beam แบบมีทิศทาง จึงไม่มี cycle และ cutter คง full authored solid การตัดต้องเหลือ solid เดียว ปริมาณบันทึก gross / join deduction / actual net ส่วน Window ขยาย Wall → hosted openings → WallBody โดยตรวจ Door/Window ร่วมกัน Native schema 1 เพิ่มชนิดแบบ additive; hash ของโมเดลเดิมไม่เพิ่มรายการว่างชนิดใหม่ ดู [BUILDING_AUTHORING.md](BUILDING_AUTHORING.md)

**ADR v0.4.0 — Drawings and Sheets:** `drawings.py` เก็บ DrawingSet/View/Sheet ใน FCStd เป็นกลุ่มแยกจาก Project.Group มี stable UUID, native links และ transactions แบบตรวจ proposal ก่อนแก้ Drawing definitions ไม่เปลี่ยน building content hash และแสดงเป็น reference/omitted ใน Coverage ส่วน drawing revision hash คิดจาก Sheet และ referenced View definitions ตามลำดับ `drawing_geometry.py` ใช้ actual OCCT clipping/cut loops และ global TechDraw hidden-line removal; `drawing_render.py` วางเวกเตอร์/annotation บน A3 ที่ scale ชัดเจน; `drawing_export.py` ตรวจ model+drawing revisions ก่อนสร้างและก่อน publish SVG/PDF Preview เป็น read-only state ชั่วคราว ไม่เป็น editable master อีกชุด ใช้ Qt ของ host กับ Sarabun ที่มี OFL notice รายละเอียดอยู่ใน [DRAWINGS_AND_SHEETS.md](DRAWINGS_AND_SHEETS.md)

**ADR v0.5.0 — Types and Quantities:** `catalog.py` เก็บ native Material/ElementType และ optional WallType layers ใน Project.Group; Type เป็น authority ของ controlled dimensions ส่วน Instance caches เป็น read-only. ก่อน mutation ใช้ transient proposed state รวมทุก opening/cutter แล้ว commit หนึ่ง native transaction. `material_quantities.py` แบ่ง gross/net OCCT solids ตามชั้นและตรวจ conservation. `schedules.py` เก็บ ScheduleSet/Schedule นอก Project.Group โดย row data เป็น fresh projection, คง source UUIDs, ใช้ model+schedule revisions และแก้ source ผ่าน `catalog.edit_instance`. IFC/CSV add fields เฉพาะ catalogue-active models; legacy empty features คง revision/CSV payload เดิม. ดู [Types and Quantities](TYPES_AND_QUANTITIES.md)

## 1. ข้อสรุปการออกแบบ

พัฒนา **3117 BIM Studio เป็น Workbench บน FreeCAD** กำหนด Windows เป็นแพลตฟอร์มเป้าหมาย โดยผลตรวจปัจจุบันเป็น Linux และ Windows ยังรอตรวจรับ ใช้ `.FCStd` เป็นข้อมูลหลักสำหรับการสร้างและแก้ไขโมเดล และใช้ IfcOpenShell สำหรับส่งออก ตรวจสอบ และอ่านข้อมูล IFC อ้างอิง

แนวคิดการใช้งานประกอบด้วย Project, Level, Grid, Category, Type, Instance, Host, View, Schedule และ Sheet ผู้ใช้แก้ไของค์ประกอบอาคารที่มีความหมายและความสัมพันธ์ แล้วโปรแกรมปรับรูปทรง แบบ และตารางจากข้อมูลเดียวกัน

การตัดสินใจนี้เป็นข้อเสนอของโครงการ ไม่ใช่การรับรองว่าโครงโครงการ v0.0.1 ทำงานครบแล้ว FreeCAD มี BIM Workbench และระบบวัตถุพาราเมตริกเป็นฐานให้ต่อยอด [S1] งานของ 3117 คือกำหนดประสบการณ์ใช้งาน กฎข้อมูล การประสานองค์ประกอบ และคุณภาพผลส่งมอบสำหรับงานอาคาร

## 2. สิ่งที่มีใน scaffold และสิ่งที่ต้องพัฒนา

| ประเด็น | v0.0.1: ขอบเขตโครงโครงการ | เป้าหมายโปรแกรม MVP |
|---|---|---|
| ข้อมูลโมเดล | Reference core ใน Python สำหรับ Level, WallType, Wall และ Door | Native FreeCAD document objects ที่บันทึกใน `.FCStd` |
| Type / Instance | WallType แยกจาก Wall; ขนาด Door ยังเป็นค่ารายตัว | Type catalogue ของผนัง ประตู หน้าต่าง เสา คาน และพื้น พร้อมกฎที่ชัดเจน |
| Geometry | สูตรสำหรับผนังตรงและช่องเปิดสี่เหลี่ยม; ดูขอบเขต exporter และผลทดสอบจริงแยกกัน | Solids, hosted openings, wall joins และการสร้างรูปทรงใหม่ใน FreeCAD |
| Transaction | In-memory reference implementation สำหรับการแก้ไของค์ประกอบ | เชื่อมกับ FreeCAD document transaction และ Undo/Redo ชุดเดียว |
| ข้อมูล JSON | Fixture และข้อมูลตัวอย่างของ reference core | ไม่ใช้เป็น master อีกชุดข้าง `.FCStd` |
| UI | จุดเริ่มต้นสำหรับเชื่อม workbench; ไม่เท่ากับ GUI ที่ตรวจรับแล้ว | การสร้างและแก้ไขผ่าน viewport, Properties และ Project Browser |
| แบบและตาราง | Reference quantity rows / CSV ตามขอบเขตตัวอย่าง | Plan, Section, Elevation, Schedule และ Sheet ที่มี revision ตรงกัน |
| Windows / FreeCAD | ต้องดูบันทึกผลทดสอบ host แยกจากผล Python | ผ่านการติดตั้ง เปิดไฟล์ แก้ไข และบันทึกบน Windows จริง |

การทดสอบ Python ผ่านไม่ใช่หลักฐานว่า FreeCAD GUI ใช้ได้แล้ว และการสร้างไฟล์ IFC สำเร็จไม่ใช่หลักฐานว่าองค์ประกอบทุกประเภทส่งออกครบ

## 3. ข้อมูลหลักและผลที่สร้างจากข้อมูลหลัก

### 3.1 ข้อตกลง MVP

| ข้อมูล | แหล่งข้อมูลหลัก | วิธีใช้งาน |
|---|---|---|
| Element identity, type, level, host, parameters | FreeCAD Document | แก้ไขผ่าน command และ native properties |
| วัตถุและข้อมูลพาราเมตริกที่บันทึกแล้ว | `.FCStd` | ใช้เปิดกลับมาแก้ไขและคำนวณซ้ำ |
| Solid geometry | ผลจาก document properties และ geometry engine | สร้างใหม่เมื่อ dependencies เปลี่ยน |
| Display mesh / selection cache | ผลสร้างชั่วคราว | ล้างและสร้างซ้ำได้ ไม่ใช้กู้คืนความหมายของโมเดล |
| แบบและตาราง | ผลจาก document revision ที่ระบุ | ต้องแสดงสถานะเมื่อข้อมูลล้าสมัย |
| IFC ส่งออก | Snapshot จาก revision ที่ระบุ | ใช้แลกเปลี่ยนและตรวจสอบ ไม่แก้เอกสารต้นทางอัตโนมัติ |
| IFC นำเข้าใน MVP | โมเดลอ้างอิงที่มีแหล่งที่มา | ตรวจ property และตำแหน่ง; แยกจากองค์ประกอบที่สร้างใหม่ |
| Reference JSON | Fixture ของโค้ดตัวอย่าง | ใช้ทดสอบและสาธิตสัญญาข้อมูลเท่านั้น |

เอกสาร FreeCAD ระบุว่า `.FCStd` แยกข้อมูล geometric/parametric definitions ออกจากการแสดงผล [S2] จึงใช้โครงสร้างเอกสารนี้เป็นฐานการบันทึก โดยไม่สร้าง live synchronization ระหว่าง `.FCStd`, JSON และ IFC สามชุด

### 3.2 Native IFC เป็นประเด็นทดลองแยก

FreeCAD มี Native IFC รวมใน BIM Workbench แล้ว [S1] แต่การเลือก Native IFC เป็นข้อมูลหลักต้องผ่านการทดลองด้านความสัมพันธ์พาราเมตริก hosted openings, type propagation, transactions และการบันทึกเปิดกลับก่อน

สำหรับ MVP นี้ **ไม่เปิด Native IFC เป็นตัวเขียนข้อมูลหลักพร้อมกับ `.FCStd`** หากผลทดลองในอนาคตสนับสนุนการเปลี่ยน ต้องมี ADR ใหม่ แผน migration และ acceptance ของไฟล์เดิมก่อนเปลี่ยน ไม่เปลี่ยนเงียบ ๆ ระหว่างรุ่น

### 3.3 การบันทึกและเปิดกลับ

ข้อมูลที่ต้องใช้สร้างรูปทรงใหม่ต้องเก็บเป็น native serializable properties ไม่เก็บไว้เฉพาะ attribute ชั่วคราวของ Python object เอกสาร FeaturePython ระบุว่า properties ถูก serialize แต่ Python class code ไม่ถูกฝังในเอกสาร [S3]

ดังนั้นไฟล์ต้องเก็บ schema/workbench version และผู้ใช้ต้องติดตั้ง workbench รุ่นที่เข้ากันเพื่อแก้ไขและคำนวณซ้ำ เป้าหมาย MVP ต้องมีไฟล์สำรอง การกู้คืน และการย้าย schema; scaffold JSON ไม่ใช่การรับรองระบบบันทึกแบบ production

## 4. ขอบเขตโมดูล

ชื่อในตารางเป็นขอบเขตที่เสนอ ไม่ใช่การยืนยันว่ามี implementation ครบทุกโฟลเดอร์แล้ว

| ส่วน | ความรับผิดชอบ | ไม่ควรรับผิดชอบ |
|---|---|---|
| Workbench UI | เครื่องมือ, selection, task panel, Properties, Browser | เก็บโมเดลอีกสำเนาและคำนวณปริมาณเอง |
| Application commands | CreateWall, PlaceDoor, ChangeType, ChangeLevel, Delete | เขียนไฟล์ผลลัพธ์ก่อน transaction ผ่าน |
| Domain rules | กฎ type/instance, units, host, dependencies, validation | ผูกกับ widget หรือ display mesh |
| Document port | สัญญาอ่าน/แก้ไขเอกสาร | ซ่อนแหล่งข้อมูลหลักที่ต่างกันหลายชุด |
| FreeCAD adapter | Native objects/properties, transactions, recompute | ติดตั้ง Qt/PySide อีกชุดทับ runtime ของ host |
| Geometry service | สร้าง solid, boolean opening, join และ geometry cache | เปลี่ยนค่าพารามิเตอร์เองโดยไม่ผ่าน command |
| IFC adapter | Export mapping, reference import และ validation report | อ้างว่า IFC ทุกชิ้นแปลงเป็น Family ที่แก้ไขได้ |
| Documentation | แปลน รูปด้าน รูปตัด มิติ annotation และ sheet | ปรับตัวเลขแบบโดยแยกจาก model revision โดยไม่แจ้ง |
| Quantity service | กฎปริมาณ, หน่วย, gross/net และที่มาของตัวเลข | นับพื้นที่จากจำนวน triangle ของ viewport |
| Family/type catalogue | Parameters, templates และ compatibility version | รัน script ที่ติดมากับ library โดยไม่กำหนดสัญญา |

Core ที่แยก host ได้ควรเป็นกฎ คำสั่ง และข้อมูลรับส่งตามสัญญา `MemoryDocument` ใช้เป็น test double ได้ ส่วน production backend ใช้ FreeCAD document เพียงชุดเดียว

## 5. ตัวตน Type และ Instance

### 5.1 ตัวตนถาวร

ทุกองค์ประกอบมี UUID ที่ไม่เปลี่ยนเมื่อเปลี่ยนชื่อ ย้ายตำแหน่ง หรือเปลี่ยนขนาด และมี mapping ไป `IfcGlobalId` สำหรับองค์ประกอบที่ส่งออก การทำสำเนาสร้าง UUID ใหม่

ไม่ใช้ชื่อที่ผู้ใช้แก้ไขได้ ลำดับใน scene หรือ STEP entity number เช่น `#123` เป็น identity ระยะยาว Metadata ที่เสนอ ได้แก่ UUID, category, type reference, schema version, source และ revision

### 5.2 กฎพารามิเตอร์

| องค์ประกอบ | Type parameters | Instance parameters |
|---|---|---|
| Wall | ชั้นวัสดุและความหนารวม | แนวเส้น, base/top level, offset, ความสูงเมื่อไม่ผูก top level |
| Door | กว้าง, สูง, รูปแบบบาน | host, ระยะตามแนวผนัง, sill, handing |
| Window | กว้าง, สูง, รูปแบบกรอบ | host, sill, ตำแหน่งตามแนวผนัง |
| Column / Beam | รูปหน้าตัด, ขนาด, วัสดุ | ตำแหน่ง, แนวแกน, base/top หรือ length, rotation |
| Slab | ชั้นวัสดุและความหนา | boundary, level, offset |

ใน reference core ปัจจุบัน Door ยังไม่แยก DoorType; ตารางนี้คือข้อกำหนดพัฒนาต่อ ไม่อ้างว่าได้ครบแล้ว

ต้องกำหนดรายการ parameters ที่อนุญาต instance override ชัดเจน โดยเฉพาะ thickness และ section ที่สัมพันธ์กับ type/material semantics ใน IFC เอกสาร IfcOpenShell ระบุว่าผู้เรียก API ต้องรักษาความสอดคล้องของ geometry กับ material layer/profile sets เอง [S4]

### 5.3 ระดับและความสูง

เมื่อผูก top level ให้ใช้:

`effective_height = top_elevation + top_offset - base_elevation - base_offset`

เมื่อไม่ผูก top level ให้ใช้ unconnected height ไม่ให้สองค่าควบคุมความสูงพร้อมกัน หาก effective height ไม่เป็นบวก ให้ยกเลิกการแก้ไขทั้ง transaction และแจ้งองค์ประกอบที่มีปัญหา

## 6. หน่วยและระบบพิกัด

### 6.1 สัญญาหน่วย

| ชั้นการทำงาน | ความยาว | กฎการแปลง |
|---|---|---|
| Reference core ในชุดนี้ | เมตร SI | ชื่อผลตารางระบุ `_m`, `_m2`, `_m3` |
| Domain reference DTO | เมตร SI | ตรวจว่าเป็นค่าจำกัดและไม่ใช้หน่วยจากข้อความ UI โดยตรง |
| Native host services v0.1–v0.3 | มิลลิเมตร | แยก package `bim3117_freecad`; argument ระบุ `_mm` และใช้ host quantities โดยตรง |
| FreeCAD adapter | ค่าความยาวฐานของ host เป็นมิลลิเมตร | แปลง m → mm ที่ขอบเข้า และ mm → m ที่ขอบออก |
| IFC export | กำหนดหน่วยโครงการให้ชัดเจน | API แต่ละตัวมีสัญญาหน่วยต่างกันได้; ตรวจ `is_si`/unit scale ตาม API จริง |
| UI | mm หรือ m ตามงานและการตั้งค่า | เปลี่ยนการแสดงหน่วยไม่เปลี่ยนขนาดจริง |

ต้องทดสอบการแปลงความยาว พื้นที่ และปริมาตรแยกกัน: `1 m = 1,000 mm`, `1 m² = 1,000,000 mm²`, `1 m³ = 1,000,000,000 mm³` ไม่ใช้ตัวคูณความยาวกับปริมาตร

IfcOpenShell อธิบาย project units และ object placement ไว้ในเอกสาร geometry [S4] ห้ามอนุมานว่า IFC ทุกไฟล์ใช้เมตร

### 6.2 Local / Project / Survey coordinates

เริ่ม geometry ใกล้ local project origin และเก็บ transformation ไปพิกัดสำรวจแยกต่างหาก เป้าหมายแกนโครงการใช้ right-handed coordinates: X ไปทาง Project East, Y ไปทาง Project North, Z ขึ้น ต้องแยก Project North ออกจาก True North

Reference wall ใช้แกน X ท้องถิ่นตาม start → end และเนื้อผนังอยู่ด้าน +Y ของแนวนั้น Door offset วัดจากจุดเริ่มผนังตามแกน X; sill วัดจากฐานผนัง ข้อตกลงนี้ต้องแสดงใน UI/adapter เมื่อเพิ่มฟังก์ชันกลับด้าน

เมื่อเชื่อม Site Agent หรือ Structural Workspace ต้องส่ง units, origin, axis convention, transformation และ element IDs ไปด้วย ไม่ถือว่าทั้งสามโปรแกรมใช้พิกัดเดียวกันโดยอัตโนมัติ

## 7. Host, Opening และการอ้างอิงผิว

Door/Window ต้องสัมพันธ์กับ host และ opening อย่างชัดเจน การย้ายหรือหมุนผนังต้องปรับ placement ขององค์ประกอบที่ host อยู่ พร้อมสร้างช่องเปิดใหม่

Reference core รองรับช่องเปิดสี่เหลี่ยมที่อยู่ภายในผนังและไม่ซ้อนกัน การลบผนังที่มี Door ถูกปฏิเสธจนกว่าจะลบ Door โดยชัดเจน เป้าหมาย UI อาจเสนอ cascade delete เป็นคำสั่งเดียวที่แจ้งรายการผลกระทบ แต่ต้องรักษา Undo ทั้งชุด

อย่าเก็บ host reference ด้วยชื่อผิว เช่น `Face1` อย่างเดียว เพราะการเปลี่ยน boolean หรือ topology อาจเปลี่ยนลำดับผิว ให้เก็บ semantic reference เช่น host UUID, wall axis, side และ local parameters แล้ว resolve ไปเป็นผิวรูปทรงปัจจุบัน

การทำ wall joins, curved walls และ multiple overlapping openings เป็นงานต่อจาก reference core ต้องกำหนดกฎปริมาณและ topology ใหม่ ไม่ขยายสูตรสี่เหลี่ยมไปใช้โดยไม่ตรวจ

## 8. Transaction, Recompute และ Revision

คำสั่งแก้ไขหนึ่งครั้งต้องมีลำดับดังนี้:

1. ตรวจ parameters และ dependencies ที่จะได้รับผลกระทบ
2. เปิด FreeCAD document transaction
3. แก้ native properties
4. Recompute องค์ประกอบที่ได้รับผลกระทบ
5. ตรวจรูปทรงและกฎความสัมพันธ์
6. Commit เมื่อสำเร็จ หรือ rollback ทั้งชุดเมื่อผิดพลาด
7. ระบุ content revision ของผลใหม่และแจ้งผลอ่าน/ส่งออกที่ล้าสมัย; v0.2.1 ใช้ content hash จาก native inputs ไม่เขียนตัวนับเพิ่มในเอกสาร

FreeCAD มี API สำหรับ document transactions/dependencies [S5] แต่ต้องตรวจ API กับ host release ที่โครงการ pin และทดสอบพฤติกรรมจริง

ข้อกำหนด:

- หนึ่งการกระทำผู้ใช้เท่ากับหนึ่งรายการ Undo; การลาก preview ยังไม่ commit ทุก frame
- Undo/Redo ต้องคืนค่า type, host, placement และ quantities ที่สัมพันธ์กัน
- หลัง Undo แล้วมีคำสั่งใหม่ ต้องล้าง redo branch
- คำสั่งล้มเหลวต้องไม่ทิ้งรูปทรงหรือ metadata ครึ่งชุด
- หากคำนวณ background ให้ส่งผลกลับเฉพาะ revision ที่ตรงกับคำขอ
- Model, plan และ schedule ที่ต่าง revision ต้องแสดงสถานะกำลังปรับปรุง/ล้าสมัย
- ไฟล์ IFC/CSV/PDF ที่สร้างแล้วเป็น snapshot; เมื่อโมเดลเปลี่ยนต้องแจ้งว่าควรส่งออกใหม่

Reference transaction ใน v0.0.1 เป็นหลักฐานเฉพาะชุดข้อมูลตัวอย่าง ไม่รับรอง transaction ของ GUI, file system หรือ FreeCAD

## 9. IFC และขอบเขตการแลกเปลี่ยน

MVP เริ่มส่งออก IFC4 ของชนิดที่รองรับ ต้องมี project hierarchy, spatial containment, type assignment, placement, units และ hosted opening relationships ตามข้อกำหนดการส่งออก

ก่อนส่งออกให้สร้าง coverage report: รายการส่งออกได้ รายการเป็น reference และรายการที่ไม่รองรับ ห้ามละองค์ประกอบโดยไม่แจ้ง

Import เริ่มจาก reference workflow การแปลงเป็นองค์ประกอบ native ที่แก้ไขได้ต้องเป็นคำสั่งแยก มีรายงานข้อมูลที่รักษาไว้/ข้อมูลที่สูญหาย และจำกัดชนิดที่ทดสอบแล้ว

ไม่รับรองการอ่าน/เขียน `.RVT` หรือ `.RFA` ไม่อ้างว่าการ export/import IFC รักษา Family constraints, sketches, view settings และประวัติพาราเมตริกได้ครบทุกชนิด

## 10. แบบ ตาราง และปริมาณ

Plan, Section, Elevation, Schedule และ Sheet ต้องสืบย้อนกลับไป document revision และ element IDs ได้ แยก model geometry, view definition, annotation และ sheet placement

Quantity rows ต้องมีหน่วย กฎการหักช่องเปิด และที่มาของค่า Reference core คิดพื้นที่ด้านข้างหนึ่งด้านของผนังตรงและปริมาตรสี่เหลี่ยม หักช่องเปิด Door โดยไม่คิด wall joins หรือปริมาตรที่ทับกันระหว่างผนัง จึงยังไม่ใช่ BOQ ที่ผ่านการตรวจสำหรับอาคารจริง

ค่าปริมาณหลัง wall joins, multilayer materials, curved/sloped objects และ finish surfaces ต้องมีกฎเฉพาะ พร้อม fixture ที่ตรวจได้

## 11. รุ่น Runtime และการทดสอบ

Pin รุ่น FreeCAD, Python, IfcOpenShell และ dependencies ที่ใช้จริง ไม่ใช้คำว่า latest เป็นสัญญาการทำงาน ระหว่างรันภายใน FreeCAD ให้ใช้ Qt/PySide ที่ตรงกับ host; ไม่ติดตั้ง standalone PySide6 ทับโดยอัตโนมัติ

แยกผลตรวจอย่างน้อยสามระดับ: reference-core tests, FreeCAD integration tests และ Windows user workflow tests มีรายละเอียดใน [ACCEPTANCE.md](ACCEPTANCE.md)

ยังไม่มีคำรับรองจำนวนชิ้นส่วนสูงสุด เวลาเปิดไฟล์ หรือ frame rate จากเอกสารนี้ ต้องทดสอบบนเครื่องที่ระบุ hardware, dataset, model count, software versions และวิธีวัดก่อนประกาศผล

## แหล่งอ้างอิงต้นทาง

- **S1 — FreeCAD BIM Workbench:** https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/BIM_Workbench.md
- **S2 — FreeCAD FCStd file format:** https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/File_Format_FCStd.md
- **S3 — FeaturePython object and serialization:** https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Create_a_FeaturePython_object_part_I.md
- **S4 — IfcOpenShell geometry, types, units and placements:** https://docs.ifcopenshell.org/ifcopenshell-python/geometry_creation.html
- **S5 — FreeCAD Document API:** https://freecad.github.io/SourceDoc/d8/d3e/classApp_1_1Document.html

แหล่งอ้างอิงข้างต้นยืนยันความสามารถ/กลไกของเทคโนโลยี ส่วนการเลือก architecture, กฎโครงการ และ acceptance ในเอกสารนี้เป็นข้อเสนอของ 3117 BIM Studio
