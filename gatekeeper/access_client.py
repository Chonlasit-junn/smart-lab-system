"""Transport and fail-closed interpretation of a Gatekeeper access decision."""

import cv2
import requests
import threading

from device_registration import GATEKEEPER_DEVICE_PREFIX, RegistrationError, normalize_api_url


DENIAL_MESSAGES = {
    "face_service_busy": "ระบบตรวจใบหน้ากำลังให้บริการ กรุณาลองใหม่สักครู่",
    "camera_unavailable": "สิทธิ์ของกล้องถูกเปลี่ยน กรุณาติดต่อผู้ดูแล",
    "guest_approval_required": "บัญชี Guest ยังไม่ได้รับการอนุมัติจาก Admin",
    "account_inactive": "บัญชีนี้ถูกปิดใช้งาน กรุณาติดต่อผู้ดูแล",
    "user_banned": "บัญชีนี้ถูกแบนอยู่ ยังเข้าใช้งาน Lab ไม่ได้",
    "booking_required": "ไม่มีรายการจอง Lab นี้ในช่วงเวลาปัจจุบัน",
    "lab_unavailable": "Lab นี้ยังไม่เปิดให้เข้าใช้งาน กรุณาติดต่อผู้ดูแล",
    "liveness_no_motion": "กรุณาขยับศีรษะเล็กน้อยแล้วลองใหม่",
    "liveness_failed": "ไม่ผ่านการตรวจว่าเป็นบุคคลจริง",
    "invalid_liveness_score": "ผลตรวจคนจริงไม่ถูกต้อง กรุณาลองใหม่",
    "face_not_recognized": "ไม่พบใบหน้าที่ตรงกับผู้ใช้ที่ลงทะเบียน",
    "face_not_detected": "ตรวจไม่พบใบหน้า กรุณาหันหน้าเข้ากล้องแล้วลองใหม่",
    "exactly_one_face_required": "กรุณาสแกนใบหน้าทีละคน",
    "invalid_face_image": "ภาพใบหน้าไม่ถูกต้อง กรุณาลองใหม่",
    "face_image_too_large": "ภาพใบหน้ามีขนาดใหญ่เกินกำหนด",
    "face_service_unavailable": "ระบบจับคู่ใบหน้าไม่พร้อมใช้งาน กรุณาลองใหม่",
    "scan_history_unavailable": "บันทึกประวัติการสแกนไม่ได้ กรุณาติดต่อผู้ดูแล",
    "legacy_scan_disabled": "กรุณาอัปเดตโปรแกรม Gatekeeper",
}


class ScanClient:
    """Serialize access to one persistent Session, including shutdown."""

    def __init__(self):
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1, pool_maxsize=1, max_retries=0, pool_block=True,
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._lock = threading.Lock()
        self._closed = False

    def verify(self, *args, stop_event=None, **kwargs):
        with self._lock:
            if self._closed or (stop_event is not None and stop_event.is_set()):
                return False, "โปรแกรมกำลังปิดการทำงาน"
            return verify_scan(*args, client=self.session, **kwargs)

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self.session.close()


def verify_scan(
    api_url, registration, frame, liveness_score, *,
    liveness_passed=True, liveness_reason=None, lab_code=None, client=requests,
):
    """A grant requires local liveness AND the server's persisted decision."""
    registration = registration or {}
    if (
        not str(registration.get("device_id") or "").startswith(GATEKEEPER_DEVICE_PREFIX)
        or not registration.get("device_token")
    ):
        return False, "ต้องลงทะเบียนกล้องก่อนใช้งาน กรุณาติดต่อผู้ดูแล"
    try:
        backend_url = normalize_api_url(api_url)
    except RegistrationError:
        return False, "Backend URL ไม่ถูกต้อง กรุณาตรวจสอบการลงทะเบียนกล้อง"

    data = {
        "lab_code": registration.get("lab_code") or lab_code,
        "device_id": registration["device_id"],
        "device_token": registration["device_token"],
        "liveness_score": f"{liveness_score:.6f}",
        "liveness_passed": "true" if liveness_passed else "false",
    }
    if liveness_reason:
        data["liveness_reason"] = liveness_reason
    request = {"data": data, "timeout": 15}
    if liveness_passed:
        if frame is None:
            return False, DENIAL_MESSAGES["invalid_face_image"]
        try:
            encoded_ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except cv2.error:
            return False, DENIAL_MESSAGES["invalid_face_image"]
        if not encoded_ok:
            return False, DENIAL_MESSAGES["invalid_face_image"]
        request["files"] = {"face_image": ("gatekeeper.jpg", encoded.tobytes(), "image/jpeg")}

    try:
        response = client.post(f"{backend_url}/gatekeeper/identify", **request)
    except requests.RequestException:
        return False, "เชื่อมต่อ Backend ไม่ได้ — ยืนยันการบันทึกประวัติไม่ได้"
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return False, f"Backend ตอบกลับผิดรูปแบบ ({response.status_code})"

    scan_id = payload.get("scan_id")
    user_name = payload.get("user_name")
    if (
        response.status_code == 200
        and liveness_passed is True
        and payload.get("access_granted") is True
        and type(scan_id) is int and scan_id > 0
        and isinstance(user_name, str) and user_name.strip()
    ):
        return True, user_name
    if response.ok:
        # Old Backends return 200 after identity matching without access checks.
        return False, "Backend ยังไม่ยืนยันสิทธิ์เข้าห้องพร้อมประวัติ กรุณาอัปเดตระบบ"

    detail = payload.get("detail")
    if isinstance(detail, dict):
        return False, DENIAL_MESSAGES.get(detail.get("code"), "ระบบไม่อนุญาตให้เข้าห้อง กรุณาติดต่อผู้ดูแล")
    if isinstance(detail, str) and detail.strip():
        return False, detail[:250]
    return False, "ระบบไม่อนุญาตให้เข้าห้อง กรุณาติดต่อผู้ดูแล"
