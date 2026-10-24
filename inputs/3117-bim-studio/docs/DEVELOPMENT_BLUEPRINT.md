# แผนพัฒนา 3117 BIM Studio

## 1 เป้าหมายของโครงการ

สร้างซอฟต์แวร์ BIM สำหรับงานอาคารที่ใช้ฟรี เปิด source code บน GitHub และสามารถสร้าง แก้ไข ตรวจสอบ และส่งต่อข้อมูลอาคารได้ ผู้ใช้ควรทำงานด้วยองค์ประกอบที่มีความหมาย เช่น ผนัง เสา คาน พื้น ประตู และหน้าต่าง พร้อมระดับชั้น ประเภทวัตถุ คุณสมบัติ วัสดุ และความสัมพันธ์กับองค์ประกอบอื่น

แนวคิดที่ยึดจาก workflow แบบ Revit คือ **โมเดลเดียวสร้างหลายผลลัพธ์** การแก้โมเดลควรทำให้แปลน รูปด้าน รูปตัด และตารางที่เกี่ยวข้องอัปเดตอย่างตรวจสอบได้ เป้าหมายคือทำงาน BIM ได้ต่อเนื่อง ตั้งแต่สร้างองค์ประกอบจนถึงแบบและปริมาณ ไม่ใช้ความเหมือนของหน้าตาโปรแกรมเป็นเกณฑ์ความสำเร็จหลัก

ชื่อทำงานเสนอเป็น **3117 BIM Studio** และ repository เป็น `3117-bim-studio` เอกสารนี้เป็นข้อเสนอการพัฒนา ฉบับ 0.1 วันที่ 23 ตุลาคม 2026 ส่วน source scaffold เริ่มที่ `0.0.1` ยังไม่ได้เผยแพร่ repository สาธารณะ

สมมติฐานเริ่มต้นคือ Windows desktop เป็นแพลตฟอร์มหลัก เพราะต้องใช้เครื่องมือเขียนแบบและจัดทำเอกสารหน้างานอาคาร หลังผ่าน pilot จึงขยายแพ็กเกจ Linux/macOS และใช้ browser/iPad สำหรับตรวจแบบและประชุมประสานงาน

## 2 ฐานโอเพนซอร์สที่เลือก

แนะนำ **FreeCAD BIM + 3117 Workbench + IfcOpenShell** โดยใช้ FreeCAD เป็น host ไม่ fork source ทั้งโปรแกรมในรอบแรก ข้อเสนอนี้ช่วยให้ทีมเริ่มจาก geometry kernel, document, parametric recompute และระบบแบบที่มีอยู่ แล้วลงแรงกับ workflow อาคาร การจัด Properties และความสัมพันธ์ข้อมูล

| ตัวเลือก | ความสามารถจากต้นทาง | บทบาทที่เสนอ |
|---|---|---|
| FreeCAD และ integrated BIM | Parametric modeler, BIM objects, Python API, Qt, geometry kernel และ TechDraw | Desktop host ของรุ่นแรก |
| IfcOpenShell | อ่านเขียน IFC, authoring API, geometry และเครื่องมือตรวจข้อมูล | IFC export, validation และ mapping |
| Bonsai บน Blender | Native IFC authoring โดยใช้ IFC เป็นข้อมูลหลัก | ทางเลือกหลักหากต้องการ IFC-native และตัวตรวจข้ามโปรแกรม |
| That Open Components และ web-ifc | เครื่องมือ BIM บน browser และ library อ่านเขียน IFC | Web viewer/review ในระยะถัดไป |

FreeCAD ระบุว่า integrated BIM รวม BIM, Native-IFC และ Arch ตั้งแต่รุ่น 1.0 มีวัตถุพาราเมตริกและทำแบบร่วมกับ TechDraw [S01, S03, S04] ส่วน Bonsai ใช้แนว IFC-native [S05, S06] ทั้งสองแนวมีเหตุผล แต่ไม่ควรสร้างสองระบบข้อมูลหลักที่แก้ไขได้พร้อมกัน

เอกสาร upstream บางส่วนเป็น archived snapshot จึงใช้ยืนยันแนวทางและความสามารถพื้นฐานเท่านั้น การเลือก FreeCAD build และ dependency รุ่นจริงต้องบันทึกผลทดสอบใน foundation spike ห้ามใช้คำว่า latest แทน version contract

