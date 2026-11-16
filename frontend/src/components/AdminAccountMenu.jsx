import { useState } from "react";
import { Close, Logout } from "@mui/icons-material";
import { Box, Button, Divider, IconButton, Popover, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import AdminHeaderAccount, { AdminIdentityDetails } from "./AdminHeaderAccount";
import AdminModeSwitch from "./AdminModeSwitch";

export default function AdminAccountMenu({ buttonSx, summaryClassName = "" }) {
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();
  const { t } = useLanguage();
  const [anchorEl, setAnchorEl] = useState(null);

  const closeMenu = () => setAnchorEl(null);
  const handleLogout = () => {
    closeMenu();
    logout();
    navigate("/");
  };

  return (
    <>
      <AdminHeaderAccount
        summaryClassName={summaryClassName}
        onClick={(event) => setAnchorEl(event.currentTarget)}
        buttonSx={buttonSx}
      />
      <Popover
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={closeMenu}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{
          paper: {
            className: "admin-account-menu",
            sx: { mt: 1.25, maxWidth: "calc(100vw - 16px)" },
          },
        }}
      >
        <Box className="admin-account-menu__heading">
          <Typography className="admin-account-menu__email" title={currentUser?.email || ""}>
            {currentUser?.email || "—"}
          </Typography>
          <IconButton
            size="small"
            onClick={closeMenu}
            aria-label={t("common.closeMenu")}
          >
            <Close fontSize="small" />
          </IconButton>
        </Box>

        <Box className="admin-account-menu__identity">
          <AdminIdentityDetails />
          <Button
            variant="outlined"
            onClick={() => {
              closeMenu();
              navigate("/profile");
            }}
            className="admin-account-menu__manage"
          >
            {t("common.manageAccount")}
          </Button>
        </Box>

        <Divider />

        <Box className="admin-account-menu__actions">
          <AdminModeSwitch destination="booking" onNavigate={closeMenu} />
          <Button
            fullWidth
            startIcon={<Logout />}
            onClick={handleLogout}
            className="admin-account-action danger"
          >
            {t("common.logout")}
          </Button>
        </Box>
      </Popover>
    </>
  );
}
