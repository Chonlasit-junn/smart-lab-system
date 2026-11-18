# Smart Lab Project Structure

แยกแต่ละระบบไว้ที่เดิม เพื่อรักษา import, คำสั่ง build และการตั้งค่า deploy ที่ใช้งานอยู่ ไม่รวม virtual environment หรือข้อมูล runtime ข้ามระบบ

## โฟลเดอร์หลัก

| โฟลเดอร์ | ใช้เก็บ |
| --- | --- |
| `backend/` | API, models, routers และ SQL migrations; Hugging Face sync เฉพาะส่วนนี้ |
| `frontend/` | React/Vite, components, pages และ static assets; เป็น Root Directory ของ Vercel |
| `smart-lab-agent/` | Agent, ตัวลงทะเบียนเครื่อง และเครื่องมือสร้าง MSI |
| `gatekeeper/` | ตัวสแกนกล้องและการลงทะเบียนกล้อง |
| `scripts/` | เครื่องมือสำหรับดูแลโปรเจกต์ |
| `tests/fixtures/` | ข้อมูลทดสอบกลาง; tests เฉพาะระบบอยู่ใน `<ระบบ>/tests/` |
| `docs/` | คู่มือโปรเจคที่ไม่ใช่ source code |
| `.github/` | GitHub Actions; ไม่ย้ายเพราะ GitHub ใช้ตำแหน่งนี้โดยตรง |
| `.vscode/` | การตั้งค่า workspace สำหรับ VS Code |
| `build/` | release snapshots และ QA output ในเครื่อง; ไม่ commit |
| `output/` | หลักฐาน benchmark/acceptance ที่คู่มืออ้างอิง |

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

โฟลเดอร์ `build/` และ generated subfolders ใน installer staging เป็นข้อมูลเฉพาะเครื่องที่ ignore โดย Git ส่วน `output/` เก็บรายงานตรวจสอบที่เอกสารอ้างอิง การย้ายไฟล์ build เข้า archive ไม่ลดพื้นที่ดิสก์และไม่ลบข้อมูลจาก Git history

ไฟล์ MSI และ EXE เป็นผลลัพธ์สำหรับติดตั้งที่เก็บไว้ในเครื่อง ไม่ commit ขึ้น Git โฟลเดอร์ `output/` ใช้เก็บผลตรวจสอบที่คู่มือโครงการอ้างถึง ส่วน `build/` เก็บ snapshot และ log ชั่วคราวในเครื่อง

## ข้อควรระวัง

- เก็บ `backend/` และ `frontend/` ไว้ที่เดิม เพื่อไม่เปลี่ยน deploy configuration
- ไม่ย้าย `build_msi/<build-id>/`: spec และ setup project ที่สร้างแล้วมี absolute path อ้างอิงตำแหน่งเดิม; ไฟล์ MSI/EXE เก็บแยกไว้ในเครื่อง
- โฟลเดอร์ `qa-archive/` เป็น profile ทดสอบเก่า ไม่ใช่ profile ผู้ใช้จริง ไม่ควรใช้ต่อหรือแจกจ่าย เพราะอาจมี cache/cookies จากการทดสอบ
- ไม่ย้ายหรือแจกจ่าย `.env`, database, token, รูปใบหน้า, embeddings และไฟล์ใน `runtime/`; ข้อมูลเหล่านี้ไม่ใช่ไฟล์ขยะ
- ไม่ย้ายหรือรวม `venv/`: entry points อาจฝัง absolute path และแต่ละระบบใช้ dependencies ต่างกัน
- ไม่ลบ `gatekeeper/Silent-Face-Anti-Spoofing/`: มี source และโมเดลที่สแกนกล้องต้องใช้ รวมถึง license ของผู้พัฒนาเดิม
- ไม่ย้าย `.git` หรือ metadata ของ repository ที่อยู่ภายใน workspace
- ก่อนลบ build, archive หรือ cache ให้ตรวจว่าไม่มีโปรแกรมใช้งานอยู่และยืนยันว่าไฟล์ไม่จำเป็นแล้ว

คู่มือใช้งานและ build Agent อยู่ที่ [Agent](../smart-lab-agent/README.md) และ [MSI installer](../smart-lab-agent/installer/README.md)
