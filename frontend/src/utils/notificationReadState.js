export const NOTIFICATION_READ_EVENT = 'smart-lab-notifications-read';

export function notificationReadKey(email) {
  const identity = typeof email === 'string' ? email.trim().toLowerCase() : '';
  return identity ? `last_seen_point_log_id:${encodeURIComponent(identity)}` : null;
}

export function readNotificationId(storage, key) {
  if (!key) return 0;
  try {
    const value = Number(storage.getItem(key));
    return Number.isSafeInteger(value) && value >= 0 ? value : 0;
  } catch { return 0; }
}

export function saveNotificationId(storage, key, id) {
  if (!key || !Number.isSafeInteger(id) || id < 0) return 0;
  const latest = Math.max(readNotificationId(storage, key), id);
  try { storage.setItem(key, String(latest)); } catch { /* Storage may be disabled. */ }
  return latest;
}
