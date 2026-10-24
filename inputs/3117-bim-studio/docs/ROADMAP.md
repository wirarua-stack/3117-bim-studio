# แผนพัฒนาและเกณฑ์ผ่าน

สถานะ 23 ตุลาคม 2026: `v0.5.0 Types and Quantities` เพิ่ม shared types, native materials/layers, persistent schedules และ guarded source-row editing บนฐาน authoring/drawings เดิม ผลที่รันจริงอยู่ใน [VERIFICATION.md](VERIFICATION.md) ส่วน Windows acceptance ยัง pending

**Gate ที่ต้องปิดก่อนเลื่อนรุ่น:** native GUI history-branch crash ของ FreeCAD 1.1.4 Linux ถูกทำซ้ำได้ด้วย Part::Feature โดยไม่มี addon ดู [HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md) v0.5.0 จึงเป็น candidate ที่ยังไม่ผ่าน Pilot/production ขั้นถัดไปคือแก้หรือเลือก host ที่ผ่านกรณีเดิม แล้วทดสอบ regression และ Windows จริง ห้ามใช้ผล native command-line/IFC ที่ผ่านแทนเกณฑ์ GUI นี้

ลำดับ v0.2.0 จบ authoring/host relationship, v0.2.1 เชื่อม quantities/IFC, v0.3.0 เพิ่ม building categories, v0.4.0 เพิ่มแบบ และ v0.5.0 เพิ่ม Type Catalogue/วัสดุ/Schedules ตาม [TYPES_AND_QUANTITIES.md](TYPES_AND_QUANTITIES.md) งานถัดไปคือ **v0.9.0 Pilot** โดยให้ Windows, migration/recovery, performance และ interoperability เป็น gate ก่อนประกาศ production readiness. Annotation editor เต็มรูปแบบ, arbitrary schedule formulas และ schedules on sheets ยังอยู่นอกขอบเขต

## Milestones

| รุ่น | เป้าหมาย | เกณฑ์ผ่าน |
|---|---|---|
| v0.1.0 Foundation Workbench | Native Project/Levels/Grid, mm, fixed local origin, selection, persistent IDs, installer | Implementation พร้อมตรวจรับ; Windows จริงยังเป็น gate ก่อนประกาศ Windows-ready |
| v0.2.0 Walls and Hosted Doors | Wall type/instance, Base/Top Level, hosted door/real opening, change type/level และ derived gross/net quantities | Boolean solid, type/level/host dependency, rollback, Undo/Redo, fresh-process reopen และ v0.1 compatibility ผ่านตามหลักฐานจริง |
| v0.2.1 Quantity / Exchange Bridge | Rows/CSV จาก native objects, model revision, coverage mapping และ native IFC4 export | ปริมาณอ้าง Wall UUID/กฎ/หน่วยชัด และ IFC ผ่าน schema/placement/relationship พร้อมตรวจข้ามโปรแกรม |
| v0.3.0 Building Authoring | Slab, Column, Beam, Window และ Slab-priority joins | อาคาร 2 ชั้นสร้าง/แก้/Undo/reopen ได้; native/CSV/IFC ตรงตามกฎ พร้อม GUI และ external-app evidence |
| v0.4.0 Drawings and Sheets | Plan, section, elevation, view range, overall dimensions, source tags, A3 1–2 views และ SVG/PDF | Native definitions/Undo/reopen; เวกเตอร์มีสเกลและอ่านได้จริง; publication ตรวจ model revision + drawing revision |
| v0.5.0 Types and Quantities | Type catalogue, material layers, schedules, quantity rules และ CSV | Type fanout/atomic edit/Undo/reopen; material partitions conserve volumes; filters/groups/source UUIDs; legacy hash/CSV compatibility; serialized IFC types/material usages |
| v0.9.0 Pilot | Installer, file migration, recovery, performance และ interoperability | ผู้ใช้ทดลองทำโครงการที่กำหนดครบวงจร ไม่มี blocker ด้าน data loss/geometry/quantity |
| v1.0.0 | Release ตามขอบเขตที่ประกาศ | คู่มือ ตัวอย่าง regression evidence และ dependency manifest ครบ |
| หลัง v1.0 | Advanced families, MEP, analytical links, browser review และ collaboration | ทำทีละโมดูลพร้อม acceptance เฉพาะ |

