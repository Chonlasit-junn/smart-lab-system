# Gatekeeper: ลดเวลารอภาพแรกหลังหน้าต่างเปิด

วันที่แก้: 28 ตุลาคม 2026 ผู้ใช้ยืนยันว่า UI เปิดแล้วแต่ภาพกล้องมาช้า

## สาเหตุและการแก้

เดิม camera worker เรียก `_discover()` ก่อนอ่านภาพจริง ทำให้เปิด–ปิด index 0–5 แล้วกลับมาเปิดกล้องที่เลือกอีกครั้ง รวม 7 ครั้งก่อนภาพแรก แม้ UI ไม่ถูกขวาง แต่ยังต้องรอ driver ของทุก index

แก้เป็นเปิดกล้องที่เลือกก่อนและใช้ handle นั้นอ่านภาพต่อทันที ค้นหากล้องอื่นอัตโนมัติเฉพาะเมื่อกล้องที่เลือกเปิด/อ่านไม่ได้ และหยุดเมื่อพบตัวแรกที่ใช้ได้ หากไม่พบเลยจะเว้นช่วงค้นหาทั้งชุด 5 วินาที พร้อมลองต่อกล้องหลักเป็นช่วง 0.5 วินาที

บน Windows ลอง DirectShow ก่อน และใช้ OpenCV auto backend เป็นทางสำรองหากเปิด/อ่านไม่ได้ ไม่อ้างว่า backend ใดเร็วที่สุดทุกกล้อง API เลือก backend ดู [เอกสาร OpenCV](https://docs.opencv.org/4.x/d0/da7/videoio_overview.html)

เพิ่มปุ่ม **ค้นหากล้องอื่น** ในเมนูกล้อง การค้นหาตามคำขอจะไม่เปิดกล้องที่กำลังใช้อยู่ซ้ำ แต่ภาพอาจหยุดระหว่าง probe กล้องอื่น ระบบแสดงสถานะค้นหาและพักการตรวจใบหน้า ไม่ให้เริ่มค้นหาระหว่างยืนยันสิทธิ์หรือ cooldown

จำ index ของกล้องที่ให้ภาพสำเร็จใน `camera_preferences.json` ข้างไฟล์ registration ของ Gatekeeper เก็บเฉพาะ `camera_index` ไม่มี token/password และไม่แก้ device credential หากอ่าน preference ไม่ได้/ข้อมูลผิดรูปแบบจะใช้ค่าเริ่มต้น หากบันทึกไฟล์ไม่ได้ยังใช้กล้องต่อได้

Native camera handles ยังมี owner thread เดียว generation และ freshness ยังป้องกันภาพ/ผลตรวจจากกล้องเก่า การเปลี่ยนกล้องระหว่าง discovery ไม่ทำให้ pixels กล้องเก่าถูกระบุเป็นกล้องใหม่ ไม่เปลี่ยน ONNX/โมเดล Liveness, thresholds, sampling, Backend, Booking, Guest, Ban หรือประวัติสแกน

## ผลวัดจำลองก่อน–หลัง

จำลองการเปิดกล้องที่มีอยู่ 20 ms, index ที่ไม่มี 100 ms, อ่านเฟรม 5 ms วัดตั้งแต่ `CameraStream.start()` จนมี snapshot แรก ไม่ใช่เวลาเปิด EXE/แตกไฟล์หรือผลจากกล้องจริง

| กรณี | ก่อน | หลัง | จำนวนเปิดกล้องก่อนภาพแรก |
|---|---:|---:|---|
| เลือก 0, กล้อง 0 ใช้ได้ | 556.85 ms | 29.19 ms | 7 → 1 |
| จำกล้อง 3, กล้อง 3 ใช้ได้ | 548.96 ms | 27.43 ms | 7 → 1 |
| เลือก 0 หาย แต่กล้อง 3 ใช้ได้ | 549.63 ms | 429.66 ms | 7 → 5 |

ผลดิบ: `output/gatekeeper-camera-start/before.json` และ `after.json` กล้องจริงยังมีค่าเปิด native driver/ตั้งความละเอียด/อ่านเฟรมแรกที่ต่างกัน ไม่มีการตั้ง timeout ที่ backend ของ OpenCV ไม่รองรับ และ stop event ไม่สามารถขัดจังหวะ native call ที่ค้างอยู่ได้

## Verification และ EXE

Gatekeeper **56 tests ผ่านทั้งหมด** รวม camera fast path, backend fallback, discovery ไม่เปิด active handle ซ้ำ, สลับกล้องระหว่าง discovery, transient empty frames, shutdown, preferences, ONNX/PyTorch parity, และ Backend-denial flow

```powershell
# เริ่มใน gatekeeper/
$env:TEMP = (Resolve-Path -LiteralPath 'runtime').Path
$env:TMP = $env:TEMP
.\venv\Scripts\python.exe -B -m unittest discover -s tests
.\venv\Scripts\python.exe -B ..\scripts\benchmark_camera_start.py --output ..\output\gatekeeper-camera-start\recheck.json
.\venv\Scripts\python.exe -B -m PyInstaller --noconfirm --distpath dist/onnx-camera-fast --workpath build/onnx-camera-fast smart_gatekeeper.spec
```

EXE ฉบับแก้: `gatekeeper/dist/onnx-camera-fast/SmartGatekeeper.exe` ขนาด **86,141,934 bytes** SHA-256 `ea9655d5c867836daa6d666a63058bddfd6c2e77067558f8ba17d2731549512a`

ผ่าน packaged self-test โดยตัด Python/venv ออกจาก PATH โหลด ONNX FP32 สำเร็จและไม่โหลด PyTorch ผลอยู่ที่ `output/gatekeeper-camera-start/bundle-self-test.json` self-test นี้ไม่เปิดกล้องจริงหรือเรียก Backend ต้อง QA เวลาภาพแรกและเลือกกล้องที่ถูกต้องบนเครื่องติดตั้งจริง โดยเฉพาะเครื่องที่มีหลายกล้อง/driver ต่างกัน

ไฟล์ที่เพิ่ม/แก้: `gatekeeper/camera_stream.py`, `gatekeeper/camera_preferences.py`, `gatekeeper/smart_gatekeeper.py`, tests ของ camera stream/preferences/access flow, `scripts/benchmark_camera_start.py`, ปรับ fake driver ใน `scripts/benchmark_gatekeeper.py` และคู่มือที่เชื่อมโยงมาหน้านี้ ไม่มี dependencies, migration หรือการแก้ฐานข้อมูลจริงเพิ่ม ไม่ Push/deploy และเก็บ EXE ทดลองรุ่นก่อนหน้าไว้
