# Windows acceptance — Types and Quantities v0.5.0

สถานะเริ่มต้น: **Pending — ยังไม่มีบันทึกการรันบน Windows จริง**

**Known host blocker:** FreeCAD 1.1.4 บน Linux เกิด native SIGSEGV ในลำดับสร้าง–ลบวัตถุ–Undo สองครั้ง–แก้ไขใหม่–Undo/Redo และทำซ้ำได้ด้วยวัตถุมาตรฐานโดยไม่ติดตั้ง 3117 ตาม [HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md) **ผลของลำดับนี้บน Windows ยังไม่ทราบ** ผล Undo/Redo ปกติหรือ public feature macro ที่ผ่านไม่แทนเกณฑ์ W62 ด้านล่าง การทำซ้ำอาจปิด FreeCAD ทั้ง process และทำให้งานที่ยังไม่บันทึกสูญหาย ต้องใช้ process/profile ทิ้งได้ บันทึกงานและปิดเอกสารอื่นทั้งหมดก่อนทดสอบ

เป้าหมาย FreeCAD 1.1.4 x86_64 ที่ดาวน์โหลดจาก [release ทางการ](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4) ใช้ผู้ใช้ทั่วไป ติดตั้งผ่าน macro ใน ZIP และปิด/เปิด FreeCAD ทุกหน้าต่างหลังติดตั้ง

## บันทึกสภาพแวดล้อม

| รายการ | ค่าจากเครื่องทดสอบ |
|---|---|
| วันที่ / ผู้ทดสอบ | Pending |
| Windows version / build / architecture | Pending |
| FreeCAD version / build hash | Pending |
| Python / Qt | Pending; ดู Host Information |
| Workbench ZIP SHA-256 | Pending |
| GPU / driver | Pending |
| User data path จาก FreeCAD | Pending |

## ขั้นตอนตรวจรับ

