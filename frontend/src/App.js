import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'; 
import { 
  AppBar, Toolbar, Typography, Button, Container, Box, 
  Drawer, List, ListItem, ListItemButton, ListItemIcon, 
  ListItemText, Divider, CssBaseline, useTheme,
  IconButton, ListSubheader // ListSubheader added for section headers
} from '@mui/material';
import { 
  Menu as MenuIcon, Dashboard as DashboardIcon, PersonAdd, Search, 
  CloudUpload, Description
} from '@mui/icons-material';

import Login from './auth/Login';
import SubscriberProvision from './provisioning/SubscriberProvision';
import BulkMigration from './migration/BulkMigration';

// Components mapped to specific views within the Provisioning component
const ProvisioningDashboard = () => <SubscriberProvision view="dashboard" />;
const SubscriberCreate = () => <SubscriberProvision view="create" />;
const SubscriberSearch = () => <SubscriberProvision view="search" />;
const MigrationUploader = () => <BulkMigration view="bulk" />; // Renamed for clarity
const MigrationReports = () => <BulkMigration view="reports" />; // Placeholder for reports

const drawerWidth = 240;

const NavigationItems = [
  { text: 'Dashboard', path: '/provision/dashboard', icon: <DashboardIcon />, section: 'Provisioning' },
  { text: 'Create Profile', path: '/provision/create', icon: <PersonAdd />, section: 'Provisioning' },
  { text: 'Search / Modify', path: '/provision/search', icon: <Search />, section: 'Provisioning' },
  { text: 'Bulk Uploader', path: '/migration/bulk', icon: <CloudUpload />, section: 'Migration' },
  { text: 'Migration Reports', path: '/migration/reports', icon: <Description />, section: 'Migration' },
];


function App() {
  const [auth, setAuth] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const theme = useTheme();
  const location = useLocation();

  useEffect(() => {
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');
    if (token && user) setAuth(JSON.parse(user));
  }, []);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setAuth(null);
    // Navigate back to login
    window.location.href = '/login'; 
  };
  
  const drawer = (
    <div>
      {/* Custom header for the sidebar */}
      <Toolbar sx={{ backgroundColor: theme.palette.primary.main, minHeight: '64px!important' }}>
        <Typography variant="h6" color="white">Portal Menu</Typography>
      </Toolbar>
      <Divider />
      
      {/* Provisioning Section */}
      <List subheader={<ListSubheader>SUBSCRIBER PROVISIONING</ListSubheader>}>
        {NavigationItems.filter(item => item.section === 'Provisioning').map((item) => (
          <ListItem key={item.path} disablePadding>
            <ListItemButton 
              component={Link} 
              to={item.path}
              selected={location.pathname === item.path}
              onClick={handleDrawerToggle} // Close drawer on mobile click
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      
      <Divider />

      {/* Migration Section */}
      <List subheader={<ListSubheader>MIGRATION MANAGEMENT</ListSubheader>}>
        {NavigationItems.filter(item => item.section === 'Migration').map((item) => (
          <ListItem key={item.path} disablePadding>
            <ListItemButton 
              component={Link} 
              to={item.path}
              selected={location.pathname === item.path}
              onClick={handleDrawerToggle} // Close drawer on mobile click
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </div>
  );

  if (!auth) {
    // Render only the login page if not authenticated
    return (
      <Routes>
        <Route path="/login" element={<Login setAuth={setAuth} />} />
        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    );
  }

  // Authenticated Layout
  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBar 
        position="fixed" 
        sx={{ 
          width: { md: `calc(100% - ${drawerWidth}px)` }, 
          ml: { md: `${drawerWidth}px` } 
        }}
      >
        <Toolbar>
          {/* Menu icon for mobile */}
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            Subscriber Management Portal
          </Typography>
          <Button color="inherit" onClick={handleLogout}>Logout ({auth.username})</Button>
        </Toolbar>
      </AppBar>
      
      {/* Sidebar Navigation */}
      <Box
        component="nav"
        sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}
        aria-label="Provisioning and Migration Menus"
      >
        {/* Mobile Drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        
        {/* Desktop Permanent Sidebar */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>
      
      {/* Main Content Area */}
      <Box
        component="main"
        sx={{ 
          flexGrow: 1, 
          p: 3, 
          width: { md: `calc(100% - ${drawerWidth}px)` },
          mt: 8 
        }}
      >
        <Routes>
          {/* Provisioning Routes */}
          <Route path="/provision/dashboard" element={<ProvisioningDashboard />} />
          <Route path="/provision/create" element={<SubscriberCreate />} />
          <Route path="/provision/search" element={<SubscriberSearch />} />
          
          {/* Migration Routes */}
          <Route path="/migration/bulk" element={<MigrationUploader />} />
          <Route path="/migration/reports" element={<MigrationReports />} />

          {/* Default Route */}
          <Route path="/" element={<Navigate to="/provision/dashboard" />} />
          <Route path="*" element={<Typography sx={{ p: 2 }}>404 - Page Not Found</Typography>} />
        </Routes>
      </Box>
    </Box>
  );
}

export default App;
