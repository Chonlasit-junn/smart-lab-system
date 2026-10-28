# Gatekeeper: ทดลอง ONNX Runtime FP32

ฉบับแก้การรอภาพแรกหลังเปิดหน้าต่าง: [Camera startup](GATEKEEPER_CAMERA_START.md) ใช้ EXE ที่ `gatekeeper/dist/onnx-camera-fast/SmartGatekeeper.exe` โดยคง ONNX FP32 ชุดเดียวกัน

## โครงสร้างที่คงเดิม

ใช้ MiniFASNetV2 จาก Silent-Face-Anti-Spoofing และน้ำหนัก `2.7_80x80_MiniFASNetV2.pth` เดิม โดยแปลงเป็น ONNX opset 17 แบบ FP32 ไม่มี quantization หรือฝึกโมเดลใหม่ เก็บไฟล์โมเดลและ manifest คู่กันที่:

```text
gatekeeper/Silent-Face-Anti-Spoofing/resources/anti_spoof_models/
  2.7_80x80_MiniFASNetV2.fp32.onnx
  2.7_80x80_MiniFASNetV2.fp32.json
```

ต้นฉบับ `.pth` SHA-256: `a5eb02e1843f19b5386b953cc4c9f011c3f985d0ee2bb9819eea9a142099bec0`

ONNX SHA-256: `5237cabc7ad9be84c66eb3c608ef0303c91d828f42456530fc579b9388d3c0f0`

การเตรียมภาพตรงกับ `src/data_io/functional.py` ของต้นฉบับ: BGR uint8 80×80 → NCHW FP32 ช่วง 0–255 **ไม่หาร 255 และไม่สลับเป็น RGB** กราฟรวม Softmax เดิมไว้แล้ว คะแนนคนจริงยังอยู่ index 1

กล้องและ Haar Cascade, crop ขยาย 2.7 เท่า, เก็บ 5 ตัวอย่างต้องผ่าน 4, threshold 0.72, motion score 2.0, ช่วงเก็บตัวอย่าง 0.12 วินาที และ UI/cooldown คงเดิม รวมถึงการลงทะเบียนกล้อง Device Credential, Facenet บน Backend, Booking/Guest/Ban และการ commit ประวัติก่อนอนุญาต

ค่าเริ่มต้นของ source และ EXE เป็น ONNX CPU Runtime โหลดโมเดลครั้งเดียว กำหนด 2 inference threads และ 1 inter-op thread ระบบตรวจ hash/manifest/ชนิดข้อมูล/shape และผล probability หากโมเดลหรือ runtime ไม่พร้อม จะขึ้น MODEL ERROR และไม่เปิดข้าม Liveness ไม่มี fallback ไป PyTorch อัตโนมัติ

## Dependencies และการรัน

คำสั่งต่อไปนี้เริ่มจาก `gatekeeper/` ใช้ Python ของ environment โดยระบุ path ตรง ไม่ต้องแก้ environment file หรือ Secrets ของ Backend

```powershell
# ใช้งานปกติ: ONNX Runtime CPU โดยไม่ต้องติดตั้ง PyTorch
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -B smart_gatekeeper.py
```

เฉพาะเครื่องพัฒนา/แปลงโมเดล/เทียบผล:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-export.txt
.\venv\Scripts\python.exe -B ..\scripts\export_gatekeeper_onnx.py
```

Exporter ต้องมี `.pth` เดิมตาม hash ข้างต้น จะตรวจกราฟ FP32 และเทียบ 16 ภาพสังเคราะห์ก่อนแทนไฟล์โมเดลที่ใช้งานได้ ไม่ดาวน์โหลดโมเดลหรือติดตั้งอะไรตอนผู้ใช้เปิดโปรแกรม

แยก PyTorch ไว้เป็น reference สำหรับการพัฒนาเท่านั้น หากต้องย้อนทดลองกับ runtime เดิมจาก source:

```powershell
$env:SMART_GATEKEEPER_LIVENESS_BACKEND = 'pytorch'
.\venv\Scripts\python.exe -B smart_gatekeeper.py
Remove-Item Env:SMART_GATEKEEPER_LIVENESS_BACKEND
```

EXE ไม่บรรจุ PyTorch และปฏิเสธการเลือก backend นี้ กำหนด thread ผ่าน `SMART_GATEKEEPER_INFERENCE_THREADS` ได้ 1–8; ยังคงอ่าน `SMART_GATEKEEPER_TORCH_THREADS` เดิมเป็นค่ารองเพื่อไม่ให้เครื่องที่ตั้งไว้เสียพฤติกรรม

## Tests และการวัดซ้ำ

```powershell
# ใน gatekeeper/
$env:TEMP = (Resolve-Path -LiteralPath 'runtime').Path
$env:TMP = $env:TEMP
.\venv\Scripts\python.exe -B -m unittest discover -s tests
.\venv\Scripts\python.exe -m pip check

