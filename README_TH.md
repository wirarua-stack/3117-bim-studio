# 3117 BIM Studio — ชุด Windows acceptance

วันที่จัดทำ: **23 ตุลาคม 2569 / 2026-10-23**

**สถานะ: ตรวจความพร้อม Windows runner จริงผ่านแล้ว ส่วนการ build FreeCAD และชุดทดสอบ Windows ยังรอรัน**

ชุดนี้ต่อจากงานแก้ native history-branch crash ของ FreeCAD 1.1.4 บน Linux
เพื่อสร้างโฮสต์ Windows ก่อน/หลัง patch และรัน regression, Undo/Redo,
save/reopen และชุดทดสอบ 3117 v0.5.0 ทั้ง native และ public GUI โดยเก็บ
หลักฐานจาก process ที่รันจริง งานรอบนี้เพิ่มระบบ build/test และตัวตรวจผล
โดยคง source ของ Workbench และ patch ที่ตรวจไว้เดิม

ไฟล์นี้เป็นชุด source สำหรับตรวจรับ ไม่ใช่ตัวติดตั้ง FreeCAD ที่ผ่าน Windows แล้ว
`release_ready` ยังคงเป็น `false` และร่าง upstream ยังไม่ได้ส่งหรือ merge

## สิ่งที่ทำเสร็จในชุดนี้

| ส่วน | งานที่เตรียมไว้ |
| --- | --- |
| คำสั่งหลัก | `Start-WindowsAcceptance.ps1` เรียก build และทดสอบตามลำดับ พร้อม log/รายงานกลาง |
| Build ก่อน/หลัง patch | แยก source/build directory ใช้ dependency ชุดเดียวกัน และตรวจ source difference |
| Source และ patch | ตรึง commit `4fd3bf320d9566a27e60069fc8387448aaa3a094`; แก้ `Document.cpp` เพิ่ม 3 บรรทัดตาม patch เดิม |
| Toolchain | VS2022 / v143, CMake 3.31.6, LibPack 3.1.1.3 ตาม Windows CI ใน source ที่ตรึงไว้ |
| Qt ของ host | เปิด compiled PySide/Shiboken และตรวจทั้ง Release defines, DLL imports และ DLL ที่ process โหลด |
| IFC | Windows wheels 7 รายการพร้อม SHA-256; เลือก isolated runtime ก่อน IFC เก่าที่มีใน LibPack |
| Crash regression | คง 6 กรณีเดิมและลำดับ transaction/Undo/Redo; ทดสอบ host ก่อน/หลัง patch |
| Native suite | 19 process ใหม่ รวม 651 checks พร้อมติดตั้ง Workbench และเปิด FCStd ข้าม process |
| Public GUI suite | Installer และ 6 public macros จาก ZIP เดิม รวม 248 GUI checks + 48 package checks |
| ตัวตรวจรับผล | อ่าน raw JSON/log/host identity อีกครั้ง ตรวจ hash, จำนวนข้อ, exit code, DLL และ dependency ที่ใช้จริง |
| GitHub Actions | Workflow สำหรับ branch ตรวจรับ และ manual dispatch; เก็บหลักฐานทุกผล และเมื่อ automated acceptance ผ่านจะ seal + เก็บ patched runtime ชุดเดียวกับที่ผ่านพร้อม SHA-256 manifest |

ดูรายละเอียด [Build Windows](docs/WINDOWS_BUILD.md),
[Public GUI และ IFC](docs/PUBLIC_GUI.md) และ
[ขอบเขตการตรวจรับ](docs/ACCEPTANCE_CONTRACT.md)

## สถานะ GitHub และ Windows runner ปัจจุบัน

