import React, { createContext, useState, useEffect, useContext, useCallback } from 'react';

// 1. สร้าง Context
const AuthContext = createContext();

// 2. สร้าง Provider เพื่อห่อหุ้มแอปพลิเคชัน
export const AuthProvider = ({ children }) => {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // 🌟 จัดการเอาฟังก์ชันมาไว้ก่อน useEffect และครอบด้วย useCallback เพื่อป้องกัน Error
  const checkAuth = useCallback(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        // ใช้ window.atob เพื่อให้ Linter รู้จักคำสั่งนี้ชัดเจน
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));

        const decoded = JSON.parse(jsonPayload);
        setCurrentUser({ 
          name: decoded.sub.split('@')[0], 
          role: decoded.role === 'student' ? 'Student' : 'Guest', 
          email: decoded.sub, 
          initial: decoded.sub.charAt(0).toUpperCase() 
        });
      } catch (error) {
        console.error("Invalid token format", error);
        localStorage.removeItem('access_token');
        setCurrentUser(null);
      }
    } else {
      setCurrentUser(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = (token) => {
    localStorage.setItem('access_token', token);
    checkAuth(); 
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setCurrentUser(null);
  };

  return (
    <AuthContext.Provider value={{ currentUser, login, logout, loading }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

// 3. สร้าง Hook สำหรับเรียกใช้
export const useAuth = () => {
  return useContext(AuthContext);
};