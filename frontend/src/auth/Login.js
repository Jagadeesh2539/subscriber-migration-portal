import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Paper, TextField, Button, Typography, Alert, Box } from '@mui/material';
import apiService from '../api';

export default function Login({ setAuth }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      // Use the correct API service method
      const response = await apiService.login({ username, password });
      
      console.log('Login response:', response); // Debug log
      
      // Backend returns: {status: "success", data: {token, user, expires_in}, message}
      if (response.status === 'success' && response.data) {
        setAuth(response.data.user);
        navigate('/dashboard'); // Navigate to dashboard
      } else {
        setError(response.message || 'Login failed');
      }
    } catch (err) {
      console.error('Login error:', err);
      const errorMessage = err.response?.data?.message || err.response?.data?.msg || err.message || 'Login failed - please check your credentials';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="80vh">
      <Paper sx={{ p: 4, width: 400 }}>
        <Typography variant="h5" gutterBottom align="center">
          🏢 Enterprise Portal Login
        </Typography>
        
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        
        <form onSubmit={handleSubmit}>
          <TextField 
            fullWidth 
            label="Username" 
            value={username} 
            onChange={e => setUsername(e.target.value)} 
            margin="normal" 
            required 
            disabled={loading}
          />
          <TextField 
            fullWidth 
            label="Password" 
            type="password" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
            margin="normal" 
            required 
            disabled={loading}
          />
          <Button 
            type="submit" 
            fullWidth 
            variant="contained" 
            sx={{ mt: 3 }} 
            disabled={loading}
          >
            {loading ? 'Logging in...' : 'Login'}
          </Button>
        </form>
        
        <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
          <Typography variant="body2" fontWeight="bold" gutterBottom>
            🔐 Test Accounts:
          </Typography>
          <Typography variant="caption" display="block">
            <strong>Admin:</strong> admin / Admin@123
          </Typography>
          <Typography variant="caption" display="block">
            <strong>Operator:</strong> operator / Operator@123
          </Typography>
          <Typography variant="caption" display="block">
            <strong>Guest:</strong> guest / Guest@123
          </Typography>
        </Box>
      </Paper>
    </Box>
  );
}
