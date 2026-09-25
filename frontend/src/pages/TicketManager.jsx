import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Paper, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, CircularProgress, Button, Chip, Pagination
} from '@mui/material';
import { CheckCircle } from '@mui/icons-material';
import axios from 'axios';
import AdminShell from '../components/AdminShell';
import { formatDateTime } from '../utils/dateFormat';
import { useLanguage } from '../context/language-context.js';

const API_URL = import.meta.env.VITE_API_URL;

export default function TicketManager() {
  const PAGE_SIZE = 20;
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const { t } = useLanguage();

  useEffect(() => {
    document.title = `${t('admin.ticketTitle')} | Smart Lab Admin`;
  }, [t]);

  // ฟังก์ชันดึงข้อมูล Ticket ทั้งหมดจาก Backend
  const fetchTickets = useCallback(async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('access_token');
      const response = await axios.get(`${API_URL}/tickets`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { page, page_size: PAGE_SIZE },
      });
      setTickets(response.data?.data || []);
      setTotal(Number(response.data?.total) || 0);
    } catch (error) {
      console.error('[TicketManager] Failed to fetch tickets:', error);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

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
      setTickets((currentTickets) => currentTickets.map(t => t.id === ticketId ? { ...t, status: 'closed' } : t));
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
            <CircularProgress />
          </Box>
        ) : (
          <>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow sx={{ bgcolor: '#f8fafc' }}>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketId')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketUserId')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketSubject')}</TableCell>
                  <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{t('admin.ticketMessage')}</TableCell>
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
                      <TableCell>{ticket.user_id}</TableCell>
                      <TableCell sx={{ fontWeight: '600', color: '#334155' }}>{ticket.subject}</TableCell>
                      <TableCell sx={{ color: '#475569' }}>{ticket.message}</TableCell>
                      <TableCell sx={{ color: '#475569' }}>
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
                        {ticket.status === 'open' ? (
                          <Button
                            variant="contained"
                            color="success"
                            size="small"
                            startIcon={<CheckCircle />}
                            onClick={() => handleCloseTicket(ticket.id)}
                            sx={{ textTransform: 'none', borderRadius: 2, boxShadow: 'none' }}
                          >
                            {t('admin.closeTicket')}
                          </Button>
                        ) : (
                          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: '600' }}>
                            {t('admin.resolved')}
                          </Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 4, color: '#94a3b8' }}>
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
    </AdminShell>
  );
}
