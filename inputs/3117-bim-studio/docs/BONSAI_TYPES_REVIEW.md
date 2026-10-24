# Bonsai review — v0.5.0 Types and Quantities

## ผลที่ตรวจจริง

**ผ่าน 216 checks ใน Bonsai/Blender ที่เปิด IFC จริง พร้อม full IFC schema/EXPRESS validation 0 findings และตรวจภาพหน้าจอจริงแล้ว** การตรวจนี้ใช้ canonical fixture สองชั้นของ v0.5.0 ซึ่งเพิ่ม Type/Material/Schedule ให้โมเดลอาคารเดิม โดยคง UUID และ solid ของ 33 authored products เดิมไว้

หลักฐานอยู่ใน [รายงาน Bonsai](evidence/v0.5.0/bonsai/bonsai-types-report.json), [process report](evidence/v0.5.0/bonsai/process-report.json) และ [ภาพหน้าจอจริง](../examples/types/Bonsai_Types_Quantities.png) ชุดตรวจที่ใช้คือ [tests/bonsai_types_review.py](../tests/bonsai_types_review.py) รายงานเก็บ hash ของ input ทุกไฟล์ จึงตรวจกลับได้ว่าเป็นไฟล์ canonical ชุดใด

| Runtime ที่รันจริง | รุ่น/รายละเอียด |
|---|---|
| Blender | 4.5.14 LTS, build `62c1db4208e8` |
| Bonsai | `0.9.0-post1-py311` |
| IfcOpenShell ใน Bonsai | `0.9.0.post1` |
| Python ใน Bonsai | 3.11.15 |
| ระบบ | Linux x86_64, kernel 6.18.55, glibc 2.39 |
| รูปแบบการตรวจ | GUI application, isolated temporary profile/display |
| ภาพหน้าจอ | 1600 × 1100 pixels, จับจาก X11 framebuffer จริง |

ผลนี้ไม่ใช่ Windows acceptance และไม่ใช่หลักฐานว่าใช้ IFC geometry kernel อีกตัวหนึ่ง: Bonsai ใช้ IfcOpenShell เช่นเดียวกับเส้นทางตรวจ IFC ของโครงการ แม้เป็นการ import และวัด mesh ภายในแอปพลิเคชันอีกตัวหนึ่งจริง

## ระบุ input ที่ตรวจ

Canonical model revision:

```text
b1d7558505e38e8eab14517490e580a875eba1bb7b5503b72d140c259384c804
```

| ไฟล์ | SHA-256 |
|---|---|
| `Types_Quantities_Workbench.ifc` | `5069ee9e77bf618be30020537b1287b4c7137b5989c69961f35f1b73896aa031` |
| `types-snapshot.json` | `2404e65c1f0b081a8da8005d09d7ed9e9cb5afac1ec124f1f7e81bb30b51d022` |
| `types-example.json` | `d074816f6facb23819e1161a3a5bc8a91e714d9714ff36a4e5f685afad9cd695` |
| `Bonsai_Types_Quantities.png` | `c731a5673f97c12e07f56d739d6fe6cb7ec86e289d7ac9f5b28d91e4b5badf40` |

Input ถูกอ่านจาก `/tmp/bim3117-v050-canonical-final/` ระหว่างทดสอบ การ import ไม่เปลี่ยน bytes ของ IFC ซึ่งตรวจ hash ก่อนและหลัง import แล้ว ตัวเลขเปรียบเทียบ geometry มาจาก native building fixture เดิมที่มีรายงานผ่านและมี independent numeric expectations ไม่ได้ใช้ผล triangulation รอบใหม่เป็น expected value ของตัวเอง

Baseline model revision คือ `6295a7332816a71852554c1bcea332f31b2618da6795231a477f8b59c621954a` โดย baseline snapshot มี SHA-256 `ee8435eb0bf2ba197fe8c67e97187656dd8929ef56069949532794a666a729b0` และ baseline native test report มี SHA-256 `424e0d640022e0f05a702daeaf4fe69072491f9f1302b0a96b5b10a7feb666c7`

## สิ่งที่ผ่านการตรวจ

ชุดตรวจเรียก public `bpy.ops.bim.load_project` แล้วอ่าน IFC model ที่ Bonsai เปิดจริง ตรวจว่า authored product แต่ละ UUID อ้างถึง Blender mesh จริงและ map กลับไปยัง IFC entity เดิมได้ จากนั้นวัด triangulated volume และ world bounds ของ mesh ที่ import แล้ว รวมถึงยิง ray ผ่านตำแหน่งช่องเปิดและบริเวณรอยต่อ

