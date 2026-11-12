import React from "react";
import LoadError from "./LoadError";
import {
  Avatar,
  Box,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  Paper,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useMediaQuery,
} from "@mui/material";
import ResponsiveDataTable from "./ResponsiveDataTable";
import {
  AccessTime,
  Block,
  CalendarMonth,
  CheckCircle,
  Close,
  Computer,
  History,
  ReportProblem,
} from "@mui/icons-material";
import { formatDate, formatDateTime } from "../utils/dateFormat";
import { useLanguage } from "../context/language-context.js";

const API_URL = import.meta.env.VITE_API_URL;

const getInitials = (user) => {
  const initials = `${user?.first_name?.[0] || ""}${user?.last_name?.[0] || ""}`;
  return initials.toUpperCase() || "U";
};

const stringToColor = (value) => {
  if (!value) return "#cbd5e1";
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = value.charCodeAt(index) + ((hash << 5) - hash);
  }
  let color = "#";
  for (let index = 0; index < 3; index += 1) {
    color += `00${((hash >> (index * 8)) & 0xff).toString(16)}`.slice(-2);
  }
  return color;
};

const getProfileImage = (profilePic) => {
  if (!profilePic) return "";
  if (/^https?:\/\//i.test(profilePic)) return profilePic;
  if (!API_URL) return profilePic;
  return `${API_URL}/${profilePic.replace(/^\/+/, "")}`;
};

const formatDuration = (seconds, t) => {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "—";
  if (value < 60) return `${value} ${t("admin.userDetails.seconds")}`;
  return `${Math.floor(value / 60)} ${t("admin.userDetails.minutes")}`;
};

const getRoleLabel = (role, t) => ({
  student: t("admin.userDetails.roleStudent"),
  guest: t("admin.userDetails.roleGuest"),
  user: t("admin.userDetails.roleUser"),
  admin: t("admin.userDetails.roleAdministrator"),
  administrator: t("admin.userDetails.roleAdministrator"),
  system_admin: t("admin.userDetails.roleSystemAdmin"),
}[String(role || "").toLowerCase()] || role || t("admin.userDetails.roleUser"));

const getScoreColor = (score) => {
  if (score < 40) return "#ef4444";
  if (score < 80) return "#f59e0b";
  return "#10b981";
};

const getBookingStatus = (status, t) => ({
  reserved: { label: t("admin.userDetails.bookingReserved"), color: "#2563eb", bg: "#eff6ff" },
  attended: { label: t("admin.userDetails.bookingAttended"), color: "#047857", bg: "#ecfdf5" },
  completed: { label: t("admin.userDetails.bookingCompleted"), color: "#047857", bg: "#ecfdf5" },
  cancelled: { label: t("admin.userDetails.bookingCancelled"), color: "#64748b", bg: "#f1f5f9" },
  no_show: { label: t("admin.userDetails.bookingNoShow"), color: "#b91c1c", bg: "#fef2f2" },
}[status] || { label: status || t("common.notSpecified"), color: "#64748b", bg: "#f1f5f9" });

const getSessionStatus = (status, t) => ({
  active: { label: t("admin.userDetails.sessionActive"), color: "#047857", bg: "#ecfdf5" },
  completed: { label: t("admin.userDetails.sessionCompleted"), color: "#2563eb", bg: "#eff6ff" },
  abandoned: { label: t("admin.userDetails.sessionAbandoned"), color: "#b91c1c", bg: "#fef2f2" },
}[status] || { label: status || t("common.notSpecified"), color: "#64748b", bg: "#f1f5f9" });

const getPointReason = (reason, t) => ({
  daily_bonus: t("admin.userDetails.pointDailyBonus"),
  no_show: t("admin.userDetails.pointNoShow"),
  forbidden_app: t("admin.userDetails.pointForbiddenProgram"),
  late_cancel: t("admin.userDetails.pointLateCancel"),
  complete_session: t("admin.userDetails.pointSessionComplete"),
  admin_grant: t("admin.userDetails.pointAdminGrant"),
}[reason] || reason || t("admin.userDetails.pointAdjustment"));

const historyPanelScrollSx = {
  minWidth: 0,
};

function EmptyHistory({ icon, title, description }) {
  return (
    <Box sx={{ py: 7, textAlign: "center", color: "#94a3b8" }}>
      {icon}
      <Typography variant="subtitle1" fontWeight="600" color="#64748b">
        {title}
      </Typography>
      <Typography variant="body2" color="#94a3b8" sx={{ mt: 0.5 }}>
        {description}
      </Typography>
    </Box>
  );
}

function ProfileField({ label, value, fallback }) {
  return (
    <Box>
      <Typography variant="caption" color="#94a3b8" fontWeight="600">
        {label}
      </Typography>
      <Typography variant="body2" color="#334155" fontWeight="500" sx={{ mt: 0.35, overflowWrap: "break-word" }}>
        {value || fallback}
      </Typography>
    </Box>
  );
}

function UserBookings({ rows, t, locale }) {
  if (!rows.length) {
    return <EmptyHistory icon={<CalendarMonth sx={{ fontSize: 52, mb: 1 }} />} title={t("admin.userDetails.noBookingHistory")} description={t("admin.userDetails.noBookingHistoryDescription")} />;
  }

  return (
    <ResponsiveDataTable sx={{ overflowX: "auto" }}>
      <Table sx={{ minWidth: 760 }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "#f8fafc" }}>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.bookingDateTime")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.room")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.purpose")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.status")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((booking) => {
            const status = getBookingStatus(booking.status, t);
            return (
              <TableRow key={booking.id} sx={{ "& td": { borderBottom: "1px solid #f1f5f9" } }}>
                <TableCell>
                  <Typography variant="body2" fontWeight="600" color="#334155">{formatDate(booking.booking_date, locale)}</Typography>
                  <Typography variant="caption" color="#94a3b8">{booking.start_time || "—"} - {booking.end_time || "—"}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="600" color="#334155">{booking.lab_code || "—"}</Typography>
                  <Typography variant="caption" color="#94a3b8">{booking.lab_name || t("admin.userDetails.noRoom")}</Typography>
                </TableCell>
                <TableCell sx={{ maxWidth: 260, overflowWrap: "break-word" }}>{booking.purpose || t("common.notSpecified")}</TableCell>
                <TableCell><Chip label={status.label} size="small" sx={{ bgcolor: status.bg, color: status.color, fontWeight: "700" }} /></TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </ResponsiveDataTable>
  );
}

function UserSessions({ rows, t, locale }) {
  if (!rows.length) {
    return <EmptyHistory icon={<AccessTime sx={{ fontSize: 52, mb: 1 }} />} title={t("admin.userDetails.noSessions")} description={t("admin.userDetails.noSessionsDescription")} />;
  }

  return (
    <ResponsiveDataTable sx={{ overflowX: "auto" }}>
      <Table sx={{ minWidth: 860 }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "#f8fafc" }}>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.checkInOut")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.room")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.status")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.deviceInUse")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.endReason")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((session) => {
            const status = getSessionStatus(session.session_status, t);
            return (
              <TableRow key={session.id} sx={{ "& td": { borderBottom: "1px solid #f1f5f9" } }}>
                <TableCell>
                  <Typography variant="body2" fontWeight="600" color="#334155">{formatDateTime(session.entry_time, locale)}</Typography>
                  <Typography variant="caption" color="#94a3b8">{t("admin.userDetails.until")} {formatDateTime(session.exit_time, locale)}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="600" color="#334155">{session.lab_code || "—"}</Typography>
                  <Typography variant="caption" color="#94a3b8">{session.lab_name || t("admin.userDetails.noRoom")}</Typography>
                </TableCell>
                <TableCell><Chip label={status.label} size="small" sx={{ bgcolor: status.bg, color: status.color, fontWeight: "700" }} /></TableCell>
                <TableCell>
                  <Typography variant="body2" color="#334155">{session.device_used || t("admin.userDetails.noDevice")}</Typography>
                  <Typography variant="caption" color="#94a3b8">{session.device_mac || t("admin.userDetails.noMac")}</Typography>
                </TableCell>
                <TableCell sx={{ color: "#64748b" }}>{session.end_reason || "—"}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </ResponsiveDataTable>
  );
}

