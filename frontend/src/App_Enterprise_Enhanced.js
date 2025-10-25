import React, { useState, useEffect } from 'react';
import {
  Box,
  CssBaseline,
  ThemeProvider,
  createTheme,
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Drawer,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Avatar,
  Menu,
  MenuItem,
  Container,
  Grid,
  Card,
  CardContent,
  Button,
  Alert,
  Snackbar,
  CircularProgress,
  Backdrop
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard,
  People,
  CloudSync,
  Analytics,
  Settings,
  Logout,
  AccountCircle,
  Notifications,
  Search as SearchIcon
} from '@mui/icons-material';

// Component imports
import Dashboard from './components/Dashboard';
import ProvisioningModule from './components/ProvisioningModule';
import MigrationModule from './components/MigrationModule';
import BulkOperationsModule from './components/BulkOperationsModule';
import DataQueryModule from './components/DataQueryModule';
import MonitoringDashboard from './components/MonitoringDashboard';
import AnalyticsModule from './components/AnalyticsModule';
import LoginForm from './auth/LoginForm';
import { api } from './api/enhanced';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      dark: '#1565c0'
    },
    secondary: {
      main: '#dc004e',
      light: '#f5005c',
      dark: '#c70039'
    },
    background: {
      default: '#f5f7fa',
      paper: '#ffffff'
    },
    text: {
      primary: '#2c3e50',
      secondary: '#5a6c7d'
    },
    success: {
      main: '#27ae60',
      light: '#2ecc71',
      dark: '#219a52'
    },
    error: {
      main: '#e74c3c',
      light: '#ec7063',
      dark: '#c0392b'
    },
    warning: {
      main: '#f39c12',
      light: '#f4d03f',
      dark: '#d68910'
    }
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontSize: '2.5rem',
      fontWeight: 600,
      color: '#2c3e50'
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 600,
      color: '#2c3e50'
    },
    h3: {
      fontSize: '1.5rem',
      fontWeight: 500,
      color: '#2c3e50'
    },
    h4: {
      fontSize: '1.25rem',
      fontWeight: 500,
      color: '#2c3e50'
    },
    body1: {
      fontSize: '1rem',
      lineHeight: 1.5,
      color: '#2c3e50'
    },
    button: {
      textTransform: 'none',
      fontWeight: 500
    }
  },
  shape: {
    borderRadius: 8
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          border: '1px solid #e9ecef',
          transition: 'box-shadow 0.3s ease, transform 0.2s ease',
          '&:hover': {
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            transform: 'translateY(-2px)'
          }
        }
      }
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          padding: '8px 16px',
          boxShadow: 'none',
          '&:hover': {
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)'
          }
        }
      }
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          borderBottom: '1px solid #e9ecef'
        }
      }
    }
  }
});

const drawerWidth = 260;

