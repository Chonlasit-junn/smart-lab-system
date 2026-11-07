# Smart Lab Agent

ส่วนนี้รวม Agent ตรวจการใช้เครื่องและตัวลงทะเบียน Lab ใน executable เดียว

- `smart_lab_device.py`: entry point ร่วมของ MSI; `--register` เปิดตัวลงทะเบียน
- `agent.pyw` และ `agent_*.py`: หน้าจอ Agent, policy, outbox และงานเบื้องหลัง
- `browser_url.py`, `program_identity.py`, `domain_normalization.py`: หลักฐานโปรแกรมและโดเมน
- `register_device_gui.pyw`, `device_registration.py`: ลงทะเบียนเครื่องกับ Backend
- `lab_setup.py`, `lab_setup.pyw`, `provision_device.py`: เครื่องมือตั้งค่า/เตรียมเครื่อง
- `installer/`: สคริปต์ build, template และ [คู่มือติดตั้ง MSI](installer/README.md)
- `tests/`: source tests; ไม่ใช่ไฟล์ชั่วคราว
- `build_msi/`: ไฟล์ระหว่าง build; `qa-archive/` ภายในเก็บ browser profiles ทดสอบเก่า
- `dist_msi/`: MSI แยกตาม `agent/` และ `qa/`; รุ่นเก่าเก็บใน `archive/agent/` และ `archive/qa/`
- `venv/`: Python environment เฉพาะเครื่อง build ไม่ต้องส่งให้เครื่อง Lab

ไม่ย้าย source modules เพราะ tests และ PyInstaller อ้างอิงตำแหน่งเหล่านี้ ดูแนวทางเก็บไฟล์ใน [โครงสร้างโปรเจค](../docs/PROJECT_STRUCTURE.md)

## ชื่อโปรแกรมใน usage

Agent อ้างอิง process เจ้าของหน้าต่างด้านหน้าผ่าน HWND/PID แล้วใช้
`OriginalFilename` หรือ `InternalName` จาก EXE เป็นชื่อ usage ตัวพิมพ์เล็ก
เช่น `notepad.exe` หากไม่มี metadata จะใช้ชื่อไฟล์ของ process จริง
ชื่อเอกสาร ชื่อหน้าเว็บ และชื่อหน้าต่างไม่ถูกนำมาใช้ตั้งชื่อ usage
ส่วน Agent เองและหน้าต่าง desktop/taskbar ของ Windows ยังคงถูกข้าม

ยังส่ง `name`, เวลา UTC, duration และ event ID ใน payload เดิม พร้อม checkpoint
ทุก 30 วินาทีและคิวส่งย้อนหลัง การเปลี่ยนนี้มีผลกับ usage ใหม่หลังอัปเดต Agent
ต้อง build/distribute MSI ใหม่เพื่อใช้บนเครื่อง Lab; ไม่ต้องรัน migration
