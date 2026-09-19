import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
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
  FormControl,
  IconButton,
  InputBase,
  InputLabel,
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
  TextField,
  Typography,
} from "@mui/material";
import {
  AdminPanelSettings,
  Assessment,
  Block,
  Close,
  Computer,
  ConfirmationNumber,
  Dashboard as DashIcon,
  Edit,
  HowToReg,
  Logout,
  ManageAccounts,
  MeetingRoom,
  Notifications,
  Person,
  Refresh,
  Save,
  Search,
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

const ROLE_COLORS = {
  admin: { backgroundColor: "#f3e8ff", color: "#7e22ce" },
  student: { backgroundColor: "#eff6ff", color: "#2563eb" },
  guest: { backgroundColor: "#f1f5f9", color: "#64748b" },
};

const getRoleColor = (roleName) =>
  ROLE_COLORS[roleName] || { backgroundColor: "#ecfeff", color: "#0f766e" };

const getRoleLabel = (role) => role?.display_name || role?.name || "ยังไม่มี Role";

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

const getErrorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
};

function RoleChip({ role }) {
  const colors = getRoleColor(role?.name);
  return (
    <Chip
      size="small"
      icon={<AdminPanelSettings sx={{ fontSize: 16 }} />}
      label={getRoleLabel(role)}
      sx={{
        backgroundColor: colors.backgroundColor,
        color: colors.color,
        fontWeight: 700,
        "& .MuiChip-icon": { color: colors.color },
      }}
    />
  );
}

