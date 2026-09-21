import React, { useState } from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, IconButton } from '@mui/material';
import { SupportAgent, Close } from '@mui/icons-material';
import axios from 'axios';
import { useLanguage } from '../context/language-context.js';

const API_URL = import.meta.env.VITE_API_URL;

export default function SupportModal({ open, onClose }) {
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useLanguage();

  const handleSubmit = async () => {
    if (!subject || !message) return alert(t('common.requiredFields'));

    const token = localStorage.getItem('access_token');
    if (!token) return alert(t('common.loginBeforeSupport'));

    try {
      setLoading(true);
      // Backend จะผูก Ticket กับผู้ใช้จาก token ไม่รับ user_id จาก client
      await axios.post(
        `${API_URL}/tickets`,
        { subject, message },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      alert(t('common.ticketSent'));
      setSubject('');
      setMessage('');
      onClose(); // ปิด Modal
    } catch (error) {
      // เอา Error จาก Backend มาแสดงที่หน้าจอเลย
      const errorMsg = error.response?.data?.detail || error.message;
      console.error('Failed to send ticket:', errorMsg);
      alert(`${t('common.error')}: ${JSON.stringify(errorMsg)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <SupportAgent color="primary" /> {t('common.contactSupport')}
        </div>
        <IconButton onClick={onClose}><Close /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <TextField
          autoFocus margin="dense" label={t('user.subject')} fullWidth variant="outlined"
          value={subject} onChange={(e) => setSubject(e.target.value)}
        />
        <TextField
          margin="dense" label={t('user.message')} fullWidth multiline rows={4} variant="outlined"
          value={message} onChange={(e) => setMessage(e.target.value)} sx={{ mt: 2 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">{t('common.cancel')}</Button>
        <Button onClick={handleSubmit} variant="contained" disabled={loading}>
          {loading ? t('common.sending') : t('common.sendTicket')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
