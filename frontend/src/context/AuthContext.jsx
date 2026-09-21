import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { AuthContext } from './auth-context';

const API_URL = import.meta.env.VITE_API_URL;

function roleLabel(roleName) {
  return roleName === "admin" ? "Admin" : roleName === "student" ? "Student" : "Guest";
}

function readStoredUser() {
  const token = localStorage.getItem('access_token');
  if (!token) return null;

  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(window.atob(base64).split('').map((character) => {
      return '%' + ('00' + character.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));

    const decoded = JSON.parse(jsonPayload);
    if (typeof decoded.sub !== 'string' || !decoded.sub.includes('@')) {
      throw new Error('Token subject is missing.');
    }
    if (decoded.exp && Number(decoded.exp) * 1000 <= Date.now()) {
      throw new Error('Token has expired.');
    }

    const roleName = typeof decoded.role === "string" ? decoded.role : "guest";

    return {
      id: decoded.user_id || null,
      name: decoded.sub.split('@')[0],
      roleName,
      role: roleLabel(roleName),
      email: decoded.sub,
      initial: decoded.sub.charAt(0).toUpperCase(),
    };
  } catch (error) {
    console.error('Invalid token format', error);
    localStorage.removeItem('access_token');
    return null;
  }
}

function mergeProfileIntoUser(tokenUser, profile) {
  const roleName = profile.role || tokenUser.roleName;
  const profileName = [profile.first_name, profile.last_name]
    .filter(Boolean)
    .join(" ")
    .trim();
  const name = profileName || tokenUser.name;

  return {
    ...tokenUser,
    id: profile.id || tokenUser.id,
    name,
    email: profile.email || tokenUser.email,
    roleName,
    role: roleLabel(roleName),
    initial: name.charAt(0).toUpperCase(),
  };
}

// 2. สร้าง Provider เพื่อห่อหุ้มแอปพลิเคชัน
export const AuthProvider = ({ children }) => {
  const [currentUser, setCurrentUser] = useState(readStoredUser);
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem('access_token')));

  const refreshCurrentUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setCurrentUser(null);
      return null;
    }

    try {
      const response = await axios.get(`${API_URL}/users/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const tokenUser = readStoredUser();
      if (!tokenUser) return null;
      const nextUser = mergeProfileIntoUser(tokenUser, response.data || {});
      setCurrentUser(nextUser);
      return nextUser;
    } catch (error) {
      if ([401, 404].includes(error.response?.status)) {
        localStorage.removeItem('access_token');
        setCurrentUser(null);
      }
      return null;
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const token = localStorage.getItem('access_token');

    if (!token) {
      return undefined;
    }

    // The refresh synchronizes the token with the authoritative profile API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshCurrentUser().finally(() => {
      if (mounted) setLoading(false);
    });

    return () => {
      mounted = false;
    };
  }, [refreshCurrentUser]);

  const login = (token) => {
    localStorage.setItem('access_token', token);
    setCurrentUser(readStoredUser());
    setLoading(false);
    void refreshCurrentUser();
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setCurrentUser(null);
  };

  return (
    <AuthContext.Provider value={{ currentUser, login, logout, loading, refreshCurrentUser }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};
