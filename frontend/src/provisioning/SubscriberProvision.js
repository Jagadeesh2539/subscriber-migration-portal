import React, { useState, useEffect } from 'react';
import {
  Paper, TextField, Button, Typography, Alert, Box, CircularProgress,
  Grid, Card, CardContent, CardHeader, List, ListItem, ListItemText, Divider,
  Dialog, DialogTitle, DialogContent, DialogActions, FormControl, InputLabel, Select, MenuItem, Checkbox, FormControlLabel
} from '@mui/material';
import { Search, Add, Edit, Delete, Dashboard as DashboardIcon, Send } from '@mui/icons-material';
import API from '../api';

// --- I. Reusable Form Component (Used for Create and Modify) ---
const SubscriberForm = ({ open, onClose, subscriber, onSave, isEditing = false }) => {
  // Use a unique key to force re-render when switching between create/edit
  const [formData, setFormData] = useState({});
  const [formKey, setFormKey] = useState(0);

  useEffect(() => {
    // Define a full default state for creation
    const defaultData = {
      uid: '', imsi: '', msisdn: '', plan: 'Gold',
      subscription_state: 'ACTIVE', service_class: 'DEFAULT_SC',
      profile_type: 'DEFAULT_LTE_PROFILE', call_barring_all_outgoing: false,
      clip_provisioned: true, clir_provisioned: false,
      call_hold_provisioned: true, call_waiting_provisioned: true,
      account_status: 'ACTIVE', language_id: 'en-US', sim_type: '4G_USIM',
      call_forward_unconditional: ''
    };

    if (subscriber && isEditing) {
      // For editing, use existing data (must normalize subscriberId back to uid for forms)
      const dataToEdit = { ...subscriber, uid: subscriber.uid || subscriber.subscriberId };
      setFormData(dataToEdit);
    } else {
      // For creation, use defaults
      setFormData(defaultData);
    }
    setFormKey(prev => prev + 1); // Increment key to force form reset
  }, [subscriber, open, isEditing]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleFormSave = () => {
    onSave(formData);
  };

  const requiredFields = ['uid', 'imsi', 'plan', 'subscription_state'];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth key={formKey}>
      <DialogTitle>{isEditing ? `Modify Subscriber: ${formData.uid}` : 'Create New Subscriber'}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
          {isEditing ? 'Modify the selected parameters and save.' : 'Enter all required data to provision a new subscriber.'}
        </Typography>

        <Grid container spacing={3}>
          {/* IDENTIFIERS SECTION */}
          <Grid item xs={12}>
            <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>Identifiers</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <TextField name="uid" label="UID" value={formData.uid || ''} onChange={handleChange} fullWidth disabled={isEditing} required error={!isEditing && !formData.uid} helperText={!isEditing && !formData.uid ? 'Required' : ''} />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField name="imsi" label="IMSI" value={formData.imsi || ''} onChange={handleChange} fullWidth required error={!formData.imsi} helperText={!formData.imsi ? 'Required' : ''} />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField name="msisdn" label="MSISDN" value={formData.msisdn || ''} onChange={handleChange} fullWidth />
              </Grid>
            </Grid>
          </Grid>
          
          {/* SUBSCRIPTION & STATUS SECTION */}
          <Grid item xs={12}>
            <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>Subscription & Status</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <TextField name="plan" label="Plan" value={formData.plan || ''} onChange={handleChange} fullWidth required />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField name="service_class" label="Service Class" value={formData.service_class || ''} onChange={handleChange} fullWidth />
              </Grid>
              <Grid item xs={12} sm={4}>
                <FormControl fullWidth>
                  <InputLabel>Subscription State *</InputLabel>
                  <Select name="subscription_state" label="Subscription State *" value={formData.subscription_state || ''} onChange={handleChange} required>
                    <MenuItem value="ACTIVE">ACTIVE</MenuItem>
                    <MenuItem value="PENDING">PENDING</MenuItem>
                    <MenuItem value="SUSPENDED">SUSPENDED</MenuItem>
                    <MenuItem value="TERMINATED">TERMINATED</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField name="profile_type" label="Profile Type" value={formData.profile_type || ''} onChange={handleChange} fullWidth />
              </Grid>
              <Grid item xs={12} sm={4}>
                <FormControl fullWidth>
                  <InputLabel>Account Status</InputLabel>
                  <Select name="account_status" label="Account Status" value={formData.account_status || ''} onChange={handleChange}>
                    <MenuItem value="ACTIVE">ACTIVE</MenuItem>
                    <MenuItem value="INACTIVE">INACTIVE</MenuItem>
                    <MenuItem value="BLOCKED">BLOCKED</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField name="language_id" label="Language ID" value={formData.language_id || ''} onChange={handleChange} fullWidth />
              </Grid>
            </Grid>
          </Grid>

          {/* HLR FEATURES SECTION */}
          <Grid item xs={12}>
            <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>HLR Features</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <FormControlLabel control={<Checkbox name="clip_provisioned" checked={formData.clip_provisioned || false} onChange={handleChange} />} label="CLIP Provisioned" />
              </Grid>
              <Grid item xs={12} sm={4}>
                <FormControlLabel control={<Checkbox name="clir_provisioned" checked={formData.clir_provisioned || false} onChange={handleChange} />} label="CLIR Provisioned" />
              </Grid>
              <Grid item xs={12} sm={4}>
                <FormControlLabel control={<Checkbox name="call_hold_provisioned" checked={formData.call_hold_provisioned || false} onChange={handleChange} />} label="Call Hold" />
              </Grid>
              <Grid item xs={12} sm={4}>
                <FormControlLabel control={<Checkbox name="call_waiting_provisioned" checked={formData.call_waiting_provisioned || false} onChange={handleChange} />} label="Call Waiting" />
              </Grid>
              <Grid item xs={12} sm={4}>
                <FormControlLabel control={<Checkbox name="call_barring_all_outgoing" checked={formData.call_barring_all_outgoing || false} onChange={handleChange} />} label="Call Barring (Outgoing)" />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField name="call_forward_unconditional" label="Call Forward Unconditional" value={formData.call_forward_unconditional || ''} onChange={handleChange} fullWidth />
              </Grid>
            </Grid>
          </Grid>

        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleFormSave} variant="contained" startIcon={<Send />} disabled={!formData.uid || !formData.imsi}>
          {isEditing ? 'Save Changes' : 'Create Subscriber'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

// --- II. A Detailed View Component for a Single Subscriber ---
const SubscriberDetail = ({ subscriber, onEdit, onDelete }) => {
  if (!subscriber) return null;

  const renderBool = (value) => (value ? 'Yes' : 'No');
  const subscriberId = subscriber.uid || subscriber.subscriberId;

  return (
    <Card variant="outlined" sx={{ mt: 3, boxShadow: 3 }}>
      <CardHeader 
        title={`Subscriber Profile: ${subscriberId}`} 
        subheader={`Source: ${subscriber.source || 'Cloud/Legacy Mix'} | Status: ${subscriber.subscription_state || 'N/A'}`}
        action={
          <Box>
            <Button variant="outlined" startIcon={<Edit />} onClick={() => onEdit(subscriber)} sx={{ mr: 1 }}>Modify</Button>
            <Button variant="outlined" color="error" startIcon={<Delete />} onClick={() => onDelete(subscriberId)}>Delete</Button>
          </Box>
        }
        sx={{ borderBottom: '1px solid #eee' }}
      />
      <CardContent>
        <Grid container spacing={3}>
          
          {/* Basic Info Column */}
          <Grid item xs={12} md={6}>
            <Typography variant="h6" sx={{ mb: 1, color: 'primary.main' }}>Basic & Identifiers</Typography>
            <List dense sx={{ '& .MuiListItemText-primary': { fontWeight: 'bold' } }}>
              <ListItem><ListItemText primary="UID" secondary={subscriberId || 'N/A'} /></ListItem>
              <ListItem><ListItemText primary="IMSI" secondary={subscriber.imsi || 'N/A'} /></ListItem>
              <ListItem><ListItemText primary="MSISDN" secondary={subscriber.msisdn || 'N/A'} /></ListItem>
              <Divider component="li" />
              <ListItem><ListItemText primary="Plan" secondary={subscriber.plan || 'N/A'} /></ListItem>
              <ListItem><ListItemText primary="Service Class" secondary={subscriber.service_class || 'N/A'} /></ListItem>
              <ListItem><ListItemText primary="Profile Type" secondary={subscriber.profile_type || 'N/A'} /></ListItem>
            </List>
          </Grid>
          
          {/* HLR Features Column */}
          <Grid item xs={12} md={6}>
            <Typography variant="h6" sx={{ mb: 1, color: 'primary.main' }}>HLR & Service Features</Typography>
            <List dense sx={{ '& .MuiListItemText-primary': { fontWeight: 'bold' } }}>
              <ListItem><ListItemText primary="Call Forward Unconditional" secondary={subscriber.call_forward_unconditional || 'Not Set'} /></ListItem>
              <ListItem><ListItemText primary="Call Barring (Outgoing)" secondary={renderBool(subscriber.call_barring_all_outgoing)} /></ListItem>
              <ListItem><ListItemText primary="CLIP Provisioned" secondary={renderBool(subscriber.clip_provisioned)} /></ListItem>
              <ListItem><ListItemText primary="CLIR Provisioned" secondary={renderBool(subscriber.clir_provisioned)} /></ListItem>
              <ListItem><ListItemText primary="Call Hold" secondary={renderBool(subscriber.call_hold_provisioned)} /></ListItem>
              <ListItem><ListItemText primary="Call Waiting" secondary={renderBool(subscriber.call_waiting_provisioned)} /></ListItem>
              <Divider component="li" />
              <ListItem><ListItemText primary="Language" secondary={subscriber.language_id || 'N/A'} /></ListItem>
              <ListItem><ListItemText primary="Account Status" secondary={subscriber.account_status || 'N/A'} /></ListItem>
            </List>
          </Grid>
        </Grid>
        
        {/* Audit/Metadata Row */}
        <Box sx={{ mt: 3, pt: 2, borderTop: '1px dashed #eee' }}>
            <Typography variant="caption" color="textSecondary">
                Provisioned By: {subscriber.created_by || 'Unknown'} | 
                Created At: {subscriber.created_at ? new Date(subscriber.created_at).toLocaleString() : 'N/A'}
            </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

// --- III. Search/Modify/Delete View ---
const SubscriberSearch = ({ setAppState }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [subscriber, setSubscriber] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isFormOpen, setIsFormOpen] = useState(false);

  const handleSearch = async () => {
    const searchIdentifier = searchTerm.trim();
    if (!searchIdentifier) {
      setError('Please enter a UID, IMSI, or MSISDN to search.');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    setSubscriber(null);

    try {
      const { data } = await API.get(`/provision/search?identifier=${searchIdentifier}`);
      setSubscriber({ ...data, source: data.subscriberId ? 'Cloud' : 'Legacy' });
      setMessage(`Subscriber found. Source: ${data.subscriberId ? 'Cloud' : 'Legacy'}`);
    } catch (err) {
      if (err.response?.status === 404) {
        setError('Subscriber not found in cloud or legacy database.');
      } else {
        setError(err.response?.data?.msg || 'An error occurred during search.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleUpdate = async (formData) => {
    setLoading(true);
    setError('');
    setMessage('');
    setIsFormOpen(false); // Close the form immediately

    try {
      const uid = formData.uid || formData.subscriberId;
      await API.put(`/provision/subscriber/${uid}`, formData);
      setMessage(`Subscriber ${uid} updated successfully!`);
      // Refresh the detailed view
      handleSearch(); 
    } catch (err) {
      setError(err.response?.data?.msg || 'Update operation failed.');
    } finally {
      setLoading(false);
    }
  };
  
  const openEditForm = (sub) => {
    setSubscriber(sub); // Ensure the latest data is in state before opening form
    setIsFormOpen(true);
  };
  
  const handleInitiateDelete = (uid) => {
    // Navigate to the dedicated delete view, passing the UID
    setAppState({ view: 'Delete', initialSearchTerm: uid });
  };

  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6 }}>
        <Typography variant="h4" gutterBottom sx={{ mb: 2 }}>Search / Modify Subscriber</Typography>
        <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
          Enter subscriber identifier (UID, IMSI, or MSISDN) to retrieve profile for display or modification.
        </Typography>

        <Box display="flex" alignItems="center" mb={4}>
          <TextField 
            fullWidth 
            label="Search Identifier (UID, IMSI, or MSISDN)" 
            value={searchTerm} 
            onChange={e => setSearchTerm(e.target.value)} 
            variant="outlined" 
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          />
          <Button variant="contained" startIcon={<Search />} onClick={handleSearch} disabled={loading || !searchTerm} sx={{ ml: 2, py: '15px' }}>
            Search
          </Button>
        </Box>

        {loading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}><CircularProgress /></Box>}
        {error && <Alert severity="error" onClose={() => setError('')} sx={{ my: 2 }}>{error}</Alert>}
        {message && <Alert severity="success" onClose={() => setMessage('')} sx={{ my: 2 }}>{message}</Alert>}
        
        {subscriber && <SubscriberDetail subscriber={subscriber} onEdit={openEditForm} onDelete={handleInitiateDelete} />}

        {/* Modify Form Dialog (Only opens when searching finds a subscriber) */}
        <SubscriberForm 
          open={isFormOpen}
          onClose={() => setIsFormOpen(false)}
          subscriber={subscriber}
          onSave={handleUpdate}
          isEditing={true}
        />
    </Paper>
  );
};

// --- IV. Dedicated Create View ---
const SubscriberCreate = ({ setAppState }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isFormOpen, setIsFormOpen] = useState(true); // Always open the form in this view

  const handleCreate = async (formData) => {
    setLoading(true);
    setError('');
    setMessage('');
    
    try {
      const { data } = await API.post('/provision/subscriber', formData);
      setMessage(`Subscriber ${data.uid} created successfully! Redirecting to search view...`);
      setTimeout(() => {
        // Redirect to search view with the new UID for immediate display
        setAppState({ view: 'SearchModify', initialSearchTerm: data.uid });
      }, 1500); 
    } catch (err) {
      // Handles the specific backend validation error format
      const errMsg = err.response?.data?.msg || 'Creation failed due to an unknown error.';
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6 }}>
      <Typography variant="h4" gutterBottom>Create New Subscriber</Typography>
      <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
        Enter a complete profile. All identifiers (UID, IMSI, MSISDN) must be unique across all databases.
      </Typography>
      
      {loading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}><CircularProgress /></Box>}
      {error && <Alert severity="error" onClose={() => setError('')} sx={{ my: 2 }}>{error}</Alert>}
      {message && <Alert severity="success" onClose={() => setMessage('')} sx={{ my: 2 }}>{message}</Alert>}

      {/* The form logic is reused but always set to creation mode */}
      <SubscriberForm 
        open={isFormOpen} 
        onClose={() => setIsFormOpen(false)} // Should ideally be disabled in this view
        subscriber={null} // No existing subscriber for creation
        onSave={handleCreate}
        isEditing={false}
      />
    </Paper>
  );
};


