import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import {
  AppBar, Toolbar, Typography, Button, Container, Box, Drawer, List, ListItem, ListItemIcon, ListItemText,
  IconButton, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, Divider,
  Badge, Avatar, Menu, MenuItem, Tooltip, useTheme, useMediaQuery
} from '@mui/material';
import {
  Home, People, CloudUpload, Analytics, Settings, Logout, Menu as MenuIcon, Dashboard as DashboardIcon,
  Storage, Security, NotificationsActive, AccountBox, Help, Close
} from '@mui/icons-material';

// Components (existing and new routes)
import Login from './auth/Login';
import SubscriberProvision from './provisioning/SubscriberProvision';
import BulkMigration from './migration/BulkMigration';

// Enterprise Dashboard Components (placeholders - will be created as needed)
const Dashboard = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4" gutterBottom>📊 Enterprise Dashboard</Typography>
    <Typography>System metrics, subscriber stats, and operational insights will be displayed here.</Typography>
  </Box>
);

const BulkOperations = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4" gutterBottom>⚡ Bulk Operations</Typography>
    <Typography>Advanced bulk operations for subscriber management will be displayed here.</Typography>
  </Box>
);

const Analytics = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4" gutterBottom>📈 Analytics & Reporting</Typography>
    <Typography>Advanced analytics, charts, and reports will be displayed here.</Typography>
  </Box>
);

const SystemMonitoring = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4" gutterBottom>🔍 System Monitoring</Typography>
    <Typography>Real-time system health, performance metrics, and alerts will be displayed here.</Typography>
  </Box>
);

const UserManagement = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4" gutterBottom>👥 User Management</Typography>
    <Typography>User roles, permissions, and access control will be displayed here.</Typography>
  </Box>
);

const SystemSettings = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4" gutterBottom>⚙️ System Settings</Typography>
    <Typography>Configuration, provisioning modes, and system preferences will be displayed here.</Typography>
  </Box>
);

// Logout Confirmation Modal
const LogoutConfirmModal = ({ open, handleClose, handleConfirm }) => (
  <Dialog open={open} onClose={handleClose}>
    <DialogTitle>🚪 Confirm Logout</DialogTitle>
    <DialogContent dividers>
      <Typography>Are you sure you want to log out of the Enterprise Portal?</Typography>
    </DialogContent>
    <DialogActions>
      <Button onClick={handleClose}>Cancel</Button>
      <Button onClick={handleConfirm} color="error" variant="contained">Logout</Button>
    </DialogActions>
  </Dialog>
);

// Enterprise Navigation Menu Configuration
const navigationConfig = [
  { path: '/dashboard', label: 'Dashboard', icon: <DashboardIcon />, roles: ['admin', 'operator', 'guest'] },
  { path: '/provision', label: 'Provisioning', icon: <People />, roles: ['admin', 'operator'] },
  { path: '/migration', label: 'Migration', icon: <CloudUpload />, roles: ['admin', 'operator'] },
  { path: '/bulk-ops', label: 'Bulk Operations', icon: <Storage />, roles: ['admin'] },
  { path: '/analytics', label: 'Analytics', icon: <Analytics />, roles: ['admin', 'operator'] },
  { path: '/monitoring', label: 'Monitoring', icon: <NotificationsActive />, roles: ['admin'] },
  { path: '/users', label: 'User Management', icon: <AccountBox />, roles: ['admin'] },
  { path: '/settings', label: 'Settings', icon: <Settings />, roles: ['admin'] },
];

// User Profile Menu
const UserProfileMenu = ({ auth, anchorEl, onClose, onLogout }) => (
  <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={onClose}>
    <MenuItem disabled>
      <Box>
        <Typography variant="body2" fontWeight="bold">{auth?.username}</Typography>
        <Typography variant="caption" color="text.secondary">{auth?.role?.toUpperCase()}</Typography>
      </Box>
    </MenuItem>
    <Divider />
    <MenuItem onClick={onLogout}>
      <ListItemIcon><Logout fontSize="small" /></ListItemIcon>
      <ListItemText>Logout</ListItemText>
    </MenuItem>
  </Menu>
);

