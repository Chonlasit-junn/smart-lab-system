import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline } from '@mui/material';
import { AuthProvider } from './context/AuthContext'; 

import Login from './pages/Login';
import Register from './pages/Register';
import Booking from './pages/Booking';
import Admin from './pages/Admin';
import ManageLabs from './pages/ManageLabs';
import Reserved from './pages/Reserved';
import History from './pages/History';
import VerifyUsers from './pages/VerifyUsers';
import BlacklistManager from './pages/BlacklistManager';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <CssBaseline /> 
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/booking" element={<Booking />} />
          <Route path="/register" element={<Register />} />
          <Route path="/reserved" element={<Reserved />} />
          <Route path="/history" element={<History />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/manage-labs" element={<ManageLabs />} />
          <Route path="/verify-users" element={<VerifyUsers />} />
          <Route path="/blacklist" element={<BlacklistManager />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;