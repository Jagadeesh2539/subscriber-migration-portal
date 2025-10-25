import React, { useState, useEffect } from 'react';
import {
  AppBar, Toolbar, Typography, Drawer, List, ListItem, ListItemIcon, ListItemText,
  Box, CssBaseline, IconButton, Alert, Chip, Badge, Avatar, Menu, MenuItem,
  Divider, ListSubheader, Collapse
} from '@mui/material';
import {
  Menu as MenuIcon, Dashboard, Settings, CloudUpload, GetApp, Assessment,
  PersonAdd, Storage, Cloud, Sync, Delete, Audit, MonitorHeart,
  ExitToApp, AccountCircle, ExpandLess, ExpandMore, History,
  BugReport, Security, Speed
} from '@mui/icons-material';
import { createTheme, ThemeProvider } from '@mui/material/styles';

// Import components
import Login from './auth/Login';
import EnhancedBulkOperations from './migration/EnhancedBulkOperations';
import ProvisioningConsole from './provisioning/ProvisioningConsole';
import SystemDashboard from './monitoring/SystemDashboard';
import BulkMigration from './migration/BulkMigration'; // Fallback to existing

// Professional theme configuration
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      dark: '#1565c0',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
  typography: {
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        },
      },
    },
  },
});

const DRAWER_WIDTH = 280;

