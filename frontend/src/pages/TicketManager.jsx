import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Avatar,
  IconButton,
  Paper,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  InputBase,
  Fade,
  Chip,
  Popover,
  CircularProgress,
} from "@mui/material";
import {
  Search,
  Notifications,
  ConfirmationNumber,
  Logout,
  Computer,
  Person,
  Dashboard as DashIcon,
  MeetingRoom,
  HowToReg,
  Assessment,
  Block,
  Settings,
  Close,
  CheckCircle,
} from "@mui/icons-material";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/auth-context";

const API_URL = import.meta.env.VITE_API_URL;

const SIDE_MENU_ITEMS = [
  { text: "Dashboard", icon: <DashIcon sx={{ fontSize: 20 }} />, path: "/admin" },
  { text: "Manage Labs", icon: <MeetingRoom sx={{ fontSize: 20 }} />, path: "/manage-labs" },
  { text: "Verify Users", icon: <HowToReg sx={{ fontSize: 20 }} />, path: "/verify-users" },
  { text: "User Points", icon: <Assessment sx={{ fontSize: 20 }} />, path: "/admin/points" },
  { text: "Point Criteria", icon: <Settings sx={{ fontSize: 20 }} />, path: "/admin/points/policy" },
  { text: "Blacklist", icon: <Block sx={{ fontSize: 20 }} />, path: "/blacklist" },
  { text: "Ticket", icon: <ConfirmationNumber sx={{ fontSize: 20 }} />, path: "/ticket" },
];