// --- V. Dedicated Delete View ---
const SubscriberDelete = ({ setAppState, initialSearchTerm }) => {
  const [searchTerm, setSearchTerm] = useState(initialSearchTerm || '');
  const [subscriber, setSubscriber] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  
  useEffect(() => {
      if (initialSearchTerm) {
          handleSearch(initialSearchTerm);
      }
  }, [initialSearchTerm]);

  const handleSearch = async (term = searchTerm) => {
    const searchIdentifier = term.trim();
    if (!searchIdentifier) {
      setError('Please enter an identifier to proceed with deletion.');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    setSubscriber(null);

    try {
      const { data } = await API.get(`/provision/search?identifier=${searchIdentifier}`);
      setSubscriber({ ...data, source: data.subscriberId ? 'Cloud' : 'Legacy' });
      setMessage(`Subscriber profile found for deletion confirmation.`);
    } catch (err) {
      if (err.response?.status === 404) {
        setError('Subscriber not found. Cannot delete.');
      } else {
        setError(err.response?.data?.msg || 'An error occurred during search.');
      }
    } finally {
      setLoading(false);
    }
  };
  
  const handleDelete = async (uid) => {
    if (window.confirm(`WARNING: Are you sure you want to PERMANENTLY delete subscriber ${uid}? This action is irreversible across both Cloud and Legacy databases.`)) {
        setLoading(true);
        setError('');
        setMessage('');
        try {
            await API.delete(`/provision/subscriber/${uid}`);
            setMessage(`Subscriber ${uid} permanently deleted successfully!`);
            setSubscriber(null); 
            setSearchTerm(''); 
        } catch (err) {
            setError(err.response?.data?.msg || 'Delete operation failed.');
        } finally {
            setLoading(false);
        }
    }
  };

  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6, borderColor: 'error.main', border: '1px solid' }}>
        <Typography variant="h4" gutterBottom sx={{ mb: 2, color: 'error.main' }}><Delete sx={{ mr: 1 }} /> Delete Subscriber Profile</Typography>
        <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
          This operation performs a permanent deletion across all provisioning systems (Cloud & Legacy).
        </Typography>

        <Box display="flex" alignItems="center" mb={4}>
          <TextField 
            fullWidth 
            label="Identifier to Delete (UID, IMSI, or MSISDN)" 
            value={searchTerm} 
            onChange={e => setSearchTerm(e.target.value)} 
            variant="outlined" 
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          />
          <Button variant="contained" color="warning" startIcon={<Search />} onClick={() => handleSearch()} disabled={loading || !searchTerm} sx={{ ml: 2, py: '15px' }}>
            Find Profile
          </Button>
        </Box>

        {loading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}><CircularProgress /></Box>}
        {error && <Alert severity="error" onClose={() => setError('')} sx={{ my: 2 }}>{error}</Alert>}
        {message && <Alert severity="success" onClose={() => setMessage('')} sx={{ my: 2 }}>{message}</Alert>}
        
        {subscriber && (
            <Card sx={{ mt: 3, p: 3, bgcolor: 'warning.light' }}>
                <Typography variant="h6" color="warning.dark">Profile Found - Confirm Deletion</Typography>
                <Divider sx={{ my: 1 }} />
                <Typography variant="body1" sx={{ mt: 1 }}>**UID:** {subscriber.uid || subscriber.subscriberId}</Typography>
                <Typography variant="body1">**IMSI:** {subscriber.imsi}</Typography>
                <Typography variant="body1">**Source:** {subscriber.source}</Typography>
                <Typography variant="body2" color="error" sx={{ mt: 2 }}>
                    Press the button below to permanently erase this profile.
                </Typography>
                <Button 
                    variant="contained" 
                    color="error" 
                    startIcon={<Delete />} 
                    onClick={() => handleDelete(subscriber.uid || subscriber.subscriberId)} 
                    sx={{ mt: 2 }}
                >
                    Confirm Permanent Delete
                </Button>
            </Card>
        )}
    </Paper>
  );
};


