import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  TextField, Button, IconButton, InputAdornment, Alert, CircularProgress, Box, Divider
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import { useAuth } from '../context/auth-context';
import { loginLocales } from '../utils/locales';
import { useLanguage } from '../context/language-context.js';

const API_URL = import.meta.env.VITE_API_URL;

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const { language: lang } = useLanguage();
  const t = loginLocales[lang];

  const [email, setEmail]             = useState('');
  const [password, setPassword]       = useState('');
  const [emailError, setEmailError]   = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [apiError, setApiError]       = useState('');
  const [isPending, setIsPending]     = useState(false);
  const [loading, setLoading]         = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    document.title = t.tabTitle;
  }, [t]);

  const handleLogin = async () => {
    let isValid = true;
    setApiError('');
    setIsPending(false);

    if (!email) {
      setEmailError(t.errEmail);
      isValid = false;
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      setEmailError(t.errEmailFormat);
      isValid = false;
    } else {
      setEmailError('');
    }

    if (!password) {
      setPasswordError(t.errPassword);
      isValid = false;
    } else {
      setPasswordError('');
    }

    if (!isValid) return;

    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('username', email.trim().toLowerCase());
      params.append('password', password);

      const response = await axios.post(`${API_URL}/login`, params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      login(response.data.access_token);

      const base64Url = response.data.access_token.split('.')[1];
      const base64Safe = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const payload = JSON.parse(atob(base64Safe));


      if (payload.role === 'admin') {
        navigate('/admin');
      } else {
        navigate('/booking');
      }
    } catch (err) {
      if (err.response?.status === 403) {
        setIsPending(true);
        setApiError(err.response?.data?.detail || t.pendingMsg);
      } else {
        setApiError(err.response?.data?.detail || t.invalidMsg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!loading) handleLogin();
  };

  return (
    <div className="login-wrapper" style={{ position: 'relative' }}>

      <div className="login-container">

        {/* ฝั่งซ้าย: banner */}
        <div className="login-banner">
          <h1 className="login-banner-title">
            {lang === 'th' ? (
              <>สำรวจห้องแล็บ<br />ที่คุณ<br /><span style={{ color: 'var(--brand-color)' }}>ต้องการ</span></>
            ) : (
              <>Explore<br />the labs<br /><span style={{ color: 'var(--brand-color)' }}>you need.</span></>
            )}
          </h1>
        </div>

        {/* ฝั่งขวา: ฟอร์ม login */}
        <div className="login-form-section">
          <form className="login-form-content" onSubmit={handleSubmit}>
            <h2 className="login-title">{t.pageTitle}</h2>

            {apiError && (
              <Alert
                severity={isPending ? 'warning' : 'error'}
                icon={isPending ? <HourglassEmptyIcon fontSize="inherit" /> : undefined}
                sx={{ mb: 3, borderRadius: '8px', fontWeight: '600' }}
              >
                {apiError}
              </Alert>
            )}

            <TextField
              fullWidth
              label={t.emailLabel}
              variant="outlined"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={!!emailError}
              helperText={emailError}
              sx={{ mb: 2 }}
            />

            <TextField
              fullWidth
              label={t.passwordLabel}
              type={showPassword ? 'text' : 'password'}
              variant="outlined"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={!!passwordError}
              helperText={passwordError}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{ mb: 3 }}
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              disabled={loading}
              sx={{
                height: '48px', fontSize: '1.1rem', fontWeight: 'bold',
                borderRadius: '24px', textTransform: 'none',
                backgroundColor: 'var(--brand-color)',
                color: 'var(--brand-contrast)',
                '&:hover': { backgroundColor: 'var(--brand-hover)' },
                mb: 2,
              }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : t.loginBtn}
            </Button>

            <Box sx={{ textAlign: 'center', mb: 3 }}>
              <a href="#" style={{ color: 'var(--brand-color)', textDecoration: 'none', fontSize: '0.95rem' }}>
                {t.forgotPassword}
              </a>
            </Box>

            <Divider sx={{ mb: 3 }} />

            <Button
              type="button"
              fullWidth
              variant="outlined"
              onClick={() => navigate('/register')}
              sx={{
                height: '48px', fontSize: '1.05rem', fontWeight: 'bold',
                borderRadius: '24px', textTransform: 'none',
                color: 'var(--brand-color)', borderColor: 'var(--brand-color)',
                '&:hover': { borderColor: 'var(--brand-hover)', backgroundColor: 'var(--brand-soft)' },
              }}
            >
              {t.createAccount}
            </Button>
          </form>
        </div>

      </div>
    </div>
  );
}
