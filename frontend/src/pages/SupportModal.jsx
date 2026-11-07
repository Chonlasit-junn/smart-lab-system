import React, { useState } from 'react';
import { Alert, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, IconButton } from '@mui/material';
import { SupportAgent, Close } from '@mui/icons-material';
import axios from 'axios';
import { useLanguage } from '../context/language-context.js';
import {
  countTicketCharacters,
  getTicketErrorMessage,
  limitTicketText,
  TICKET_MESSAGE_MAX_LENGTH,
  TICKET_SUBJECT_MAX_LENGTH,
} from '../utils/ticketValidation.js';

const API_URL = import.meta.env.VITE_API_URL;

export default function SupportModal({ open, onClose }) {
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState('');
  const { t } = useLanguage();

  const handleSubmit = async () => {
    if (!subject.trim() || !message.trim()) {
      setFormError(t('common.requiredFields'));
      return;
    }
    if (countTicketCharacters(subject) > TICKET_SUBJECT_MAX_LENGTH) {
      setFormError(t('common.ticketSubjectTooLong'));
      return;
    }
    if (countTicketCharacters(message) > TICKET_MESSAGE_MAX_LENGTH) {
      setFormError(t('common.ticketMessageTooLong'));
      return;
    }

    const token = localStorage.getItem('access_token');
    if (!token) {
      setFormError(t('common.loginBeforeSupport'));
      return;
    }

    try {
      setLoading(true);
      // Backend จะผูก Ticket กับผู้ใช้จาก token ไม่รับ user_id จาก client
      await axios.post(
        `${API_URL}/tickets`,
        { subject: subject.trim(), message: message.trim() },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      alert(t('common.ticketSent'));
      setSubject('');
      setMessage('');
      setFormError('');
      onClose(); // ปิด Modal
    } catch (error) {
      setFormError(getTicketErrorMessage(error, t));
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
        {formError && <Alert severity="error" sx={{ mb: 1 }}>{formError}</Alert>}
        <TextField
          autoFocus margin="dense" label={t('user.subject')} fullWidth variant="outlined"
          value={subject}
          onChange={(e) => {
            setSubject(limitTicketText(e.target.value, TICKET_SUBJECT_MAX_LENGTH));
            setFormError('');
          }}
          helperText={`${t('common.ticketSubjectLimit')} · ${countTicketCharacters(subject)}/${TICKET_SUBJECT_MAX_LENGTH} ${t('common.characterCount')}`}
        />
        <TextField
          margin="dense" label={t('user.message')} fullWidth multiline rows={4} variant="outlined"
          value={message}
          onChange={(e) => {
            setMessage(limitTicketText(e.target.value, TICKET_MESSAGE_MAX_LENGTH));
            setFormError('');
          }}
          helperText={`${t('common.ticketMessageLimit')} · ${countTicketCharacters(message)}/${TICKET_MESSAGE_MAX_LENGTH} ${t('common.characterCount')}`}
          sx={{ mt: 2 }}
        />
      </DialogContent>
      <DialogActions className="support-dialog-actions">
        <Button onClick={onClose} color="inherit">
          <span className="support-button-label">{t('common.cancel')}</span>
        </Button>
        <Button onClick={handleSubmit} variant="contained" disabled={loading}>
          <span className="support-button-label">
            {loading ? t('common.sending') : t('common.sendTicket')}
          </span>
        </Button>
      </DialogActions>
    </Dialog>
  );
}
