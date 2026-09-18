import React, { useState } from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, IconButton } from '@mui/material';
import { SupportAgent, Close } from '@mui/icons-material';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

export default function SupportModal({ open, onClose, user }) {
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!subject || !message) return alert('กรุณากรอกข้อมูลให้ครบถ้วน');

    // ต้องตรงกับ key ที่ auth-context.jsx ใช้ตอน login (localStorage.setItem('access_token', token))
    const token = localStorage.getItem('access_token');

    try {
      setLoading(true);
      // ไม่ส่ง user_id แล้ว — backend ดึง user จาก token เอง (get_current_user)
      await axios.post(
        `${API_URL}/tickets`,
        { subject, message },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('ส่ง Ticket ให้แอดมินเรียบร้อยแล้ว');
      setSubject('');
      setMessage('');
      onClose(); // ปิด Modal
    } catch (error) {
      console.log("Data sent:", { subject, message });

      // เอา Error จาก Backend มาแสดงที่หน้าจอเลย
      const errorMsg = error.response?.data?.detail || error.message;
      console.error('Failed to send ticket:', errorMsg);
      alert(`เกิดข้อผิดพลาด: ${JSON.stringify(errorMsg)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <SupportAgent color="primary" /> ส่งแจ้งปัญหาถึงผู้ดูแลระบบ
        </div>
        <IconButton onClick={onClose}><Close /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <TextField
          autoFocus margin="dense" label="หัวข้อปัญหา" fullWidth variant="outlined"
          value={subject} onChange={(e) => setSubject(e.target.value)}
        />
        <TextField
          margin="dense" label="รายละเอียด" fullWidth multiline rows={4} variant="outlined"
          value={message} onChange={(e) => setMessage(e.target.value)} sx={{ mt: 2 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">ยกเลิก</Button>
        <Button onClick={handleSubmit} variant="contained" disabled={loading}>
          {loading ? 'กำลังส่ง...' : 'ส่ง Ticket'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}