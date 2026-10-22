# การจัดวางไฟล์ Smart Lab

แยกแต่ละระบบไว้ที่เดิม เพื่อรักษา import, คำสั่ง build และการตั้งค่า deploy ที่ใช้งานอยู่ ไม่รวม virtual environment หรือข้อมูล runtime ข้ามระบบ

## โฟลเดอร์หลัก

| โฟลเดอร์ | ใช้เก็บ |
| --- | --- |
| `backend/` | API, models, routers และ SQL migrations; Hugging Face sync เฉพาะส่วนนี้ |
| `frontend/` | React/Vite, components, pages และ static assets; เป็น Root Directory ของ Vercel |
| `smart-lab-agent/` | Agent, ตัวลงทะเบียนเครื่อง และเครื่องมือสร้าง MSI |
| `gatekeeper/` | ตัวสแกนกล้องและการลงทะเบียนกล้อง |
| `scripts/` | เครื่องมือตรวจสอบร่วม เช่น domain contract ข้ามสามระบบ |
| `tests/fixtures/` | ข้อมูลทดสอบกลาง; tests เฉพาะระบบอยู่ใน `<ระบบ>/tests/` |
| `docs/` | คู่มือโปรเจคที่ไม่ใช่ source code |
| `.github/` | GitHub Actions; ไม่ย้ายเพราะ GitHub ใช้ตำแหน่งนี้โดยตรง |
| `.vscode/` | การตั้งค่า workspace สำหรับ VS Code |

## ผลลัพธ์ build และไฟล์เฉพาะเครื่อง

```text
smart-lab-agent/
  installer/                   # Script, template และคู่มือ build ที่ track ใน Git
  build_msi/
    <version-timestamp>/       # EXE payload, spec และไฟล์ระหว่าง build
    qa-archive/                # Browser profiles จากการทดสอบเก่า
  dist_msi/
    <version-timestamp>/       # MSI รุ่นที่ใช้งาน/เพิ่ง build
    archive/
      <version-timestamp>/     # MSI รุ่นก่อนหน้า เก็บไว้ย้อนกลับได้

frontend/
  dist/                        # ผลลัพธ์ npm run build
  node_modules/                # Dependencies ของ Frontend

backend/venv/                  # Python environment ของ Backend
smart-lab-agent/venv/           # Python environment ของ Agent/build
gatekeeper/venv/                # Python environment ของ Gatekeeper
```

โฟลเดอร์ build และ archive เหล่านี้ถูก ignore โดย Git อยู่แล้ว การย้ายเข้า archive ช่วยลดความรก แต่ **ไม่ลดพื้นที่ดิสก์** และไม่ได้ลบไฟล์

MSI ล่าสุดคือ `smart-lab-agent/dist_msi/1.1.6-20261022-200752/SmartLabAgent.msi` (45.44 MB) การ build ครั้งต่อไปยังสร้างโฟลเดอร์ใหม่ตามเวอร์ชันและ timestamp โดยไม่ทับของเดิม ไม่ใช้ชื่อ archive เป็นตัวตัดสินว่าเวอร์ชันใดใหม่ที่สุด

## ข้อควรระวัง

- เก็บ `backend/` และ `frontend/` ไว้ที่เดิม เพื่อไม่เปลี่ยน deploy configuration
- ไม่ย้าย `build_msi/<build-id>/`: spec และ setup project ที่สร้างแล้วมี absolute path อ้างอิงตำแหน่งเดิม ส่วน MSI ที่เสร็จแล้วเป็นไฟล์แจกจ่ายแยกได้
- โฟลเดอร์ `qa-archive/` เป็น profile ทดสอบเก่า ไม่ใช่ profile ผู้ใช้จริง ไม่ควรใช้ต่อหรือแจกจ่าย เพราะอาจมี cache/cookies จากการทดสอบ
- ไม่ย้ายหรือแจกจ่าย `.env`, database, token, รูปใบหน้า, embeddings และไฟล์ใน `runtime/`; ข้อมูลเหล่านี้ไม่ใช่ไฟล์ขยะ
- ไม่ย้ายหรือรวม `venv/`: entry points อาจฝัง absolute path และแต่ละระบบใช้ dependencies ต่างกัน
- ไม่ลบ `gatekeeper/Silent-Face-Anti-Spoofing/`: มี source และโมเดลที่สแกนกล้องต้องใช้ รวมถึง license ของผู้พัฒนาเดิม
- ไม่ย้าย `.git` หรือ metadata ของ repository ที่อยู่ภายใน workspace
- ก่อนลบ build, archive หรือ cache ให้ตรวจว่าไม่มีโปรแกรมใช้งานอยู่ ยืนยันรายการกับเจ้าของงาน และเก็บ MSI ที่ต้องแจกจ่ายไว้ก่อน

คู่มือใช้งานและ build Agent อยู่ที่ [Agent](../smart-lab-agent/README.md) และ [MSI installer](../smart-lab-agent/installer/README.md)