| หมวด | Authored products | IFC type ที่สัมพันธ์จริง | Material quantity rows |
|---|---:|---|---:|
| Wall | 8 | 1 `IfcWallType` | 24 |
| Slab | 3 | 1 `IfcSlabType` | 9 |
| Column | 8 | 1 `IfcColumnType` | 8 |
| Beam | 8 | 1 `IfcBeamType` | 8 |
| Door | 2 | 1 `IfcDoorType` | 2 |
| Window | 4 | 1 `IfcWindowType` | 4 |
| รวม | **33** | **6 types** | **55 rows** |

พบ `IfcMaterial` จาก native catalogue 7 รายการ, `IfcMaterialLayerSet` 2 ชุด และ `IfcMaterialLayerSetUsage` 11 รายการสำหรับ Wall 8 ชิ้นและ Slab 3 ชิ้น ส่วนผลิตภัณฑ์เนื้อเดียว 22 ชิ้นสืบทอด material จาก type จริงผ่าน IFC type relationship Material UUID ถูกเก็บใน `IfcMaterialProperties` พร้อม code และ content revision เพราะ `IfcMaterial` ไม่ใช่ `IfcRoot` ที่มี GlobalId

สิ่งที่ checks ครอบคลุม ได้แก่ UUID/GUID และจำนวนผลิตภัณฑ์, type relationships, material identities, layer order/role/thickness/direction/offset, native content revision, material quantity conservation, source metadata และ hash, actual imported mesh volumes/bounds, ช่อง Door/Window ที่ยังว่างจริง, แถบกรอบ Door/Window ที่ยังมีเนื้อจริง และ Slab-priority cuts ของ Column/Beam หลัง import

มี 33 authored mesh products ใน scene ไม่มี mesh product เพิ่มเพื่อแทนชั้นวัสดุ และไม่มีการนับ derived WallBody เป็นผนังอีกชิ้นหนึ่ง `IfcOpeningElement` และ void/fill relationships ยังคงเป็น semantics ของช่องเปิดตามเดิม

## ชั้นวัสดุและพิกัด IFC

การวาง material layers อ้างอิง placement ของ occurrence และไม่ได้แก้ swept solid ของผลิตภัณฑ์ให้เปลี่ยนตำแหน่งตามวัสดุ:

| Fixture type | ชั้นวัสดุตามลำดับ | IFC usage ที่ตรวจ |
|---|---|---|
| Wall 200 mm | Plaster 15 mm → Masonry 170 mm → Plaster 15 mm | `AXIS2`, `POSITIVE`, offset `0.0 m` |
| Slab 150 mm | Floor finish 10 mm → Screed 40 mm → Concrete 100 mm | `AXIS3`, `NEGATIVE`, offset `0.15 m` |

ผนังเริ่มที่ local Y = 0 และเรียงชั้นไปทาง +Y ส่วน Slab นิยามชั้นจากผิวบนลงล่าง ขณะที่ IFC prism เดิมเริ่มที่ผิวล่างและ extrude ไปทาง +Z จึงใช้ offset เท่าความหนารวมและ direction `NEGATIVE` เพื่อให้ชั้นแรกเริ่มที่ผิวบนตาม native definition ความหนาใน IFC อยู่ในหน่วยเมตร

