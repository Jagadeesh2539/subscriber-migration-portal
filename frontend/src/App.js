import React, { useState, useEffect, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { ErrorBoundary } from 'react-error-boundary';
import { Toaster } from 'react-hot-toast';
import {
  AppBar, Toolbar, Typography, Button, Container, Box, Drawer, List, ListItem, ListItemIcon, ListItemText,
  IconButton, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, Divider,
  Badge, Avatar, Menu, MenuItem, Tooltip, useTheme, useMediaQuery, Skeleton,
  ThemeProvider, createTheme, CssBaseline, Alert, Fade, LinearProgress, Chip, Stack
} from '@mui/material';
import {
  People, CloudUpload, Analytics as AnalyticsIcon, Settings, Logout, Menu as MenuIcon, Dashboard as DashboardIcon,
  Storage, NotificationsActive, AccountBox, Help, Close, Brightness4, Brightness7, Refresh
} from '@mui/icons-material';

// Enhanced imports with lazy loading
const Login = React.lazy(() => import('./auth/Login'));
const BulkMigration = React.lazy(() => import('./migration/BulkMigration'));
const SettingsPage = React.lazy(() => import('./settings/SettingsPage'));
const ProvisioningHub = React.lazy(() => import('./provisioning/ProvisioningHub'));

// API and hooks
import { queryConfig } from './api/apiClient';
import { useDashboardStats, useSystemHealth, usePrefetchQueries } from './hooks/useApiQueries';
import { settingsService } from './api/settingsService';

// Enhanced theme configuration
const createAppTheme = (mode) => createTheme({
  palette: {
    mode,
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      dark: '#1565c0',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: mode === 'light' ? '#f5f5f5' : '#121212',
      paper: mode === 'light' ? '#ffffff' : '#1e1e1e',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h6: {
      fontWeight: 600,
    },
  },
  components: {
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: '1px solid rgba(0, 0, 0, 0.12)',
        },
      },
    },
  },
});

// Create Query Client with enhanced configuration
const queryClient = new QueryClient(queryConfig || {
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      cacheTime: 10 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
});

// Error Fallback Component
const ErrorFallback = ({ error, resetErrorBoundary }) => {
  return (
    <Container maxWidth="sm" sx={{ mt: 8, textAlign: 'center' }}>
      <Box sx={{ p: 4, border: '1px solid #f44336', borderRadius: 2, bgcolor: 'error.light', color: 'error.contrastText' }}>
        <Typography variant="h5" gutterBottom>🚨 Application Error</Typography>
        <Typography variant="body1" gutterBottom>{error.message}</Typography>
        <Button variant="contained" onClick={resetErrorBoundary} sx={{ mt: 2 }}>
          <Refresh sx={{ mr: 1 }} /> Try Again
        </Button>
      </Box>
    </Container>
  );
};

// Loading Skeleton Component
const LoadingSkeleton = () => (
  <Box sx={{ p: 3 }}>
    <Skeleton variant="text" width="60%" height={40} />
    <Skeleton variant="rectangular" width="100%" height={200} sx={{ my: 2 }} />
    <Skeleton variant="text" width="80%" />
    <Skeleton variant="text" width="40%" />
  </Box>
);

