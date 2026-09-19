import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  Paper,
  Popover,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
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
  Notifications,
  Person,
  Settings,
  SupportAgent,
} from "@mui/icons-material";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/auth-context";
import SupportModal from "./SupportModal";

const API_URL = import.meta.env.VITE_API_URL;

const STATUS_LABELS = {
  open: { label: "รอดำเนินการ", color: "warning" },
  in_progress: { label: "กำลังดำเนินการ", color: "info" },
  closed: { label: "ดำเนินการเสร็จสิ้น", color: "success" },
};

const MENU_ITEMS = [
  { label: "Lab Reserve", icon: <EventNote />, path: "/booking" },
  { label: "Reserved", icon: <Assignment />, path: "/reserved" },
  { label: "History", icon: <HistoryIcon />, path: "/history" },
  {
    label: "My Tickets",
    icon: <ConfirmationNumber />,
    path: "/my-tickets",
  },
];

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
  });
};

export default function MyTickets() {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser, logout } = useAuth();

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchMyTickets = useCallback(async () => {
    if (!currentUser) return;

    try {
      setLoading(true);
      setError("");
      const token = localStorage.getItem("access_token");
      const response = await axios.get(`${API_URL}/tickets/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTickets(response.data?.data || []);
    } catch (requestError) {
      setError(
        requestError.response?.data?.detail ||
          "ไม่สามารถโหลดคำร้องของคุณได้",
      );
    } finally {
      setLoading(false);
    }
  }, [currentUser]);

  useEffect(() => {
    document.title = "My Tickets | Smart Lab";
    if (!currentUser) {
      navigate("/");
      return;
    }
    fetchMyTickets();
  }, [currentUser, fetchMyTickets, navigate]);

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
    <div className="app-layout">
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
            <Typography variant="h6" fontWeight="bold" lineHeight={1.2}>
              Smart Lab
            </Typography>
            <Typography variant="caption" color="textSecondary">
              Reserve Lab to use
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
              {item.icon} {item.label}
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
              aria-label="Open navigation"
            >
              <MenuIcon />
            </IconButton>
            <Typography
              variant="h5"
              fontWeight="800"
              color="#111827"
              sx={{ display: { xs: "none", sm: "block" } }}
            >
              My Tickets
            </Typography>
          </Box>

          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: { xs: 1, sm: 3 },
            }}
          >
            <IconButton aria-label="Notifications">
              <Notifications sx={{ color: "#111827" }} />
            </IconButton>
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
                    fontWeight="bold"
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
                  aria-label="Open user menu"
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
                      fontWeight="600"
                      color="#64748b"
                      noWrap
                    >
                      {currentUser.email}
                    </Typography>
                    <IconButton
                      size="small"
                      onClick={() => setAnchorEl(null)}
                      aria-label="Close user menu"
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
                      fontWeight="700"
                      fontSize="18px"
                    >
                      Hi, {currentUser.name}
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
                  <Box sx={{ px: 1, py: 1 }}>
                    <Box
                      onClick={() => {
                        setAnchorEl(null);
                        navigate("/profile");
                      }}
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1.5,
                        px: 1.5,
                        py: 1,
                        borderRadius: 2,
                        cursor: "pointer",
                        "&:hover": { bgcolor: "#f8fafc" },
                      }}
                    >
                      <Settings sx={{ fontSize: 20, color: "#64748b" }} />
                      <Typography fontSize="13px" fontWeight="700" color="#1e293b">
                        Setting
                      </Typography>
                    </Box>
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
                      <Logout sx={{ fontSize: 20, color: "#ef4444" }} />
                      <Typography fontSize="13px" fontWeight="700" color="#ef4444">
                        Log out
                      </Typography>
                    </Box>
                  </Box>
                </Popover>
              </Box>
            )}
          </Box>
        </div>

        <div className="content-area">
          <Box sx={{ maxWidth: 1100, mx: "auto" }}>
            <Box
              sx={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: { xs: "flex-start", sm: "center" },
                gap: 2,
                mb: 3,
                flexWrap: "wrap",
              }}
            >
              <Box>
                <Typography variant="h4" fontWeight="800" color="#1e293b">
                  คำร้องของฉัน
                </Typography>
                <Typography variant="body2" color="#64748b" sx={{ mt: 0.75 }}>
                  ติดตามสถานะคำร้องที่ส่งถึงผู้ดูแลระบบ
                </Typography>
              </Box>
              <Chip
                icon={<ConfirmationNumber />}
                label={`${tickets.length} คำร้อง`}
                sx={{
                  bgcolor: "#eff6ff",
                  color: "#2563eb",
                  fontWeight: "800",
                  borderRadius: 2.5,
                  "& .MuiChip-icon": { color: "inherit" },
                }}
              />
            </Box>

            {error && (
              <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>
                {error}
              </Alert>
            )}

            {loading ? (
              <Paper
                elevation={0}
                sx={{
                  minHeight: 320,
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                  borderRadius: 4,
                  border: "1px solid #e2e8f0",
                }}
              >
                <CircularProgress />
              </Paper>
            ) : (
              <Paper
                elevation={0}
                sx={{
                  p: { xs: 2, sm: 3 },
                  border: "1px solid #e2e8f0",
                  borderRadius: 4,
                  bgcolor: "white",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.05)",
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 2,
                    mb: 2,
                  }}
                >
                  <Box>
                    <Typography variant="h6" fontWeight="800" color="#0f172a">
                      ประวัติคำร้อง
                    </Typography>
                    <Typography variant="body2" color="#94a3b8">
                      รายการสนทนาและการติดตามปัญหาของคุณ
                    </Typography>
                  </Box>
                  <Chip
                    label="Support"
                    size="small"
                    sx={{
                      bgcolor: "#f8fafc",
                      color: "#64748b",
                      fontWeight: "700",
                    }}
                  />
                </Box>

                {tickets.length === 0 ? (
                  <Box
                    sx={{
                      py: 8,
                      textAlign: "center",
                      bgcolor: "#f8fafc",
                      borderRadius: 3,
                    }}
                  >
                    <ConfirmationNumber
                      sx={{ fontSize: 52, color: "#cbd5e1", mb: 1 }}
                    />
                    <Typography variant="body1" color="#64748b" fontWeight="700">
                      คุณยังไม่เคยส่งคำร้อง
                    </Typography>
                    <Typography variant="body2" color="#94a3b8" sx={{ mt: 0.5 }}>
                      หากพบปัญหา สามารถกด Support จากเมนูด้านซ้ายได้
                    </Typography>
                  </Box>
                ) : (
                  <TableContainer>
                    <Table sx={{ minWidth: 760 }}>
                      <TableHead>
                        <TableRow sx={{ bgcolor: "#f8fafc" }}>
                          <TableCell sx={{ fontWeight: "800", color: "#64748b" }}>
                            หัวข้อ
                          </TableCell>
                          <TableCell sx={{ fontWeight: "800", color: "#64748b" }}>
                            รายละเอียด
                          </TableCell>
                          <TableCell sx={{ fontWeight: "800", color: "#64748b" }}>
                            วันที่ส่ง
                          </TableCell>
                          <TableCell sx={{ fontWeight: "800", color: "#64748b" }}>
                            สถานะ
                          </TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {tickets.map((ticket) => {
                          const status = STATUS_LABELS[ticket.status] || {
                            label: ticket.status || "ไม่ทราบสถานะ",
                            color: "default",
                          };

                          return (
                            <TableRow key={ticket.id} hover>
                              <TableCell
                                sx={{
                                  minWidth: 180,
                                  maxWidth: 240,
                                  fontWeight: "700",
                                  color: "#334155",
                                  wordBreak: "break-word",
                                }}
                              >
                                {ticket.subject}
                              </TableCell>
                              <TableCell
                                sx={{
                                  minWidth: 260,
                                  maxWidth: 420,
                                  color: "#475569",
                                  whiteSpace: "pre-wrap",
                                  wordBreak: "break-word",
                                }}
                              >
                                {ticket.message}
                              </TableCell>
                              <TableCell
                                sx={{
                                  minWidth: 170,
                                  color: "#475569",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {formatDate(ticket.created_at)}
                              </TableCell>
                              <TableCell sx={{ minWidth: 150 }}>
                                <Chip
                                  label={status.label}
                                  color={status.color}
                                  size="small"
                                  sx={{ fontWeight: "800" }}
                                />
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </TableContainer>
                )}
              </Paper>
            )}
          </Box>
        </div>
      </div>

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
