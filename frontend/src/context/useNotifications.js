import { useCallback, useSyncExternalStore } from 'react';
import { useAuth } from './auth-context';
import { notificationStore, readNotificationToken } from '../utils/notificationClient.js';

export function useNotifications(enabled = true) {
  const { currentUser } = useAuth();
  const email = enabled ? currentUser?.email : null;
  const token = enabled ? readNotificationToken(email) : null;
  const subscribe = useCallback(notify => notificationStore.subscribe(email, token, notify), [email, token]);
  const snapshot = useCallback(() => notificationStore.getSnapshot(email, token), [email, token]);
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  const refresh = useCallback((force = false) => {
    if (email && token === readNotificationToken()) return notificationStore.refresh(force);
  }, [email, token]);
  return { ...state, refresh };
}
