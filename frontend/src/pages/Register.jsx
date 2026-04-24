// ============================================================================
// 1. IMPORTS & CONFIGURATION
// ============================================================================
import React, { useState, useRef, useCallback } from 'react';
import axios from 'axios';
import Webcam from 'react-webcam';
import { 
  TextField, Button, IconButton, InputAdornment, Box, Typography, Alert, CircularProgress,
  Checkbox, FormControlLabel, Dialog, DialogTitle, DialogContent, DialogActions, Grid
} from '@mui/material';
import { useNavigate, Link as RouterLink } from 'react-router-dom';

// Icons
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import CameraAltIcon from '@mui/icons-material/CameraAlt';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import CancelIcon from '@mui/icons-material/Cancel';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import AppRegistrationIcon from '@mui/icons-material/AppRegistration';
import LanguageIcon from '@mui/icons-material/Language';

// Localization (i18n)
import { registerLocales } from '../utils/locales';

const API_URL = 'http://localhost:8000';

// ตั้งค่าความละเอียดและกล้องหน้าสำหรับ Webcam
const videoConstraints = { width: 400, height: 400, facingMode: "user" };

// ============================================================================
// 2. MAIN COMPONENT
// ============================================================================
export default function Register() {
  const navigate = useNavigate();
  
  // ============================================================================
  // 3. STATE MANAGEMENT
  // ============================================================================
  
  /** @description Language & Localization - จัดการภาษาของหน้าเว็บ (en/th) */
  const [lang, setLang] = useState('en');
  const t = registerLocales[lang]; 

  /** @description Progress & Status - จัดการขั้นตอนของฟอร์ม (Step 1-4) และสถานะการโหลด/แจ้งเตือน */
  const [step, setStep] = useState(1); 
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(''); 
  
  /** @description Form Data - จัดการข้อมูลที่ผู้ใช้กรอกในแต่ละขั้นตอน */
  const [accountType, setAccountType] = useState('general'); // 'general' หรือ 'student'
  const [consentChecked, setConsentChecked] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    first_name: '', last_name: '', email: '', otp: '', password: '', student_id: '', phone: ''
  });

  /** @description Face Capture - จัดการข้อมูลรูปภาพและสถานะการเปิด/ปิดกล้อง */
  const [faceImage, setFaceImage] = useState(null); 
  const [imagePreview, setImagePreview] = useState(null); 
  const [openCamera, setOpenCamera] = useState(false);
  const webcamRef = useRef(null);

  // ============================================================================
  // 4. EVENT HANDLERS & LOGIC
  // ============================================================================

  /**
   * @function handleChange
   * @description อัปเดตข้อมูลใน formData และเคลียร์ข้อความแจ้งเตือนเมื่อผู้ใช้เริ่มพิมพ์
   */
  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    if (error) setError('');
    if (success) setSuccess('');
  };

  /**
   * @function toggleLanguage
   * @description สลับภาษาระหว่างไทยและอังกฤษ
   */
  const toggleLanguage = () => {
    setLang(prev => prev === 'en' ? 'th' : 'en');
    setError(''); 
    setSuccess('');
  };

  /**
   * @function handleRequestOTP
   * @description (Step 1) ส่ง Email ไปขอรหัส OTP จาก Backend
   */
  const handleRequestOTP = async (e) => {
    e.preventDefault();
    if (!formData.email) return setError(t.errEmailReq);
    
    setLoading(true); setError(''); setSuccess('');
    try {
      const response = await axios.post(`${API_URL}/request-otp`, { email: formData.email });
      setAccountType(response.data.account_type); 
      setSuccess(response.data.message); 
      setStep(2); // ไปยังขั้นตอนที่ 2
    } catch (err) {
      setError(err.response?.data?.detail || "Connection error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function handleVerifyOTP
   * @description (Step 2) ส่ง OTP ไปตรวจสอบความถูกต้อง
   */
  const handleVerifyOTP = async (e) => {
    e.preventDefault();
    if (!formData.otp) return setError(t.errOtpReq);
    
    setLoading(true); setError(''); setSuccess('');
    try {
      await axios.post(`${API_URL}/verify-otp`, { email: formData.email, otp: formData.otp });
      setSuccess(lang === 'en' ? "OTP Verified Successfully." : "ยืนยัน OTP สำเร็จ");
      setStep(3); // ไปยังขั้นตอนที่ 3
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid OTP. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function handleGoToStep4
   * @description (Step 3) ตรวจสอบข้อมูลส่วนตัวก่อนไปยังขั้นตอนการถ่ายรูป
   */
  const handleGoToStep4 = (e) => {
    e.preventDefault();
    setError(''); setSuccess('');
    
    if (!formData.first_name || !formData.last_name || !formData.password) {
      return setError(t.errFieldsReq);
    }
    // ผู้ใช้ทั่วไปต้องกดยอมรับ Consent ก่อน
    if (accountType === 'general' && !consentChecked) {
      return setError(t.errConsent);
    }
    setStep(4); // ไปยังขั้นตอนที่ 4
  };

  /**
   * @function capture
   * @description ถ่ายรูปภาพจาก Webcam ปัจจุบันและแปลงเป็นไฟล์เตรียมส่ง API
   */
  const capture = useCallback(() => {
    const imageSrc = webcamRef.current.getScreenshot();
    if (imageSrc) {
        fetch(imageSrc).then(res => res.blob()).then(blob => {
            const file = new File([blob], "face_capture.jpg", { type: "image/jpeg" });
            setFaceImage(file);
        });
        setImagePreview(imageSrc);
        setOpenCamera(false); // ปิด Pop-up กล้อง
    }
  }, [webcamRef]);

  /**
   * @function handleImageUpload
   * @description จัดการเมื่อผู้ใช้อัปโหลดรูปภาพผ่านปุ่ม Upload
   */
  const handleImageUpload = (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setFaceImage(file);
      setImagePreview(URL.createObjectURL(file));
    }
  };

  /**
   * @function handleCompleteRegistration
   * @description (Step 4) รวบรวมข้อมูลทั้งหมดแล้วส่งไปยัง Backend เพื่อสร้างบัญชี
   */
  const handleCompleteRegistration = async (e) => {
    e.preventDefault();
    if (!faceImage) return setError(t.errFaceReq);

    setLoading(true); setError('');
    const submitData = new FormData();
    submitData.append('email', formData.email);
    submitData.append('otp', formData.otp); 
    submitData.append('password', formData.password);
    submitData.append('first_name', formData.first_name);
    submitData.append('last_name', formData.last_name);
    submitData.append('face_image', faceImage); 

    // แนบฟิลด์เฉพาะตามประเภทบัญชี
    if (accountType === 'student') {
      submitData.append('student_id', formData.student_id);
    } else {
      submitData.append('phone', formData.phone);
    }

    try {
      const response = await axios.post(`${API_URL}/register`, submitData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      alert(response.data.message);
      navigate('/login'); // สมัครเสร็จ พากลับไปหน้า Login
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed. Please contact support.");
    } finally {
      setLoading(false);
    }
  };

  // ============================================================================
  // 5. RENDER HELPERS (UI COMPONENTS)
  // ============================================================================
  
  const renderStep1 = () => (
    <>
      <h1 className="login-title">{t.step1Title}</h1>
      <p className="login-subtitle">{t.step1Sub}</p>
      <form onSubmit={handleRequestOTP}>
        <TextField fullWidth label={t.emailLabel} name="email" type="email" variant="outlined" className="login-input" value={formData.email} onChange={handleChange} sx={{ mb: 3 }} />
        <Button fullWidth type="submit" variant="contained" className="login-button" disabled={loading} endIcon={!loading && <ArrowForwardIcon />} sx={{ py: 1.5, fontSize: '1rem', fontWeight: 'bold' }}>
          {loading ? <CircularProgress size={24} color="inherit" /> : t.reqOtpBtn}
        </Button>
      </form>
    </>
  );

  const renderStep2 = () => (
    <>
      <h1 className="login-title">{t.step2Title}</h1>
      <p className="login-subtitle">{t.step2Sub} <b>{formData.email}</b></p>
      <form onSubmit={handleVerifyOTP}>
        <TextField fullWidth label={t.otpLabel} name="otp" type="text" variant="outlined" className="login-input" inputProps={{ maxLength: 6 }} value={formData.otp} onChange={handleChange} sx={{ mb: 3 }} />
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <Button fullWidth variant="outlined" color="primary" onClick={() => setStep(1)} startIcon={<ArrowBackIcon />} sx={{ height: '54px', fontSize: '0.95rem', fontWeight: 'bold', borderRadius: '12px', borderWidth: '2px' }}>
            {t.changeEmailBtn}
          </Button>
          <Button fullWidth type="submit" variant="contained" className="login-button" disabled={loading} endIcon={!loading && <ArrowForwardIcon />} sx={{ height: '54px', margin: '0 !important', padding: '0 !important', fontSize: '0.95rem', fontWeight: 'bold', borderRadius: '12px' }}>
            {loading ? <CircularProgress size={24} color="inherit" /> : t.verifyBtn}
          </Button>
        </Box>
      </form>
    </>
  );

  const renderStep3 = () => (
    <>
      <h1 className="login-title">{t.step3Title}</h1>
      <p className="login-subtitle">{t.step3Sub} <strong>{accountType === 'student' ? t.roleStudent : t.roleGuest}</strong></p>
      <form onSubmit={handleGoToStep4}>
        <Box sx={{ display: 'flex', gap: 2, mb: 0 }}>
          <TextField fullWidth label={t.firstName} name="first_name" variant="outlined" className="login-input" value={formData.first_name} onChange={handleChange} />
          <TextField fullWidth label={t.lastName} name="last_name" variant="outlined" className="login-input" value={formData.last_name} onChange={handleChange} />
        </Box>
        <TextField fullWidth label={t.emailLabel} name="email" variant="outlined" className="login-input" value={formData.email} disabled />

        {accountType === 'student' && (
          <Box sx={{ p: 2, mb: 2, mt: '-10px', bgcolor: '#f0f7ff', borderRadius: '8px', border: '1px solid #cce3ff' }}>
            <Typography variant="caption" color="primary" fontWeight="bold">{t.uniDetails}</Typography>
            <TextField fullWidth label={t.studentId} name="student_id" size="small" value={formData.student_id} onChange={handleChange} sx={{ mt: 1, bgcolor: 'white' }} />
          </Box>
        )}

        {accountType === 'general' && (
          <Box sx={{ p: 2, mb: 2, mt: '-10px', bgcolor: '#fff5f5', borderRadius: '8px', border: '1px solid #ffd6d6' }}>
            <Typography variant="caption" color="error" fontWeight="bold">{t.guestDetails}</Typography>
            <TextField fullWidth label={t.phoneNum} name="phone" size="small" type="tel" value={formData.phone} onChange={handleChange} sx={{ mt: 1, mb: 1, bgcolor: 'white' }} />
            <FormControlLabel
              control={<Checkbox checked={consentChecked} onChange={(e) => setConsentChecked(e.target.checked)} color="error" size="small" />}
              label={<Typography variant="body2" color="textSecondary" sx={{ fontSize: '0.8rem', lineHeight: 1.2 }}>{t.consentText}</Typography>}
              sx={{ alignItems: 'flex-start', mt: 1 }}
            />
          </Box>
        )}

        <TextField 
          fullWidth label={t.password} name="password" type={showPassword ? 'text' : 'password'} variant="outlined" className="login-input" 
          value={formData.password} onChange={handleChange} sx={{ mb: 3 }} inputProps={{ maxLength: 50 }} 
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <IconButton onClick={() => setShowPassword(!showPassword)} edge="end">
                  {showPassword ? <VisibilityOff /> : <Visibility />}
                </IconButton>
              </InputAdornment>
            )
          }}
        />

        <Button fullWidth type="submit" variant="contained" className="login-button" endIcon={<ArrowForwardIcon />} sx={{ height: '54px', margin: '0 !important', padding: '0 !important', fontSize: '1rem', fontWeight: 'bold', borderRadius: '12px' }}>
          {t.nextFaceSetup}
        </Button>
      </form>
    </>
  );

  const renderStep4 = () => (
    <>
      <h1 className="login-title">{t.step4Title}</h1>
      <p className="login-subtitle">{t.step4Sub}</p>
      <form onSubmit={handleCompleteRegistration}>
        <Box sx={{ mb: 3, textAlign: 'center' }}>
          {imagePreview ? (
            <Box sx={{ position: 'relative', display: 'inline-block' }}>
              <img src={imagePreview} alt="Face Capture" style={{ width: '200px', height: '200px', borderRadius: '50%', objectFit: 'cover', border: '4px solid #f0f0f0' }} />
              <IconButton onClick={() => { setImagePreview(null); setFaceImage(null); }} sx={{ position: 'absolute', top: 5, right: 5, bgcolor: 'white', '&:hover': { bgcolor: '#f0f0f0' } }}>
                <CancelIcon color="error" />
              </IconButton>
            </Box>
          ) : (
            <Box sx={{ p: 3, border: '2px dashed #ccc', borderRadius: '12px', bgcolor: '#fbfbfb', mb: 2 }}>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 1.5, fontSize: '0.9rem' }}>{t.faceInst}</Typography>
            </Box>
          )}
        </Box>

        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6}>
            <Button variant="outlined" fullWidth color="success" startIcon={<CameraAltIcon />} onClick={() => setOpenCamera(true)} sx={{ borderRadius: '12px', py: 1.5, textTransform: 'none', fontWeight: 'bold' }}>
              {t.openCam}
            </Button>
          </Grid>
          <Grid item xs={6}>
            <Button variant="outlined" component="label" fullWidth startIcon={<CloudUploadIcon />} sx={{ borderRadius: '12px', py: 1.5, textTransform: 'none', fontWeight: 'bold' }}>
              {t.uploadImg}
              <input hidden accept="image/*" type="file" onChange={handleImageUpload} />
            </Button>
          </Grid>
        </Grid>

        <Alert severity="info" sx={{ mb: 3, borderRadius: '8px', '& .MuiAlert-message': { fontSize: '0.85rem' } }}>{t.camNote}</Alert>

        <Box sx={{ display: 'flex', gap: 2, mt: 2, alignItems: 'center' }}>
          <Button fullWidth variant="outlined" color="primary" onClick={() => setStep(3)} startIcon={<ArrowBackIcon />} sx={{ height: '54px', fontSize: '0.95rem', fontWeight: 'bold', borderRadius: '12px', borderWidth: '2px' }}>
            {t.backBtn}
          </Button>
          <Button fullWidth type="submit" variant="contained" className="login-button" disabled={loading || !faceImage} sx={{ height: '54px', margin: '0 !important', padding: '0 !important', fontSize: '0.95rem', fontWeight: 'bold', borderRadius: '12px' }}>
            {loading ? <CircularProgress size={24} color="inherit" /> : t.completeBtn}
          </Button>
        </Box>
      </form>
    </>
  );

  const renderCameraDialog = () => (
    <Dialog open={openCamera} onClose={() => setOpenCamera(false)} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ textAlign: 'center', fontWeight: 'bold' }}>{t.camTitle}</DialogTitle>
      <DialogContent sx={{ p: 0, position: 'relative' }}>
        <Webcam audio={false} ref={webcamRef} screenshotFormat="image/jpeg" videoConstraints={videoConstraints} style={{ width: '100%', height: '100%', display: 'block' }} />
        <Box sx={{ position: 'absolute', top: '15%', left: '15%', right: '15%', bottom: '15%', border: '3px dashed white', borderRadius: '50%', pointerEvents: 'none' }} />
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'center', p: 2 }}>
        <Button variant="contained" color="success" onClick={capture} startIcon={<CameraAltIcon />}>{t.captureBtn}</Button>
        <Button variant="outlined" color="error" onClick={() => setOpenCamera(false)}>{t.cancelBtn}</Button>
      </DialogActions>
    </Dialog>
  );

  // ============================================================================
  // 6. MAIN RENDER
  // ============================================================================
  return (
    <div className="login-wrapper" style={{ position: 'relative' }}>
      
      {/* Floating Language Switcher */}
      <Box sx={{ position: 'absolute', top: 24, right: 24, zIndex: 10 }}>
        <Button 
          onClick={toggleLanguage} startIcon={<LanguageIcon />} variant="outlined" size="small"
          sx={{ 
            color: '#64748b', borderColor: '#e2e8f0', bgcolor: 'white', fontWeight: 'bold', 
            borderRadius: 2, textTransform: 'none', '&:hover': { bgcolor: '#f8fafc', borderColor: '#cbd5e1' }
          }}
        >
          {lang === 'en' ? 'ภาษาไทย' : 'English'}
        </Button>
      </Box>

      <div className="login-container">
        
        {/* --- LEFT PANEL: Branding --- */}
        <div className="login-banner">
          <AppRegistrationIcon sx={{ fontSize: 72, color: 'var(--banner-title)', mb: 2 }} />
          <h2 className="login-banner-title">{t.bannerTitle}</h2>
          <p className="login-banner-subtitle" dangerouslySetInnerHTML={{ __html: t.bannerSub }}></p>
        </div>

        {/* --- RIGHT PANEL: Dynamic Form Steps --- */}
        <div className="login-form-section">
          {error && <Alert severity="error" sx={{ mb: 2, borderRadius: '8px' }}>{error}</Alert>}
          {success && step !== 4 && <Alert severity="success" sx={{ mb: 2, borderRadius: '8px' }}>{success}</Alert>}

          {/* Conditional Step Rendering */}
          {step === 1 && renderStep1()}
          {step === 2 && renderStep2()}
          {step === 3 && renderStep3()}
          {step === 4 && renderStep4()}

          {/* Footer Link */}
          {step !== 4 && (
            <div className="login-links" style={{ justifyContent: 'center', marginTop: '1.5rem' }}>
              <RouterLink to="/login" className="login-link">
                {t.alreadyAccount} <b>{t.loginHere}</b>
              </RouterLink>
            </div>
          )}
          
        </div>
      </div>

      {/* --- CAMERA DIALOG --- */}
      {renderCameraDialog()}
    </div>
  );
}