| รหัส | ขั้นตอน | เกณฑ์ผ่าน | ผล |
|---|---|---|---|
| W01 | แตก ZIP ใน path ภาษาไทย แล้วรัน Install macro | แสดงตำแหน่งติดตั้งของ host; ไม่ต้องใช้ administrator | Pending |
| W02 | ปิด FreeCAD ทุกหน้าต่าง เปิดใหม่ และเลือก 3117 BIM Studio | มี toolbar/menu; ไม่มี error ใน Report view | Pending |
| W03 | Create Project พร้อม L00/L01 | มี native Project และสองระดับในต้นไม้ | Pending |
| W04 | เพิ่ม Level และสร้าง Grid X/Y พร้อมชื่อ | เลือกได้ เส้น/วงกลม/ข้อความแสดงถูกตำแหน่ง | Pending |
| W05 | เลือก Grid ผูก L01 แล้ว Edit Selected ของ L01 เป็น 3300 mm | Grid เปลี่ยน Z ตาม; Undo ครั้งเดียวคืนหลาย property ได้; Redo คืนผลใหม่ | Pending |
| W06 | แก้ Elevation ผ่าน native Data/Properties | geometry และ link สอดคล้อง; Undo/Redo ใช้งานได้ | Pending |
| W07 | ยกเลิกฟอร์ม / ส่งชื่อว่างหรือระยะไม่ถูกต้อง | ไม่สร้าง object หรือ transaction ค้าง | Pending |
| W08 | ลบ Level ที่ Grid ยังอ้างอิง | ปฏิเสธพร้อมคำแนะนำ; โมเดลไม่กระโดดไป Z=0 | Pending |
| W09 | Save ใน path/ชื่อภาษาไทย ปิดโปรแกรมทั้งหมด แล้วเปิดใหม่ | Project/Level/Grid, IDs, proxy และกริด labels คืนครบ | Pending |
| W10 | แก้ Level หลังเปิดใหม่ และ Undo/Redo | dependency และ geometry ยังทำงาน | Pending |
| W11 | รัน Run_3117_Smoke_Test macro | gui-smoke-report.json ระบุ passed พร้อม OS/FreeCAD version | Pending |
| W12 | ติดตั้งซ้ำ แล้วใช้ Manage macro เพื่อคืนรุ่น/ถอนติดตั้ง | สำรองนอก Mod; ไฟล์โครงการไม่ถูกลบ; restart แล้วสถานะถูกต้อง | Pending |
| W13 | สร้าง Wall Type 200 mm แล้วสร้างผนังสองชิ้นจาก type เดียว | เลือก base/top levels ได้; มี solid จริงและ type link เดียวกัน | Pending |
| W14 | สร้าง Door 900 × 2100 mm ในผนัง 6000 × 3000 × 200 mm | ช่องถูกตัดผ่านความหนา; NetVolume = 3.222 m³ และยังเห็นช่องเมื่อซ่อน Door | Pending |
| W15 | เปลี่ยน Type เป็น 250 mm แล้ว Undo/Redo | ผนังทั้งสองและกรอบประตูเปลี่ยนตาม แล้วคืนค่าได้ | Pending |
| W16 | เปลี่ยน L01 เป็น 3300 mm | ผนังตามระดับ, Door ยังมีความสูงเดิม, NetVolume fixture = 3.582 m³ เมื่อ type 200 mm | Pending |
| W17 | ลดระดับยอดต่ำกว่า Door หรือลดผนังจน Door เลยปลาย | แจ้งเหตุผลและคืน state เดิม ไม่มีการแก้ครึ่งชุด | Pending |
| W18 | คลิกผิวผนังแล้ว Edit Selected เปลี่ยน start/end เป็นแนวเฉียง | แก้ authored Wall ได้; ช่องเปิดและกรอบตามตำแหน่งใหม่ | Pending |
| W19 | ย้าย Door ไป Host ใหม่แล้ว Undo/Redo | ผนังเก่าปิดช่อง ผนังใหม่เปิดช่องในหนึ่ง transaction | Pending |
| W20 | ลบ Door ผ่าน 3117 Delete Selected แล้ว Undo | ปิดช่องก่อน และคืนประตู/ช่องเปิดพร้อมกันหลัง Undo | Pending |
| W21 | ลบ referenced Wall/Type/Level หรือ native WallBody แยกเดี่ยว | ปฏิเสธและชี้คำสั่งที่ควรใช้ โมเดลไม่เหลือ orphan | Pending |
| W22 | ลบผนังที่ไม่มี Door หรือ Window ผ่าน 3117 Delete Selected แล้ว Undo | Wall และ WallBody หาย/คืนด้วยกัน | Pending |
| W23 | Save/ปิด FreeCAD ทั้งหมด/เปิดไฟล์ Architecture_Workbench ใหม่ | proxies, UUID, links และช่องเปิดคืนครบ; เปลี่ยน type/level และ Undo ต่อได้ | Pending |
| W24 | เปิดไฟล์ Foundation v0.1 ด้วย Workbench v0.5.0 | IDs เดิมอยู่ครบ; Grid/Level ยังแก้และ Undo ได้ | Pending |
| W25 | รัน Run_3117_Architecture_Test macro | architecture-gui-report.json ระบุ passed พร้อม Windows/FreeCAD/Qt จริง | Pending |

## Quantity / Exchange additions

| รหัส | ขั้นตอน | เกณฑ์ผ่าน | สถานะ |
|---|---|---|---|
| W26 | เปิด Quantities & Exchange | Wall/Door rows เท่าจำนวน authored UUID, หน่วย m/m²/m³ ชัด และไม่ซ้ำ WallBody | Pending |
| W27 | คลิกแถวและแก้ Level/Type พร้อม Undo/Redo | เลือกวัตถุถูกชิ้น ตาราง/รหัสเนื้อหาเปลี่ยนและคืนตามโมเดล | Pending |
| W28 | ส่ง CSV ใน path ภาษาไทย | Wall/Door CSV + metadata เปิดได้ ชื่อไทย/ตัวเลขถูกต้อง และ hashes ตรง | Pending |
| W29 | ส่ง IFC4 จาก native sample | schema/placement/relationships/geometry ผ่าน readback และ metadata บันทึกรุ่น dependency | Pending |
| W30 | แก้โมเดลหลังส่งออก | แสดงผลเก่า Stale และ expected-revision guard ปฏิเสธการส่งจาก preview เก่า | Pending |
| W31 | Cancel/overwrite/locked output | ยกเลิกไม่เขียนไฟล์ รายชื่อ sidecar ก่อนแทนที่ครบ และไม่ทับไฟล์ที่ไม่ยืนยัน | Pending |
| W32 | เปิด .FCStd ใหม่และทดสอบ dependency | UUID/revision คงเดิม, หาก IFC dependency ไม่มี CSV ยังใช้ได้พร้อมคำอธิบาย | Pending |
| W33 | รัน Run_3117_Exchange_Test macro | exchange-gui-report.json passed พร้อม Windows/FreeCAD/Qt/IfcOpenShell ที่รันจริง | Pending |

