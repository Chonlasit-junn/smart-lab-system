import { AdminPanelSettings, EventNote } from "@mui/icons-material";
import { Button } from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import { canSwitchAdminMode, getAdminReturnPath } from "../utils/adminModeSwitch";

export default function AdminModeSwitch({ destination, onNavigate }) {
  const { currentUser } = useAuth();
  const { pathname, state } = useLocation();
  const navigate = useNavigate();
  const { t } = useLanguage();

  if (!canSwitchAdminMode(currentUser)) return null;

  const toBooking = destination === "booking";
  const handleClick = () => {
    onNavigate?.();
    if (toBooking) {
      navigate("/booking", { state: { adminReturnTo: pathname } });
      return;
    }

    navigate(getAdminReturnPath(state?.adminReturnTo));
  };

  return (
    <Button
      fullWidth
      startIcon={toBooking ? <EventNote /> : <AdminPanelSettings />}
      onClick={handleClick}
      aria-label={t(toBooking ? "common.goToLabBooking" : "common.backToAdmin")}
      sx={{
        justifyContent: "flex-start",
        color: "primary.main",
        fontWeight: 600,
        textAlign: "left",
        textTransform: "none",
        borderRadius: 2,
      }}
    >
      {t(toBooking ? "common.goToLabBooking" : "common.backToAdmin")}
    </Button>
  );
}
