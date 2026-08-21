import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, CircularProgress, Button, Chip, IconButton
} from '@mui/material';
import { ArrowBack, CheckCircle } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function TicketManager() {
  const navigate = useNavigate();
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = 'Ticket Manager | Smart Lab Admin';
    fetchTickets();
  }, []);

  // ฟังก์ชันดึงข้อมูล Ticket ทั้งหมดจาก Backend
  const fetchTickets = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/tickets`);
      setTickets(response.data?.data || []);
    } catch (error) {
      console.error('[TicketManager] Failed to fetch tickets:', error);
    } finally {
      setLoading(false);
    }
  };

  // ฟังก์ชันอัปเดตสถานะ Ticket เป็น Closed
  const handleCloseTicket = async (ticketId) => {
    try {
      await axios.patch(`${API_URL}/admin/tickets/${ticketId}`, { status: 'closed' });
      // อัปเดต State ในหน้าจอให้เปลี่ยนเป็น closed ทันทีโดยไม่ต้องรีเฟรชหน้า
      setTickets(tickets.map(t => t.id === ticketId ? { ...t, status: 'closed' } : t));
    } catch (error) {
      console.error('Failed to close ticket:', error);
      alert('เกิดข้อผิดพลาดในการอัปเดตสถานะ');
    }
  };

  return (
    <Box sx={{ p: 4, bgcolor: '#fcfdfe', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
      {/* ส่วนหัว */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 4, gap: 2 }}>
        <IconButton onClick={() => navigate('/admin')} sx={{ bgcolor: '#f1f5f9' }}>
          <ArrowBack />
        </IconButton>
        <Typography variant="h4" fontWeight="800" color="#1e293b">
          Support Tickets
        </Typography>
      </Box>

      {/* ตารางแสดงข้อมูล */}
      <Paper elevation={0} sx={{ p: 4, borderRadius: 4, border: '1px solid #e2e8f0' }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow sx={{ bgcolor: '#f8fafc' }}>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>ID</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>User ID</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>หัวข้อ (Subject)</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>รายละเอียด (Message)</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>สถานะ</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b', textAlign: 'center' }}>จัดการ</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.length > 0 ? (
                  tickets.map((ticket) => (
                    <TableRow key={ticket.id} sx={{ '& td': { borderBottom: '1px solid #f1f5f9' } }}>
                      <TableCell>{ticket.id}</TableCell>
                      <TableCell>{ticket.user_id}</TableCell>
                      <TableCell sx={{ fontWeight: '700', color: '#334155' }}>{ticket.subject}</TableCell>
                      <TableCell sx={{ color: '#475569' }}>{ticket.message}</TableCell>
                      <TableCell>
                        <Chip
                          label={ticket.status === 'open' ? 'รอแก้ไข' : 'ปิดแล้ว'}
                          color={ticket.status === 'open' ? 'warning' : 'success'}
                          size="small"
                          sx={{ fontWeight: 'bold' }}
                        />
                      </TableCell>
                      <TableCell align="center">
                        {ticket.status === 'open' ? (
                          <Button
                            variant="contained"
                            color="success"
                            size="small"
                            startIcon={<CheckCircle />}
                            onClick={() => handleCloseTicket(ticket.id)}
                            sx={{ textTransform: 'none', borderRadius: 2, boxShadow: 'none' }}
                          >
                            Mark as Closed
                          </Button>
                        ) : (
                          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 'bold' }}>
                            Resolved
                          </Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 4, color: '#94a3b8' }}>
                      ไม่มีคำร้องขอความช่วยเหลือในขณะนี้
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
}