function UserProgramUsage({ rows, t, locale }) {
  if (!rows.length) {
    return <EmptyHistory icon={<Computer sx={{ fontSize: 52, mb: 1 }} />} title={t("admin.userDetails.noProgramUsage")} description={t("admin.userDetails.noProgramUsageDescription")} />;
  }

  return (
    <ResponsiveDataTable sx={{ overflowX: "auto" }}>
      <Table sx={{ minWidth: 860 }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "#f8fafc" }}>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.time")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.program")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.room")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.duration")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.device")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((usage) => (
            <TableRow key={usage.id} sx={{ "& td": { borderBottom: "1px solid #f1f5f9" } }}>
              <TableCell>
                <Typography variant="body2" fontWeight="600" color="#334155">{formatDateTime(usage.usage_start_time, locale)}</Typography>
                <Typography variant="caption" color="#94a3b8">{t("admin.userDetails.until")} {formatDateTime(usage.usage_end_time, locale)}</Typography>
              </TableCell>
              <TableCell sx={{ maxWidth: 220, overflowWrap: "break-word" }}>
                <Typography variant="body2" fontWeight="600" color="#334155">{usage.program_name || t("admin.userDetails.noProgram")}</Typography>
                <Typography variant="caption" color="#94a3b8">{t("admin.userDetails.event")} #{usage.id}</Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" fontWeight="600" color="#334155">{usage.lab_code || "—"}</Typography>
                <Typography variant="caption" color="#94a3b8">{usage.lab_name || t("admin.userDetails.noRoom")}</Typography>
              </TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDuration(usage.duration_seconds, t)}</TableCell>
              <TableCell sx={{ maxWidth: 180, overflowWrap: "break-word" }}>{usage.device_name || t("admin.userDetails.noDevice")}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </ResponsiveDataTable>
  );
}

