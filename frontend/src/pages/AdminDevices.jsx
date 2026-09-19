import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import {
  Assessment,
  Block,
  Close,
  Computer,
  ConfirmationNumber,
  ContentCopy,
  Dashboard as DashIcon,
  HowToReg,
  Logout,
  ManageAccounts,
  MeetingRoom,
  Notifications,
  Person,
  Settings,
} from "@mui/icons-material";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/auth-context";
import { authConfig } from "../utils/auth";
import { useLanguage } from "../context/language-context.js";

const API_URL = import.meta.env.VITE_API_URL;

const SIDE_MENU_ITEMS = [
  { key: "dashboard", icon: <DashIcon sx={{ fontSize: 20 }} />, path: "/admin" },
  { key: "manageLabs", icon: <MeetingRoom sx={{ fontSize: 20 }} />, path: "/manage-labs" },
  { key: "labDevices", icon: <Computer sx={{ fontSize: 20 }} />, path: "/admin/devices" },
  { key: "verifyUsers", icon: <HowToReg sx={{ fontSize: 20 }} />, path: "/verify-users" },
  { key: "userPoints", icon: <Assessment sx={{ fontSize: 20 }} />, path: "/admin/points" },
  { key: "pointCriteria", icon: <Settings sx={{ fontSize: 20 }} />, path: "/admin/points/policy" },
  { key: "roleManagement", icon: <ManageAccounts sx={{ fontSize: 20 }} />, path: "/admin/roles" },
  { key: "blacklist", icon: <Block sx={{ fontSize: 20 }} />, path: "/blacklist" },
  { key: "ticket", icon: <ConfirmationNumber sx={{ fontSize: 20 }} />, path: "/ticket" },
];

const STATUS_LABELS = {
  active: "active",
  maintenance: "maintenance",
  revoked: "revoked",
};

