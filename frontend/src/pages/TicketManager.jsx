import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, CircularProgress, Button, Chip, Pagination,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { CheckCircle, Visibility } from '@mui/icons-material';
import axios from 'axios';
import AdminShell from '../components/AdminShell';
import LoadError from '../components/LoadError';
import { formatDateTime } from '../utils/dateFormat';
import { useLanguage } from '../context/language-context.js';

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

  // ฟังก์ชันอัปเดตสถานะ Ticket เป็น Closed
  const handleCloseTicket = async (ticketId) => {
    try {
      const token = localStorage.getItem('access_token');
      await axios.patch(
        `${API_URL}/admin/tickets/${ticketId}`,
        { status: 'closed' },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      // อัปเดต State ในหน้าจอให้เปลี่ยนเป็น closed ทันทีโดยไม่ต้องรีเฟรชหน้า
      setTicketData(previous => ({ ...previous,
        items: previous.items.map(ticket => ticket.id === ticketId ? { ...ticket, status: 'closed' } : ticket),
      }));
      setSelectedTicket(previous => previous?.id === ticketId
        ? { ...previous, status: 'closed' }
        : previous);
    } catch (error) {
      console.error('Failed to close ticket:', error);
      alert(t("admin.ticketStatusUpdateFailed"));
    }
  };

  return (
    <AdminShell title={t('admin.ticketTitle')}>
      {/* ตารางแสดงข้อมูล */}
      <Paper className="admin-table-paper surface-card data-table-shell" elevation={0} sx={{ p: 4 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress aria-label={t("common.loading")} />
          </Box>
        ) : (
          <>
          {loadError && <LoadError onRetry={fetchTickets} />}
          <TableContainer sx={{ width: '100%', maxWidth: '100%', overflowX: 'auto' }}>
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
                  tickets.map((ticket) => (
                    <TableRow key={ticket.id} sx={{ '& td': { borderBottom: '1px solid #f1f5f9' } }}>
                      <TableCell>{ticket.id}</TableCell>
                      <TableCell sx={{ overflowWrap: 'anywhere' }}>
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
                            color: '#334155',
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
                          label={ticket.status === 'open' ? t('admin.pendingTicketStatus') : t('admin.closedTicketStatus')}
                          color={ticket.status === 'open' ? 'warning' : 'success'}
                          size="small"
                          sx={{ fontWeight: '600' }}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<Visibility />}
                          onClick={() => setSelectedTicket(ticket)}
                          sx={{ textTransform: 'none', whiteSpace: 'nowrap' }}
                        >
                          {t('admin.viewDetails')}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
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
          {total > PAGE_SIZE && (
            <Box sx={{ display: 'flex', justifyContent: 'center', pt: 3 }}>
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
        open={Boolean(selectedTicket)}
        onClose={() => setSelectedTicket(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle sx={{ fontWeight: '600', overflowWrap: 'anywhere' }}>
          {t('admin.viewDetails')}
        </DialogTitle>
        <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {selectedTicket && (
            <>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">{t('admin.ticketId')}</Typography>
                  <Typography sx={{ overflowWrap: 'anywhere' }}>{selectedTicket.id}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">{t('admin.ticketReporter')}</Typography>
                  <Typography sx={{ overflowWrap: 'anywhere' }}>
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
                    <Chip
                      label={selectedTicket.status === 'open' ? t('admin.pendingTicketStatus') : t('admin.closedTicketStatus')}
                      color={selectedTicket.status === 'open' ? 'warning' : 'success'}
                      size="small"
                    />
                  </Box>
                </Box>
              </Box>

              <Box>
                <Typography variant="caption" color="text.secondary">{t('admin.ticketSubject')}</Typography>
                <Typography sx={{ fontWeight: '600', overflowWrap: 'anywhere' }}>
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
                    maxHeight: 'min(42vh, 360px)',
                    overflowY: 'auto',
                    overflowWrap: 'anywhere',
                    whiteSpace: 'pre-wrap',
                    bgcolor: 'var(--surface-subtle)',
                  }}
                >
                  {selectedTicket.message || '—'}
                </Paper>
              </Box>
            </>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2.5, gap: 1 }}>
          {selectedTicket?.status === 'open' && (
            <Button
              variant="contained"
              color="success"
              startIcon={<CheckCircle />}
              onClick={() => handleCloseTicket(selectedTicket.id)}
              sx={{ mr: 'auto', boxShadow: 'none' }}
            >
              {t('admin.closeTicket')}
            </Button>
          )}
          {selectedTicket?.status === 'closed' && (
            <Typography variant="caption" sx={{ mr: 'auto', color: 'text.secondary', fontWeight: '600' }}>
              {t('admin.resolved')}
            </Typography>
          )}
          <Button onClick={() => setSelectedTicket(null)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>
    </AdminShell>
  );
}
