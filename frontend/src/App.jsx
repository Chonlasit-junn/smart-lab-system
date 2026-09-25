import { lazy, Suspense, useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline, ThemeProvider as MuiThemeProvider, createTheme } from '@mui/material';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/auth-context';
import { ThemeProvider as AppThemeProvider } from './context/theme-context.jsx';
import { useTheme } from './context/theme-context.js';
import ThemeToggle from './components/ThemeToggle';
import { LanguageProvider } from './context/language-context.jsx';
import LanguageToggle from './components/LanguageToggle';

const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Booking = lazy(() => import('./pages/Booking'));
const Admin = lazy(() => import('./pages/Admin'));
const AdminPoints = lazy(() => import('./pages/AdminPoints'));
const AdminPointPolicy = lazy(() => import('./pages/AdminPointPolicy'));
const RoleManagement = lazy(() => import('./pages/RoleManagement'));
const ManageLabs = lazy(() => import('./pages/ManageLabs'));
const AdminDevices = lazy(() => import('./pages/AdminDevices'));
const Reserved = lazy(() => import('./pages/Reserved'));
const History = lazy(() => import('./pages/History'));
const VerifyUsers = lazy(() => import('./pages/VerifyUsers'));
const BlacklistManager = lazy(() => import('./pages/BlacklistManager'));
const Profile = lazy(() => import('./pages/Profile'));
const TicketManager = lazy(() => import('./pages/TicketManager'));
const MyTickets = lazy(() => import('./pages/MyTickets'));

function ProtectedRoute({ children }) {
  const { currentUser, loading } = useAuth();
  if (loading) return null;
  return currentUser ? children : <Navigate to="/" replace />;
}

function AdminRoute({ children }) {
  const { currentUser, loading } = useAuth();
  if (loading) return null;
  if (!currentUser) return <Navigate to="/" replace />;
  return currentUser.roleName === "admin" ? children : <Navigate to="/booking" replace />;
}

function AppContent() {
  const { mode } = useTheme();
  const muiFontFamily = '"Kanit", sans-serif';
  const muiTheme = useMemo(() => {
    // Use one font family and one typography scale in every language.
    const typographySize = (value) => value;
    const muiTypography = {
      fontFamily: muiFontFamily,
      fontWeightLight: 200,
      fontWeightRegular: 300,
      fontWeightMedium: 400,
      fontWeightBold: 600,
      h1: { fontSize: typographySize("6rem"), fontWeight: 600, lineHeight: 1.15 },
      h2: { fontSize: typographySize("3.75rem"), fontWeight: 600, lineHeight: 1.18 },
      h3: { fontSize: typographySize("3rem"), fontWeight: 600, lineHeight: 1.2 },
      h4: { fontSize: typographySize("2.125rem"), fontWeight: 600, lineHeight: 1.22 },
      h5: { fontSize: typographySize("1.5rem"), fontWeight: 600, lineHeight: 1.28 },
      h6: { fontSize: typographySize("1.25rem"), fontWeight: 500, lineHeight: 1.35 },
      subtitle1: { fontSize: typographySize("1rem"), fontWeight: 400, lineHeight: 1.45 },
      subtitle2: { fontSize: typographySize("0.875rem"), fontWeight: 400, lineHeight: 1.4 },
      body1: { fontSize: typographySize("1rem"), fontWeight: 300, lineHeight: 1.5 },
      body2: { fontSize: typographySize("0.875rem"), fontWeight: 300, lineHeight: 1.45 },
      button: { fontSize: typographySize("0.875rem"), fontWeight: 500, lineHeight: 1.3, textTransform: "none" },
      caption: { fontSize: typographySize("0.75rem"), fontWeight: 300, lineHeight: 1.35 },
      overline: { fontSize: typographySize("0.75rem"), fontWeight: 600, lineHeight: 1.35, letterSpacing: "0.08em" },
    };
    return createTheme({
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
    typography: muiTypography,
    shape: { borderRadius: 12 },
    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: "var(--radius-control)",
            fontFamily: muiFontFamily,
            lineHeight: 1.3,
            textTransform: "none",
          },
          startIcon: { lineHeight: 0 },
          endIcon: { lineHeight: 0 },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-pill)", fontFamily: muiFontFamily },
          label: { fontSize: typographySize("0.8125rem"), lineHeight: 1.2 },
          icon: { marginLeft: 6, marginRight: -4 },
        },
      },
      MuiInputBase: {
        styleOverrides: {
          root: { fontFamily: muiFontFamily, fontSize: typographySize("1rem") },
          input: { fontFamily: muiFontFamily, fontSize: typographySize("1rem"), lineHeight: 1.4 },
        },
      },
      MuiInputLabel: {
        styleOverrides: {
          root: { fontFamily: muiFontFamily, lineHeight: 1.25 },
        },
      },
      MuiFormHelperText: {
        styleOverrides: {
          root: { fontFamily: muiFontFamily, lineHeight: 1.35 },
        },
      },
      MuiMenuItem: {
        styleOverrides: {
          root: { fontFamily: muiFontFamily, lineHeight: 1.35 },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { fontFamily: muiFontFamily, lineHeight: 1.4 },
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: { borderRadius: "var(--radius-control)", fontFamily: muiFontFamily },
          message: { lineHeight: 1.4 },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: { fontFamily: muiFontFamily, lineHeight: 1.3, textTransform: "none" },
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
    },
    });
  }, [mode, muiFontFamily]);

  return (
    <MuiThemeProvider theme={muiTheme}>
      <CssBaseline enableColorScheme />
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={(
            <div
              role="status"
              aria-live="polite"
              style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}
            >
              Loading...
            </div>
          )}>
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
          </Suspense>
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