# ปิดงาน build/งานหนักก่อนวัดประสิทธิภาพ
.\venv\Scripts\python.exe -B ..\scripts\benchmark_gatekeeper_onnx.py --runs 3 --iterations 200 --output ..\output\gatekeeper-onnx\comparison.json
```

Parity suite ใช้ demo images จากโครงการต้นทาง 3 รูป ครอปด้วย detector RetinaFace ของต้นทางเพื่อให้ภาพโจมตีจากหน้าจอถูกส่งถึงโมเดลทดสอบ (ไม่ได้เปลี่ยน Haar gate ในโปรแกรมจริง), ภาพดัดแปลง brightness/blur/flip/shift/JPEG และภาพสังเคราะห์ รวม 50 inputs ตรวจ:

- probability ทั้ง 3 class ด้วย `rtol=1e-4, atol=1e-5`, argmax และผล threshold 0.72
- ผลตัดสิน 5 เฟรมพร้อมเหตุผล ทั้ง motion ผ่านและไม่ผ่าน
- pixel/layout ตรงกับ ToTensor ต้นฉบับ, โมเดลหาย/เสีย, output ผิด, ไม่มีการนำเข้า PyTorch ใน runtime ONNX
- ใช้ ONNX จริงใน flow Liveness แต่จำลองคำตอบ Backend เพื่อยืนยันว่า Booking/Guest/Ban denial ยังปฏิเสธ

ผลที่รัน: Gatekeeper 45 tests ผ่านทั้งหมด; Backend เฉพาะ Gatekeeper 40 tests ผ่าน โดยใช้ SQLite ในหน่วยความจำและ mock Facenet ไม่ใช้ฐานข้อมูลจริง

Benchmark แยกเป็น subprocess ของแต่ละ runtime เพื่อไม่ให้ DLL/หน่วยความจำที่อีก runtime โหลดแล้วปนกัน ใช้ 2 CPU threads เท่ากัน สลับลำดับการรัน 3 รอบต่อ runtime อุ่นโมเดล 10 ครั้งแล้ววัด 200 ครั้งต่อรอบ วัด predict รวม preprocessing/Softmax, process CPU time, cold import+load และ Windows working set/private bytes รายละเอียดและคะแนนรายภาพอยู่ใน `output/gatekeeper-onnx/comparison.json`

### ผลวัด 28 ตุลาคม 2026

วัดบน Windows x64 / Python 3.11.9 ด้วย PyTorch 2.1.2+cpu และ ONNX Runtime 1.23.2 ทั้งสอง process โหลด NumPy/OpenCV/Pillow เหมือนกัน ปิดงาน build และ tests ระหว่างวัด ตัวเลขเป็น median ของ 3 รอบ:

| ตัวชี้วัด | PyTorch | ONNX FP32 |
|---|---:|---:|
| predict ต่อภาพ รวม preprocessing และ Softmax | 49.224 ms | 6.020 ms |
| p95 predict ต่อภาพ | 68.572 ms | 8.959 ms |
| process CPU time ต่อภาพ | 51.484 ms | 11.328 ms |
| import libraries + โหลดโมเดล ใน process ใหม่ | 13,507 ms | 1,721 ms |
| working set ของ process ทดสอบ | 212.57 MiB | 72.55 MiB |
| private bytes ของ process ทดสอบ | 276.35 MiB | 83.13 MiB |
| ขนาดแพ็กเกจ runtime ที่ติดตั้งบนดิสก์ | 1,059.27 MB | 43.38 MB |

ในชุดนี้ predict เร็วขึ้นประมาณ **8.18 เท่า** และ working set ลดลงประมาณ **66%** ขนาดแพ็กเกจในตารางนับเฉพาะ `torch`/`onnxruntime` ไม่ใช่ทั้ง venv หรือ EXE ส่วนค่า cold import ไม่ใช่เวลาเปิดแอปจนพร้อมสแกน และ memory ไม่ใช่ RAM รวมของ UI/กล้อง/โปรแกรมจริง ช่วงรอเก็บ 5 เฟรม เครือข่าย และ Facenet/ฐานข้อมูลบน Backend ยังเป็นงานเดิม จึงไม่อ้างว่าเวลาสแกนทั้ง flow เร็วขึ้น 8 เท่า

Probability ต่างกันสูงสุด **0.0000035167** ใน 50 inputs; argmax และ threshold decision ตรงกันทั้งหมด การตัดสินหลายเฟรม 100 ชุดจำลองตรงกันทั้งหมด (ผ่าน 31 / ปฏิเสธ 69 ทั้งสอง runtime) ช่วง motion ของ benchmark เป็นข้อมูลควบคุมเพื่อทดสอบ logic ไม่ใช่วิดีโอเคลื่อนไหวจริง

ค่าความแม่นยำที่เทียบเป็น **ความสอดคล้องกับ PyTorch บนชุดทดสอบนี้** ไม่ใช่ผลรับรอง anti-spoof กับทุกกล้อง ผลของกล้อง/แสงจริงและ false accept/false reject ต้องให้ QA ทดสอบต่อ ไม่ได้ใช้รูปผู้ใช้หรือบันทึกข้อมูล production

## Build และตรวจการบรรจุ runtime

```powershell
# ใน gatekeeper/
.\venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\venv\Scripts\python.exe -B -m PyInstaller --noconfirm --distpath dist/onnx-fp32 --workpath build/onnx-fp32 smart_gatekeeper.spec