function formatDate(value, locale = "th-TH") {
  if (!value) return "";
  return new Date(value).toLocaleString(locale, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export default function AdminDevices() {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout } = useAuth();
  const { t } = useLanguage();
  const [anchorEl, setAnchorEl] = useState(null);
  const [devices, setDevices] = useState([]);
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openEnrollment, setOpenEnrollment] = useState(false);
  const [selectedLabId, setSelectedLabId] = useState("");
  const [expiresInMinutes, setExpiresInMinutes] = useState(10);
  const [enrollmentCode, setEnrollmentCode] = useState(null);
  const [savingDeviceId, setSavingDeviceId] = useState(null);
  const [notice, setNotice] = useState({ open: false, message: "", severity: "success" });

  const showNotice = (message, severity = "success") => {
    setNotice({ open: true, message, severity });
  };

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const [devicesResponse, labsResponse] = await Promise.all([
        axios.get(`${API_URL}/admin/lab-devices`, authConfig()),
        axios.get(`${API_URL}/labs`),
      ]);
      setDevices(devicesResponse.data?.data || []);
      setLabs(labsResponse.data?.data || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "ไม่สามารถโหลดข้อมูลเครื่องได้");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = `${t("admin.devicesTitle")} | Smart Lab Admin`;
    fetchData();
  }, [fetchData, t]);

  const handleCreateEnrollment = async () => {
    if (!selectedLabId) {
      showNotice(t("admin.chooseLabFirst"), "warning");
      return;
    }
    try {
      const response = await axios.post(
        `${API_URL}/admin/lab-devices/enrollment-codes`,
        { lab_id: Number(selectedLabId), expires_in_minutes: Number(expiresInMinutes) },
        authConfig(),
      );
      setEnrollmentCode(response.data);
    } catch (requestError) {
      showNotice(requestError.response?.data?.detail || "สร้างรหัสลงทะเบียนไม่สำเร็จ", "error");
    }
  };

  const handleCopyCode = async () => {
    if (!enrollmentCode?.enrollment_code) return;
    try {
      await navigator.clipboard.writeText(enrollmentCode.enrollment_code);
      showNotice(t("admin.copied"));
    } catch {
      showNotice(t("admin.copyFailed"), "warning");
    }
  };

  const handleCloseEnrollment = () => {
    setOpenEnrollment(false);
    setEnrollmentCode(null);
    setSelectedLabId("");
  };

  const handleSaveDevice = async (device) => {
    try {
      setSavingDeviceId(device.id);
      await axios.put(
        `${API_URL}/admin/lab-devices/${device.id}`,
        {
          status: device.status,
          lab_id: device.lab.id,
          device_name: device.device_name,
        },
        authConfig(),
      );
      showNotice(t("admin.deviceRegistered"));
      await fetchData();
    } catch (requestError) {
      showNotice(requestError.response?.data?.detail || t("admin.deviceSaveFailed"), "error");
    } finally {
      setSavingDeviceId(null);
    }
  };

  const updateDevice = (deviceId, field, value) => {
    setDevices((current) => current.map((device) => {
      if (device.id !== deviceId) return device;
      if (field === "lab_id") {
        const lab = labs.find((item) => item.id === Number(value));
        return lab ? { ...device, lab } : device;
      }
      return { ...device, [field]: value };
    }));
  };

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate("/");
  };

  return (
    <Box className="app-layout admin-layout" sx={{ display: "flex", minHeight: "100vh", bgcolor: "#fcfdfe", fontFamily: "'Inter', sans-serif" }}>
      <Box className="sidebar admin-sidebar" sx={{ width: "var(--sidebar-width)", bgcolor: "#f0f7ff", borderRight: "1px solid #e2efff", display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh", zIndex: 10 }}>
        <Box className="sidebar-logo" sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}>
          <Box className="admin-brand-mark" sx={{ bgcolor: "#000", p: 1, borderRadius: 2.5, display: "flex", boxShadow: "0 4px 10px rgba(0,0,0,0.2)" }}>
            <Computer sx={{ color: "white", fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h6" fontWeight="800" sx={{ color: "#0f172a", letterSpacing: "-0.5px" }}>Smart Lab</Typography>
            <Typography variant="caption" sx={{ color: "#64748b", fontWeight: "500", display: "block", mt: -0.5 }}>Admin Dashboard</Typography>
          </Box>
        </Box>
        <Box className="sidebar-menu" sx={{ px: 2, mt: 4 }}>
          {SIDE_MENU_ITEMS.map((item) => (
            <Button
              key={item.key}
              className={location.pathname === item.path ? "active" : ""}
              fullWidth
              onClick={() => navigate(item.path)}
              startIcon={item.icon}
              sx={{ justifyContent: "flex-start", py: 1, px: 2.5, mb: 0.5, bgcolor: location.pathname === item.path ? "white" : "transparent", color: location.pathname === item.path ? "#3b82f6" : "#94a3b8", fontWeight: location.pathname === item.path ? "700" : "600", fontSize: "var(--sidebar-font-size)", boxShadow: location.pathname === item.path ? "0 10px 25px rgba(0,0,0,0.03)" : "none", borderRadius: "var(--sidebar-active-radius)", textTransform: "none", "&:hover": { bgcolor: "white", color: "#3b82f6" } }}
            >
              {t(`admin.${item.key}`)}
            </Button>
          ))}
        </Box>
      </Box>

      <Box className="main-area admin-main-area" sx={{ flex: 1, display: "flex", flexDirection: "column", overflowX: "hidden" }}>
        <Box className="top-header admin-top-header" sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 6, py: 1, bgcolor: "white", borderBottom: "1px solid #e2e8f0" }}>
          <Typography variant="h5" fontWeight="800" sx={{ color: "#1e293b", letterSpacing: "-1px" }}>{t("admin.devicesTitle")}</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconButton className="admin-notification-button" aria-label={t("common.notifications")}><Notifications sx={{ color: "#64748b" }} /></IconButton>
            <Divider orientation="vertical" flexItem sx={{ height: 30, my: "auto", bgcolor: "#e2e8f0" }} />
            <Box sx={{ textAlign: "right" }}>
              <Typography variant="subtitle2" fontWeight="800" color="#1e293b">{t("common.systemAdmin")}</Typography>
              <Typography variant="caption" fontWeight="600" color="#94a3b8">{t("common.administrator")}</Typography>
            </Box>
            <IconButton onClick={(event) => setAnchorEl(event.currentTarget)} sx={{ p: 0.8 }}>
              <Avatar sx={{ bgcolor: "#0f172a", width: 36, height: 36 }}><Person sx={{ fontSize: 20 }} /></Avatar>
            </IconButton>
          </Box>
        </Box>

        <Box className="content-area admin-content-area page-content" sx={{ p: { xs: 2, md: 5 }, flex: 1 }}>
          <Box className="page-header" sx={{ display: "flex", justifyContent: "space-between", alignItems: { xs: "flex-start", md: "center" }, gap: 2, mb: 3, flexDirection: { xs: "column", md: "row" } }}>
            <Box>
              <Typography variant="h4" fontWeight="800" color="#0f172a">{t("admin.deviceHeading")}</Typography>
              <Typography color="#64748b" sx={{ mt: 0.5 }}>{t("admin.deviceSubtitle")}</Typography>
            </Box>
            <Button variant="contained" startIcon={<Computer />} onClick={() => setOpenEnrollment(true)} sx={{ borderRadius: 2, textTransform: "none", fontWeight: 700, px: 2.5 }}>{t("admin.createEnrollment")}</Button>
          </Box>

          {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
          <Paper className="surface-card data-table-shell" elevation={0} sx={{ border: "1px solid #e2e8f0", borderRadius: 3, overflow: "hidden" }}>
            <TableContainer sx={{ overflowX: "auto" }}>
              <Table sx={{ minWidth: 980 }}>
                <TableHead sx={{ bgcolor: "#f8fafc" }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 800 }}>{t("admin.machine")}</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>{t("user.lab")}</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>{t("common.status")}</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>{t("admin.agent")}</TableCell>
                    <TableCell sx={{ fontWeight: 800 }}>{t("admin.lastSignal")}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 800 }}>{t("admin.manage")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loading ? (
                    <TableRow><TableCell colSpan={6} align="center" sx={{ py: 7 }}><CircularProgress size={28} /></TableCell></TableRow>
                  ) : devices.length === 0 ? (
                    <TableRow><TableCell colSpan={6} align="center" sx={{ py: 7, color: "#94a3b8" }}>{t("admin.noDevices")}</TableCell></TableRow>
                  ) : devices.map((device) => (
                    <TableRow key={device.id} hover>
                      <TableCell>
                        <Typography fontWeight={700} color="#1e293b">{device.device_name}</Typography>
                        <Typography variant="caption" color="#94a3b8">{device.device_id}</Typography>
                        <Typography variant="caption" display="block" color="#94a3b8">{device.device_mac || t("common.noMac")}</Typography>
                      </TableCell>
                      <TableCell sx={{ minWidth: 210 }}>
                        <FormControl size="small" fullWidth>
                          <Select value={device.lab.id} onChange={(event) => updateDevice(device.id, "lab_id", event.target.value)}>
                            {labs.map((lab) => <MenuItem key={lab.id} value={lab.id}>{lab.code} — {lab.name}</MenuItem>)}
                          </Select>
                        </FormControl>
                      </TableCell>
                      <TableCell sx={{ minWidth: 155 }}>
                        <Select size="small" value={device.status} onChange={(event) => updateDevice(device.id, "status", event.target.value)}>
                          {Object.keys(STATUS_LABELS).map((value) => <MenuItem key={value} value={value}>{t(`common.${value}`)}</MenuItem>)}
                        </Select>
                      </TableCell>
                      <TableCell>{device.agent_version || t("common.source")}</TableCell>
                      <TableCell>{formatDate(device.last_seen_at, t("common.locale")) || t("common.noSignal")}</TableCell>
                      <TableCell align="right">
                        <Button size="small" variant="outlined" disabled={savingDeviceId === device.id} onClick={() => handleSaveDevice(device)} sx={{ textTransform: "none", borderRadius: 2 }}>
                          {savingDeviceId === device.id ? t("admin.savingDevice") : t("admin.saveDevice")}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Box>
      </Box>

      <Dialog open={openEnrollment} onClose={handleCloseEnrollment} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>{t("admin.enrollmentTitle")}</DialogTitle>
        <DialogContent>
          {!enrollmentCode ? (
            <Box sx={{ display: "grid", gap: 2, pt: 1 }}>
              <FormControl fullWidth>
                <InputLabel>Lab</InputLabel>
                <Select label="Lab" value={selectedLabId} onChange={(event) => setSelectedLabId(event.target.value)}>
                  {labs.filter((lab) => lab.status === "active").map((lab) => <MenuItem key={lab.id} value={lab.id}>{lab.code} — {lab.name}</MenuItem>)}
                </Select>
              </FormControl>
                <TextField select label={t("admin.enrollmentAge")} value={expiresInMinutes} onChange={(event) => setExpiresInMinutes(event.target.value)}>
                <MenuItem value={10}>10 {t("common.minutes")}</MenuItem>
                <MenuItem value={30}>30 {t("common.minutes")}</MenuItem>
                <MenuItem value={60}>60 {t("common.minutes")}</MenuItem>
              </TextField>
              <Alert severity="info">{t("admin.oneTimeCode")}</Alert>
            </Box>
          ) : (
            <Box sx={{ display: "grid", gap: 2, pt: 1 }}>
              <Alert severity="success">{t("admin.generatedFor")} {enrollmentCode.lab?.code} — {enrollmentCode.lab?.name}</Alert>
              <TextField label="Enrollment Code" value={enrollmentCode.enrollment_code} InputProps={{ readOnly: true }} fullWidth />
              <Button variant="outlined" startIcon={<ContentCopy />} onClick={handleCopyCode} sx={{ textTransform: "none" }}>{t("admin.copyCode")}</Button>
              <Typography variant="body2" color="#64748b">{t("admin.expiresAt")}: {formatDate(enrollmentCode.expires_at, t("common.locale"))} · {t("admin.setupCommand")}</Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2.5 }}>
          <Button onClick={handleCloseEnrollment} sx={{ textTransform: "none" }}>{enrollmentCode ? t("common.close") : t("common.cancel")}</Button>
          {!enrollmentCode && <Button variant="contained" onClick={handleCreateEnrollment} sx={{ textTransform: "none" }}>{t("admin.createCode")}</Button>}
        </DialogActions>
      </Dialog>

      <Snackbar open={notice.open} autoHideDuration={3500} onClose={() => setNotice((current) => ({ ...current, open: false }))}>
        <Alert severity={notice.severity} onClose={() => setNotice((current) => ({ ...current, open: false }))}>{notice.message}</Alert>
      </Snackbar>

      {Boolean(anchorEl) && (
        <Paper className="surface-card" sx={{ position: "fixed", right: 28, top: 68, zIndex: 20, p: 1, width: 190, border: "1px solid #e2e8f0" }}>
          <Button fullWidth startIcon={<Logout />} onClick={handleLogout} sx={{ justifyContent: "flex-start", textTransform: "none", color: "#ef4444" }}>{t("common.logout")}</Button>
          <IconButton size="small" onClick={() => setAnchorEl(null)} sx={{ position: "absolute", top: 3, right: 3 }}><Close fontSize="small" /></IconButton>
        </Paper>
      )}
    </Box>
  );
}
