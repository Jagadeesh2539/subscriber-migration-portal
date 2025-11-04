import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  Alert,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  Divider,
  CircularProgress,
  Tooltip
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Search,
  Refresh,
  CloudSync,
  Storage,
  Settings,
  Visibility,
  Download,
  Upload
} from '@mui/icons-material';
import { api } from '../api/enhanced';

const ProvisioningModule = ({ user, onNotification, onStatsUpdate }) => {
  // State management
  const [currentTab, setCurrentTab] = useState(0);
  const [subscribers, setSubscribers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedSubscriber, setSelectedSubscriber] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [provisioningMode, setProvisioningMode] = useState('dual_prov');
  const [formData, setFormData] = useState({
    subscriber_id: '',
    name: '',
    email: '',
    phone: '',
    plan: 'basic',
    status: 'active',
    region: 'us-east-1'
  });
  const [filters, setFilters] = useState({
    status: 'all',
    plan: 'all',
    region: 'all'
  });

  // Provisioning modes
  const provisioningModes = [
    { value: 'legacy', label: 'Legacy Mode', description: 'Provision only in legacy system', color: '#f39c12' },
    { value: 'cloud', label: 'Cloud Mode', description: 'Provision only in cloud system', color: '#3498db' },
    { value: 'dual_prov', label: 'Dual Provisioning', description: 'Provision in both systems', color: '#27ae60' }
  ];

  // Available plans and regions
  const plans = ['basic', 'premium', 'enterprise'];
  const regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'];
  const statuses = ['active', 'inactive', 'suspended', 'pending'];

  // Load subscribers on component mount and when filters change
  useEffect(() => {
    loadSubscribers();
  }, [page, rowsPerPage, searchTerm, filters, provisioningMode]);

  // Load subscribers from API
  const loadSubscribers = async () => {
    try {
      setLoading(true);
      const params = {
        page: page + 1,
        limit: rowsPerPage,
        search: searchTerm,
        provisioning_mode: provisioningMode,
        ...filters
      };
      
      const response = await api.getSubscribers(params);
      setSubscribers(response.subscribers || []);
      setTotalCount(response.total || 0);
    } catch (error) {
      console.error('Error loading subscribers:', error);
      onNotification('Error loading subscribers: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Handle search
  const handleSearch = (event) => {
    setSearchTerm(event.target.value);
    setPage(0); // Reset to first page
  };

  // Handle filter changes
  const handleFilterChange = (field, value) => {
    setFilters(prev => ({ ...prev, [field]: value }));
    setPage(0);
  };

  // Open create/edit dialog
  const openDialog = (subscriber = null) => {
    if (subscriber) {
      setFormData({ ...subscriber });
      setSelectedSubscriber(subscriber);
    } else {
      setFormData({
        subscriber_id: '',
        name: '',
        email: '',
        phone: '',
        plan: 'basic',
        status: 'active',
        region: 'us-east-1'
      });
      setSelectedSubscriber(null);
    }
    setDialogOpen(true);
  };

  // Close dialog
  const closeDialog = () => {
    setDialogOpen(false);
    setSelectedSubscriber(null);
  };

  // Handle form input changes
  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Submit form (create/update subscriber)
  const handleSubmit = async () => {
    try {
      setLoading(true);
      const payload = { ...formData, provisioning_mode: provisioningMode };
      
      if (selectedSubscriber) {
        await api.updateSubscriber(selectedSubscriber.subscriber_id, payload);
        onNotification('Subscriber updated successfully', 'success');
      } else {
        await api.createSubscriber(payload);
        onNotification('Subscriber created successfully', 'success');
      }
      
      closeDialog();
      loadSubscribers();
      onStatsUpdate && onStatsUpdate();
    } catch (error) {
      console.error('Error saving subscriber:', error);
      onNotification('Error saving subscriber: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Delete subscriber
  const handleDelete = async (subscriberId) => {
    if (!window.confirm('Are you sure you want to delete this subscriber?')) {
      return;
    }
    
    try {
      setLoading(true);
      await api.deleteSubscriber(subscriberId, { provisioning_mode: provisioningMode });
      onNotification('Subscriber deleted successfully', 'success');
      loadSubscribers();
      onStatsUpdate && onStatsUpdate();
    } catch (error) {
      console.error('Error deleting subscriber:', error);
      onNotification('Error deleting subscriber: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Export subscribers
  const handleExport = async () => {
    try {
      setLoading(true);
      const response = await api.exportSubscribers({ 
        ...filters, 
        provisioning_mode: provisioningMode,
        search: searchTerm 
      });
      
      // Create and trigger download
      const blob = new Blob([response], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `subscribers_${provisioningMode}_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      
      onNotification('Subscribers exported successfully', 'success');
    } catch (error) {
      console.error('Error exporting subscribers:', error);
      onNotification('Error exporting subscribers: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Get status chip color
  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return 'success';
      case 'inactive': return 'default';
      case 'suspended': return 'error';
      case 'pending': return 'warning';
      default: return 'default';
    }
  };

  // Get plan chip color
  const getPlanColor = (plan) => {
    switch (plan) {
      case 'basic': return 'info';
      case 'premium': return 'secondary';
      case 'enterprise': return 'primary';
      default: return 'default';
    }
  };

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary' }}>
          Subscriber Provisioning
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Manage subscriber provisioning operations across legacy, cloud, and dual provisioning modes
        </Typography>

        {/* Provisioning Mode Selector */}
        <Card sx={{ mb: 3, p: 2, backgroundColor: 'background.paper' }}>
          <Typography variant="h6" gutterBottom sx={{ mb: 2, fontWeight: 500 }}>
            Provisioning Mode
          </Typography>
          <Grid container spacing={2}>
            {provisioningModes.map((mode) => (
              <Grid item xs={12} md={4} key={mode.value}>
                <Card 
                  sx={{ 
                    cursor: 'pointer',
                    border: provisioningMode === mode.value ? `2px solid ${mode.color}` : '2px solid transparent',
                    transition: 'all 0.2s',
                    '&:hover': {
                      boxShadow: 3,
                      transform: 'translateY(-2px)'
                    }
                  }}
                  onClick={() => setProvisioningMode(mode.value)}
                >
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <Box 
                        sx={{ 
                          width: 12, 
                          height: 12, 
                          borderRadius: '50%', 
                          backgroundColor: mode.color,
                          mr: 1
                        }} 
                      />
                      <Typography variant="h6" sx={{ fontWeight: 500 }}>
                        {mode.label}
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {mode.description}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Card>
      </Box>

      {/* Action Bar */}
      <Card sx={{ mb: 3, p: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              variant="outlined"
              placeholder="Search subscribers..."
              value={searchTerm}
              onChange={handleSearch}
              InputProps={{
                startAdornment: <Search sx={{ color: 'text.secondary', mr: 1 }} />
              }}
              size="small"
            />
          </Grid>
          <Grid item xs={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Status</InputLabel>
              <Select
                value={filters.status}
                label="Status"
                onChange={(e) => handleFilterChange('status', e.target.value)}
              >
                <MenuItem value="all">All Status</MenuItem>
                {statuses.map(status => (
                  <MenuItem key={status} value={status}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Plan</InputLabel>
              <Select
                value={filters.plan}
                label="Plan"
                onChange={(e) => handleFilterChange('plan', e.target.value)}
              >
                <MenuItem value="all">All Plans</MenuItem>
                {plans.map(plan => (
                  <MenuItem key={plan} value={plan}>
                    {plan.charAt(0).toUpperCase() + plan.slice(1)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={4}>
            <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
              <Button
                variant="outlined"
                startIcon={<Download />}
                onClick={handleExport}
                disabled={loading}
                size="small"
              >
                Export
              </Button>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={loadSubscribers}
                disabled={loading}
                size="small"
              >
                Refresh
              </Button>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={() => openDialog()}
                disabled={loading}
                size="small"
              >
                Add Subscriber
              </Button>
            </Box>
          </Grid>
        </Grid>
      </Card>

      {/* Subscribers Table */}
      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: 'grey.100' }}>
                <TableCell sx={{ fontWeight: 600 }}>ID</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Email</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Plan</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Region</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <CircularProgress size={40} />
                    <Typography variant="body2" sx={{ mt: 2 }}>Loading subscribers...</Typography>
                  </TableCell>
                </TableRow>
              ) : subscribers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <Typography variant="body1" color="text.secondary">
                      No subscribers found
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                subscribers.map((subscriber) => (
                  <TableRow key={subscriber.subscriber_id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {subscriber.subscriber_id}
                      </Typography>
                    </TableCell>
                    <TableCell>{subscriber.name}</TableCell>
                    <TableCell>{subscriber.email}</TableCell>
                    <TableCell>
                      <Chip 
                        label={subscriber.plan} 
                        color={getPlanColor(subscriber.plan)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={subscriber.status} 
                        color={getStatusColor(subscriber.status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{subscriber.region}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 0.5 }}>
                        <Tooltip title="View Details">
                          <IconButton size="small" color="primary">
                            <Visibility fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Edit Subscriber">
                          <IconButton 
                            size="small" 
                            color="primary"
                            onClick={() => openDialog(subscriber)}
                          >
                            <Edit fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete Subscriber">
                          <IconButton 
                            size="small" 
                            color="error"
                            onClick={() => handleDelete(subscriber.subscriber_id)}
                          >
                            <Delete fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
        
        <TablePagination
          component="div"
          count={totalCount}
          page={page}
          onPageChange={(event, newPage) => setPage(newPage)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(event) => {
            setRowsPerPage(parseInt(event.target.value, 10));
            setPage(0);
          }}
          rowsPerPageOptions={[5, 10, 25, 50]}
        />
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedSubscriber ? 'Edit Subscriber' : 'Create Subscriber'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Subscriber ID"
                value={formData.subscriber_id}
                onChange={(e) => handleInputChange('subscriber_id', e.target.value)}
                disabled={!!selectedSubscriber}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Name"
                value={formData.name}
                onChange={(e) => handleInputChange('name', e.target.value)}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Email"
                type="email"
                value={formData.email}
                onChange={(e) => handleInputChange('email', e.target.value)}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Phone"
                value={formData.phone}
                onChange={(e) => handleInputChange('phone', e.target.value)}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Plan</InputLabel>
                <Select
                  value={formData.plan}
                  label="Plan"
                  onChange={(e) => handleInputChange('plan', e.target.value)}
                >
                  {plans.map(plan => (
                    <MenuItem key={plan} value={plan}>
                      {plan.charAt(0).toUpperCase() + plan.slice(1)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={formData.status}
                  label="Status"
                  onChange={(e) => handleInputChange('status', e.target.value)}
                >
                  {statuses.map(status => (
                    <MenuItem key={status} value={status}>
                      {status.charAt(0).toUpperCase() + status.slice(1)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>Region</InputLabel>
                <Select
                  value={formData.region}
                  label="Region"
                  onChange={(e) => handleInputChange('region', e.target.value)}
                >
                  {regions.map(region => (
                    <MenuItem key={region} value={region}>
                      {region}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <Alert severity="info" sx={{ mt: 2 }}>
                <strong>Current Mode: {provisioningModes.find(m => m.value === provisioningMode)?.label}</strong><br />
                {provisioningModes.find(m => m.value === provisioningMode)?.description}
              </Alert>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button 
            onClick={handleSubmit} 
            variant="contained" 
            disabled={loading || !formData.subscriber_id || !formData.name || !formData.email}
          >
            {loading ? <CircularProgress size={20} /> : (selectedSubscriber ? 'Update' : 'Create')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ProvisioningModule;