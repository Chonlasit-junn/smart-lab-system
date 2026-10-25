import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Autocomplete, Box, Button, CircularProgress, MenuItem, Paper, TextField, Typography } from "@mui/material";
import { Download } from "@mui/icons-material";
import axios from "axios";
import dayjs from "dayjs";
import "dayjs/locale/th";
import "dayjs/locale/en-gb";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import AdminShell from "../components/AdminShell";
import LoadError from "../components/LoadError";
import { useLanguage } from "../context/language-context.js";
import { authConfig } from "../utils/auth";
import { reportDatePickerThai, reportLocales } from "../utils/reportLocales";
import { initialReportDates, reportDateError, reportErrorKey, saveReportBlob, usageReportParams } from "../utils/usageReport";

const API_URL = import.meta.env.VITE_API_URL;

export default function AdminReports() {
  const { language } = useLanguage();
  const text = reportLocales[language];
  const [filters, setFilters] = useState(() => {
    const dates = initialReportDates();
    return { dateFrom: dayjs(dates.dateFrom), dateTo: dayjs(dates.dateTo), labId: "", deviceId: "" };
  });
  const [options, setOptions] = useState({ labs: [], devices: [] });
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [userSearch, setUserSearch] = useState("");
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersFailed, setUsersFailed] = useState(false);
  const [moreUsers, setMoreUsers] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [notice, setNotice] = useState(null);
  const optionsRequest = useRef(null);
  const exportRequest = useRef(null);
  const reportFilters = {
    ...filters,
    dateFrom: filters.dateFrom?.isValid() ? filters.dateFrom.format("YYYY-MM-DD") : "",
    dateTo: filters.dateTo?.isValid() ? filters.dateTo.format("YYYY-MM-DD") : "",
  };
  const dateError = reportDateError(reportFilters.dateFrom, reportFilters.dateTo);

  const loadOptions = useCallback(async () => {
    optionsRequest.current?.abort();
    const controller = new AbortController();
    optionsRequest.current = controller;
    setOptionsLoading(true);
    setOptionsFailed(false);
    try {
      const response = await axios.get(`${API_URL}/admin/reports/options`, { ...authConfig(), signal: controller.signal });
      if (!controller.signal.aborted) setOptions(response.data);
    } catch (error) {
      if (!axios.isCancel(error) && !controller.signal.aborted) setOptionsFailed(true);
    } finally {
      if (!controller.signal.aborted) setOptionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOptions();
    return () => { optionsRequest.current?.abort(); exportRequest.current?.abort(); };
  }, [loadOptions]);

  useEffect(() => { document.title = `${text.title} | Smart Lab Admin`; }, [text.title]);

  useEffect(() => {
    const controller = new AbortController();
    const term = userSearch.trim();
    const timer = setTimeout(async () => {
      setUsersFailed(false);
      setMoreUsers(false);
      if (term.length < 2 || selectedUser) {
        setUsers([]);
        setUsersLoading(false);
        return;
      }
      setUsersLoading(true);
      try {
        const response = await axios.get(`${API_URL}/admin/reports/users`, {
          ...authConfig(), signal: controller.signal, params: { q: term },
        });
        if (!controller.signal.aborted) {
          setUsers(response.data.data);
          setMoreUsers(response.data.has_more);
        }
      } catch (error) {
        if (!axios.isCancel(error) && !controller.signal.aborted) { setUsers([]); setUsersFailed(true); }
      } finally {
        if (!controller.signal.aborted) setUsersLoading(false);
      }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [userSearch, selectedUser]);

  const updateFilter = (key) => (event) => {
    setFilters((current) => ({ ...current, [key]: event.target.value }));
    setNotice(null);
  };

  const download = async (event) => {
    event.preventDefault();
    if (dateError || exportRequest.current) return;
    const controller = new AbortController();
    exportRequest.current = controller;
    setExporting(true);
    setNotice(null);
    try {
      const response = await axios.get(`${API_URL}/admin/reports/usage.xlsx`, {
        ...authConfig(), signal: controller.signal, responseType: "blob",
        params: usageReportParams({ ...reportFilters, userId: selectedUser?.id }, language),
      });
      if (controller.signal.aborted) return;
      const filename = `smart-lab-usage_${reportFilters.dateFrom}_${reportFilters.dateTo}_${language}.xlsx`;
      saveReportBlob(response.data, filename);
      setNotice({ severity: "success", key: "ready" });
    } catch (error) {
      if (!axios.isCancel(error) && !controller.signal.aborted) {
        const key = await reportErrorKey(error);
        if (!controller.signal.aborted) setNotice({ severity: "error", key });
      }
    } finally {
      if (exportRequest.current === controller) {
        exportRequest.current = null;
        if (!controller.signal.aborted) setExporting(false);
      }
    }
  };

  return (
    <AdminShell title={text.title}>
      <Box sx={{ width: "100%", maxWidth: 1120, mx: "auto", pb: 8 }}>
        <Typography color="text.secondary" sx={{ mb: 3 }}>{text.description}</Typography>
        {notice && <Alert severity={notice.severity} sx={{ mb: 2 }} role="status">{text[notice.key]}</Alert>}
        {optionsFailed ? <LoadError onRetry={loadOptions} /> : (
          <Paper component="form" onSubmit={download} elevation={0} className="surface-card" sx={{ p: { xs: 2, sm: 3 } }}>
            <Box component="fieldset" disabled={exporting || optionsLoading} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
              <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale={language === "th" ? "th" : "en-gb"}
                localeText={language === "th" ? reportDatePickerThai : undefined}>
              <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 2.5 }}>
                <DatePicker disabled={exporting || optionsLoading} label={text.dateFrom} format="DD/MM/YYYY" value={filters.dateFrom}
                  onChange={(value) => { setFilters((current) => ({ ...current, dateFrom: value })); setNotice(null); }} slotProps={{ textField: { required: true } }} />
                <DatePicker disabled={exporting || optionsLoading} label={text.dateTo} format="DD/MM/YYYY" value={filters.dateTo}
                  onChange={(value) => { setFilters((current) => ({ ...current, dateTo: value })); setNotice(null); }} slotProps={{ textField: { required: true } }} />
                <TextField select disabled={exporting || optionsLoading} label={text.lab} value={filters.labId} onChange={updateFilter("labId")}>
                  <MenuItem value="">{text.all}</MenuItem>
                  {options.labs.map((lab) => <MenuItem key={lab.id} value={lab.id}>{lab.code} — {lab.name}</MenuItem>)}
                </TextField>
                <TextField select disabled={exporting || optionsLoading} label={text.device} value={filters.deviceId} onChange={updateFilter("deviceId")}>
                  <MenuItem value="">{text.all}</MenuItem>
                  {options.devices.map((device) => <MenuItem key={device.id} value={device.id}>{device.device_name} — {device.device_id}</MenuItem>)}
                </TextField>
                <Autocomplete
                  sx={{ gridColumn: { sm: "1 / -1" } }} options={users} value={selectedUser} loading={usersLoading} disabled={exporting || optionsLoading}
                  filterOptions={(values) => values} isOptionEqualToValue={(option, value) => option.id === value.id}
                  getOptionLabel={(user) => `${user.first_name} ${user.last_name} (${user.email})`}
                  onChange={(_event, value) => { setSelectedUser(value); setNotice(null); }}
                  onInputChange={(_event, value, reason) => { if (reason === "input" || reason === "clear") { setUserSearch(value); if (reason === "input") setSelectedUser(null); } }}
                  noOptionsText={text.noUsers} loadingText={text.searching} clearText={text.clear} openText={text.open} closeText={text.close}
                  renderInput={(params) => <TextField {...params} label={text.user} error={usersFailed} helperText={usersFailed ? text.usersFailed : moreUsers ? text.moreUsers : text.userHint} />}
                />
              </Box>
              </LocalizationProvider>
              {dateError && <Alert severity="warning" sx={{ mt: 2 }}>{text[dateError]}</Alert>}
              <Button type="submit" variant="contained" startIcon={exporting || optionsLoading ? <CircularProgress size={18} color="inherit" /> : <Download />}
                disabled={Boolean(dateError) || exporting || optionsLoading} sx={{ mt: 3, minHeight: 44 }}>
                {exporting ? text.exporting : text.download}
              </Button>
            </Box>
          </Paper>
        )}
        <Paper elevation={0} className="surface-card" sx={{ p: { xs: 2, sm: 3 }, mt: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>{text.includes}</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2.5 }}>
            {["summary", "usage", "sessions", "violations"].map((key) => <Box key={key}>
              <Typography fontWeight={500}>{text[key]}</Typography>
              <Typography variant="body2" color="text.secondary">{text[`${key}Hint`]}</Typography>
            </Box>)}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>{text.note}</Typography>
        </Paper>
      </Box>
    </AdminShell>
  );
}
