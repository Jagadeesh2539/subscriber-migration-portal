import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  InputAdornment,
  IconButton,
  CircularProgress,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Divider
} from '@mui/material';
import {
  Visibility,
  VisibilityOff,
  AccountCircle,
  Lock,
  Business,
  CloudSync
} from '@mui/icons-material';

const LoginForm = ({ onLogin, loading }) => {
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    role: 'operator'
  });
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({});
  const [loginMode, setLoginMode] = useState('credentials'); // credentials, demo

  // Demo accounts
  const demoAccounts = [
    { username: 'admin', password: 'Admin@123', role: 'admin', description: 'Full system access' },
    { username: 'operator', password: 'Operator@123', role: 'operator', description: 'Migration and provisioning' },
    { username: 'guest', password: 'Guest@123', role: 'guest', description: 'Read-only access' }
  ];

  const roles = [
    { value: 'admin', label: 'Administrator', description: 'Full system access and management' },
    { value: 'operator', label: 'Operator', description: 'Migration and provisioning operations' },
    { value: 'guest', label: 'Guest', description: 'Read-only access to data and reports' }
  ];

  // Handle input changes
  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: '' }));
    }
  };

  // Validate form
  const validateForm = () => {
    const newErrors = {};
    
    if (!formData.username.trim()) {
      newErrors.username = 'Username is required';
    }
    
    if (!formData.password.trim()) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters';
    }
    
    if (!formData.role) {
      newErrors.role = 'Role is required';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    try {
      await onLogin(formData);
    } catch (error) {
      setErrors({ general: 'Login failed. Please check your credentials.' });
    }
  };

  // Handle demo login
  const handleDemoLogin = (demoAccount) => {
    setFormData({
      username: demoAccount.username,
      password: demoAccount.password,
      role: demoAccount.role
    });
  };

  // Toggle password visibility
  const togglePasswordVisibility = () => {
    setShowPassword(!showPassword);
  };

  return (
    <Box sx={{ maxWidth: 450, width: '100%', mx: 2 }}>
      {/* Header */}
      <Box sx={{ textAlign: 'center', mb: 4, color: 'white' }}>
        <CloudSync sx={{ fontSize: 60, mb: 2 }} />
        <Typography variant="h3" sx={{ fontWeight: 600, mb: 1 }}>
          Migration Portal
        </Typography>
        <Typography variant="h6" sx={{ opacity: 0.9 }}>
          Enterprise Subscriber Management
        </Typography>
      </Box>

      {/* Login Card */}
      <Card sx={{ 
        borderRadius: 3,
        boxShadow: '0 20px 40px rgba(0,0,0,0.3)',
        backdropFilter: 'blur(10px)',
        backgroundColor: 'rgba(255,255,255,0.95)'
      }}>
        <CardContent sx={{ p: 4 }}>
          {/* Mode Toggle */}
          <Box sx={{ display: 'flex', gap: 1, mb: 3 }}>
            <Button
              variant={loginMode === 'credentials' ? 'contained' : 'outlined'}
              onClick={() => setLoginMode('credentials')}
              size="small"
              sx={{ flex: 1 }}
            >
              Login
            </Button>
            <Button
              variant={loginMode === 'demo' ? 'contained' : 'outlined'}
              onClick={() => setLoginMode('demo')}
              size="small"
              sx={{ flex: 1 }}
            >
              Demo Accounts
            </Button>
          </Box>

          {loginMode === 'credentials' ? (
            <>
              <Typography variant="h5" sx={{ mb: 3, textAlign: 'center', fontWeight: 600 }}>
                Sign In
              </Typography>

              {errors.general && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {errors.general}
                </Alert>
              )}

              <Box component="form" onSubmit={handleSubmit} sx={{ space: 2 }}>
                {/* Username */}
                <TextField
                  fullWidth
                  label="Username"
                  value={formData.username}
                  onChange={(e) => handleInputChange('username', e.target.value)}
                  error={!!errors.username}
                  helperText={errors.username}
                  disabled={loading}
                  sx={{ mb: 2 }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <AccountCircle color="action" />
                      </InputAdornment>
                    ),
                  }}
                />

                {/* Password */}
                <TextField
                  fullWidth
                  label="Password"
                  type={showPassword ? 'text' : 'password'}
                  value={formData.password}
                  onChange={(e) => handleInputChange('password', e.target.value)}
                  error={!!errors.password}
                  helperText={errors.password}
                  disabled={loading}
                  sx={{ mb: 2 }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Lock color="action" />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={togglePasswordVisibility}
                          edge="end"
                          disabled={loading}
                        >
                          {showPassword ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />

                {/* Role Selection */}
                <FormControl fullWidth sx={{ mb: 3 }} error={!!errors.role}>
                  <InputLabel>Role</InputLabel>
                  <Select
                    value={formData.role}
                    label="Role"
                    onChange={(e) => handleInputChange('role', e.target.value)}
                    disabled={loading}
                    startAdornment={
                      <InputAdornment position="start">
                        <Business color="action" sx={{ ml: 1 }} />
                      </InputAdornment>
                    }
                  >
                    {roles.map((role) => (
                      <MenuItem key={role.value} value={role.value}>
                        <Box>
                          <Typography variant="body1">{role.label}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {role.description}
                          </Typography>
                        </Box>
                      </MenuItem>
                    ))}
                  </Select>
                  {errors.role && (
                    <Typography variant="caption" color="error" sx={{ mt: 0.5, ml: 2 }}>
                      {errors.role}
                    </Typography>
                  )}
                </FormControl>

                {/* Submit Button */}
                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  size="large"
                  disabled={loading}
                  sx={{ 
                    py: 1.5,
                    fontSize: '1.1rem',
                    fontWeight: 600,
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%)'
                    }
                  }}
                >
                  {loading ? (
                    <>
                      <CircularProgress size={24} color="inherit" sx={{ mr: 1 }} />
                      Signing In...
                    </>
                  ) : (
                    'Sign In'
                  )}
                </Button>
              </Box>
            </>
          ) : (
            <>
              <Typography variant="h5" sx={{ mb: 3, textAlign: 'center', fontWeight: 600 }}>
                Demo Accounts
              </Typography>
              
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3, textAlign: 'center' }}>
                Click on any demo account to automatically fill in the credentials
              </Typography>

              <Box sx={{ space: 2 }}>
                {demoAccounts.map((account, index) => (
                  <Card 
                    key={account.username}
                    sx={{ 
                      mb: 2, 
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      '&:hover': {
                        boxShadow: 3,
                        transform: 'translateY(-2px)'
                      }
                    }}
                    onClick={() => handleDemoLogin(account)}
                  >
                    <CardContent sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Box>
                          <Typography variant="h6" sx={{ fontWeight: 600, color: 'primary.main' }}>
                            {account.role.charAt(0).toUpperCase() + account.role.slice(1)}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {account.description}
                          </Typography>
                          <Typography variant="caption" sx={{ fontFamily: 'monospace', mt: 0.5, display: 'block' }}>
                            {account.username} / {account.password}
                          </Typography>
                        </Box>
                        <AccountCircle 
                          sx={{ 
                            fontSize: 40, 
                            color: index === 0 ? 'error.main' : index === 1 ? 'primary.main' : 'success.main'
                          }} 
                        />
                      </Box>
                    </CardContent>
                  </Card>
                ))}

                <Divider sx={{ my: 2 }} />
                
                {/* Quick Login Button for Demo */}
                {formData.username && (
                  <Button
                    fullWidth
                    variant="contained"
                    size="large"
                    onClick={handleSubmit}
                    disabled={loading}
                    sx={{ 
                      py: 1.5,
                      fontSize: '1.1rem',
                      fontWeight: 600,
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      '&:hover': {
                        background: 'linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%)'
                      }
                    }}
                  >
                    {loading ? (
                      <>
                        <CircularProgress size={24} color="inherit" sx={{ mr: 1 }} />
                        Signing In as {formData.role}...
                      </>
                    ) : (
                      `Sign In as ${formData.role.charAt(0).toUpperCase() + formData.role.slice(1)}`
                    )}
                  </Button>
                )}
              </Box>
            </>
          )}
        </CardContent>
      </Card>

      {/* Footer */}
      <Box sx={{ textAlign: 'center', mt: 3, color: 'rgba(255,255,255,0.8)' }}>
        <Typography variant="body2">
          Enterprise Subscriber Migration Portal v2.0
        </Typography>
        <Typography variant="caption">
          Secure • Scalable • Reliable
        </Typography>
      </Box>
    </Box>
  );
};

export default LoginForm;