import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Paper,
  Popover,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  Pagination,
} from "@mui/material";
import {
  Assignment,
  Close,
  Computer,
  ConfirmationNumber,
  EventNote,
  History as HistoryIcon,
  Logout,
  Menu as MenuIcon,
  Person,
  SupportAgent,
  Visibility,
} from "@mui/icons-material";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import { formatDateTime } from "../utils/dateFormat";
import SupportModal from "./SupportModal";
import NotificationBell from "../components/NotificationBell";
import LoadError from "../components/LoadError";
import AdminModeSwitch from "../components/AdminModeSwitch";
import ResponsiveDataTable from "../components/ResponsiveDataTable";
import { getTicketReplyStatus, getTicketReplyStatusPresentation } from "../utils/ticketStatus.js";

const API_URL = import.meta.env.VITE_API_URL;

const STATUS_LABELS = {
  open: { key: "user.openTicket", color: "warning" },
  in_progress: { key: "user.inProgressTicket", color: "info" },
  closed: { key: "user.closedTicket", color: "success" },
};

const MENU_ITEMS = [
  { key: "common.labReserve", icon: <EventNote />, path: "/booking" },
  { key: "common.reserved", icon: <Assignment />, path: "/reserved" },
  { key: "common.history", icon: <HistoryIcon />, path: "/history" },
  {
    key: "common.myTickets",
    icon: <ConfirmationNumber />,
    path: "/my-tickets",
  },
];