function UserViolations({ rows, t, locale }) {
  if (!rows.length) {
    return <EmptyHistory icon={<CheckCircle sx={{ fontSize: 52, mb: 1, color: "#10b981" }} />} title={t("admin.userDetails.noViolations")} description={t("admin.userDetails.noViolationsDescription")} />;
  }

  return (
    <ResponsiveDataTable sx={{ overflowX: "auto" }}>
      <Table sx={{ minWidth: 900 }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "#f8fafc" }}>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.detectedAt")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.program")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.evidence")}</TableCell>
            <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.actionTaken")}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((violation) => (
            <TableRow key={violation.id} sx={{ "& td": { borderBottom: "1px solid #f1f5f9" } }}>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDateTime(violation.detected_at, locale)}</TableCell>
              <TableCell sx={{ maxWidth: 220, overflowWrap: "break-word" }}>
                <Typography variant="body2" fontWeight="600" color="#b91c1c">{violation.program_name || t("admin.userDetails.noProgram")}</Typography>
                <Typography variant="caption" color="#94a3b8">{violation.reason || t("admin.userDetails.noReason")}</Typography>
              </TableCell>
              <TableCell sx={{ maxWidth: 330, overflowWrap: "break-word" }}>
                <Typography variant="body2" color="#334155">{violation.process_name || t("admin.userDetails.noProcess")}</Typography>
                <Typography variant="caption" color="#94a3b8">{violation.window_title || violation.exe_path || t("admin.userDetails.noDetails")}</Typography>
              </TableCell>
              <TableCell><Chip icon={<ReportProblem />} label={violation.action_taken || t("admin.userDetails.recordedEvent")} size="small" sx={{ bgcolor: "#fef2f2", color: "#b91c1c", fontWeight: "700", "& .MuiChip-icon": { color: "inherit" } }} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </ResponsiveDataTable>
  );
}

