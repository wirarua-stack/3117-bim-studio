# 3117 BIM Studio — เกณฑ์ตรวจรับและหลักฐานการทดสอบ

**Current gate v0.5.0:** Type/material/schedule acceptance ประกอบด้วย native fanout รวมหลาย opening/cutter พร้อมกัน, การ reject โดยรักษา Redo, source edit transaction เดียว, native save/fresh reopen, material volume conservation/assignment omissions, schedule filter/group/distinct count, stale revision/export rejection, IFC types/material layer usage/readback และ actual GUI. รายงานปัจจุบันอยู่ใน [Verification](VERIFICATION.md); Windows ยังเป็น gate แยก. รายการ scaffold และข้อความรุ่นก่อนด้านล่างเป็นประวัติการพัฒนา.

**Current failed gate:** GUI history branching หลัง create/delete/Undo/Undo/new edit/Undo/Redo ทำให้ FreeCAD 1.1.4 Linux เกิด SIGSEGV โดยทำซ้ำได้โดยไม่มี 3117 ข้อขัดข้องนี้ยังปิดไม่ได้จากผลฟังก์ชันอื่นที่ผ่าน ดู [Host compatibility](HOST_COMPATIBILITY.md) และต้องรันทดสอบเดิมบน host ที่แก้แล้วก่อนยอมรับ Pilot


สถานะ: แผนตรวจรับจาก scaffold v0.0.1  
วันที่: 23 ตุลาคม 2569 (2026-10-23)

อัปเดต v0.2.0: เพิ่ม native WallType/Wall/Door และ real boolean openings พร้อม host/GUI harness แยกจาก Foundation ตาม [WALL_DOOR_WORKBENCH.md](WALL_DOOR_WORKBENCH.md) และ [VERIFICATION.md](VERIFICATION.md) ใช้ [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md) สำหรับ gate Windows โดยเฉพาะ ข้อความอัปเดต v0.2.0 เป็นประวัติ; Native IFC ต้องอ้างหลักฐาน v0.2.1 โดยเฉพาะ และ drawings ยังเป็นงานอนาคต

อัปเดต v0.2.1: native quantity rows/CSV/IFC4 และหน้าต่างอ่านปริมาณเพิ่มแล้วตาม [QUANTITY_EXCHANGE.md](QUANTITY_EXCHANGE.md) ผลตรวจจริงอยู่ใน [VERIFICATION.md](VERIFICATION.md) Full drawing/sheet/schedule-editor workflow และ Windows GUI ยังไม่ถือว่าผ่านจากชุดนี้

อัปเดต v0.3.0: เพิ่ม Slab/Column/Beam/Window และ explicit Slab-priority joins ตาม [BUILDING_AUTHORING.md](BUILDING_AUTHORING.md) เกณฑ์ใหม่รวม top datum, concave boundary, mixed Door/Window overlap, split/full-cut rollback, direct Properties, fresh-process restore, native/CSV/IFC agreement และ actual GUI/Bonsai evidence โดยใช้ [VERIFICATION.md](VERIFICATION.md) เป็นผลจริง ไม่ถือว่ารายการแบบ/แผ่นแบบ/Windows ในแผนนี้ผ่านทั้งหมด

อัปเดต v0.4.0: เพิ่ม native DrawingSet/View/Sheet, Plan/Section/Elevation จาก solids, View range, overall dimensions, source tags, A3 1–2 views และ SVG/PDF ตาม [DRAWINGS_AND_SHEETS.md](DRAWINGS_AND_SHEETS.md) ตรวจ actual cut holes/joins/occlusion, explicit scale/overflow, transactions/Undo/Redo/reopen, unchanged legacy model hash, separate drawing hash, stale publication/rollback, actual GUI และ PDF page/font/vector render ผลจริงอยู่ใน [VERIFICATION.md](VERIFICATION.md) Custom annotation/detail editor, schedule editor, full pilot และ Windows interactive acceptance ยังไม่ผ่านจากการเพิ่มชุดนี้โดยอัตโนมัติ

## 1. วิธีอ่านสถานะ

