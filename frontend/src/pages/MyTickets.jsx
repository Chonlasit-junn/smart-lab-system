import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Avatar, IconButton, Paper, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, CircularProgress, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Divider
} from '@mui/material';
import {
  Notifications, EventNote, Assignment, History,
  SupportAgent, Logout, Computer, ConfirmationNumber, Close,
  Menu as MenuIconOutlined
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/auth-context';
import SupportModal from './SupportModal';

const API_URL = import.meta.env.VITE_API_URL;

export default function MyTickets() {
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTicket, setSelectedTicket] = useState(null); // ticket ที่กำลังดูรายละเอียดใน popup

  // ต้องตรงกับ key ที่ auth-context.jsx ใช้ตอน login (localStorage.setItem('access_token', token))
  const token = localStorage.getItem('access_token');

  useEffect(() => {
    document.title = 'คำร้องของฉัน | Smart Lab';
    fetchMyTickets();
  }, []);

  const fetchMyTickets = async () => {
    try {
      setLoading(true);
      // ใช้ /tickets/me — backend ดึง user จาก token เอง ไม่ต้องส่ง user_id มาเลือกเอง
      const res = await axios.get(`${API_URL}/tickets/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTickets(res.data?.data || []);
    } catch (error) {
      console.error('[MyTickets] failed to fetch:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const handleRowClick = (ticket) => setSelectedTicket(ticket);
  const handleCloseDialog = () => setSelectedTicket(null);

  return (
    <div className="app-layout">
      {isSidebarOpen && <div className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)}></div>}

      {/* SIDEBAR */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-logo">
          <Computer sx={{ fontSize: 40, color: '#1877f2' }} />
          <div>
            <Typography variant="h6" fontWeight="bold" lineHeight={1.2}>Smart Lab</Typography>
            <Typography variant="caption" color="textSecondary">Reserve Lab to use</Typography>
          </div>
        </div>

        <div className="sidebar-menu">
          <div className="menu-item" onClick={() => navigate('/booking')}>
            <EventNote /> Lab Reserve
          </div>
          <div className="menu-item" onClick={() => navigate('/reserved')}>
            <Assignment /> Reserved
          </div>
          <div className="menu-item" onClick={() => navigate('/history')}>
            <History /> History
          </div>
        </div>

        <div className="sidebar-menu" style={{ flex: 'none', paddingBottom: '24px' }}>
          <div className="menu-item" onClick={() => setIsSupportOpen(true)}>
            <SupportAgent /> Support
          </div>
          <div className="menu-item active" onClick={() => setIsSidebarOpen(false)}>
            <ConfirmationNumber /> My Tickets
          </div>
          <div className="menu-item" onClick={handleLogout}><Logout /> Log Out</div>
        </div>
      </div>

      {/* MAIN AREA */}
      <div className="main-area">
        <div className="top-header">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <IconButton
              sx={{ display: { xs: 'block', md: 'none' }, color: '#111827' }}
              onClick={() => setIsSidebarOpen(true)}
            >
              <MenuIconOutlined />
            </IconButton>
            <Typography variant="h5" fontWeight="bold" color="#111827" sx={{ display: { xs: 'none', sm: 'block' } }}>
              My Tickets
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 3 } }}>
            <IconButton><Notifications sx={{ color: '#111827' }} /></IconButton>
            {currentUser && (
              <Box
                onClick={() => navigate('/profile')}
                sx={{
                  display: 'flex', alignItems: 'center', gap: 1.5,
                  borderLeft: '1px solid #e2e8f0', pl: { xs: 1, sm: 3 },
                  cursor: 'pointer', transition: '0.2s', '&:hover': { opacity: 0.75 },
                }}
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

        <div className="content-area">
          <Paper elevation={0} sx={{ p: { xs: 2, sm: 4 }, border: '1px solid #e2e8f0', borderRadius: 4, maxWidth: '900px', mx: 'auto', bgcolor: 'white' }}>
            <Typography variant="h6" fontWeight="bold" color="#0f172a" sx={{ mb: 3 }}>
              รายการคำร้องที่ส่งไป
            </Typography>

            {loading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
              </Box>
            ) : (
              <TableContainer>
                <Table sx={{ minWidth: 600 }}>
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#f8fafc' }}>
                      <TableCell sx={{ fontWeight: 'bold', color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>หัวข้อ</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>รายละเอียด</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>วันที่ส่ง</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>สถานะ</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {tickets.length > 0 ? (
                      tickets.map((t) => (
                        <TableRow
                          key={t.id}
                          onClick={() => handleRowClick(t)}
                          sx={{
                            cursor: 'pointer',
                            '& td': { borderBottom: '1px solid #f1f5f9' },
                            '&:hover': { bgcolor: '#f8fafc' },
                          }}
                        >
                          <TableCell sx={{ fontWeight: '700', color: '#334155' }}>{t.subject}</TableCell>
                          <TableCell
                            sx={{
                              color: '#475569',
                              maxWidth: 280,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {t.message}
                          </TableCell>
                          <TableCell sx={{ color: '#475569' }}>
                            {t.created_at ? new Date(t.created_at).toLocaleString('th-TH') : '-'}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={t.status === 'open' ? 'รอดำเนินการ' : 'ดำเนินการเสร็จสิ้น'}
                              color={t.status === 'open' ? 'warning' : 'success'}
                              size="small"
                              sx={{ fontWeight: 'bold' }}
                            />
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={4} align="center" sx={{ py: 4, color: '#94a3b8' }}>
                          คุณยังไม่เคยส่งคำร้อง
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        </div>
      </div>

      {/* Popup แสดงรายละเอียด ticket ที่เลือก */}
      <Dialog open={!!selectedTicket} onClose={handleCloseDialog} fullWidth maxWidth="sm">
        {selectedTicket && (
          <>
            <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="h6" fontWeight="800">รายละเอียดคำร้อง</Typography>
              <IconButton onClick={handleCloseDialog}><Close /></IconButton>
            </DialogTitle>
            <DialogContent dividers>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Box>
                  <Typography variant="caption" color="#94a3b8" fontWeight="bold">หัวข้อ</Typography>
                  <Typography variant="body1" fontWeight="700" color="#334155">{selectedTicket.subject}</Typography>
                </Box>

                <Divider />

                <Box>
                  <Typography variant="caption" color="#94a3b8" fontWeight="bold">รายละเอียด</Typography>
                  <Typography variant="body2" color="#475569" sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>
                    {selectedTicket.message}
                  </Typography>
                </Box>

                <Divider />

                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography variant="caption" color="#94a3b8" fontWeight="bold">วันที่ส่ง</Typography>
                    <Typography variant="body2" color="#475569">
                      {selectedTicket.created_at ? new Date(selectedTicket.created_at).toLocaleString('th-TH') : '-'}
                    </Typography>
                  </Box>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="caption" color="#94a3b8" fontWeight="bold" sx={{ display: 'block' }}>สถานะ</Typography>
                    <Chip
                      label={selectedTicket.status === 'open' ? 'รอดำเนินการ' : 'ดำเนินการเสร็จสิ้น'}
                      color={selectedTicket.status === 'open' ? 'warning' : 'success'}
                      size="small"
                      sx={{ fontWeight: 'bold', mt: 0.5 }}
                    />
                  </Box>
                </Box>
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={handleCloseDialog} variant="contained" sx={{ textTransform: 'none', borderRadius: 2 }}>
                ปิด
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      <SupportModal
        open={isSupportOpen}
        onClose={() => setIsSupportOpen(false)}
        user={currentUser}
      />
    </div>
  );
}