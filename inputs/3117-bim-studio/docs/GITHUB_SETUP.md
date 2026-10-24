# นำโครงโครงการขึ้น GitHub

ชุดนี้ยังไม่ผูก Git remote หรือเผยแพร่ repository ไม่มีการสมมติชื่อบัญชี/องค์กรของผู้ใช้

## ก่อนเผยแพร่

1. เลือก owner หรือ organization ที่จะเป็นผู้ดูแล `3117-bim-studio`
2. ตรวจ README, LICENSE และ THIRD_PARTY ให้ตรงนโยบายโครงการ
3. ติดตั้งและรัน reference tests ตาม README
4. ใช้เฉพาะ fixture สังเคราะห์ ไม่ใส่โมเดลลูกค้าหรือ secret

## สร้าง repository ด้วย GitHub CLI

คำสั่งต่อไปนี้เป็นคำแนะนำให้รันในเครื่องที่ลงชื่อเข้าใช้ GitHub แล้ว การรัน `gh repo create --public --push` จะเผยแพร่ source เป็นสาธารณะ ให้เลือก owner ที่ต้องการก่อน

```bash
git init -b main
git add .
git commit -m "Initialize 3117 BIM Studio scaffold"
gh auth login
gh repo create OWNER/3117-bim-studio --public --source=. --remote=origin --push
```

`OWNER` เป็น placeholder ต้องแทนด้วยบัญชีหรือองค์กรจริง อย่ารัน placeholder ตามตัวอักษร ถ้าจะทบทวนภายในก่อนให้สร้าง private แล้วค่อยปรับ visibility เมื่อพร้อมนโยบาย open source

## การจัดงาน

- เปิด Issues จาก `docs/BACKLOG.csv`; CSV นี้เป็นรายการงาน ไม่ใช่สคริปต์สร้าง issue อัตโนมัติ
- ตั้ง milestones ตาม `docs/ROADMAP.md`
- ตั้ง labels ตามโมดูล เช่น `domain`, `freecad`, `ifc`, `ui`, `drawings`, `quantities`, `docs`
- ใช้ PR template และเปิด branch protection ให้ tests เป็น required checks ตาม job ที่เปิดใช้จริง
- Tag release จาก commit ที่ผ่าน gate; แนบ source archive, change log, dependency manifest และ binary เฉพาะเมื่อทดสอบแล้ว
- รักษาแผนโครงการและ code review ใน GitHub แต่โมเดลโครงการก่อสร้างขนาดใหญ่ควรอยู่ระบบจัดการ revision สำหรับงานออกแบบ ไม่คาดว่า Git merge ไฟล์ binary FCStd ให้ถูกต้องโดยอัตโนมัติ

## อ้างอิง

- https://docs.github.com/en/repositories/creating-and-managing-repositories/quickstart-for-repositories
- https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github