เอกสารนี้กำหนดสิ่งที่ต้องพิสูจน์ ไม่ใช่รายงานว่าผ่านทั้งหมดแล้ว ผลที่ผ่านต้องอ้างอิงบันทึกการรันทดสอบจริง พร้อมรุ่นซอฟต์แวร์และขอบเขตการทดสอบ

| ระดับหลักฐาน | พิสูจน์อะไรได้ | ยังพิสูจน์อะไรไม่ได้ |
|---|---|---|
| Reference-core tests | กฎข้อมูล สูตรปริมาณ ID และ transaction ของชุดตัวอย่าง | FreeCAD GUI, การติดตั้ง Windows หรือแบบก่อสร้าง |
| IFC checks ใน Python | โครงสร้างที่ตรวจ ข้อมูลและ geometry ตาม assertions | การอ่านในโปรแกรมอื่นหรือ round-trip ครบทุกความหมาย |
| FreeCAD host integration | Object lifecycle, recompute, save/open และ host transactions ที่ทดสอบ | การใช้งาน Windows หากรันเฉพาะเครื่อง/OS อื่น |
| External application review | การเปิดและตรวจโมเดลในแอปที่ระบุ | ความเข้ากันได้กับทุกซอฟต์แวร์หรือทุก IFC class |
| Windows workflow test | ขั้นตอนผู้ใช้จริงบนเครื่องและรุ่นที่บันทึก | เครื่องและรุ่นอื่นที่ยังไม่ทดสอบ |

**ถือว่า FreeCAD host บน Windows ยังไม่ผ่านการตรวจรับ จนกว่าจะมีบันทึกทดสอบจริง** การมีไฟล์ workbench หรือโค้ด import ผ่านไม่แทนหลักฐานนี้

## 2. G0 — การตรวจโครงโครงการ

| รหัส | สิ่งที่ตรวจ | ผลที่ต้องได้ |
|---|---|---|
| G0-01 | ติดตั้ง package ใน environment ใหม่ตาม README | ติดตั้งและรันคำสั่งที่ประกาศได้ |
| G0-02 | รัน reference tests | รายงานจำนวนทดสอบและข้อจำกัดตรงกับผลจริง |
| G0-03 | สร้าง demo fixture และ quantity CSV | ค่าและ units ตรงกับกรณีตัวอย่าง |
| G0-04 | ทดสอบ IFC exporter หากติดตั้ง optional dependency | ระบุ IfcOpenShell รุ่นที่ใช้; ถ้าไม่ได้รันให้ระบุ skipped/untested |
| G0-05 | ตรวจ README และเอกสาร | แยก implemented, scaffold และ planned ชัดเจน |
| G0-06 | ตรวจ artifact/repository | ไม่มี secrets หรือ customer model ที่ไม่ได้เลือกเป็นตัวอย่าง |

กรณีนี้ใช้ข้อมูลสังเคราะห์สำหรับโครงการ การตรวจไฟล์ไม่ได้เป็นเหตุให้ต้องเผยแพร่ repository หรืออัปโหลดโมเดลลูกค้า

## 3. G1 — สัญญาข้อมูลและคำสั่ง

### 3.1 Identity / Type / Level

| รหัส | การกระทำ | ผลที่ต้องได้ |
|---|---|---|
| G1-01 | เปลี่ยนชื่อและตำแหน่ง Wall | UUID คงเดิม |
| G1-02 | ทำสำเนาวัตถุผ่านคำสั่งสำเนาในรุ่นที่รองรับ | สำเนามี UUID ใหม่ และไม่มี IFC GUID ชนกัน |
| G1-03 | เปลี่ยนความหนา WallType | ทุก Wall instance ที่อ้างอิง type มีความหนาและปริมาณใหม่ |
| G1-04 | เปลี่ยน top level | effective height ของ Wall ที่ผูกระดับเปลี่ยนตาม |
| G1-05 | ตั้ง top level ต่ำกว่าฐานจนความสูงไม่เป็นบวก | ปฏิเสธและคืน state เดิมทั้ง transaction |
| G1-06 | ลบ level/type ที่มี Wall ใช้งาน | ปฏิเสธ หรือใช้คำสั่งจัดการ dependencies ที่มีนโยบายชัดเจน |
| G1-07 | ใส่ NaN, infinity, ขนาดติดลบ หรือค่าชนิดผิด | ปฏิเสธก่อน commit |

