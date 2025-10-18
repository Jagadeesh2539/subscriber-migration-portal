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

  const PrivateRoute = ({ children }) => auth ? children : <Navigate to="/login" />;

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
            <Route path="/provision" element={<PrivateRoute><SubscriberProvision /></PrivateRoute>} />
            <Route path="/migration" element={<PrivateRoute><BulkMigration /></PrivateRoute>} />
            <Route path="/" element={<Navigate to="/provision" />} />
          </Routes>
        </Box>
      </Container>
    </BrowserRouter>
  );
}

export default App;
