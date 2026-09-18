// ============================================================================
// 1. IMPORTS & CONFIGURATION
// ============================================================================
import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Box,
  Typography,
  Avatar,
  IconButton,
  Paper,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
  Popover,
  Divider,
  Chip,
  Badge,
} from "@mui/material";
import {
  Notifications,
  EventNote,
  Assignment,
  History,
  SupportAgent,
  Logout,
  Computer,
  Person,
  Menu as MenuIcon,
  Close,
} from "@mui/icons-material";
import CancelIcon from "@mui/icons-material/Cancel";

import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/auth-context";
import {
  formatRelativeTime,
  formatFullTime,
  groupNotifications,
} from "../utils/notificationTime";

const API_URL = import.meta.env.VITE_API_URL;

// ป้ายชื่อเหตุผลของการเปลี่ยนแปลงคะแนน (ใช้แสดงในกระดิ่งแจ้งเตือน)
const POINT_REASON_LABELS = {
  daily_bonus: "Daily bonus",
  no_show: "ไม่มาตามการจอง",
  forbidden_app: "ใช้โปรแกรมต้องห้าม",
  late_cancel: "ยกเลิกการจองกระชั้นชิด",
  complete_session: "จบการใช้งานปกติ",
  admin_grant: "Admin อนุมัติเพิ่มคะแนน",
};

// localStorage key prefix ที่ใช้จำว่าผู้ใช้อ่านแจ้งเตือนคะแนนล่าสุดถึงไอดีไหนแล้ว
const LAST_SEEN_POINT_LOG_KEY = "last_seen_point_log_id";

