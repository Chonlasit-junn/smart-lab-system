import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  IconButton,
  InputBase,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Popover,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import {
  Assessment,
  Block,
  CheckCircle,
  Close,
  Computer,
  ConfirmationNumber,
  Dashboard as DashIcon,
  Group,
  HowToReg,
  Lock,
  Logout,
  MeetingRoom,
  Notifications,
  Person,
  Refresh,
  Search,
  Settings,
  WarningAmber,
} from "@mui/icons-material";
import { useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/auth-context";

const API_URL = import.meta.env.VITE_API_URL;
const DEFAULT_BOOKING_MIN_POINTS = 80;

const SIDE_MENU_ITEMS = [
  {
    text: "Dashboard",
    icon: <DashIcon sx={{ fontSize: 20 }} />,
    path: "/admin",
  },
  {
    text: "Manage Labs",
    icon: <MeetingRoom sx={{ fontSize: 20 }} />,
    path: "/manage-labs",
  },
  {
    text: "Verify Users",
    icon: <HowToReg sx={{ fontSize: 20 }} />,
    path: "/verify-users",
  },
  {
    text: "User Points",
    icon: <Assessment sx={{ fontSize: 20 }} />,
    path: "/admin/points",
  },
  {
    text: "Blacklist",
    icon: <Block sx={{ fontSize: 20 }} />,
    path: "/blacklist",
  },
  {
    text: "Ticket",
    icon: <ConfirmationNumber sx={{ fontSize: 20 }} />,
    path: "/ticket",
  },
];

const EMPTY_SUMMARY = {
  total_users: 0,
  average_points: 0,
  below_booking_threshold: 0,
  banned_users: 0,
  booking_allowed: 0,
};

const stringToColor = (value) => {
  if (!value) return "#cbd5e1";
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = value.charCodeAt(index) + ((hash << 5) - hash);
  }
  let color = "#";
  for (let index = 0; index < 3; index += 1) {
    color += `00${((hash >> (index * 8)) & 0xff).toString(16)}`.slice(-2);
  }
  return color;
};

const getInitials = (user) => {
  const initials = `${user.first_name?.[0] || ""}${user.last_name?.[0] || ""}`;
  return initials.toUpperCase() || "U";
};

const getScoreColor = (score) => {
  if (score < 40) return "#ef4444";
  if (score < DEFAULT_BOOKING_MIN_POINTS) return "#f59e0b";
  return "#10b981";
};

