// ============================================================================
// 1. IMPORTS & CONFIGURATION
// ============================================================================
import React, { useState } from 'react';
import axios from 'axios'; 
import { 
  TextField, Button, IconButton, InputAdornment, Alert, CircularProgress 
} from '@mui/material';
import { useNavigate, Link as RouterLink } from 'react-router-dom'; 

import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';

import { useAuth } from '../context/AuthContext';

// API Endpoint configuration
const API_URL = 'http://localhost:8000'; 

// ============================================================================
// 2. MAIN COMPONENT
// ============================================================================
export default function Login() {
  
  // --- Contexts & Hooks ---
  const navigate = useNavigate();
  const { login } = useAuth(); 

  // ============================================================================
  // 3. STATE MANAGEMENT
  // ============================================================================
  
  /** @description Form Data States - เก็บข้อมูลที่ผู้ใช้พิมพ์เข้ามา */
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  /** @description Error States - เก็บข้อความแจ้งเตือนข้อผิดพลาดแต่ละจุด */
  const [emailError, setEmailError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [apiError, setApiError] = useState(''); 

  /** @description UI States - ควบคุมการแสดงผล (เช่น โหลดดิ้ง, ปิดเปิดตาดูรหัสผ่าน) */
  const [loading, setLoading] = useState(false); 
  const [showPassword, setShowPassword] = useState(false);

  // ============================================================================
  // 4. EVENT HANDLERS
  // ============================================================================

  /**
   * @function handleClickShowPassword
   * @description สลับสถานะการแสดงผลรหัสผ่าน (ซ่อน/แสดง)
   */
  const handleClickShowPassword = () => {
    setShowPassword(!showPassword);
  };

  /**
   * @function handleLogin
   * @description ตรวจสอบข้อมูลเบื้องต้น (Validation) และส่ง Request ไปล็อกอินที่ Backend
   */
  const handleLogin = async () => {
    let isValid = true;
    setApiError(''); 

    // --- Validation: เช็กเงื่อนไข Email ---
    if (!email) {
      setEmailError('Please enter your email address');
      isValid = false;
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      setEmailError('Invalid email format');
      isValid = false;
    } else {
      setEmailError('');
    }

    // --- Validation: เช็กเงื่อนไข Password ---
    if (!password) {
      setPasswordError('Please enter your password');
      isValid = false;
    } else {
      setPasswordError('');
    }

    // --- API Call: ถ้าข้อมูลผ่านเกณฑ์ ให้ยิง API ---
    if (isValid) {
      setLoading(true);
      try {
        // FastAPI OAuth2PasswordRequestForm รับข้อมูลแบบ x-www-form-urlencoded
        const params = new URLSearchParams();
        params.append('username', email);
        params.append('password', password);

        const response = await axios.post(`${API_URL}/login`, params, {
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
          }
        });

        // 🌟 อัปเดต Context แจ้งส่วนกลางว่าล็อกอินสำเร็จ พร้อมเก็บ Token
        login(response.data.access_token);
        
        // 🌟 วาร์ปผู้ใช้เข้าไปที่หน้าหลัก (Dashboard/Booking)
        navigate('/'); 

      } catch (err) {
        // ดักจับ Error จาก Backend เช่น รหัสผ่านผิด หรือไม่มีอีเมลนี้ในระบบ
        setApiError(err.response?.data?.detail || "เกิดข้อผิดพลาดในการเข้าสู่ระบบ");
      } finally {
        setLoading(false);
      }
    }
  };

  // ============================================================================
  // 5. RENDER UI
  // ============================================================================
  return (
    <div className="login-wrapper">
      <div className="login-container">
        
        {/* --- LEFT PANEL: Branding & Visuals --- */}
        <div className="login-banner">
          <div className="login-banner-icon">🖥️</div>
          <h2 className="login-banner-title">Smart Lab</h2>
          <p className="login-banner-subtitle">
            Reserve your lab space effortlessly.<br />
            For students and guests.
          </p>
        </div>

        {/* --- RIGHT PANEL: Login Form --- */}
        <div className="login-form-section">
          <h1 className="login-title">Log in</h1>
          <p className="login-subtitle">Please enter your details to access the lab.</p>

          {/* API Error Alert */}
          {apiError && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: '8px' }}>
              {apiError}
            </Alert>
          )}

          {/* Email Input */}
          <TextField 
            fullWidth 
            label="Email address" 
            variant="outlined" 
            className="login-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)} 
            error={!!emailError} 
            helperText={emailError} 
            sx={{ mb: 2 }} 
          />

          {/* Password Input */}
          <TextField 
            fullWidth 
            label="Password" 
            type={showPassword ? 'text' : 'password'} 
            variant="outlined" 
            className="login-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={!!passwordError}
            helperText={passwordError}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={handleClickShowPassword} edge="end">
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              )
            }}
            sx={{ mb: 3 }}
          />

          {/* Submit Button */}
          <Button 
            fullWidth 
            variant="contained" 
            className="login-button"
            onClick={handleLogin}
            disabled={loading} 
            sx={{ height: '54px', fontSize: '1rem', fontWeight: 'bold' }}
          >
            {loading ? <CircularProgress size={24} color="inherit" /> : 'Log in'}
          </Button>

          {/* Footer Links */}
          <div className="login-links">
            <a href="#" className="login-link">Forget Password?</a>
            <RouterLink to="/register" className="login-link">Create Account</RouterLink>
          </div>
        </div>

      </div>
    </div>
  );
}