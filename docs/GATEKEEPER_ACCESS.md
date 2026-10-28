# Gatekeeper: ตรวจสิทธิ์และประวัติการสแกน

## Flow ปัจจุบัน

1. Admin ลงทะเบียนเครื่องกล้องและผูกกับ Lab ผ่าน `/admin/lab-devices/register`
2. เครื่องกล้องใช้ MiniFASNetV2 เดิมผ่าน ONNX Runtime แบบ FP32 ตรวจ Liveness หลายเฟรมและการเคลื่อนไหว ดู [รายละเอียด ONNX](GATEKEEPER_ONNX.md)
3. ส่งผลไปยัง `/gatekeeper/identify` ด้วย Device Credential ถ้า Liveness ไม่ผ่าน ส่งเฉพาะผลโดยไม่ส่งรูป
4. Backend ตรวจ Credential และสถานะ Lab ก่อน หาก Liveness ผ่านจึงจับคู่ใบหน้าด้วย Facenet
5. ตรวจการอนุมัติ Guest, สถานะบัญชี, Ban ที่ยังไม่หมดอายุ และ Booking ของผู้ใช้นั้นใน Lab ของกล้อง
6. บันทึกผลลง `gatekeeper_scan_logs` และ commit ก่อนตอบอนุญาต
7. Gatekeeper แสดง `ACCESS GRANTED` เฉพาะเมื่อได้รับ `access_granted: true` พร้อม `scan_id` จาก Backend

Booking ใช้ปฏิทิน Asia/Bangkok โดย `start_time <= เวลาปัจจุบัน < end_time` และสถานะต้องเป็น `reserved` หรือ `attended` การสแกนไม่เปลี่ยนสถานะ Booking, ไม่สร้าง Agent Session และไม่เปลี่ยนคะแนน จึงยังเริ่ม Session จาก Agent ตามเดิมได้ การมีคะแนนต่ำเพียงอย่างเดียวไม่ห้ามเข้า ถ้าไม่มี Ban ที่ยังมีผล

Guest ที่ไม่มีแถวอนุมัติหรือ `user_passport.is_active = false` จะถูกปฏิเสธ รวมถึงกรณีมี role อื่นร่วมด้วย บัญชีนักศึกษาที่ `students.is_active = false` ถูกปฏิเสธเช่นกัน Admin ไม่ได้รับข้อยกเว้น Booking หรือ Ban

## Migration และการ deploy

ไฟล์ SQL สำหรับผู้ดูแลรันเอง: [`017_gatekeeper_scan_logs.sql`](../backend/migrations/017_gatekeeper_scan_logs.sql)

ลำดับใช้งาน:

1. ผู้ดูแลรัน Migration 017 ในฐานข้อมูลเป้าหมาย
2. Deploy Backend ที่มีการตรวจสิทธิ์และบันทึกประวัติ
3. อัปเดตโปรแกรม Gatekeeper จาก source ชุดเดียวกัน หรือ build `smart_gatekeeper.spec` ใหม่
4. QA ทดสอบด้วยกล้องจริงและบัญชีทดสอบที่มี Booking

ตารางกำหนด `manual_migration` จึงไม่ถูกสร้างอัตโนมัติจาก startup ของ API ถ้าตารางยังไม่มีหรือบันทึกไม่สำเร็จ API ตอบ `503 / scan_history_unavailable` และไม่อนุญาตเข้า ไม่มีการรัน SQL นี้จากแอปหรือ tests

Gatekeeper รุ่นใหม่จะปฏิเสธ Backend รุ่นเก่าที่ตอบเพียงผลจับคู่ใบหน้า แม้ได้ HTTP 200 เพราะยังไม่มีหลักฐานว่าตรวจสิทธิ์และบันทึกแล้ว ไม่ต้องตั้ง Secret เพิ่ม ใช้ Device Credential ของกล้องที่ลงทะเบียนไว้

## ประวัติที่เก็บ

เก็บเฉพาะเวลา UTC, Lab ID และรหัส Lab ณ ตอนสแกน, Device ID, User/Booking ID ถ้าระบุได้, ผล `granted/denied`, เหตุผล, คะแนน Liveness และระยะห่างใบหน้า ไม่เก็บรูปสแกน วิดีโอ Embedding หรือ Credential ซ้ำในประวัติ

