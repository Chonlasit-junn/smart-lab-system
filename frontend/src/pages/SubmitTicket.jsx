import React, { useState } from 'react';
import { Box, Typography, Paper, TextField, Button, Alert } from '@mui/material';
import { Send } from '@mui/icons-material';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

export default function SubmitTicket() {
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState(null); // 'success' | 'error' | null
  const [loading, setLoading] = useState(false);

  // token เก็บไว้ตอน login — ปรับ key ตามระบบ auth จริงของคุณ
  const token = localStorage.getItem('token');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!subject.trim() || !message.trim()) return;

    try {
      setLoading(true);
      // ไม่ส่ง user_id แล้ว — backend ดึง user จาก token เอง (get_current_user)
      await axios.post(
        `${API_URL}/tickets`,
        { subject, message },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setStatus('success');
      setSubject('');
      setMessage('');
    } catch (error) {
      console.error('[SubmitTicket] failed to submit:', error);
      setStatus('error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ p: 4, maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h5" fontWeight="800" sx={{ mb: 3 }}>
        แจ้งปัญหา / ส่งคำร้อง
      </Typography>

      <Paper elevation={0} sx={{ p: 4, borderRadius: 4, border: '1px solid #e2e8f0' }}>
        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {status === 'success' && <Alert severity="success">ส่งคำร้องเรียบร้อยแล้ว</Alert>}
          {status === 'error' && <Alert severity="error">เกิดข้อผิดพลาด ลองใหม่อีกครั้ง</Alert>}

          <TextField
            label="หัวข้อ"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            required
            fullWidth
          />
          <TextField
            label="รายละเอียด"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            required
            multiline
            rows={4}
            fullWidth
          />
          <Button
            type="submit"
            variant="contained"
            startIcon={<Send />}
            disabled={loading}
            sx={{ alignSelf: 'flex-start', textTransform: 'none', borderRadius: 2 }}
          >
            {loading ? 'กำลังส่ง...' : 'ส่งคำร้อง'}
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}