import { useCallback, useSyncExternalStore } from 'react';
import { NOTIFICATION_READ_EVENT, notificationReadKey, readNotificationId, saveNotificationId } from '../utils/notificationReadState.js';

export function useNotificationReadState(email) {
  const key = notificationReadKey(email);
  const snapshot = useCallback(() => readNotificationId(window.localStorage, key), [key]);
  const subscribe = useCallback(notify => {
    const onStorage = event => { if (event.key === null || event.key === key) notify(); };
    const onRead = event => { if (event.detail === key) notify(); };
    window.addEventListener('storage', onStorage);
    window.addEventListener(NOTIFICATION_READ_EVENT, onRead);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(NOTIFICATION_READ_EVENT, onRead);
    };
  }, [key]);
  const lastSeenId = useSyncExternalStore(subscribe, snapshot, () => 0);
  const markRead = useCallback(id => {
    if (!key) return;
    saveNotificationId(window.localStorage, key, id);
    window.dispatchEvent(new CustomEvent(NOTIFICATION_READ_EVENT, { detail: key }));
  }, [key]);
  return [lastSeenId, markRead];
}
