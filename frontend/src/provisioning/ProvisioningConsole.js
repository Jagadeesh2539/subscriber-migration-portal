import React, { useState, useEffect } from 'react';
import {
  Paper, Button, Typography, TextField, Select, MenuItem, FormControl, InputLabel,
  Card, Grid, Alert, Box, Chip, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Switch, FormControlLabel, Divider, IconButton, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions, Tabs, Tab
} from '@mui/material';
import {
  PersonAdd, Update, Delete, Pause, PlayArrow, Settings, History,
  Cloud, Storage, Sync, CheckCircle, Error, Warning, Info
} from '@mui/icons-material';
import API from '../api';

// Single Provision Request Component
const SingleProvisionForm = ({ mode, setMode, setMessage, refreshHistory }) => {
  const [formData, setFormData] = useState({
    operation: 'CREATE',
    uid: '',
    imsi: '',
    msisdn: '',
    status: 'ACTIVE',
    plan: '4G',
    callForwarding: false,
    odbicActive: true,
    odbocActive: true,
    csService: true,
    fourGService: true,
    fiveGService: false
  });
  
  const [submitting, setSubmitting] = useState(false);

  const operations = {
    'CREATE': { label: 'Create New', icon: <PersonAdd />, color: 'success' },
    'UPDATE': { label: 'Update Existing', icon: <Update />, color: 'info' },
    'SUSPEND': { label: 'Suspend Service', icon: <Pause />, color: 'warning' },
    'ACTIVATE': { label: 'Activate Service', icon: <PlayArrow />, color: 'success' },
    'DELETE': { label: 'Delete Subscriber', icon: <Delete />, color: 'error' }
  };

  const modes = {
    'LEGACY': { label: 'Legacy Mode', description: 'Provision in Legacy OSS/BSS only', icon: <Storage />, color: 'warning' },
    'CLOUD': { label: 'Cloud Mode', description: 'Provision in Cloud platform only', icon: <Cloud />, color: 'primary' },
    'DUAL_PROV': { label: 'Dual Provision', description: 'Provision in both Legacy and Cloud with consistency', icon: <Sync />, color: 'success' }
  };

  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleProvisionRequest = async () => {
    if (!formData.uid && !formData.imsi && !formData.msisdn) {
      setMessage({ type: 'error', text: 'Please provide at least one identifier (UID, IMSI, or MSISDN)' });
      return;
    }

    setSubmitting(true);
    setMessage({ type: 'info', text: `Processing ${operations[formData.operation].label} in ${modes[mode].label}...` });

    try {
      const requestPayload = {
        mode,
        operation: formData.operation,
        uid: formData.uid,
        imsi: formData.imsi,
        msisdn: formData.msisdn,
        payload: {
          status: formData.status,
          plan: formData.plan,
          callForwarding: formData.callForwarding,
          odbicActive: formData.odbicActive,
          odbocActive: formData.odbocActive,
          csService: formData.csService,
          fourGService: formData.fourGService,
          fiveGService: formData.fiveGService
        }
      };

      const response = await API.post('/provision/request', requestPayload);
      
      if (response.data.success) {
        setMessage({ 
          type: 'success', 
          text: `${operations[formData.operation].label} completed successfully in ${modes[mode].label}!` 
        });
        
        // Clear form after successful provision
        setFormData({
          operation: 'CREATE', uid: '', imsi: '', msisdn: '',
          status: 'ACTIVE', plan: '4G', callForwarding: false,
          odbicActive: true, odbocActive: true, csService: true,
          fourGService: true, fiveGService: false
        });
        
        // Refresh provision history
        if (refreshHistory) refreshHistory();
      }
    } catch (error) {
      console.error('Provision request failed:', error);
      setMessage({ 
        type: 'error', 
        text: `Provision failed: ${error.response?.data?.error || error.message}` 
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h6" sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
        <Settings sx={{ mr: 1 }} />
        Single Provision Request
      </Typography>

      {/* Mode Selection */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" sx={{ mb: 2 }}>Provisioning Mode</Typography>
        <Grid container spacing={2}>
          {Object.entries(modes).map(([key, config]) => (
            <Grid item xs={12} md={4} key={key}>
              <Card 
                variant={mode === key ? 'elevation' : 'outlined'}
                sx={{ 
                  p: 2, cursor: 'pointer', 
                  border: mode === key ? `2px solid` : '1px solid',
                  borderColor: mode === key ? `${config.color}.main` : 'divider',
                  '&:hover': { elevation: 2 }
                }}
                onClick={() => setMode(key)}
              >
                <Box display="flex" alignItems="center" sx={{ mb: 1 }}>
                  {config.icon}
                  <Typography variant="subtitle2" sx={{ ml: 1 }}>{config.label}</Typography>
                </Box>
                <Typography variant="body2" color="textSecondary">
                  {config.description}
                </Typography>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>

      <Divider sx={{ my: 3 }} />

      {/* Operation and Identifiers */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth size="small">
            <InputLabel>Operation Type</InputLabel>
            <Select 
              value={formData.operation} 
              onChange={(e) => handleInputChange('operation', e.target.value)}
              label="Operation Type"
            >
              {Object.entries(operations).map(([key, config]) => (
                <MenuItem key={key} value={key}>
                  <Box display="flex" alignItems="center">
                    {config.icon}
                    <Typography sx={{ ml: 1 }}>{config.label}</Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth size="small" label="Subscriber UID"
            value={formData.uid}
            onChange={(e) => handleInputChange('uid', e.target.value)}
            placeholder="e.g., SUB_12345"
          />
        </Grid>
        
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth size="small" label="IMSI"
            value={formData.imsi}
            onChange={(e) => handleInputChange('imsi', e.target.value)}
            placeholder="e.g., 404101234567890"
          />
        </Grid>
        
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth size="small" label="MSISDN"
            value={formData.msisdn}
            onChange={(e) => handleInputChange('msisdn', e.target.value)}
            placeholder="e.g., 919876543210"
          />
        </Grid>
      </Grid>

      {/* Service Configuration */}
      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle2" sx={{ mb: 2 }}>Service Configuration</Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <FormControl fullWidth size="small">
              <InputLabel>Subscriber Status</InputLabel>
              <Select 
                value={formData.status} 
                onChange={(e) => handleInputChange('status', e.target.value)}
                label="Subscriber Status"
              >
                <MenuItem value="ACTIVE">Active</MenuItem>
                <MenuItem value="SUSPENDED">Suspended</MenuItem>
                <MenuItem value="INACTIVE">Inactive</MenuItem>
                <MenuItem value="TERMINATED">Terminated</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormControl fullWidth size="small">
              <InputLabel>Service Plan</InputLabel>
              <Select 
                value={formData.plan} 
                onChange={(e) => handleInputChange('plan', e.target.value)}
                label="Service Plan"
              >
                <MenuItem value="2G">2G Basic</MenuItem>
                <MenuItem value="3G">3G Standard</MenuItem>
                <MenuItem value="4G">4G Premium</MenuItem>
                <MenuItem value="5G">5G Ultra</MenuItem>
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Box>

      {/* Service Features */}
      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle2" sx={{ mb: 2 }}>Service Features</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch 
                  checked={formData.callForwarding} 
                  onChange={(e) => handleInputChange('callForwarding', e.target.checked)}
                />
              }
              label="Call Forwarding"
            />
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch 
                  checked={formData.odbicActive} 
                  onChange={(e) => handleInputChange('odbicActive', e.target.checked)}
                />
              }
              label="ODBIC (Outgoing Barring)"
            />
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch 
                  checked={formData.odbocActive} 
                  onChange={(e) => handleInputChange('odbocActive', e.target.checked)}
                />
              }
              label="ODBOC (Outgoing Barring Override)"
            />
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch 
                  checked={formData.csService} 
                  onChange={(e) => handleInputChange('csService', e.target.checked)}
                />
              }
              label="CS Service (Circuit Switched)"
            />
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch 
                  checked={formData.fourGService} 
                  onChange={(e) => handleInputChange('fourGService', e.target.checked)}
                />
              }
              label="4G/LTE Service"
            />
          </Grid>
          
          <Grid item xs={12} md={6}>
            <FormControlLabel
              control={
                <Switch 
                  checked={formData.fiveGService} 
                  onChange={(e) => handleInputChange('fiveGService', e.target.checked)}
                />
              }
              label="5G Service"
            />
          </Grid>
        </Grid>
      </Box>

      {/* Submit Button */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="body2" color="textSecondary">
            Selected Mode: <strong>{modes[mode].label}</strong>
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Operation: <strong>{operations[formData.operation].label}</strong>
          </Typography>
        </Box>
        
        <Button 
          variant="contained" 
          size="large"
          color={operations[formData.operation].color}
          startIcon={submitting ? <CircularProgress size={20} color="inherit" /> : operations[formData.operation].icon}
          onClick={handleProvisionRequest}
          disabled={submitting}
        >
          {submitting ? 'Processing...' : `${operations[formData.operation].label} in ${modes[mode].label}`}
        </Button>
      </Box>
    </Card>
  );
};

// Provisioning History Component
const ProvisionHistory = ({ setMessage }) => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterMode, setFilterMode] = useState('ALL');
  const [filterOperation, setFilterOperation] = useState('ALL');

  // Mock provision history data
  useEffect(() => {
    const mockRequests = [
      {
        RequestId: 'prov-1729851234-abc123',
        operation: 'CREATE',
        mode: 'CLOUD',
        status: 'COMPLETED',
        uid: 'SUB_789012',
        msisdn: '919876543210',
        created: '2025-10-25T08:30:00Z',
        statusMessage: 'Provisioned successfully in Cloud'
      },
      {
        RequestId: 'prov-1729851100-def456',
        operation: 'UPDATE',
        mode: 'DUAL_PROV',
        status: 'COMPLETED',
        uid: 'SUB_345678',
        msisdn: '919123456789',
        created: '2025-10-25T08:25:00Z',
        statusMessage: 'Updated in both Legacy and Cloud'
      },
      {
        RequestId: 'prov-1729850900-ghi789',
        operation: 'SUSPEND',
        mode: 'LEGACY',
        status: 'FAILED',
        uid: 'SUB_901234',
        msisdn: '919555666777',
        created: '2025-10-25T08:20:00Z',
        statusMessage: 'Failed: Legacy system timeout'
      }
    ];
    
    setRequests(mockRequests);
  }, []);

  const getStatusIcon = (status) => {
    switch (status) {
      case 'COMPLETED': return <CheckCircle color="success" />;
      case 'FAILED': return <Error color="error" />;
      case 'PENDING': return <Info color="info" />;
      default: return <Warning color="warning" />;
    }
  };

  const filteredRequests = requests.filter(req => {
    if (filterMode !== 'ALL' && req.mode !== filterMode) return false;
    if (filterOperation !== 'ALL' && req.operation !== filterOperation) return false;
    return true;
  });

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
        <History sx={{ mr: 1 }} />
        Provision History
      </Typography>

      {/* Filters */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2 }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Mode</InputLabel>
          <Select value={filterMode} onChange={(e) => setFilterMode(e.target.value)} label="Mode">
            <MenuItem value="ALL">All Modes</MenuItem>
            <MenuItem value="LEGACY">Legacy</MenuItem>
            <MenuItem value="CLOUD">Cloud</MenuItem>
            <MenuItem value="DUAL_PROV">Dual Provision</MenuItem>
          </Select>
        </FormControl>
        
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Operation</InputLabel>
          <Select value={filterOperation} onChange={(e) => setFilterOperation(e.target.value)} label="Operation">
            <MenuItem value="ALL">All Operations</MenuItem>
            <MenuItem value="CREATE">Create</MenuItem>
            <MenuItem value="UPDATE">Update</MenuItem>
            <MenuItem value="SUSPEND">Suspend</MenuItem>
            <MenuItem value="ACTIVATE">Activate</MenuItem>
            <MenuItem value="DELETE">Delete</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { fontWeight: 'bold', backgroundColor: 'grey.50' } }}>
              <TableCell>Request ID</TableCell>
              <TableCell>Operation</TableCell>
              <TableCell>Mode</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Subscriber</TableCell>
              <TableCell>MSISDN</TableCell>
              <TableCell>Created</TableCell>
              <TableCell>Message</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <CircularProgress size={24} />
                </TableCell>
              </TableRow>
            ) : filteredRequests.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <Typography variant="body2" color="textSecondary">
                    No provision requests found for the selected filters.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              filteredRequests.map((request) => (
                <TableRow key={request.RequestId} hover>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {request.RequestId.substring(0, 8)}...
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={request.operation} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Chip label={request.mode} size="small" color="info" />
                  </TableCell>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      {getStatusIcon(request.status)}
                      <Chip 
                        label={request.status} 
                        size="small" 
                        color={request.status === 'COMPLETED' ? 'success' : request.status === 'FAILED' ? 'error' : 'default'}
                        sx={{ ml: 0.5 }}
                      />
                    </Box>
                  </TableCell>
                  <TableCell>{request.uid}</TableCell>
                  <TableCell>{request.msisdn}</TableCell>
                  <TableCell>
                    <Typography variant="caption">
                      {new Date(request.created).toLocaleString()}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="textSecondary">
                      {request.statusMessage}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

// Provisioning Dashboard
const ProvisionDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const response = await API.get('/provision/dashboard');
        setDashboardData(response.data.dashboard);
      } catch (error) {
        console.error('Dashboard load error:', error);
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();
  }, []);

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (!dashboardData) {
    return (
      <Alert severity="warning">
        Dashboard data not available. Please check backend connectivity.
      </Alert>
    );
  }

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 3 }}>Provisioning Dashboard</Typography>
      
      <Grid container spacing={3}>
        {/* Overview Stats */}
        <Grid item xs={12} md={6} lg={3}>
          <Card sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h4" color="primary">{dashboardData.totalProvisions}</Typography>
            <Typography variant="body2">Total Provisions</Typography>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h4" color="success.main">{dashboardData.todayProvisions}</Typography>
            <Typography variant="body2">Today's Provisions</Typography>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h4" color="info.main">{dashboardData.last24hSuccess}%</Typography>
            <Typography variant="body2">24h Success Rate</Typography>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="h4" color="warning.main">{dashboardData.avgResponseTime}</Typography>
            <Typography variant="body2">Avg Response Time</Typography>
          </Card>
        </Grid>

        {/* Mode Breakdown */}
        <Grid item xs={12} md={6}>
          <Card sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Mode Performance</Typography>
            {Object.entries(dashboardData.modeBreakdown).map(([mode, stats]) => (
              <Box key={mode} sx={{ mb: 1 }}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">{mode}</Typography>
                  <Typography variant="body2">{stats.count} ({stats.successRate}%)</Typography>
                </Box>
                <LinearProgress 
                  variant="determinate" 
                  value={stats.successRate} 
                  sx={{ height: 6, borderRadius: 3 }}
                />
              </Box>
            ))}
          </Card>
        </Grid>

        {/* Operation Breakdown */}
        <Grid item xs={12} md={6}>
          <Card sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Operations Summary</Typography>
            {Object.entries(dashboardData.operationBreakdown).map(([operation, count]) => (
              <Box key={operation} display="flex" justifyContent="space-between" sx={{ mb: 1 }}>
                <Typography variant="body2">{operation}</Typography>
                <Chip label={count} size="small" />
              </Box>
            ))}
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

// Main Provisioning Console
export default function ProvisioningConsole() {
  const [activeTab, setActiveTab] = useState(0);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [provisionMode, setProvisionMode] = useState('CLOUD');
  
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userRole = user.role || 'guest';

  const refreshHistory = () => {
    // Trigger history refresh
    setActiveTab(2); // Switch to history tab
    setTimeout(() => setActiveTab(1), 100); // Switch back
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
    setMessage({ type: '', text: '' });
  };

  return (
    <Paper sx={{ p: 3, my: 2 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
        <Settings sx={{ mr: 2, fontSize: 32 }} />
        Professional Provisioning Console
      </Typography>
      
      <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
        Comprehensive OSS/BSS subscriber provisioning with Legacy, Cloud, and Dual-mode support.
        Professional-grade operations with full audit trail and error handling.
      </Typography>

      {message.text && (
        <Alert 
          severity={message.type} 
          onClose={() => setMessage({ type: '', text: '' })} 
          sx={{ mb: 3 }}
        >
          {message.text}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange}>
          <Tab label="Single Provision" icon={<PersonAdd />} iconPosition="start" />
          <Tab label="Dashboard" icon={<Dashboard />} iconPosition="start" />
          <Tab label="History" icon={<History />} iconPosition="start" />
        </Tabs>
      </Box>

      {activeTab === 0 && (
        <SingleProvisionForm 
          mode={provisionMode}
          setMode={setProvisionMode}
          setMessage={setMessage}
          refreshHistory={refreshHistory}
        />
      )}
      
      {activeTab === 1 && <ProvisionDashboard />}
      {activeTab === 2 && <ProvisionHistory setMessage={setMessage} />}
    </Paper>
  );
}