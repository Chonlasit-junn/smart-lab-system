import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, CircularProgress, Button, Chip, Pagination,
  Dialog, DialogTitle, DialogContent, DialogActions, MenuItem, TextField,
} from '@mui/material';
import { Send, Visibility } from '@mui/icons-material';
import axios from 'axios';
import AdminShell from '../components/AdminShell';
import LoadError from '../components/LoadError';
import { formatDateTime } from '../utils/dateFormat';
import { useLanguage } from '../context/language-context.js';
import {
  getInitialTicketReplyStatus,
  getTicketReplyStatus,
  getTicketReplyStatusPresentation,
  getTicketStatusForReply,
} from '../utils/ticketStatus.js';

const API_URL = import.meta.env.VITE_API_URL;

export default function TicketManager() {
  const PAGE_SIZE = 20;
  const [ticketData, setTicketData] = useState({ page: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const tickets = ticketData.page === page ? ticketData.items : [];
  const [total, setTotal] = useState(0);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [replyMessage, setReplyMessage] = useState('');
  const [replyStatus, setReplyStatus] = useState('received');
  const [replySaving, setReplySaving] = useState(false);
  const ticketsControllerRef = useRef(null);
  const { t } = useLanguage();

  useEffect(() => {
    document.title = `${t('admin.ticketTitle')} | Smart Lab Admin`;
  }, [t]);

  // ฟังก์ชันดึงข้อมูล Ticket ทั้งหมดจาก Backend
  const fetchTickets = useCallback(async () => {
    ticketsControllerRef.current?.abort();
    const controller = new AbortController();
    ticketsControllerRef.current = controller;
    try {
      setLoading(true);
      setLoadError(false);
      const token = localStorage.getItem('access_token');
      const response = await axios.get(`${API_URL}/tickets`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
        params: { page, page_size: PAGE_SIZE },
      });
      if (ticketsControllerRef.current !== controller) return;
      setTicketData({ page, items: response.data?.data || [] });
      setTotal(Number(response.data?.total) || 0);
    } catch (error) {
      if (!axios.isCancel(error) && ticketsControllerRef.current === controller) {
        setLoadError(true);
      }
    } finally {
      if (ticketsControllerRef.current === controller) {
        ticketsControllerRef.current = null;
        setLoading(false);
      }
    }
  }, [page]);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  useEffect(() => () => ticketsControllerRef.current?.abort(), []);

  const handleSendReply = async () => {
    if (!selectedTicket || !replyMessage.trim()) return;
    try {
      const token = localStorage.getItem('access_token');
      setReplySaving(true);
      const response = await axios.post(
        `${API_URL}/admin/tickets/${selectedTicket.id}/replies`,
        { message: replyMessage.trim(), status: replyStatus },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const newReply = response.data?.data;
      const updatedTicket = {
        ...selectedTicket,
        status: getTicketStatusForReply(newReply?.status ?? replyStatus),
        replies: [...(selectedTicket.replies || []), newReply],
      };
      setTicketData(previous => ({
        ...previous,
        items: previous.items.map(ticket => ticket.id === selectedTicket.id ? updatedTicket : ticket),
      }));
      setSelectedTicket(updatedTicket);
      setReplyMessage('');
    } catch (error) {
      console.error('Failed to send ticket reply:', error);
      alert(t('admin.ticketReplyFailed'));
    } finally {
      setReplySaving(false);
    }
  };

  const openTicketDetails = (ticket) => {
    setSelectedTicket(ticket);
    setReplyMessage('');
    setReplyStatus(getInitialTicketReplyStatus(ticket));
  };

  const getStatusPresentation = (ticket) => {
    const latestReply = ticket.replies?.[ticket.replies.length - 1];
    if (latestReply) {
      const replyStatus = getTicketReplyStatusPresentation(getTicketReplyStatus(latestReply));
      return { label: t(replyStatus.labelKey), color: replyStatus.color };
    }
    const { status } = ticket;
    if (status === 'closed') return { label: t('user.closedTicket'), color: 'success' };
    if (status === 'in_progress') return { label: t('user.inProgressTicket'), color: 'info' };
    return { label: t('admin.pendingTicketStatus'), color: 'warning' };
  };

  return (
    <AdminShell title={t('admin.ticketTitle')}>
      {/* ตารางแสดงข้อมูล */}
      <Paper className="admin-table-paper surface-card data-table-shell admin-ticket-list" elevation={0} sx={{ p: 4 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress aria-label={t("common.loading")} />
          </Box>
        ) : (
          <>
          {loadError && <LoadError onRetry={fetchTickets} />}
          <TableContainer className="admin-ticket-table-desktop" sx={{ width: '100%', maxWidth: '100%', overflowX: 'auto' }}>
            <Table sx={{ width: '100%', minWidth: 900, tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: 72 }} />
                <col style={{ width: 110 }} />
                <col />
                <col style={{ width: 180 }} />
                <col style={{ width: 140 }} />
                <col style={{ width: 170 }} />
              </colgroup>
              <TableHead>
                <TableRow sx={{ bgcolor: '#f8fafc' }}>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketId')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketReporter')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketSubject')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketSubmitted')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketStatus')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b', textAlign: 'center' }}>{t('admin.ticketManage')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.length > 0 ? (
                  tickets.map((ticket) => {
                    const status = getStatusPresentation(ticket);
                    return (
                      <TableRow key={ticket.id} sx={{ '& td': { borderBottom: '1px solid #f1f5f9' } }}>
                      <TableCell>{ticket.id}</TableCell>
                      <TableCell sx={{ overflowWrap: 'break-word' }}>
                        {ticket.user_name || t('common.unknownName')}
                      </TableCell>
                      <TableCell sx={{ minWidth: 0 }}>
                        <Box
                          title={ticket.subject || '—'}
                          sx={{
                            display: 'block',
                            minWidth: 0,
                            maxWidth: '100%',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontWeight: '600',
                            color: 'var(--text-dark)',
                          }}
                        >
                          {ticket.subject || '—'}
                        </Box>
                      </TableCell>
                      <TableCell sx={{ color: '#475569', whiteSpace: 'nowrap' }}>
                        {formatDateTime(ticket.created_at, t('common.locale'), { fallback: '-', includeSeconds: true })}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={status.label}
                          color={status.color}
                          size="small"
                          sx={{ fontWeight: '600' }}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<Visibility />}
                          onClick={() => openTicketDetails(ticket)}
                          sx={{ textTransform: 'none', whiteSpace: 'nowrap' }}
                        >
                          {t('admin.viewDetails')}
                        </Button>
                      </TableCell>
                      </TableRow>
                    );
                  })
                ) : loadError ? null : (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 4, color: '#94a3b8' }}>
                      {t('admin.noTickets')}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <Box className="admin-ticket-mobile-list">
            {tickets.length > 0 ? tickets.map((ticket) => {
              const status = getStatusPresentation(ticket);
              return (
                <Paper key={ticket.id} className="admin-ticket-mobile-card" variant="outlined">
                  <Box className="admin-ticket-mobile-card-top">
                    <Typography variant="caption" color="text.secondary">
                      {t('admin.ticketId')} #{ticket.id}
                    </Typography>
                    <Chip label={status.label} color={status.color} size="small" />
                  </Box>
                  <Typography className="admin-ticket-mobile-reporter" variant="subtitle2">
                    {ticket.user_name || t('common.unknownName')}
                  </Typography>
                  <Typography className="admin-ticket-mobile-subject" variant="body2">
                    {ticket.subject || '—'}
                  </Typography>
                  <Box className="admin-ticket-mobile-card-bottom">
                    <Typography variant="caption" color="text.secondary">
                      {formatDateTime(ticket.created_at, t('common.locale'), { fallback: '-', includeSeconds: true })}
                    </Typography>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Visibility />}
                      onClick={() => openTicketDetails(ticket)}
                      sx={{ textTransform: 'none', whiteSpace: 'nowrap' }}
                    >
                      {t('admin.viewDetails')}
                    </Button>
                  </Box>
                </Paper>
              );
            }) : !loadError ? (
              <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                {t('admin.noTickets')}
              </Typography>
            ) : null}
          </Box>
          {total > PAGE_SIZE && (
            <Box className="admin-ticket-pagination" sx={{ display: 'flex', justifyContent: 'center', pt: 3 }}>
              <Pagination
                count={Math.max(1, Math.ceil(total / PAGE_SIZE))}
                page={page}
                onChange={(_, nextPage) => setPage(nextPage)}
                color="primary"
              />
            </Box>
          )}
          </>
        )}
      </Paper>

      <Dialog
        className="ticket-details-dialog"
        open={Boolean(selectedTicket)}
        onClose={() => setSelectedTicket(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle sx={{ fontWeight: '600', overflowWrap: 'break-word' }}>
          {t('admin.viewDetails')}
        </DialogTitle>
        <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 2, minHeight: 0, overflowY: 'auto' }}>
          {selectedTicket && (
            <>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">{t('admin.ticketId')}</Typography>
                  <Typography sx={{ overflowWrap: 'break-word' }}>{selectedTicket.id}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">{t('admin.ticketReporter')}</Typography>
                  <Typography sx={{ overflowWrap: 'break-word' }}>
                    {selectedTicket.user_name || t('common.unknownName')}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">{t('admin.ticketSubmitted')}</Typography>
                  <Typography>{formatDateTime(selectedTicket.created_at, t('common.locale'), { fallback: '-', includeSeconds: true })}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">{t('admin.ticketStatus')}</Typography>
                  <Box>
                    {(() => {
                      const status = getStatusPresentation(selectedTicket);
                      return <Chip label={status.label} color={status.color} size="small" />;
                    })()}
                  </Box>
                </Box>
              </Box>

              <Box>
                <Typography variant="caption" color="text.secondary">{t('admin.ticketSubject')}</Typography>
                <Typography sx={{ fontWeight: '600', overflowWrap: 'break-word' }}>
                  {selectedTicket.subject || '—'}
                </Typography>
              </Box>

              <Box sx={{ minWidth: 0 }}>
                <Typography variant="caption" color="text.secondary">{t('admin.ticketMessage')}</Typography>
                <Paper
                  variant="outlined"
                  role="region"
                  aria-label={t('admin.ticketMessage')}
                  sx={{
                    mt: 0.75,
                    p: 2,
                    overflowWrap: 'anywhere',
                    whiteSpace: 'pre-wrap',
                    bgcolor: 'var(--surface-subtle)',
                  }}
                >
                  {selectedTicket.message || '—'}
                </Paper>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: '700' }}>
                  {t('admin.ticketReplies')}
                </Typography>
                {selectedTicket.replies?.length ? (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {selectedTicket.replies.map((reply) => {
                      const statusPresentation = getTicketReplyStatusPresentation(getTicketReplyStatus(reply));
                      return (
                        <Paper key={reply.id} variant="outlined" sx={{ p: 1.5, bgcolor: 'var(--surface-subtle)' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 0.75 }}>
                            <Typography variant="body2" fontWeight="700" sx={{ overflowWrap: 'break-word' }}>
                              {reply.responder_name}
                            </Typography>
                            <Chip
                              label={t(statusPresentation.labelKey)}
                              color={statusPresentation.color}
                              size="small"
                            />
                          </Box>
                          <Typography variant="caption" color="text.secondary">
                            {formatDateTime(reply.created_at, t('common.locale'), { fallback: '-', includeSeconds: true })}
                          </Typography>
                          <Typography sx={{ mt: 0.75, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                            {reply.message}
                          </Typography>
                        </Paper>
                      );
                    })}
                  </Box>
                ) : (
                  <Typography color="text.secondary" variant="body2">
                    {t('admin.noTicketReplies')}
                  </Typography>
                )}
              </Box>

              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <TextField
                  label={t('admin.replyMessage')}
                  value={replyMessage}
                  onChange={(event) => setReplyMessage(event.target.value)}
                  multiline
                  minRows={3}
                  maxRows={8}
                  fullWidth
                  inputProps={{ maxLength: 5000 }}
                />
                <TextField
                  select
                  size="small"
                  fullWidth
                  label={t('admin.ticketReplyStatus')}
                  value={replyStatus}
                  onChange={(event) => setReplyStatus(event.target.value)}
                  disabled={replySaving}
                >
                  <MenuItem value="received">{t('common.ticketStatusReceived')}</MenuItem>
                  <MenuItem value="in_progress">{t('common.ticketStatusInProgress')}</MenuItem>
                  <MenuItem value="resolved">{t('common.ticketStatusResolved')}</MenuItem>
                </TextField>
                <Button
                  variant="contained"
                  startIcon={<Send />}
                  onClick={handleSendReply}
                  disabled={replySaving || !replyMessage.trim()}
                  sx={{ alignSelf: 'flex-end', boxShadow: 'none' }}
                >
                  {replySaving ? t('common.sending') : t('admin.sendTicketReply')}
                </Button>
              </Box>
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2.5, gap: 1 }}>
          <Button onClick={() => setSelectedTicket(null)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>
    </AdminShell>
  );
}
