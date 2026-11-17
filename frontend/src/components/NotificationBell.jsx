import React, { useMemo, useState } from "react";
import { Avatar, Badge, Box, Button, IconButton, Popover, Typography } from "@mui/material";
import { DeleteSweep, Notifications } from "@mui/icons-material";
import { useLanguage } from "../context/language-context.js";
import { formatDateTime } from "../utils/dateFormat";
import { getPointReasonLabel } from "../utils/pointReason";
import { getTicketReplyStatusPresentation } from "../utils/ticketStatus.js";
import { useNotificationReadState } from "../context/useNotificationReadState.js";
import { useNotificationClearState } from "../context/useNotificationClearState.js";
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
  const { logs, loading, ready, error, refresh } = useNotifications(loadNotifications);
  const [lastSeenPointLogId, markPointNotificationsRead] = useNotificationReadState(currentUser?.email);
  const [lastSeenTicketReplyId, markTicketNotificationsRead] = useNotificationReadState(currentUser?.email, "tickets");
  const [clearedPointThroughId, clearPointNotificationsThrough] = useNotificationClearState(currentUser?.email);
  const [clearedTicketThroughId, clearTicketNotificationsThrough] = useNotificationClearState(currentUser?.email, "tickets");

  const pointLogs = useMemo(
    () => logs.filter((log) => log.notification_kind !== "ticket_reply"),
    [logs],
  );
  const ticketReplies = useMemo(
    () => logs.filter((log) => log.notification_kind === "ticket_reply"),
    [logs],
  );

  const visiblePointLogs = useMemo(
    () => pointLogs.filter((log) => log.id > clearedPointThroughId).slice(0, 10),
    [clearedPointThroughId, pointLogs],
  );
  const visibleTicketReplies = useMemo(
    () => ticketReplies.filter((reply) => reply.id > clearedTicketThroughId).slice(0, 10),
    [clearedTicketThroughId, ticketReplies],
  );

  const notifications = useMemo(
    () => [
      ...visiblePointLogs.map((log) => {
        const isPositive = log.change > 0;
        const reasonLabel = getPointReasonLabel(log.reason, t);
        return {
          id: `point:${log.id}`,
          title: `${reasonLabel} ${isPositive ? "+" : ""}${log.change} ${t("common.points")}`,
          subtitle: log.note || "—",
          createdAt: log.created_at,
          time: formatDateTime(log.created_at, t("common.locale"), {
            includeSeconds: true,
          }),
          color: isPositive ? "#16a34a" : "#dc2626",
          iconText: isPositive ? "+" : "-",
          unread: log.id > lastSeenPointLogId,
        };
      }),
      ...visibleTicketReplies.map((reply) => {
        const statusPresentation = getTicketReplyStatusPresentation(reply.status);
        const replyMessage = reply.message || "";
        const messagePreview = replyMessage.length > 180
          ? `${replyMessage.slice(0, 180)}…`
          : replyMessage;
        return {
          id: `ticket:${reply.id}`,
          title: `${t("common.ticketReplyNotification")}: ${reply.subject}`,
          subtitle: `${messagePreview} · ${t("common.status")}: ${t(statusPresentation.labelKey)}`,
          createdAt: reply.created_at,
          time: formatDateTime(reply.created_at, t("common.locale"), {
            includeSeconds: true,
          }),
          color: "#2563eb",
          iconText: "T",
          unread: reply.id > lastSeenTicketReplyId,
        };
      }),
    ].sort((left, right) =>
      (Date.parse(right.createdAt) || 0) - (Date.parse(left.createdAt) || 0),
    ),
    [lastSeenPointLogId, lastSeenTicketReplyId, t, visiblePointLogs, visibleTicketReplies],
  );

  const handleNotificationClick = (event) => {
    setAnchorEl(event.currentTarget);
    refresh();
    const latestPointId = visiblePointLogs.reduce((latest, log) => Math.max(latest, Number(log.id) || 0), 0);
    const latestTicketId = visibleTicketReplies.reduce((latest, reply) => Math.max(latest, Number(reply.id) || 0), 0);
    if (latestPointId > lastSeenPointLogId) markPointNotificationsRead(latestPointId);
    if (latestTicketId > lastSeenTicketReplyId) markTicketNotificationsRead(latestTicketId);
  };

  const handleClearNotifications = () => {
    const latestPointId = pointLogs.reduce((latest, log) => Math.max(latest, Number(log.id) || 0), 0);
    const latestTicketId = ticketReplies.reduce((latest, reply) => Math.max(latest, Number(reply.id) || 0), 0);
    if (latestPointId) {
      markPointNotificationsRead(latestPointId);
      clearPointNotificationsThrough(latestPointId);
    }
    if (latestTicketId) {
      markTicketNotificationsRead(latestTicketId);
      clearTicketNotificationsThrough(latestTicketId);
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
            justifyContent: "space-between",
            gap: 1,
            px: 2.5,
            py: 2,
            flexShrink: 0,
          }}
        >
          <Typography fontSize="16px" fontWeight="600">
            {t("common.notifications")}
          </Typography>
          <Button
            color="error"
            size="small"
            startIcon={<DeleteSweep fontSize="small" />}
            onClick={handleClearNotifications}
            disabled={notifications.length === 0}
            aria-label={t("common.clearNotifications")}
            sx={{ ml: "auto", minWidth: 0, whiteSpace: "nowrap", textTransform: "none" }}
          >
            {t("common.clearNotifications")}
          </Button>
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
                    sx={{
                      color: "var(--text-gray)",
                      mt: 0.3,
                      display: "-webkit-box",
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      overflowWrap: "anywhere",
                    }}
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