## Building Authoring additions

| รหัส | ขั้นตอน | เกณฑ์ผ่าน | สถานะ |
|---|---|---|---|
| W34 | Create Slab แบบสี่เหลี่ยมและ polygon เว้า | Top=Level+Offset, thickness ลงล่าง, area/volume ตรง; ขอบตัดตัวเองถูกปฏิเสธ | Pending |
| W35 | สร้าง Column และ Beam รวมแนวหมุน/ย้อนกลับ | พิกัดแกน/section/levels ตรงกับ Properties และ quantity rows | Pending |
| W36 | Join Slab กับสมาชิก แล้ว Undo/Redo/Unjoin | Reference/solid/net volume เปลี่ยนและคืนในหนึ่ง transaction | Pending |
| W37 | แก้ Thickness/Level จนตัดสมาชิกหมดหรือขาด | Rollback ทั้งชุด โมเดลเดิมไม่เสีย | Pending |
| W38 | Create/Rehost/Delete Window พร้อม Door บน Host | ช่องเปิดจริง ผนังเดิมปิดกลับ ตรวจ mixed overlap และ Undo คืนได้ | Pending |
| W39 | เปิด quantity 6 หมวด คลิกเลือกและ export | UUID/หน่วย/revision ตรง; CSV sidecars/IFC classes และ gross/net ตรง | Pending |
| W40 | Save/ปิดทั้งหมด/เปิด Building example ใหม่ | New proxies/UUID/JoinSlabs คงอยู่; แก้พื้นแล้วสมาชิกปรับตามและ Undo ได้ | Pending |
| W41 | รัน Run_3117_Building_Test macro จาก ZIP ที่ระบุ hash | building-gui-report.json passed พร้อม Windows/FreeCAD/Qt/IFC runtime จริง | Pending |

## Drawings and Sheets additions

| รหัส | ขั้นตอน | เกณฑ์ผ่าน | สถานะ |
|---|---|---|---|
| W42 | สร้าง Plan ผูก Level กับ Bottom/Cut/Top และ Scale | Cut holes/overhead ถูกต้อง; invalid/cancel ไม่เปลี่ยน history; Undo/Redo คืนค่า | Pending |
| W43 | สร้าง Section/Elevation ทิศ cardinal และ Depth | ทิศมอง/ขอบเขตตรง มี cut fill เฉพาะ Section | Pending |
| W44 | สร้าง Sheet 1–2 views แล้วเปิด Preview | A3/สเกล/ชื่อไทย/มิติ/แท็กอ่านได้; Fit/Pan/Zoom ทำงาน | Pending |
| W45 | แก้โมเดลขณะ Preview เปิด แล้วแก้ View Scale | model/drawing hashes เปลี่ยนแยกถูกชุด; Undo/Redo คืน; export เก่าแสดง Stale | Pending |
| W46 | ส่ง SVG/PDF ใน path ภาษาไทย และ Cancel/ยืนยัน overwrite | ไฟล์และ metadata ครบ, embedded fonts, แทนที่เฉพาะเมื่อยืนยัน และ source hashes ตรง | Pending |
| W47 | พิมพ์ A101 PDF A3 ด้วย Actual size / 100% | ระยะ 6500 mm ที่ 1:50 วัดได้ 130 mm บนกระดาษ; ตัวอักษร/เส้นไม่ถูกตัด | Pending |
| W48 | Save/ปิด FreeCAD ทุกหน้าต่าง/เปิด Drawings example ใหม่ | View/Sheet UUID/link/proxy คืนครบ; ดับเบิลคลิก Sheet และแก้โมเดล/Undo ต่อได้ | Pending |
| W49 | ลบ View ที่ Sheet อ้าง/Level ที่ Plan อ้าง และสร้าง Sheet สเกลไม่พอดี | ปฏิเสธอย่างมีเหตุผล, ไม่เผยแพร่ภาพเก่า/เปลี่ยนสเกลลับหลัง | Pending |
| W50 | รัน Run_3117_Drawings_Test macro จาก ZIP ที่ระบุ hash | drawings-gui-report.json passed พร้อม Windows/FreeCAD/Qt จริง | Pending |