รายการที่ scaffold ยังไม่มี เช่น คำสั่งสำเนา เป็นเกณฑ์สำหรับ feature เมื่อเพิ่มจริง ไม่ถือว่าผ่านเพียงเพราะไม่ได้เรียกใช้

### 3.2 Host / Opening

| รหัส | การกระทำ | ผลที่ต้องได้ |
|---|---|---|
| G1-08 | วาง Door ภายใน Wall | เก็บ host, offset, width, height และ sill ครบ |
| G1-09 | วาง Door เลยขอบหรือสูงเกินผนัง | ปฏิเสธและคืน state เดิม |
| G1-10 | สร้าง opening ซ้อนกันใน reference core | ปฏิเสธตามขอบเขตที่ประกาศ |
| G1-11 | ย้าย/หมุน Wall ใน host integration | Door และ opening เคลื่อนตาม local placement ที่ถูกต้อง |
| G1-12 | ลบ Wall ที่มี Door | Reference policy ปฏิเสธ; หากมี cascade command ต้อง Undo คืนทั้งชุดได้ |

การตรวจตัวเลข offset อย่างเดียวไม่เพียงพอสำหรับ G1-11 ต้องตรวจ geometry ใน host และ IFC placement ด้วย

### 3.3 Transaction / Undo / Redo

- แก้หลาย properties ในหนึ่ง command แล้ว Undo ครั้งเดียวกลับ state เดิม
- คำสั่งผิดพลาดหลังเปลี่ยนค่าบางส่วนต้องไม่ทิ้งข้อมูลครึ่งชุด
- Redo คืน state หลังแก้ไข รวม type, host และปริมาณ
- Undo แล้วแก้ไขคำสั่งใหม่ต้องไม่สามารถ Redo branch เก่าได้
- ยกเลิก preview ด้วย Escape ต้องไม่สร้างองค์ประกอบค้าง
- Parent/child dependencies ที่คำนวณแล้วต้องสอดคล้องกันหลัง Undo/Redo

สำหรับ FreeCAD ให้ทดสอบผ่าน transaction ของ host; ผลจาก in-memory reference history ไม่ใช้แทนกัน

## 4. G2 — ตัวเลขตรวจรับปริมาณ

### 4.1 ผนังตรงเดี่ยว

เงื่อนไข: ผนังเป็นสี่เหลี่ยมตรง ไม่มีรอยต่อกับผนังอื่น วัดพื้นที่ด้านข้างหนึ่งด้าน หนา 0.20 m ยาว 6.00 m สูง 3.00 m มีช่องประตู 0.90 × 2.10 m และไม่มีช่องเปิดอื่น

| ค่า | ผลที่คำนวณตรวจได้ |
|---|---:|
| Gross side area | 18.000 m² |
| Door opening area | 1.890 m² |
| Net side area | 16.110 m² |
| Gross volume | 3.600 m³ |
| Net volume | 3.222 m³ |

เมื่อเปลี่ยนความสูงเป็น 3.30 m โดยขนาดประตูคงเดิม:

| ค่า | ผลที่คำนวณตรวจได้ |
|---|---:|
| Gross side area | 19.800 m² |
| Net side area | 17.910 m² |
| Gross volume | 3.960 m³ |
| Net volume | 3.582 m³ |

ต้องตรวจผลคำนวณทั้งก่อนแก้ หลังแก้ หลัง Undo และหลัง Redo สำหรับสูตร reference core ใช้ numeric tolerance ที่ระบุใน test; tolerance ของ solid geometry ต้องกำหนดแยกตาม kernel ไม่ใช้เกณฑ์ตัวเลขเดียวกันโดยไม่มีเหตุผล

### 4.2 ห้องตัวอย่าง reference 6 × 4 m