## 3 ขอบเขตรุ่นแรก

รุ่นทดลองต้องทำหนึ่ง workflow ให้ครบก่อนขยายทุก discipline อาคารตัวอย่างหลักเป็นอาคาร 2 ชั้นขนาดเล็กประมาณ 100–300 ตารางเมตร มีผนังตรง เสา คาน พื้น ช่องเปิด บันไดอย่างง่าย และหลังคาแบบจำกัดชนิด โดยตัวเลขนี้เป็นขนาด fixture ที่เสนอ ไม่ใช่ขีดจำกัดทางเทคนิคของผลิตภัณฑ์

| ระดับความสำคัญ | รายการ |
|---|---|
| ต้องมีใน foundation | Project, units, local origin, Levels, Grid, stable IDs, selection, Properties, transaction, Undo/Redo, save/open |
| ต้องมีใน authoring MVP | Wall, slab, beam, column, door, window; type/instance; hosted openings; limited joins; IFC4 export |
| ต้องมีใน drawing MVP | Floor plan, section, elevation, dimensions, tags, schedule, sheet และ PDF ตามชุดแบบที่กำหนด |
| พัฒนาหลังผ่าน pilot | Advanced roofs/stairs, rooms/spaces เต็มระบบ, Family Editor, complex materials, MEP connectors/systems |
| ระยะยาว | Clash coordination, structural analytical links, web review, multiuser authoring และ AI command assistant |

งานวิเคราะห์ออกแบบโครงสร้างและการตรวจตามมาตรฐานวิศวกรรมเป็นโมดูลแยก การมี BIM ของคาน/เสาไม่ได้ยืนยันว่าได้ analytical model หรือผลออกแบบกำลังรับแรงที่ถูกต้องแล้ว

## 4 สถาปัตยกรรมข้อมูล

กำหนด `.FCStd` เป็น **แหล่งข้อมูลหลักสำหรับการสร้างและแก้ไข** ใน MVP ให้ FreeCAD document เก็บองค์ประกอบ พารามิเตอร์ ความสัมพันธ์ UUID และชนิดวัตถุด้วย native persistent properties [S15] โค้ด 3117 รับผิดชอบกฎข้อมูลและลำดับคำสั่งผ่าน adapter

IFC เป็นข้อมูลส่งออกของ model revision หนึ่ง ๆ การนำเข้า IFC ในช่วงแรกเป็น linked reference ที่ดู ตรวจ property และประสานพิกัดได้ การแปลงเป็นวัตถุพาราเมตริกที่แก้ไขได้ต้องเป็นคำสั่งเฉพาะ จำกัดชนิด และมี coverage report

รูปทรง B-rep, display mesh, plan cache และ schedule cache มีหน้าที่ต่างกัน ห้ามใช้ mesh สำหรับแสดงผลเป็นข้อมูลหลักแทนพารามิเตอร์ ทุกผลลัพธ์ต้องทราบ source revision หากกำลังคำนวณผลใหม่ให้แสดงสถานะอย่างชัดเจน และห้ามนำผลจากงาน background รุ่นเก่ามาทับเอกสารปัจจุบัน

JSON ใน reference core ที่แนบมามีไว้เป็น fixture และพิสูจน์กติกาเท่านั้น ไม่มีแผนให้ผู้ใช้แก้โมเดลเดียวกันทั้ง JSON, FCStd และ IFC พร้อมกัน

## 5 ระบบข้อมูลขององค์ประกอบ

| ข้อมูล | ความหมายและกติกา |
|---|---|
| ElementId | UUID ถาวร ไม่ใช้ชื่อที่ผู้ใช้แก้ได้หรือหมายเลขแถว IFC |
| TypeId | อ้างวัตถุประเภทที่ใช้ร่วมกัน เช่นผนังหนา 200 มม. |
| Category | Wall, Floor, Column, Beam, Door, Window และอื่น ๆ |
| Level constraints | Base level, top level หรือ unconnected height พร้อม offset และกฎเลือกใช้ |
| Host relation | ประตู/หน้าต่างอ้างผนัง พร้อม placement ในพิกัดของ host |
| Material definition | ชั้นวัสดุหรือหน้าตัด ไม่ปนกับสีการแสดงผล |
| Placement | ตำแหน่งและทิศทาง local ที่แปลงไป project/world coordinates ได้ |
| IFC identity | GUID mapping คงเดิมเมื่อแก้ตัวเดิม และสร้างใหม่เมื่อลอกตัวใหม่ |
| Version | schema, object, quantity-rule และ document revision |

