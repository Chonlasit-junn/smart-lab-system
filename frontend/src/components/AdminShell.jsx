import SmartLabLogo from "./SmartLabLogo";
import { useState } from "react";
import { Menu as MenuIcon } from "@mui/icons-material";
import { Box, Divider, IconButton, Typography } from "@mui/material";
import { useLanguage } from "../context/language-context.js";
import AdminNavigation from "./AdminNavigation";
import AdminAccountMenu from "./AdminAccountMenu";
import AdminNotificationBell from "./AdminNotificationBell";

export default function AdminShell({ title, children }) {
  const { t } = useLanguage();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <Box className="app-layout admin-layout admin-shell">
      {isSidebarOpen && (
        <Box
          className="sidebar-overlay"
          onClick={() => setIsSidebarOpen(false)}
          role="presentation"
        />
      )}

      <Box className={`sidebar admin-sidebar ${isSidebarOpen ? "open" : ""}`}>
        <Box className="sidebar-logo">
          <SmartLabLogo decorative />
          <Box>
            <Typography variant="h6" fontWeight="700" className="admin-brand-title">
              Smart Lab
            </Typography>
            <Typography variant="caption" className="admin-brand-subtitle">
              {t("common.adminDashboard")}
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
              aria-label={t("common.openMenu")}
            >
              <MenuIcon />
            </IconButton>
            <Typography variant="h5" fontWeight="700" className="admin-page-heading">
              {title}
            </Typography>
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <AdminNotificationBell
              className="admin-notification-button"
              iconColor="#64748b"
            />
            <Divider orientation="vertical" flexItem className="admin-header-divider" />
            <AdminAccountMenu buttonSx={{ p: 0.8 }} />
          </Box>
        </Box>

        <Box className="content-area admin-content-area">{children}</Box>
      </Box>

    </Box>
  );
}