Demo ระบุแนวอ้างอิงผนังสี่ด้านยาว 6, 4, 6 และ 4 m สูง 3 m หนา 0.20 m และช่องประตู 0.90 × 2.10 m หนึ่งช่อง

| ผลรวมรายผนัง | ค่า |
|---|---:|
| ความยาวรวม | 20.000 m |
| Gross side area รวม | 60.000 m² |
| Net side area รวม | 58.110 m² |
| Gross volume รวม | 12.000 m³ |
| Net volume รวม | 11.622 m³ |

ตัวเลขนี้เป็นผลรวมของผนังแต่ละชิ้น **ยังไม่หัก volume overlap ที่มุมและยังไม่ได้ทำ wall joins** ขนาด 6 × 4 m เป็นระยะของแนวอ้างอิง ไม่ใช่การรับรอง clear room area หรือพื้นที่ใช้สอย 24 m²

## 5. G3 — One-room vertical slice ใน FreeCAD

เกณฑ์นี้เป็นงานต่อจาก reference core ต้องสร้างผ่าน workbench และบันทึกเป็น `.FCStd`

| รหัส | ขั้นตอนผู้ใช้ | หลักฐานผ่าน |
|---|---|---|
| G3-01 | สร้าง project, สอง levels และ grid | Browser และ properties แสดงความสัมพันธ์ถูกต้อง |
| G3-02 | สร้างสี่ผนังและหนึ่ง slab | Geometry ใน 3D และแปลนตรงกัน |
| G3-03 | วางประตูหนึ่งบานในผนัง | มี host relation และช่องเปิดจริงใน solid |
| G3-04 | แก้ top level และ wall type | รูปทรง Door/Wall และตารางเปลี่ยนตามกฎ |
| G3-05 | ใช้ Plan, Section และ 3D view | แสดงองค์ประกอบเดียวกันจาก document revision เดียวกัน |
| G3-06 | เปิด wall/door schedule | แถวอ้างอิง element IDs; ค่าตรงกับโมเดล |
| G3-07 | Undo/Redo หลายคำสั่ง | Geometry, parameters และ quantities คืน state ถูกต้อง |
| G3-08 | Save, ปิดโปรแกรม, เปิดไฟล์ใหม่ | UUID, types, levels และ host links คงอยู่; recompute ได้ |
| G3-09 | ส่งออก IFC4 | ผ่านโครงสร้าง/geometry checks และ external review ที่ระบุใน G4 |
| G3-10 | แก้โมเดลหลังส่งออก | ผลเดิมถูกระบุว่าเป็น snapshot เก่า ไม่แสดงว่าเป็น current |

Window, joins, finishes และ quantity rules เพิ่มเติมให้มีชุด acceptance ของตนเองก่อนใช้กับ pilot

### Revision consistency

- ทดสอบเปลี่ยนระดับขณะ plan/schedule เปิดอยู่
- ระหว่างคำนวณให้เห็นสถานะกำลังปรับปรุง; หลังเสร็จทุก surface ต้องชี้ revision เดียวกัน
- ทดสอบงานคำนวณช้าสองคำสั่งต่อกัน ผลของคำสั่งเก่าต้องไม่เขียนทับผลใหม่
- การส่งออกต้องบันทึก source revision หรือข้อมูลเทียบเท่าที่สืบย้อนกลับได้

## 6. G4 — IFC validation และการเปิดในโปรแกรมอื่น

### 6.1 ตรวจอัตโนมัติ

ตรวจอย่างน้อย:

1. IFC schema ที่ประกาศและ project units
2. Project / Site / Building / Storey hierarchy ตาม mapping ที่รองรับ
3. Class, type assignment และ spatial containment ขององค์ประกอบที่ส่งออก
4. `IfcRelVoidsElement` สำหรับ opening และ `IfcRelFillsElement` สำหรับประตูที่รองรับ
5. Placement รวมหลัง host ถูกย้าย/หมุน; ตรวจความยาวจริงเพื่อจับความผิดพลาด m ↔ mm
6. UUID-to-IFC mapping และ GlobalId ขององค์ประกอบเดิมคงที่เมื่อ export ซ้ำ
7. Geometry สร้างได้ ช่องเปิดปรากฏจริง และปริมาตรตรงกับ fixture ภายใน tolerance ที่ประกาศ
8. Export coverage report แสดงสิ่งที่ข้ามหรือไม่รองรับ

