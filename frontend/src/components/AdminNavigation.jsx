import { Box, Button, Typography } from "@mui/material";
import {
  Assessment,
  Block,
  Computer,
  ConfirmationNumber,
  Dashboard,
  HowToReg,
  ManageAccounts,
  MeetingRoom,
  Settings,
} from "@mui/icons-material";
import { useLocation, useNavigate } from "react-router-dom";
import { useLanguage } from "../context/language-context.js";

const ADMIN_NAV_GROUPS = [
  {
    key: "overview",
    labelKey: "admin.navOverview",
    items: [
      { key: "dashboard", icon: <Dashboard sx={{ fontSize: 20 }} />, path: "/admin" },
    ],
  },
  {
    key: "labsAndDevices",
    labelKey: "admin.navLabsAndDevices",
    items: [
      { key: "manageLabs", icon: <MeetingRoom sx={{ fontSize: 20 }} />, path: "/manage-labs" },
      { key: "labDevices", icon: <Computer sx={{ fontSize: 20 }} />, path: "/admin/devices" },
    ],
  },
  {
    key: "users",
    labelKey: "admin.navUsers",
    items: [
      { key: "verifyUsers", icon: <HowToReg sx={{ fontSize: 20 }} />, path: "/verify-users" },
      { key: "roleManagement", icon: <ManageAccounts sx={{ fontSize: 20 }} />, path: "/admin/roles" },
    ],
  },
  {
    key: "pointsAndRules",
    labelKey: "admin.navPointsAndRules",
    items: [
      { key: "userPoints", icon: <Assessment sx={{ fontSize: 20 }} />, path: "/admin/points" },
      { key: "pointCriteria", icon: <Settings sx={{ fontSize: 20 }} />, path: "/admin/points/policy" },
      { key: "blacklist", icon: <Block sx={{ fontSize: 20 }} />, path: "/blacklist" },
    ],
  },
  {
    key: "support",
    labelKey: "admin.navSupport",
    items: [
      { key: "ticket", icon: <ConfirmationNumber sx={{ fontSize: 20 }} />, path: "/ticket" },
    ],
  },
];

export default function AdminNavigation({ onNavigate }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useLanguage();

  const handleNavigate = (path) => {
    onNavigate?.();
    navigate(path);
  };

  return (
    <Box className="admin-navigation">
      {ADMIN_NAV_GROUPS.map((group) => (
        <Box className="admin-nav-group" key={group.key}>
          <Typography component="div" className="admin-nav-group-label">
            {t(group.labelKey)}
          </Typography>
          <Box className="admin-nav-group-items">
            {group.items.map(({ key, icon, path }) => {
              const isActive = location.pathname === path;

              return (
                <Button
                  key={path}
                  fullWidth
                  className={isActive ? "active" : ""}
                  onClick={() => handleNavigate(path)}
                  startIcon={icon}
                  aria-current={isActive ? "page" : undefined}
                >
                  <span className="font-baseline-text">{t(`admin.${key}`)}</span>
                </Button>
              );
            })}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