function App() {
  const [auth, setAuth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const [profileMenuAnchor, setProfileMenuAnchor] = useState(null);
  
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const location = useLocation();
  const navigate = useNavigate();
  
  const drawerWidth = 280;

  useEffect(() => {
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');
    if (token && user) {
      try {
        setAuth(JSON.parse(user));
      } catch (e) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
    }
    setLoading(false);
  }, []);

  // Auto-close drawer on mobile after navigation
  useEffect(() => {
    if (isMobile && drawerOpen) {
      setDrawerOpen(false);
    }
  }, [location.pathname, isMobile]);

  const toggleDrawer = () => setDrawerOpen(!drawerOpen);
  const handleLogoutClick = () => {
    setProfileMenuAnchor(null);
    setIsLogoutModalOpen(true);
  };
  
  const handleConfirmLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setAuth(null);
    setIsLogoutModalOpen(false);
    navigate('/login');
  };

  // Filter navigation items based on user role
  const accessibleItems = navigationConfig.filter(item => 
    !auth || item.roles.includes(auth.role)
  );

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ ml: 2 }}>Loading Enterprise Portal...</Typography>
      </Box>
    );
  }

  // Login page (no layout)
  if (!auth) {
    return (
      <Container maxWidth="sm" sx={{ mt: 8 }}>
        <Routes>
          <Route path="/login" element={<Login setAuth={setAuth} />} />
          <Route path="*" element={<Navigate to="/login" />} />
        </Routes>
      </Container>
    );
  }

  // Enterprise Layout with Sidebar
  const drawer = (
    <Box sx={{ height: '100%', bgcolor: '#f5f5f5' }}>
      <Box sx={{ p: 2, bgcolor: '#1976d2', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="h6" fontWeight="bold">Portal Menu</Typography>
        {isMobile && (
          <IconButton color="inherit" onClick={toggleDrawer}>
            <Close />
          </IconButton>
        )}
      </Box>
      <Divider />
      <List sx={{ pt: 1 }}>
        {accessibleItems.map((item) => (
          <ListItem 
            key={item.path} 
            button 
            onClick={() => navigate(item.path)}
            sx={{
              bgcolor: location.pathname === item.path ? '#e3f2fd' : 'transparent',
              borderRight: location.pathname === item.path ? '4px solid #1976d2' : 'none',
              '&:hover': { bgcolor: '#f0f0f0' }
            }}
          >
            <ListItemIcon sx={{ color: location.pathname === item.path ? '#1976d2' : 'inherit' }}>
              {item.icon}
            </ListItemIcon>
            <ListItemText 
              primary={item.label} 
              sx={{ 
                '& .MuiTypography-root': { 
                  fontWeight: location.pathname === item.path ? 'bold' : 'normal',
                  color: location.pathname === item.path ? '#1976d2' : 'inherit'
                } 
              }} 
            />
          </ListItem>
        ))}
      </List>
      <Divider sx={{ mt: 2 }} />
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          🏢 Enterprise Portal v2.0.0
        </Typography>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* Top AppBar */}
      <AppBar position="fixed" sx={{ zIndex: theme.zIndex.drawer + 1, bgcolor: '#1976d2' }}>
        <Toolbar>
          <IconButton color="inherit" edge="start" onClick={toggleDrawer} sx={{ mr: 2 }}>
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
            🏢 Subscriber Migration Portal - Enterprise
          </Typography>
          
          {/* Notifications (placeholder) */}
          <Tooltip title="Notifications">
            <IconButton color="inherit">
              <Badge badgeContent={0} color="error">
                <NotificationsActive />
              </Badge>
            </IconButton>
          </Tooltip>
          
          {/* Help */}
          <Tooltip title="Help & Support">
            <IconButton color="inherit">
              <Help />
            </IconButton>
          </Tooltip>
          
          {/* User Profile */}
          <Tooltip title="User Profile">
            <IconButton 
              color="inherit" 
              onClick={(e) => setProfileMenuAnchor(e.currentTarget)}
              sx={{ ml: 1 }}
            >
              <Avatar sx={{ width: 32, height: 32, bgcolor: '#42a5f5' }}>
                {auth.username?.charAt(0)?.toUpperCase()}
              </Avatar>
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      {/* Navigation Drawer */}
      <Drawer
        variant={isMobile ? 'temporary' : 'persistent'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
            top: isMobile ? 0 : '64px',
            height: isMobile ? '100vh' : 'calc(100vh - 64px)',
            borderRight: '1px solid #e0e0e0'
          }
        }}
      >
        {drawer}
      </Drawer>

      {/* Main Content */}
      <Box component="main" sx={{ 
        flexGrow: 1, 
        transition: theme.transitions.create(['margin'], {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.leavingScreen,
        }),
        marginLeft: !isMobile && drawerOpen ? 0 : `-${drawerWidth}px`,
        ...((!isMobile && drawerOpen) && {
          transition: theme.transitions.create(['margin'], {
            easing: theme.transitions.easing.easeOut,
            duration: theme.transitions.duration.enteringScreen,
          }),
          marginLeft: 0,
        }),
      }}>
        <Toolbar /> {/* Spacer for fixed AppBar */}
        
        <Container maxWidth="xl" sx={{ py: 3 }}>
          <Routes>
            {/* Dashboard - Default route */}
            <Route path="/dashboard" element={<Dashboard />} />
            
            {/* Core Features */}
            <Route path="/provision" element={<SubscriberProvision />} />
            <Route path="/migration" element={<BulkMigration />} />
            
            {/* Enterprise Features */}
            <Route path="/bulk-ops" element={<BulkOperations />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/monitoring" element={<SystemMonitoring />} />
            
            {/* Admin Features */}
            <Route path="/users" element={<UserManagement />} />
            <Route path="/settings" element={<SystemSettings />} />
            
            {/* Default redirect to dashboard */}
            <Route path="/" element={<Navigate to="/dashboard" />} />
            
            {/* 404 Handler */}
            <Route path="*" element={
              <Box sx={{ textAlign: 'center', mt: 10 }}>
                <Typography variant="h4" color="error" gutterBottom>
                  🚫 404 - Page Not Found
                </Typography>
                <Typography variant="body1" color="text.secondary" gutterBottom>
                  The requested page could not be found in the Enterprise Portal.
                </Typography>
                <Button variant="contained" onClick={() => navigate('/dashboard')} sx={{ mt: 2 }}>
                  🏠 Return to Dashboard
                </Button>
              </Box>
            } />
          </Routes>
        </Container>
      </Box>

      {/* User Profile Menu */}
      <UserProfileMenu 
        auth={auth}
        anchorEl={profileMenuAnchor}
        onClose={() => setProfileMenuAnchor(null)}
        onLogout={handleLogoutClick}
      />
      
      {/* Logout Confirmation Modal */}
      <LogoutConfirmModal
        open={isLogoutModalOpen}
        handleClose={() => setIsLogoutModalOpen(false)}
        handleConfirm={handleConfirmLogout}
      />
    </Box>
  );
}

export default App;
