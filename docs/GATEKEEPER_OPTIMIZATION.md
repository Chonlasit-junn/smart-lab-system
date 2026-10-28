# Gatekeeper optimization: ข้อ 1–4

วันที่ตรวจและวัดผล: 28 ตุลาคม 2026 (Asia/Bangkok)

งานต่อเนื่องเรื่อง **เวลาจนได้ภาพแรก** อยู่ที่ [Camera startup](GATEKEEPER_CAMERA_START.md) ผลในเอกสารนี้เป็นรอบก่อนแก้การไล่เปิดกล้องทั้งชุด จึงแยกจากผลวัดภาพแรกล่าสุด

## การเปลี่ยนแปลง

1. `gatekeeper/camera_stream.py`: ให้ worker เดียวเป็นเจ้าของการค้นหา เปิด อ่าน เปลี่ยน และปิดกล้องทั้งหมด การค้นหาไม่ขวาง Tk thread คืนภาพล่าสุดแบบอ่านอย่างเดียว มี generation และเวลาหมดความสด 1 วินาที ภาพเก่า/ผลตรวจจากกล้องก่อนหน้าไม่ใช้อนุญาต กล้องหลุดจะยกเลิกผลเดิมและลองเปิดใหม่เป็นช่วง 0.5 วินาที
2. `gatekeeper/smart_gatekeeper.py`: ใช้ CTkImage ตัวเดิม อัปเดตภาพ PIL ชุดเดียวต่อเฟรม แยกภาพวาด UI ออกจากภาพดิบที่ใช้ AI/อัปโหลด และข้ามการวาดซ้ำเมื่อกล้องยังไม่ส่งเฟรมใหม่ รักษา display interval 40 ms และ cadence ตรวจใบหน้าเดิม
3. `gatekeeper/access_client.py`: ใช้ Requests Session เดียวต่อโปรแกรม มี lock ป้องกันใช้ Session พร้อมกัน connection pool ขนาด 1 และปิดหลังงานที่กำลังทำเสร็จ ไม่ retry POST เพื่อไม่สร้างประวัติ/การอนุญาตซ้ำ Timeout และเกณฑ์รับ grant/scan_id เดิมยังอยู่ งานที่รอ transport จะไม่ส่งหลังเริ่มปิดโปรแกรม
4. `backend/routers/gatekeeper.py` และ `backend/face_service.py`: จบ transaction ที่ใช้ตรวจ credential ก่อนรอโมเดลหรือประมวลผล AI ปล่อย connection คืน pool แล้วอ่าน credential/Lab สดอีกครั้งก่อนค้นหาและตรวจสิทธิ์ จัดช่องประมวลผล Gatekeeper พร้อมกัน 1 งานต่อ process รอได้ 0.25 วินาที ก่อนตอบ busy แบบปฏิเสธและบันทึกประวัติ

ผลจาก worker ส่งผ่าน queue ให้ Tk thread จัดการ การปิดโปรแกรมส่ง stop event และรอ worker แบบไม่ขวาง UI สูงสุด 1 วินาที กล้องจะ release โดย owner ของมัน Native camera read และ HTTP request ที่เริ่มไปแล้วอาจต้องรอ driver/timeout แต่จะไม่มีผลอนุญาตย้อนหลังบน UI หลังปิดหรือเปลี่ยน generation ระหว่างตรวจสิทธิ์ dropdown เปลี่ยนกล้องจะให้รอจนจบรอบนั้นก่อน

## สิ่งที่คงเดิม

- Liveness 5 ตัวอย่าง ต้องผ่าน 4 ตัวอย่าง เกณฑ์ 0.72 และการเคลื่อนไหวเดิม ช่วงเก็บตัวอย่าง 0.12 วินาที ไม่เปลี่ยนโมเดล/น้ำหนัก/threshold
- อุปกรณ์ต้องลงทะเบียน Lab เปิดใช้งาน Booking ตรงเจ้าของ/Lab/วันและเวลาไทย Guest อนุมัติ บัญชี active และไม่มี Ban ที่ยังมีผล
- ตรวจเงื่อนไขหลัง AI โดยอ่าน DB ใหม่ การถอนอนุมัติ แบน ยกเลิก Booking ปิด Lab หรือถอน credential ระหว่างรอ AI ไม่ทำให้ผ่าน
- บันทึก granted/denied ก่อนตอบผล ไม่มีรูปสแกนถูกเก็บซ้ำ การเขียนประวัติล้มเหลวยังปฏิเสธ ไม่เปลี่ยน Booking, แต้ม หรือ Agent Session
- credential ที่ผิดตั้งแต่ต้นไม่เพิ่มประวัติตามกฎเดิม ส่วน credential ที่ผ่านตอนเริ่มแต่ถูกถอนระหว่างรอ AI จะปฏิเสธด้วย `camera_unavailable` พร้อมประวัติของการสแกนนั้น
- ไม่มีการเพิ่ม schema หรือ migration ในงาน Optimize นี้ Migration 017 จากงานก่อนหน้ายังต้องติดตั้งโดยผู้ดูแลก่อนใช้ระบบประวัติบนฐานข้อมูลจริง

