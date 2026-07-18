import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Avatar, IconButton, Paper, CircularProgress,
  Divider, Chip, Grid
} from '@mui/material';
import {
  Notifications, EventNote, Assignment, History,
  SupportAgent, Logout, Computer, Menu as MenuIcon,
  Person, Email, Phone, School, Badge, CalendarMonth
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// maps faculty id → display name (ใช้ EN สำหรับ profile)
const FACULTY_NAMES = {
  business:      'School of Business Administration',
  communication: 'School of Communication Arts',
  engineering:   'School of Engineering',
  it:            'School of Information Technology and Innovation',
  architecture:  'School of Architecture',
  humanities:    'School of Humanities',
  finearts:      'School of Fine and Applied Arts',
  law:           'School of Law',
  accounting:    'School of Accounting',
  economics:     'School of Economics',
};

export default function Profile() {
  const navigate  = useNavigate();
  const { currentUser, logout } = useAuth();

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [profile, setProfile]             = useState(null);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState('');

  useEffect(() => {
    if (!currentUser) { navigate('/'); return; }
    fetchProfile();
  }, [currentUser, navigate]);

  const fetchProfile = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('access_token');
      const headers = { Authorization: `Bearer ${token}` };

      // step 1: ดึง profile ก่อน — ได้ user id มา
      const profileRes = await axios.get(`${API_URL}/users/me`, { headers });
      const profileData = profileRes.data;

      // step 2: ดึง points โดยใช้ id จาก step 1
      const pointsRes = await axios.get(`${API_URL}/users/${profileData.id}/points`, { headers });

      setProfile({ ...profileData, ...pointsRes.data });
    } catch (err) {
      setError('ไม่สามารถโหลดข้อมูลโปรไฟล์ได้');
      console.error('[Profile] fetch failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => { logout(); navigate('/'); };

  const formatDate = (dateString) =>
    dateString
      ? new Date(dateString).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
      : '—';

  const roleColor = profile?.role === 'student' ? '#3b82f6' : profile?.role === 'admin' ? '#8b5cf6' : '#f59e0b';
  const roleLabel = profile?.role === 'student' ? 'นักศึกษา' : profile?.role === 'admin' ? 'ผู้ดูแลระบบ' : 'บุคคลทั่วไป';

  return (
    <div className="app-layout">
      {isSidebarOpen && <div className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)} />}

      {/* sidebar */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-logo">
          <Computer sx={{ fontSize: 40, color: '#1877f2' }} />
          <div>
            <Typography variant="h6" fontWeight="bold" lineHeight={1.2}>Smart Lab</Typography>
            <Typography variant="caption" color="textSecondary">Reserve Lab to use</Typography>
          </div>
        </div>
        <div className="sidebar-menu">
          <div className="menu-item" onClick={() => navigate('/booking')}><EventNote /> Lab Reserve</div>
          <div className="menu-item" onClick={() => navigate('/reserved')}><Assignment /> Reserved</div>
          <div className="menu-item" onClick={() => navigate('/history')}><History /> History</div>
        </div>
        <div className="sidebar-menu" style={{ flex: 'none', paddingBottom: '24px' }}>
          <div className="menu-item"><SupportAgent /> Support</div>
          <div className="menu-item" onClick={handleLogout}><Logout /> Log Out</div>
        </div>
      </div>

      <div className="main-area">
        {/* header */}
        <div className="top-header">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <IconButton sx={{ display: { xs: 'block', md: 'none' }, color: '#111827' }} onClick={() => setIsSidebarOpen(true)}>
              <MenuIcon />
            </IconButton>
            <Typography variant="h5" fontWeight="bold" color="#111827" sx={{ display: { xs: 'none', sm: 'block' } }}>
              My Profile
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 3 } }}>
            <IconButton><Notifications sx={{ color: '#111827' }} /></IconButton>
            {currentUser && (
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '1px solid #e2e8f0', pl: { xs: 1, sm: 3 }, cursor: 'pointer' }}
                onClick={() => navigate('/profile')}
              >
                <Box className="profile-text-container" sx={{ textAlign: 'right' }}>
                  <Typography variant="subtitle2" fontWeight="bold" lineHeight={1.2}>{currentUser.name}</Typography>
                  <Typography variant="caption" color="textSecondary">{currentUser.role}</Typography>
                </Box>
                <Avatar sx={{ bgcolor: '#111827', width: 36, height: 36 }}>{currentUser.initial}</Avatar>
              </Box>
            )}
          </Box>
        </div>

        {/* content */}
        <div className="content-area">
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}><CircularProgress /></Box>
          ) : error ? (
            <Box sx={{ textAlign: 'center', mt: 10, color: '#ef4444' }}>
              <Typography>{error}</Typography>
            </Box>
          ) : profile && (
            <Box sx={{ maxWidth: '860px', mx: 'auto' }}>
              <Grid container spacing={3}>

                {/* left: avatar + name card */}
                <Grid item xs={12} md={4}>
                  <Paper elevation={0} sx={{ p: 4, border: '1px solid #e2e8f0', borderRadius: 4, bgcolor: 'white', textAlign: 'center' }}>

                    {/* profile picture */}
                    <Box sx={{ position: 'relative', display: 'inline-block', mb: 2 }}>
                      {profile.profile_pic ? (
                        <Avatar
                          src={`${API_URL}/${profile.profile_pic}`}
                          sx={{ width: 110, height: 110, border: '4px solid #e2e8f0', mx: 'auto' }}
                        />
                      ) : (
                        <Avatar sx={{ width: 110, height: 110, bgcolor: '#1e293b', fontSize: 42, mx: 'auto' }}>
                          {profile.first_name?.charAt(0).toUpperCase()}
                        </Avatar>
                      )}
                    </Box>

                    <Typography variant="h6" fontWeight="bold" color="#0f172a">
                      {profile.first_name} {profile.last_name}
                    </Typography>

                    <Chip
                      label={roleLabel}
                      size="small"
                      sx={{ mt: 1, mb: 2, bgcolor: `${roleColor}18`, color: roleColor, fontWeight: 'bold' }}
                    />

                    <Divider sx={{ mb: 2 }} />

                    {/* joined date */}
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, color: '#94a3b8' }}>
                      <CalendarMonth fontSize="small" />
                      <Typography variant="caption">เข้าร่วมเมื่อ {formatDate(profile.created_at)}</Typography>
                    </Box>
                  </Paper>

                  {/* stats card */}
                  <Paper elevation={0} sx={{ mt: 3, p: 3, border: '1px solid #e2e8f0', borderRadius: 4, bgcolor: 'white' }}>
                    <Typography variant="subtitle2" fontWeight="bold" color="#64748b" sx={{ mb: 2 }}>สถิติการใช้งาน</Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold" color="#1e293b">{profile.stats?.total_bookings ?? 0}</Typography>
                        <Typography variant="caption" color="#94a3b8">การจองทั้งหมด</Typography>
                      </Box>
                      {/* placeholder สำหรับ point system */}
                      <Divider orientation="vertical" flexItem />
                      <Box>
                        <Typography variant="h4" fontWeight="bold" color={
                          profile.points >= 80 ? '#10b981' :
                          profile.points >= 60 ? '#f59e0b' :
                          profile.points !== undefined ? '#ef4444' : '#94a3b8'
                        }>
                          {profile.points ?? '—'}
                        </Typography>
                        <Typography variant="caption" color="#94a3b8">คะแนน</Typography>
                      </Box>
                    </Box>
                  </Paper>
                </Grid>

                {/* right: info details */}
                <Grid item xs={12} md={8}>
                  <Paper elevation={0} sx={{ p: 4, border: '1px solid #e2e8f0', borderRadius: 4, bgcolor: 'white' }}>
                    <Typography variant="subtitle1" fontWeight="bold" color="#0f172a" sx={{ mb: 3 }}>ข้อมูลส่วนตัว</Typography>

                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>

                      {/* email */}
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Avatar sx={{ bgcolor: '#eff6ff', width: 40, height: 40 }}>
                          <Email sx={{ color: '#3b82f6', fontSize: 20 }} />
                        </Avatar>
                        <Box>
                          <Typography variant="caption" color="#94a3b8" fontWeight="bold">อีเมล</Typography>
                          <Typography variant="body2" fontWeight="600" color="#1e293b">{profile.email}</Typography>
                        </Box>
                      </Box>

                      {/* student fields */}
                      {profile.role === 'student' && (
                        <>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                            <Avatar sx={{ bgcolor: '#eff6ff', width: 40, height: 40 }}>
                              <Badge sx={{ color: '#3b82f6', fontSize: 20 }} />
                            </Avatar>
                            <Box>
                              <Typography variant="caption" color="#94a3b8" fontWeight="bold">รหัสนักศึกษา</Typography>
                              <Typography variant="body2" fontWeight="600" color="#1e293b">{profile.student_id || '—'}</Typography>
                            </Box>
                          </Box>

                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                            <Avatar sx={{ bgcolor: '#eff6ff', width: 40, height: 40 }}>
                              <School sx={{ color: '#3b82f6', fontSize: 20 }} />
                            </Avatar>
                            <Box>
                              <Typography variant="caption" color="#94a3b8" fontWeight="bold">คณะ / สาขา</Typography>
                              <Typography variant="body2" fontWeight="600" color="#1e293b">
                                {FACULTY_NAMES[profile.faculty] || profile.faculty || '—'}
                              </Typography>
                              <Typography variant="caption" color="#64748b">{profile.department || ''}</Typography>
                            </Box>
                          </Box>
                        </>
                      )}

                      {/* guest fields */}
                      {profile.role === 'guest' && (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          <Avatar sx={{ bgcolor: '#fff7ed', width: 40, height: 40 }}>
                            <Phone sx={{ color: '#f59e0b', fontSize: 20 }} />
                          </Avatar>
                          <Box>
                            <Typography variant="caption" color="#94a3b8" fontWeight="bold">เบอร์โทรศัพท์</Typography>
                            <Typography variant="body2" fontWeight="600" color="#1e293b">{profile.phone || '—'}</Typography>
                          </Box>
                        </Box>
                      )}

                    </Box>

                    <Divider sx={{ my: 3 }} />

                    {/* point system */}
                      <Box sx={{ p: 3, bgcolor: '#f8fafc', borderRadius: 3, border: '1px solid #e2e8f0' }}>
                        <Typography variant="subtitle2" fontWeight="bold" color="#0f172a" sx={{ mb: 2 }}>
                          ⭐ คะแนนของฉัน
                        </Typography>

                        {profile.points !== undefined ? (
                          <>
                            {/* score bar */}
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="body2" color="#64748b">คะแนนปัจจุบัน</Typography>
                              <Typography variant="body2" fontWeight="bold" color={
                                profile.points >= 80 ? '#10b981' :
                                profile.points >= 60 ? '#f59e0b' : '#ef4444'
                              }>
                                {profile.points} / 100
                              </Typography>
                            </Box>

                            <Box sx={{ width: '100%', height: 10, bgcolor: '#e2e8f0', borderRadius: 5, overflow: 'hidden', mb: 1.5 }}>
                              <Box sx={{
                                width: `${profile.points}%`, height: '100%', borderRadius: 5,
                                bgcolor: profile.points >= 80 ? '#10b981' : profile.points >= 60 ? '#f59e0b' : '#ef4444',
                                transition: 'width 0.6s ease',
                              }} />
                            </Box>

                            {/* ban status */}
                            {profile.is_banned ? (
                              <Chip
                                label={`ถูกระงับถึง ${new Date(profile.ban_until).toLocaleDateString('th-TH')}`}
                                size="small"
                                sx={{ bgcolor: '#fef2f2', color: '#ef4444', fontWeight: 'bold' }}
                              />
                            ) : (
                              <Chip
                                label="สถานะปกติ"
                                size="small"
                                sx={{ bgcolor: '#f0fdf4', color: '#16a34a', fontWeight: 'bold' }}
                              />
                            )}
                          </>
                        ) : (
                          <Typography variant="body2" color="#94a3b8">ไม่พบข้อมูลคะแนน</Typography>
                        )}
                      </Box>
                  </Paper>
                </Grid>

              </Grid>
            </Box>
          )}
        </div>
      </div>
    </div>
  );
}