Type parameter กับ instance parameter ต้องแยกให้ชัด เช่นความหนาผนังอยู่ที่ type ส่วนความยาวและระดับอยู่ที่ instance การแก้ type จึงอัปเดตสมาชิกทั้งกลุ่ม หากอนุญาต override ต้องแสดงสถานะและนโยบาย mapping ให้ชัด

ระบบหน่วยต้องมีจุดแปลงที่ตรวจได้ Reference core ใช้ SI เมตร ส่วน FreeCAD host ใช้หน่วยระยะภายในตาม API ของ host จึงต้องมี adapter แปลงหน่วยและ fixture ป้องกันความผิดพลาด 1,000 เท่า ไม่อาศัยค่าที่เห็นในหน้าจออย่างเดียว

สำหรับพิกัดสำรวจ ให้แยก local modeling origin, project north, true north และ world transform ตั้งแต่ต้น เพื่อไม่ลากโมเดลทุกชิ้นไปอยู่ห่าง origin จนกระทบความแม่นของการแสดงผล

## 6 พฤติกรรมคำสั่งและความสัมพันธ์

หนึ่งการกระทำของผู้ใช้ต้องย้อนกลับได้เป็นหนึ่ง Undo ตัวอย่างเช่นวางประตูต้องสร้างประตู ช่องเปิด และ host relation ใน transaction เดียว เมื่อเกิดข้อผิดพลาดต้อง rollback ทั้งชุด

ลำดับมาตรฐานคือรับ input ตรวจค่า เปิด transaction แก้ native properties regenerate ตรวจ geometry commit แล้วจึงแจ้งมุมมองและตาราง ระหว่างลากเมาส์เป็น preview และเมื่อคลิกยืนยันจึง commit ไม่สร้างประวัติหลายร้อยรายการจาก pointer move

เมื่อย้ายผนัง ประตูที่ host อยู่ต้องย้ายตาม เมื่อเปลี่ยนระดับบน ผนังที่ผูกกับระดับนั้นต้องเปลี่ยนสูงตาม ถ้าทำให้ประตูอยู่นอกขอบให้แสดงข้อผิดพลาดตาม policy ที่ประกาศ การลบผนังต้องแจ้งผลต่อองค์ประกอบที่พึ่งพา ไม่ทิ้ง orphan door

การอ้างอิงขอบ/ผิวสำหรับ dimension และ hosting ต้องมี semantic reference หรือ resolver ที่ทนต่อการคำนวณใหม่ ห้ามถือว่า Face1 จะเป็นผิวเดิมเสมอ

## 7 แนวทาง UX และ UI

ใช้เมนูหลักตามงาน ได้แก่ Project, Architecture, Structure, MEP, Annotate, View, Quantities และ Manage เมนูย่อยแสดงเมื่อใช้งานหมวดนั้น โดย MEP และโมดูลที่ยังไม่พร้อมต้องแสดงสถานะตามจริง

| ตำแหน่ง | หน้าที่ |
|---|---|
| ด้านบน | เมนูตามหมวดและเครื่องมือเฉพาะคำสั่ง |
| ด้านซ้าย | Project Browser แยก Levels, Views, Sheets, Schedules และ Types พับได้ |
| กลาง | พื้นที่ทำงาน 2D/3D และแท็บมุมมอง |
| ด้านขวา | Properties แยก Type / Instance เป็นกลุ่มอ่านง่าย |
| ด้านล่าง | หน่วย พิกัด snap สถานะคำสั่งและข้อความ validation |
| มุม viewport | Orbit, Pan, Zoom, Fit และเลือก standard view |