export default function MyTickets() {
  const PAGE_SIZE = 20;
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser, logout } = useAuth();
  const { t } = useLanguage();
  const ticketsControllerRef = useRef(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [ticketData, setTicketData] = useState({ identity: null, page: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedTicket, setSelectedTicket] = useState(null);

  const userIdentity = currentUser?.id || currentUser?.email;
  const tickets = ticketData.identity === userIdentity && ticketData.page === page ? ticketData.items : [];

  const fetchMyTickets = useCallback(async () => {
    ticketsControllerRef.current?.abort();
    ticketsControllerRef.current = null;
    if (!userIdentity) return;

    const controller = new AbortController();
    ticketsControllerRef.current = controller;

    try {
      setLoading(true);
      setError("");
      const token = localStorage.getItem("access_token");
      const response = await axios.get(`${API_URL}/tickets/me`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
        params: { page, page_size: PAGE_SIZE },
      });
      if (ticketsControllerRef.current !== controller) return;
      setTicketData({ identity: userIdentity, page, items: response.data?.data || [] });
      setTotal(Number(response.data?.total) || 0);
    } catch (requestError) {
      if (axios.isCancel(requestError) || ticketsControllerRef.current !== controller) return;
      setError(true);
    } finally {
      if (ticketsControllerRef.current === controller) {
        ticketsControllerRef.current = null;
        setLoading(false);
      }
    }
  }, [page, userIdentity]);

  useEffect(() => {
    document.title = `${t("user.ticketTitle")} | Smart Lab`;
  }, [t]);

  useEffect(() => {
    if (!userIdentity) {
      navigate("/");
      return;
    }
    fetchMyTickets();
  }, [fetchMyTickets, navigate, userIdentity]);

  useEffect(() => () => ticketsControllerRef.current?.abort(), []);

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate("/");
  };

  const handleNavigate = (path) => {
    setIsSidebarOpen(false);
    navigate(path);
  };

  return (
    <div className="app-layout user-scroll-page-layout">
      {isSidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <div className={`sidebar ${isSidebarOpen ? "open" : ""}`}>
        <div className="sidebar-logo">
          <Computer sx={{ fontSize: 40, color: "#1877f2" }} />
          <div>
            <Typography variant="h6" fontWeight="600" lineHeight={1.2}>
              Smart Lab
            </Typography>
            <Typography variant="caption" color="textSecondary">
              {t("common.brandTagline")}
            </Typography>
          </div>
        </div>

        <div className="sidebar-menu">
          {MENU_ITEMS.map((item) => (
            <div
              key={item.path}
              className={`menu-item ${
                location.pathname === item.path ? "active" : ""
              }`}
              onClick={() => handleNavigate(item.path)}
            >
              {item.icon} {t(item.key)}
            </div>
          ))}
        </div>

        <div
          className="sidebar-menu"
          style={{ flex: "none", paddingBottom: "24px" }}
        >
          <div
            className="menu-item"
            onClick={() => {
              setIsSidebarOpen(false);
              setIsSupportOpen(true);
            }}
          >
            <SupportAgent /> {t("common.support")}
          </div>
        </div>
      </div>

      <div className="main-area">
        <div className="top-header">
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconButton
              sx={{ display: { xs: "block", md: "none" }, color: "#111827" }}
              onClick={() => setIsSidebarOpen(true)}
              aria-label={t("common.openNavigation")}
            >
              <MenuIcon />
            </IconButton>
            <Typography
              variant="h5"
              fontWeight="700"
              color="#111827"
              sx={{ display: { xs: "none", sm: "block" } }}
            >
              {t("user.ticketTitle")}
            </Typography>
          </Box>

          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: { xs: 1, sm: 3 },
            }}
          >
            <NotificationBell />
            {currentUser && (
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.5,
                  borderLeft: "1px solid #e2e8f0",
                  pl: { xs: 1, sm: 3 },
                }}
              >
                <Box
                  className="profile-text-container"
                  sx={{ textAlign: "right" }}
                >
                  <Typography
                    variant="subtitle2"
                    fontWeight="600"
                    lineHeight={1.2}
                  >
                    {currentUser.name}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {currentUser.role}
                  </Typography>
                </Box>
                <IconButton
                  onClick={(event) => setAnchorEl(event.currentTarget)}
                  sx={{ p: 0.5, "&:hover": { bgcolor: "#f1f5f9" } }}
                  aria-label={t("common.openUserMenu")}
                >
                  <Avatar
                    sx={{
                      bgcolor: "#111827",
                      width: 36,
                      height: 36,
                      boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
                    }}
                  >
                    {currentUser.initial || currentUser.name?.charAt(0)}
                  </Avatar>
                </IconButton>

                <Popover
                  anchorEl={anchorEl}
                  open={Boolean(anchorEl)}
                  onClose={() => setAnchorEl(null)}
                  anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                  transformOrigin={{ vertical: "top", horizontal: "right" }}
                  PaperProps={{
                    className: "user-account-popover",
                    sx: {
                      mt: 1.5,
                      width: 320,
                      borderRadius: 5,
                      boxShadow: "0 20px 45px rgba(15,23,42,0.16)",
                      border: "1px solid #e2e8f0",
                      overflow: "hidden",
                    },
                  }}
                >
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      px: 2,
                      pt: 1.5,
                    }}
                  >
                    <Typography
                      fontSize="13px"
                      fontWeight="500"
                      color="#64748b"
                      noWrap
                    >
                      {currentUser.email}
                    </Typography>
                    <IconButton
                      size="small"
                      onClick={() => setAnchorEl(null)}
                      aria-label={t("common.closeUserMenu")}
                    >
                      <Close sx={{ fontSize: 18, color: "#64748b" }} />
                    </IconButton>
                  </Box>

                  <Box sx={{ textAlign: "center", px: 3, pb: 3, pt: 0.5 }}>
                    <Avatar
                      sx={{
                        bgcolor: "#0f172a",
                        width: 84,
                        height: 84,
                        mx: "auto",
                        fontSize: "32px",
                        boxShadow:
                          "0 0 0 4px #eff6ff, 0 8px 20px rgba(59,130,246,0.25)",
                      }}
                    >
                      {currentUser.initial || currentUser.name?.charAt(0)}
                    </Avatar>
                    <Typography
                      sx={{ mt: 1.5, color: "#1e293b" }}
                      fontWeight="600"
                      fontSize="18px"
                    >
                      {t("common.greeting")}, {currentUser.name}
                    </Typography>
                    <Button
                      variant="outlined"
                      onClick={() => {
                        setAnchorEl(null);
                        navigate("/profile");
                      }}
                      sx={{
                        mt: 2,
                        borderRadius: 20,
                        textTransform: "none",
                        fontWeight: "600",
                        fontSize: "13px",
                        px: 2.5,
                        py: 0.6,
                        color: "#3b82f6",
                        borderColor: "#cbd8f5",
                        "&:hover": {
                          borderColor: "#3b82f6",
                          bgcolor: "#eff6ff",
                        },
                      }}
                    >
                      {t("common.manageAccount")}
                    </Button>
                  </Box>

                  <Divider />
                  <Box sx={{ px: 1, py: 1 }}>
                    <AdminModeSwitch destination="admin" onNavigate={() => setAnchorEl(null)} />
                    <Box
                      onClick={handleLogout}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1.5,
                        px: 1.5,
                        py: 1,
                        borderRadius: 2,
                        cursor: "pointer",
                        "&:hover": { bgcolor: "#fef2f2" },
                      }}
                    >
                      <Logout className="theme-colored" sx={{ fontSize: 20, color: "#ef4444" }} />
                      <Typography className="theme-colored" fontSize="13px" fontWeight="600" color="#ef4444">
                        {t("common.logout")}
                      </Typography>
                    </Box>
                  </Box>
                </Popover>
              </Box>
            )}
          </Box>
        </div>

        <div className="content-area page-content">
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", mt: 10 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Paper
              className="surface-card data-table-shell"
              elevation={0}
              sx={{
                p: { xs: 2, sm: 4 },
                border: "2px solid #cbd5e1",
                borderRadius: 4,
                width: "100%",
                maxWidth: "1200px",
                mx: "auto",
                bgcolor: "white",
              }}
            >
              {error && <LoadError onRetry={fetchMyTickets} />}

              <Typography
                variant="h6"
                fontWeight="600"
                color="#64748b"
                sx={{ mb: 3 }}
              >
                {t("user.myRequests")}
              </Typography>

              {tickets.length > 0 ? (
                <>
                  <ResponsiveDataTable sx={{ width: "100%", maxWidth: "100%", overflowX: "auto" }}>
                    <Table sx={{ width: "100%", minWidth: 940, tableLayout: "fixed" }}>
                      <colgroup>
                        <col style={{ width: 145 }} />
                        <col style={{ width: 200 }} />
                        <col style={{ width: 145 }} />
                        <col style={{ width: 115 }} />
                        <col style={{ width: 220 }} />
                        <col style={{ width: 115 }} />
                      </colgroup>
                      <TableHead>
                        <TableRow>
                          <TableCell
                            sx={{
                              fontWeight: "600",
                              borderBottom: "1px solid #e2e8f0",
                              color: "#64748b",
                            }}
                          >
                            {t("user.subject")}
                          </TableCell>
                          <TableCell
                            sx={{
                              fontWeight: "600",
                              borderBottom: "1px solid #e2e8f0",
                              color: "#64748b",
                            }}
                          >
                            {t("user.message")}
                          </TableCell>
                          <TableCell
                            sx={{
                              fontWeight: "600",
                              borderBottom: "1px solid #e2e8f0",
                              color: "#64748b",
                            }}
                          >
                            {t("user.submittedAt")}
                          </TableCell>
                          <TableCell
                            sx={{
                              fontWeight: "600",
                              borderBottom: "1px solid #e2e8f0",
                              color: "#64748b",
                            }}
                          >
                            {t("common.status")}
                          </TableCell>
                          <TableCell
                            sx={{
                              fontWeight: "600",
                              borderBottom: "1px solid #e2e8f0",
                              color: "#64748b",
                            }}
                          >
                            {t("user.adminResponse")}
                          </TableCell>
                          <TableCell
                            sx={{
                              fontWeight: "600",
                              borderBottom: "1px solid #e2e8f0",
                              color: "#64748b",
                              textAlign: "center",
                            }}
                          >
                            {t("admin.viewDetails")}
                          </TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {tickets.map((ticket) => {
                          const latestReply = ticket.replies?.[ticket.replies.length - 1];
                          const status = latestReply
                            ? getTicketReplyStatusPresentation(getTicketReplyStatus(latestReply))
                            : STATUS_LABELS[ticket.status] || {
                            key: "user.unknownStatus",
                            color: "default",
                          };

                          return (
                            <TableRow
                              key={ticket.id}
                              sx={{
                                "&:last-child td, &:last-child th": { border: 0 },
                              }}
                            >
                              <TableCell
                                sx={{
                                  minWidth: 0,
                                  fontWeight: "600",
                                  color: "#334155",
                                }}
                              >
                                <Box
                                  sx={{
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                  }}
                                >
                                  {ticket.subject || "—"}
                                </Box>
                              </TableCell>
                              <TableCell
                                sx={{
                                  minWidth: 0,
                                  color: "#475569",
                                }}
                              >
                                <Box
                                  sx={{
                                    display: "-webkit-box",
                                    overflow: "hidden",
                                    WebkitBoxOrient: "vertical",
                                    WebkitLineClamp: 2,
                                    overflowWrap: "anywhere",
                                    lineHeight: 1.4,
                                  }}
                                >
                                  {ticket.message || "—"}
                                </Box>
                              </TableCell>
                              <TableCell
                                sx={{
                                  color: "#475569",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {formatDateTime(ticket.created_at, t("common.locale"), { fallback: "-" })}
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={t(status.labelKey || status.key)}
                                  color={status.color}
                                  size="small"
                                  sx={{ fontWeight: "700" }}
                                />
                              </TableCell>
                              <TableCell sx={{ minWidth: 0 }}>
                                {latestReply ? (
                                  <Box sx={{ minWidth: 0 }}>
                                    <Typography
                                      variant="caption"
                                      fontWeight="700"
                                      noWrap
                                      title={latestReply.responder_name || t("common.unknownName")}
                                    >
                                      {t("user.adminReplyBy")}: {latestReply.responder_name || t("common.unknownName")}
                                    </Typography>
                                    <Typography
                                      variant="body2"
                                      sx={{
                                        display: "-webkit-box",
                                        overflow: "hidden",
                                        WebkitBoxOrient: "vertical",
                                        WebkitLineClamp: 2,
                                        overflowWrap: "anywhere",
                                        lineHeight: 1.4,
                                      }}
                                    >
                                      {latestReply.message}
                                    </Typography>
                                  </Box>
                                ) : (
                                  <Typography variant="body2" color="text.secondary">
                                    {t("user.awaitingAdminResponse")}
                                  </Typography>
                                )}
                              </TableCell>
                              <TableCell align="center">
                                <Button
                                  variant="outlined"
                                  size="small"
                                  startIcon={<Visibility />}
                                  onClick={() => setSelectedTicket(ticket)}
                                  sx={{ textTransform: "none", whiteSpace: "nowrap" }}
                                >
                                  {t("admin.viewDetails")}
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </ResponsiveDataTable>
                  {total > PAGE_SIZE && (
                    <Box sx={{ display: "flex", justifyContent: "center", pt: 3 }}>
                      <Pagination
                        count={Math.max(1, Math.ceil(total / PAGE_SIZE))}
                        page={page}
                        onChange={(_, nextPage) => setPage(nextPage)}
                        color="primary"
                      />
                    </Box>
                  )}
                </>
              ) : error ? null : (
                <Box
                  className="empty-state history-empty-state"
                  sx={{ bgcolor: "var(--surface-subtle)" }}
                >
                  <Typography variant="body1" color="textSecondary">
                    {t("user.noTicketsSent")}
                  </Typography>
                </Box>
              )}
            </Paper>
          )}
        </div>
      </div>

      <Dialog
        open={Boolean(selectedTicket)}
        onClose={() => setSelectedTicket(null)}
        fullWidth
        maxWidth="sm"
      >
        {selectedTicket && (() => {
          const latestReply = selectedTicket.replies?.[selectedTicket.replies.length - 1];
          const status = latestReply
            ? getTicketReplyStatusPresentation(getTicketReplyStatus(latestReply))
            : STATUS_LABELS[selectedTicket.status] || {
            key: "user.unknownStatus",
            color: "default",
          };

          return (
            <>
              <DialogTitle
                sx={{
                  fontWeight: "700",
                  overflowWrap: "anywhere",
                  maxHeight: "20vh",
                  overflowY: "auto",
                }}
              >
                {selectedTicket.subject || t("user.myRequests")}
              </DialogTitle>
              <DialogContent
                dividers
                sx={{ display: "flex", flexDirection: "column", gap: 2, borderColor: "var(--border-light)" }}
              >
                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
                  <Box>
                    <Typography variant="caption" sx={{ color: "var(--text-gray)" }}>
                      {t("user.submittedAt")}
                    </Typography>
                    <Typography>
                      {formatDateTime(selectedTicket.created_at, t("common.locale"), { fallback: "-" })}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" sx={{ color: "var(--text-gray)" }}>
                      {t("common.status")}
                    </Typography>
                    <Box>
                      <Chip label={t(status.labelKey || status.key)} color={status.color} size="small" />
                    </Box>
                  </Box>
                </Box>

                <Box>
                  <Typography variant="subtitle2" fontWeight="700">
                    {t("user.message")}
                  </Typography>
                  <Paper
                    variant="outlined"
                    role="region"
                    aria-label={t("user.message")}
                    sx={{
                      mt: 0.75,
                      p: 2,
                      maxHeight: "min(35vh, 320px)",
                      overflowY: "auto",
                      overflowWrap: "anywhere",
                      whiteSpace: "pre-wrap",
                      bgcolor: "var(--surface-subtle)",
                      color: "var(--text-dark)",
                    }}
                  >
                    {selectedTicket.message || "—"}
                  </Paper>
                </Box>

                <Box>
                  <Typography variant="subtitle2" fontWeight="700" sx={{ mb: 1 }}>
                    {t("user.adminResponse")}
                  </Typography>
                  {selectedTicket.replies?.length ? (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, maxHeight: 360, overflowY: "auto", pr: 0.5 }}>
                      {selectedTicket.replies.map((reply) => {
                        const statusPresentation = getTicketReplyStatusPresentation(getTicketReplyStatus(reply));
                        return (
                          <Paper
                            key={reply.id}
                            variant="outlined"
                            sx={{ p: 1.5, bgcolor: "var(--surface-subtle)" }}
                          >
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1, mb: 0.75 }}>
                              <Typography variant="body2" fontWeight="700" sx={{ overflowWrap: "anywhere" }}>
                                {t("user.adminReplyBy")}: {reply.responder_name || t("common.unknownName")}
                              </Typography>
                              <Chip
                                label={t(statusPresentation.labelKey)}
                                color={statusPresentation.color}
                                size="small"
                              />
                            </Box>
                            <Typography variant="caption" sx={{ color: "var(--text-gray)" }}>
                              {formatDateTime(reply.created_at, t("common.locale"), { fallback: "-", includeSeconds: true })}
                            </Typography>
                            <Typography sx={{ mt: 0.75, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                              {reply.message}
                            </Typography>
                          </Paper>
                        );
                      })}
                    </Box>
                  ) : (
                    <Typography variant="body2" sx={{ color: "var(--text-gray)" }}>
                      {t("user.awaitingAdminResponse")}
                    </Typography>
                  )}
                </Box>
              </DialogContent>
              <DialogActions sx={{ p: 2 }}>
                <Button onClick={() => setSelectedTicket(null)}>{t("common.close")}</Button>
              </DialogActions>
            </>
          );
        })()}
      </Dialog>

      <SupportModal
        open={isSupportOpen}
        onClose={() => {
          setIsSupportOpen(false);
          fetchMyTickets();
        }}
      />
    </div>
  );
}
