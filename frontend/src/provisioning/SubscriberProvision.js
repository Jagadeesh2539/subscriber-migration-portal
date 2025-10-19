import React, { useState, useEffect } from 'react';
import {
  Paper, TextField, Button, Typography, Alert, Box, CircularProgress,
  Grid, Card, CardContent, CardHeader, List, ListItem, ListItemText, 
  Dialog, DialogTitle, DialogContent, DialogActions, FormControlLabel, Checkbox, 
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow
} from '@mui/material';
import { Search, Add, Edit, Delete, Groups } from '@mui/icons-material';
import API from '../api';

// --- Sub-Component 1: Provisioning Dashboard (User-Friendly Overview) ---
const ProvisioningDashboard = () => {
    const [totalSubs, setTotalSubs] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchCount = async () => {
            try {
                // Calls the backend /provision/count endpoint
                const { data } = await API.get('/provision/count');
                setTotalSubs(data.total_subscribers);
            } catch (err) {
                setError('Failed to fetch total subscriber count from cloud.');
            } finally {
                setLoading(false);
            }
        };
        fetchCount();
    }, []);

    return (
        <Paper sx={{ p: 4, borderRadius: 2 }}>
            <Typography variant="h4" gutterBottom component="h1">Subscriber Provisioning Dashboard</Typography>
            <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
                Real-time snapshot of the cloud subscriber base and system health metrics.
            </Typography>

            <Grid container spacing={4}>
                {/* Total Subscribers Card */}
                <Grid item xs={12} sm={6} md={4}>
                    <Card sx={{ bgcolor: 'primary.main', color: 'white', borderRadius: 2, boxShadow: 6 }}>
                        <CardContent>
                            <Box display="flex" alignItems="center" justifyContent="space-between">
                                <Groups sx={{ fontSize: 50 }} />
                                <Box textAlign="right">
                                    <Typography variant="h3" sx={{ fontWeight: 700 }}>
                                        {loading ? <CircularProgress size={30} color="inherit" /> : totalSubs}
                                    </Typography>
                                    <Typography variant="h6">Total Cloud Subscribers</Typography>
                                </Box>
                            </Box>
                        </CardContent>
                    </Card>
                </Grid>

                {/* Placeholder for future health check metrics */}
                <Grid item xs={12} sm={6} md={4}>
                    <Card variant="outlined" sx={{ height: '100%', borderRadius: 2 }}>
                         <CardContent>
                            <Typography variant="h6" color="success.main">System Status</Typography>
                            <Typography variant="h5" sx={{ mt: 1 }}>All Systems Nominal</Typography>
                            <Typography variant="body2" color="textSecondary">Last check: {new Date().toLocaleTimeString()}</Typography>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>
             {error && <Alert severity="error" sx={{ mt: 3 }}>{error}</Alert>}
        </Paper>
    );
};

