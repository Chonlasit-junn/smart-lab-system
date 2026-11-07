import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  Alert,
  Avatar,
  Badge,
  Box,
  Button,
  CircularProgress,
  IconButton,
  Popover,
  Typography,
} from "@mui/material";
import { DeleteSweep, Notifications, PersonAddAlt1, Star, SupportAgent } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/auth-context";
import { useLanguage } from "../context/language-context.js";
import { readNotificationToken } from "../utils/notificationClient.js";
import {
  readAdminNotificationState,
  writeAdminNotificationState,
} from "../utils/adminNotificationState.js";
import { formatDateTime } from "../utils/dateFormat";

const API_URL = import.meta.env.VITE_API_URL;
const ADMIN_NOTIFICATION_PATHS = {
  guest_approval: "/verify-users",
  ticket: "/ticket",
  point_request: "/admin/points",
};
const NOTIFICATION_PRESENTATION = {
  guest_approval: { title: "admin.notificationGuestApproval", icon: PersonAddAlt1, color: "#2563eb" },
  ticket: { title: "admin.notificationTicket", icon: SupportAgent, color: "#d97706" },
  point_request: { title: "admin.notificationPointRequest", icon: Star, color: "#7c3aed" },
};

function getStorage() {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export default function AdminNotificationBell({
  className = "admin-notification-button",
  iconColor = "#64748b",
  compact = false,
}) {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const { t } = useLanguage();
  const email = currentUser?.email || "";
  const requestRef = useRef(null);
  const itemsRef = useRef([]);
  const [anchorEl, setAnchorEl] = useState(null);
  const [items, setItems] = useState([]);
  const [itemsOwnerEmail, setItemsOwnerEmail] = useState(email);
  const [localState, setLocalState] = useState(() => readAdminNotificationState(getStorage(), email));
  const [localStateOwnerEmail, setLocalStateOwnerEmail] = useState(email);
  const [loading, setLoading] = useState(Boolean(email));
  const [error, setError] = useState(false);

  const fetchNotifications = useCallback(async ({ silent = false } = {}) => {
    if (!email) {
      setItems([]);
      itemsRef.current = [];
      setLoading(false);
      return;
    }

    const token = readNotificationToken(email);
    if (!token) {
      setError(true);
      setLoading(false);
      return;
    }

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    if (!silent || itemsRef.current.length === 0) setLoading(true);
    setError(false);

    try {
      const response = await axios.get(`${API_URL}/admin/notifications`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });
      if (requestRef.current !== controller) return;
      const nextItems = Array.isArray(response.data?.data) ? response.data.data : [];
      itemsRef.current = nextItems;
      setItems(nextItems);
      setItemsOwnerEmail(email);
    } catch (requestError) {
      if (requestRef.current === controller && !axios.isCancel(requestError)) setError(true);
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  }, [email]);

  useEffect(() => {
    setItems([]);
    itemsRef.current = [];
    setLocalState(readAdminNotificationState(getStorage(), email));
    setItemsOwnerEmail(email);
    setLocalStateOwnerEmail(email);
    setError(false);
    fetchNotifications();
    return () => {
      requestRef.current?.abort();
      requestRef.current = null;
    };
  }, [email, fetchNotifications]);

  const accountState = localStateOwnerEmail === email
    ? localState
    : readAdminNotificationState(getStorage(), email);
  const dismissedIds = useMemo(() => new Set(accountState.dismissed), [accountState.dismissed]);
  const seenIds = useMemo(() => new Set(accountState.seen), [accountState.seen]);
  const visibleItems = useMemo(
    () => itemsOwnerEmail === email
      ? items.filter((item) => !dismissedIds.has(String(item.id)))
      : [],
    [dismissedIds, email, items, itemsOwnerEmail],
  );
  const unreadCount = visibleItems.reduce(
    (count, item) => count + (seenIds.has(String(item.id)) ? 0 : 1),
    0,
  );

  const saveState = useCallback((nextState) => {
    writeAdminNotificationState(getStorage(), email, nextState);
    setLocalState(nextState);
    setLocalStateOwnerEmail(email);
  }, [email]);

  const markSeen = useCallback((ids) => {
    const nextState = {
      ...accountState,
      seen: [...new Set([...accountState.seen, ...ids])],
    };
    saveState(nextState);
  }, [accountState, saveState]);

  const handleOpen = (event) => {
    setAnchorEl(event.currentTarget);
    markSeen(visibleItems.map((item) => String(item.id)));
    fetchNotifications({ silent: true });
  };

  const handleClear = () => {
    const ids = visibleItems.map((item) => String(item.id));
    if (ids.length === 0) return;
    saveState({
      dismissed: [...new Set([...accountState.dismissed, ...ids])],
      seen: [...new Set([...accountState.seen, ...ids])],
    });
  };

  const handleItemClick = (item) => {
    markSeen([String(item.id)]);
    setAnchorEl(null);
    const path = ADMIN_NOTIFICATION_PATHS[item.kind];
    if (path) navigate(path);
  };

  return (
    <>
      <IconButton
        className={className}
        onClick={handleOpen}
        aria-label={t("common.notifications")}
        aria-haspopup="true"
        aria-expanded={Boolean(anchorEl)}
      >
        <Badge badgeContent={unreadCount} max={99} color="error" invisible={unreadCount === 0}>
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
            width: 390,
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
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2.5, py: 2 }}>
          <Typography fontSize="16px" fontWeight="600" sx={{ flex: 1 }}>
            {t("common.notifications")}
          </Typography>
          <Button
            size="small"
            startIcon={<DeleteSweep fontSize="small" />}
            onClick={handleClear}
            disabled={visibleItems.length === 0}
            aria-label={t("common.clearNotifications")}
            sx={{ minWidth: 0, whiteSpace: "nowrap", textTransform: "none" }}
          >
            {t("common.clearNotifications")}
          </Button>
        </Box>

        <Box sx={{ overflowY: "auto", px: 1, pb: 1 }}>
          {error && (
            <Alert
              severity="error"
              action={<Button color="inherit" size="small" onClick={() => fetchNotifications()}>{t("common.retry")}</Button>}
              sx={{ mb: 1, fontSize: 13 }}
            >
              {t("common.loadFailed")}
            </Alert>
          )}
          {loading && visibleItems.length === 0 ? (
            <Box role="status" sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 1.5, p: 3 }}>
              <CircularProgress size={18} />
              <Typography fontSize="13px" sx={{ color: "var(--text-gray)" }}>{t("common.loading")}</Typography>
            </Box>
          ) : visibleItems.length === 0 && !error ? (
            <Box sx={{ py: 4, textAlign: "center" }}>
              <Typography fontSize="13px" sx={{ color: "var(--text-gray)" }}>
                {t("common.noNotifications")}
              </Typography>
            </Box>
          ) : (
            visibleItems.map((item) => {
              const presentation = NOTIFICATION_PRESENTATION[item.kind];
              if (!presentation) return null;
              const Icon = presentation.icon;
              const subtitle = item.kind === "point_request"
                ? [item.user_name, `${item.requested_points} ${t("common.points")}`, item.summary].filter(Boolean).join(" · ")
                : [item.user_name, item.summary].filter(Boolean).join(" · ");
              return (
                <Box
                  component="button"
                  type="button"
                  key={item.id}
                  onClick={() => handleItemClick(item)}
                  aria-label={`${t(presentation.title)}: ${subtitle}`}
                  sx={{
                    width: "100%",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 1.5,
                    px: 1.5,
                    py: 1.25,
                    border: 0,
                    borderRadius: 2,
                    textAlign: "left",
                    color: "inherit",
                    bgcolor: "transparent",
                    cursor: "pointer",
                    "&:hover": { bgcolor: "var(--surface-subtle)" },
                  }}
                >
                  <Avatar sx={{ bgcolor: presentation.color, width: 36, height: 36 }}>
                    <Icon sx={{ fontSize: 19 }} />
                  </Avatar>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography fontSize={compact ? "13px" : "14px"} fontWeight="600" noWrap>
                      {t(presentation.title)}
                    </Typography>
                    <Typography fontSize="12px" sx={{ color: "var(--text-gray)" }} noWrap title={subtitle}>
                      {subtitle || "—"}
                    </Typography>
                    <Typography fontSize="11px" sx={{ color: "var(--text-muted)", mt: 0.25 }}>
                      {formatDateTime(item.created_at, t("common.locale"), { includeSeconds: false, fallback: "—" })}
                    </Typography>
                  </Box>
                  {!seenIds.has(String(item.id)) && (
                    <Box aria-hidden="true" sx={{ width: 8, height: 8, mt: 0.8, borderRadius: "50%", bgcolor: "#2563eb", flexShrink: 0 }} />
                  )}
                </Box>
              );
            })
          )}
        </Box>
      </Popover>
    </>
  );
}
