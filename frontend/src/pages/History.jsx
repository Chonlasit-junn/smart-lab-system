// ============================================================================
// 1. IMPORTS & CONFIGURATION
// ============================================================================
import React, { useState, useEffect } from 'react';
import { 
  Box, Typography, Avatar, IconButton, Paper, CircularProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip 
} from '@mui/material';
import { 
  Search, Notifications, EventNote, Assignment, History as HistoryIcon, 
  SupportAgent, Logout, Computer, Person, Menu as MenuIcon 
} from '@mui/icons-material';

import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

// API Endpoint configuration
const API_URL = 'http://localhost:8000';

// ============================================================================
// 2. MAIN COMPONENT
// ============================================================================
export default function History() {
  // --- Contexts & Hooks ---
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();
  
  // ============================================================================
  // 3. STATE MANAGEMENT
  // ============================================================================
  /** @description ควบคุมการเปิด/ปิด Sidebar บนจอมือถือ */
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  
  /** @description เก็บรายการประวัติการจองที่ผ่านมาแล้ว (หลังจากกรองข้อมูลแล้ว) */
  const [pastBookings, setPastBookings] = useState([]);
  
  /** @description สถานะการโหลดข้อมูลจาก API */
  const [loading, setLoading] = useState(true);

  // ============================================================================
  // 4. LIFECYCLE & API CALLS
  // ============================================================================
  useEffect(() => {
    // ป้องกันไม่ให้ผู้ใช้ที่ยังไม่ล็อกอินเข้ามาหน้านี้
    if (!currentUser) {
      navigate('/login');
      return;
    }
    fetchMyHistory();
  }, [currentUser, navigate]);

  /**
   * @function fetchMyHistory
   * @description ดึงประวัติการจองทั้งหมดของผู้ใช้ และกรองเอาเฉพาะรายการที่เป็น "อดีต"
   */
  const fetchMyHistory = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/bookings/user/${currentUser.email}`);
      const allBookings = response.data.data;

      // เซ็ตเวลาเปรียบเทียบเป็น 00:00:00 ของวันนี้
      const todayMidnight = new Date();
      todayMidnight.setHours(0, 0, 0, 0);

      // กรองเอาเฉพาะรายการที่วันที่จอง น้อยกว่า วันนี้ (ผ่านไปแล้ว)
      const historyOnly = allBookings.filter(booking => {
        const bookingDate = new Date(booking.booking_date);
        bookingDate.setHours(0, 0, 0, 0);
        return bookingDate.getTime() < todayMidnight.getTime();
      });

      setPastBookings(historyOnly);
    } catch (error) {
      console.error("[API Error] Failed to fetch history:", error);
    } finally {
      setLoading(false);
    }
  };

  // ============================================================================
  // 5. EVENT HANDLERS & UTILITIES
  // ============================================================================
  
  /**
   * @function handleLogout
   * @description จัดการการออกจากระบบและพาผู้ใช้กลับไปหน้า Login
   */
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  /**
   * @function renderStatusChip
   * @description คืนค่า Component Chip (ป้ายสถานะ) ที่มีสีสอดคล้องกับสถานะ
   * @param {string} status - สถานะของการจอง (เช่น approved, pending, rejected)
   */
  const renderStatusChip = (status) => {
    switch(status.toLowerCase()) {
      case 'approved': 
        return <Chip label="Approved" sx={{ bgcolor: '#a7f3d0', color: '#166534', fontWeight: 'bold', borderRadius: 2 }} size="small" />;
      case 'pending': 
        return <Chip label="Waiting" sx={{ bgcolor: '#e5e7eb', color: '#475569', fontWeight: 'bold', borderRadius: 2 }} size="small" />;
      case 'rejected': 
      case 'full':
        return <Chip label={status.charAt(0).toUpperCase() + status.slice(1)} sx={{ bgcolor: '#fecaca', color: '#b91c1c', fontWeight: 'bold', borderRadius: 2 }} size="small" />;
      default: 
        return <Chip label={status} size="small" />;
    }
  };

  /**
   * @function formatDate
   * @description แปลงรูปแบบวันที่ให้อ่านง่าย เช่น 10 Mar 2026
   * @param {string} dateString - วันที่ในรูปแบบ String จาก Database
   */
  const formatDate = (dateString) => {
    const options = { day: 'numeric', month: 'short', year: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-GB', options);
  };

  // ============================================================================
  // 6. RENDER UI
  // ============================================================================
  return (
    <div className="app-layout">
      {/* --- OVERLAY (Mobile) --- */}
      {isSidebarOpen && <div className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)}></div>}

      {/* --- SIDEBAR --- */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-logo">
          <Computer sx={{ fontSize: 40, color: '#0052cc' }} />
          <div>
            <Typography variant="h6" fontWeight="bold" lineHeight={1.2}>Smart Lab</Typography>
            <Typography variant="caption" color="textSecondary">Reserve Lab to use</Typography>
          </div>
        </div>

        <div className="sidebar-menu">
          <div className="menu-item" onClick={() => navigate('/')}>
            <EventNote /> Lab Reserve
          </div>
          <div className="menu-item" onClick={() => navigate('/reserved')}>
            <Assignment /> Reserved
          </div>
          <div className="menu-item active" onClick={() => setIsSidebarOpen(false)}>
            <HistoryIcon /> History
          </div>
        </div>

        <div className="sidebar-menu" style={{ flex: 'none', paddingBottom: '24px' }}>
          <div className="menu-item"><SupportAgent /> Support</div>
          <div className="menu-item" onClick={handleLogout}><Logout /> Log Out</div>
        </div>
      </div>

      {/* --- MAIN AREA --- */}
      <div className="main-area">
        
        {/* --- HEADER --- */}
        <div className="top-header">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <IconButton sx={{ display: { xs: 'block', md: 'none' }, color: '#111827' }} onClick={() => setIsSidebarOpen(true)}>
              <MenuIcon />
            </IconButton>
            <Typography variant="h5" fontWeight="bold" color="#111827" sx={{ display: { xs: 'none', sm: 'block' } }}>
              Booking History
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 3 } }}>
            <IconButton><Notifications sx={{ color: '#111827' }} /></IconButton>
            {/* Profile Section */}
            {currentUser && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '1px solid #e2e8f0', pl: { xs: 1, sm: 3 } }}>
                <Box className="profile-text-container" sx={{ textAlign: 'right' }}>
                  <Typography variant="subtitle2" fontWeight="bold" lineHeight={1.2}>{currentUser.name}</Typography>
                  <Typography variant="caption" color="textSecondary">{currentUser.role}</Typography>
                </Box>
                <Avatar sx={{ bgcolor: '#111827', width: 36, height: 36 }}>{currentUser.initial}</Avatar>
              </Box>
            )}
          </Box>
        </div>

        {/* --- CONTENT AREA --- */}
        <div className="content-area">
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Paper 
              elevation={0} 
              sx={{ 
                p: { xs: 2, sm: 4 }, 
                border: '2px solid #cbd5e1', 
                borderRadius: 4, 
                maxWidth: '900px',
                mx: 'auto',
                bgcolor: 'white'
              }}
            >
              <Typography variant="h6" fontWeight="bold" color="#64748b" sx={{ mb: 3 }}>
                Past Reservations
              </Typography>

              {pastBookings.length > 0 ? (
                <TableContainer>
                  <Table sx={{ minWidth: 600 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>#ID</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>Room</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>Date</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>Time</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>Status</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {pastBookings.map((row) => (
                        <TableRow key={row.id} sx={{ '&:last-child td, &:last-child th': { border: 0 }, opacity: 0.8 }}>
                          <TableCell sx={{ color: '#94a3b8' }}>{row.id.toString().padStart(4, '0')}</TableCell>
                          <TableCell sx={{ color: '#64748b' }}>{row.lab_code}</TableCell>
                          <TableCell sx={{ color: '#64748b' }}>{formatDate(row.booking_date)}</TableCell>
                          <TableCell sx={{ color: '#64748b' }}>{row.start_time} - {row.end_time}</TableCell>
                          <TableCell>
                            {renderStatusChip(row.status)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Box sx={{ py: 6, textAlign: 'center', bgcolor: '#f8fafc', borderRadius: 3 }}>
                  <Typography variant="body1" color="textSecondary">No past history found.</Typography>
                </Box>
              )}
            </Paper>
          )}
        </div>
      </div>
    </div>
  );
}