export default function RoleManagement() {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser, logout } = useAuth();
  const { t } = useLanguage();

  const [anchorEl, setAnchorEl] = useState(null);
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [savingUserId, setSavingUserId] = useState(null);
  const [editingRole, setEditingRole] = useState(null);
  const [displayName, setDisplayName] = useState("");
  const [savingRole, setSavingRole] = useState(false);

  const fetchRoleData = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const requestConfig = authConfig();
      const [rolesResponse, usersResponse] = await Promise.all([
        axios.get(`${API_URL}/admin/roles`, requestConfig),
        axios.get(`${API_URL}/admin/roles/users`, requestConfig),
      ]);
      setRoles(Array.isArray(rolesResponse.data?.data) ? rolesResponse.data.data : []);
      setUsers(Array.isArray(usersResponse.data?.data) ? usersResponse.data.data : []);
    } catch (requestError) {
      setError(getErrorMessage(requestError, "ไม่สามารถโหลดข้อมูล Role ได้"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    document.title = `${t("admin.rolesTitle")} | Smart Lab Admin`;
    fetchRoleData();
  }, [fetchRoleData, t]);

  const filteredUsers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return users.filter((user) => {
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      const searchable = [
        user.first_name,
        user.last_name,
        user.email,
        user.role,
        user.role_display_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return matchesRole && (!query || searchable.includes(query));
    });
  }, [roleFilter, searchQuery, users]);

  const assignedUsers = users.filter((user) => user.roles?.length > 0).length;
  const systemRoles = roles.filter((role) => role.is_system).length;

  const handleRoleAssignment = async (userId, roleId) => {
    try {
      setSavingUserId(userId);
      setError("");
      setSuccess("");
      const response = await axios.put(
        `${API_URL}/admin/roles/users/${userId}`,
        { role_id: Number(roleId) },
        authConfig(),
      );
      const updatedUser = response.data?.data;
      if (updatedUser) {
        setUsers((currentUsers) =>
          currentUsers.map((user) => (user.id === userId ? updatedUser : user)),
        );
      }
      setRoles((currentRoles) =>
        currentRoles.map((role) => {
          const nextCount = role.user_count +
            (updatedUser?.role === role.name ? 1 : 0) -
            (users.find((user) => user.id === userId)?.role === role.name ? 1 : 0);
          return { ...role, user_count: Math.max(0, nextCount) };
        }),
      );
      setSuccess("เปลี่ยน Role ของผู้ใช้เรียบร้อยแล้ว");
    } catch (requestError) {
      setError(getErrorMessage(requestError, "ไม่สามารถเปลี่ยน Role ของผู้ใช้ได้"));
    } finally {
      setSavingUserId(null);
    }
  };

  const openEditDialog = (role) => {
    setEditingRole(role);
    setDisplayName(role.display_name || role.name);
    setError("");
    setSuccess("");
  };

  const handleSaveRole = async () => {
    if (!editingRole || !displayName.trim()) return;
    try {
      setSavingRole(true);
      setError("");
      setSuccess("");
      const response = await axios.put(
        `${API_URL}/admin/roles/${editingRole.id}`,
        { display_name: displayName.trim() },
        authConfig(),
      );
      const updatedRole = response.data?.data;
      if (updatedRole) {
        setRoles((currentRoles) =>
          currentRoles.map((role) => (role.id === updatedRole.id ? updatedRole : role)),
        );
        setUsers((currentUsers) =>
          currentUsers.map((user) => ({
            ...user,
            role_display_name:
              user.role === updatedRole.name ? updatedRole.display_name : user.role_display_name,
            roles: user.roles?.map((role) =>
              role.id === updatedRole.id
                ? { ...role, display_name: updatedRole.display_name }
                : role,
            ),
          })),
        );
      }
      setEditingRole(null);
      setSuccess("บันทึกชื่อ Role เรียบร้อยแล้ว");
    } catch (requestError) {
      setError(getErrorMessage(requestError, "ไม่สามารถบันทึกชื่อ Role ได้"));
    } finally {
      setSavingRole(false);
    }
  };

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate("/");
  };

  return (
    <Box
      className="app-layout admin-layout"
      sx={{
        display: "flex",
        minHeight: "100vh",
        bgcolor: "#fcfdfe",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <Box
        className="sidebar admin-sidebar"
        sx={{
          width: "var(--sidebar-width)",
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
        <Box className="sidebar-logo" sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}>
          <Box
            className="admin-brand-mark"
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

        <Box className="sidebar-menu" sx={{ px: 2, mt: 4 }}>
          {SIDE_MENU_ITEMS.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Button
                key={item.key}
                className={isActive ? "active" : ""}
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
                  fontSize: "var(--sidebar-font-size)",
                  boxShadow: isActive ? "0 10px 25px rgba(0,0,0,0.03)" : "none",
                  borderRadius: "var(--sidebar-active-radius)",
                  textTransform: "none",
                  transition: "0.3s",
                  "&:hover": {
                    bgcolor: isActive ? "white" : "transparent",
                    color: "#3b82f6",
                    transform: "translateX(5px)",
                  },
                }}
              >
                {t(`admin.${item.key}`)}
              </Button>
            );
          })}
        </Box>
      </Box>

      <Box className="main-area admin-main-area" sx={{ flex: 1, display: "flex", flexDirection: "column", overflowX: "hidden", minWidth: 0 }}>
        <Box
          className="top-header admin-top-header"
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
            {t("admin.rolesTitle")}
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconButton className="admin-notification-button" aria-label={t("common.notifications")}>
              <Notifications sx={{ color: "#64748b" }} />
            </IconButton>
            <Divider orientation="vertical" flexItem sx={{ height: 30, my: "auto", bgcolor: "#e2e8f0" }} />
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <Box sx={{ textAlign: "right", display: { xs: "none", sm: "block" } }}>
                <Typography variant="subtitle2" fontWeight="800" color="#1e293b">
                  {t("common.systemAdmin")}
                </Typography>
                <Typography variant="caption" fontWeight="600" color="#94a3b8">
                  {t("common.administrator")}
                </Typography>
              </Box>
              <IconButton
                onClick={(event) => setAnchorEl(event.currentTarget)}
                aria-label={t("common.openMenu")}
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
                slotProps={{
                  paper: {
                    sx: {
                      mt: 1.5,
                      width: 280,
                      borderRadius: 4,
                      boxShadow: "0 20px 45px rgba(15,23,42,0.16)",
                      border: "1px solid #e2e8f0",
                    },
                  },
                }}
              >
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, pt: 1.5 }}>
                  <Typography fontSize="13px" fontWeight="600" color="#64748b">
                    {currentUser?.email || "admin@smartlab.ac.th"}
                  </Typography>
                  <IconButton size="small" onClick={() => setAnchorEl(null)} aria-label={t("common.closeMenu")}>
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
                    {t("common.logout")}
                  </Button>
                </Box>
              </Popover>
            </Box>
          </Box>
        </Box>

        <Box className="content-area admin-content-area page-content" sx={{ p: { xs: 3, md: 6 }, flex: 1 }}>
          <Box className="page-header" sx={{ display: "flex", justifyContent: "space-between", alignItems: { xs: "flex-start", sm: "center" }, gap: 2, mb: 3, flexWrap: "wrap" }}>
            <Box>
              <Typography variant="h4" fontWeight="800" color="#1e293b" sx={{ letterSpacing: "-1px" }}>
                {t("admin.rolesHeading")}
              </Typography>
              <Typography variant="body2" color="#64748b" sx={{ mt: 0.75 }}>
                {t("admin.rolesSubtitle")}
              </Typography>
            </Box>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={fetchRoleData}
              disabled={loading}
              sx={{ borderRadius: 3, textTransform: "none", fontWeight: "700", borderColor: "#cbd5e1", color: "#475569" }}
            >
              {t("admin.refreshData")}
            </Button>
          </Box>

          <Alert severity="info" sx={{ mb: 3, borderRadius: 3 }}>
            Role key ของระบบจะไม่ถูกเปลี่ยน เพื่อไม่ให้กระทบการ Login และสิทธิ์ Admin
            สามารถแก้ชื่อแสดงผลและกำหนด Role ให้ผู้ใช้ได้
          </Alert>

          {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>{error}</Alert>}
          {success && <Alert severity="success" sx={{ mb: 3, borderRadius: 3 }}>{success}</Alert>}

          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" }, gap: 2, mb: 3 }}>
            {[
              { label: "Roles ทั้งหมด", value: roles.length, color: "#3b82f6", icon: <AdminPanelSettings /> },
              { label: "ผู้ใช้ที่มี Role", value: assignedUsers, color: "#10b981", icon: <Person /> },
              { label: "System Roles", value: systemRoles, color: "#8b5cf6", icon: <Settings /> },
            ].map((card) => (
              <Paper key={card.label} className="surface-card" elevation={0} sx={{ p: 2.5, borderRadius: 4, border: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 2 }}>
                <Box sx={{ width: 46, height: 46, borderRadius: 3, bgcolor: `${card.color}15`, color: card.color, display: "grid", placeItems: "center" }}>
                  {card.icon}
                </Box>
                <Box>
                  <Typography variant="body2" color="#64748b" fontWeight="600">{card.label}</Typography>
                  <Typography variant="h5" color="#0f172a" fontWeight="800">{card.value}</Typography>
                </Box>
              </Paper>
            ))}
          </Box>

          {loading ? (
            <Box sx={{ minHeight: 360, display: "grid", placeItems: "center" }}><CircularProgress /></Box>
          ) : (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <Paper className="surface-card data-table-shell" elevation={0} sx={{ borderRadius: 4, border: "1px solid #e2e8f0", overflow: "hidden" }}>
                <Box sx={{ p: { xs: 2.5, md: 3 }, borderBottom: "1px solid #e2e8f0" }}>
                  <Typography variant="h6" fontWeight="800" color="#1e293b">{t("admin.rolesInSystem")}</Typography>
                  <Typography variant="body2" color="#64748b" sx={{ mt: 0.5 }}>
                    ชื่อ Role ใช้เป็น key ภายในระบบ ส่วนชื่อแสดงผลสามารถปรับให้เหมาะกับหน่วยงานได้
                  </Typography>
                </Box>
                <TableContainer sx={{ overflowX: "auto" }}>
                  <Table>
                    <TableHead>
                      <TableRow sx={{ bgcolor: "#f8fafc" }}>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>Role</TableCell>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>{t("admin.roleDisplayName")}</TableCell>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>{t("admin.roleUsers")}</TableCell>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>{t("admin.roleType")}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 800, color: "#64748b" }}>{t("admin.manage")}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {roles.map((role) => (
                        <TableRow key={role.id} hover>
                          <TableCell><Chip label={role.name} size="small" variant="outlined" sx={{ fontWeight: 700, borderRadius: 2 }} /></TableCell>
                          <TableCell sx={{ fontWeight: 700, color: "#334155" }}>{getRoleLabel(role)}</TableCell>
                          <TableCell sx={{ color: "#475569", fontWeight: 700 }}>{role.user_count}</TableCell>
                          <TableCell>
                            <Chip label={role.is_system ? "System role" : "Custom role"} size="small" sx={{ bgcolor: role.is_system ? "#eff6ff" : "#f1f5f9", color: role.is_system ? "#2563eb" : "#64748b", fontWeight: 700 }} />
                          </TableCell>
                          <TableCell align="right">
                            <Button startIcon={<Edit />} size="small" onClick={() => openEditDialog(role)} sx={{ textTransform: "none", fontWeight: 700, borderRadius: 2 }}>
                              {t("common.edit")}
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                      {!roles.length && (
                        <TableRow><TableCell colSpan={5} align="center" sx={{ py: 5, color: "#94a3b8" }}>{t("admin.noRoles")}</TableCell></TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>

              <Paper className="surface-card data-table-shell" elevation={0} sx={{ borderRadius: 4, border: "1px solid #e2e8f0", overflow: "hidden" }}>
                <Box sx={{ p: { xs: 2.5, md: 3 }, borderBottom: "1px solid #e2e8f0" }}>
                  <Typography variant="h6" fontWeight="800" color="#1e293b">{t("admin.assignRole")}</Typography>
                  <Typography variant="body2" color="#64748b" sx={{ mt: 0.5 }}>
                    การเปลี่ยน Role จะมีผลกับการเข้าใช้งานครั้งถัดไป ผู้ดูแลระบบจะไม่สามารถเปลี่ยน Role ของตัวเองได้
                  </Typography>
                  <Box sx={{ display: "flex", gap: 1.5, mt: 2, flexWrap: "wrap" }}>
                    <Box sx={{ flex: "1 1 280px", minWidth: 220, bgcolor: "#f8fafc", borderRadius: 2.5, px: 1.5, display: "flex", alignItems: "center", gap: 1 }}>
                      <Search sx={{ color: "#94a3b8" }} />
                      <InputBase value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder={t("admin.searchUsers")} sx={{ flex: 1, py: 0.75 }} />
                    </Box>
                    <FormControl size="small" sx={{ minWidth: 180 }}>
                      <InputLabel id="role-filter-label">{t("common.role")}</InputLabel>
                      <Select labelId="role-filter-label" value={roleFilter} label={t("common.role")} onChange={(event) => setRoleFilter(event.target.value)}>
                        <MenuItem value="all">{t("common.allRoles")}</MenuItem>
                        {roles.map((role) => <MenuItem key={role.id} value={role.name}>{getRoleLabel(role)}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Box>
                </Box>
                <TableContainer sx={{ overflowX: "auto" }}>
                  <Table>
                    <TableHead>
                      <TableRow sx={{ bgcolor: "#f8fafc" }}>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>ผู้ใช้</TableCell>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>Role ปัจจุบัน</TableCell>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b" }}>วันที่สร้าง</TableCell>
                        <TableCell sx={{ fontWeight: 800, color: "#64748b", minWidth: 210 }}>เปลี่ยน Role</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredUsers.map((user) => {
                        const currentRole = user.roles?.[0];
                        const isSelf = user.email === currentUser?.email;
                        return (
                          <TableRow key={user.id} hover>
                            <TableCell>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                                <Avatar sx={{ width: 34, height: 34, bgcolor: getRoleColor(user.role).color, fontSize: 14, fontWeight: 800 }}>
                                  {(user.first_name?.[0] || user.email?.[0] || "U").toUpperCase()}
                                </Avatar>
                                <Box>
                                  <Typography fontWeight={700} color="#334155">{`${user.first_name || ""} ${user.last_name || ""}`.trim() || "ไม่ระบุชื่อ"}</Typography>
                                  <Typography variant="caption" color="#94a3b8">{user.email}</Typography>
                                </Box>
                              </Box>
                            </TableCell>
                            <TableCell><RoleChip role={currentRole || { name: user.role, display_name: user.role_display_name }} /></TableCell>
                            <TableCell sx={{ color: "#64748b" }}>{formatDate(user.created_at)}</TableCell>
                            <TableCell>
                              <Select
                                size="small"
                                fullWidth
                                value={currentRole?.id || ""}
                                disabled={isSelf || savingUserId === user.id}
                                displayEmpty
                                onChange={(event) => handleRoleAssignment(user.id, event.target.value)}
                                renderValue={(selected) => {
                                  const selectedRole = roles.find((role) => role.id === selected);
                                  return selectedRole ? getRoleLabel(selectedRole) : "เลือก Role";
                                }}
                              >
                                {roles.filter((role) => role.assignable).map((role) => (
                                  <MenuItem key={role.id} value={role.id}>{getRoleLabel(role)}</MenuItem>
                                ))}
                              </Select>
                              {isSelf && <Typography variant="caption" color="#94a3b8">ไม่สามารถเปลี่ยน Role ตัวเอง</Typography>}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                      {!filteredUsers.length && (
                        <TableRow><TableCell colSpan={4} align="center" sx={{ py: 5, color: "#94a3b8" }}>{t("admin.noMatchingUsers")}</TableCell></TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            </Box>
          )}
        </Box>
      </Box>

      <Dialog open={Boolean(editingRole)} onClose={() => !savingRole && setEditingRole(null)} fullWidth maxWidth="xs">
        <DialogTitle sx={{ fontWeight: 800 }}>{t("admin.editRoleTitle")}</DialogTitle>
        <DialogContent>
          <TextField label={t("admin.roleKey")} value={editingRole?.name || ""} fullWidth disabled sx={{ mt: 1, mb: 2 }} />
          <TextField label={t("admin.roleDisplayName")} value={displayName} onChange={(event) => setDisplayName(event.target.value)} fullWidth autoFocus inputProps={{ maxLength: 100 }} />
        </DialogContent>
        <DialogActions sx={{ p: 2.5 }}>
          <Button onClick={() => setEditingRole(null)} disabled={savingRole} sx={{ textTransform: "none", color: "#64748b" }}>{t("common.cancel")}</Button>
          <Button variant="contained" startIcon={<Save />} onClick={handleSaveRole} disabled={savingRole || !displayName.trim()} sx={{ textTransform: "none", borderRadius: 2.5, boxShadow: "none" }}>
            {savingRole ? t("admin.saving") : t("common.save")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