// --- Sub-Component 2: Subscriber Form (Centralized logic for Create and Modify) ---
const SubscriberForm = ({ open, onClose, subscriber, onSave }) => {
  const [formData, setFormData] = useState({});

  useEffect(() => {
    if (open) {
      // Set comprehensive defaults for consistency
      const defaults = {
        uid: '', imsi: '', msisdn: '', plan: 'Gold',
        subscription_state: 'ACTIVE', service_class: 'DEFAULT_SC',
        profile_type: 'DEFAULT_LTE_PROFILE', charging_characteristics: 'DEFAULT_CC',
        call_forward_unconditional: '', call_barring_all_outgoing: false,
        clip_provisioned: true, clir_provisioned: false,
        call_hold_provisioned: true, call_waiting_provisioned: true,
        account_status: 'ACTIVE', language_id: 'en-US', sim_type: '4G_USIM',
      };
      
      setFormData({ 
        ...defaults,
        ...(subscriber || {}), // Overwrite defaults with existing subscriber data if modifying
        // Ensure booleans are handled for checkboxes
        call_barring_all_outgoing: !!(subscriber?.call_barring_all_outgoing),
        clip_provisioned: !!(subscriber?.clip_provisioned),
        clir_provisioned: !!(subscriber?.clir_provisioned),
        call_hold_provisioned: !!(subscriber?.call_hold_provisioned),
        call_waiting_provisioned: !!(subscriber?.call_waiting_provisioned),
      });
    }
  }, [subscriber, open]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleFormSave = () => {
    // Basic validation
    if (!formData.uid || !formData.imsi) {
        alert("UID and IMSI are required fields.");
        return;
    }
    onSave(formData);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>{subscriber ? 'Modify Subscriber Profile' : 'Create New Subscriber Profile'}</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="error" sx={{ mb: 2 }}>
            Fields marked with * are mandatory. UID cannot be changed after creation.
        </Typography>
        <Grid container spacing={3} sx={{ mt: 1 }}>
          
          {/* Group 1: Core Identifiers */}
          <Grid item xs={12}><Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>Core Identifiers</Typography></Grid>
          <Grid item xs={12} sm={3}><TextField name="uid" label="UID *" value={formData.uid || ''} onChange={handleChange} fullWidth disabled={!!subscriber} required size="small" /></Grid>
          <Grid item xs={12} sm={3}><TextField name="imsi" label="IMSI *" value={formData.imsi || ''} onChange={handleChange} fullWidth required size="small" /></Grid>
          <Grid item xs={12} sm={3}><TextField name="msisdn" label="MSISDN" value={formData.msisdn || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          <Grid item xs={12} sm={3}><TextField name="plan" label="Plan" value={formData.plan || ''} onChange={handleChange} fullWidth size="small" /></Grid>

          {/* Group 2: Subscription State & Service */}
          <Grid item xs={12}><Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>Subscription & HSS Profile</Typography></Grid>
          <Grid item xs={12} sm={3}><TextField name="subscription_state" label="Subscription State" value={formData.subscription_state || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          <Grid item xs={12} sm={3}><TextField name="service_class" label="Service Class" value={formData.service_class || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          <Grid item xs={12} sm={3}><TextField name="profile_type" label="Profile Type (HSS)" value={formData.profile_type || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          <Grid item xs={12} sm={3}><TextField name="charging_characteristics" label="Charging Characteristics" value={formData.charging_characteristics || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          
          {/* Group 3: HLR Features */}
          <Grid item xs={12}><Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>HLR Features</Typography></Grid>
          <Grid item xs={12} sm={4}><TextField name="call_forward_unconditional" label="Call Forward Unconditional" value={formData.call_forward_unconditional || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          
          {/* Checkboxes for boolean features */}
          <Grid item xs={12} sm={2}>
              <FormControlLabel 
                control={<Checkbox name="call_barring_all_outgoing" checked={!!formData.call_barring_all_outgoing} onChange={handleChange} />} 
                label="Call Barring Out" 
              />
          </Grid>
          <Grid item xs={12} sm={2}>
              <FormControlLabel 
                control={<Checkbox name="clip_provisioned" checked={!!formData.clip_provisioned} onChange={handleChange} />} 
                label="CLIP" 
              />
          </Grid>
          <Grid item xs={12} sm={2}>
              <FormControlLabel 
                control={<Checkbox name="clir_provisioned" checked={!!formData.clir_provisioned} onChange={handleChange} />} 
                label="CLIR" 
              />
          </Grid>
          <Grid item xs={12} sm={2}>
              <FormControlLabel 
                control={<Checkbox name="call_hold_provisioned" checked={!!formData.call_hold_provisioned} onChange={handleChange} />} 
                label="Call Hold" 
              />
          </Grid>
          <Grid item xs={12} sm={2}>
              <FormControlLabel 
                control={<Checkbox name="call_waiting_provisioned" checked={!!formData.call_waiting_provisioned} onChange={handleChange} />} 
                label="Call Waiting" 
              />
          </Grid>

          {/* Group 4: VAS Services */}
          <Grid item xs={12}><Typography variant="subtitle1" sx={{ mt: 2, mb: 1, borderBottom: '1px solid #eee' }}>VAS Services</Typography></Grid>
          <Grid item xs={12} sm={4}><TextField name="account_status" label="Account Status" value={formData.account_status || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          <Grid item xs={12} sm={4}><TextField name="language_id" label="Language ID" value={formData.language_id || ''} onChange={handleChange} fullWidth size="small" /></Grid>
          <Grid item xs={12} sm={4}><TextField name="sim_type" label="SIM Type" value={formData.sim_type || ''} onChange={handleChange} fullWidth size="small" /></Grid>

        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleFormSave} variant="contained" color={subscriber ? 'warning' : 'primary'}>{subscriber ? 'Save Changes' : 'Create Subscriber'}</Button>
      </DialogActions>
    </Dialog>
  );
};


// --- Sub-Component 3: Subscriber Detail View (for Search/Modify/Delete) ---
const SubscriberDetail = ({ subscriber, onEdit, onDelete }) => {
  if (!subscriber) return null;

  const renderBool = (value) => (value ? 'Yes' : 'No');

  return (
    <Box sx={{ mt: 3, p: 3, border: '1px solid #e0e0e0', borderRadius: 2, bgcolor: '#f9f9f9' }}>
       <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 2, pb: 1, borderBottom: '2px solid #ccc' }}>
        <Typography variant="h5" color="primary.main">Subscriber Profile: {subscriber.uid}</Typography>
        <Box>
            <Button variant="contained" color="warning" startIcon={<Edit />} onClick={() => onEdit(subscriber)} sx={{ mr: 1 }}>Modify</Button>
            <Button variant="contained" color="error" startIcon={<Delete />} onClick={() => onDelete(subscriber.uid)}>Delete</Button>
        </Box>
      </Box>
      <Grid container spacing={4}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title="Core & Subscription Info" titleTypographyProps={{ variant: 'subtitle1' }} />
            <CardContent sx={{ pt: 0 }}>
              <TableContainer>
                <Table size="small">
                  <TableBody>
                    <TableRow><TableCell sx={{ fontWeight: 'bold', width: '40%' }}>UID / Sub ID</TableCell><TableCell>{subscriber.uid || 'N/A'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>IMSI</TableCell><TableCell>{subscriber.imsi || 'N/A'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>MSISDN</TableCell><TableCell>{subscriber.msisdn || 'N/A'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>Plan</TableCell><TableCell>{subscriber.plan || 'N/A'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>Subscription State</TableCell><TableCell>{subscriber.subscription_state || 'N/A'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>Profile Type</TableCell><TableCell>{subscriber.profile_type || 'N/A'}</TableCell></TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardHeader title="HLR & VAS Features" titleTypographyProps={{ variant: 'subtitle1' }} />
            <CardContent sx={{ pt: 0 }}>
              <TableContainer>
                <Table size="small">
                  <TableBody>
                    <TableRow><TableCell sx={{ fontWeight: 'bold', width: '40%' }}>Call Forward Unconditional</TableCell><TableCell>{subscriber.call_forward_unconditional || 'Not Set'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>Call Barring (Outgoing)</TableCell><TableCell>{renderBool(subscriber.call_barring_all_outgoing)}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>CLIP Provisioned</TableCell><TableCell>{renderBool(subscriber.clip_provisioned)}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>CLIR Provisioned</TableCell><TableCell>{renderBool(subscriber.clir_provisioned)}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>Account Status</TableCell><TableCell>{subscriber.account_status || 'N/A'}</TableCell></TableRow>
                    <TableRow><TableCell sx={{ fontWeight: 'bold' }}>SIM Type</TableCell><TableCell>{subscriber.sim_type || 'N/A'}</TableCell></TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12}>
            <Card variant="outlined">
                <CardHeader title="PDP Contexts (APNs)" titleTypographyProps={{ variant: 'subtitle1' }} />
                <CardContent sx={{ pt: 0 }}>
                    <List dense sx={{ maxHeight: 150, overflow: 'auto', border: '1px solid #eee' }}>
                    {Array.isArray(subscriber.pdp_contexts) && subscriber.pdp_contexts.length > 0 ? (
                        subscriber.pdp_contexts.map((pdp, index) => (
                        <ListItem key={index}>
                            <ListItemText 
                            primary={`APN: ${pdp.apn}`} 
                            secondary={`Context ID: ${pdp.context_id} | QoS: ${pdp.qos_profile}`} 
                            />
                        </ListItem>
                        ))
                    ) : (
                        <ListItem><ListItemText primary="No PDP contexts defined." /></ListItem>
                    )}
                    </List>
                </CardContent>
            </Card>
        </Grid>
      </Grid>
    </Box>
  );
};


// --- Sub-Component 4: Search/Modify/Delete View ---
const SubscriberSearch = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [subscriber, setSubscriber] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingSubscriber, setEditingSubscriber] = useState(null);

  const handleSearch = async (term = searchTerm) => {
    const searchIdentifier = term.trim();
    if (!searchIdentifier) {
      setError('Please enter an identifier to search (UID, IMSI, or MSISDN).');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    setSubscriber(null);

    try {
      const { data } = await API.get(`/provision/search?identifier=${searchIdentifier}`);
      setSubscriber(data);
      setMessage(`Subscriber ${data.uid} found. Profile loaded successfully.`);
    } catch (err) {
      if (err.response?.status === 404) {
        setError('Subscriber not found in cloud or legacy database. Use Create Profile to add a new entry.');
      } else {
        setError(err.response?.data?.msg || 'An error occurred during search.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (formData) => {
    setLoading(true);
    setError('');
    setMessage('');
    
    try {
      await API.put(`/provision/subscriber/${formData.uid}`, formData);
      setMessage('Modification Successful! The profile has been updated.');
      setIsFormOpen(false);
      // Refresh the view with the updated data
      handleSearch(formData.uid); 
    } catch (err) {
      setError(err.response?.data?.msg || 'Modification Failed: Check server logs.');
    } finally {
      setLoading(false);
    }
  };
  
  const handleDelete = async (uid) => {
    // Confirm dialog is handled inside the function
    if (window.confirm(`Are you sure you want to permanently delete subscriber ${uid}? This action cannot be undone.`)) {
        setLoading(true);
        setError('');
        setMessage('');
        try {
            await API.delete(`/provision/subscriber/${uid}`);
            setMessage('Deletion Successful! Subscriber profile has been removed.');
            setSubscriber(null); // Clear the detailed view
            setSearchTerm(''); // Clear the search bar
        } catch (err) {
            setError(err.response?.data?.msg || 'Deletion Failed: Check server logs.');
        } finally {
            setLoading(false);
        }
    }
  };
  
  const openEditForm = (sub) => {
    setEditingSubscriber(sub); 
    setIsFormOpen(true);
  };

  return (
    <Paper sx={{ p: 4, borderRadius: 2 }}>
        <Typography variant="h4" gutterBottom>Search, Modify, & Delete Profile</Typography>
        <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
            Use a **UID, IMSI, or MSISDN** to retrieve a profile. You can then **Modify** or **Delete** the record.
        </Typography>

        <Box display="flex" alignItems="center" mb={4}>
            <TextField 
                fullWidth 
                label="Enter Identifier (UID, IMSI, or MSISDN)" 
                value={searchTerm} 
                onChange={e => setSearchTerm(e.target.value)} 
                variant="outlined" 
                size="medium"
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
            <Button variant="contained" startIcon={<Search />} onClick={() => handleSearch()} disabled={loading} sx={{ ml: 2, py: '14px' }}>Search</Button>
        </Box>

        {loading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}><CircularProgress /></Box>}
        {error && <Alert severity="error" onClose={() => setError('')} sx={{ my: 2 }}>{error}</Alert>}
        {message && <Alert severity="success" onClose={() => setMessage('')} sx={{ my: 2 }}>{message}</Alert>}
        
        {subscriber && <SubscriberDetail subscriber={subscriber} onEdit={openEditForm} onDelete={handleDelete} />}

        <SubscriberForm 
            open={isFormOpen}
            onClose={() => setIsFormOpen(false)}
            subscriber={editingSubscriber}
            onSave={handleSave}
        />
    </Paper>
  );
}

// --- Sub-Component 5: Create Only View ---
const SubscriberCreate = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [isFormOpen, setIsFormOpen] = useState(true); // Always open the form here

    const handleSave = async (formData) => {
        setLoading(true);
        setError('');
        setMessage('');
        
        try {
            await API.post('/provision/subscriber', formData);
            setMessage(`Creation Successful! Subscriber ${formData.uid} provisioned. You can now use the search tool to verify.`);
            // Reset form for next entry
            setIsFormOpen(false);
            setTimeout(() => {
                setIsFormOpen(true);
            }, 500); 
        } catch (err) {
            setError(err.response?.data?.msg || 'Creation Failed: Check input fields and ensure UID is unique.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Paper sx={{ p: 4, borderRadius: 2 }}>
            <Typography variant="h4" gutterBottom>Create New Subscriber Profile</Typography>
            <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
                Fill in the comprehensive details below to provision a new subscriber profile across the target systems.
            </Typography>
            
            {loading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}><CircularProgress /></Box>}
            {error && <Alert severity="error" onClose={() => setError('')} sx={{ my: 2 }}>{error}</Alert>}
            {message && <Alert severity="success" onClose={() => setMessage('')} sx={{ my: 2 }}>{message}</Alert>}
            
            <SubscriberForm 
                open={isFormOpen}
                onClose={() => {setIsFormOpen(false);}} // User closes the form
                subscriber={null} // null means create mode
                onSave={handleSave}
            />
        </Paper>
    );
};


// --- Main Component Switcher (Router Target) ---
export default function SubscriberProvision({ view }) {
    switch (view) {
        case 'dashboard':
            return <ProvisioningDashboard />;
        case 'create':
            return <SubscriberCreate />;
        case 'search':
            return <SubscriberSearch />;
        default:
            return <Typography variant="h5" sx={{ p: 4 }}>Please select a provisioning action from the sidebar.</Typography>;
    }
}
