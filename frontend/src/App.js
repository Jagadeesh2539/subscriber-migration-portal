import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, Link } from 'react-router-dom'; 
import { AppBar, Toolbar, Typography, Button, Container, Box } from '@mui/material';
import Login from './auth/Login';
import SubscriberProvision from './provisioning/SubscriberProvision';
import BulkMigration from './migration/BulkMigration';
import { Home } from '@mui/icons-material';

function App() {
  const [auth, setAuth] = useState(null);

  useEffect(() => {
    // Check local storage for persistent user and token on initial load
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');
    if (token && user) setAuth(JSON.parse(user));
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setAuth(null);
  };

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
              <Button color="inherit" component={Link} to="/provision" startIcon={<Home />}>
                Provisioning
              </Button>
              <Button color="inherit" component={Link} to="/migration">
                Migration
              </Button>
              <Box sx={{ ml: 3, p: 1, bgcolor: '#42a5f5', borderRadius: 1 }}>
                <Typography variant="body2">
                    Logged in as: **{auth.username}** ({auth.role})
                </Typography>
              </Box>
              <Button color="inherit" onClick={handleLogout} sx={{ ml: 2, bgcolor: '#f44336', '&:hover': { bgcolor: '#e53935' } }}>
                Logout
              </Button>
            </>
          )}
        </Toolbar>
      </AppBar>

      {/* Main Content Container */}
      <Container maxWidth="xl" sx={{ p: 0 }}>
        <Box sx={{ mt: 3, mb: 5 }}>
          <Routes>
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

            {/* Default route */}
            <Route
              path="/"
              element={auth ? <Navigate to="/provision" /> : <Navigate to="/login" />}
            />

            {/* Catch-all 404 */}
            <Route path="*" element={
                <Box sx={{ textAlign: 'center', mt: 10 }}>
                    <Typography variant="h4" color="error">404 - Page Not Found</Typography>
                    <Button component={Link} to="/" variant="contained" sx={{ mt: 3 }}>Go Home</Button>
                </Box>
            } />
          </Routes>
        </Box>
      </Container>
    </>
  );
}

export default App;
