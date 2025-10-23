import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Paper, TextField, Button, Typography, Alert, Box } from '@mui/material';
import API from '../api';

export default function Login({ setAuth }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const { data } = await API.post('/users/login', { username, password });
      localStorage.setItem('token', data.token);
      localStorage.setItem('user', JSON.stringify(data.user));
      setAuth(data.user);
      navigate('/provision');
    } catch (err) {
      setError(err.response?.data?.msg || 'Login failed');
    }
  };

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="80vh">
      <Paper sx={{ p: 4, width: 400 }}>
        <Typography variant="h5" gutterBottom>Login</Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <form onSubmit={handleSubmit}>
          <TextField fullWidth label="Username" value={username} onChange={e => setUsername(e.target.value)} margin="normal" required />
          <TextField fullWidth label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} margin="normal" required />
          <Button type="submit" fullWidth variant="contained" sx={{ mt: 3 }}>Login</Button>
        </form>
        <Typography variant="caption" display="block" sx={{ mt: 2 }}>
          Test accounts: admin/Admin@123, operator/Operator@123, guest/Guest@123
        </Typography>
      </Paper>
    </Box>
  );
}