const App = () => {
  // State management
  const [user, setUser] = useState(null);
  const [currentModule, setCurrentModule] = useState('dashboard');
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [anchorEl, setAnchorEl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });
  const [globalStats, setGlobalStats] = useState({
    totalSubscribers: 0,
    migrationJobs: 0,
    provisioningOperations: 0,
    systemHealth: 100
  });

  // Navigation items
  const navigationItems = [
    { id: 'dashboard', label: 'Dashboard', icon: <Dashboard />, description: 'Overview and statistics' },
    { id: 'provisioning', label: 'Provisioning', icon: <People />, description: 'Subscriber provisioning operations' },
    { id: 'migration', label: 'Migration', icon: <CloudSync />, description: 'Bulk migration and sync' },
    { id: 'bulk-operations', label: 'Bulk Operations', icon: <Analytics />, description: 'Bulk deletion and audit operations' },
    { id: 'data-query', label: 'Data Query', icon: <SearchIcon />, description: 'Query and export data' },
    { id: 'monitoring', label: 'Monitoring', icon: <Notifications />, description: 'System monitoring and alerts' },
    { id: 'analytics', label: 'Analytics', icon: <Analytics />, description: 'Detailed analytics and reports' }
  ];

  // Check authentication on component mount
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    if (token) {
      // Validate token and get user info
      api.getCurrentUser()
        .then(userData => {
          setUser(userData);
          loadGlobalStats();
        })
        .catch(error => {
          console.error('Authentication failed:', error);
          localStorage.removeItem('authToken');
        });
    }
  }, []);

  // Load global statistics
  const loadGlobalStats = async () => {
    try {
      setLoading(true);
      const stats = await api.getGlobalStats();
      setGlobalStats(stats);
    } catch (error) {
      console.error('Failed to load global stats:', error);
      showNotification('Failed to load statistics', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Authentication handlers
  const handleLogin = async (credentials) => {
    try {
      setLoading(true);
      const result = await api.login(credentials);
      localStorage.setItem('authToken', result.token);
      setUser(result.user);
      showNotification('Login successful', 'success');
      loadGlobalStats();
    } catch (error) {
      console.error('Login failed:', error);
      showNotification('Login failed. Please check your credentials.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    setUser(null);
    setCurrentModule('dashboard');
    setAnchorEl(null);
    showNotification('Logged out successfully', 'info');
  };

  // UI handlers
  const handleDrawerToggle = () => {
    setDrawerOpen(!drawerOpen);
  };

  const handleProfileMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleProfileMenuClose = () => {
    setAnchorEl(null);
  };

  const showNotification = (message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  };

  const hideNotification = () => {
    setNotification({ ...notification, open: false });
  };

  // Module renderer
  const renderModule = () => {
    const moduleProps = {
      user,
      onNotification: showNotification,
      globalStats,
      onStatsUpdate: loadGlobalStats
    };

    switch (currentModule) {
      case 'dashboard':
        return <Dashboard {...moduleProps} />;
      case 'provisioning':
        return <ProvisioningModule {...moduleProps} />;
      case 'migration':
        return <MigrationModule {...moduleProps} />;
      case 'bulk-operations':
        return <BulkOperationsModule {...moduleProps} />;
      case 'data-query':
        return <DataQueryModule {...moduleProps} />;
      case 'monitoring':
        return <MonitoringDashboard {...moduleProps} />;
      case 'analytics':
        return <AnalyticsModule {...moduleProps} />;
      default:
        return <Dashboard {...moduleProps} />;
    }
  };

  // If not authenticated, show login form
  if (!user) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box 
          sx={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
          }}
        >
          <LoginForm onLogin={handleLogin} loading={loading} />
        </Box>
        {/* Loading backdrop */}
        <Backdrop
          sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.drawer + 1 }}
          open={loading}
        >
          <CircularProgress color="inherit" />
        </Backdrop>
        {/* Notification snackbar */}
        <Snackbar
          open={notification.open}
          autoHideDuration={6000}
          onClose={hideNotification}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert onClose={hideNotification} severity={notification.severity} sx={{ width: '100%' }}>
            {notification.message}
          </Alert>
        </Snackbar>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <Box sx={{ display: 'flex' }}>
        <CssBaseline />
        
        {/* App Bar */}
        <AppBar
          position="fixed"
          sx={{
            width: { sm: `calc(100% - ${drawerOpen ? drawerWidth : 0}px)` },
            ml: { sm: `${drawerOpen ? drawerWidth : 0}px` },
            transition: 'width 0.3s, margin 0.3s'
          }}
        >
          <Toolbar>
            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={handleDrawerToggle}
              sx={{ mr: 2, display: { sm: 'none' } }}
            >
              <MenuIcon />
            </IconButton>
            
            <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
              Subscriber Migration Portal - {navigationItems.find(item => item.id === currentModule)?.label || 'Dashboard'}
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {/* System Health Indicator */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Box
                  sx={{
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    backgroundColor: globalStats.systemHealth > 90 ? '#27ae60' : 
                                   globalStats.systemHealth > 70 ? '#f39c12' : '#e74c3c'
                  }}
                />
                <Typography variant="body2" sx={{ color: 'inherit', fontSize: '0.875rem' }}>
                  System: {globalStats.systemHealth}%
                </Typography>
              </Box>
              
              {/* User Profile */}
              <IconButton
                size="large"
                aria-label="account of current user"
                aria-controls="primary-search-account-menu"
                aria-haspopup="true"
                onClick={handleProfileMenuOpen}
                color="inherit"
                sx={{ padding: 1 }}
              >
                <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main' }}>
                  {user.username?.charAt(0).toUpperCase() || 'U'}
                </Avatar>
              </IconButton>
            </Box>
          </Toolbar>
        </AppBar>

        {/* User Profile Menu */}
        <Menu
          anchorEl={anchorEl}
          id="primary-search-account-menu"
          keepMounted
          open={Boolean(anchorEl)}
          onClose={handleProfileMenuClose}
          PaperProps={{
            elevation: 8,
            sx: {
              overflow: 'visible',
              filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.32))',
              mt: 1.5,
              minWidth: 200,
              '& .MuiAvatar-root': {
                width: 24,
                height: 24,
                ml: -0.5,
                mr: 1,
              },
            }
          }}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
        >
          <MenuItem onClick={handleProfileMenuClose}>
            <Avatar sx={{ bgcolor: 'primary.main' }} /> 
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 500 }}>
                {user.username || 'Unknown User'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {user.role || 'User'}
              </Typography>
            </Box>
          </MenuItem>
          <Divider />
          <MenuItem onClick={handleLogout}>
            <Logout fontSize="small" sx={{ mr: 2 }} />
            Logout
          </MenuItem>
        </Menu>

        {/* Navigation Drawer */}
        <Drawer
          variant="temporary"
          open={drawerOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerWidth,
              background: 'linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%)',
              borderRight: '1px solid #e9ecef'
            }
          }}
        >
          <DrawerContent 
            navigationItems={navigationItems}
            currentModule={currentModule}
            onModuleChange={setCurrentModule}
            user={user}
            globalStats={globalStats}
          />
        </Drawer>
        
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: drawerOpen ? drawerWidth : 0,
              transition: 'width 0.3s',
              overflow: 'hidden',
              background: 'linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%)',
              borderRight: '1px solid #e9ecef'
            }
          }}
          open={drawerOpen}
        >
          <DrawerContent 
            navigationItems={navigationItems}
            currentModule={currentModule}
            onModuleChange={setCurrentModule}
            user={user}
            globalStats={globalStats}
          />
        </Drawer>

        {/* Main Content */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            width: { sm: `calc(100% - ${drawerOpen ? drawerWidth : 0}px)` },
            transition: 'width 0.3s',
            minHeight: '100vh',
            backgroundColor: 'background.default'
          }}
        >
          <Toolbar />
          <Container maxWidth="xl" sx={{ py: 3 }}>
            {renderModule()}
          </Container>
        </Box>

        {/* Global Loading Backdrop */}
        <Backdrop
          sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.drawer + 1 }}
          open={loading}
        >
          <CircularProgress color="inherit" />
        </Backdrop>

        {/* Global Notification Snackbar */}
        <Snackbar
          open={notification.open}
          autoHideDuration={6000}
          onClose={hideNotification}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert onClose={hideNotification} severity={notification.severity} sx={{ width: '100%' }}>
            {notification.message}
          </Alert>
        </Snackbar>
      </Box>
    </ThemeProvider>
  );
};