Schema validation ตรวจเพียงส่วนหนึ่งของคุณภาพ ไม่ยืนยันว่าแบบก่อสร้างหรือปริมาณถูกต้องทั้งหมด

### 6.2 เปิดไฟล์ด้วยแอปอื่น

ใช้ **Bonsai ใน Blender** เป็นอย่างน้อยหนึ่งแอปสำหรับเปิด IFC ที่ส่งออก บันทึกรุ่นที่ใช้และตรวจด้วยผู้ทดสอบ:

- อาคารวางตรงตำแหน่งและมีขนาดจริงถูกต้อง
- ประตูและช่องเปิดสัมพันธ์กัน ไม่มีรูหายหรือรูปทรงอยู่คนละตำแหน่ง
- ชื่อ type, storey และ properties ที่ประกาศปรากฏครบ
- ไม่เกิด duplicate elements หรือ GUID ที่ชนกัน
- เปรียบเทียบ fixture geometry/quantities กับค่าคาดหมาย

การอ่านกลับด้วย IfcOpenShell ในสคริปต์เดิมไม่ใช้แทนขั้นตอนนี้ Bonsai ใช้ IfcOpenShell เป็นส่วนหนึ่งของระบบเช่นกัน จึงเป็นการทดสอบข้ามแอป แต่ยังไม่ใช่หลักฐานข้าม geometry engine ทุกชนิด หากจะประกาศรองรับ Revit หรือโปรแกรมปลายทางอื่น ต้องทดสอบโปรแกรมนั้นเพิ่มเฉพาะขอบเขตที่ประกาศ

## 7. G5 — Windows และการใช้งานจริง

บันทึก OS, FreeCAD version/build, Python, IfcOpenShell, workbench commit และรายละเอียด hardware พร้อมผลแต่ละข้อ

| การทดสอบ | ผลที่ต้องได้ |
|---|---|
| ติดตั้งตามคู่มือบน Windows environment ใหม่ | Workbench ปรากฏและคำสั่งที่ประกาศเรียกได้ |
| Properties / Browser / viewport | ไม่บังพื้นที่ทำงานโดยไม่จำเป็น; dock/resize ทำงาน |
| Select และคลิกพื้นที่ว่าง | Selected element ชัดเจน; คลิกว่างยกเลิกเลือก |
| Window/crossing selection เมื่อรองรับ | ทิศลากมีพฤติกรรมตามที่ UI ประกาศ |
| Orbit / Pan / Zoom | ทิศทางและ pivot สม่ำเสมอตาม navigation preset |
| Ctrl+Z / Ctrl+Y / Escape | ทำงานตาม transaction/preview policy |
| Save/Open ในชื่อและ path ภาษาไทย | ข้อมูลและไฟล์ไม่เสียหาย |
| ปิด/เปิดหลังแก้ไข | เตือนข้อมูลยังไม่บันทึกตาม policy และเปิดกลับได้ |
| Missing/incompatible workbench dependency | แจ้งปัญหาที่แก้ไขได้ ไม่แสดงว่าคำนวณสำเร็จผิด ๆ |
| เปลี่ยน UI units | ขนาดจริงและ IFC export ไม่เปลี่ยน |

หากยังไม่ได้ทดสอบข้อใด ให้ระบุ `Not tested` ไม่ใช้คำว่า ready หรือ complete แทนสถานะ

## 8. G6 — Pilot อาคารสองชั้น

ใช้อาคารทดสอบสังเคราะห์หรือโมเดลที่อนุญาตให้ใช้เป็นตัวอย่าง มีอย่างน้อยสองชั้น และมีองค์ประกอบ Arch/Structure ที่อยู่ใน feature set ของรุ่นนั้น

### ขอบเขตที่ต้องตรวจ

