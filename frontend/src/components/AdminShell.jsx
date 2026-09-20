import { useState } from "react";
import {
  Computer,
  Logout,
  Menu as MenuIcon,
  Notifications,
  Person,
  Settings,
} from "@mui/icons-material";
import {
  Avatar,
  Box,
  Button,
  Divider,
  IconButton,
  Popover,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import AdminNavigation from "./AdminNavigation";

export default function AdminShell({ title, children }) {
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();
  const { t } = useLanguage();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);

  const handleNavigate = (path) => {
    setIsSidebarOpen(false);
    setAnchorEl(null);
    navigate(path);
  };

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate("/");
  };

  return (
    <Box className="app-layout admin-layout">
      {isSidebarOpen && (
        <Box
          className="sidebar-overlay"
          onClick={() => setIsSidebarOpen(false)}
          role="presentation"
        />
      )}

      <Box className={`sidebar admin-sidebar ${isSidebarOpen ? "open" : ""}`}>
        <Box className="sidebar-logo">
          <Box className="admin-brand-mark">
            <Computer sx={{ color: "white", fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h6" fontWeight="800" className="admin-brand-title">
              Smart Lab
            </Typography>
            <Typography variant="caption" className="admin-brand-subtitle">
              Admin Dashboard
            </Typography>
          </Box>
        </Box>

        <AdminNavigation onNavigate={() => setIsSidebarOpen(false)} />
      </Box>

      <Box className="main-area admin-main-area">
        <Box className="top-header admin-top-header">
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <IconButton
              className="admin-menu-toggle"
              onClick={() => setIsSidebarOpen(true)}
              aria-label="เปิดเมนูผู้ดูแลระบบ"
            >
              <MenuIcon />
            </IconButton>
            <Typography variant="h5" fontWeight="800" className="admin-page-heading">
              {title}
            </Typography>
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <IconButton className="admin-notification-button" aria-label={t("common.notifications")}>
              <Notifications />
            </IconButton>
            <Divider orientation="vertical" flexItem className="admin-header-divider" />
            <Box className="admin-user-summary">
              <Typography variant="subtitle2" fontWeight="800">
                {currentUser?.name || "System Admin"}
              </Typography>
              <Typography variant="caption" fontWeight="600">
                {currentUser?.role || t("common.administrator")}
              </Typography>
            </Box>
            <IconButton
              onClick={(event) => setAnchorEl(event.currentTarget)}
              aria-label={t("common.profile")}
              sx={{ p: 0.8 }}
            >
              <Avatar className="admin-avatar">
                {currentUser?.initial || <Person sx={{ fontSize: 20 }} />}
              </Avatar>
            </IconButton>
          </Box>
        </Box>

        <Box className="content-area admin-content-area">{children}</Box>
      </Box>

      <Popover
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        PaperProps={{ className: "admin-account-menu" }}
      >
        <Button
          fullWidth
          startIcon={<Settings />}
          onClick={() => handleNavigate("/profile")}
          className="admin-account-action"
        >
          {t("common.settings")}
        </Button>
        <Button
          fullWidth
          startIcon={<Logout />}
          onClick={handleLogout}
          className="admin-account-action danger"
        >
          {t("common.logout")}
        </Button>
      </Popover>
    </Box>
  );
}
