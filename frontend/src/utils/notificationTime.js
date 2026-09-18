// ============================================================================
// notificationTime.js
// ตัวช่วยสำหรับ "การแจ้งเตือน" แบบ YouTube
//  - formatRelativeTime : แปลงเวลาเป็นข้อความ เช่น "12 นาทีที่ผ่านมา"
//  - groupNotifications : แบ่งรายการแจ้งเตือนออกเป็น 2 กลุ่ม "วันนี้" / "ที่ผ่านมา"
// ============================================================================

/** แปลงค่าที่รับเข้ามา (string | number | Date) ให้เป็น Date ที่ใช้งานได้ หรือ null */
export function toDate(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** เช็คว่าเป็น "วันเดียวกัน" ตามเวลาท้องถิ่นหรือไม่ */
export function isSameDay(a, b) {
  if (!a || !b) return false;
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** เช็คว่าเป็น "วันนี้" หรือไม่ */
export function isToday(value, now = new Date()) {
  return isSameDay(toDate(value), now);
}

/**
 * แปลงเวลาเป็นข้อความสัมพัทธ์แบบ YouTube
 * เช่น "เมื่อสักครู่", "12 นาทีที่ผ่านมา", "18 ชั่วโมงที่ผ่านมา", "3 วันที่ผ่านมา"
 * ถ้าเกิน 7 วันจะแสดงเป็นวันที่แบบเต็ม (เช่น 12 ก.ย. 2568)
 */
export function formatRelativeTime(value, now = new Date()) {
  const date = toDate(value);
  if (!date) return "—";

  const diffMs = now.getTime() - date.getTime();

  // กันกรณีเวลาเครื่อง client เร็วกว่าเซิร์ฟเวอร์เล็กน้อย
  if (diffMs < 0) return "เมื่อสักครู่";

  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) return "เมื่อสักครู่";
  if (diffMinutes < 60) return `${diffMinutes} นาทีที่ผ่านมา`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} ชั่วโมงที่ผ่านมา`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return "เมื่อวานนี้";
  if (diffDays < 7) return `${diffDays} วันที่ผ่านมา`;

  return date.toLocaleDateString("th-TH", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** ข้อความเวลาแบบเต็ม ใช้เป็น tooltip เวลา hover */
export function formatFullTime(value) {
  const date = toDate(value);
  return date ? date.toLocaleString("th-TH") : "—";
}

/**
 * แบ่งรายการแจ้งเตือนเป็น 2 กลุ่มตามวันที่สร้าง
 * โครงสร้างที่คืนค่า: [{ key, label, items: [...] }] (เฉพาะกลุ่มที่มีข้อมูล)
 *
 * @param {Array} notifications รายการแจ้งเตือน (ต้องมี field วันที่)
 * @param {Object} options
 * @param {Function} options.getDate ฟังก์ชันดึงค่าวันที่จากแต่ละรายการ (ค่าเริ่มต้น n.createdAt)
 * @param {Date}     options.now     เวลาปัจจุบัน (ใส่เองได้เพื่อความสะดวกในการทดสอบ)
 */
export function groupNotifications(notifications = [], options = {}) {
  const { getDate = (n) => n.createdAt, now = new Date() } = options;

  const today = [];
  const earlier = [];

  notifications.forEach((item) => {
    const date = toDate(getDate(item));
    if (date && isSameDay(date, now)) {
      today.push(item);
    } else {
      earlier.push(item);
    }
  });

  // เรียงจากใหม่ -> เก่า ภายในแต่ละกลุ่ม
  const byNewest = (a, b) => {
    const da = toDate(getDate(a));
    const db = toDate(getDate(b));
    return (db ? db.getTime() : 0) - (da ? da.getTime() : 0);
  };
  today.sort(byNewest);
  earlier.sort(byNewest);

  return [
    { key: "today", label: "วันนี้", items: today },
    { key: "earlier", label: "ที่ผ่านมา", items: earlier },
  ].filter((group) => group.items.length > 0);
}

export default groupNotifications;