export default function TicketManager() {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout } = useAuth();

  // --- User menu (avatar dropdown) — เหมือนหน้า Blacklist ---
  const [anchorEl, setAnchorEl] = useState(null);
  const openUserMenu = Boolean(anchorEl);
  const handleAvatarClick = (e) => setAnchorEl(e.currentTarget);
  const handleCloseUserMenu = () => setAnchorEl(null);
  const handleLogout = () => {
    handleCloseUserMenu();
    logout();
    navigate("/");
  };

  // --- Ticket data ---
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTicket, setSelectedTicket] = useState(null); // ticket ที่กำลังดูรายละเอียดใน popup

  useEffect(() => {
    document.title = "Ticket Manager | Smart Lab Admin";
    fetchTickets();
  }, []);

  const fetchTickets = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/tickets`);
      setTickets(response.data?.data || []);
    } catch (error) {
      console.error("[TicketManager] Failed to fetch tickets:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleCloseTicket = async (ticketId) => {
    try {
      await axios.patch(`${API_URL}/admin/tickets/${ticketId}`, { status: "closed" });
      setTickets(tickets.map((t) => (t.id === ticketId ? { ...t, status: "closed" } : t)));
      setSelectedTicket((prev) => (prev && prev.id === ticketId ? { ...prev, status: "closed" } : prev));
    } catch (error) {
      console.error("Failed to close ticket:", error);
      alert("เกิดข้อผิดพลาดในการอัปเดตสถานะ");
    }
  };

  const handleRowClick = (ticket) => setSelectedTicket(ticket);
  const handleCloseDialog = () => setSelectedTicket(null);

  const getUserName = (ticket) =>
    ticket.user ? `${ticket.user.first_name} ${ticket.user.last_name}` : `User #${ticket.user_id}`;

  const filtered = tickets.filter(
    (t) =>
      t.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (t.message || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
      getUserName(t).toLowerCase().includes(searchQuery.toLowerCase()),
  );

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "#fcfdfe", fontFamily: "'Inter', sans-serif" }}>
      {/* SIDEBAR */}
      <Box
        sx={{
          width: "240px",
          bgcolor: "#f0f7ff",
          borderRight: "1px solid #e2efff",
          display: "flex",
          flexDirection: "column",
          position: "sticky",
          top: 0,
          height: "100vh",
          zIndex: 10,
        }}
      >
        <Box sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}>
          <Box
            sx={{
              bgcolor: "#000",
              p: 1,
              borderRadius: 2.5,
              display: "flex",
              boxShadow: "0 4px 10px rgba(0,0,0,0.2)",
            }}
          >
            <Computer sx={{ color: "white", fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h6" fontWeight="800" sx={{ color: "#0f172a", letterSpacing: "-0.5px" }}>
              Smart Lab
            </Typography>
            <Typography variant="caption" sx={{ color: "#64748b", fontWeight: "500", display: "block", mt: -0.5 }}>
              Admin Dashboard
            </Typography>
          </Box>
        </Box>

        <Box sx={{ px: 2, mt: 4 }}>
          {SIDE_MENU_ITEMS.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Button
                key={item.text}
                fullWidth
                onClick={() => navigate(item.path)}
                startIcon={item.icon}
                sx={{
                  justifyContent: "flex-start",
                  py: 1,
                  px: 2.5,
                  mb: 0.5,
                  bgcolor: isActive ? "white" : "transparent",
                  color: isActive ? "#3b82f6" : "#94a3b8",
                  fontWeight: isActive ? "700" : "600",
                  boxShadow: isActive ? "0 10px 25px rgba(0,0,0,0.03)" : "none",
                  borderRadius: 4,
                  textTransform: "none",
                  transition: "0.3s",
                  "&:hover": {
                    bgcolor: isActive ? "white" : "transparent",
                    color: isActive ? "#3b82f6" : "#64748b",
                    transform: "translateX(5px)",
                  },
                }}
              >
                {item.text}
              </Button>
            );
          })}
        </Box>
      </Box>

      {/* MAIN AREA */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflowX: "hidden" }}>
        {/* HEADER */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 6,
            py: 1,
            bgcolor: "white",
            borderBottom: "1px solid #e2e8f0",
            zIndex: 5,
          }}
        >
          <Typography variant="h5" fontWeight="800" sx={{ color: "#1e293b", letterSpacing: "-1px" }}>
            Ticket Manager
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Paper
              elevation={0}
              sx={{
                bgcolor: "#f1f5f9",
                px: 2,
                py: 0.5,
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                width: 400,
                height: 44,
              }}
            >
              <Search sx={{ color: "#94a3b8", mr: 1.5 }} />
              <InputBase
                placeholder="Search tickets by user, subject, message..."
                fullWidth
                sx={{ fontSize: "15px", fontWeight: "500" }}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </Paper>
            <IconButton sx={{ bgcolor: "#f8fafc" }}>
              <Notifications sx={{ color: "#64748b" }} />
            </IconButton>
            <Divider orientation="vertical" flexItem sx={{ height: 30, my: "auto", bgcolor: "#e2e8f0" }} />
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box sx={{ textAlign: "right" }}>
                <Typography variant="subtitle2" fontWeight="800" color="#1e293b">
                  System Admin
                </Typography>
                <Typography variant="caption" fontWeight="600" color="#94a3b8">
                  Administrator
                </Typography>
              </Box>
              <IconButton onClick={handleAvatarClick} sx={{ p: 0.8, "&:hover": { bgcolor: "#f1f5f9" } }}>
                <Avatar sx={{ bgcolor: "#0f172a", width: 36, height: 36, boxShadow: "0 4px 10px rgba(0,0,0,0.1)" }}>
                  <Person sx={{ fontSize: 20 }} />
                </Avatar>
              </IconButton>

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
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5 }}>
                  <Typography fontSize="13px" fontWeight="600" color="#64748b" sx={{ pl: 0.5 }}>
                    admin@smartlab.ac.th
                  </Typography>
                  <IconButton size="small" onClick={handleCloseUserMenu}>
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
                      boxShadow: "0 0 0 4px #eff6ff, 0 8px 20px rgba(59,130,246,0.25)",
                    }}
                  >
                    <Person sx={{ fontSize: 40 }} />
                  </Avatar>

                  <Typography sx={{ mt: 1.5, color: "#1e293b" }} fontWeight="700" fontSize="18px">
                    Hi, System Admin
                  </Typography>

                  <Button
                    variant="outlined"
                    onClick={handleCloseUserMenu}
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
                      "&:hover": { borderColor: "#3b82f6", bgcolor: "#eff6ff" },
                    }}
                  >
                    Manage your Account
                  </Button>
                </Box>

                <Divider />

                <Box sx={{ px: 1, py: 1 }}>
                  <Box
                    onClick={handleCloseUserMenu}
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
          </Box>
        </Box>

        {/* CONTENT */}
        <Box sx={{ p: 6, flex: 1 }}>
          <Fade in timeout={400}>
            <Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 5 }}>
                <Typography variant="h6" fontWeight="700" color="#64748b">
                  {tickets.length} ticket{tickets.length !== 1 ? "s" : ""} total
                </Typography>
              </Box>

              <Paper
                elevation={0}
                sx={{
                  borderRadius: 6,
                  border: "1px solid #e2e8f0",
                  overflow: "hidden",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.02)",
                }}
              >
                <Box
                  sx={{
                    px: 5,
                    py: 3.5,
                    borderBottom: "1px solid #f1f5f9",
                    display: "flex",
                    alignItems: "center",
                    gap: 2,
                  }}
                >
                  <ConfirmationNumber sx={{ color: "#3b82f6", fontSize: 22 }} />
                  <Typography variant="h6" fontWeight="800" color="#1e293b">
                    Support Tickets
                  </Typography>
                </Box>

                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow sx={{ bgcolor: "#f8fafc" }}>
                        {["ผู้ส่ง (User)", "หัวข้อ", "รายละเอียด", "วันที่", "สถานะ", "จัดการ"].map((h, i) => (
                          <TableCell
                            key={h}
                            align={i === 5 ? "center" : "left"}
                            sx={{ color: "#64748b", fontWeight: "800", py: 2, borderBottom: "1px solid #e2e8f0" }}
                          >
                            {h}
                          </TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {loading ? (
                        <TableRow>
                          <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                            <CircularProgress size={28} />
                          </TableCell>
                        </TableRow>
                      ) : filtered.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} align="center" sx={{ py: 6, color: "#94a3b8", fontWeight: "600" }}>
                            {searchQuery ? `No results for "${searchQuery}"` : "ไม่มีคำร้องขอความช่วยเหลือในขณะนี้"}
                          </TableCell>
                        </TableRow>
                      ) : (
                        filtered.map((ticket) => (
                          <TableRow
                            key={ticket.id}
                            onClick={() => handleRowClick(ticket)}
                            sx={{
                              cursor: "pointer",
                              "& td": { borderBottom: "1px solid #f1f5f9" },
                              "&:hover": { bgcolor: "#fafafa" },
                            }}
                          >
                            <TableCell sx={{ fontWeight: "700", color: "#334155" }}>{getUserName(ticket)}</TableCell>
                            <TableCell sx={{ fontWeight: "600", color: "#1e293b" }}>{ticket.subject}</TableCell>
                            <TableCell
                              sx={{
                                color: "#64748b",
                                maxWidth: 260,
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {ticket.message}
                            </TableCell>
                            <TableCell sx={{ color: "#94a3b8", fontWeight: "600", whiteSpace: "nowrap" }}>
                              {ticket.created_at ? new Date(ticket.created_at).toLocaleString("th-TH") : "-"}
                            </TableCell>
                            <TableCell>
                              <Chip
                                label={ticket.status === "open" ? "รอแก้ไข" : "ปิดแล้ว"}
                                size="small"
                                sx={{
                                  bgcolor: ticket.status === "open" ? "#fff7ed" : "#f0fdf4",
                                  color: ticket.status === "open" ? "#d97706" : "#16a34a",
                                  fontWeight: "700",
                                }}
                              />
                            </TableCell>
                            <TableCell align="center">
                              {ticket.status === "open" ? (
                                <Button
                                  variant="contained"
                                  color="success"
                                  size="small"
                                  startIcon={<CheckCircle />}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleCloseTicket(ticket.id);
                                  }}
                                  sx={{ textTransform: "none", borderRadius: 2, boxShadow: "none" }}
                                >
                                  Mark as Closed
                                </Button>
                              ) : (
                                <Typography variant="caption" sx={{ color: "#94a3b8", fontWeight: "bold" }}>
                                  Resolved
                                </Typography>
                              )}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            </Box>
          </Fade>
        </Box>
      </Box>

      {/* DIALOG: Ticket detail popup */}
      <Dialog open={!!selectedTicket} onClose={handleCloseDialog} fullWidth maxWidth="sm">
        {selectedTicket && (
          <>
            <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Typography variant="h6" fontWeight="800">
                รายละเอียดคำร้อง #{selectedTicket.id}
              </Typography>
              <IconButton onClick={handleCloseDialog}>
                <Close />
              </IconButton>
            </DialogTitle>
            <DialogContent dividers>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between" }}>
                  <Box>
                    <Typography variant="caption" color="#94a3b8" fontWeight="bold">
                      ผู้ส่ง (User)
                    </Typography>
                    <Typography variant="body2" color="#475569">
                      {getUserName(selectedTicket)}
                    </Typography>
                  </Box>
                  <Box sx={{ textAlign: "right" }}>
                    <Typography variant="caption" color="#94a3b8" fontWeight="bold" sx={{ display: "block" }}>
                      สถานะ
                    </Typography>
                    <Chip
                      label={selectedTicket.status === "open" ? "รอแก้ไข" : "ปิดแล้ว"}
                      size="small"
                      sx={{
                        mt: 0.5,
                        fontWeight: "bold",
                        bgcolor: selectedTicket.status === "open" ? "#fff7ed" : "#f0fdf4",
                        color: selectedTicket.status === "open" ? "#d97706" : "#16a34a",
                      }}
                    />
                  </Box>
                </Box>

                <Divider />

                <Box>
                  <Typography variant="caption" color="#94a3b8" fontWeight="bold">
                    หัวข้อ
                  </Typography>
                  <Typography variant="body1" fontWeight="700" color="#334155">
                    {selectedTicket.subject}
                  </Typography>
                </Box>

                <Divider />

                <Box>
                  <Typography variant="caption" color="#94a3b8" fontWeight="bold">
                    รายละเอียด
                  </Typography>
                  <Typography variant="body2" color="#475569" sx={{ whiteSpace: "pre-wrap", mt: 0.5 }}>
                    {selectedTicket.message}
                  </Typography>
                </Box>

                <Divider />

                <Box>
                  <Typography variant="caption" color="#94a3b8" fontWeight="bold">
                    วันที่ส่ง
                  </Typography>
                  <Typography variant="body2" color="#475569">
                    {selectedTicket.created_at ? new Date(selectedTicket.created_at).toLocaleString("th-TH") : "-"}
                  </Typography>
                </Box>
              </Box>
            </DialogContent>
            <DialogActions>
              {selectedTicket.status === "open" && (
                <Button
                  onClick={() => handleCloseTicket(selectedTicket.id)}
                  variant="contained"
                  color="success"
                  startIcon={<CheckCircle />}
                  sx={{ textTransform: "none", borderRadius: 2, boxShadow: "none" }}
                >
                  Mark as Closed
                </Button>
              )}
              <Button onClick={handleCloseDialog} variant="outlined" sx={{ textTransform: "none", borderRadius: 2 }}>
                ปิดหน้าต่าง
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  );
}