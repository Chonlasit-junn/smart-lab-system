const STORAGE_PREFIX = "smart-lab-admin-notifications:";
const MAX_STORED_IDS = 500;

export function adminNotificationStateKey(email) {
  const identity = typeof email === "string" ? email.trim().toLowerCase() : "";
  return identity ? `${STORAGE_PREFIX}${encodeURIComponent(identity)}` : null;
}

function normalizeIds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((id) => typeof id === "string"))].slice(-MAX_STORED_IDS);
}

export function readAdminNotificationState(storage, email) {
  const key = adminNotificationStateKey(email);
  if (!storage || !key) return { dismissed: [], seen: [] };
  try {
    const value = JSON.parse(storage.getItem(key) || "{}");
    return {
      dismissed: normalizeIds(value.dismissed),
      seen: normalizeIds(value.seen),
    };
  } catch {
    return { dismissed: [], seen: [] };
  }
}

export function writeAdminNotificationState(storage, email, state) {
  const key = adminNotificationStateKey(email);
  if (!storage || !key) return;
  try {
    storage.setItem(key, JSON.stringify({
      dismissed: normalizeIds(state.dismissed),
      seen: normalizeIds(state.seen),
    }));
  } catch {
    // Notifications remain usable when browser storage is unavailable.
  }
}