# ตรวจโมเดล/ONNX ใน EXE โดยไม่เปิดกล้อง ไม่ Login และไม่เรียก Backend
.\dist\onnx-fp32\SmartGatekeeper.exe --liveness-self-test C:\path\to\writable\self-test.json
```

Build นี้เป็น **EXE ทดลองของ Gatekeeper** แยกจาก MSI ของ Agent รวม ONNX Runtime, โมเดล, manifest และ license notices ไว้แล้ว Source/vendor PyTorch และ `.pth` ยังคงไว้สำหรับการแปลง/เทียบผล แต่ไม่บรรจุไปกับ EXE ต้อง QA บน Windows เครื่องสะอาดและกล้องจริงก่อนแจกใช้งาน

ผล build: `gatekeeper/dist/onnx-fp32/SmartGatekeeper.exe`, **86,139,619 bytes** (86.14 MB), SHA-256 `3049d79de9837b9e89c5f42c95e263928d336f256ea1a9a2a256f419d8cf3565` ตรวจ archive พบ ONNX Runtime DLL และ notices, ไม่พบ Torch DLL/`.pth` ผล self-test สำเร็จโดยตัด Python/venv ออกจาก PATH และรายงาน `torch_loaded: false` เก็บผลไว้ที่ `output/gatekeeper-onnx/bundle-self-test-final.json`

ไฟล์หลักที่เพิ่ม/แก้ในงานนี้: `gatekeeper/liveness_runtime.py`, `gatekeeper/liveness_reference.py`, `gatekeeper/smart_gatekeeper.py`, `gatekeeper/requirements.txt`, `gatekeeper/requirements-export.txt`, `gatekeeper/smart_gatekeeper.spec`, `gatekeeper/tests/liveness_samples.py`, `gatekeeper/tests/test_liveness_onnx.py`, `scripts/export_gatekeeper_onnx.py`, `scripts/benchmark_gatekeeper_onnx.py`, โมเดล ONNX/manifest และคู่มือ README/Gatekeeper ที่เกี่ยวข้อง

งานนี้ไม่แก้ Backend/schema เพิ่ม ไม่รัน migration ไม่แก้ฐานข้อมูลจริง และไม่ Push/deploy ส่วน Migration 017 จากงาน Gatekeeper access ก่อนหน้ายังต้องจัดการโดยผู้ดูแลตามคู่มือเดิม
