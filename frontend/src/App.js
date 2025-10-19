import React, { useState, useEffect } from 'react';
import { Home } from '@mui/icons-material';
import { Routes, Route, Navigate, Link } from 'react-router-dom';
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
  Container,
  Box,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
} from '@mui/material';

import Login from './auth/Login';
import SubscriberProvision from './provisioning/SubscriberProvision';
import BulkMigration from './migration/BulkMigration';

// --- New Component: Logout Confirmation Modal ---
const LogoutConfirmModal = ({ open, handleClose, handleConfirm }) => (
  <Dialog open={open} onClose={handleClose}>
    <DialogTitle>Confirm Logout</DialogTitle>
    <DialogContent dividers>
      <Typography>Are you sure you want to log out of the Subscriber Portal?</Typography>
    </DialogContent>
    <DialogActions>
      <Button onClick={handleClose} color="primary">
        Cancel
      </Button>
      <Button onClick={handleConfirm} color="error" variant="contained">
        Logout
      </Button>
    </DialogActions>
  </Dialog>
);
// ---------------------------------------------


function App() {
  const [auth, setAuth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isLogoutModalOpen, setIsLogoutModalOpen] = useState(false);

  useEffect(() => {
    // Check local storage for persistent user and token on initial load
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');
    if (token && user) setAuth(JSON.parse(user));
    setLoading(false);
  }, []);

  const initiateLogout = () => {
    setIsLogoutModalOpen(true);
  };

  const handleConfirmLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setAuth(null);
    setIsLogoutModalOpen(false);
  };

  // Display a loading screen briefly while verifying localStorage
  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
        }}
      >
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ ml: 2 }}>
          Loading Application...
        </Typography>
      </Box>
    );
  }

  return (
    <>
      {/* Top Application Bar */}
      <AppBar position="static" sx={{ bgcolor: '#1976d2' }}>
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1, fontWeight: 'bold' }}>
            Subscriber Provisioning & Migration Portal
          </Typography>

          {auth && (
            <>
              <Button
                color="inherit"
                component={Link}
                to="/provision"
                startIcon={<Home />}
              >
                Provisioning
              </Button>
              <Button color="inherit" component={Link} to="/migration">
                Migration
              </Button>

              {/* User info block with professional styling */}
              <Box
                sx={{
                  ml: 3,
                  px: 2,
                  py: 1,
                  bgcolor: '#42a5f5',
                  borderRadius: 1,
                }}
              >
                <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                  User: <strong>{auth.username}</strong> ({auth.role.toUpperCase()})
                </Typography>
              </Box>

              {/* Logout button triggers the modal */}
              <Button
                color="inherit"
                onClick={initiateLogout}
                sx={{
                  ml: 2,
                  bgcolor: '#f44336',
                  '&:hover': { bgcolor: '#e53935' },
                }}
              >
                Logout
              </Button>
            </>
          )}
        </Toolbar>
      </AppBar>

      {/* Main Content */}
      <Container maxWidth="xl" sx={{ p: 0 }}>
        <Box sx={{ mt: 3, mb: 5 }}>
          <Routes>
            {/* Public login route */}
            <Route path="/login" element={<Login setAuth={setAuth} />} />

            {/* Protected routes */}
            <Route
              path="/provision"
              element={auth ? <SubscriberProvision /> : <Navigate to="/login" />}
            />
            <Route
              path="/migration"
              element={auth ? <BulkMigration /> : <Navigate to="/login" />}
            />

            {/* Default redirect */}
            <Route
              path="/"
              element={auth ? <Navigate to="/provision" /> : <Navigate to="/login" />}
            />

            {/* 404 Page */}
            <Route
              path="*"
              element={
                <Box sx={{ textAlign: 'center', mt: 10 }}>
                  <Typography variant="h4" color="error">
                    404 - Page Not Found
                  </Typography>
                  <Button
                    component={Link}
                    to="/"
                    variant="contained"
                    sx={{ mt: 3 }}
                  >
                    Go Home
                  </Button>
                </Box>
              }
            />
          </Routes>
        </Box>
      </Container>
      
      {/* Logout Confirmation Modal is rendered outside the router */}
      <LogoutConfirmModal
        open={isLogoutModalOpen}
        handleClose={() => setIsLogoutModalOpen(false)}
        handleConfirm={handleConfirmLogout}
      />
    </>
  );
}

export default App;
