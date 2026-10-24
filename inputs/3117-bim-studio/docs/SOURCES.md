# แหล่งข้อมูลและเหตุผลการเลือกฐานพัฒนา

ตรวจสอบแหล่งข้อมูล: **2026-10-23**

เอกสารนี้แยกข้อเท็จจริงของโครงการต้นทางออกจากข้อเสนอสำหรับ 3117 BIM Studio ความสามารถที่มีใน FreeCAD, Bonsai หรือไลบรารีต้นทาง **ไม่ได้หมายความว่าชุดโครงโครงการนี้ได้พัฒนาหรือทดสอบความสามารถนั้นแล้ว** สถานะจริงของงานให้ดู README และผลการทดสอบของ release นั้น

## ข้อเท็จจริงที่ตรวจสอบได้

| ID | แหล่งข้อมูลหลัก | ข้อเท็จจริงที่ใช้ | ขอบเขตการอ้างอิง |
| --- | --- | --- | --- |
| S01 | [FreeCAD official repository](https://github.com/FreeCAD/FreeCAD) | FreeCAD เป็นโปรแกรมสร้างโมเดลพาราเมตริก มี model history และเครื่องมือสร้างแบบจากโมเดล | เป็นฐาน host ที่มีอยู่ ไม่ใช่ผลงานของ 3117 |
| S02 | [FreeCAD core LICENSE](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE) | ไฟล์ LICENSE หลักเป็น GNU LGPL version 2.1 | ต้องตรวจ source headers, modules และ dependencies ที่ใช้จริงเพิ่มเติม ไม่ตีความว่า installer ทุกส่วนมี license เดียว |
| S03 | [เดิม: BIM_Workbench](https://github.com/yorikvanhavre/BIM_Workbench) | README ระบุว่า BIM รวมเข้า FreeCAD ตั้งแต่ v1.0 และไม่ต้องติดตั้ง add-on เดิมแล้ว | ใช้ยืนยันการย้ายเข้า core; ไม่ใช้ repo เดิมเป็นฐานพัฒนาปัจจุบัน |
| S04 | [เอกสาร FreeCAD BIM Workbench](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/BIM_Workbench.md) | อธิบาย parametric walls, beams, roofs, windows, stairs, pipes, IFC, TechDraw และ schedules | repository เอกสารถูก archived วันที่ 2026-04-01; ใช้อธิบายแนวทางและความสามารถที่บันทึกไว้ ไม่ยืนยันทุก API ของรุ่นล่าสุด |
| S05 | [Bonsai official website](https://bonsaibim.org/) | Bonsai Studio เป็น native IFC authoring environment บน Blender | เป็นทางเลือก authoring และแหล่งอ้างอิง ไม่ใช่ dependency ที่ bundle มาใน scaffold |
| S06 | [Bonsai development architecture](https://docs.bonsaibim.org/studio/guides/development/hello_world.html) | Bonsai ใช้ IFC ใน memory เป็น source of truth และแยก Delivery, Domain, Data | แนว native IFC ต่างจากการใช้ FreeCAD document เป็น authoring master |
| S07 | [IfcOpenShell repository และตาราง component licenses](https://github.com/IfcOpenShell/IfcOpenShell) | มี IFC parsing/geometry และเครื่องมือประกอบ; Python library ระบุ LGPL-3.0-or-later ส่วน Bonsai ระบุ GPL-3.0-or-later | repo มีหลาย licenses; ความครอบคลุม parsing ไม่เท่ากับ authoring หรือ geometry support ครบทุก schema |
| S08 | [IfcOpenShell LGPL text](https://github.com/IfcOpenShell/IfcOpenShell/blob/v0.9.0/COPYING.LESSER) | มีเงื่อนไข notices, license copies และ combined works | เป็นข้อความที่ ref v0.9.0; ตรวจข้อความของ package version ที่แจกจริงอีกครั้ง |
| S09 | [IfcOpenShell Python documentation](https://docs.ifcopenshell.org/ifcopenshell-python.html) | มี API และเอกสาร geometry creation, manipulation, validation และ schema querying | ต้องล็อกและทดสอบ package version; เอกสารเว็บอาจเคลื่อนตาม release |
| S10 | [That Open Components](https://github.com/ThatOpen/engine_components) | ชุด BIM tools บน Three.js สำหรับ browser applications เช่น navigation, dimensions และ DXF export | ไม่ใช่ complete parametric BIM authoring engine |
| S11 | [That Open Components LICENSE](https://github.com/ThatOpen/engine_components/blob/main/LICENSE.md) | MIT license พร้อมข้อกำหนดให้รักษา copyright และ permission notice | ใช้กับ component นี้; dependencies ต้องตรวจแยก |
| S12 | [web-ifc repository](https://github.com/ThatOpen/engine_web-ifc) | JavaScript/WASM library สำหรับอ่านและเขียน IFC | เป็น library ไม่ใช่โปรแกรม editor ที่มีความสัมพันธ์ Level/Host/Type พร้อมใช้ |
| S13 | [web-ifc LICENSE](https://github.com/ThatOpen/engine_web-ifc/blob/main/LICENSE.md) | Mozilla Public License 2.0 | การแจก covered code และ executable มีเงื่อนไข source availability; larger work ต้องปฏิบัติต่อ covered code ให้ครบ |
| S14 | [FreeCAD releases](https://github.com/FreeCAD/FreeCAD/releases) | upstream แยก development builds และระบุข้อจำกัดการใช้ใน production | ใช้กำหนดนโยบายเลือก stable baseline และทดสอบเป็นรายรุ่น ไม่ใช้คำว่า latest เป็น compatibility contract |

## ข้อเสนอสำหรับ 3117 BIM Studio

ข้อเสนอต่อไปนี้เป็นการตัดสินใจออกแบบโครงการ ไม่ใช่ความสามารถที่ upstream รับรองให้ 3117:

1. **เริ่มจาก user-installed FreeCAD และ 3117 Workbench** เพื่อใช้ document model, geometry และ desktop interaction ที่มีอยู่แล้ว แทนการสร้างทุกชั้นพร้อมกัน
2. **กำหนด FCStd เป็น authoring master ใน baseline แรก** และใช้ IFC เป็น exchange output พร้อม mapping identifiers การสาธิตผ่าน IfcOpenShell แยกจาก authoring document และยังไม่ใช่ two-way synchronization
3. **บันทึก native IFC เป็นทางเลือกใน ADR ระยะถัดไป** หากเลือกเปลี่ยน master ภายหลัง ต้องกำหนด ownership, migration, stable IDs, undo และแบบทดสอบก่อน ห้ามมี editable masters สองชุดที่ขัดกันโดยไม่ตรวจพบ
4. ใช้ Bonsai เป็นแหล่งอ้างอิงและโปรแกรมอิสระสำหรับตรวจการแลกเปลี่ยน IFC โดยไม่คัดลอกโค้ดหรือบรรจุ upstream ใน scaffold นี้
5. พิจารณา That Open/web-ifc สำหรับ viewer และ coordination บนเว็บภายหลัง แยก published revisions ที่ใช้ดูออกจาก working authoring model
6. ล็อกเวอร์ชัน dependencies ที่ผ่านการทดสอบจริงในแต่ละ release และเก็บหลักฐาน save/reopen, IFC validation และการเปิดข้ามโปรแกรม

## การตีความสถานะและความเข้ากันได้

- IFC ที่ parser อ่านได้ ไม่ได้แปลว่าแปลงกลับเป็น editable objects พร้อมประวัติและ constraints เดิมได้ครบ
- ความสามารถของ FreeCAD ไม่ได้แปลว่าหน้า 3117 Workbench มีคำสั่งนั้นแล้ว ต้องระบุเป็น implemented, inherited host capability หรือ planned ให้ชัด
- เอกสาร/API ที่อ้างอิงบน branch main หรือหน้า stable อาจเปลี่ยนภายหลัง release ต้องเก็บ commit/tag และ dependency manifest ของตนเอง
- การรองรับ RVT/RFA และการถ่ายโอน Family constraints ไม่ได้เกิดขึ้นจากการรองรับ IFC และไม่ได้อยู่ในขอบเขตที่ยืนยันแล้วของ scaffold นี้
- หลักฐานนี้เป็นการค้นคว้าและตรวจเอกสาร ไม่ใช่ผลทดสอบ GUI ของ FreeCAD บนเครื่องผู้ใช้


## เอกสารเสริมสำหรับสถาปัตยกรรมและการเริ่มโครงการ

- **S15** [FreeCAD FCStd format](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/File_Format_FCStd.md): geometric/parametric document กับ GUI representation แยกกันใน native file; archived snapshot ตามข้อจำกัด S04
- **S16** [IfcOpenShell geometry creation](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_creation.html): authoring geometry และความสัมพันธ์กับ type/material; แอปยังต้องรักษาความสอดคล้องของข้อมูลเอง
- **S17** [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html): ข้อความ license ที่เสนอสำหรับ source ใหม่ ให้ดูเงื่อนไขฉบับเต็มใน LICENSE
- **S18** [FreeCAD Arch API source](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/BIM/Arch.py): API ที่ใช้ใน workbench probe ต้องทดสอบกับ build จริงก่อนประกาศรองรับ
- **S19** [GitHub repository quickstart](https://docs.github.com/en/repositories/creating-and-managing-repositories/quickstart-for-repositories): ขั้นตอนสร้าง repository; โครงนี้ยังไม่ถูกเผยแพร่ไป remote