สร้าง repository
[**`wirarua-stack/3117-bim-studio`**](https://github.com/wirarua-stack/3117-bim-studio)
แล้ว และใช้ branch ตรวจรับ
[`acceptance/windows-history-fix`](https://github.com/wirarua-stack/3117-bim-studio/tree/acceptance/windows-history-fix)
source Workbench เดิมอยู่ใน `inputs/3117-bim-studio/`

งาน [Windows runner readiness ครั้งที่ 39934642607](https://github.com/wirarua-stack/3117-bim-studio/actions/runs/39934642607)
**ผ่านแล้วบน Windows จริง** ที่ commit
[`1139434ce9bc2ca4bb2813bea1623e5c249c316c`](https://github.com/wirarua-stack/3117-bim-studio/commit/1139434ce9bc2ca4bb2813bea1623e5c249c316c)
และ [job 120351087462](https://github.com/wirarua-stack/3117-bim-studio/actions/runs/39934642607/job/120351087462)
ผลที่บันทึกระบุ Windows build `10.0.20348`, PowerShell `7.6.6`,
directory สำหรับงานที่เขียนได้และมีพื้นที่เกิน 30 GiB, desktop session `2`,
visible window station และจอภาพ 1 จอ

เก็บ [รายงาน JSON ต้นฉบับ](evidence/ci/runner-readiness-39934642607.json)
และ [ที่มาของ artifact พร้อม SHA-256](evidence/ci/runner-readiness-39934642607.provenance.json)
ไว้ในชุดนี้ ผลดังกล่าวยืนยันความพร้อมของ runner ในครั้งนั้น
**การสังเกต desktop ผ่าน WinAPI ยังไม่ใช่ผลตรวจ Qt หรือ FreeCAD GUI**
การ build FreeCAD, crash regression, Undo/Redo, save/reopen,
native 651 checks และ public GUI 248 + package 48 checks ยังรอรัน
แต่ละการรันตรวจรับต้องตรวจสภาพแวดล้อมและ desktop ของตัวเองอีกครั้ง

ไฟล์ [PREPARATION_STATUS.json](PREPARATION_STATUS.json) คงไว้ตามต้นฉบับ
เป็นสถานะย้อนหลังเมื่อ **23 ตุลาคม 2569 เวลา 09:25:33 UTC**
ก่อนตั้ง repository และก่อนรัน Windows readiness เวลา **09:49:32 UTC**
ข้อความในไฟล์นั้นที่ยังไม่มี repository ปลายทางจึงอธิบายช่วงเวลาดังกล่าว
ส่วนผล offline ในไฟล์ยังเป็นหลักฐานการเตรียมบน Linux

โครงชุดนี้ใช้เป็น root ของ branch สำหรับตรวจรับได้โดยตรง
โดยรักษา `.github` และ `.gitattributes` ไว้ครบ

ไฟล์ [workflow](.github/workflows/windows-acceptance.yml) ใช้ `contents: read`
และไม่มีคำสั่งสร้าง Release, merge หรือส่ง PR ไปยัง FreeCAD upstream
การเรียกใช้งาน Actions จะใช้ runner/สิทธิ์/โควตาที่ repository นั้นมีอยู่

## รันบน Windows ด้วยคำสั่งเดียว

เครื่อง build ต้องเป็น **Windows x64 จริง** มี VS2022 C++ x64 tools/v143
และ Windows SDK, PowerShell 7.4+, Python 3.12+ สำหรับตัวควบคุม และ 7-Zip
ชุด build ตรวจเครื่องมือที่ติดตั้งอยู่แล้ว และดาวน์โหลด source/LibPack/CMake
ตาม lock โดยไม่ติดตั้ง Visual Studio หรือเปลี่ยน environment ถาวรให้เอง

ต้องมีพื้นที่ว่าง **อย่างน้อย 30 GiB ตอนเริ่ม** และ 12 GiB ก่อน build ตัวที่สอง
เพราะ LibPack เมื่อแตกแล้วประมาณ 6.68 GB และต้องเก็บโฮสต์สองชุดไว้เทียบกัน
ใช้ path build สั้น เช่น `C:\3117Acceptance\run-01` และใช้ directory ใหม่ทุกครั้ง
ตัวทดสอบจะสร้าง path ภาษาไทยและ user profile แยกของตนเอง

เปิด PowerShell 7 ในโฟลเดอร์ชุดนี้ แล้วรัน:

```powershell
pwsh -NoProfile -File .\Start-WindowsAcceptance.ps1 `
  -WorkRoot C:\3117Acceptance\run-01 `
  -Jobs 2
```

คำสั่งจะดำเนินการตามลำดับ:

1. ตรวจ hash ของ input ที่ตรึงไว้
2. ดาวน์โหลดและ build FreeCAD แบบ unpatched
3. เตรียม IFC runtime สำหรับ Python 3.12 ของ host และทดสอบ import ใน FreeCADCmd จริง
4. รัน regression ทั้ง 6 กรณีกับ unpatched host และบันทึกผลที่สังเกตได้
5. สร้าง source/build อีกชุด ใส่ patch เดิม และ build patched host
6. รัน patched regression รวม history invariants, fresh-process reopen และ original 3117 UI
7. รัน native suite 19 process และ public GUI suite 7 process
8. รวบรวมหลักฐานและตัดสิน automated acceptance

ทุกขั้นมี timeout และ log ไม่ล้าง Undo history ไม่แก้ลำดับ crash เดิม
เมื่อมี timeout จะพยายามหยุดเฉพาะ process tree ที่ตัวทดสอบสร้างขึ้น
ไม่มีคำสั่งปิด FreeCAD ทุกหน้าต่างด้วยชื่อ process

ตัวทดสอบ GUI ต้องอยู่ใน desktop session ที่ใช้งานได้จริง ตรวจ Qt platform
`windows`, หน้าจอ, visible window station และ session ที่ไม่ใช่ 0
ถ้า runner ไม่รองรับเงื่อนไขนี้ จะรายงานว่าไม่ผ่านข้อกำหนด ไม่เปลี่ยนไปใช้
offscreen แล้วนับเป็น desktop acceptance

### รันบน GitHub Actions

workflow กำหนด `windows-2022` เป็นเส้นทางเริ่มต้น และตรวจพื้นที่/desktop
ก่อนยอมรับผล ไม่รับรองว่า standard hosted runner ทุกเครื่องมีทรัพยากรพอ
หากใช้เครื่อง Windows ของโครงการ ให้ตั้ง runner ที่มีอยู่แล้วด้วย labels
`self-hosted`, `Windows`, `X64`, `3117-desktop` และรันใน session ผู้ใช้
จากนั้นเลือก `desktop` ใน manual dispatch

workflow ที่ใช้ manual dispatch ต้องอยู่ใน default branch ตามกติกา GitHub
ส่วนการ push ไป branch `acceptance/windows-history-fix` ที่มีไฟล์ workflow
และเปลี่ยนไฟล์ในขอบเขตที่ระบุ จะเป็นอีกทางหนึ่งสำหรับเริ่มตรวจรับ

## อ่านผลจากไฟล์ใด

ใน `WorkRoot` ที่เลือก:

| ไฟล์/โฟลเดอร์ | ใช้ตรวจอะไร |
| --- | --- |
| `run.json` | ขั้นตอนที่เรียกจริง, exit code, เวลา, GitHub run/commit เมื่อรันผ่าน Actions |
| `controller-logs/` | Log ของ build และแต่ละ test suite |
| `hosts/unpatched/host-manifest.json` | ตัวตน source, compiler, SDK, EXE/DLL ของ baseline |
| `hosts/patched/host-manifest.json` | ตัวตน host ที่ใส่ patch |
| `results/regression-unpatched/` | ผล Windows baseline ที่สังเกตจริง |
| `results/regression-patched/` | ผล crash/Undo/Redo/save/reopen ของ patched host |
| `results/native-patched/` | Native 19 process / 651 checks |
| `results/public-gui-patched/` | Installer และ public GUI พร้อม raw reports/รูป/ผลส่งออก |
| `ifc-runtime/ifc-preflight.json` | ผล import dependency ใน embedded Windows Python |
| `WINDOWS_ACCEPTANCE.json` และ `.md` | สรุป gate ที่อ่านย้อนจากหลักฐานจริง |

หาก Windows baseline ไม่ crash ให้รายงานตามนั้น ไม่ยกผล Linux มาใส่แทน
หาก baseline crash จะบันทึก native exit code และตำแหน่งลำดับสุดท้ายที่ทราบ
โดยไม่แต่ง native stack หรืออ้างว่าเป็นจุดเดียวกันเมื่อยังไม่มีหลักฐาน

## ผลเตรียมบน Linux และผล Windows readiness

หลักฐานการเตรียมบน Linux อยู่ใน snapshot
[PREPARATION_STATUS.json](PREPARATION_STATUS.json) ที่ลงเวลาข้างต้น
และ `evidence/` ครอบคลุม:

- ทดสอบตัวควบคุมและเงื่อนไขการรับ/ปฏิเสธหลักฐาน โดยใช้ fixture ที่ระบุว่าเป็นข้อมูลสังเคราะห์
- ตรวจ parser ของ PowerShell ด้วย runtime Linux; ไม่ใช่การรัน script บน Windows
- ตรวจ LibPack จากไฟล์ดาวน์โหลดครบจริง พร้อม SHA-256 และรายการภายใน archive
- ดาวน์โหลด Windows IFC wheels ทั้ง 7 รายการ ตรวจ hash แตก 817 ไฟล์ และตรวจ PE AMD64 ของ `.pyd`
- ตรวจ source/patch กับ archive จริง และปฏิเสธการใส่ patch ซ้ำ
- ตรวจว่า input 898 ไฟล์ยังตรงกับ hash เดิม

หลัง snapshot นี้ ได้รัน Windows runner readiness จริงผ่านแล้วตาม
[รายงานต้นฉบับ](evidence/ci/runner-readiness-39934642607.json)
ซึ่งบันทึกความพร้อมพื้นที่ทำงานและ desktop แยกจากชุดทดสอบโปรแกรม

**ยังไม่ได้ build FreeCAD หรือเรียกใช้ FreeCAD DLL และ FreeCAD GUI บน Windows**
ดังนั้นยังไม่มีผล 651/248/48 checks ของ Windows และยังไม่สร้างตัวติดตั้ง
จาก host ที่ไม่ผ่านการตรวจรับ

## หลัง automated acceptance ผ่าน

ใช้ [Windows checklist W01–W62](inputs/3117-bim-studio/docs/WINDOWS_ACCEPTANCE.md)
ตรวจเครื่องใช้งานจริงต่อ โดยเฉพาะ Windows 10/11, การติดตั้ง/อัปเกรด/
คืนรุ่น/ถอนติดตั้ง, ภาพและการเลือกใน viewport, การพิมพ์ A3 จริงที่ 100%
และการเปิด IFC ในโปรแกรม BIM ปลายทางที่ระบุชื่อและรุ่น

เมื่อ automated acceptance ผ่าน workflow จะสร้าง `accepted-runtime-seal/accepted-runtime-manifest.json` จากไฟล์ใน patched build ที่ถูกทดสอบจริง และอัปโหลด artifact `3117-accepted-patched-runtime-<run>-<attempt>` ซึ่งเก็บ runtime families `bin/data/doc/Ext/lib/Mod`, host manifest, acceptance report, isolated IFC runtime และ ZIP Workbench ที่ตรึงไว้ การเก็บ artifact นี้เกิดเฉพาะเมื่อผล automated เป็น `passed` และยังคง `release_ready: false`

จากนั้นจึงจัดชุดติดตั้งสำหรับทดลองจาก **binary ชุดเดียวกับที่ผ่านทดสอบ**
พร้อม license, source/patch provenance และ dependency manifest โดยต้องตรวจ hash กับ accepted-runtime manifest หลังดาวน์โหลด/ย้ายที่อยู่ก่อนใช้งาน
การผ่าน automated suite ไม่ใช้แทนการตรวจรายการ desktop ที่ยังไม่ได้ทำ

## License และที่มา

ตัวควบคุมและ Workbench ใช้ GPL-3.0-or-later ตาม [LICENSE](LICENSE)
FreeCAD, patch, dependencies และฟอนต์มีเงื่อนไขของตนเองตามต้นทาง
ดู [Third-party notices](inputs/3117-bim-studio/THIRD_PARTY.md)
ชุดนี้ไม่รวม FreeCAD/Qt/LibPack/Windows runtime binaries

ต้นทางที่ใช้เลือก build route และ checksum ระบุไว้ใน
[WINDOWS_BUILD.md](docs/WINDOWS_BUILD.md) และ `build/windows-build.lock.json`
hash ของ LibPack เป็นค่าที่คำนวณจากไฟล์ดาวน์โหลดครบในรอบนี้
เนื่องจาก release API ไม่ได้เผยแพร่ digest ของ asset ดังกล่าว