สัญญานี้อิงความหมายของ [buildingSMART IFC4 — IfcMaterialLayerSetUsage](https://standards.buildingsmart.org/IFC/RELEASE/IFC4/FINAL/HTML/schema/ifcmaterialresource/lexical/ifcmateriallayersetusage.htm) และการแยก material definition ของ type ออกจาก occurrence usage ตาม [IfcOpenShell material assignment documentation](https://docs.ifcopenshell.org/autoapi/ifcopenshell/api/material/assign_material/index.html) ค่า offset สำหรับ Slab ข้างต้นเป็นผลจาก placement convention ของ 3117 ที่ตรวจใน fixture นี้

## ปริมาตรและกฎที่ใช้

| หมวด | Native expected net volume (m³) | รวมจาก Blender meshes (m³, แสดง 6 ตำแหน่ง) |
|---|---:|---:|
| Wall | 17.268000 | 17.268002 |
| Slab | 13.162500 | 13.162506 |
| Column หลัง Slab cuts | 2.052000 | 2.052001 |
| Beam หลัง Slab cuts | 3.600000 | 3.600002 |
| Door generic frames | 0.100000 | 0.100000 |
| Window generic frames | 0.184000 | 0.184000 |

เกณฑ์เปรียบเทียบ volume ต่อชิ้นคือ `max(2e-6 m³, abs(expected) × 2e-6)` ความต่างเล็กน้อยในตารางเป็นความละเอียดของ mesh/floating point ใน Blender; รายงานเก็บค่าจริงรายชิ้นและ bounds ก่อนปัดเศษ ทุกชิ้นผ่านเกณฑ์ ไม่ได้เปลี่ยน expected values เพื่อให้เข้ากับค่าที่วัดใหม่

Native material totals ของ fixture คือ gross **40.1825 m³**, deductions **3.8160 m³** และ net **36.3665 m³** โดย assigned-product coverage เท่ากับ **33/33** และ unassigned products = 0 Material rows เป็นการแบ่งปริมาตรผลิตภัณฑ์เดิมตามวัสดุ จึงต้องไม่บวก 55 material rows ซ้ำเข้ากับ product quantities อีกครั้ง

กฎหักปริมาตรยังจำกัดเฉพาะช่องเปิด Wall และ Slab-priority joins ที่ประกาศกับ Column/Beam พื้นคงปริมาตรเต็ม ไม่มีการหัก overlap ทั่วอาคารทุกคู่ ไม่มี density, weight, cost หรือ waste factor ที่สมมติขึ้น ผลนี้จึงไม่ใช่การรับรอง BOQ รวมอาคารที่หักรอยต่อทั้งหมดแล้ว

Door/Window ยังคงเป็น generic frames แบบสามแถบ/สี่แถบ Width/Height หมายถึง overall wall opening รวมกรอบ ไม่ใช่ clear passage หรือขนาดบาน วัสดุ Timber/Aluminium ใน fixture ผูกกับ frame solid ทั้งชิ้น ไม่สร้าง leaf, glazing, hardware หรือชั้นวัสดุของส่วนประกอบที่ยังไม่ได้สร้าง

## ภาพที่ตรวจด้วยสายตา

ตรวจ PNG ที่มี hash ข้างต้นแล้ว ภาพแสดงอาคารสองชั้นใน User Orthographic view เห็นแผ่นพื้นสามระดับ เสา คาน ผนังและกรอบที่อ้าง host ช่องประตูด้านหน้าและช่องหน้าต่างด้านหน้า/ด้านข้างยังเห็นได้ หน้าต่างด้านข้างชั้นบนที่เลือกมีเส้นขอบสีส้ม ด้าน Project Info แสดง `Types_Quantities_Workbench.ifc`, `IFC4` และจำนวน `33 Elements` ไม่มี error dialog หรือ viewport ว่าง

ภาพเป็นมุมมองเดียวของ fixture สังเคราะห์ ความถูกต้องของ identity, order และความหนาชั้นวัสดุอ้างจาก numeric IFC checks ไม่ได้อนุมานจากสี viewport การทดสอบใช้ display settings/camera/selection เพื่อจัดภาพโดยไม่แก้ mesh หรือ IFC source

## รันทวน

ใช้ Blender/Bonsai ที่เปิด add-on แล้วใน disposable profile; harness จะล้าง scene เดิมก่อน import อย่ารันใน authoring session ที่มีงานยังไม่บันทึก ตัวอย่าง background validation:

```bash
blender --background --python tests/bonsai_types_review.py -- \
  --ifc /path/to/Types_Quantities_Workbench.ifc \
  --snapshot /path/to/types-snapshot.json \
  --native-report /path/to/types-example.json \
  --baseline-snapshot examples/building/building-snapshot.json \
  --baseline-native-report docs/evidence/v0.3.0/linux-building-report.json \
  --output /path/to/new-review-directory
```

Background validation ไม่ทำ visual review การตรวจ GUI ครั้งนี้ใช้ temporary Xvfb display แล้วจับ framebuffer หลัง `capture.ready`; process report เก็บ command, environment, harness hash และ exit code = 0 ต้องเปิดตรวจ PNG จริงก่อนเปลี่ยน `visual_review.status` เป็น `passed`
