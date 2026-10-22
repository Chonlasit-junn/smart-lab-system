import React, { useMemo, useState } from "react";
import { Avatar, Badge, Box, IconButton, Popover, Typography } from "@mui/material";
import { Notifications } from "@mui/icons-material";
import { useLanguage } from "../context/language-context.js";
import { formatDateTime } from "../utils/dateFormat";
import { getPointReasonLabel } from "../utils/pointReason";
import { useNotificationReadState } from "../context/useNotificationReadState.js";
import { useNotifications } from "../context/useNotifications.js";
import { useAuth } from "../context/auth-context";
import LoadError from "./LoadError";

export default function NotificationBell({
  className = "header-notification-button",
  iconColor = "#111827",
  loadNotifications = true,
  compact = false,
}) {
  const { currentUser } = useAuth();
  const { t } = useLanguage();
  const [anchorEl, setAnchorEl] = useState(null);
  const { logs: pointLogs, loading, ready, error, refresh } = useNotifications(loadNotifications);
  const [lastSeenLogId, markNotificationsRead] = useNotificationReadState(currentUser?.email);

  const visiblePointLogs = useMemo(
    () => pointLogs.slice(0, 10),
    [pointLogs],
  );

  const notifications = useMemo(
    () =>
      visiblePointLogs.map((log) => {
        const isPositive = log.change > 0;
        const reasonLabel = getPointReasonLabel(log.reason, t);
        return {
          id: log.id,
          title: `${reasonLabel} ${isPositive ? "+" : ""}${log.change} ${t("common.points")}`,
          subtitle: log.note || "—",
          time: formatDateTime(log.created_at, t("common.locale"), {
            includeSeconds: true,
          }),
          color: isPositive ? "#16a34a" : "#dc2626",
          iconText: isPositive ? "+" : "-",
          unread: log.id > lastSeenLogId,
        };
      }),
    [lastSeenLogId, t, visiblePointLogs],
  );

  const handleNotificationClick = (event) => {
    setAnchorEl(event.currentTarget);
    refresh();
    if (visiblePointLogs.length === 0) return;

    const latestId = Math.max(...visiblePointLogs.map((log) => log.id));
    if (latestId > lastSeenLogId) {
      markNotificationsRead(latestId);
    }
  };

  return (
    <>
      <IconButton
        className={className}
        onClick={handleNotificationClick}
        aria-label={t("common.notifications")}
        aria-haspopup="true"
        aria-expanded={anchorEl ? "true" : undefined}
      >
        <Badge
          variant="dot"
          color="error"
          overlap="circular"
          invisible={!notifications.some((notification) => notification.unread)}
        >
          <Notifications sx={{ color: iconColor }} />
        </Badge>
      </IconButton>

      <Popover
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        PaperProps={{
          sx: {
            mt: 1.5,
            width: 380,
            maxWidth: "92vw",
            maxHeight: 520,
            borderRadius: compact ? 3 : "var(--radius-modal)",
            bgcolor: "var(--card-bg)",
            color: "var(--text-dark)",
            border: "1px solid var(--border-light)",
            boxShadow: "0 20px 45px rgba(15,23,42,0.35)",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          },
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            px: 2.5,
            py: 2,
            flexShrink: 0,
          }}
        >
          <Typography fontSize="16px" fontWeight="600">
            {t("common.notifications")}
          </Typography>
        </Box>

        <Box sx={{ overflowY: "auto", px: 1, pb: 1 }}>
          {error && <LoadError onRetry={() => refresh(true)} />}
          {loadNotifications && !ready && !error ? (
            <Typography role="status" sx={{ p: 3, color: "var(--text-gray)" }}>{t("common.loading")}</Typography>
          ) : notifications.length === 0 && !error && !loading ? (
            <Box sx={{ py: 4, textAlign: "center" }}>
              <Typography fontSize="13px" sx={{ color: "var(--text-gray)" }}>
                {t("common.noNotifications")}
              </Typography>
            </Box>
          ) : (
            notifications.map((notification) => (
              <Box
                key={notification.id}
                sx={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 1.5,
                  px: 1.5,
                  py: 1,
                  borderRadius: 2,
                  cursor: "pointer",
                  "&:hover": { bgcolor: "var(--surface-subtle)" },
                }}
              >
                <Box sx={{ pt: 1.2 }}>
                  {notification.unread ? (
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        bgcolor: "#2563eb",
                      }}
                    />
                  ) : (
                    <Box sx={{ width: 8, height: 8 }} />
                  )}
                </Box>

                <Avatar
                  sx={{
                    bgcolor: notification.color,
                    width: 36,
                    height: 36,
                    fontSize: 14,
                  }}
                >
                  {notification.iconText}
                </Avatar>

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography
                    fontSize={compact ? "13.5px" : "14px"}
                    fontWeight="500"
                    sx={{
                      color: "var(--text-dark)",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {notification.title}
                  </Typography>
                  <Typography
                    fontSize={compact ? "12px" : "13px"}
                    fontWeight={compact ? undefined : "400"}
                    sx={{ color: "var(--text-gray)", mt: 0.3 }}
                  >
                    {notification.subtitle}
                  </Typography>
                  <Typography
                    fontSize={compact ? "12px" : "12.5px"}
                    sx={{ color: "var(--text-muted)", mt: 0.3 }}
                  >
                    {notification.time}
                  </Typography>
                </Box>
              </Box>
            ))
          )}
        </Box>
      </Popover>
    </>
  );
}