## ผลวัดก่อน–หลัง

วัดในเครื่องพัฒนาเดียวกัน ใช้กล้องจำลองที่เปิดแต่ละ index ใช้เวลา 20 ms, ภาพสังเคราะห์ 640×480, Tk image handle จำลอง, HTTP server บน loopback และ Backend SQLite ในหน่วยความจำแทนฐานข้อมูลจริง โมเดล Backend จำลองเวลา AI 50 ms ต่อรอบ ไม่มีรูปคนหรือข้อมูล production

| ตัวชี้วัด | ก่อน | หลัง |
|---|---:|---:|
| CTkImage ที่สร้าง / 250 เฟรม | 250 | 1 |
| PIL Image ที่สร้าง / 250 เฟรม | 500 | 250 |
| median เวลาเตรียม preview ต่อเฟรม (ไม่รวม Tk วาดจริง) | 1.044 ms | 0.896 ms |
| เวลาที่ caller/UI ถูกขวางตอนเริ่มค้นหากล้องจำลอง | 124.341 ms | 1.061 ms |
| TCP connection / 8 คำขอ | 8 | 1 |
| รอบ AI ที่ถือ connection DB / 8 รอบ | 8 | 0 |
| เวลาถือ connection DB รวมเฉพาะขณะรอ AI จำลอง | 405.695 ms | 0 ms |
| ประวัติสแกนสำเร็จ / 8 รอบ | 8 | 8 |

ไฟล์ผลดิบอยู่ใน `output/gatekeeper-optimization/{before,after}-{kiosk,backend}.json` ค่าก่อนถูกเก็บก่อนแก้โค้ด ค่าเวลามีความแปรปรวนตามโหลดเครื่อง การย้ายงานกล้องไป worker ลดเวลาที่ UI ถูกขวาง ไม่ใช่เวลาจนได้ภาพแรก หน่วยความจำ CTk/PIL ที่ลดการสร้างเป็นจำนวน object ไม่ใช่ผลวัด RAM ของโปรแกรมจริง

ยังไม่ได้วัด CPU/RAM ระหว่างเปิดกล้องจริง ความแม่นยำ Liveness/Facenet throughput หลายกล้อง หรือ latency เครือข่าย Hugging Face/Supabase การอ่าน credential/Lab ซ้ำเพิ่ม DB read เพื่อยืนยันสิทธิ์สด จึงไม่อ้างว่าทุก request จะตอบเร็วขึ้นตามตัวเลขในตาราง

## Verification

ผลทดสอบในชุดนี้: Backend 226 tests, skipped 10; Gatekeeper 34 tests ผ่าน การทดสอบใช้ SQLite ในหน่วยความจำและ mock กล้อง/AI ไม่มีการเชื่อมต่อฐานข้อมูลจริง

ครอบคลุมกฎเดิม รวมทั้ง connection ว่างระหว่าง AI, busy audit, คืนช่อง AI หลัง error, การเปลี่ยนสิทธิ์ระหว่าง AI, stale frame/generation, กล้องหลุด/เปลี่ยนกล้อง/ปิดโปรแกรม, ภาพดิบไม่ถูกวาดทับ, ไม่ส่ง POST ซ้ำ และไม่ส่งงานที่รอคิวหลัง shutdown

```powershell
# จาก workspace root
Push-Location backend
try {
    $env:SQLALCHEMY_DATABASE_URL = 'sqlite:///:memory:'
    .\venv\Scripts\python.exe -B -m unittest discover -s tests
} finally { Pop-Location }

Push-Location gatekeeper
try {
    $env:TEMP = (Resolve-Path -LiteralPath 'runtime').Path
    $env:TMP = $env:TEMP
    .\venv\Scripts\python.exe -B -m unittest discover -s tests
} finally { Pop-Location }

.\gatekeeper\venv\Scripts\python.exe -B scripts/benchmark_gatekeeper.py kiosk --output output/gatekeeper-optimization/recheck-kiosk.json
.\backend\venv\Scripts\python.exe -B scripts/benchmark_gatekeeper.py backend --output output/gatekeeper-optimization/recheck-backend.json
```

ไฟล์ tests ที่เพิ่ม/ปรับ: `backend/tests/test_gatekeeper_access.py`, `gatekeeper/tests/test_access_client.py`, `gatekeeper/tests/test_camera_stream.py`, `gatekeeper/tests/test_gatekeeper_access_flow.py` ส่วนเครื่องมือวัดซ้ำคือ `scripts/benchmark_gatekeeper.py`

## ก่อนใช้งานจริง

Deploy Backend และ build/อัปเดต Gatekeeper แยกจาก MSI ของ Agent แล้ว QA กล้องจริง: ถอด/เสียบกล้อง เปลี่ยนกล้อง ปิดโปรแกรมระหว่างตรวจ/HTTP ให้มีคำขอพร้อมกันหลายเครื่อง และตรวจผล granted/denied พร้อมประวัติ ไม่มีการ Push, deploy, build executable หรือรัน SQL จริงในงานนี้
