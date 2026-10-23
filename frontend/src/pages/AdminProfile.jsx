import { Avatar, Box, Paper, Typography } from "@mui/material";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import AdminShell from "../components/AdminShell";

export default function AdminProfile() {
  const { currentUser, currentProfile } = useAuth();
  const { t } = useLanguage();
  const profile = currentProfile?.data || {};
  const name = [profile.first_name, profile.last_name].filter(Boolean).join(" ") || currentUser?.name || "Admin";

  return (
    <AdminShell title={t("user.profileTitle")}>
      <Paper className="surface-card" elevation={0} sx={{ maxWidth: 720, mx: "auto", p: { xs: 2.5, sm: 4 } }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
          <Avatar sx={{ width: 64, height: 64, bgcolor: "primary.main" }}>
            {currentUser?.initial || "A"}
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h5" fontWeight={600} sx={{ overflowWrap: "anywhere" }}>{name}</Typography>
            <Typography variant="body2" color="text.secondary">{t("user.adminRole")}</Typography>
          </Box>
        </Box>
        <Typography variant="overline" color="text.secondary">{t("user.personalInfo")}</Typography>
        <Box sx={{ mt: 1.5, p: 2, borderRadius: 2, bgcolor: "background.default", overflowWrap: "anywhere" }}>
          <Typography variant="caption" color="text.secondary">{t("common.email")}</Typography>
          <Typography variant="body1">{profile.email || currentUser?.email || "—"}</Typography>
        </Box>
      </Paper>
    </AdminShell>
  );
}
