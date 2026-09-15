import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Paper, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, CircularProgress, Chip
} from '@mui/material';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

export default function MyTickets() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);

  // ต้องตรงกับ key ที่ auth-context.jsx ใช้ตอน login (localStorage.setItem('access_token', token))
  const token = localStorage.getItem('access_token');

  useEffect(() => {
    document.title = 'คำร้องของฉัน';
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

  return (
    <Box sx={{ p: 4 }}>
      <Typography variant="h5" fontWeight="800" sx={{ mb: 3 }}>
        คำร้องของฉัน
      </Typography>

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
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>หัวข้อ</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>รายละเอียด</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>วันที่ส่ง</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', color: '#64748b' }}>สถานะ</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.length > 0 ? (
                  tickets.map((t) => (
                    <TableRow key={t.id} sx={{ '& td': { borderBottom: '1px solid #f1f5f9' } }}>
                      <TableCell sx={{ fontWeight: '700', color: '#334155' }}>{t.subject}</TableCell>
                      <TableCell sx={{ color: '#475569' }}>{t.message}</TableCell>
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
    </Box>
  );
}