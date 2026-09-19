import { useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline, ThemeProvider as MuiThemeProvider, createTheme } from '@mui/material';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/auth-context';
import { ThemeProvider as AppThemeProvider } from './context/theme-context.jsx';
import { useTheme } from './context/theme-context.js';
import ThemeToggle from './components/ThemeToggle';
import { LanguageProvider } from './context/language-context.jsx';
import LanguageToggle from './components/LanguageToggle';

import Login from './pages/Login';
import Register from './pages/Register';
import Booking from './pages/Booking';
import Admin from './pages/Admin';
import AdminPoints from './pages/AdminPoints';
import AdminPointPolicy from './pages/AdminPointPolicy';
import RoleManagement from './pages/RoleManagement';
import ManageLabs from './pages/ManageLabs';
import AdminDevices from './pages/AdminDevices';
import Reserved from './pages/Reserved';
import History from './pages/History';
import VerifyUsers from './pages/VerifyUsers';
import BlacklistManager from './pages/BlacklistManager';
import Profile from './pages/Profile';
import TicketManager from './pages/TicketManager';
import MyTickets from './pages/MyTickets';

function ProtectedRoute({ children }) {
  const { currentUser } = useAuth();
  return currentUser ? children : <Navigate to="/" replace />;
}

function AdminRoute({ children }) {
  const { currentUser } = useAuth();
  if (!currentUser) return <Navigate to="/" replace />;
  return currentUser.roleName === "admin" ? children : <Navigate to="/booking" replace />;
}

function AppContent() {
  const { mode } = useTheme();
  const muiTheme = useMemo(() => createTheme({
    palette: {
      mode,
      primary: {
        main: mode === "dark" ? "#5EEAD4" : "#0F766E",
        contrastText: mode === "dark" ? "#042F2E" : "#FFFFFF",
      },
      background: {
        default: mode === "dark" ? "#111827" : "#F6F7F5",
        paper: mode === "dark" ? "#1F2937" : "#FFFFFF",
      },
      text: {
        primary: mode === "dark" ? "#F8FAFC" : "#17202A",
        secondary: mode === "dark" ? "#CBD5E1" : "#52606D",
      },
      divider: mode === "dark" ? "#3A4758" : "#D8DDD8",
    },
    shape: { borderRadius: 12 },
    components: {
      MuiButton: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-control)" },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-control)" },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-card)" },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-card)" },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: { borderRadius: "var(--radius-modal)" },
        },
      },
      MuiPopover: {
        styleOverrides: {
          paper: { borderRadius: "var(--radius-modal)" },
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: { borderRadius: "var(--radius-modal)" },
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-control)" },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-pill)" },
        },
      },
    },
  }), [mode]);

  return (
    <MuiThemeProvider theme={muiTheme}>
      <CssBaseline enableColorScheme />
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Login />} />
            <Route path="/booking" element={<ProtectedRoute><Booking /></ProtectedRoute>} />
            <Route path="/register" element={<Register />} />
            <Route path="/reserved" element={<ProtectedRoute><Reserved /></ProtectedRoute>} />
            <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
            <Route path="/my-tickets" element={<ProtectedRoute><MyTickets /></ProtectedRoute>} />
            <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
            <Route path="/admin/points" element={<AdminRoute><AdminPoints /></AdminRoute>} />
            <Route path="/admin/points/policy" element={<AdminRoute><AdminPointPolicy /></AdminRoute>} />
            <Route path="/admin/roles" element={<AdminRoute><RoleManagement /></AdminRoute>} />
            <Route path="/manage-labs" element={<AdminRoute><ManageLabs /></AdminRoute>} />
            <Route path="/admin/devices" element={<AdminRoute><AdminDevices /></AdminRoute>} />
            <Route path="/verify-users" element={<AdminRoute><VerifyUsers /></AdminRoute>} />
            <Route path="/blacklist" element={<AdminRoute><BlacklistManager /></AdminRoute>} />
            <Route path="/ticket" element={<AdminRoute><TicketManager /></AdminRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <LanguageToggle className="global-language-toggle" />
          <ThemeToggle className="global-theme-toggle" />
        </BrowserRouter>
      </AuthProvider>
    </MuiThemeProvider>
  );
}

function App() {
  return (
    <AppThemeProvider>
      <LanguageProvider>
        <AppContent />
      </LanguageProvider>
    </AppThemeProvider>
  );
}

export default App;
