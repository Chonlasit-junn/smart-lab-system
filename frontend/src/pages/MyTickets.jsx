import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

const STATUS_LABELS = {
  open: { label: 'รอดำเนินการ', color: 'warning' },
  in_progress: { label: 'กำลังดำเนินการ', color: 'info' },
  closed: { label: 'ดำเนินการเสร็จสิ้น', color: 'success' },
};

export default function MyTickets() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    document.title = 'คำร้องของฉัน | Smart Lab';

    const fetchMyTickets = async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setError('กรุณาเข้าสู่ระบบก่อนดูคำร้อง');
        setLoading(false);
        return;
      }

      try {
        const response = await axios.get(`${API_URL}/tickets/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setTickets(response.data?.data || []);
      } catch (requestError) {
        setError(
          requestError.response?.data?.detail ||
            'ไม่สามารถโหลดคำร้องของคุณได้',
        );
      } finally {
        setLoading(false);
      }
    };

    fetchMyTickets();
  }, []);

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, bgcolor: '#fcfdfe', minHeight: '100vh' }}>
      <Typography variant="h4" fontWeight="800" color="#1e293b" sx={{ mb: 3 }}>
        คำร้องของฉัน
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      <Paper
        elevation={0}
        sx={{ p: { xs: 1, md: 3 }, borderRadius: 4, border: '1px solid #e2e8f0' }}
      >
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        ) : tickets.length === 0 ? (
          <Typography align="center" sx={{ py: 6, color: '#94a3b8' }}>
            คุณยังไม่เคยส่งคำร้อง
          </Typography>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow sx={{ bgcolor: '#f8fafc' }}>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>หัวข้อ</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>รายละเอียด</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>วันที่ส่ง</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>สถานะ</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.map((ticket) => {
                  const status = STATUS_LABELS[ticket.status] || {
                    label: ticket.status || 'ไม่ทราบสถานะ',
                    color: 'default',
                  };
                  return (
                    <TableRow key={ticket.id} hover>
                      <TableCell sx={{ fontWeight: '700', color: '#334155' }}>
                        {ticket.subject}
                      </TableCell>
                      <TableCell sx={{ color: '#475569', whiteSpace: 'pre-wrap' }}>
                        {ticket.message}
                      </TableCell>
                      <TableCell sx={{ color: '#475569' }}>
                        {ticket.created_at
                          ? new Date(ticket.created_at).toLocaleString('th-TH')
                          : '-'}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={status.label}
                          color={status.color}
                          size="small"
                          sx={{ fontWeight: 'bold' }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
}