export default function Reserved() {
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [bookingToCancel, setBookingToCancel] = useState(null);

  // State สำหรับกระดิ่งแจ้งเตือน (ดึงจากประวัติการเปลี่ยนแปลงคะแนน เหมือนหน้า Booking)
  const [pointLogs, setPointLogs] = useState([]);
  const [lastSeenLogId, setLastSeenLogId] = useState(
    () => Number(localStorage.getItem(LAST_SEEN_POINT_LOG_KEY)) || 0,
  );

  const fetchMyBookings = useCallback(async () => {
    if (!currentUser) return;
    try {
      setLoading(true);
      const token = localStorage.getItem("access_token");
      const response = await axios.get(
        `${API_URL}/bookings/user/${currentUser.email}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const allBookings = response.data.data;

      const todayMidnight = new Date();
      todayMidnight.setHours(0, 0, 0, 0);

      const upcomingOnly = allBookings.filter((booking) => {
        const bookingDate = new Date(booking.booking_date);
        bookingDate.setHours(0, 0, 0, 0);
        return bookingDate.getTime() >= todayMidnight.getTime();
      });

      setBookings(upcomingOnly);
    } catch (error) {
      console.error("[API Error] Failed to fetch bookings:", error);
    } finally {
      setLoading(false);
    }
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) {
      navigate("/");
      return;
    }
    fetchMyBookings();
  }, [currentUser, fetchMyBookings, navigate]);

  // ดึงประวัติการเปลี่ยนแปลงคะแนน เพื่อนำมาแสดงในกระดิ่งแจ้งเตือน
  useEffect(() => {
    if (!currentUser?.email) {
      setPointLogs([]);
      return undefined;
    }

    const token = localStorage.getItem("access_token");

    const fetchPointLogs = async () => {
      try {
        const response = await axios.get(
          `${API_URL}/users/me/points/logs?limit=20`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        setPointLogs(response.data?.data || []);
      } catch (error) {
        console.error("[API Error] Failed to fetch point logs:", error);
      }
    };

    fetchPointLogs();
    const intervalId = setInterval(fetchPointLogs, 15000);
    return () => clearInterval(intervalId);
  }, [currentUser?.email]);

  const handleConfirmCancel = async () => {
    if (!bookingToCancel) return;
    try {
      await axios.delete(`${API_URL}/bookings/${bookingToCancel}`, {
        params: { email: currentUser.email },
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      setCancelDialogOpen(false);
      setBookingToCancel(null);
      fetchMyBookings();
    } catch {
      alert("Failed to cancel booking.");
    }
  };

  const handleOpenCancelDialog = (bookingId) => {
    setBookingToCancel(bookingId);
    setCancelDialogOpen(true);
  };

  const handleCloseCancelDialog = () => {
    setCancelDialogOpen(false);
    setBookingToCancel(null);
  };

  const formatDate = (dateString) => {
    const options = { day: "numeric", month: "short", year: "numeric" };
    return new Date(dateString).toLocaleDateString("en-GB", options);
  };

  // Add Popover State & Handlers
  const [anchorEl, setAnchorEl] = useState(null);
  const openUserMenu = Boolean(anchorEl);

  const handleAvatarClick = (e) => setAnchorEl(e.currentTarget);
  const handleCloseUserMenu = () => setAnchorEl(null);

  // ----- กระดิ่งแจ้งเตือน (เหมือนหน้า Booking) -----
  const [notifAnchorEl, setNotifAnchorEl] = useState(null);
  const openNotifMenu = Boolean(notifAnchorEl);

  const handleNotifClick = (e) => {
    setNotifAnchorEl(e.currentTarget);
    if (pointLogs.length > 0) {
      const latestId = Math.max(...pointLogs.map((log) => log.id));
      if (latestId > lastSeenLogId) {
        setLastSeenLogId(latestId);
        localStorage.setItem(LAST_SEEN_POINT_LOG_KEY, String(latestId));
      }
    }
  };
  const handleCloseNotifMenu = () => setNotifAnchorEl(null);

  // นาฬิกาสำหรับคำนวณเวลาสัมพัทธ์ ("12 นาทีที่ผ่านมา") ให้ขยับเองทุก 1 นาที
  const [notifNow, setNotifNow] = useState(() => new Date());
  useEffect(() => {
    const timerId = setInterval(() => setNotifNow(new Date()), 60000);
    return () => clearInterval(timerId);
  }, []);

  const notifications = useMemo(
    () =>
      pointLogs.map((log) => {
        const isPositive = log.change > 0;
        const reasonLabel = POINT_REASON_LABELS[log.reason] || log.reason;
        return {
          id: log.id,
          title: `${reasonLabel} ${isPositive ? "+" : ""}${log.change} คะแนน`,
          subtitle: log.note || "—",
          createdAt: log.created_at || null,
          time: formatRelativeTime(log.created_at, notifNow),
          fullTime: formatFullTime(log.created_at),
          color: isPositive ? "#16a34a" : "#dc2626",
          iconText: isPositive ? "+" : "-",
          unread: log.id > lastSeenLogId,
        };
      }),
    [pointLogs, lastSeenLogId, notifNow],
  );

  const notificationGroups = useMemo(
    () => groupNotifications(notifications, { now: notifNow }),
    [notifications, notifNow],
  );

  const handleLogoutAction = () => {
    handleCloseUserMenu();
    logout();
    navigate("/");
  };

  return (
    <div className="app-layout">
      {isSidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setIsSidebarOpen(false)}
        ></div>
      )}

      <div className={`sidebar ${isSidebarOpen ? "open" : ""}`}>
        <div className="sidebar-logo">
          <Computer sx={{ fontSize: 40, color: "#1877f2" }} />
          <div>
            <Typography variant="h6" fontWeight="bold" lineHeight={1.2}>
              Smart Lab
            </Typography>
            <Typography variant="caption" color="textSecondary">
              Reserve Lab to use
            </Typography>
          </div>
        </div>

        <div className="sidebar-menu">
          <div className="menu-item" onClick={() => navigate("/booking")}>
            <EventNote /> Lab Reserve
          </div>
          <div
            className="menu-item active"
            onClick={() => setIsSidebarOpen(false)}
          >
            <Assignment /> Reserved
          </div>
          <div className="menu-item" onClick={() => navigate("/history")}>
            <History /> History
          </div>
        </div>

        <div
          className="sidebar-menu"
          style={{ flex: "none", paddingBottom: "24px" }}
        >
          <div className="menu-item">
            <SupportAgent /> Support
          </div>
        </div>
      </div>

      <div className="main-area">
        <div className="top-header">
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconButton
              sx={{ display: { xs: "block", md: "none" }, color: "#111827" }}
              onClick={() => setIsSidebarOpen(true)}
            >
              <MenuIcon />
            </IconButton>
            <Typography
              variant="h5"
              fontWeight="800"
              color="#111827"
              sx={{ display: { xs: "none", sm: "block" } }}
            >
              My Reservations
            </Typography>
          </Box>

          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: { xs: 1, sm: 3 },
            }}
          >
            <IconButton onClick={handleNotifClick}>
              <Badge
                variant="dot"
                color="error"
                overlap="circular"
                invisible={!notifications.some((n) => n.unread)}
              >
                <Notifications sx={{ color: "#111827" }} />
              </Badge>
            </IconButton>

            {/* Notification Popover */}
            <Popover
              anchorEl={notifAnchorEl}
              open={openNotifMenu}
              onClose={handleCloseNotifMenu}
              anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
              transformOrigin={{ vertical: "top", horizontal: "right" }}
              PaperProps={{
                sx: {
                  mt: 1.5,
                  width: 380,
                  maxWidth: "92vw",
                  maxHeight: 520,
                  borderRadius: 3,
                  bgcolor: "#FFFFFF",
                  color: "#0f172a",
                  boxShadow: "0 20px 45px rgba(15,23,42,0.35)",
                  overflow: "hidden",
                  display: "flex",
                  flexDirection: "column",
                },
              }}
            >
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  px: 2.5,
                  py: 2,
                  flexShrink: 0,
                }}
              >
                <Typography fontSize="16px" fontWeight="700">
                  การแจ้งเตือน
                </Typography>
                {notifications.some((n) => n.unread) && (
                  <Chip
                    size="small"
                    label={`ใหม่ ${notifications.filter((n) => n.unread).length}`}
                    sx={{
                      bgcolor: "#2563eb",
                      color: "#fff",
                      fontSize: 11,
                      height: 22,
                    }}
                  />
                )}
              </Box>

              <Box sx={{ overflowY: "auto", px: 1, pb: 1 }}>
                {notificationGroups.length === 0 ? (
                  <Box sx={{ py: 4, textAlign: "center" }}>
                    <Typography fontSize="13px" sx={{ color: "#64748b" }}>
                      ยังไม่มีการแจ้งเตือน
                    </Typography>
                  </Box>
                ) : (
                  notificationGroups.map((group, groupIndex) => (
                    <Box key={group.key} sx={{ pb: 0.5 }}>
                      {groupIndex > 0 && (
                        <Divider sx={{ my: 1, borderColor: "#e2e8f0" }} />
                      )}

                      <Box
                        sx={{
                          position: "sticky",
                          top: 0,
                          zIndex: 1,
                          bgcolor: "#FFFFFF",
                          px: 1.5,
                          pt: 1,
                          pb: 0.75,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 1,
                        }}
                      >
                        <Typography
                          fontSize="13px"
                          fontWeight="700"
                          sx={{ color: "#0f172a" }}
                        >
                          {group.label}
                        </Typography>
                        {group.key === "today" && (
                          <Typography
                            fontSize="11.5px"
                            sx={{ color: "#94a3b8" }}
                          >
                            {group.items.length} รายการ
                          </Typography>
                        )}
                      </Box>

                      {group.items.map((n) => (
                        <Box
                          key={n.id}
                          title={n.fullTime}
                          sx={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 1.5,
                            px: 1.5,
                            py: 1,
                            borderRadius: 2,
                            cursor: "pointer",
                            bgcolor: n.unread
                              ? "rgba(37, 99, 235, 0.06)"
                              : "transparent",
                            "&:hover": { bgcolor: "rgba(0, 0, 0, 0.04)" },
                          }}
                        >
                          <Box sx={{ pt: 1.2 }}>
                            {n.unread ? (
                              <Box
                                sx={{
                                  width: 8,
                                  height: 8,
                                  borderRadius: "50%",
                                  bgcolor: "#2563eb",
                                }}
                              />
                            ) : (
                              <Box sx={{ width: 8, height: 8 }} />
                            )}
                          </Box>

                          <Avatar
                            sx={{
                              bgcolor: n.color,
                              width: 36,
                              height: 36,
                              fontSize: 14,
                            }}
                          >
                            {n.iconText}
                          </Avatar>

                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography
                              fontSize="13.5px"
                              fontWeight="600"
                              sx={{
                                color: "#1e293b",
                                display: "-webkit-box",
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden",
                              }}
                            >
                              {n.title}
                            </Typography>
                            <Typography
                              fontSize="12px"
                              sx={{ color: "#475569", mt: 0.3 }}
                            >
                              {n.subtitle}
                            </Typography>
                            <Typography
                              fontSize="12px"
                              sx={{ color: "#64748b", mt: 0.3 }}
                            >
                              {n.time}
                            </Typography>
                          </Box>
                        </Box>
                      ))}
                    </Box>
                  ))
                )}
              </Box>
            </Popover>

            {currentUser ? (
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.5,
                  borderLeft: "1px solid #e2e8f0",
                  pl: { xs: 1, sm: 3 },
                }}
              >
                {/* ข้อความชื่อผู้ใช้ */}
                <Box
                  className="profile-text-container"
                  sx={{ textAlign: "right" }}
                >
                  <Typography
                    variant="subtitle2"
                    fontWeight="bold"
                    lineHeight={1.2}
                  >
                    {currentUser.name}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {currentUser.role}
                  </Typography>
                </Box>

                {/* ปุ่ม Avatar สำหรับกดเปิด Popover */}
                <IconButton
                  onClick={handleAvatarClick}
                  sx={{ p: 0.5, "&:hover": { bgcolor: "#f1f5f9" } }}
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

                {/* Popover Card */}
                <Popover
                  anchorEl={anchorEl}
                  open={openUserMenu}
                  onClose={handleCloseUserMenu}
                  anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                  transformOrigin={{ vertical: "top", horizontal: "right" }}
                  PaperProps={{
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
                  {/* Header: อีเมล + ปุ่มปิด */}
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
                      fontWeight="600"
                      color="#64748b"
                      sx={{ pl: 0.5 }}
                    >
                      {currentUser.email}
                    </Typography>
                    <IconButton size="small" onClick={handleCloseUserMenu}>
                      <Close sx={{ fontSize: 18, color: "#64748b" }} />
                    </IconButton>
                  </Box>

                  {/* Profile Main Body */}
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
                      fontWeight="700"
                      fontSize="18px"
                    >
                      Hi, {currentUser.name}
                    </Typography>

                    <Button
                      variant="outlined"
                      onClick={() => {
                        handleCloseUserMenu();
                        navigate("/profile");
                      }}
                      sx={{
                        mt: 2,
                        borderRadius: 20,
                        textTransform: "none",
                        fontWeight: "700",
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
                      Manage your Account
                    </Button>
                  </Box>

                  <Divider />

                  {/* Menu Action List */}
                  <Box sx={{ px: 1, py: 1 }}>
                    <Box
                      onClick={handleLogoutAction}
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
                      <Logout sx={{ fontSize: 20, color: "#ef4444" }} />
                      <Typography
                        fontSize="13px"
                        fontWeight="700"
                        color="#ef4444"
                      >
                        Log out
                      </Typography>
                    </Box>
                  </Box>
                </Popover>
              </Box>
            ) : (
              /* กรณี Guest User (กดแล้วพาไปหน้า Login) */
              <Box
                onClick={() => navigate("/")}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1.5,
                  borderLeft: "1px solid #e2e8f0",
                  pl: { xs: 1, sm: 3 },
                  cursor: "pointer",
                  transition: "0.2s",
                  "&:hover": { opacity: 0.7 },
                }}
              >
                <Box
                  className="profile-text-container"
                  sx={{ textAlign: "right" }}
                >
                  <Typography
                    variant="subtitle2"
                    fontWeight="bold"
                    lineHeight={1.2}
                    color="textSecondary"
                  >
                    Guest User
                  </Typography>
                  <Typography variant="caption" color="primary.main">
                    Click to Log in
                  </Typography>
                </Box>
                <Avatar sx={{ bgcolor: "#cbd5e1", width: 36, height: 36 }}>
                  <Person sx={{ color: "#64748b" }} />
                </Avatar>
              </Box>
            )}
          </Box>
        </div>

        <div className="content-area">
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", mt: 10 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Paper
              elevation={0}
              sx={{
                p: { xs: 2, sm: 4 },
                border: "1px solid #e2e8f0",
                borderRadius: 4,
                maxWidth: "900px",
                mx: "auto",
                bgcolor: "white",
                boxShadow: "0 4px 12px rgba(0,0,0,0.05)",
              }}
            >
              <Typography
                variant="h6"
                fontWeight="700"
                color="#0f172a"
                sx={{ mb: 3 }}
              >
                Reserved Status
              </Typography>

              {bookings.length > 0 ? (
                <TableContainer>
                  <Table sx={{ minWidth: 600 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell
                          sx={{
                            fontWeight: "bold",
                            borderBottom: "1px solid #e2e8f0",
                            color: "#0f172a",
                          }}
                        >
                          #ID
                        </TableCell>
                        <TableCell
                          sx={{
                            fontWeight: "bold",
                            borderBottom: "1px solid #e2e8f0",
                            color: "#0f172a",
                          }}
                        >
                          Room
                        </TableCell>
                        <TableCell
                          sx={{
                            fontWeight: "bold",
                            borderBottom: "1px solid #e2e8f0",
                            color: "#0f172a",
                          }}
                        >
                          Date
                        </TableCell>
                        <TableCell
                          sx={{
                            fontWeight: "bold",
                            borderBottom: "1px solid #e2e8f0",
                            color: "#0f172a",
                          }}
                        >
                          Time
                        </TableCell>
                        <TableCell
                          sx={{ borderBottom: "1px solid #e2e8f0" }}
                        ></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {bookings.map((row) => (
                        <TableRow
                          key={row.id}
                          sx={{
                            "&:last-child td, &:last-child th": { border: 0 },
                          }}
                        >
                          <TableCell sx={{ color: "#64748b" }}>
                            {row.id.toString().padStart(4, "0")}
                          </TableCell>
                          <TableCell sx={{ color: "#475569" }}>
                            {row.lab_code}
                          </TableCell>
                          <TableCell sx={{ color: "#475569" }}>
                            {formatDate(row.booking_date)}
                          </TableCell>
                          <TableCell sx={{ color: "#475569" }}>
                            {row.start_time} - {row.end_time}
                            <Typography
                              variant="caption"
                              display="block"
                              color="#94a3b8"
                            >
                              {!row.status || row.status === "reserved"
                                ? "รอยืนยันการเข้าใช้งาน"
                                : row.status === "attended"
                                  ? "กำลังใช้งาน"
                                  : row.status === "completed"
                                    ? "ใช้งานเสร็จแล้ว"
                                    : row.status === "no_show"
                                      ? "ไม่มาตามการจอง"
                                      : "ยกเลิกแล้ว"}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            {!row.status || row.status === "reserved" ? (
                              <IconButton
                                size="small"
                                onClick={() => handleOpenCancelDialog(row.id)}
                                sx={{
                                  color: "#ef4444",
                                  transition: "0.2s",
                                  "&:hover": {
                                    color: "#dc2626",
                                    transform: "scale(1.1)",
                                  },
                                }}
                              >
                                <CancelIcon />
                              </IconButton>
                            ) : (
                              <Chip
                                label={
                                  row.status === "no_show"
                                    ? "No-show"
                                    : "Closed"
                                }
                                size="small"
                                variant="outlined"
                              />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Box
                  sx={{
                    py: 6,
                    textAlign: "center",
                    bgcolor: "#f8fafc",
                    borderRadius: 3,
                  }}
                >
                  <Typography variant="body1" color="textSecondary">
                    No upcoming reservations found.
                  </Typography>
                </Box>
              )}
            </Paper>
          )}
        </div>
      </div>

      <Dialog
        open={cancelDialogOpen}
        onClose={handleCloseCancelDialog}
        PaperProps={{ sx: { borderRadius: 3, p: 1, minWidth: "350px" } }}
      >
        <DialogTitle sx={{ fontWeight: "bold", color: "#0f172a" }}>
          Cancel Reservation
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ color: "#475569" }}>
            Are you sure you want to cancel this booking? This action cannot be
            undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={handleCloseCancelDialog}
            sx={{ color: "#64748b", fontWeight: "bold", textTransform: "none" }}
          >
            Keep it
          </Button>
          <Button
            onClick={handleConfirmCancel}
            variant="contained"
            sx={{
              bgcolor: "#ef4444",
              color: "white",
              fontWeight: "bold",
              textTransform: "none",
              boxShadow: "none",
              "&:hover": { bgcolor: "#dc2626", boxShadow: "none" },
            }}
          >
            Yes, Cancel
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
