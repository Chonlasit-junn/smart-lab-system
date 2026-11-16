import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Avatar,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  CardActionArea,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Typography,
} from "@mui/material";
import {
  ArrowBack,
  Computer,
  DeleteOutline,
  ExpandMore,
  LocationOn,
  PeopleAlt,
  PauseCircleOutline,
  PlayArrow,
  ShieldOutlined,
} from "@mui/icons-material";
import axios from "axios";
import AdminNavigation from "../components/AdminNavigation";
import { authConfig } from "../utils/auth";
import { getApiErrorMessage } from "../utils/apiErrorMessage";
import { formatDateTime } from "../utils/dateFormat";
import { useLanguage } from "../context/language-context.js";
import AdminNotificationBell from "../components/AdminNotificationBell";
import AdminAccountMenu from "../components/AdminAccountMenu";
import LoadError from "../components/LoadError";
import { PageContentLoadingState } from "../components/PageLoadingState";

const API_URL = import.meta.env.VITE_API_URL;

const MAINTENANCE_DURATIONS = [15, 30, 60, 120];
const AGENT_ONLINE_WINDOW_MS = 90_000;

export default function AdminDevices() {
  const { t } = useLanguage();
  const devicesControllerRef = useRef(null);
  const [devices, setDevices] = useState([]);
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [selectedLabId, setSelectedLabId] = useState(null);
  const [controllingDeviceId, setControllingDeviceId] = useState(null);
  const [removingDeviceId, setRemovingDeviceId] = useState(null);
  const [deviceToRemove, setDeviceToRemove] = useState(null);
  const [maintenanceDurations, setMaintenanceDurations] = useState({});
  const [notice, setNotice] = useState({ open: false, message: "", severity: "success" });

  const showNotice = (message, severity = "success") => {
    setNotice({ open: true, message, severity });
  };

  const fetchData = useCallback(async ({ silent = false } = {}) => {
    devicesControllerRef.current?.abort();
    const controller = new AbortController();
    devicesControllerRef.current = controller;

    try {
      if (!silent) {
        setLoading(true);
        setLoadFailed(false);
      }
      const requestConfig = { ...authConfig(), signal: controller.signal };
      const [devicesResponse, labsResponse] = await Promise.all([
        axios.get(`${API_URL}/admin/lab-devices`, requestConfig),
        axios.get(`${API_URL}/labs`, { signal: controller.signal }),
      ]);
      if (devicesControllerRef.current !== controller) return;
      setDevices(devicesResponse.data?.data || []);
      setLabs(labsResponse.data?.data || []);
      setLoadFailed(false);
    } catch (requestError) {
      if (axios.isCancel(requestError) || devicesControllerRef.current !== controller) return;
      if (!silent) setLoadFailed(true);
    } finally {
      if (devicesControllerRef.current === controller) {
        devicesControllerRef.current = null;
        if (!silent) setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    document.title = `${t("admin.devicesTitle")} | Smart Lab Admin`;
  }, [t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => () => devicesControllerRef.current?.abort(), []);

  useEffect(() => {
    const intervalId = window.setInterval(() => fetchData({ silent: true }), 15_000);
    return () => window.clearInterval(intervalId);
  }, [fetchData]);

  const handleAgentControl = async (device) => {
    const nextStatus = device.status === "maintenance" ? "active" : "maintenance";
    try {
      setControllingDeviceId(device.id);
      await axios.put(
        `${API_URL}/admin/lab-devices/${device.id}`,
        {
          status: nextStatus,
          ...(nextStatus === "maintenance"
            ? { maintenance_minutes: maintenanceDurations[device.id] || 30 }
            : {}),
        },
        authConfig(),
      );
      showNotice(t(nextStatus === "maintenance" ? "admin.pauseRequested" : "admin.resumeRequested"));
      await fetchData({ silent: true });
    } catch (requestError) {
      showNotice(getApiErrorMessage(requestError, t, t("admin.deviceSaveFailed")), "error");
    } finally {
      setControllingDeviceId(null);
    }
  };

  const handleRemoveDevice = async () => {
    if (!deviceToRemove) return;
    const device = deviceToRemove;
    try {
      setRemovingDeviceId(device.id);
      await axios.delete(`${API_URL}/admin/lab-devices/${device.id}`, authConfig());
      setDeviceToRemove(null);
      showNotice(t("admin.deviceRemoved"));
      await fetchData();
    } catch (requestError) {
      const message = requestError.response?.status === 409
        ? t("admin.deviceRemoveActiveSession")
        : getApiErrorMessage(requestError, t, t("admin.deviceRemoveFailed"));
      showNotice(message, "error");
    } finally {
      setRemovingDeviceId(null);
    }
  };

  const labCards = useMemo(() => {
    const grouped = new Map();
    labs.forEach((lab) => grouped.set(String(lab.id), {
      ...lab,
      gatekeepers: [],
      agents: [],
    }));
    devices.forEach((device) => {
      const key = String(device.lab?.id ?? "unassigned");
      if (!grouped.has(key)) {
        grouped.set(key, {
          ...(device.lab || { id: key, code: t("admin.unassignedLab"), name: "" }),
          gatekeepers: [],
          agents: [],
        });
      }
      const group = grouped.get(key);
      const isGatekeeper = device.device_type === "gatekeeper"
        || device.device_id?.startsWith("gatekeeper-");
      group[isGatekeeper ? "gatekeepers" : "agents"].push(device);
    });
    return [...grouped.values()].sort((a, b) =>
      String(a.code || "").localeCompare(String(b.code || "")),
    );
  }, [devices, labs, t]);

  const selectedLab = useMemo(
    () => labCards.find((lab) => String(lab.id) === String(selectedLabId)) || null,
    [labCards, selectedLabId],
  );

  const getAgentControlView = (device) => {
    const hasControlProtocol = Number(device.agent_control_version || 0) >= 1;
    const lastSeenAt = device.last_seen_at ? new Date(device.last_seen_at).getTime() : 0;
    const isOnline = lastSeenAt > 0 && Date.now() - lastSeenAt < AGENT_ONLINE_WINDOW_MS;
    const requestedAt = device.control_requested_at ? new Date(device.control_requested_at).getTime() : 0;
    const acknowledgedAt = device.agent_control_ack_at ? new Date(device.agent_control_ack_at).getTime() : 0;
    const acknowledged = device.agent_control_status === device.status
      && (!requestedAt || acknowledgedAt >= requestedAt);

    if (!hasControlProtocol) return { label: t("admin.agentUpdateRequired"), color: "warning" };
    if (!isOnline) return { label: t("admin.agentOffline"), color: "default" };
    if (!acknowledged) {
      return {
        label: t(device.status === "maintenance" ? "admin.pausePending" : "admin.resumePending"),
        color: "warning",
      };
    }
    return {
      label: t(device.status === "maintenance" ? "admin.agentPaused" : "admin.agentActive"),
      color: device.status === "maintenance" ? "info" : "success",
    };
  };

  const renderDeviceCard = (device, kind) => {
    const isAgent = kind === "agent";
    const controlView = isAgent ? getAgentControlView(device) : null;
    const isBusy = controllingDeviceId === device.id
      || removingDeviceId === device.id;
    const deviceStatus = isAgent
      ? controlView
      : {
        label: t(`common.${device.status}`),
        color: device.status === "active" ? "success" : "default",
      };

    return (
      <Paper
        key={device.id}
        variant="outlined"
        sx={{
          p: { xs: 1.5, sm: 2.25 },
          borderRadius: 3,
          minWidth: 0,
          bgcolor: "var(--card-bg)",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25, minWidth: 0 }}>
          <Avatar
            sx={{
              width: 38,
              height: 38,
              flexShrink: 0,
              bgcolor: "var(--surface-neutral)",
              color: "var(--text-muted)",
            }}
          >
            {isAgent ? <Computer fontSize="small" /> : <ShieldOutlined fontSize="small" />}
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography fontWeight={700} sx={{ lineHeight: 1.35, overflowWrap: "anywhere" }}>
              {device.device_name}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25, overflowWrap: "anywhere" }}>
              {device.device_id}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>
              {device.device_mac || t("common.noMac")}
            </Typography>
          </Box>
          <Chip
            size="small"
            color={deviceStatus.color}
            label={deviceStatus.label}
            sx={{ flexShrink: 0, maxWidth: { xs: "42%", sm: "none" }, ml: "auto" }}
          />
        </Box>

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "minmax(0, 1fr)",
              sm: isAgent ? "repeat(2, minmax(0, 1fr))" : "minmax(0, 1fr)",
              lg: isAgent ? "repeat(2, minmax(0, 1fr))" : "minmax(0, 1fr)",
            },
            gap: 1.25,
            mt: 2,
          }}
        >
          <Box sx={{ minWidth: 0, p: 1.25, border: "1px solid var(--border-light)", borderRadius: 2, bgcolor: "var(--surface-subtle)" }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              {isAgent ? t("admin.agentVersion") : t("admin.lastSignal")}
            </Typography>
            <Typography variant="body2" sx={{ pt: 0.75, overflowWrap: "anywhere" }}>
              {isAgent
                ? device.agent_version || t("common.source")
                : formatDateTime(device.last_seen_at, t("common.locale"), { fallback: "" }) || t("common.noSignal")}
            </Typography>
            {isAgent && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                {t("admin.lastSignal")}: {formatDateTime(device.last_seen_at, t("common.locale"), { fallback: "" }) || t("common.noSignal")}
              </Typography>
            )}
          </Box>
          {isAgent && (device.status === "maintenance" && device.maintenance_until ? (
            <Box sx={{ minWidth: 0, p: 1.25, border: "1px solid var(--border-light)", borderRadius: 2, bgcolor: "var(--surface-subtle)" }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                {t("admin.maintenanceUntil")}
              </Typography>
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                {formatDateTime(device.maintenance_until, t("common.locale"), { fallback: "" })}
              </Typography>
            </Box>
          ) : (
            <Box sx={{ minWidth: 0, p: 1.25, border: "1px solid var(--border-light)", borderRadius: 2, bgcolor: "var(--surface-subtle)" }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                {t("admin.maintenanceDuration")}
              </Typography>
              <FormControl size="small" fullWidth>
                <Select
                  value={maintenanceDurations[device.id] || 30}
                  onChange={(event) => setMaintenanceDurations((current) => ({
                    ...current,
                    [device.id]: Number(event.target.value),
                  }))}
                  inputProps={{ "aria-label": `${t("admin.maintenanceDuration")} ${device.device_name}` }}
                >
                  {MAINTENANCE_DURATIONS.map((minutes) => (
                    <MenuItem key={minutes} value={minutes}>{minutes} {t("admin.minutes")}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
          ))}
        </Box>

        {isAgent && Number(device.agent_control_version || 0) < 1 && (
          <Alert severity="info" sx={{ mt: 1.5, py: 0, borderRadius: 2 }}>
            {t("admin.agentUpdateForControl")}
          </Alert>
        )}

        <Divider sx={{ my: 1.5, borderColor: "var(--border-light)" }} />

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "minmax(0, 1fr)",
              sm: `repeat(${isAgent ? 2 : 1}, minmax(140px, auto))`,
            },
            gap: 1,
            width: { xs: "100%", sm: "fit-content" },
            ml: { sm: "auto" },
          }}
        >
          {isAgent && (
            <Button
              size="small"
              variant="outlined"
              color={device.status === "maintenance" ? "success" : "warning"}
              startIcon={controllingDeviceId === device.id
                ? <CircularProgress size={15} color="inherit" />
                : device.status === "maintenance" ? <PlayArrow /> : <PauseCircleOutline />}
              disabled={isBusy || (device.status !== "maintenance" && Number(device.agent_control_version || 0) < 1)}
              onClick={() => handleAgentControl(device)}
              sx={{ textTransform: "none", minHeight: 40 }}
            >
              {controllingDeviceId === device.id
                ? t("admin.savingDevice")
                : t(device.status === "maintenance" ? "admin.resumeAgent" : "admin.pauseAgent")}
            </Button>
          )}
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<DeleteOutline />}
            disabled={isBusy}
            onClick={() => setDeviceToRemove(device)}
            sx={{ textTransform: "none", minHeight: 40 }}
          >
            {t("common.delete")}
          </Button>
        </Box>
      </Paper>
    );
  };

  const renderLabDeviceSection = (lab, kind) => {
    const isGatekeeper = kind === "gatekeeper";
    const labDevices = isGatekeeper ? lab.gatekeepers : lab.agents;

    return (
      <Paper key={kind} elevation={0} sx={{ px: { xs: 1.5, sm: 2.25 }, border: "1px solid var(--border-light)", borderRadius: 3, bgcolor: "var(--card-bg)" }}>
      <Accordion disableGutters defaultExpanded elevation={0} sx={{ bgcolor: "transparent", "&:before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMore />} sx={{ px: 0, minHeight: 58, "& .MuiAccordionSummary-content": { my: 1 } }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            {isGatekeeper
              ? <ShieldOutlined fontSize="small" color="primary" />
              : <Computer fontSize="small" color="primary" />}
            <Typography fontWeight={700}>
              {t(isGatekeeper ? "admin.gatekeeperSection" : "admin.labAgentsSection")}
            </Typography>
            <Chip size="small" label={labDevices.length} sx={{ fontWeight: 700 }} />
          </Box>
        </AccordionSummary>
        <AccordionDetails sx={{ px: 0, pt: 0, pb: 2 }}>
          <Box sx={{ display: "grid", gap: 1.25 }}>
            {labDevices.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t(isGatekeeper ? "admin.noGatekeepers" : "admin.noAgents")}
              </Typography>
            ) : labDevices.map((device) => renderDeviceCard(device, kind))}
          </Box>
        </AccordionDetails>
      </Accordion>
      </Paper>
    );
  };

  return (
    <Box className="app-layout admin-layout" sx={{ display: "flex", minHeight: "100vh", bgcolor: "#fcfdfe", fontFamily: "var(--font-family-ui)" }}>
      <Box className="sidebar admin-sidebar" sx={{ width: "var(--sidebar-width)", bgcolor: "#f0f7ff", borderRight: "1px solid #e2efff", display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh", zIndex: 10 }}>
        <Box className="sidebar-logo" sx={{ p: 4, display: "flex", gap: 2, alignItems: "center" }}>
          <Box className="admin-brand-mark" sx={{ bgcolor: "#000", p: 1, borderRadius: 2.5, display: "flex", boxShadow: "0 4px 10px rgba(0,0,0,0.2)" }}>
            <Computer sx={{ color: "white", fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h6" fontWeight="700" sx={{ color: "#0f172a", letterSpacing: "-0.5px" }}>Smart Lab</Typography>
            <Typography variant="caption" sx={{ color: "#64748b", fontWeight: "400", display: "block", mt: -0.5 }}>{t("common.adminDashboard")}</Typography>
          </Box>
        </Box>
        <AdminNavigation />
      </Box>

      <Box className="main-area admin-main-area" sx={{ flex: 1, display: "flex", flexDirection: "column", overflowX: "hidden" }}>
        <Box className="top-header admin-top-header admin-devices-top-header" sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 6, py: 1, bgcolor: "white", borderBottom: "1px solid #e2e8f0" }}>
          <Typography className="admin-devices-header-title" variant="h5" fontWeight="700" sx={{ color: "#1e293b", letterSpacing: "-1px" }}>{t("admin.devicesTitle")}</Typography>
          <Box className="admin-devices-header-actions" sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <AdminNotificationBell
              className="admin-notification-button"
              iconColor="#64748b"
            />
            <Divider className="admin-header-divider admin-devices-header-divider" orientation="vertical" flexItem sx={{ height: 30, my: "auto", bgcolor: "#e2e8f0" }} />
            <AdminAccountMenu summaryClassName="admin-devices-header-summary" />
          </Box>
        </Box>

        <Box className="content-area admin-content-area page-content admin-devices-content" sx={{ p: { xs: 2, md: 5 }, flex: 1 }}>
          {loadFailed && <LoadError onRetry={fetchData} />}
          {loading ? (
            <PageContentLoadingState type="devices" />
          ) : (
            selectedLab ? (
              <Box>
                <Button
                  startIcon={<ArrowBack />}
                  onClick={() => setSelectedLabId(null)}
                  sx={{
                    mb: 2.5,
                    color: "#64748b",
                    fontWeight: 600,
                    textTransform: "none",
                    "&:hover": { color: "#0f172a", bgcolor: "transparent" },
                  }}
                >
                  {t("admin.backToAllRooms")}
                </Button>

                <Paper
                  elevation={0}
                  sx={{
                    display: "flex",
                    alignItems: { xs: "flex-start", sm: "center" },
                    gap: 2,
                    p: { xs: 2, sm: 3 },
                    mb: 3,
                    borderRadius: 3,
                    border: "1px solid #e2e8f0",
                    bgcolor: "white",
                  }}
                >
                  <Avatar sx={{ bgcolor: "#f1f5f9", color: "#64748b", width: 56, height: 56 }}>
                    <Computer />
                  </Avatar>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="h5" fontWeight={700} color="#1e293b" sx={{ overflowWrap: "anywhere" }}>
                      {selectedLab.code}
                    </Typography>
                    <Typography color="#64748b" sx={{ overflowWrap: "anywhere" }}>{selectedLab.name}</Typography>
                    {selectedLab.location && (
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.75, color: "#64748b" }}>
                        <LocationOn sx={{ fontSize: 17 }} />
                        <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{selectedLab.location}</Typography>
                      </Box>
                    )}
                  </Box>
                  <Chip
                    size="small"
                    label={t(selectedLab.status === "active" ? "common.active" : "admin.disabled")}
                    sx={{
                      flexShrink: 0,
                      bgcolor: selectedLab.status === "active" ? "#dcfce7" : "#fee2e2",
                      color: selectedLab.status === "active" ? "#15803d" : "#dc2626",
                      fontWeight: 700,
                    }}
                  />
                </Paper>

                <Box sx={{ display: "grid", gap: 2 }}>
                  {renderLabDeviceSection(selectedLab, "gatekeeper")}
                  {renderLabDeviceSection(selectedLab, "agent")}
                </Box>
              </Box>
            ) : (
              <Box>
                <Box
                  className="page-header manage-labs-list-header"
                  sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2, mb: 3 }}
                >
                  <Box>
                    <Typography variant="h6" fontWeight={600} color="#64748b">
                      {t("admin.allLaboratoryRooms")}
                    </Typography>
                    <Typography color="#64748b" variant="body2" sx={{ mt: 0.5 }}>
                      {t("admin.deviceSubtitle")}
                    </Typography>
                  </Box>
                </Box>

                {labCards.length === 0 ? (
                  <Paper elevation={0} sx={{ py: 7, px: 2, textAlign: "center", border: "1px solid #e2e8f0", borderRadius: 3 }}>
                    <Typography color="text.secondary">{t("admin.noDevices")}</Typography>
                  </Paper>
                ) : (
                  <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))" }, gap: { xs: 2, md: 3 } }}>
                    {labCards.map((lab) => (
                      <Card
                        key={lab.id}
                        className="lab-card surface-card"
                        variant="outlined"
                        sx={{
                          display: "flex",
                          flexDirection: "column",
                          height: "100%",
                          minWidth: 0,
                          overflow: "hidden",
                          borderRadius: 6,
                          borderColor: "#e2e8f0",
                          boxShadow: "0 4px 12px rgba(0,0,0,0.04)",
                          transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
                          "&:hover": {
                            transform: "translateY(-6px)",
                            boxShadow: "0 20px 40px rgba(59, 130, 246, 0.15)",
                            borderColor: "#93c5fd",
                          },
                        }}
                      >
                        <CardActionArea
                          onClick={() => setSelectedLabId(String(lab.id))}
                          aria-label={`${t("common.details")}: ${lab.code} ${lab.name || ""}`}
                          sx={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "stretch" }}
                        >
                          <Box sx={{ height: 150, bgcolor: "#f8fafc", display: "flex", alignItems: "center", justifyContent: "center", width: "100%" }}>
                            <Computer sx={{ fontSize: 60, color: "#cbd5e1", transition: "color 0.25s", ".MuiCardActionArea-root:hover &": { color: "#3b82f6" } }} />
                          </Box>
                          <CardContent sx={{ p: { xs: 2.5, md: 4 }, width: "100%", flexGrow: 1, "&:last-child": { pb: { xs: 2.5, md: 4 } } }}>
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, minWidth: 0 }}>
                              <Typography variant="h5" fontWeight={700} color="#1e293b" sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
                                {lab.code}
                              </Typography>
                              <Chip
                                size="small"
                                label={t(lab.status === "active" ? "common.active" : "admin.disabled")}
                                sx={{
                                  flexShrink: 0,
                                  bgcolor: lab.status === "active" ? "#dcfce7" : "#fee2e2",
                                  color: lab.status === "active" ? "#15803d" : "#dc2626",
                                  fontWeight: 700,
                                }}
                              />
                            </Box>
                            <Typography variant="body2" color="#64748b" sx={{ mt: 0.5, minHeight: 22, overflowWrap: "anywhere" }}>
                              {lab.name || "—"}
                            </Typography>

                            <Divider sx={{ my: 2.5, borderColor: "#e2e8f0" }} />
                            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0, color: "#64748b" }}>
                                <ShieldOutlined sx={{ fontSize: 18, flexShrink: 0 }} />
                                <Typography variant="body2" fontWeight={600} sx={{ overflowWrap: "anywhere" }}>
                                  {lab.gatekeepers.length} {t("admin.gatekeeperSection")}
                                </Typography>
                              </Box>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0, color: "#64748b" }}>
                                <PeopleAlt sx={{ fontSize: 18, flexShrink: 0 }} />
                                <Typography variant="body2" fontWeight={600} sx={{ overflowWrap: "anywhere" }}>
                                  {lab.agents.length} {t("admin.labAgentsSection")}
                                </Typography>
                              </Box>
                            </Box>
                            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 2.5, color: "#64748b", minWidth: 0 }}>
                              <LocationOn sx={{ fontSize: 17, flexShrink: 0 }} />
                              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                                {lab.location || "—"}
                              </Typography>
                            </Box>
                          </CardContent>
                        </CardActionArea>
                      </Card>
                    ))}
                  </Box>
                )}
              </Box>
            )
          )}
        </Box>
      </Box>

      <Dialog
        open={Boolean(deviceToRemove)}
        onClose={() => removingDeviceId === null && setDeviceToRemove(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t("admin.removeDeviceTitle")}</DialogTitle>
        <DialogContent>
          <Typography>{t("admin.removeDeviceConfirm")}</Typography>
          <Typography fontWeight={700} sx={{ mt: 1, overflowWrap: "break-word" }}>
            {deviceToRemove?.device_name}
          </Typography>
          <Alert severity="info" sx={{ mt: 2 }}>
            {t("admin.deviceRemovalPreservesLogs")}
          </Alert>
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button disabled={removingDeviceId !== null} onClick={() => setDeviceToRemove(null)}>
            {t("common.cancel")}
          </Button>
          <Button
            color="error"
            variant="contained"
            startIcon={removingDeviceId !== null ? <CircularProgress size={16} color="inherit" /> : <DeleteOutline />}
            disabled={removingDeviceId !== null}
            onClick={handleRemoveDevice}
          >
            {removingDeviceId !== null ? t("admin.removingDevice") : t("common.delete")}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={notice.open} autoHideDuration={3500} onClose={() => setNotice((current) => ({ ...current, open: false }))}>
        <Alert severity={notice.severity} onClose={() => setNotice((current) => ({ ...current, open: false }))}>{notice.message}</Alert>
      </Snackbar>

    </Box>
  );
}
