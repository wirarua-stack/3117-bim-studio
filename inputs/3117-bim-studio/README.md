# 3117 BIM Studio — Types and Quantities

Free and open source BIM authoring on FreeCAD: native building elements, shared types, material layers, schedules, drawings and IFC4 exchange.

**สถานะ: v0.5.0 development candidate สำหรับ FreeCAD 1.1.4 — Windows acceptance ยังรอตรวจรับ**

**ยังไม่ผ่านเกณฑ์ Pilot/production:** พบ native GUI crash ใน FreeCAD 1.1.4 บน Linux เมื่อสร้าง–ลบวัตถุ, Undo สองครั้ง, แก้ไขเป็น branch ใหม่ แล้ว Undo/Redo การทดสอบด้วย Part::Feature โดยไม่ติดตั้ง 3117 ให้ผลเดียวกัน อาจสูญเสียงานที่ยังไม่บันทึก ใช้ชุดนี้กับสำเนา/โครงการทดสอบ และอ่าน [Host compatibility](docs/HOST_COMPATIBILITY.md) ก่อนทดลอง ผลฟังก์ชันที่ผ่านไม่ปิดเกณฑ์นี้ และยังไม่มีผลยืนยันบน Windows

เป้าหมายคือ workflow อาคารที่เชื่อม Project, Level, Grid, Type, Instance, Host, View, Schedule และ Sheet กับโมเดลเดียวกัน `.FCStd` เป็นข้อมูลหลัก การแก้ไขใช้ native document transaction และ Undo/Redo ส่วน CSV/IFC/PDF เป็นผลส่งออกจาก revision ที่ระบุ

## เริ่มใช้งาน

1. ติดตั้ง FreeCAD 1.1.4 ตามแพลตฟอร์มและแตก ZIP `3117_BIM_Studio_v0_5_0_FreeCAD.zip`
2. รัน `Install_3117_BIM_Studio.FCMacro` ตรวจตำแหน่งติดตั้งที่โปรแกรมแสดง แล้วยืนยันติดตั้ง
3. ปิด/เปิด FreeCAD ใหม่ เลือก Workbench **3117 BIM Studio**
4. เปิด `examples/types/Types_Quantities_Workbench.FCStd` แล้วเปิด **Type Catalogue** และ **Schedules**
5. แก้ Type เพื่อเปลี่ยนสมาชิกทั้งกลุ่ม ใช้ Edit Row เพื่อแก้ชิ้นส่วนต้นทาง และตรวจ Undo/Redo ก่อนส่งออก

[คู่มือติดตั้ง](packaging/INSTALL_TH.md) · [Types / Materials / Schedules](docs/TYPES_AND_QUANTITIES.md) · [Drawings / Sheets](docs/DRAWINGS_AND_SHEETS.md) · [Building Authoring](docs/BUILDING_AUTHORING.md) · [Quantity / IFC](docs/QUANTITY_EXCHANGE.md)

## สิ่งที่เพิ่มใน v0.5.0

| ส่วน | พฤติกรรมที่ใช้งานได้ |
|---|---|
| Type Catalogue | WallType เดิมและ ElementType สำหรับ Slab/Column/Beam/Door/Window; create/edit/duplicate/assign/detach และ dependency guards |
| Shared dimensions | ขนาดที่ Type ควบคุมเป็น read-only ที่ Instance; เปลี่ยน Type แล้ว geometry/ช่องเปิด/รอยต่อ/ปริมาณเปลี่ยนตาม |
| Materials | Native UUID, ชื่อและ Code; homogeneous assignment หรือ ordered layers ของ Wall/Slab |
| Material quantities | ตัด solid จริงตามชั้นและรวมกลับเท่ากับปริมาตรต้นทาง พร้อม gross/deduction/net และ assignment coverage |
| Schedules | Native definitions, Category/Level/Type/name filters, sort, group by Type/Material, distinct source counts |
| Edit Row | เลือก UUID ต้นทางแล้วแก้ชื่อ Type และค่ารายตัวที่รองรับในหนึ่ง transaction; ค่าปริมาณคำนวณเป็น read-only |
| CSV / IFC | Type/material sidecars, Schedule CSV+metadata, IFC types/materials/layer usages และ serialized readback |
| Compatibility | ไฟล์เดิมที่ยังไม่ใช้ catalogue features คง building hash และ CSV payload เดิมตาม regression fixture |

การเปลี่ยน Type ตรวจ proposed state ของทุกสมาชิกก่อนเปิด transaction รวมกรณีช่องเปิดหลายชิ้นขยายพร้อมกันและ Slab cutters หลายชิ้นตัด member เดียวกัน ข้อเสนอที่ผิดต้องคง Undo/Redo เดิม

Material rows เป็นการแจกแจงของ product quantities **อย่าบวกซ้ำกัน** และการ assign วัสดุครบโมเดลไม่ใช่ BOQ ที่ครบทุกงานก่อสร้าง ไม่มีราคาวัสดุ ค่าแรง เผื่อสูญเสียหรือน้ำหนักที่ระบบสมมติขึ้น

## ฐานความสามารถที่ใช้งานร่วมกัน