แนบ `drawings-gui-report.json`, `building-gui-report.json`, `gui-smoke-report.json`, `architecture-gui-report.json`, `exchange-gui-report.json`, Screenshot, PDF ที่ตรวจ, FreeCAD Report view หากมีข้อผิดพลาด และผล W01–W50 ที่ตรวจด้วยผู้ใช้จริงใน issue/PR การรัน headless CI ของ Windows พิสูจน์ document API แต่ยังไม่แทนรายการ GUI เหล่านี้

หากพบ blocker ให้คงสถานะ development candidate ของรุ่นนี้ แก้และทดสอบรายการที่เกี่ยวข้องก่อนประกาศ Windows-ready

## Types and Quantities additions

| ID | การตรวจ Windows จริง | ผลที่ต้องได้ | สถานะ |
|---|---|---|---|
| W51 | ติดตั้ง ZIP v0.5.0 ใน user profile/path ที่มีอักษรไทย แล้ว restart | Catalogue/Schedules เปิดได้ด้วย host Qt | Pending |
| W52 | สร้าง Material และ shared Type ครบหก Category; assign/duplicate/detach | Category/UUID/link ถูกต้อง; typed dimensions read-only | Pending |
| W53 | เปลี่ยน Type ที่หลายชิ้นส่วนใช้ แล้ว Undo/Redo | Geometry/quantity/member assignment เปลี่ยนพร้อมกันใน transaction เดียว | Pending |
| W54 | เพิ่ม Wall/Slab layers และเปลี่ยนความหนาชั้น | Layer order ถูกทิศ; รวม material gross/net เท่ากับ product solid | Pending |
| W55 | ขยายหลาย openings หรือ cutters จนเกิด invalid combined model | Reject ก่อนแก้ source และรักษา Redo เดิม | Pending |
| W56 | สร้าง/กรอง/จัดเรียง/รวมกลุ่ม Schedule | distinct UUID count ไม่ซ้ำตามจำนวน layers; Schedule definition อยู่ใน FCStd | Pending |
| W57 | Edit Row ชื่อ/Type/ตำแหน่ง; แก้จากตารางเก่าหรือเขียน quantity | Valid edit หนึ่ง Undo; stale/computed quantity ถูก reject | Pending |
| W58 | CSV ใหม่/overwrite/cancel; ชื่อไทยและชื่อเริ่ม = | payload+metadata สอดคล้อง, two revisions, formula-like text escaped | Pending |
| W59 | Save/ปิด FreeCAD ทุกหน้าต่าง/เปิด types example ใหม่ | Catalogue, links, Schedule proxies/definitions และ geometry คืนครบ | Pending |
| W60 | ส่ง IFC ใหม่แล้วนำเข้าโปรแกรม BIM ที่ระบุชื่อ/รุ่น | product GUIDs, types, material/layer order, placements และ quantities ตรงกัน | Pending |
| W61 | รัน Run_3117_Types_Test จาก ZIP ที่ระบุ SHA256 | types-gui-report.json passed พร้อม Windows/FreeCAD/Qt จริง | Pending |
| W62 | ใน process/profile ทิ้งได้ที่ไม่มีงานค้าง ทำซ้ำ native และ 3117 history branch ตาม Host compatibility: สร้างและลบวัตถุในคนละ transaction, Undo สองครั้ง, commit การแก้ใหม่ให้วัตถุที่เหลือ แล้ว Undo/Redo โดยไม่ล้าง history | ไม่ crash; UUID/properties/geometry/scene graph และการแก้ต่อยังถูกต้อง บันทึก build/hash, log, process exit และผลของทั้งสองลำดับแยกจาก feature macro; JSON ที่เขียนไม่จบไม่ถือว่าผ่าน | Pending — Windows unknown |

แนบผล W51–W62 พร้อม `types-gui-report.json` และหลักฐาน history branch แยกต่างหาก หาก W62 ล้มเหลวให้คง failed host gate แม้รายการอื่นผ่าน และอย่าทำซ้ำใน process ที่เปิดงานจริงอยู่