// --- VI. Dashboard View ---
const ProvisioningDashboard = () => {
  const [totalSubscribers, setTotalSubscribers] = useState(0);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const fetchCount = async () => {
      try {
        const { data } = await API.get('/provision/count');
        setTotalSubscribers(data.count);
      } catch (e) {
        console.error("Failed to fetch subscriber count:", e);
        setTotalSubscribers('N/A');
      } finally {
        setLoading(false);
      }
    };
    fetchCount();
  }, []);
  
  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6 }}>
        <Typography variant="h4" gutterBottom sx={{ borderBottom: '1px solid #ddd', pb: 1 }}>
            <DashboardIcon sx={{ mr: 1, color: 'primary.main' }} /> Provisioning Dashboard
        </Typography>
        
        <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item xs={12} md={4}>
                <Card sx={{ bgcolor: 'primary.light', color: '#fff', textAlign: 'center', p: 3 }}>
                    <Typography variant="h6">Total Subscribers (Cloud DB)</Typography>
                    {loading ? (
                        <CircularProgress color="inherit" sx={{ mt: 1 }} />
                    ) : (
                        <Typography variant="h3" sx={{ mt: 1 }}>
                            {totalSubscribers.toLocaleString()}
                        </Typography>
                    )}
                </Card>
            </Grid>
             <Grid item xs={12} md={4}>
                <Card sx={{ bgcolor: 'success.light', color: '#fff', textAlign: 'center', p: 3 }}>
                    <Typography variant="h6">Dual Provisioning Status</Typography>
                    <Typography variant="h3" sx={{ mt: 1 }}>{MODE === 'cloud' ? 'Cloud Only' : 'Active'}</Typography>
                </Card>
            </Grid>
            <Grid item xs={12} md={4}>
                <Card sx={{ bgcolor: 'secondary.light', color: '#fff', textAlign: 'center', p: 3 }}>
                    <Typography variant="h6">Today's Provisions (Mock)</Typography>
                    <Typography variant="h3" sx={{ mt: 1 }}>{Math.floor(Math.random() * 50) + 10}</Typography>
                </Card>
            </Grid>
        </Grid>
        
        <Box sx={{ mt: 5 }}>
            <Typography variant="h5" sx={{ mb: 2 }}>System Overview</Typography>
            <Alert severity="info">
                This dashboard reflects data primarily from the high-performance Cloud (DynamoDB) system. 
                Legacy lookups occur only during search operations.
            </Alert>
        </Box>
    </Paper>
  );
};

// --- VII. Main Provisioning Router Component ---
export default function SubscriberProvision() {
  // Central state to manage which sub-view is active, and any state passed between them
  const [appState, setAppState] = useState({ 
    view: 'Dashboard', 
    initialSearchTerm: null 
  }); 

  // Function to render the correct component based on the current view
  const renderView = () => {
    switch (appState.view) {
      case 'Dashboard':
        return <ProvisioningDashboard />;
      case 'Create':
        return <SubscriberCreate setAppState={setAppState} />;
      case 'SearchModify':
        return <SubscriberSearch setAppState={setAppState} />;
      case 'Delete':
        return <SubscriberDelete setAppState={setAppState} initialSearchTerm={appState.initialSearchTerm} />;
      default:
        return <ProvisioningDashboard />;
    }
  };

  const navItems = [
    { label: 'Dashboard', icon: <DashboardIcon />, view: 'Dashboard' },
    { label: 'Create Subscriber', icon: <Add />, view: 'Create' },
    { label: 'Search / Modify', icon: <Search />, view: 'SearchModify' },
    { label: 'Delete Subscriber', icon: <Delete />, view: 'Delete', color: 'error.main' },
  ];

  return (
    <Box sx={{ display: 'flex', mt: 3, bgcolor: '#f5f5f5', minHeight: '80vh' }}>
      {/* Sidebar Navigation */}
      <Paper sx={{ width: 280, p: 2, mr: 3, boxShadow: 4 }}>
        <Typography variant="h6" sx={{ mb: 3, color: 'primary.dark' }}>Mobile Subscriber Admin</Typography>
        <List>
          {navItems.map((item) => (
            <ListItem 
              button 
              key={item.label} 
              onClick={() => setAppState({ view: item.view, initialSearchTerm: null })} 
              sx={{ 
                borderRadius: 1, 
                mb: 1,
                bgcolor: appState.view === item.view ? 'primary.main' : 'transparent',
                color: appState.view === item.view ? '#fff' : (item.color || 'text.primary'),
                '&:hover': { 
                    bgcolor: appState.view === item.view ? 'primary.dark' : 'primary.light',
                    color: appState.view === item.view ? '#fff' : '#fff',
                }
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', '& svg': { mr: 2, fontSize: '1.2rem' } }}>
                  {item.icon}
                  <ListItemText primary={item.label} />
              </Box>
            </ListItem>
          ))}
        </List>
      </Paper>
      
      {/* Content Area */}
      <Box sx={{ flexGrow: 1, p: 2 }}>
        {renderView()}
      </Box>
    </Box>
  );
}