- Project, Levels, Grid และ persistent UUIDs; พิกัด native เป็น mm
- Wall ผูก Base/Top Level; Door/Window อ้าง Wall และตัดช่องเปิดจริง
- Slab polygon แนวราบผูก Level + top offset; Column สี่เหลี่ยมแนวดิ่ง; Beam สี่เหลี่ยมแนวราบ
- รอยต่อ Slab priority สำหรับ Column/Beam ตามรายการ JoinSlabs ที่ระบุ; ไม่มี global overlap deduction
- Plan/Section/Elevation จาก OCCT solids, view range, global hidden-line removal, มิติรวมและ source tags
- A3 Sheet 1–2 views ที่ scale ชัดเจน, vector SVG/PDF และฟอนต์ Sarabun พร้อม OFL notice
- Quantity / IFC และ Drawing publication ตรวจ freshness ก่อนเขียนผลลัพธ์; Schedule ตรวจ model revision และ schedule revision

ตัวอย่าง `examples/types/` มี 33 products, 6 Types, 7 Materials, 55 material rows, 9 Schedules, 4 Views และ 2 Sheets ขอบเขต solids และ UUIDs ของอาคารเดิมคงไว้ ดู [README ตัวอย่าง](examples/types/README.md) และ `types-example.json` ที่บันทึก hashes/ข้อทดสอบ

ตัวอย่างรุ่นเก่าอยู่ใน `examples/freecad`, `examples/exchange`, `examples/building` และ `examples/drawings` พร้อมไฟล์ผลส่งออกของ revision เดิม PDF/SVG ของตัวอย่างเก่าไม่ได้เปลี่ยน metadata ตาม Type ที่เพิ่มในรุ่นใหม่ หากใช้โมเดล typed ให้ export แบบจาก FCStd รุ่นนี้อีกครั้ง

## การตรวจรับ

ผลที่รันจริงแยกตาม runtime อยู่ใน [VERIFICATION.md](docs/VERIFICATION.md) และ JSON evidence; ไม่มีการนำการติดตั้งสำเร็จมาแทนผลทดสอบ GUI หรือใช้ผล Linux แทน Windows

รัน **`Run_3117_Types_Test.FCMacro`** เพื่อทดสอบ Type Catalogue/วัสดุ/Schedules ผ่านหน้าต่างจริง และใช้ `Run_3117_Smoke_Test`, `Run_3117_Architecture_Test`, `Run_3117_Exchange_Test`, `Run_3117_Building_Test`, `Run_3117_Drawings_Test` สำหรับฐานเดิม แต่ละ macro สร้างเอกสารทดสอบของตนเองพร้อมรายงาน ไม่ใช้โครงการลูกค้าเป็น fixture

## สำหรับผู้พัฒนา

อ่าน [AGENTS.md](AGENTS.md), [Architecture](docs/ARCHITECTURE.md) และ [Acceptance](docs/ACCEPTANCE.md) ก่อนแก้ Native runner ใช้ **19 process แยกกัน**: install, foundation/reopen, architecture/reopen, exchange/reopen, building/reopen, drawing_geometry, drawings/reopen, drawing_render, types/reopen, types_exchange/reopen และ schedules/reopen โหลด Workbench จากตำแหน่งติดตั้งจริง ดู [CI_HOSTS.md](packaging/CI_HOSTS.md)

```bash
python scripts/build_workbench_package.py --output out/3117_BIM_Studio_v0_5_0_FreeCAD.zip
```

Source package มี GitHub Actions สำหรับ Linux/Windows และ issue templates พร้อมนำเข้า GitHub แต่การมี workflow ในไฟล์ไม่ใช่หลักฐานว่า remote CI ผ่านหรือ repository ถูกเผยแพร่แล้ว ดู [GitHub setup](docs/GITHUB_SETUP.md)

`src/bim3117` เป็น independent reference package รุ่น 0.0.1 สำหรับกฎ/fixture เดิม หน่วยเมตร JSON ของ package นี้ไม่ใช่ข้อมูลหลักของ Workbench Native exporter อยู่ที่ `workbench/bim3117_freecad/ifc_native.py` หากทดสอบ reference package ให้ใช้ virtual environment แยกจาก FreeCAD:

```bash
python -m venv .venv
# Activate this independent environment, then:
python -m pip install -e ".[ifc,test]"
python -m unittest discover -s tests -v
python -m bim3117 demo --output out/demo --ifc
```

## ขอบเขตและงานถัดไป

งานเร่งด่วนถัดไปคือปิด native history-branch crash พร้อมทดสอบโฮสต์ที่แก้แล้ว ก่อน **v0.9.0 Pilot** ซึ่งครอบคลุม Windows installation/upgrade, file migration/recovery, performance และ interoperability ตาม [Roadmap](docs/ROADMAP.md) ต้องตรวจ Windows จริงก่อนประกาศ Windows-ready

ยังไม่รวม family editor/formulas, arbitrary schedule columns/calculated fields, schedules on sheets, multilayer join priorities, wall-wall joins, curved/sloped geometry, roof/stair tools, MEP, structural analysis, .rvt/.rfa หรือ multiuser authoring แบบครบ workflow

โค้ดใช้ [GPL-3.0-or-later](LICENSE) Dependencies และฟอนต์มี license ของตนเอง ดู [THIRD_PARTY.md](THIRD_PARTY.md) ชุดติดตั้งไม่รวม FreeCAD/Qt binaries
