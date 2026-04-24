// ============================================================================
// 1. IMPORTS
// ============================================================================
import React from 'react';
import { 
  Box, Typography, Paper, Grid, InputBase, IconButton, Avatar, 
  Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Divider, Stack 
} from '@mui/material';
import { 
  Search, Notifications, Dashboard as DashIcon, ConfirmationNumber, 
  Settings, Logout, Person, Group, Computer, MeetingRoom
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

// ============================================================================
// 2. MOCK DATA & CONSTANTS (ย้ายออกมาข้างนอกเพื่อลดภาระการ Re-render)
// ============================================================================
const SIDE_MENU_ITEMS = [
  { text: 'Manage Labs', icon: <MeetingRoom />, path: '/manage-labs' },
  { text: 'Ticket', icon: <ConfirmationNumber />, path: '/ticket' },
  { text: 'Control', icon: <Settings />, path: '/control' }
];

const STATS_DATA = [
  { label: 'Total Request', v: 128, c: '#3b82f6', i: <Person /> },
  { label: 'Active User', v: 58, c: '#10b981', i: <Group /> },
  { label: 'Ticket', v: 13, c: '#f59e0b', i: <ConfirmationNumber /> }
];

const RECENT_RESERVATIONS = [
  { user: 'Never Gonna', room: 'B4-505', date: '18/02/2026', time: '14.30', color: '#8b5cf6' },
  { user: 'Giveyou UP', room: 'B4-505', date: '18/02/2026', time: '14.30', color: '#f59e0b' },
];

const PENDING_APPROVALS = [
  { name: 'Never Gonna', time: '2m ago', initial: 'N', color: '#ec4899' },
  { name: 'Letyou Down', time: '55m ago', initial: 'L', color: '#3b82f6' },
];

// ============================================================================
// 3. MAIN COMPONENT
// ============================================================================
export default function Admin() {
  const navigate = useNavigate();

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: '#fcfdfe', fontFamily: "'Inter', sans-serif" }}>
      
      {/* =====================================================================
          SECTION A: SIDEBAR 
          ===================================================================== */}
      <Box sx={{ width: '280px', bgcolor: '#f0f7ff', borderRight: '1px solid #e2efff', display: 'flex', flexDirection: 'column', position: 'sticky', top: 0, height: '100vh' }}>
        
        {/* A1: Logo & Branding */}
        <Box sx={{ p: 4, display: 'flex', gap: 2, alignItems: 'center' }}>
          <Box sx={{ bgcolor: '#000', p: 1, borderRadius: 2.5, display: 'flex', boxShadow: '0 4px 10px rgba(0,0,0,0.2)' }}>
            <Computer sx={{ color: 'white', fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h6" fontWeight="800" sx={{ color: '#0f172a', letterSpacing: '-0.5px' }}>Smart Lab</Typography>
            <Typography variant="caption" sx={{ color: '#64748b', fontWeight: '500', display: 'block', mt: -0.5 }}>Admin Dashboard</Typography>
          </Box>
        </Box>

        {/* A2: Navigation Menu */}
        <Box sx={{ px: 2, mt: 4 }}>
          {/* Main Dashboard Button */}
          <Button 
            fullWidth 
            onClick={() => navigate('/admin')} 
            startIcon={<DashIcon sx={{ fontSize: 24 }} />} 
            sx={{ 
              justifyContent: 'flex-start', py: 1.8, px: 3, mb: 1,
              bgcolor: 'white', color: '#3b82f6', fontWeight: '700', 
              boxShadow: '0 10px 25px rgba(0,0,0,0.03)', borderRadius: 4,
              textTransform: 'none', transition: '0.3s',
              '&:hover': { bgcolor: 'white', transform: 'translateX(5px)' }
            }}
          >
            Dashboard
          </Button>

          {/* Dynamic Menu Items */}
          {SIDE_MENU_ITEMS.map((item) => (
            <Button 
              key={item.text}
              fullWidth 
              onClick={() => navigate(item.path)} 
              startIcon={item.icon} 
              sx={{ 
                justifyContent: 'flex-start', py: 1.8, px: 3, mb: 1,
                color: '#94a3b8', textTransform: 'none', fontWeight: '600',
                borderRadius: 4, transition: '0.2s',
                '&:hover': { color: '#64748b', transform: 'translateX(5px)' }
              }}
            >
              {item.text}
            </Button>
          ))}
        </Box>

        {/* A3: Logout Section */}
        <Box sx={{ mt: 'auto', p: 4 }}>
          <Button 
            startIcon={<Logout />} 
            onClick={() => navigate('/')} 
            sx={{ color: '#94a3b8', textTransform: 'none', fontWeight: '700', '&:hover': { color: '#ef4444' } }}
          >
            Log Out
          </Button>
        </Box>
      </Box>

      {/* =====================================================================
          SECTION B: MAIN CONTENT AREA 
          ===================================================================== */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        
        {/* B1: Top Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 6, py: 3, bgcolor: 'white' }}>
          <Typography variant="h4" fontWeight="800" sx={{ color: '#1e293b', letterSpacing: '-1px' }}>Dashboard</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {/* Search Bar */}
            <Paper elevation={0} sx={{ bgcolor: '#f1f5f9', px: 2.5, py: 1, borderRadius: 4, display: 'flex', alignItems: 'center', width: 350 }}>
              <Search sx={{ color: '#94a3b8', mr: 1.5 }} />
              <InputBase placeholder="Search approve lab...." fullWidth sx={{ fontSize: '15px', fontWeight: '500' }} />
            </Paper>
            {/* Notifications */}
            <IconButton sx={{ bgcolor: '#f8fafc' }}><Notifications sx={{ color: '#64748b' }} /></IconButton>
            <Divider orientation="vertical" flexItem sx={{ height: 30, my: 'auto', bgcolor: '#e2e8f0' }} />
            {/* Admin Profile */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box sx={{ textAlign: 'right' }}>
                <Typography variant="subtitle2" fontWeight="800" color="#1e293b">Khivin Admin</Typography>
                <Typography variant="caption" fontWeight="600" color="#94a3b8">Administrator</Typography>
              </Box>
              <Avatar sx={{ bgcolor: '#0f172a', width: 48, height: 48, boxShadow: '0 4px 10px rgba(0,0,0,0.1)' }}><Person /></Avatar>
            </Box>
          </Box>
        </Box>

        {/* B2: Content Body (Scrollable) */}
        <Box sx={{ p: 6, overflowY: 'auto' }}>
          
          {/* B2.1: Summary Stats Cards */}
          <Grid container spacing={4} sx={{ mb: 6 }}>
            {STATS_DATA.map((s, idx) => (
              <Grid item xs={12} md={4} key={idx}>
                <Paper elevation={0} sx={{ p: 4, borderRadius: 6, display: 'flex', alignItems: 'center', gap: 3, border: '1px solid #f1f5f9', bgcolor: 'white', transition: '0.3s', '&:hover': { transform: 'translateY(-5px)', boxShadow: '0 20px 40px rgba(0,0,0,0.03)' } }}>
                  <Avatar sx={{ bgcolor: s.c, width: 64, height: 64, borderRadius: 4, boxShadow: `0 8px 20px ${s.c}33` }}>{s.i}</Avatar>
                  <Box>
                    <Typography variant="body2" sx={{ color: '#94a3b8', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.5px', fontSize: '12px' }}>{s.label}</Typography>
                    <Typography variant="h3" fontWeight="800" sx={{ color: '#1e293b' }}>{s.v}</Typography>
                  </Box>
                </Paper>
              </Grid>
            ))}
          </Grid>

          {/* B2.2: Tables & Approvals Layout */}
          <Grid container spacing={5}>
            
            {/* Left Side: Recent Reservations Table */}
            <Grid item xs={12} lg={7.5}>
              <Paper elevation={0} sx={{ p: 5, borderRadius: 8, border: '1px solid #f1f5f9', bgcolor: 'white', boxShadow: '0 4px 20px rgba(0,0,0,0.01)' }}>
                <Typography variant="h5" fontWeight="800" sx={{ mb: 4, color: '#1e293b' }}>Recently Reserving</Typography>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        {['User', 'Room', 'Date', 'Time'].map((h, i) => (
                          <TableCell key={h} sx={{ border: 'none', color: '#94a3b8', fontWeight: '700', py: 2, bgcolor: '#f8fafc', borderRadius: i === 0 ? '12px 0 0 12px' : i === 3 ? '0 12px 12px 0' : 0 }}>{h}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {RECENT_RESERVATIONS.map((row, i) => (
                        <TableRow key={i} sx={{ '& td': { borderBottom: '1px solid #f8fafc' } }}>
                          <TableCell sx={{ py: 3 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                              <Avatar sx={{ bgcolor: row.color, width: 38, height: 38, fontSize: 14, fontWeight: '800' }}>{row.user[0]}</Avatar>
                              <Typography variant="subtitle1" fontWeight="700" color="#334155">{row.user}</Typography>
                            </Box>
                          </TableCell>
                          <TableCell sx={{ fontWeight: '600', color: '#64748b' }}>{row.room}</TableCell>
                          <TableCell sx={{ color: '#94a3b8', fontWeight: '500' }}>{row.date}</TableCell>
                          <TableCell sx={{ fontWeight: '700', color: '#334155' }}>{row.time}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            </Grid>

            {/* Right Side: Pending Approvals Stack */}
            <Grid item xs={12} lg={4.5}>
              <Typography variant="h5" fontWeight="800" sx={{ mb: 4, color: '#1e293b' }}>Approval</Typography>
              <Stack spacing={3}>
                {PENDING_APPROVALS.map((p, i) => (
                  <Paper key={i} elevation={0} sx={{ p: 4, borderRadius: 8, border: '1px solid #f1f5f9', bgcolor: 'white', transition: '0.3s', '&:hover': { boxShadow: '0 15px 30px rgba(0,0,0,0.05)' } }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Box sx={{ display: 'flex', gap: 2.5 }}>
                        <Avatar sx={{ bgcolor: p.color, width: 50, height: 50, fontWeight: '800', boxShadow: `0 8px 15px ${p.color}33` }}>{p.initial}</Avatar>
                        <Box>
                          <Typography variant="subtitle1" fontWeight="800" color="#1e293b">{p.name}</Typography>
                          <Typography variant="body2" fontWeight="600" color="#94a3b8">Verify identity</Typography>
                        </Box>
                      </Box>
                      <Typography variant="caption" sx={{ color: '#cbd5e1', fontWeight: '800' }}>{p.time}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 4 }}>
                      <Button variant="contained" disableElevation sx={{ bgcolor: '#e0f2fe', color: '#0369a1', fontWeight: '800', textTransform: 'none', px: 4, py: 1, borderRadius: 4, fontSize: '15px', '&:hover': { bgcolor: '#bae6fd' } }}>
                        View Detail
                      </Button>
                    </Box>
                  </Paper>
                ))}
              </Stack>
            </Grid>

          </Grid>
        </Box>
      </Box>
    </Box>
  );
}