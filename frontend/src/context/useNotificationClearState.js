import { useCallback, useSyncExternalStore } from 'react';
import { notificationClearKey, readNotificationId, saveNotificationId } from '../utils/notificationReadState.js';

export const NOTIFICATION_CLEAR_EVENT = 'smart-lab-notifications-cleared';

export function useNotificationClearState(email) {
  const key = notificationClearKey(email);
  const snapshot = useCallback(() => readNotificationId(window.localStorage, key), [key]);
  const subscribe = useCallback(notify => {
    const onStorage = event => { if (event.key === null || event.key === key) notify(); };
    const onClear = event => { if (event.detail === key) notify(); };
    window.addEventListener('storage', onStorage);
    window.addEventListener(NOTIFICATION_CLEAR_EVENT, onClear);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(NOTIFICATION_CLEAR_EVENT, onClear);
    };
  }, [key]);
  const clearedThroughId = useSyncExternalStore(subscribe, snapshot, () => 0);
  const clearThrough = useCallback(id => {
    if (!key) return;
    saveNotificationId(window.localStorage, key, id);
    window.dispatchEvent(new CustomEvent(NOTIFICATION_CLEAR_EVENT, { detail: key }));
  }, [key]);
  return [clearedThroughId, clearThrough];
}
