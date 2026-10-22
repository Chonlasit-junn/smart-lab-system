import axios from 'axios';
import { createNotificationStore } from './notificationStore.js';

export function readNotificationToken(email) {
  try {
    const token = window.localStorage.getItem('access_token');
    if (email === undefined) return token;
    if (!email || !token) return null;
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const bytes = Uint8Array.from(atob(payload), character => character.charCodeAt(0));
    const subject = JSON.parse(new TextDecoder().decode(bytes)).sub;
    // Another tab can replace localStorage before AuthContext rerenders here.
    // Never fetch that account's notifications under the previous profile.
    return typeof subject === 'string' && subject.toLowerCase() === email.toLowerCase() ? token : null;
  } catch { return null; }
}

let pageActive = true;
export const notificationStore = createNotificationStore({
  readToken: readNotificationToken,
  isVisible: () => pageActive && document.visibilityState !== 'hidden' && navigator.onLine !== false,
  fetchLogs: async (token, signal) => {
    const response = await axios.get(`${import.meta.env.VITE_API_URL}/users/me/points/logs`, {
      headers: { Authorization: `Bearer ${token}` }, signal,
      params: { limit: 20, notifications_only: true },
    });
    return response.data?.data;
  },
  listen: notify => {
    pageActive = true;
    const hide = () => { pageActive = false; notify(); };
    const show = () => { pageActive = true; notify(); };
    const storage = event => { if (event.key === null || event.key === 'access_token') notify(); };
    document.addEventListener('visibilitychange', notify);
    window.addEventListener('online', notify);
    window.addEventListener('offline', notify);
    window.addEventListener('pagehide', hide);
    window.addEventListener('pageshow', show);
    window.addEventListener('storage', storage);
    return () => {
      document.removeEventListener('visibilitychange', notify);
      window.removeEventListener('online', notify);
      window.removeEventListener('offline', notify);
      window.removeEventListener('pagehide', hide);
      window.removeEventListener('pageshow', show);
      window.removeEventListener('storage', storage);
    };
  },
});