// Main App Component
function EnhancedApp() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [jobs, setJobs] = useState([]);
  const [systemStatus, setSystemStatus] = useState('healthy');
  const [migrationSubmenuOpen, setMigrationSubmenuOpen] = useState(false);
  const [provisionSubmenuOpen, setProvisionSubmenuOpen] = useState(false);
  const [profileMenuAnchor, setProfileMenuAnchor] = useState(null);

  // Check authentication on app load
  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    
    if (token && userData) {
      try {
        const userObj = JSON.parse(userData);
        setUser(userObj);
        setIsAuthenticated(true);
      } catch (error) {
        console.error('Invalid user data:', error);
        handleLogout();
      }
    }
  }, []);

  const handleLogin = (userData, token) => {
    setUser(userData);
    setIsAuthenticated(true);
    localStorage.setItem('user', JSON.stringify(userData));
    localStorage.setItem('token', token);
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('migrationJobs');
    setCurrentPage('dashboard');
    setProfileMenuAnchor(null);
  };

  // Navigation menu structure
  const navigationMenu = [
    {
      id: 'dashboard',
      label: 'System Dashboard',
      icon: <Dashboard />,
      component: 'dashboard'
    },
    {
      id: 'provisioning',
      label: 'Provisioning',
      icon: <Settings />,
      submenu: [
        {
          id: 'single-provision',
          label: 'Single Provision',
          icon: <PersonAdd />,
          component: 'provisioning'
        },
        {
          id: 'provision-history',
          label: 'Provision History',
          icon: <History />,
          component: 'provisioning'
        }
      ]
    },
    {
      id: 'migration',
      label: 'Migration Operations',
      icon: <CloudUpload />,
      submenu: [
        {
          id: 'bulk-migration',
          label: 'Bulk Migration',
          icon: <CloudUpload />,
          component: 'migration'
        },
        {
          id: 'bulk-deletion',
          label: 'Bulk Deletion',
          icon: <Delete />,
          component: 'bulk-delete'
        },
        {
          id: 'bulk-audit',
          label: 'Bulk Audit',
          icon: <Audit />,
          component: 'bulk-audit'
        },
        {
          id: 'data-export',
          label: 'Data Export',
          icon: <GetApp />,
          component: 'data-export'
        }
      ]
    },
    {
      id: 'monitoring',
      label: 'System Health',
      icon: <MonitorHeart />,
      component: 'monitoring'
    }
  ];

  const renderContent = () => {
    switch (currentPage) {
      case 'dashboard':
        return <SystemDashboard />;
      case 'provisioning':
        return <ProvisioningConsole />;
      case 'migration':
        return (
          <EnhancedBulkOperations 
            operationType="MIGRATION"
            jobs={jobs}
            setJobs={setJobs}
            userRole={user?.role}
            uploading={false}
            setUploading={() => {}}
            setMessage={() => {}}
          />
        );
      case 'bulk-delete':
        return (
          <EnhancedBulkOperations 
            operationType="BULK_DELETE"
            jobs={jobs}
            setJobs={setJobs}
            userRole={user?.role}
            uploading={false}
            setUploading={() => {}}
            setMessage={() => {}}
          />
        );
      case 'bulk-audit':
        return (
          <EnhancedBulkOperations 
            operationType="BULK_AUDIT"
            jobs={jobs}
            setJobs={setJobs}
            userRole={user?.role}
            uploading={false}
            setUploading={() => {}}
            setMessage={() => {}}
          />
        );
      case 'data-export':
        return (
          <EnhancedBulkOperations 
            operationType="DATA_EXPORT"
            jobs={jobs}
            setJobs={setJobs}
            userRole={user?.role}
            uploading={false}
            setUploading={() => {}}
            setMessage={() => {}}
          />
        );
      case 'monitoring':
        return <SystemDashboard />;
      default:
        return <SystemDashboard />;
    }
  };

  if (!isAuthenticated) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box 
          sx={{ 
            minHeight: '100vh',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          <Login onLogin={handleLogin} />
        </Box>
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
            width: drawerOpen ? `calc(100% - ${DRAWER_WIDTH}px)` : '100%',
            ml: drawerOpen ? `${DRAWER_WIDTH}px` : 0,
            transition: theme.transitions.create(['width', 'margin'], {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.leavingScreen,
            })
          }}
        >
          <Toolbar>
            <IconButton
              edge="start"
              color="inherit"
              onClick={() => setDrawerOpen(!drawerOpen)}
              sx={{ mr: 2 }}
            >
              <MenuIcon />
            </IconButton>
            
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              OSS/BSS Subscriber Management Portal
            </Typography>
            
            <Box display="flex" alignItems="center" gap={1}>
              <Chip 
                icon={systemStatus === 'healthy' ? <CheckCircle /> : <Warning />}
                label={systemStatus === 'healthy' ? 'System Healthy' : 'System Issues'}
                size="small"
                color={systemStatus === 'healthy' ? 'success' : 'warning'}
                variant="outlined"
                sx={{ color: 'white', borderColor: 'white' }}
              />
              
              <IconButton
                color="inherit"
                onClick={(e) => setProfileMenuAnchor(e.currentTarget)}
              >
                <Avatar sx={{ width: 32, height: 32, bgcolor: 'secondary.main' }}>
                  {user?.username?.charAt(0).toUpperCase()}
                </Avatar>
              </IconButton>
            </Box>
          </Toolbar>
        </AppBar>

        {/* Profile Menu */}
        <Menu
          anchorEl={profileMenuAnchor}
          open={Boolean(profileMenuAnchor)}
          onClose={() => setProfileMenuAnchor(null)}
        >
          <MenuItem disabled>
            <AccountCircle sx={{ mr: 1 }} />
            {user?.username} ({user?.role})
          </MenuItem>
          <Divider />
          <MenuItem onClick={handleLogout}>
            <ExitToApp sx={{ mr: 1 }} />
            Logout
          </MenuItem>
        </Menu>

        {/* Navigation Drawer */}
        <Drawer
          variant="persistent"
          anchor="left"
          open={drawerOpen}
          sx={{
            width: DRAWER_WIDTH,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: DRAWER_WIDTH,
              boxSizing: 'border-box',
              backgroundColor: '#f8f9fa',
              borderRight: '1px solid #e0e0e0'
            },
          }}
        >
          <Toolbar>
            <Typography variant="h6" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
              Enterprise Portal
            </Typography>
          </Toolbar>
          
          <Divider />
          
          <List sx={{ pt: 1 }}>
            {navigationMenu.map((item) => (
              <React.Fragment key={item.id}>
                {item.submenu ? (
                  // Menu item with submenu
                  <>
                    <ListItem 
                      button 
                      onClick={() => {
                        if (item.id === 'migration') {
                          setMigrationSubmenuOpen(!migrationSubmenuOpen);
                        } else if (item.id === 'provisioning') {
                          setProvisionSubmenuOpen(!provisionSubmenuOpen);
                        }
                      }}
                      sx={{ 
                        '&:hover': { backgroundColor: 'primary.light', color: 'white' },
                        borderRadius: 1, mx: 1
                      }}
                    >
                      <ListItemIcon>{item.icon}</ListItemIcon>
                      <ListItemText primary={item.label} />
                      {item.id === 'migration' ? 
                        (migrationSubmenuOpen ? <ExpandLess /> : <ExpandMore />) :
                        (provisionSubmenuOpen ? <ExpandLess /> : <ExpandMore />)
                      }
                    </ListItem>
                    
                    <Collapse 
                      in={item.id === 'migration' ? migrationSubmenuOpen : provisionSubmenuOpen} 
                      timeout="auto" 
                      unmountOnExit
                    >
                      <List component="div" disablePadding>
                        {item.submenu.map((subItem) => (
                          <ListItem
                            button
                            key={subItem.id}
                            onClick={() => setCurrentPage(subItem.component)}
                            sx={{ 
                              pl: 4, 
                              backgroundColor: currentPage === subItem.component ? 'primary.light' : 'transparent',
                              color: currentPage === subItem.component ? 'white' : 'inherit',
                              '&:hover': { backgroundColor: 'primary.light', color: 'white' },
                              borderRadius: 1, mx: 1
                            }}
                          >
                            <ListItemIcon sx={{ color: currentPage === subItem.component ? 'white' : 'inherit' }}>
                              {subItem.icon}
                            </ListItemIcon>
                            <ListItemText primary={subItem.label} />
                          </ListItem>
                        ))}
                      </List>
                    </Collapse>
                  </>
                ) : (
                  // Regular menu item
                  <ListItem
                    button
                    onClick={() => setCurrentPage(item.component)}
                    sx={{
                      backgroundColor: currentPage === item.component ? 'primary.main' : 'transparent',
                      color: currentPage === item.component ? 'white' : 'inherit',
                      '&:hover': { backgroundColor: 'primary.light', color: 'white' },
                      borderRadius: 1, mx: 1, mb: 0.5
                    }}
                  >
                    <ListItemIcon sx={{ color: currentPage === item.component ? 'white' : 'inherit' }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText primary={item.label} />
                  </ListItem>
                )
              )}
              </React.Fragment>
            ))}
          </List>
          
          <Divider sx={{ my: 2 }} />
          
          {/* System Status in Drawer */}
          <Box sx={{ p: 2 }}>
            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
              SYSTEM STATUS
            </Typography>
            <Chip 
              icon={systemStatus === 'healthy' ? <CheckCircle /> : <Warning />}
              label={systemStatus === 'healthy' ? 'All Systems Operational' : 'System Issues Detected'}
              size="small"
              color={systemStatus === 'healthy' ? 'success' : 'warning'}
              sx={{ width: '100%' }}
            />
            
            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 1 }}>
              Enterprise v2.0.0 | {jobs.length} Active Jobs
            </Typography>
          </Box>
        </Drawer>

        {/* Main Content */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            bgcolor: 'background.default',
            p: 3,
            width: drawerOpen ? `calc(100% - ${DRAWER_WIDTH}px)` : '100%',
            ml: drawerOpen ? 0 : `-${DRAWER_WIDTH}px`,
            transition: theme.transitions.create(['width', 'margin'], {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.enteringScreen,
            }),
            minHeight: '100vh',
            pt: '88px' // Account for AppBar height
          }}
        >
          {/* System Alert Banner */}
          {user?.role === 'admin' && systemStatus !== 'healthy' && (
            <Alert severity="warning" sx={{ mb: 3 }}>
              System monitoring has detected potential issues. Check the monitoring dashboard for details.
            </Alert>
          )}
          
          {/* Page Content */}
          {renderContent()}
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default EnhancedApp;