const formatDate = (value) => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("th-TH", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const formatDateTime = (value) => {
  if (!value) return "ยังไม่มีข้อมูล";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "ยังไม่มีข้อมูล";
  return date.toLocaleString("th-TH", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const getRoleLabel = (role) => ({
  admin: "Admin",
  student: "Student",
  guest: "Guest",
}[role] || "Guest");

const getRoleColor = (role) => ({
  admin: { bgcolor: "#f3e8ff", color: "#7e22ce" },
  student: { bgcolor: "#eff6ff", color: "#2563eb" },
  guest: { bgcolor: "#f1f5f9", color: "#64748b" },
}[role] || { bgcolor: "#f1f5f9", color: "#64748b" });

export default function AdminPoints() {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout } = useAuth();

  const [anchorEl, setAnchorEl] = useState(null);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [bookingMinPoints, setBookingMinPoints] = useState(DEFAULT_BOOKING_MIN_POINTS);
  const [scoreDate, setScoreDate] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sortBy, setSortBy] = useState("pointsAsc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchPoints = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setError("กรุณาเข้าสู่ระบบด้วยบัญชี Admin ก่อนดูคะแนนผู้ใช้");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError("");
      const response = await axios.get(`${API_URL}/admin/points`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const payload = response.data || {};
      setRows(Array.isArray(payload.data) ? payload.data : []);
      setSummary({ ...EMPTY_SUMMARY, ...(payload.summary || {}) });
      setBookingMinPoints(Number(payload.booking_min_points) || DEFAULT_BOOKING_MIN_POINTS);
      setScoreDate(payload.score_date || null);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "ไม่สามารถโหลดคะแนนของผู้ใช้ได้");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = "User Points | Smart Lab Admin";
    fetchPoints();
  }, [fetchPoints]);

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate("/");
  };

  const filteredRows = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const visibleRows = rows.filter((user) => {
      const searchableText = `${user.name || ""} ${user.email || ""} ${user.user_id || ""}`.toLowerCase();
      if (query && !searchableText.includes(query)) return false;
      if (filter === "low" && user.points >= bookingMinPoints) return false;
      if (filter === "banned" && !user.is_banned) return false;
      if (filter === "allowed" && !user.booking_allowed) return false;
      return true;
    });

    return [...visibleRows].sort((first, second) => {
      if (sortBy === "pointsDesc") return second.points - first.points;
      if (sortBy === "name") return (first.name || "").localeCompare(second.name || "");
      return first.points - second.points;
    });
  }, [bookingMinPoints, filter, rows, searchQuery, sortBy]);

  const statCards = [
    {
      label: "ผู้ใช้ทั้งหมด",
      value: summary.total_users,
      helper: "บัญชีในระบบ",
      color: "#3b82f6",
      icon: <Group />,
    },
    {
      label: "คะแนนเฉลี่ย",
      value: `${summary.average_points}/100`,
      helper: "คะแนนสะสมปัจจุบัน",
      color: "#10b981",
      icon: <Assessment />,
    },
    {
      label: "ต่ำกว่าเกณฑ์",
      value: summary.below_booking_threshold,
      helper: `ต่ำกว่า ${bookingMinPoints} คะแนน`,
      color: "#f59e0b",
      icon: <WarningAmber />,
    },
    {
      label: "ถูกระงับการจอง",
      value: summary.banned_users,
      helper: "มี Ban ที่ยังใช้งาน",
      color: "#ef4444",
      icon: <Lock />,
    },
  ];

  return (
    <Box
      sx={{
        display: "flex",
        minHeight: "100vh",
        bgcolor: "#fcfdfe",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <Box
        sx={{
          width: 240,
          bgcolor: "#f0f7ff",
          borderRight: "1px solid #e2efff",
          display: { xs: "none", md: "flex" },
          flexDirection: "column",
          position: "sticky",
          top: 0,
          height: "100vh",
          flexShrink: 0,
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
                    color: "#3b82f6",
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

      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflowX: "hidden", minWidth: 0 }}>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 2,
            px: { xs: 3, md: 6 },
            py: 1.5,
            bgcolor: "white",
            borderBottom: "1px solid #e2e8f0",
            zIndex: 5,
          }}
        >
          <Typography variant="h5" fontWeight="800" sx={{ color: "#1e293b", letterSpacing: "-1px" }}>
            User Points
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconButton sx={{ bgcolor: "#f8fafc" }} aria-label="Notifications">
              <Notifications sx={{ color: "#64748b" }} />
            </IconButton>
            <Divider orientation="vertical" flexItem sx={{ height: 30, my: "auto", bgcolor: "#e2e8f0" }} />
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box sx={{ textAlign: "right", display: { xs: "none", sm: "block" } }}>
                <Typography variant="subtitle2" fontWeight="800" color="#1e293b">
                  System Admin
                </Typography>
                <Typography variant="caption" fontWeight="600" color="#94a3b8">
                  Administrator
                </Typography>
              </Box>
              <IconButton
                onClick={(event) => setAnchorEl(event.currentTarget)}
                aria-label="Open admin menu"
                sx={{ p: 0.8, "&:hover": { bgcolor: "#f1f5f9" } }}
              >
                <Avatar sx={{ bgcolor: "#0f172a", width: 36, height: 36 }}>
                  <Person sx={{ fontSize: 20 }} />
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
                    width: 280,
                    borderRadius: 4,
                    boxShadow: "0 20px 45px rgba(15,23,42,0.16)",
                    border: "1px solid #e2e8f0",
                  },
                }}
              >
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5 }}>
                  <Typography fontSize="13px" fontWeight="600" color="#64748b">
                    admin@smartlab.ac.th
                  </Typography>
                  <IconButton size="small" onClick={() => setAnchorEl(null)} aria-label="Close menu">
                    <Close sx={{ fontSize: 18, color: "#64748b" }} />
                  </IconButton>
                </Box>
                <Box sx={{ px: 2, py: 1.5 }}>
                  <Button
                    fullWidth
                    onClick={handleLogout}
                    startIcon={<Logout />}
                    sx={{ justifyContent: "flex-start", color: "#ef4444", fontWeight: "700", textTransform: "none", borderRadius: 2 }}
                  >
                    Log out
                  </Button>
                </Box>
              </Popover>
            </Box>
          </Box>
        </Box>

        <Box sx={{ p: { xs: 3, md: 6 }, flex: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: { xs: "flex-start", sm: "center" }, gap: 2, mb: 4, flexWrap: "wrap" }}>
            <Box>
              <Typography variant="h4" fontWeight="800" color="#1e293b" sx={{ letterSpacing: "-1px" }}>
                คะแนนของผู้ใช้ทั้งหมด
              </Typography>
              <Typography variant="body2" color="#64748b" sx={{ mt: 0.75 }}>
                ตรวจสอบคะแนนสะสม คะแนนรายวัน และสิทธิ์การจองของทุกบัญชี
              </Typography>
              <Typography variant="caption" color="#94a3b8" sx={{ display: "block", mt: 0.5 }}>
                คะแนนรายวัน ณ {formatDate(scoreDate)} · เกณฑ์การจอง {bookingMinPoints} คะแนน
              </Typography>
            </Box>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={fetchPoints}
              disabled={loading}
              sx={{ borderRadius: 3, textTransform: "none", fontWeight: "700", borderColor: "#cbd5e1", color: "#475569" }}
            >
              รีเฟรชข้อมูล
            </Button>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>
              {error}
            </Alert>
          )}

          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 2.5, mb: 4 }}>
            {statCards.map((card) => (
              <Paper key={card.label} elevation={0} sx={{ p: 3, borderRadius: 4, border: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 2 }}>
                <Avatar sx={{ bgcolor: card.color, width: 48, height: 48, borderRadius: 3 }}>
                  {card.icon}
                </Avatar>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="caption" fontWeight="700" color="#64748b">
                    {card.label}
                  </Typography>
                  <Typography variant="h5" fontWeight="800" color="#1e293b">
                    {card.value}
                  </Typography>
                  <Typography variant="caption" color="#94a3b8" noWrap>
                    {card.helper}
                  </Typography>
                </Box>
              </Paper>
            ))}
          </Box>

          <Paper elevation={0} sx={{ borderRadius: 4, border: "1px solid #e2e8f0", overflow: "hidden" }}>
            <Box sx={{ p: { xs: 2.5, md: 3 }, display: "flex", alignItems: { xs: "stretch", md: "center" }, gap: 2, flexWrap: "wrap", borderBottom: "1px solid #f1f5f9" }}>
              <Box sx={{ flex: 1, minWidth: 240, display: "flex", alignItems: "center", bgcolor: "#f8fafc", borderRadius: 3, px: 1.5, py: 0.5 }}>
                <Search sx={{ color: "#94a3b8", mr: 1 }} />
                <InputBase
                  fullWidth
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="ค้นหาชื่อ อีเมล หรือ User ID..."
                  sx={{ fontSize: "14px", fontWeight: "500" }}
                  inputProps={{ "aria-label": "ค้นหาผู้ใช้" }}
                />
              </Box>
              <FormControl size="small" sx={{ minWidth: 170 }}>
                <InputLabel id="points-filter-label">ตัวกรอง</InputLabel>
                <Select labelId="points-filter-label" value={filter} label="ตัวกรอง" onChange={(event) => setFilter(event.target.value)}>
                  <MenuItem value="all">ผู้ใช้ทั้งหมด</MenuItem>
                  <MenuItem value="low">ต่ำกว่าเกณฑ์</MenuItem>
                  <MenuItem value="banned">ถูกระงับการจอง</MenuItem>
                  <MenuItem value="allowed">จองได้</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 170 }}>
                <InputLabel id="points-sort-label">เรียงตาม</InputLabel>
                <Select labelId="points-sort-label" value={sortBy} label="เรียงตาม" onChange={(event) => setSortBy(event.target.value)}>
                  <MenuItem value="pointsAsc">คะแนนน้อยไปมาก</MenuItem>
                  <MenuItem value="pointsDesc">คะแนนมากไปน้อย</MenuItem>
                  <MenuItem value="name">ชื่อผู้ใช้</MenuItem>
                </Select>
              </FormControl>
            </Box>

            {loading ? (
              <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 280 }}>
                <CircularProgress />
              </Box>
            ) : (
              <TableContainer sx={{ overflowX: "auto" }}>
                <Table sx={{ minWidth: 980 }}>
                  <TableHead>
                    <TableRow sx={{ bgcolor: "#f8fafc" }}>
                      <TableCell sx={{ color: "#64748b", fontWeight: "800", py: 2 }}>User</TableCell>
                      <TableCell sx={{ color: "#64748b", fontWeight: "800", py: 2 }}>Role</TableCell>
                      <TableCell sx={{ color: "#64748b", fontWeight: "800", py: 2, minWidth: 190 }}>คะแนนสะสม</TableCell>
                      <TableCell sx={{ color: "#64748b", fontWeight: "800", py: 2, minWidth: 140 }}>คะแนนวันนี้</TableCell>
                      <TableCell sx={{ color: "#64748b", fontWeight: "800", py: 2 }}>สิทธิ์การจอง</TableCell>
                      <TableCell sx={{ color: "#64748b", fontWeight: "800", py: 2 }}>อัปเดตล่าสุด</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredRows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} align="center" sx={{ py: 8, color: "#94a3b8" }}>
                          ไม่พบข้อมูลผู้ใช้ตามเงื่อนไขที่เลือก
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredRows.map((user) => {
                        const points = Math.max(0, Math.min(100, Number(user.points) || 0));
                        const dailyScore = Math.max(0, Math.min(100, Number(user.daily_score) || 0));
                        const scoreColor = getScoreColor(points);
                        const roleColor = getRoleColor(user.role);
                        return (
                          <TableRow key={user.user_id} sx={{ "& td": { borderBottom: "1px solid #f1f5f9" }, "&:hover": { bgcolor: "#fafafa" } }}>
                            <TableCell>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, minWidth: 230 }}>
                                <Avatar sx={{ bgcolor: stringToColor(user.name), width: 40, height: 40, fontSize: "14px", fontWeight: "800" }}>
                                  {getInitials(user)}
                                </Avatar>
                                <Box sx={{ minWidth: 0 }}>
                                  <Typography variant="subtitle2" fontWeight="800" color="#1e293b" noWrap>
                                    {user.name || "ไม่ระบุชื่อ"}
                                  </Typography>
                                  <Typography variant="caption" color="#64748b" display="block" noWrap>
                                    {user.email}
                                  </Typography>
                                  <Typography variant="caption" color="#94a3b8">
                                    ID #{user.user_id}
                                  </Typography>
                                </Box>
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Chip label={getRoleLabel(user.role)} size="small" sx={{ bgcolor: roleColor.bgcolor, color: roleColor.color, fontWeight: "800" }} />
                            </TableCell>
                            <TableCell>
                              <Box sx={{ minWidth: 165 }}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", mb: 0.75 }}>
                                  <Typography fontWeight="800" color={scoreColor}>
                                    {points}/100
                                  </Typography>
                                  <Typography variant="caption" color="#94a3b8">
                                    เกณฑ์ {bookingMinPoints}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={points}
                                  aria-label={`คะแนนสะสม ${points} จาก 100`}
                                  sx={{ height: 7, borderRadius: 4, bgcolor: "#f1f5f9", "& .MuiLinearProgress-bar": { bgcolor: scoreColor, borderRadius: 4 } }}
                                />
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ minWidth: 115 }}>
                                <Typography fontWeight="800" color="#334155">
                                  {dailyScore}/100
                                </Typography>
                                <LinearProgress
                                  variant="determinate"
                                  value={dailyScore}
                                  aria-label={`คะแนนวันนี้ ${dailyScore} จาก 100`}
                                  sx={{ mt: 0.75, height: 6, borderRadius: 4, bgcolor: "#f1f5f9", "& .MuiLinearProgress-bar": { bgcolor: "#60a5fa", borderRadius: 4 } }}
                                />
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 0.75 }}>
                                <Chip
                                  icon={user.booking_allowed ? <CheckCircle /> : <Block />}
                                  label={user.booking_allowed ? "จองได้" : "จองไม่ได้"}
                                  size="small"
                                  sx={{ bgcolor: user.booking_allowed ? "#ecfdf5" : "#fef2f2", color: user.booking_allowed ? "#047857" : "#b91c1c", fontWeight: "800", "& .MuiChip-icon": { color: "inherit", fontSize: 16 } }}
                                />
                                {user.is_banned && (
                                  <Typography variant="caption" color="#ef4444" fontWeight="700">
                                    Ban ถึง {formatDate(user.ban_until)}
                                  </Typography>
                                )}
                              </Box>
                            </TableCell>
                            <TableCell sx={{ color: "#64748b", fontSize: "13px", whiteSpace: "nowrap" }}>
                              {formatDateTime(user.updated_at)}
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {!loading && (
              <Box sx={{ px: 3, py: 2, borderTop: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
                <Typography variant="caption" color="#64748b" fontWeight="600">
                  แสดง {filteredRows.length} จาก {rows.length} ผู้ใช้
                </Typography>
                <Typography variant="caption" color="#94a3b8">
                  คะแนนสูงสุด 100 คะแนน
                </Typography>
              </Box>
            )}
          </Paper>
        </Box>
      </Box>
    </Box>
  );
}
