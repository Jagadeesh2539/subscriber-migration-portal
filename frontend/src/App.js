import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import { AppBar, Toolbar, Typography, Button, Container, Box } from '@mui/material';
import Login from './auth/Login';
import SubscriberProvision from './provisioning/SubscriberProvision';
import BulkMigration from './migration/BulkMigration';

function App() {
  const [auth, setAuth] = useState(null);

  useEffect(() => {
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
    <BrowserRouter>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>Subscriber Portal</Typography>
          {auth && (
            <>
              <Button color="inherit" component={Link} to="/provision">Provisioning</Button>
              <Button color="inherit" component={Link} to="/migration">Migration</Button>
              <Button color="inherit" onClick={handleLogout}>Logout ({auth.username})</Button>
            </>
          )}
        </Toolbar>
      </AppBar>

      <Container>
        <Box sx={{ mt: 3 }}>
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
            <Route path="*" element={<Typography>Page Not Found</Typography>} />
          </Routes>
        </Box>
      </Container>
    </BrowserRouter>
  );
}

export default App;