Roof/stair templates จากแผนเริ่มต้นถูกแยกเป็นงานภายหลัง v0.3.0 เพื่อให้รุ่นนี้ตรงกับขอบเขต Slab → Column/Beam → Window → limited joins ที่กำหนด ไม่ถือว่า roof/stair เสร็จแล้ว

## แผน 12 สัปดาห์แรก

| สัปดาห์ | งาน | ผลตรวจรับ |
|---|---|---|
| 1–2 | Pin FreeCAD build, ติดตั้ง workbench, units/origin, persistent properties, transaction spike | สร้าง object แล้ว save/close/reopen/Undo ได้ |
| 3–4 | Levels/Grid, selection, wall type/instance, Properties, baseline snap | เขียนผนังผ่านเมาส์และแก้ค่าจาก Properties ได้ |
| 5–6 | Hosted door/opening, dependency, type and level updates | ย้าย host แล้วช่องเปิดตาม และ invalid edit rollback |
| 7–8 | Gross/net quantities, CSV, deterministic revisions, save/migration fixture | ปริมาณตรงตัวเลขอิสระ ไม่ใช้ค่าจาก geometry cache เก่า |
| 9–10 | Slab ใน vertical slice, floor plan, section ขั้นต้น, tags | แปลนและตารางอ้าง revision เดียวกับ 3D |
| 11–12 | IFC4 coverage, cross-app inspection, Windows installation/recovery | รายงาน pass/fail พร้อมโมเดลทดสอบและรายการข้อจำกัด |

หากขั้นหนึ่งไม่ผ่าน ให้แก้ blocker ก่อนเลื่อนรุ่น ห้ามเติมฟังก์ชัน MEP/AI เพื่อชดเชยปัญหา host relation หรือ data persistence

## กรอบทรัพยากร

ประมาณการตั้งต้น: developer เต็มเวลา 3 คน (CAD/geometry, BIM/domain, UI/integration), BIM product owner จากงานจริง และ QA บางเวลา Vertical slice ประมาณ 8–12 สัปดาห์ Building MVP เดือนที่ 4–8 Pilot เดือนที่ 8–12 นับจากเริ่มทีมพร้อมทำงาน ตัวเลขเป็นประมาณการวางแผน ไม่ใช่ผล benchmark หรือใบเสนอราคา ต้องทบทวนหลังสัปดาห์ 2 และ 6

## Definition of done

1. พฤติกรรมตรง acceptance ของ issue และไม่มีการเปลี่ยนหน่วย/พิกัดโดยเงียบ
2. กรณีแก้ model มี Undo/Redo/rollback และ reopen fixture ที่เกี่ยวข้อง
3. IFC change มี schema/relationship/quantity evidence ตามขอบเขต
4. UI change ที่กระทบการทำงานมีการทดสอบ host จริง ไม่รับเพียง compile ผ่าน
5. README/limitations/changelog และ dependency notices ตรงกับ release
6. ไม่มีข้อมูลลูกค้าจริงหรือ credential ใน fixture/repository

## งานที่วางไว้ภายหลัง

MEP ต้องมี connector topology, system identity, elevation และ slope ก่อน automatic routing ส่วน AI ต้องเรียก command API เดียวกับ UI พร้อมรายการเปลี่ยนแปลงและ Undo ห้ามแก้ document ผ่านช่องทางลัดที่ข้าม validation

Multiuser authoring ต้องออกแบบ element ownership/conflict/version history โดยเฉพาะ การ sync ไฟล์ FCStd ผ่าน Drive เพียงอย่างเดียวไม่ทำให้แก้พร้อมกันได้