// Enhanced Dashboard with provisioning mode
const Dashboard = ({ provisioningMode }) => {
  const { data: stats, isLoading: statsLoading, error: statsError } = useDashboardStats();
  const { data: health, isLoading: healthLoading } = useSystemHealth();
  
  if (statsLoading || healthLoading) return <LoadingSkeleton />;
  
  if (statsError) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">Failed to load dashboard data: {statsError.message}</Alert>
      </Box>
    );
  }
  
  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" alignItems="center" spacing={2} mb={3}>
        <Typography variant="h4">📊 Enterprise Dashboard</Typography>
        <Chip 
          label={`Active Mode: ${provisioningMode}`}
          color={provisioningMode === 'CLOUD' ? 'success' : provisioningMode === 'LEGACY' ? 'warning' : 'info'}
          variant="outlined"
        />
      </Stack>
      
      {health && (
        <Alert 
          severity={health.status === 'healthy' ? 'success' : 'warning'} 
          sx={{ mb: 3 }}
        >
          System Status: {health.status?.toUpperCase()} | Last Updated: {new Date(health.lastUpdated).toLocaleString()}
        </Alert>
      )}
      
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 2, mb: 3 }}>
        <Box sx={{ p: 2, bgcolor: 'primary.light', color: 'primary.contrastText', borderRadius: 2 }}>
          <Typography variant="h6">Total Subscribers</Typography>
          <Typography variant="h4">{stats?.totalSubscribers?.toLocaleString() || 0}</Typography>
        </Box>
        <Box sx={{ p: 2, bgcolor: 'secondary.light', color: 'secondary.contrastText', borderRadius: 2 }}>
          <Typography variant="h6">Cloud Subscribers</Typography>
          <Typography variant="h4">{stats?.cloudSubscribers?.toLocaleString() || 0}</Typography>
        </Box>
        <Box sx={{ p: 2, bgcolor: 'success.light', color: 'success.contrastText', borderRadius: 2 }}>
          <Typography variant="h6">Active Mode</Typography>
          <Typography variant="h4">{provisioningMode}</Typography>
        </Box>
      </Box>
      
      <Typography variant="body1" color="text.secondary">
        Real-time system metrics, subscriber statistics, and operational insights.
      </Typography>
    </Box>
  );
};

// Navigation Configuration with role-based access
const navigationConfig = [
  { path: '/dashboard', label: 'Dashboard', icon: <DashboardIcon />, roles: ['admin', 'operator', 'guest'] },
  { path: '/provision', label: 'Provisioning', icon: <People />, roles: ['admin', 'operator'] },
  { path: '/migration', label: 'Migration', icon: <CloudUpload />, roles: ['admin', 'operator'] },
  { path: '/bulk-ops', label: 'Bulk Operations', icon: <Storage />, roles: ['admin'] },
  { path: '/analytics', label: 'Analytics', icon: <AnalyticsIcon />, roles: ['admin', 'operator'] },
  { path: '/monitoring', label: 'Monitoring', icon: <NotificationsActive />, roles: ['admin'] },
  { path: '/users', label: 'User Management', icon: <AccountBox />, roles: ['admin'] },
  { path: '/settings', label: 'Settings', icon: <Settings />, roles: ['admin'] },
];

// Enhanced User Profile Menu
const UserProfileMenu = ({ auth, anchorEl, onClose, onLogout, onThemeToggle, darkMode }) => (
  <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={onClose}>
    <MenuItem disabled>
      <Box>
        <Typography variant="body2" fontWeight="bold">{auth?.username}</Typography>
        <Typography variant="caption" color="text.secondary">{auth?.role?.toUpperCase()}</Typography>
      </Box>
    </MenuItem>
    <Divider />
    <MenuItem onClick={onThemeToggle}>
      <ListItemIcon>
        {darkMode ? <Brightness7 fontSize="small" /> : <Brightness4 fontSize="small" />}
      </ListItemIcon>
      <ListItemText>{darkMode ? 'Light Mode' : 'Dark Mode'}</ListItemText>
    </MenuItem>
    <MenuItem onClick={onLogout}>
      <ListItemIcon><Logout fontSize="small" /></ListItemIcon>
      <ListItemText>Logout</ListItemText>
    </MenuItem>
  </Menu>
);

