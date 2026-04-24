// ============================================================================
// 1. IMPORTS & CONFIGURATION
// ============================================================================
import React, { useState, useEffect } from 'react';
import { 
  Box, Typography, Avatar, IconButton, Paper, CircularProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Button 
} from '@mui/material';
import { 
  Search, Notifications, EventNote, Assignment, History, 
  SupportAgent, Logout, Computer, Person, Menu as MenuIcon 
} from '@mui/icons-material';
import CancelIcon from '@mui/icons-material/Cancel';

import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

// API Endpoint configuration
const API_URL = 'http://localhost:8000';

// ============================================================================
// 2. MAIN COMPONENT
// ============================================================================
export default function Reserved() {
  // --- Contexts & Hooks ---
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();
  
  // ============================================================================
  // 3. STATE MANAGEMENT
  // ============================================================================
  /** @description ควบคุมการเปิด/ปิด Sidebar บนจอมือถือ */
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  
  /** @description เก็บข้อมูลการจองเฉพาะของ "วันนี้และอนาคต" */
  const [bookings, setBookings] = useState([]);
  
  /** @description สถานะการโหลดข้อมูล */
  const [loading, setLoading] = useState(true);

  /** @description ควบคุม Pop-up ยืนยันการยกเลิกการจอง */
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [bookingToCancel, setBookingToCancel] = useState(null);

  // ============================================================================
  // 4. LIFECYCLE & API CALLS
  // ============================================================================
  useEffect(() => {
    if (!currentUser) {
      navigate('/login');
      return;
    }
    fetchMyBookings();
  }, [currentUser, navigate]);

  /**
   * @function fetchMyBookings
   * @description ดึงข้อมูลการจองทั้งหมดของผู้ใช้ และกรองเอาเฉพาะรายการที่ยังไม่ผ่านพ้นไป
   */
  const fetchMyBookings = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/bookings/user/${currentUser.email}`);
      const allBookings = response.data.data;

      // 🌟 กรองเอาเฉพาะ "วันนี้และอนาคต" (ถ้าเป็นอดีตจะไปโชว์ใน History)
      const todayMidnight = new Date();
      todayMidnight.setHours(0, 0, 0, 0);

      const upcomingOnly = allBookings.filter(booking => {
        const bookingDate = new Date(booking.booking_date);
        bookingDate.setHours(0, 0, 0, 0);
        return bookingDate.getTime() >= todayMidnight.getTime();
      });

      setBookings(upcomingOnly);
    } catch (error) {
      console.error("[API Error] Failed to fetch bookings:", error);
    } finally {
      setLoading(false);
    }
  };

  /**
   * @function handleConfirmCancel
   * @description ยิง API ไปที่ Backend เพื่อลบ (ยกเลิก) การจองนั้นๆ
   */
  const handleConfirmCancel = async () => {
    if (!bookingToCancel) return;
    
    try {
      await axios.delete(`${API_URL}/bookings/${bookingToCancel}`, {
        params: { email: currentUser.email } 
      });
      // ปิด Pop-up และดึงข้อมูลตารางใหม่เพื่อรีเฟรชหน้าจอ
      setCancelDialogOpen(false);
      setBookingToCancel(null);
      fetchMyBookings();
    } catch (error) {
      alert("Failed to cancel booking.");
      console.error("[API Error]", error);
    }
  };

  // ============================================================================
  // 5. EVENT HANDLERS & UTILITIES
  // ============================================================================
  
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleOpenCancelDialog = (bookingId) => {
    setBookingToCancel(bookingId);
    setCancelDialogOpen(true);
  };

  const handleCloseCancelDialog = () => {
    setCancelDialogOpen(false);
    setBookingToCancel(null);
  };

  /**
   * @function renderStatusChip
   * @description คืนค่า Component Chip ป้ายสีสถานะ (Approved, Pending, Rejected)
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
          <div className="menu-item active" onClick={() => setIsSidebarOpen(false)}>
            <Assignment /> Reserved
          </div>
          <div className="menu-item" onClick={() => navigate('/history')}>
            <History /> History
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
              My Reservations
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 3 } }}>
            <IconButton><Notifications sx={{ color: '#111827' }} /></IconButton>
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
                border: '2px solid #3b82f6', 
                borderRadius: 4, 
                maxWidth: '900px',
                mx: 'auto', 
                bgcolor: 'white'
              }}
            >
              <Typography variant="h6" fontWeight="bold" color="#0f172a" sx={{ mb: 3 }}>
                Reserved Status
              </Typography>

              {bookings.length > 0 ? (
                <TableContainer>
                  <Table sx={{ minWidth: 600 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#0f172a' }}>#ID</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#0f172a' }}>Room</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#0f172a' }}>Date</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#0f172a' }}>Time</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', borderBottom: '1px solid #e2e8f0', color: '#0f172a' }}>Status</TableCell>
                        <TableCell sx={{ borderBottom: '1px solid #e2e8f0' }}></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {bookings.map((row) => (
                        <TableRow key={row.id} sx={{ '&:last-child td, &:last-child th': { border: 0 } }}>
                          <TableCell sx={{ color: '#64748b' }}>{row.id.toString().padStart(4, '0')}</TableCell>
                          <TableCell sx={{ color: '#475569' }}>{row.lab_code}</TableCell>
                          <TableCell sx={{ color: '#475569' }}>{formatDate(row.booking_date)}</TableCell>
                          <TableCell sx={{ color: '#475569' }}>{row.start_time} - {row.end_time}</TableCell>
                          <TableCell>
                            {renderStatusChip(row.status)}
                          </TableCell>
                          <TableCell align="right">
                            <IconButton 
                              size="small" 
                              onClick={() => handleOpenCancelDialog(row.id)} 
                              sx={{ 
                                color: '#ef4444', 
                                transition: '0.2s',
                                '&:hover': { color: '#dc2626', transform: 'scale(1.1)' } 
                              }}
                            >
                              <CancelIcon />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Box sx={{ py: 6, textAlign: 'center', bgcolor: '#f8fafc', borderRadius: 3 }}>
                  <Typography variant="body1" color="textSecondary">No upcoming reservations found.</Typography>
                </Box>
              )}
            </Paper>
          )}

        </div>
      </div>

      {/* ============================================================================
          7. DIALOGS & MODALS
          ============================================================================ */}
      <Dialog
        open={cancelDialogOpen}
        onClose={handleCloseCancelDialog}
        PaperProps={{ sx: { borderRadius: 3, p: 1, minWidth: '350px' } }}
      >
        <DialogTitle sx={{ fontWeight: 'bold', color: '#0f172a' }}>
          Cancel Reservation
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ color: '#475569' }}>
            Are you sure you want to cancel this booking? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button 
            onClick={handleCloseCancelDialog} 
            sx={{ color: '#64748b', fontWeight: 'bold', textTransform: 'none' }}
          >
            Keep it
          </Button>
          <Button 
            onClick={handleConfirmCancel} 
            variant="contained" 
            sx={{ 
              bgcolor: '#ef4444', 
              color: 'white', 
              fontWeight: 'bold', 
              textTransform: 'none',
              boxShadow: 'none',
              '&:hover': { bgcolor: '#dc2626', boxShadow: 'none' } 
            }}
          >
            Yes, Cancel
          </Button>
        </DialogActions>
      </Dialog>

    </div>
  );
}