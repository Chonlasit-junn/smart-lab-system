import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline } from '@mui/material';
import { AuthProvider } from './context/AuthContext';
import { useAuth } from './context/auth-context';

import Login from './pages/Login';
import Register from './pages/Register';
import Booking from './pages/Booking';
import Admin from './pages/Admin';
import AdminPoints from './pages/AdminPoints';
import AdminPointPolicy from './pages/AdminPointPolicy';
import ManageLabs from './pages/ManageLabs';
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

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <CssBaseline /> 
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
            <Route path="/manage-labs" element={<AdminRoute><ManageLabs /></AdminRoute>} />
            <Route path="/verify-users" element={<AdminRoute><VerifyUsers /></AdminRoute>} />
            <Route path="/blacklist" element={<AdminRoute><BlacklistManager /></AdminRoute>} />
            <Route path="/ticket" element={<AdminRoute><TicketManager /></AdminRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
            
          </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