ข้อกำหนดการเลือกคือ highlight ชัด คลิกที่ว่าง deselect, Escape ยกเลิก preview, Ctrl+Z/Ctrl+Y ทำงานสม่ำเสมอ การลากซ้ายไปขวาเลือกวัตถุที่อยู่ในกรอบทั้งหมด และลากขวาไปซ้ายเลือกวัตถุที่กรอบตัดผ่าน กำหนด navigation preset แล้วทดสอบทิศ Orbit/Pan/Zoom จริง

ธีมโปรแกรมใช้ Navy–Orange ตามกลุ่มซอฟต์แวร์ 3117 พร้อมภาษาไทย/อังกฤษในระดับ interface โดยใช้ชื่อพารามิเตอร์และรหัสภายในที่คงที่เพื่อไม่ให้การเปลี่ยนภาษาเปลี่ยนข้อมูล

## 8 แบบ ตาราง และ Family

แบบควรสร้างจาก model revision เดียวกับตาราง โดยเริ่ม floor plan, section และ elevation ที่มี scale, cut plane, view range และ category visibility กำกับ จากนั้นเพิ่ม dimensions, tags, line weights, hatch, sheet placement และ PDF ก่อนถือว่าใช้ทำชุดแบบได้จริง

แยก model geometry ออกจาก 2D symbolic representation เช่นแนวเปิดประตูในแปลน เมื่อเปลี่ยน type ประตูทั้ง geometry และสัญลักษณ์ต้องสัมพันธ์กัน ไม่วาดแบบอีกชุดที่ขาดความเชื่อมโยงกับโมเดล

Family รุ่นแรกควรเป็น template/type catalogue ที่มีพารามิเตอร์ชัดเจน เช่นผนังชั้นวัสดุ เสาสี่เหลี่ยม คานสี่เหลี่ยม ประตูและหน้าต่างมาตรฐาน ต่อมาจึงเพิ่ม graphical editor, formula, constraints และ nested components การแจก Family library ต้องมี license ของ asset แยกจาก license ของโปรแกรม

ตารางเริ่มจาก count, length, gross/net area, volume และ material quantities ควรแสดงกฎการหักช่องเปิด การปัดเศษ และวิธีจัดการรอยต่อ ราคา BOQ เป็นข้อมูลคนละชั้น มีแหล่งราคา วันที่ และเงื่อนไข ไม่ฝังราคาสมมติเป็นปริมาณจากโมเดล

## 9 การเชื่อม OpenBIM และระบบ 3117

เริ่มส่งออก IFC4 ของชนิดที่รองรับ พร้อม project/site/building/storey containment, type assignment, properties, material และ opening/filling relation ตามขอบเขตที่ทดสอบ IfcOpenShell ให้ API สำหรับ authoring และ geometry แต่ตัวแอปยังต้องรักษาความสอดคล้องของ type กับรูปทรงเอง [S16]

การทดสอบต้องตรวจทั้ง schema, IDs, units, placements, geometry และปริมาณ และเปิดดูด้วยโปรแกรมอีกตัว การเขียน IFC แล้วเปิดกลับด้วย library เดียวกันอย่างเดียวไม่ยืนยัน interoperability ของทั้งผลิตภัณฑ์

การเชื่อม Site Agent ในอนาคตใช้ published building geometry, origin และทิศเหนือ ส่วน Structural Workspace รับองค์ประกอบพร้อม mapping ไป analytical model ที่ตรวจสอบได้ Cost Database รับ quantity revision และรหัสงานร่วมกัน ทุกการเชื่อมควรเริ่มจาก interface contract และ fixture ไม่ถือว่าฐานโค้ดเดิมเข้ากันโดยอัตโนมัติ

## 10 GitHub และวิธีพัฒนาร่วมกัน

ใช้ repository เดียวก่อน แยก application/domain/adapters/UI/docs/tests ชัดเจน ให้ main เป็น branch ที่ผ่านการทดสอบแล้ว งานใหม่อยู่ feature branch และรวมด้วย pull request ที่ระบุปัญหา พฤติกรรมใหม่ และหลักฐานตรวจรับ

GitHub Actions ควรตรวจ Python contracts บน Windows/Linux และ job IFC แยกที่ติดตั้ง dependency ที่ pin ไว้ก่อน ส่วน FreeCAD GUI และการเปิด IFC ข้ามโปรแกรมต้องมี test matrix เพิ่ม ไม่ใช้สถานะเขียวของ Python tests แทน gate ทั้งหมด