// Main App Component
function AppContent() {
  const [auth, setAuth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);
  const [profileMenuAnchor, setProfileMenuAnchor] = useState(null);
  const [provisioningMode, setProvisioningMode] = useState('CLOUD');
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode');
    return saved ? JSON.parse(saved) : false;
  });
  
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const location = useLocation();
  const navigate = useNavigate();
  const { prefetchDashboard, prefetchSubscribers } = usePrefetchQueries();
  
  const drawerWidth = 280;
  const appTheme = createAppTheme(darkMode ? 'dark' : 'light');

  // Load provisioning mode
  const loadProvisioningMode = async () => {
    try {
      const { data } = await settingsService.getProvisioningMode();
      const mode = data?.data?.mode || data?.mode || 'CLOUD';
      setProvisioningMode(mode);
    } catch (error) {
      console.log('Could not load provisioning mode, defaulting to CLOUD');
    }
  };

  // Enhanced authentication check
  useEffect(() => {
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');
    
    if (token && user) {
      try {
        const userData = JSON.parse(user);
        setAuth(userData);
        
        // Load provisioning mode for authenticated users
        loadProvisioningMode();
        
        // Prefetch dashboard data for better UX
        if (prefetchDashboard) prefetchDashboard();
        if (prefetchSubscribers) prefetchSubscribers();
      } catch (e) {
        console.error('Invalid user data:', e);
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
    }
    setLoading(false);
  }, [prefetchDashboard, prefetchSubscribers]);

  // Handle provisioning mode changes from Settings page
  const handleProvisioningModeChange = (newMode) => {
    setProvisioningMode(newMode);
  };

  // Auto-close drawer on mobile after navigation
  useEffect(() => {
    if (isMobile && drawerOpen) {
      setDrawerOpen(false);
    }
  }, [location.pathname, isMobile, drawerOpen]);

  // Save dark mode preference
  useEffect(() => {
    localStorage.setItem('darkMode', JSON.stringify(darkMode));
  }, [darkMode]);

  const toggleDrawer = () => setDrawerOpen(!drawerOpen);
  const toggleTheme = () => setDarkMode(!darkMode);
  
  const handleLogoutClick = () => {
    setProfileMenuAnchor(null);
    setIsLogoutModalOpen(true);
  };
  
  const handleConfirmLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    queryClient.clear(); // Clear React Query cache
    setAuth(null);
    setIsLogoutModalOpen(false);
    navigate('/login');
  };

  // Filter navigation items based on user role
  const accessibleItems = navigationConfig.filter(item => 
    !auth || item.roles.includes(auth.role)
  );

  // Enhanced loading screen
  if (loading) {
    return (
      <ThemeProvider theme={appTheme}>
        <CssBaseline />
        <Box sx={{ 
          display: 'flex', 
          flexDirection: 'column',
          justifyContent: 'center', 
          alignItems: 'center', 
          minHeight: '100vh',
          gap: 2
        }}>
          <CircularProgress size={60} />
          <Typography variant="h6">Loading Enterprise Portal...</Typography>
          <LinearProgress sx={{ width: '200px' }} />
        </Box>
      </ThemeProvider>
    );
  }

  // Login page
  if (!auth) {
    return (
      <ThemeProvider theme={appTheme}>
        <CssBaseline />
        <Container maxWidth="sm" sx={{ mt: 8 }}>
          <Suspense fallback={
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          }>
            <Routes>
              <Route path="/login" element={<Login setAuth={setAuth} />} />
              <Route path="*" element={<Navigate to="/login" />} />
            </Routes>
          </Suspense>
        </Container>
        <Toaster position="top-right" />
      </ThemeProvider>
    );
  }

  // Enhanced drawer component
  const drawer = (
    <Box sx={{ height: '100%', bgcolor: 'background.paper' }}>
      <Box sx={{ 
        p: 2, 
        bgcolor: 'primary.main', 
        color: 'primary.contrastText', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between' 
      }}>
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
              bgcolor: location.pathname.startsWith(item.path) ? 'action.selected' : 'transparent',
              borderRight: location.pathname.startsWith(item.path) ? '4px solid' : 'none',
              borderRightColor: 'primary.main',
              '&:hover': { bgcolor: 'action.hover' }
            }}
          >
            <ListItemIcon sx={{ color: location.pathname.startsWith(item.path) ? 'primary.main' : 'inherit' }}>
              {item.icon}
            </ListItemIcon>
            <ListItemText 
              primary={item.label} 
              sx={{ 
                '& .MuiTypography-root': { 
                  fontWeight: location.pathname.startsWith(item.path) ? 'bold' : 'normal',
                  color: location.pathname.startsWith(item.path) ? 'primary.main' : 'inherit'
                } 
              }} 
            />
          </ListItem>
        ))}
      </List>
      <Divider sx={{ mt: 2 }} />
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          🏢 Enterprise Portal v3.0.0
        </Typography>
      </Box>
    </Box>
  );

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <ErrorBoundary FallbackComponent={ErrorFallback} onReset={() => window.location.reload()}>
        <Box sx={{ display: 'flex', minHeight: '100vh' }}>
          {/* Enhanced AppBar with global provisioning mode badge */}
          <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
            <Toolbar>
              <IconButton color="inherit" edge="start" onClick={toggleDrawer} sx={{ mr: 2 }}>
                <MenuIcon />
              </IconButton>
              <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
                🏢 Subscriber Migration Portal - Enterprise
              </Typography>
              
              {/* Global Provisioning Mode Badge */}
              <Stack direction="row" spacing={2} alignItems="center">
                <Chip 
                  label={`Mode: ${provisioningMode}`}
                  color={provisioningMode === 'CLOUD' ? 'success' : provisioningMode === 'LEGACY' ? 'warning' : 'info'}
                  size="small"
                  variant="outlined"
                  sx={{ color: 'white', borderColor: 'white' }}
                />
                
                {/* Theme Toggle */}
                <Tooltip title={`Switch to ${darkMode ? 'light' : 'dark'} mode`}>
                  <IconButton color="inherit" onClick={toggleTheme}>
                    {darkMode ? <Brightness7 /> : <Brightness4 />}
                  </IconButton>
                </Tooltip>
                
                {/* Notifications */}
                <Tooltip title="Notifications">
                  <IconButton color="inherit">
                    <Badge badgeContent={0} color="error">
                      <NotificationsActive />
                    </Badge>
                  </IconButton>
                </Tooltip>
                
                {/* User Profile */}
                <Tooltip title="User Profile">
                  <IconButton 
                    color="inherit" 
                    onClick={(e) => setProfileMenuAnchor(e.currentTarget)}
                    sx={{ ml: 1 }}
                  >
                    <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main' }}>
                      {auth.username?.charAt(0)?.toUpperCase()}
                    </Avatar>
                  </IconButton>
                </Tooltip>
              </Stack>
            </Toolbar>
          </AppBar>

          {/* Enhanced Navigation Drawer */}
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
              },
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
              <Fade in={true} timeout={300}>
                <div>
                  <Suspense fallback={<LoadingSkeleton />}>
                    <Routes>
                      {/* Dashboard - Default route */}
                      <Route path="/dashboard" element={<Dashboard provisioningMode={provisioningMode} />} />
                      
                      {/* Provisioning Hub with nested routes */}
                      <Route path="/provision/*" element={<ProvisioningHub />} />
                      
                      {/* Migration */}
                      <Route path="/migration" element={<BulkMigration />} />
                      
                      {/* Enterprise Features - Placeholder for now */}
                      <Route path="/bulk-ops" element={<div>Bulk Operations Coming Soon</div>} />
                      <Route path="/analytics" element={<div>Analytics Coming Soon</div>} />
                      <Route path="/monitoring" element={<div>System Monitoring Coming Soon</div>} />
                      
                      {/* Admin Features */}
                      <Route path="/users" element={<div>User Management Coming Soon</div>} />
                      <Route 
                        path="/settings" 
                        element={<SettingsPage onModeChanged={handleProvisioningModeChange} />} 
                      />
                      
                      {/* Default redirect */}
                      <Route path="/" element={<Navigate to="/dashboard" />} />
                      
                      {/* Enhanced 404 Handler */}
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
                  </Suspense>
                </div>
              </Fade>
            </Container>
          </Box>

          {/* Enhanced User Profile Menu */}
          <UserProfileMenu 
            auth={auth}
            anchorEl={profileMenuAnchor}
            onClose={() => setProfileMenuAnchor(null)}
            onLogout={handleLogoutClick}
            onThemeToggle={toggleTheme}
            darkMode={darkMode}
          />
          
          {/* Logout Confirmation Modal */}
          <Dialog open={isLogoutModalOpen} onClose={() => setIsLogoutModalOpen(false)} maxWidth="xs" fullWidth>
            <DialogTitle>🚪 Confirm Logout</DialogTitle>
            <DialogContent>
              <Typography>Are you sure you want to log out of the Enterprise Portal?</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                You will need to log in again to access your account.
              </Typography>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setIsLogoutModalOpen(false)}>Cancel</Button>
              <Button onClick={handleConfirmLogout} color="error" variant="contained">Logout</Button>
            </DialogActions>
          </Dialog>
          
          {/* Toast Notifications */}
          <Toaster 
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: darkMode ? '#333' : '#fff',
                color: darkMode ? '#fff' : '#333',
              },
            }}
          />
          
          {/* React Query DevTools (development only) */}
          {process.env.NODE_ENV === 'development' && (
            <ReactQueryDevtools initialIsOpen={false} />
          )}
        </Box>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppContent />
      </Router>
    </QueryClientProvider>
  );
}

export default App;