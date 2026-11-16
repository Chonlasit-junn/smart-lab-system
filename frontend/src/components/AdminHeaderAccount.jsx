import { Avatar, Box, IconButton, Typography } from "@mui/material";
import { Person } from "@mui/icons-material";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";

const ROLE_LABELS = {
  admin: "Admin",
  student: "Student",
  guest: "Guest",
};

function useAdminIdentity() {
  const { currentUser, currentProfile } = useAuth();
  const isCurrentProfile = Boolean(
    currentUser?.email &&
      currentProfile?.identity?.toLowerCase() === currentUser.email.toLowerCase(),
  );
  const profile = isCurrentProfile ? currentProfile.data : null;
  const profileName = [profile?.first_name, profile?.last_name]
    .filter(Boolean)
    .join(" ")
    .trim();
  const emailName = currentUser?.email?.split("@")[0];
  const name = profileName || currentUser?.name || emailName || "Admin";
  const rawRole = profile?.role || currentUser?.roleName || currentUser?.role;
  const role = ROLE_LABELS[String(rawRole || "").toLowerCase()] || rawRole || "Admin";
  const initial = name.trim().charAt(0).toUpperCase();

  return { name, role, initial, profilePicture: profile?.profile_pic };
}

export function AdminIdentityAvatar({ className, sx }) {
  const { name, initial, profilePicture } = useAdminIdentity();

  return (
    <Avatar className={className} src={profilePicture || undefined} alt={name} sx={sx}>
      {initial || <Person sx={{ fontSize: 20 }} />}
    </Avatar>
  );
}

export default function AdminHeaderAccount({
  onClick,
  summaryClassName = "",
  buttonSx,
}) {
  const { name, role } = useAdminIdentity();
  const { t } = useLanguage();

  return (
    <>
      <Box
        className={`admin-user-summary ${summaryClassName}`.trim()}
        sx={{ minWidth: 0, maxWidth: 220, textAlign: "right" }}
      >
        <Typography variant="subtitle2" fontWeight="700" color="var(--text-dark)" noWrap>
          {name}
        </Typography>
        <Typography variant="caption" fontWeight="500" color="var(--text-muted)" noWrap>
          {role}
        </Typography>
      </Box>
      <IconButton
        className="admin-header-account-button"
        onClick={onClick}
        aria-label={t("common.openMenu")}
        sx={{ p: 0.8, ...buttonSx }}
      >
        <AdminIdentityAvatar
          className="admin-avatar"
        />
      </IconButton>
    </>
  );
}
