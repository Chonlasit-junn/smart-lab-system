import { useState } from "react";
import { Computer, Menu as MenuIcon } from "@mui/icons-material";
import { Box, IconButton, Typography } from "@mui/material";
import { useLocation } from "react-router-dom";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import AdminNavigation from "./AdminNavigation";

const isAdminPage = (pathname) => /^(\/admin(?:\/|$)|\/manage-labs$|\/verify-users$|\/blacklist$|\/ticket$|\/profile$)/.test(pathname);

export default function AdminMobileNavigation() {
  const { currentUser } = useAuth();
  const { pathname } = useLocation();
  const { t } = useLanguage();
  const [openPath, setOpenPath] = useState(null);
  const open = openPath === pathname;
  const isAdmin = currentUser?.roleName === "admin" && isAdminPage(pathname);
  const pageHasOwnDrawer = pathname === "/ticket" || pathname === "/profile";

  if (!isAdmin || pageHasOwnDrawer) return null;

  return (
    <>
      {!open && (
        <IconButton
          className="admin-global-menu-toggle"
          onClick={() => setOpenPath(pathname)}
          aria-label={t("common.openMenu")}
        >
          <MenuIcon />
        </IconButton>
      )}
      {open && (
        <>
          <Box
            className="sidebar-overlay"
            onClick={() => setOpenPath(null)}
            role="presentation"
          />
          <Box className="sidebar admin-sidebar open admin-mobile-drawer">
            <Box className="sidebar-logo">
              <Box className="admin-brand-mark">
                <Computer sx={{ color: "white", fontSize: 28 }} />
              </Box>
              <Box>
                <Typography variant="h6" fontWeight="700" className="admin-brand-title">
                  Smart Lab
                </Typography>
                <Typography variant="caption" className="admin-brand-subtitle">
                  {t("common.adminDashboard")}
                </Typography>
              </Box>
            </Box>
            <AdminNavigation onNavigate={() => setOpenPath(null)} />
          </Box>
        </>
      )}
    </>
  );
}