// Drawer Content Component
const DrawerContent = ({ navigationItems, currentModule, onModuleChange, user, globalStats }) => {
  return (
    <>
      {/* Header */}
      <Box sx={{ p: 2, borderBottom: '1px solid #e9ecef' }}>
        <Typography variant="h6" sx={{ 
          color: 'primary.main', 
          fontWeight: 600,
          textAlign: 'center'
        }}>
          Migration Portal
        </Typography>
        <Typography variant="caption" sx={{ 
          color: 'text.secondary',
          textAlign: 'center',
          display: 'block'
        }}>
          Enterprise Edition
        </Typography>
      </Box>

      {/* Quick Stats */}
      <Box sx={{ p: 2, borderBottom: '1px solid #e9ecef' }}>
        <Grid container spacing={1}>
          <Grid item xs={6}>
            <Card sx={{ p: 1, textAlign: 'center', backgroundColor: 'primary.light', color: 'white' }}>
              <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                {globalStats.totalSubscribers?.toLocaleString() || '0'}
              </Typography>
              <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                Subscribers
              </Typography>
            </Card>
          </Grid>
          <Grid item xs={6}>
            <Card sx={{ p: 1, textAlign: 'center', backgroundColor: 'success.main', color: 'white' }}>
              <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                {globalStats.migrationJobs || '0'}
              </Typography>
              <Typography variant="caption" sx={{ fontSize: '0.75rem' }}>
                Jobs
              </Typography>
            </Card>
          </Grid>
        </Grid>
      </Box>

      {/* Navigation Items */}
      <List sx={{ px: 1, py: 2 }}>
        {navigationItems.map((item) => (
          <ListItem 
            button 
            key={item.id}
            onClick={() => onModuleChange(item.id)}
            sx={{
              mb: 1,
              borderRadius: 2,
              transition: 'all 0.2s',
              backgroundColor: currentModule === item.id ? 'primary.light' : 'transparent',
              color: currentModule === item.id ? 'white' : 'text.primary',
              '&:hover': {
                backgroundColor: currentModule === item.id ? 'primary.main' : 'action.hover',
                transform: 'translateX(4px)'
              }
            }}
          >
            <ListItemIcon sx={{ 
              color: currentModule === item.id ? 'white' : 'primary.main',
              minWidth: 40
            }}>
              {item.icon}
            </ListItemIcon>
            <ListItemText 
              primary={
                <Typography variant="body2" sx={{ 
                  fontWeight: currentModule === item.id ? 600 : 400,
                  fontSize: '0.875rem'
                }}>
                  {item.label}
                </Typography>
              }
              secondary={
                <Typography variant="caption" sx={{ 
                  color: currentModule === item.id ? 'rgba(255,255,255,0.8)' : 'text.secondary',
                  fontSize: '0.75rem'
                }}>
                  {item.description}
                </Typography>
              }
            />
          </ListItem>
        ))}
      </List>

      {/* User Info Footer */}
      <Box sx={{ mt: 'auto', p: 2, borderTop: '1px solid #e9ecef' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main', fontSize: '0.875rem' }}>
            {user?.username?.charAt(0).toUpperCase() || 'U'}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ 
              fontWeight: 500, 
              fontSize: '0.875rem',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}>
              {user?.username || 'User'}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
              {user?.role || 'Role'}
            </Typography>
          </Box>
        </Box>
      </Box>
    </>
  );
};

export default App;