กรณีไม่รู้จักใบหน้าและ Liveness ไม่ผ่านจะมี `user_id = null` ถ้ามีการลบบัญชีในภายหลัง Foreign Key จะเปลี่ยน User ID ในประวัติเป็น null โดยยังรักษาผลการสแกนไว้

บันทึกคำขอที่ยืนยัน Credential ของเครื่องได้ รวมถึงการปฏิเสธเพราะ Lab ไม่เปิดใช้งาน คำขอ Credential ผิดและข้อมูลที่ผิดรูปแบบจน FastAPI รับไม่ได้จะไม่สร้างประวัติ หากเครือข่ายขัดข้อง เครื่องกล้องไม่ให้ผ่าน และยืนยันไม่ได้ว่าประวัติถูกบันทึกแล้วหรือไม่ ยังไม่มี Offline Outbox สำหรับ Gatekeeper

RLS เปิดใช้งานโดยไม่มี public policy และถอนสิทธิ์จาก PUBLIC, anon และ authenticated การอ่านผ่าน Backend ต้องใช้บัญชี Admin ส่วน SQL role ที่ Backend ใช้ต้องเป็นเจ้าของตารางหรือมีสิทธิ์ที่ผู้ดูแลกำหนดไว้

## อ่านประวัติผ่าน Admin API

`GET /admin/gatekeeper/scans` ใช้ Bearer token ของ Admin เท่านั้น รองรับ:

| Parameter | ความหมาย |
|---|---|
| `limit` | จำนวนต่อชุด 1–100, ค่าเริ่มต้น 50 |
| `before_id` | Cursor จาก `next_before_id` ของชุดก่อน |
| `lab_id` | กรอง Lab |
| `user_id` | กรองผู้ใช้ |
| `device_id` | กรอง Device ID ของกล้อง |
| `decision` | `granted` หรือ `denied` |

ผลเรียง ID ล่าสุดก่อน มี `has_more` และ `next_before_id` การอ่านนี้ไม่แก้ข้อมูล ยังไม่ได้เพิ่มหน้า UI ประวัติใหม่หรือรวมใน Excel รายงาน Agent

## การปิดทางทดสอบที่ข้ามกฎ

- `/gatekeeper/scan` เดิมตอบ HTTP 410 และไม่เขียน `lab_access_logs` อีก ต้องส่งภาพเข้า `/gatekeeper/identify`
- ปุ่ม DEV MOCK ปิดโดยปริยาย หากต้องทดสอบ UI ให้ตั้ง `SMART_GATEKEEPER_DEV_MOCK=1` เฉพาะเครื่องทดสอบ ผลจำลองขึ้น `DEMO: REAL FACE` ไม่ใช่ `ACCESS GRANTED` และไม่เขียนประวัติ
- Liveness ยังตรวจบนเครื่องกล้อง Backend ตรวจ Credential และผลที่เครื่องรายงาน การประเมินความแม่นยำของ Anti-spoof/Facenet ต้องใช้ภาพและกล้องจริงเพิ่มเติม

## Tests ที่ใช้ข้อมูลจำลอง

```powershell
cd backend
$env:SQLALCHEMY_DATABASE_URL = 'sqlite:///:memory:'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_gatekeeper_*.py' -v
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_guest_rejection.py' -v
```

```powershell
cd gatekeeper
$env:TEMP = (Resolve-Path -LiteralPath 'runtime').Path
$env:TMP = $env:TEMP
.\venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Tests ของ Backend สร้าง SQLite ในหน่วยความจำและ mock การจับคู่ของ DeepFace ส่วน tests เครื่องกล้องใช้ภาพสังเคราะห์และ mock เครือข่าย ไม่เรียกฐานข้อมูลหรือกล้องจริง

## การ Optimize กล้อง, UI, HTTP และ Backend

ดูการเปลี่ยนแปลง ผลวัดก่อน–หลัง ข้อจำกัด และคำสั่งวัดซ้ำใน [GATEKEEPER_OPTIMIZATION.md](GATEKEEPER_OPTIMIZATION.md)

Backend จำกัดงานจับคู่ใบหน้าของ Gatekeeper ให้ทำพร้อมกันหนึ่งงานต่อ API process รอช่องว่างได้ 0.25 วินาที ถ้าเต็มจะปฏิเสธด้วย `503 / face_service_busy` พร้อมประวัติสแกน ไม่ลองส่ง POST ซ้ำอัตโนมัติ การอนุญาตยังต้องตรวจ Booking/Guest/Ban และ commit ประวัติสำเร็จเสมอ
