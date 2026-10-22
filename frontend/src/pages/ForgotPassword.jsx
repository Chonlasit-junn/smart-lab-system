import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Alert, Box, Button, CircularProgress, IconButton, InputAdornment, TextField } from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { Link } from 'react-router-dom';
import { useLanguage } from '../context/language-context.js';
import { otpDeadlines, otpErrorMessage, requiresNewOtp, retrySeconds, secondsUntil } from '../utils/registrationOtp';
import { passwordResetError, passwordResetLocales } from '../utils/passwordReset';

const API_URL = import.meta.env.VITE_API_URL;

export default function ForgotPassword() {
  const { language } = useLanguage();
  const t = passwordResetLocales[language] || passwordResetLocales.th;
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [deadlines, setDeadlines] = useState({ expiresAt: 0, resendAt: 0 });
  const [now, setNow] = useState(Date.now);
  const pending = useRef(null);
  const panel = useRef(null);

  useEffect(() => { document.title = t.tabTitle; }, [t.tabTitle]);
  useEffect(() => {
    if (step === 4 || (step === 1 && deadlines.resendAt === 0)) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [step, deadlines.resendAt]);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => { panel.current?.scrollTo({ top: 0 }); }, [step]);

  const expiresIn = secondsUntil(deadlines.expiresAt, now);
  const resendIn = secondsUntil(deadlines.resendAt, now);
  const counter = (text, seconds) => text.replace('{seconds}', String(seconds));

  const run = async (action) => {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError('');
    try {
      await action(controller.signal);
    } catch (failure) {
      if (axios.isCancel(failure)) return;
      setError(otpErrorMessage(failure, t, t.failed));
      if (failure.response?.status === 429) {
        setDeadlines(previous => ({ ...previous, resendAt: Date.now() + retrySeconds(failure) * 1000 }));
      }
      if (requiresNewOtp(failure)) {
        setStep(2);
        setOtp('');
        setDeadlines(previous => ({ ...previous, expiresAt: 0 }));
      }
    } finally {
      if (!controller.signal.aborted) {
        pending.current = null;
        setBusy(false);
      }
    }
  };

  const request = () => {
    if (resendIn > 0) return;
    run(async signal => {
      const response = await axios.post(`${API_URL}/password-reset/request-otp`, { email: email.trim().toLowerCase() }, { signal });
      const receivedAt = Date.now();
      setNow(receivedAt);
      setDeadlines(otpDeadlines(response.data, receivedAt));
      setOtp('');
      setStep(2);
    });
  };

  const submit = (event) => {
    event.preventDefault();
    if (step === 1) return request();
    if (!/^[0-9]{6}$/.test(otp)) return setError(t.errOtpReq);
    if (expiresIn === 0) return setError(t.otpExpired);
    if (step === 3) {
      const validation = passwordResetError(password, confirmation, t);
      if (validation) return setError(validation);
    }
    run(async signal => {
      await axios.post(`${API_URL}/password-reset/${step === 2 ? 'verify-otp' : 'confirm'}`, {
        email: email.trim().toLowerCase(), otp,
        ...(step === 3 ? { new_password: password } : {}),
      }, { signal });
      if (step === 3) {
        setPassword('');
        setConfirmation('');
        setOtp('');
        setStep(4);
      } else setStep(3);
    });
  };

  return (
    <Box className="login-wrapper" sx={{ height: '100dvh', '& .login-banner': { display: { xs: 'none', md: 'flex' } },
      '& .login-form-section': { pb: { xs: '110px', md: '2rem' }, minHeight: 0 } }}>
      <div className="login-container">
        <div className="login-banner"><h1 className="login-banner-title">Smart Lab</h1></div>
        <div ref={panel} className="login-form-section" style={{ justifyContent: 'flex-start' }}>
          <form className="login-form-content" onSubmit={submit} style={{ marginBlock: 'auto', flexShrink: 0 }}>
            <h2 className="login-title">{t.title}</h2>
            {step === 4 ? <Alert severity="success" sx={{ my: 2 }}>{t.success}</Alert> : <>
              <p className="login-subtitle">{step === 1 ? t.intro : t.notice}</p>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
              <TextField fullWidth required name="email" type="email" autoComplete="email" label={t.emailLabel}
                value={email} disabled={step !== 1 || busy} onChange={event => setEmail(event.target.value)} sx={{ mb: 2 }} />
              {step === 2 && <TextField fullWidth required name="otp" label={t.otpLabel} value={otp} disabled={busy}
                onChange={event => setOtp(event.target.value.replace(/[^0-9]/g, '').slice(0, 6))}
                slotProps={{ htmlInput: { inputMode: 'numeric', autoComplete: 'one-time-code', maxLength: 6 } }} sx={{ mb: 2 }} />}
              {step === 3 && <>
                <TextField fullWidth required name="new_password" label={t.newPassword} value={password} disabled={busy}
                  type={showPassword ? 'text' : 'password'} autoComplete="new-password"
                  helperText={t.passwordHint} onChange={event => setPassword(event.target.value)} sx={{ mb: 2 }}
                  slotProps={{ input: { endAdornment: <InputAdornment position="end">
                    <IconButton type="button" aria-label={showPassword ? t.hidePassword : t.showPassword}
                      onClick={() => setShowPassword(value => !value)}>
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton></InputAdornment> } }} />
                <TextField fullWidth required name="confirm_password" label={t.confirmPassword} value={confirmation} disabled={busy}
                  type={showPassword ? 'text' : 'password'} autoComplete="new-password"
                  onChange={event => setConfirmation(event.target.value)} sx={{ mb: 2 }} />
              </>}
              {step > 1 && <p role="status" className="login-subtitle">
                {expiresIn > 0 ? counter(t.otpExpiresIn, expiresIn) : t.otpExpired}
              </p>}
              <Button fullWidth type="submit" variant="contained" disabled={busy || (step > 1 && expiresIn === 0) || (step === 1 && resendIn > 0)} sx={{ mb: 2 }}>
                {busy ? <CircularProgress size={22} color="inherit" /> : step === 1 ? t.reqOtpBtn : step === 2 ? t.verifyBtn : t.reset}
              </Button>
              {step > 1 && <Button fullWidth type="button" disabled={busy || resendIn > 0} onClick={request} sx={{ mb: 1 }}>
                {resendIn > 0 ? counter(t.otpResendWait, resendIn) : t.otpResend}
              </Button>}
              {step > 1 && <Button fullWidth type="button" disabled={busy} onClick={() => {
                setStep(1); setOtp(''); setPassword(''); setConfirmation(''); setError('');
              }}>{t.changeEmailBtn}</Button>}
              {step === 1 && resendIn > 0 && <p role="status">{counter(t.otpResendWait, resendIn)}</p>}
            </>}
            <p style={{ textAlign: 'center' }}><Link to="/" style={{ color: 'var(--brand-color)' }}>{t.loginHere}</Link></p>
          </form>
        </div>
      </div>
    </Box>
  );
}
