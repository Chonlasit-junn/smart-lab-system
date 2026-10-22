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
- `dist_msi/`: MSI ที่ build แล้ว; `archive/` ภายในเก็บรุ่นก่อนหน้า
- `venv/`: Python environment เฉพาะเครื่อง build ไม่ต้องส่งให้เครื่อง Lab

ไม่ย้าย source modules เพราะ tests และ PyInstaller อ้างอิงตำแหน่งเหล่านี้ ดูแนวทางเก็บไฟล์ใน [โครงสร้างโปรเจค](../docs/PROJECT_STRUCTURE.md)