Repository ต้องมี README, LICENSE, CONTRIBUTING, THIRD_PARTY, ADR, issue templates, PR template, changelog และ regression fixtures เก็บ model ลูกค้าจริงแยกจาก public repository ใช้ตัวอย่างสังเคราะห์ที่ตรวจสอบได้สำหรับรายงาน bug

โค้ดใหม่ของ scaffold เสนอ GPL-3.0-or-later เพื่อให้การแจกส่วนดัดแปลงยังอยู่ภายใต้เงื่อนไขซอฟต์แวร์เสรีตาม license ส่วน FreeCAD, IfcOpenShell, Bonsai และ web stack ใช้ license ของต้นทาง ต้องตรวจตามรายการ dependency ที่แจกจริง [S02, S07, S08, S11, S13, S17] การเปิด source บน GitHub และการแจกใช้ฟรีเป็นคนละการตัดสินใจ โครงการนี้ตั้งใจทำทั้งสองอย่าง

## 11 ลำดับพัฒนาและทรัพยากร

เริ่มด้วย foundation spike 2–3 สัปดาห์ เลือก host build, ทดลอง persistent properties, Undo, save/reopen และ IFC จากนั้นทำ vertical slice หนึ่งห้องให้ครบภายในกรอบประมาณ 8–12 สัปดาห์ รวม foundation แล้วจึงขยายเป็น building MVP

ประมาณการนี้สมมติทีม developer 3 คน ได้แก่ CAD/geometry, BIM/domain และ UI/integration พร้อม BIM product owner และ QA บางเวลา Building MVP อยู่ประมาณเดือนที่ 4–8 และ pilot ประมาณเดือนที่ 8–12 โดยต้องปรับหลัง spike ตามผลจริง ไม่ใช่กำหนดส่งมอบที่รับประกัน

รุ่น v1.0 ควรหมายถึงขอบเขตที่ประกาศใช้งานได้และผ่านการทดสอบ ไม่ใช้หมายเลขรุ่นเพื่อสื่อว่าทัดเทียม Revit ทุกฟังก์ชัน การพัฒนาสู่ authoring ครบหลาย discipline เป็นงานต่อเนื่องหลายปี

## 12 เกณฑ์เริ่มต้นที่ตรวจได้

ตัวอย่างผนังเดี่ยวแนวตรงยาว 6.00 เมตร สูง 3.00 เมตร หนา 0.20 เมตร มีช่องประตู 0.90 × 2.10 เมตร โดยไม่คิดรอยต่อกับผนังอื่น จะได้พื้นที่ด้านข้างสุทธิ 16.11 ตารางเมตร และปริมาตรสุทธิ 3.222 ลูกบาศก์เมตร เมื่อแก้สูงเป็น 3.30 เมตร ต้องเป็น 17.91 ตารางเมตร และ 3.582 ลูกบาศก์เมตร Undo ต้องกลับค่าทั้งข้อมูลและผลลัพธ์ได้

หลังผ่านกรณีเล็กนี้ จึงตรวจห้องหนึ่งห้องที่มีพื้น กริด แปลน 3D และตารางใน revision เดียวกัน รวมการบันทึกเปิดใหม่และ IFC ข้ามโปรแกรม ชุด scaffold ปัจจุบันพิสูจน์ได้เฉพาะส่วนที่ระบุใน Verification ไม่ถือว่าผ่าน host GUI gate โดยอัตโนมัติ

งานถัดไปที่เสนอคือ **v0.1.0 Foundation Workbench**: ติดตั้งชุด 3117 ใน FreeCAD บน Windows เลือก version baseline สร้าง project/levels/grid และเชื่อมคำสั่งแก้ไขกับ document transaction ให้ใช้งานได้จริง ก่อนเริ่มตกแต่ง UI เต็มรูปแบบ

## แหล่งอ้างอิง

รหัส S01–S19 และรายการอ่านเพิ่มเติมอยู่ใน `docs/SOURCES.md` แต่ละการตัดสินใจทางสถาปัตยกรรมเป็นข้อเสนอของโครงการ ไม่ใช่คุณสมบัติที่ upstream รับประกันให้ 3117 โดยอัตโนมัติ