function UserPointHistory({ pointLogs, dailyScores, t, locale }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1.5fr) minmax(280px, 1fr)" }, gap: 3 }}>
      <Box>
        {!pointLogs.length ? (
          <EmptyHistory icon={<History sx={{ fontSize: 52, mb: 1 }} />} title={t("admin.userDetails.noPointsHistory")} description={t("admin.userDetails.noPointsHistoryDescription")} />
        ) : (
          <ResponsiveDataTable sx={{ overflowX: "auto" }}>
            <Table sx={{ minWidth: 640 }}>
              <TableHead>
                <TableRow sx={{ bgcolor: "#f8fafc" }}>
                  <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.dateTime")}</TableCell>
                  <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.reason")}</TableCell>
                  <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.pointChange")}</TableCell>
                  <TableCell sx={{ fontWeight: "700", color: "#64748b" }}>{t("admin.userDetails.pointsAfter")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {pointLogs.map((log) => (
                  <TableRow key={log.id} sx={{ "& td": { borderBottom: "1px solid #f1f5f9" } }}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDateTime(log.created_at, locale)}</TableCell>
                    <TableCell sx={{ maxWidth: 260, overflowWrap: "break-word" }}>
                      <Typography variant="body2" fontWeight="600" color="#334155">{getPointReason(log.reason, t)}</Typography>
                      <Typography variant="caption" color="#94a3b8">{log.note || t("admin.userDetails.noDetails")}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography className="theme-colored" fontWeight="700" color={log.change < 0 ? "#ef4444" : "#10b981"}>
                        {log.change > 0 ? "+" : ""}{log.change}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ color: "#334155", fontWeight: "600" }}>{log.points_after ?? "—"}/100</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ResponsiveDataTable>
        )}
      </Box>
      <Paper className="surface-card" elevation={0} sx={{ border: "1px solid #e2e8f0", borderRadius: 3, alignSelf: "start", overflow: "hidden" }}>
        <Box sx={{ p: 2.5, borderBottom: "1px solid #f1f5f9" }}>
          <Typography fontWeight="700" color="#334155">{t("admin.userDetails.dailyPoints")}</Typography>
          <Typography variant="caption" color="#94a3b8">{t("admin.userDetails.dailyPointsLimit")}</Typography>
        </Box>
        {!dailyScores.length ? (
          <Box sx={{ p: 3 }}><Typography variant="body2" color="#94a3b8">{t("admin.userDetails.noDailyPoints")}</Typography></Box>
        ) : (
          <Box sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 2 }}>
            {dailyScores.map((row) => {
              const score = Math.max(0, Math.min(100, Number(row.score) || 0));
              return (
                <Box key={String(row.score_date)}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1, mb: 0.6 }}>
                    <Typography variant="body2" color="#64748b">{formatDate(row.score_date, locale)}</Typography>
                    <Typography className="theme-colored" variant="body2" fontWeight="700" color={getScoreColor(score)}>{score}/100</Typography>
                  </Box>
                  <LinearProgress variant="determinate" value={score} sx={{ height: 6, borderRadius: 4, bgcolor: "#f1f5f9", "& .MuiLinearProgress-bar": { bgcolor: getScoreColor(score), borderRadius: 4 } }} />
                </Box>
              );
            })}
          </Box>
        )}
      </Paper>
    </Box>
  );
}