- Project, site, building, levels และ grids
- ผนังหลาย type, พื้น, เสา, คาน, ประตูและหน้าต่าง
- การเปลี่ยนระดับ ความหนา และขนาดหน้าตัดโดยข้อมูลที่สัมพันธ์กันปรับตาม
- Plan สองชั้น, อย่างน้อยหนึ่ง section, elevation และหนึ่ง sheet ที่มี scale และ annotation
- Wall/door/window schedules และ quantity report ที่บอกกฎการคิด
- `.FCStd` save/open, revision consistency, IFC4 export และ Bonsai review
- การย้าย origin/การอ้างอิงพิกัดตามความสามารถที่ประกาศ
- ประเภทองค์ประกอบที่ยังไม่รองรับถูกแสดงในข้อจำกัดของ pilot

### เกณฑ์ตัดสิน

ผู้ใช้ทดสอบต้องทำ workflow สร้าง → แก้ไข → ออกแบบ → ตาราง → ส่งออก ได้ตามคู่มือโดยไม่ต้องแก้ไฟล์ข้อมูลด้วยมือ ต้องไม่มีข้อมูลสูญหายหรือผลปริมาณที่ผิดจากกฎที่ประกาศโดยไม่แจ้ง

บันทึก defect พร้อม fixture ที่ทำซ้ำได้ แยกระหว่างข้อบกพร่องที่ต้องแก้ก่อนรุ่นถัดไปกับ feature ที่ยังไม่อยู่ใน scope

## 9. ประสิทธิภาพและความทนทาน

เอกสารนี้ **ไม่มีผล benchmark** และไม่รับรองจำนวน elements สูงสุดหรือ frame rate

ก่อนประกาศผลต้องกำหนด hardware, dataset, จำนวนองค์ประกอบ, จำนวน instances/types, geometry complexity, views ที่เปิด, software versions และวิธีวัด แล้วรายงานเวลาเปิดไฟล์/บันทึก/แก้พารามิเตอร์/ออก IFC และ peak memory จากการรันจริง

ทดสอบความเสี่ยงที่พบจริง เช่น file-write interruption, schema migration, missing references และ stale background jobs การขยายชุดทดสอบควรตอบความเสี่ยงหรือ release gate ที่ระบุ ไม่เพิ่มชุดทดสอบเพื่อให้จำนวนดูมาก

## 10. แบบบันทึกผลขั้นต่ำ

| ช่องบันทึก | ข้อมูลที่ต้องมี |
|---|---|
| Test ID | รหัสจากเอกสารหรือรหัส regression ที่เพิ่ม |
| Environment | OS, host/dependency versions, commit และ hardware เมื่อเกี่ยวข้อง |
| Fixture | ชื่อไฟล์/เวอร์ชัน/ขนาดและจำนวนองค์ประกอบ |
| Steps | ขั้นตอนที่ทำซ้ำได้ |
| Expected | ค่าหรือพฤติกรรมที่ต้องได้ |
| Actual | ค่าหรือพฤติกรรมที่สังเกตจริง |
| Status | Passed / Failed / Skipped / Not tested |
| Evidence | Log, file หรือภาพประกอบที่ไม่มีข้อมูลอ่อนไหว |
| Limitation / Defect | ขอบเขตที่ยังไม่พิสูจน์และ issue ที่เกี่ยวข้อง |

## เอกสารและแหล่งอ้างอิง

- [ARCHITECTURE.md](ARCHITECTURE.md) — ข้อมูลหลัก หน่วย พิกัด transactions และ IFC policy
- [FreeCAD BIM Workbench](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/BIM_Workbench.md)
- [FreeCAD FCStd file format](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/File_Format_FCStd.md)
- [IfcOpenShell geometry and placements](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_creation.html)
- [IfcOpenShell validation](https://docs.ifcopenshell.org/ifcopenshell-python/validation.html)
- [Bonsai documentation](https://docs.bonsaibim.org/)

ตัวเลขตัวอย่างในเอกสารเป็นผลคำนวณจากเงื่อนไขที่ระบุ ส่วนขั้นตอนและ release gates เป็นข้อเสนอของโครงการ
