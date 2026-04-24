// ============================================================================
// 1. IMPORTS & CONFIGURATION
// ============================================================================
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { 
  Box, Typography, Avatar, IconButton, Paper, Button, Grid, Divider,
  Slide, Fade, Chip, Dialog, DialogContent 
} from '@mui/material';
import { 
  Search, Notifications, EventNote, Assignment, History, 
  SupportAgent, Logout, Computer, Person, ChevronLeft, ChevronRight, 
  PeopleAlt, Computer as PcIcon, Menu as MenuIcon, ArrowBack, CheckCircle 
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

// API Endpoint configuration
const API_URL = 'http://localhost:8000';

// Mapping for display texts
const SLOT_DISPLAY_MAPPING = {
  1: '08:40 - 11:00 AM',
  2: '12:00 - 14:20 PM',
  3: '14:30 - 16:50 PM',
  4: '17:00 - 19:20 PM'
};

// Mapping for actual time calculation logic
const SLOT_TIMES = {
  1: { hours: 8, minutes: 40 },
  2: { hours: 12, minutes: 0 },
  3: { hours: 14, minutes: 30 },
  4: { hours: 17, minutes: 0 }
};

// ============================================================================
// 2. MAIN COMPONENT
// ============================================================================
export default function Booking() {
  
  // --- Contexts & Hooks ---
  const navigate = useNavigate();
  const { currentUser, logout } = useAuth();

  // ============================================================================
  // 3. STATE MANAGEMENT
  // ============================================================================
  
  /** @description UI States - สำหรับจัดการการแสดงผลบนหน้าจอ */
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [successDialogOpen, setSuccessDialogOpen] = useState(false);

  /** @description Data States - สำหรับเก็บข้อมูลที่ดึงมาจาก API */
  const [labs, setLabs] = useState([]);
  const [availability, setAvailability] = useState(null);

  /** @description Selection States - สำหรับเก็บข้อมูลที่ผู้ใช้กำลังเลือกอยู่ (Room -> Date -> Time) */
  const [selectedRoom, setSelectedRoom] = useState(null); 
  const [currentDateObj, setCurrentDateObj] = useState(new Date()); 
  const [selectedDate, setSelectedDate] = useState(null); 
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null); 

  // ============================================================================
  // 4. LIFECYCLE & API CALLS
  // ============================================================================
  
  // Fetch labs on component mount
  useEffect(() => {
    fetchLabs();
  }, []);

  /**
   * @function fetchLabs
   * @description ดึงข้อมูลห้องแล็บทั้งหมดจาก Backend
   */
  const fetchLabs = async () => {
    try {
      const response = await axios.get(`${API_URL}/labs`);
      setLabs(response.data.data);
    } catch (error) {
      console.error("[API Error] Failed to fetch labs:", error);
      alert("❌ ไม่สามารถดึงข้อมูลห้องแล็บได้ กรุณาเช็กว่า Backend เปิดทำงานอยู่หรือไม่");
    }
  };

  /**
   * @function fetchAvailability
   * @description ดึงสถานะคิวว่างของห้องแล็บตามวันที่ระบุ
   * @param {number} labId - ID ของห้องแล็บ
   * @param {number} year - ปี ค.ศ.
   * @param {number} monthIndex - Index ของเดือน (0-11)
   * @param {number} dayNumber - วันที่ (1-31)
   */
  const fetchAvailability = async (labId, year, monthIndex, dayNumber) => {
    const dateStr = getFormattedDateString(year, monthIndex, dayNumber);
    try {
      const response = await axios.get(`${API_URL}/labs/${labId}/availability`, {
        params: { target_date: dateStr }
      });
      setAvailability(response.data.slots);
    } catch (error) {
      console.error("[API Error] Failed to fetch availability:", error);
      alert("❌ เกิดข้อผิดพลาดตอนดึงตารางเวลา! กรุณารีเฟรชหน้าเว็บ");
      setAvailability(null);
    }
  };

  // ============================================================================
  // 5. MEMOIZATION & COMPUTED VALUES
  // ============================================================================
  
  /** * @description ค้นหาห้องแล็บ (ใช้ useMemo เพื่อป้องกันการ Filter ใหม่ทุกครั้งที่ State อื่นเปลี่ยน) 
   */
  const filteredLabs = useMemo(() => {
    const query = searchQuery.toLowerCase();
    return labs.filter(lab => 
      (lab.name?.toLowerCase() || '').includes(query) ||
      (lab.code?.toLowerCase() || '').includes(query) ||
      (lab.location?.toLowerCase() || '').includes(query)
    );
  }, [labs, searchQuery]);

  // --- Date Math for Calendar Rendering ---
  const currentYear = currentDateObj.getFullYear();
  const currentMonth = currentDateObj.getMonth();
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const firstDayOfMonthJS = new Date(currentYear, currentMonth, 1).getDay();
  // แปลงวันอาทิตย์ (0) ให้อยู่ท้ายสุด เพื่อให้ปฏิทินเริ่มที่วันจันทร์
  const emptySlots = firstDayOfMonthJS === 0 ? 6 : firstDayOfMonthJS - 1;

  const monthName = currentDateObj.toLocaleString('en-US', { month: 'long' });
  const monthNameShort = currentDateObj.toLocaleString('en-US', { month: 'short' });

  /**
   * @function getFormattedDateString
   * @description แปลงข้อมูลวัน/เดือน/ปี ให้เป็น String รูปแบบ YYYY-MM-DD
   */
  const getFormattedDateString = useCallback((year, monthIndex, day) => {
    const padMonth = String(monthIndex + 1).padStart(2, '0');
    const padDay = String(day).padStart(2, '0');
    return `${year}-${padMonth}-${padDay}`;
  }, []);

  /**
   * @function checkSlotTimeValidity
   * @description ตรวจสอบว่า Slot เวลานี้ สามารถกดจองได้หรือไม่ตาม Business Logic (ล่วงหน้า 2 ชม.)
   * @returns {"valid" | "passed" | "too_close"}
   */
  const checkSlotTimeValidity = useCallback((slotNumber) => {
    if (!selectedDate) return "valid";

    // 1. จำลองเวลาที่ผู้ใช้เลือก (ให้เป็น 00:00:00 ของวันนั้น)
    const selectedDateObj = new Date(currentYear, currentMonth, selectedDate);
    selectedDateObj.setHours(0, 0, 0, 0);

    // 2. จำลองเวลาวันนี้ (00:00:00)
    const todayMidnight = new Date();
    todayMidnight.setHours(0, 0, 0, 0);

    // Rule A: ถ้าเลือกวันพรุ่งนี้หรือมะรืน ถือว่าผ่านกฎ 2 ชม. ทันที
    if (selectedDateObj.getTime() > todayMidnight.getTime()) return "valid";

    // Rule B: ถ้าเป็นวันนี้ ต้องเช็กเวลาเป๊ะๆ
    const slotTimeObj = new Date(currentYear, currentMonth, selectedDate);
    slotTimeObj.setHours(SLOT_TIMES[slotNumber].hours, SLOT_TIMES[slotNumber].minutes, 0, 0);

    const now = new Date();
    
    // Check: เวลาของ Slot นั้นผ่านไปแล้ว
    if (slotTimeObj.getTime() <= now.getTime()) return "passed";
    
    // Check: เวลากระชั้นชิดไม่ถึง 2 ชั่วโมง
    const twoHoursFromNow = new Date(now.getTime() + 2 * 60 * 60 * 1000);
    if (slotTimeObj.getTime() < twoHoursFromNow.getTime()) return "too_close";

    // ผ่านทุกเงื่อนไข
    return "valid";
  }, [selectedDate, currentYear, currentMonth]);

  // ============================================================================
  // 6. ACTION HANDLERS
  // ============================================================================
  
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // เคลียร์ค่าที่เลือกไว้ในขั้นตอนการจอง
  const resetSelections = () => {
    setSelectedDate(null);
    setSelectedTimeSlot(null);
    setAvailability(null);
  };

  const handlePrevMonth = () => {
    setCurrentDateObj(new Date(currentYear, currentMonth - 1, 1));
    resetSelections();
  };

  const handleNextMonth = () => {
    setCurrentDateObj(new Date(currentYear, currentMonth + 1, 1));
    resetSelections();
  };

  // ผู้ใช้เลือกห้อง
  const handleSelectRoom = (room) => {
    if (room.status !== 'active') return;
    setSelectedRoom(room);
    setSearchQuery(''); 
    resetSelections();
  };

  // กดย้อนกลับไปหน้าเลือกห้อง
  const handleBackToRooms = () => {
    setSelectedRoom(null);
    resetSelections();
  };

  // ผู้ใช้เลือกวันที่ในปฏิทิน
  const handleSelectDate = (dayNumber) => {
    setSelectedDate(dayNumber);
    setSelectedTimeSlot(null); 
    setAvailability(null); // เคลียร์ตารางของวันเก่าทิ้งก่อน
    fetchAvailability(selectedRoom.id, currentYear, currentMonth, dayNumber);
  };

  /**
   * @function handleConfirmBooking
   * @description ส่ง Request ไปยัง Backend เพื่อสร้างการจอง
   */
  const handleConfirmBooking = async () => {
    if (!selectedDate || !selectedTimeSlot) return;

    const dateStr = getFormattedDateString(currentYear, currentMonth, selectedDate);
    
    try {
      const payload = {
        lab_id: selectedRoom.id,
        email: currentUser.email, 
        booking_date: dateStr,
        slot_number: selectedTimeSlot,
        purpose: "General Study",
        total_participants: 1
      };

      await axios.post(`${API_URL}/bookings`, payload);
      // ยิง API ผ่าน จะเปิด Pop-up เขียว
      setSuccessDialogOpen(true);
    } catch (error) {
      const errMsg = error.response?.data?.detail || "Failed to confirm booking";
      alert(`❌ Booking Failed: ${errMsg}`); 
    }
  };

  // เมื่อกดปิด Pop-up ให้เคลียร์หน้าจอกลับสู่สภาพเริ่มต้น
  const handleCloseSuccessDialog = () => {
    setSuccessDialogOpen(false);
    handleBackToRooms(); 
  };

  // ============================================================================
  // 7. RENDER HELPERS
  // ============================================================================
  
  // Date validation setup for calendar rendering
  const todayMidnightForCalendar = new Date();
  todayMidnightForCalendar.setHours(0, 0, 0, 0);
  const maxDateMidnight = new Date();
  maxDateMidnight.setHours(0, 0, 0, 0);
  maxDateMidnight.setDate(maxDateMidnight.getDate() + 2); // Max booking window = 2 days

  // ============================================================================
  // 8. RENDER UI
  // ============================================================================
  return (
    <div className="app-layout">
      {/* --- OVERLAY (Mobile) --- */}
      {isSidebarOpen && <div className="sidebar-overlay" onClick={() => setIsSidebarOpen(false)}></div>}

      {/* --- SIDEBAR --- */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-logo">
          <Computer sx={{ fontSize: 40, color: '#0052cc' }} />
          <div>
            <Typography variant="h6" fontWeight="bold" lineHeight={1.2}>Smart Lab</Typography>
            <Typography variant="caption" color="textSecondary">Reserve Lab to use</Typography>
          </div>
        </div>

        <div className="sidebar-menu">
          <div className="menu-item active" onClick={() => setIsSidebarOpen(false)}>
            <EventNote /> Lab Reserve
          </div>
          <div className="menu-item" onClick={() => navigate('/reserved')}>
            <Assignment /> Reserved
          </div>
          <div className="menu-item" onClick={() => navigate('/history')}>
            <History /> History
          </div>
        </div>

        <div className="sidebar-menu" style={{ flex: 'none', paddingBottom: '24px' }}>
          <div className="menu-item"><SupportAgent /> Support</div>
          <div className="menu-item" onClick={handleLogout}><Logout /> Log Out</div>
        </div>
      </div>

      {/* --- MAIN AREA --- */}
      <div className="main-area">
        
        {/* --- HEADER --- */}
        <div className="top-header">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <IconButton sx={{ display: { xs: 'block', md: 'none' }, color: '#111827' }} onClick={() => setIsSidebarOpen(true)}>
              <MenuIcon />
            </IconButton>
            <Typography variant="h5" fontWeight="bold" color="#111827" sx={{ display: { xs: 'none', sm: 'block' } }}>
              Lab Reserve
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 3 } }}>
            <div className="search-bar">
              <Search sx={{ color: '#94a3b8' }} />
              <input 
                type="text" 
                placeholder="Search by code, name, or location..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                disabled={!!selectedRoom} 
              />
            </div>
            <IconButton sx={{ display: { xs: 'block', md: 'none' } }}><Search sx={{ color: '#111827' }} /></IconButton>
            <IconButton><Notifications sx={{ color: '#111827' }} /></IconButton>

            {/* Profile Section */}
            {currentUser ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '1px solid #e2e8f0', pl: { xs: 1, sm: 3 }, cursor: 'pointer' }}>
                <Box className="profile-text-container" sx={{ textAlign: 'right' }}>
                  <Typography variant="subtitle2" fontWeight="bold" lineHeight={1.2}>{currentUser.name}</Typography>
                  <Typography variant="caption" color="textSecondary">{currentUser.role}</Typography>
                </Box>
                <Avatar sx={{ bgcolor: '#111827', width: 36, height: 36 }}>{currentUser.initial}</Avatar>
              </Box>
            ) : (
              <Box onClick={() => navigate('/login')} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, borderLeft: '1px solid #e2e8f0', pl: { xs: 1, sm: 3 }, cursor: 'pointer', transition: '0.2s', '&:hover': { opacity: 0.7 } }}>
                <Box className="profile-text-container" sx={{ textAlign: 'right' }}>
                  <Typography variant="subtitle2" fontWeight="bold" lineHeight={1.2} color="textSecondary">Guest User</Typography>
                  <Typography variant="caption" color="primary.main">Click to Log in</Typography>
                </Box>
                <Avatar sx={{ bgcolor: '#cbd5e1', width: 36, height: 36 }}><Person sx={{ color: '#64748b' }} /></Avatar>
              </Box>
            )}
          </Box>
        </div>

        {/* --- CONTENT AREA --- */}
        <div className="content-area" style={{ position: 'relative', overflowX: 'hidden' }}>
          
          {/* VIEW 1: ROOM SELECTION */}
          {!selectedRoom && (
            <Fade in={!selectedRoom} timeout={400}>
              <Box>
                <Typography variant="h6" fontWeight="bold" sx={{ mb: 3 }}>
                  {searchQuery ? `Search Results for "${searchQuery}"` : "Select a Lab Room"}
                </Typography>
                <Grid container spacing={3}>
                  {filteredLabs.length > 0 ? (
                    filteredLabs.map((room) => (
                      <Grid item xs={12} sm={6} lg={4} key={room.id}>
                        <Paper 
                          elevation={0} 
                          onClick={() => handleSelectRoom(room)}
                          className="room-card"
                          sx={{ 
                            opacity: room.status === 'active' ? 1 : 0.6,
                            pointerEvents: room.status === 'active' ? 'auto' : 'none'
                          }}
                        >
                          <Box sx={{ height: '140px', bgcolor: '#e0f2fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Computer sx={{ fontSize: 60, color: '#3b82f6' }} />
                          </Box>
                          <Box sx={{ p: 3, flexGrow: 1, bgcolor: 'white' }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <Typography variant="h5" fontWeight="bold" color="#1e293b">{room.code}</Typography>
                              <span className={room.status === 'active' ? "animated-chip" : ""}>
                                <Chip 
                                  label={room.status === 'active' ? 'Available' : 'Maintenance'} 
                                  color={room.status === 'active' ? 'success' : 'error'} 
                                  size="small" 
                                  sx={{ fontWeight: 'bold' }} 
                                />
                              </span>
                            </Box>
                            <Typography variant="body2" color="#64748b" sx={{ mt: 1 }}>{room.name}</Typography>
                            <Divider sx={{ my: 2 }} />
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', color: '#64748b' }}>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <PeopleAlt fontSize="small" /> 
                                <Typography variant="body2" fontWeight="bold">{room.capacity} Users</Typography>
                              </Box>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                📍 {room.location || '-'}
                              </Box>
                            </Box>
                          </Box>
                        </Paper>
                      </Grid>
                    ))
                  ) : (
                    <Grid item xs={12}>
                      <Paper elevation={0} sx={{ p: 5, textAlign: 'center', border: '1px dashed #cbd5e1', borderRadius: 4, bgcolor: '#f8fafc' }}>
                        <Typography variant="h6" color="textSecondary" fontWeight="bold">No labs found matching "{searchQuery}"</Typography>
                        <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>Try adjusting your search keywords.</Typography>
                        <Button variant="outlined" onClick={() => setSearchQuery('')} sx={{ mt: 2, borderRadius: 2, textTransform: 'none', fontWeight: 'bold' }}>Clear Search</Button>
                      </Paper>
                    </Grid>
                  )}
                </Grid>
              </Box>
            </Fade>
          )}

          {/* VIEW 2: BOOKING PROCESS */}
          {selectedRoom && (
            <Box sx={{ display: 'flex', flexDirection: { xs: 'column', lg: 'row' }, gap: 4, height: '100%' }}>
              
              {/* Left Panel: Selected Room Info */}
              <Slide direction="right" in={!!selectedRoom} mountOnEnter unmountOnExit timeout={400}>
                <Box sx={{ flex: '1', maxWidth: { lg: '380px' } }}>
                  <Button 
                    startIcon={<ArrowBack />} 
                    onClick={handleBackToRooms} 
                    sx={{ mb: 2, color: '#64748b', textTransform: 'none', fontWeight: 'bold', transition: 'all 0.2s', '&:hover': { color: '#0f172a', bgcolor: 'transparent', transform: 'translateX(-5px)' } }}
                  >
                    Back to all rooms
                  </Button>
                  
                  <Paper elevation={0} sx={{ border: '2px solid #b5dbff', borderRadius: 4, overflow: 'hidden' }}>
                    <Box sx={{ height: '220px', bgcolor: '#e0f2fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Computer sx={{ fontSize: 80, color: '#3b82f6' }} />
                    </Box>
                    <Box sx={{ p: 4 }}>
                      <Typography variant="h4" fontWeight="bold" color="#0f172a" sx={{ mb: 1 }}>{selectedRoom.code}</Typography>
                      <Typography variant="body1" color="textSecondary" sx={{ mb: 3, lineHeight: 1.6 }}>{selectedRoom.name}</Typography>
                      <Divider sx={{ mb: 3 }} />
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, color: '#475569' }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          <Avatar sx={{ bgcolor: '#f1f5f9', color: '#64748b' }}><PeopleAlt /></Avatar>
                          <Typography fontWeight="bold">Capacity: {selectedRoom.capacity} Users</Typography>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          <Avatar sx={{ bgcolor: '#f1f5f9', color: '#64748b' }}><PcIcon /></Avatar>
                          <Typography fontWeight="bold">Location: {selectedRoom.location || '-'}</Typography>
                        </Box>
                      </Box>
                    </Box>
                  </Paper>
                </Box>
              </Slide>

              {/* Right Panel: Calendar & Time Slots */}
              <Slide direction="up" in={!!selectedRoom} mountOnEnter unmountOnExit timeout={600}>
                <Box sx={{ flex: '2', display: 'flex', flexDirection: 'column', gap: 3 }}>
                  
                  {/* STEP 1: CALENDAR */}
                  <Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                      <Typography variant="h6" fontWeight="bold">1. Select Date</Typography>
                      <Chip label="Advance booking up to 2 days" size="small" sx={{ bgcolor: '#eff6ff', color: '#2563eb', fontWeight: 'bold' }} />
                    </Box>
                    <Paper elevation={0} sx={{ p: { xs: 2, sm: 4 }, border: '1px solid #e2e8f0', borderRadius: 4 }}>
                      
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                        <Typography variant="h6" fontWeight="bold" color="#1e293b">{monthName} {currentYear}</Typography>
                        <Box>
                          <IconButton onClick={handlePrevMonth} size="small"><ChevronLeft /></IconButton>
                          <IconButton onClick={handleNextMonth} size="small"><ChevronRight /></IconButton>
                        </Box>
                      </Box>

                      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 1, textAlign: 'center' }}>
                        {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map(day => (
                          <Typography key={day} variant="caption" fontWeight="bold" color="#94a3b8" sx={{ mb: 1 }}>{day}</Typography>
                        ))}

                        {[...Array(emptySlots)].map((_, i) => <Box key={`empty-${i}`} />)}

                        {[...Array(daysInMonth)].map((_, i) => {
                          const dayNumber = i + 1;
                          const isSelected = dayNumber === selectedDate; 
                          
                          // คำนวณสถานะปุ่มวันที่ ว่ากดได้หรือไม่
                          const iterationDate = new Date(currentYear, currentMonth, dayNumber);
                          iterationDate.setHours(0, 0, 0, 0); 
                          const isPastDate = iterationDate.getTime() < todayMidnightForCalendar.getTime();
                          const isTooFarDate = iterationDate.getTime() > maxDateMidnight.getTime();
                          const isDisabledDate = isPastDate || isTooFarDate;

                          return (
                            <IconButton 
                              key={dayNumber}
                              onClick={() => handleSelectDate(dayNumber)} 
                              disabled={isDisabledDate}
                              sx={{ 
                                width: { xs: 32, sm: 40 }, height: { xs: 32, sm: 40 }, margin: 'auto',
                                bgcolor: isSelected ? '#3b82f6' : 'transparent',
                                color: isSelected ? 'white' : (isDisabledDate ? '#cbd5e1' : '#334155'),
                                transition: 'all 0.2s',
                                '&:hover': { 
                                  bgcolor: isDisabledDate ? 'transparent' : (isSelected ? '#2563eb' : '#f1f5f9'),
                                  transform: isDisabledDate ? 'none' : 'scale(1.1)' 
                                }
                              }}
                            >
                              <Typography variant="body2" fontWeight={isSelected ? 'bold' : 'normal'}>{dayNumber}</Typography>
                            </IconButton>
                          )
                        })}
                      </Box>
                    </Paper>
                  </Box>

                  {/* STEP 2: TIME SLOTS GRID */}
                  <Fade in={!!selectedDate} timeout={500}>
                    <Box sx={{ display: selectedDate ? 'block' : 'none' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6" fontWeight="bold">2. Select Time</Typography>
                        <Chip label="Requires 2 hours advance notice" size="small" sx={{ bgcolor: '#fff7ed', color: '#d97706', fontWeight: 'bold' }} />
                      </Box>
                      <Paper elevation={0} sx={{ p: 3, border: '1px solid #e2e8f0', borderRadius: 4 }}>
                        <Grid container spacing={2}>
                          {[1, 2, 3, 4].map((slotNumber) => {
                            // ดึงข้อมูล Slot จาก API response
                            const slotInfo = availability?.[slotNumber];
                            const isAvailable = slotInfo?.status === "available";
                            const isClass = slotInfo?.status === "class";
                            const isFull = slotInfo?.status === "full";
                            
                            // เช็กข้อจำกัดด้านเวลา (ล่วงหน้า 2 ชม.)
                            const timeStatus = checkSlotTimeValidity(slotNumber);
                            const isTimeValid = timeStatus === "valid";

                            const isSelected = selectedTimeSlot === slotNumber;
                            // ปุ่มจะถูกล็อกถ้า 1. ไม่ว่าง 2. ผิดเงื่อนไขเวลา
                            const isDisabled = !isAvailable || !isTimeValid;
                            
                            return (
                              <Grid item xs={12} sm={6} key={slotNumber}>
                                <Button
                                  fullWidth
                                  onClick={() => isAvailable && isTimeValid && setSelectedTimeSlot(slotNumber)} 
                                  variant={isSelected ? 'contained' : 'outlined'}
                                  disabled={isDisabled}
                                  sx={{
                                    py: 2, borderRadius: 3, fontWeight: 'bold', textTransform: 'none', fontSize: '15px', display: 'flex', flexDirection: 'column',
                                    borderColor: !isDisabled && !isSelected ? '#cbd5e1' : 'transparent',
                                    color: isSelected ? 'white' : (isDisabled ? '#94a3b8' : '#334155'),
                                    bgcolor: isSelected ? '#3b82f6' : (isDisabled ? '#f8fafc' : 'white'),
                                    '&:hover': { borderColor: '#3b82f6', bgcolor: !isDisabled && !isSelected ? '#eff6ff' : '' }
                                  }}
                                >
                                  <span>{SLOT_DISPLAY_MAPPING[slotNumber]}</span>
                                  <span style={{ fontSize: '12px', fontWeight: 'normal', marginTop: '4px' }}>
                                    {isClass && "Reserved for Class"}
                                    {isFull && "Fully Booked"}
                                    {!isTimeValid && isAvailable && timeStatus === "too_close" && "Too Close (Wait 2 hours)"}
                                    {!isTimeValid && isAvailable && timeStatus === "passed" && "Time Passed"}
                                    {isAvailable && isTimeValid && slotInfo?.remaining_seats !== undefined ? `${slotInfo.remaining_seats} Seats Left` : ''}
                                  </span>
                                </Button>
                              </Grid>
                            )
                          })}
                        </Grid>
                      </Paper>
                    </Box>
                  </Fade>

                  {/* STEP 3: ACTION CONFIRMATION */}
                  <Slide direction="up" in={!!selectedTimeSlot} mountOnEnter unmountOnExit>
                    <Paper 
                      elevation={0} 
                      sx={{ 
                        p: { xs: 2, md: 3 }, bgcolor: '#e0f2fe', borderRadius: 4, 
                        display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, 
                        justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'center' },
                        gap: 2, border: '1px solid #bae6fd'
                      }}
                    >
                      <Box>
                        <Typography variant="caption" color="textSecondary" fontWeight="bold">YOUR SELECTION</Typography>
                        <Typography variant="h6" fontWeight="bold" color="#0c4a6e">
                          {selectedRoom?.code} • {monthNameShort} {selectedDate}, {SLOT_DISPLAY_MAPPING[selectedTimeSlot]}
                        </Typography>
                      </Box>
                      
                      <Button 
                        variant="contained" 
                        onClick={currentUser ? handleConfirmBooking : () => navigate('/login')} 
                        sx={{ 
                          bgcolor: '#0284c7', color: 'white', px: 4, py: 1.5, borderRadius: 3, 
                          fontWeight: 'bold', width: { xs: '100%', sm: 'auto' },
                          transition: 'all 0.2s',
                          '&:hover': { bgcolor: '#0369a1', transform: 'scale(1.03)' }
                        }}
                      >
                        {currentUser ? 'Confirm Booking' : 'Log in to Book'}
                      </Button>
                    </Paper>
                  </Slide>

                </Box>
              </Slide>
            </Box>
          )}
        </div>
      </div>

      {/* ============================================================================
          9. DIALOGS & MODALS
          ============================================================================ */}
      <Dialog 
        open={successDialogOpen} 
        onClose={handleCloseSuccessDialog} 
        PaperProps={{ 
          sx: { borderRadius: 4, p: 3, textAlign: 'center', maxWidth: 400, boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)' } 
        }}
      >
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', pb: 1 }}>
          <Box sx={{ bgcolor: '#dcfce7', p: 2, borderRadius: '50%', display: 'inline-flex', mb: 3 }}>
            <CheckCircle sx={{ fontSize: 64, color: '#16a34a' }} />
          </Box>
          <Typography variant="h5" fontWeight="800" color="#0f172a" gutterBottom>
            Booking Request Sent!
          </Typography>
          <Typography variant="body1" color="#64748b" sx={{ mb: 3, lineHeight: 1.6 }}>
            Your reservation for <strong>{selectedRoom?.code}</strong> on <strong>{monthNameShort} {selectedDate}</strong> at <strong>{SLOT_DISPLAY_MAPPING[selectedTimeSlot]}</strong> has been received and is pending approval.
          </Typography>
          <Button 
            fullWidth
            variant="contained" 
            onClick={handleCloseSuccessDialog} 
            sx={{ 
              borderRadius: 3, py: 1.5, fontWeight: '700', fontSize: '1rem',
              bgcolor: '#0f172a', textTransform: 'none',
              '&:hover': { bgcolor: '#334155' }
            }}
          >
            Got it, thanks!
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}