export default function AdminUserDetailsDialog({
  open,
  onClose,
  selectedUser,
  detail,
  loading,
  error,
  onRetry,
  tab,
  onTabChange,
}) {
  const { t } = useLanguage();
  const isMobile = useMediaQuery("(max-width:600px)");
  const locale = t("common.locale");
  const profile = detail?.profile || selectedUser || {};
  const points = detail?.points || {};
  const summary = detail?.summary || {};
  const pointValue = Math.max(0, Math.min(100, Number(points.points) || 0));
  const dailyValue = Math.max(0, Math.min(100, Number(points.daily_score) || 0));
  const profileName = `${profile.first_name || ""} ${profile.last_name || ""}`.trim() || t("common.unknownName");
  const profileImage = getProfileImage(profile.profile_pic);
  const accountStatus = profile.account_status || "active";

  const tabs = [
    { label: t("admin.userDetails.bookings"), count: summary.total_bookings ?? (detail?.bookings?.length || 0) },
    { label: t("admin.userDetails.sessions"), count: summary.total_sessions ?? (detail?.sessions?.length || 0) },
    { label: t("admin.userDetails.programs"), count: summary.total_program_usage ?? (detail?.program_usage?.length || 0) },
    { label: t("admin.userDetails.pointHistory"), count: summary.total_point_events ?? (detail?.point_history?.length || 0) },
    { label: t("admin.userDetails.violations"), count: summary.total_violations ?? (detail?.violations?.length || 0) },
  ];

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen={isMobile}
      fullWidth
      maxWidth="xl"
      scroll="paper"
      className="admin-user-details-dialog"
      sx={{ zIndex: 1500 }}
      PaperProps={{
        sx: {
          display: "flex",
          flexDirection: "column",
          height: isMobile ? "100dvh" : "auto",
          minHeight: isMobile ? 0 : "min(760px, calc(100dvh - 64px))",
          maxHeight: isMobile ? "100dvh" : "calc(100dvh - 64px)",
          overflow: "hidden",
          margin: isMobile ? 0 : undefined,
          borderRadius: isMobile ? 0 : 4,
        },
      }}
    >
      <DialogTitle sx={{ p: { xs: "max(12px, env(safe-area-inset-top)) 16px 12px", md: 4 }, pb: { xs: 1.5, md: 2 }, flex: "0 0 auto", bgcolor: "var(--surface-elevated)", borderBottom: "1px solid var(--border-light)" }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: { xs: 1.25, md: 2 }, minWidth: 0 }}>
            <Avatar src={profileImage || undefined} sx={{ bgcolor: stringToColor(profileName), width: { xs: 52, md: 64 }, height: { xs: 52, md: 64 }, fontSize: { xs: 18, md: 22 }, fontWeight: "700", flexShrink: 0 }}>
              {getInitials(profile)}
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant={isMobile ? "h6" : "h5"} fontWeight="700" color="#1e293b" sx={{ lineHeight: 1.2, overflowWrap: "break-word" }}>
                {profileName}
              </Typography>
              <Typography variant="body2" color="#64748b" sx={{ mt: 0.25, fontSize: { xs: "0.78rem", sm: "0.875rem" }, lineHeight: 1.35, overflowWrap: "anywhere" }}>
                {profile.email || t("common.noEmail")} · {t("common.userId")} #{profile.id || selectedUser?.user_id || "—"}
              </Typography>
              <Box sx={{ display: "flex", gap: 0.75, mt: { xs: 0.75, md: 1 }, flexWrap: "wrap" }}>
                <Chip label={getRoleLabel(profile.role, t)} size="small" sx={{ bgcolor: "#eff6ff", color: "#2563eb", fontWeight: "700" }} />
                <Chip label={accountStatus === "active" ? t("admin.userDetails.accountUsable") : t("admin.userDetails.awaitingReview")} size="small" sx={{ bgcolor: accountStatus === "active" ? "#ecfdf5" : "#fff7ed", color: accountStatus === "active" ? "#047857" : "#c2410c", fontWeight: "700" }} />
              </Box>
            </Box>
          </Box>
          <IconButton onClick={onClose} aria-label={`${t("common.close")} ${t("common.details")}`} sx={{ color: "#64748b", mt: -0.5, mr: -0.75, flexShrink: 0 }}>
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>

      <Box sx={{ flex: "0 0 auto", bgcolor: "var(--surface-elevated)", borderBottom: "1px solid var(--border-light)" }}>
        <Tabs
          value={tab}
          onChange={onTabChange}
          variant={isMobile ? "standard" : "scrollable"}
          scrollButtons="auto"
          sx={{
            px: { xs: 0.5, md: 2 },
            minHeight: { xs: 0, md: 58 },
            "& .MuiTabs-scroller": { overflow: { xs: "visible !important", md: "hidden" } },
            "& .MuiTabs-flexContainer": {
              display: { xs: "grid", md: "flex" },
              gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", md: "none" },
              gap: { xs: 0.75, md: 0 },
              p: { xs: 1, md: 0 },
            },
            "& .MuiTabs-indicator": { display: { xs: "none", md: "block" } },
            "& .MuiTab-root": {
              textTransform: "none",
              fontWeight: "700",
              minHeight: { xs: 42, md: 58 },
              minWidth: { xs: 0, md: 100 },
              maxWidth: { xs: "none", md: 360 },
              px: { xs: 1, md: 2 },
              py: { xs: 0.75, md: 1.5 },
              borderRadius: { xs: 2, md: 0 },
              color: "var(--text-muted)",
              "&.Mui-selected": {
                color: "var(--brand-color)",
                bgcolor: { xs: "var(--surface-subtle)", md: "transparent" },
              },
            },
            "& .MuiTab-root.Mui-selected .admin-user-details-tab-count": {
              color: "var(--brand-color)",
              bgcolor: "var(--brand-soft)",
            },
            "& .MuiTabs-scrollButtons": { display: { xs: "none", md: "flex" } },
          }}
        >
          {tabs.map((item) => (
            <Tab
              key={item.label}
              label={(
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0.75, width: "100%", minWidth: 0 }}>
                  <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.label}</Box>
                  <Box
                    component="span"
                    className="admin-user-details-tab-count"
                    sx={{ minWidth: 24, px: 0.75, py: 0.15, borderRadius: 999, bgcolor: "var(--surface-subtle)", color: "var(--text-muted)", fontSize: "0.72rem", fontWeight: 700, lineHeight: 1.5 }}
                  >
                    {item.count}
                  </Box>
                </Box>
              )}
            />
          ))}
        </Tabs>
      </Box>

      <DialogContent
        className="admin-user-details-dialog-frame"
        dividers
        sx={{
          p: 0,
          bgcolor: "var(--surface-elevated)",
          flex: "1 1 0%",
          height: "auto",
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        <Box
          className="admin-user-details-scroll-area"
          sx={{
            p: { xs: 1.25, md: 4 },
            height: "100%",
            boxSizing: "border-box",
            minHeight: 0,
            overflowY: "auto",
            overflowX: "hidden",
            WebkitOverflowScrolling: "touch",
            overscrollBehaviorY: "contain",
            touchAction: "pan-y",
            pb: isMobile ? "calc(16px + env(safe-area-inset-bottom))" : undefined,
          }}
        >
          {error && <LoadError onRetry={onRetry} />}

          {loading && !detail ? (
            <Box sx={{ minHeight: 420, display: "flex", justifyContent: "center", alignItems: "center" }}>
              <CircularProgress aria-label={t("common.loading")} />
            </Box>
          ) : detail ? (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5, minHeight: "max-content" }}>
              <Box sx={{ order: { xs: 2, md: 1 }, display: "grid", gridTemplateColumns: { xs: "1fr", md: "minmax(0, 1fr) minmax(0, 1fr)" }, gap: 2.5, flexShrink: 0 }}>
                <Paper className="surface-card" elevation={0} sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 3, border: "1px solid var(--border-light)", bgcolor: "var(--card-bg)" }}>
                  <Typography variant="subtitle2" fontWeight="700" color="#64748b" sx={{ mb: 2 }}>{t("admin.userDetails.accountDetails")}</Typography>
                  <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 2 }}>
                    <ProfileField label={t("admin.userDetails.studentId")} value={profile.student_id} fallback={t("common.notSpecified")} />
                    <ProfileField label={t("common.phone")} value={profile.phone} fallback={t("common.notSpecified")} />
                    <ProfileField label={t("admin.userDetails.faculty")} value={profile.faculty} fallback={t("common.notSpecified")} />
                    <ProfileField label={t("admin.userDetails.department")} value={profile.department} fallback={t("common.notSpecified")} />
                    <ProfileField label={t("admin.userDetails.createdAt")} value={formatDateTime(profile.created_at, locale)} fallback={t("common.noData")} />
                    <ProfileField label={t("admin.lastUpdated")} value={formatDateTime(profile.updated_at, locale)} fallback={t("common.noData")} />
                  </Box>
                </Paper>
                <Paper className="surface-card" elevation={0} sx={{ p: { xs: 2, md: 2.5 }, borderRadius: 3, border: "1px solid var(--border-light)", bgcolor: "var(--card-bg)" }}>
                  <Typography variant="subtitle2" fontWeight="700" color="#64748b" sx={{ mb: 2 }}>{t("admin.userDetails.accountStatusAndUsage")}</Typography>
                  <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 2 }}>
                    <Box><Typography variant="caption" color="#94a3b8">{t("common.points")}</Typography><Typography className="theme-colored" variant="h5" fontWeight="700" color={getScoreColor(pointValue)}>{pointValue}/100</Typography></Box>
                    <Box><Typography variant="caption" color="#94a3b8">{t("user.todayPoints")}</Typography><Typography className="theme-colored" variant="h5" fontWeight="700" color="#2563eb">{dailyValue}/100</Typography></Box>
                    <Box><Typography variant="caption" color="#94a3b8">{t("admin.userDetails.bookingAccess")}</Typography><Box sx={{ mt: 0.6 }}><Chip icon={points.booking_allowed ? <CheckCircle /> : <Block />} label={points.booking_allowed ? t("admin.bookingAllowed") : t("admin.bookingBanned")} size="small" sx={{ bgcolor: points.booking_allowed ? "#ecfdf5" : "#fef2f2", color: points.booking_allowed ? "#047857" : "#b91c1c", fontWeight: "700", "& .MuiChip-icon": { color: "inherit" } }} /></Box></Box>
                    <Box><Typography variant="caption" color="#94a3b8">{t("admin.userDetails.historySummary")}</Typography><Typography variant="body2" color="#334155" fontWeight="600" sx={{ mt: 0.7 }}>{summary.total_sessions || 0} {t("admin.userDetails.sessions")} · {summary.total_bookings || 0} {t("admin.userDetails.bookings")}</Typography></Box>
                  </Box>
                </Paper>
              </Box>

              <Paper className="surface-card data-table-shell" elevation={0} sx={{ order: { xs: 1, md: 2 }, flexShrink: 0, borderRadius: 3, border: "1px solid var(--border-light)", overflow: "hidden", bgcolor: "var(--card-bg)" }}>
                <Box sx={{ p: { xs: 1.25, md: 1 } }}>
                  <Box sx={historyPanelScrollSx}>
                    {tab === 0 && <UserBookings rows={detail.bookings || []} t={t} locale={locale} />}
                    {tab === 1 && <UserSessions rows={detail.sessions || []} t={t} locale={locale} />}
                    {tab === 2 && <UserProgramUsage rows={detail.program_usage || []} t={t} locale={locale} />}
                    {tab === 3 && <UserPointHistory pointLogs={detail.point_history || []} dailyScores={detail.daily_scores || []} t={t} locale={locale} />}
                    {tab === 4 && <UserViolations rows={detail.violations || []} t={t} locale={locale} />}
                  </Box>
                </Box>
              </Paper>
            </Box>
          ) : null}
        </Box>
      </DialogContent>
    </Dialog>
  );
}
