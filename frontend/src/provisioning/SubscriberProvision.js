import React, { useState, useEffect } from 'react';
import {
  Paper, TextField, Button, Typography, Alert, Box, CircularProgress,
  Grid, Card, CardContent, CardHeader, List, ListItem, ListItemText, Divider,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton
} from '@mui/material';
import { Search, Add, Edit, Delete } from '@mui/icons-material';
import API from '../api.js';

// --- A Reusable Form for Adding/Editing Subscribers ---
const SubscriberForm = ({ open, onClose, subscriber, onSave }) => {
  const [formData, setFormData] = useState({});

  useEffect(() => {
    // When the dialog opens, populate the form with the subscriber's data if editing
    if (subscriber) {
      setFormData(subscriber);
    } else {
      // Reset to default values for a new subscriber
      setFormData({
        uid: '', imsi: '', msisdn: '', plan: 'Gold',
        subscription_state: 'ACTIVE', service_class: 'DEFAULT_SC',
        profile_type: 'DEFAULT_LTE_PROFILE', call_barring_all_outgoing: false,
        clip_provisioned: true, clir_provisioned: false,
        call_hold_provisioned: true, call_waiting_provisioned: true,
        ts11_provisioned: true, ts21_provisioned: true,
        ts22_provisioned: true, bs30_genr_provisioned: true,
        account_status: 'ACTIVE', language_id: 'en-US', sim_type: '4G_USIM'
      });
    }
  }, [subscriber, open]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleFormSave = () => {
    onSave(formData);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{subscriber ? 'Edit Subscriber' : 'Add New Subscriber'}</DialogTitle>
      <DialogContent>
        <Typography variant="subtitle2" sx={{ mt: 2 }}>Identifiers</Typography>
        <Grid container spacing={2} sx={{ mt: 1 }}>
          <Grid item xs={12} sm={4}><TextField name="uid" label="UID" value={formData.uid || ''} onChange={handleChange} fullWidth disabled={!!subscriber} required /></Grid>
          <Grid item xs={12} sm={4}><TextField name="imsi" label="IMSI" value={formData.imsi || ''} onChange={handleChange} fullWidth required /></Grid>
          <Grid item xs={12} sm={4}><TextField name="msisdn" label="MSISDN" value={formData.msisdn || ''} onChange={handleChange} fullWidth /></Grid>
        </Grid>
        <Typography variant="subtitle2" sx={{ mt: 3 }}>Subscription Details</Typography>
        <Grid container spacing={2} sx={{ mt: 1 }}>
          <Grid item xs={12} sm={4}><TextField name="plan" label="Plan" value={formData.plan || ''} onChange={handleChange} fullWidth /></Grid>
          <Grid item xs={12} sm={4}><TextField name="subscription_state" label="Subscription State" value={formData.subscription_state || ''} onChange={handleChange} fullWidth /></Grid>
          <Grid item xs={12} sm={4}><TextField name="service_class" label="Service Class" value={formData.service_class || ''} onChange={handleChange} fullWidth /></Grid>
          <Grid item xs={12} sm={4}><TextField name="profile_type" label="Profile Type" value={formData.profile_type || ''} onChange={handleChange} fullWidth /></Grid>
          <Grid item xs={12} sm={8}><TextField name="call_forward_unconditional" label="Call Forward Unconditional" value={formData.call_forward_unconditional || ''} onChange={handleChange} fullWidth /></Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleFormSave} variant="contained">Save</Button>
      </DialogActions>
    </Dialog>
  );
};


// This is the detailed view for a single subscriber
const SubscriberDetail = ({ subscriber, onEdit, onDelete }) => {
  if (!subscriber) return null;

  const renderBool = (value) => (value ? 'Yes' : 'No');

  return (
    <Box>
       <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mt: 3, mb: 2, pb: 1, borderBottom: '1px solid #eee' }}>
        <Typography variant="h6">Subscriber Profile</Typography>
        <Box>
            <Button variant="outlined" startIcon={<Edit />} onClick={() => onEdit(subscriber)} sx={{ mr: 1 }} disabled>Edit</Button>
            <Button variant="outlined" color="error" startIcon={<Delete />} onClick={() => onDelete(subscriber.uid)}>Delete</Button>
        </Box>
      </Box>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardHeader title="Basic & Subscription Info" />
            <CardContent>
              <List dense>
                <ListItem><ListItemText primary="UID" secondary={subscriber.uid || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="IMSI" secondary={subscriber.imsi || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="MSISDN" secondary={subscriber.msisdn || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Plan" secondary={subscriber.plan || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Subscription State" secondary={subscriber.subscription_state || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Service Class" secondary={subscriber.service_class || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Subscription ID" secondary={subscriber.subscription_id || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Profile Type" secondary={subscriber.profile_type || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Private User ID" secondary={subscriber.private_user_id || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="Public User ID" secondary={subscriber.public_user_id || 'N/A'} /></ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card elevation={2} sx={{ mb: 3 }}>
            <CardHeader title="HLR & Service Features" />
            <CardContent>
              <List dense>
                <ListItem><ListItemText primary="Call Forward Unconditional" secondary={subscriber.call_forward_unconditional || 'Not Set'} /></ListItem>
                <ListItem><ListItemText primary="Call Barring (Outgoing)" secondary={renderBool(subscriber.call_barring_all_outgoing)} /></ListItem>
                <ListItem><ListItemText primary="CLIP Provisioned" secondary={renderBool(subscriber.clip_provisioned)} /></ListItem>
                <ListItem><ListItemText primary="CLIR Provisioned" secondary={renderBool(subscriber.clir_provisioned)} /></ListItem>
                <ListItem><ListItemText primary="Call Hold" secondary={renderBool(subscriber.call_hold_provisioned)} /></ListItem>
                <ListItem><ListItemText primary="Call Waiting" secondary={renderBool(subscriber.call_waiting_provisioned)} /></ListItem>
                <ListItem><ListItemText primary="Language" secondary={subscriber.language_id || 'N/A'} /></ListItem>
                <ListItem><ListItemText primary="SIM Type" secondary={subscriber.sim_type || 'N/A'} /></ListItem>
              </List>
            </CardContent>
          </Card>
          <Card elevation={2}>
            <CardHeader title="PDP Contexts (APNs)" />
            <CardContent>
              <List dense>
                {subscriber.pdp_contexts && subscriber.pdp_contexts.length > 0 ? (
                  subscriber.pdp_contexts.map(pdp => (
                    <ListItem key={pdp.context_id}>
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


// This is the main component that orchestrates everything.
export default function SubscriberProvision() {
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
      setError('Please enter an identifier to search.');
      return;
    }
    setLoading(true);
    setError('');
    setMessage('');
    setSubscriber(null);

    try {
      const { data } = await API.get(`/provision/search?identifier=${searchIdentifier}`);
      setSubscriber(data);
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

  const handleSave = async (formData) => {
    setLoading(true);
    setError('');
    setMessage('');
    try {
      if (editingSubscriber) {
        // NOTE: A full update endpoint is complex and not yet implemented in the backend.
        // This is a placeholder for that future functionality.
        setMessage('Subscriber update functionality is not yet implemented.');
      } else {
        // Create new subscriber
        await API.post('/provision/subscriber', formData);
        setMessage('Subscriber created successfully!');
      }
      setIsFormOpen(false);
      // Refresh the data for the subscriber we just edited/created
      handleSearch(formData.uid); 
    } catch (err) {
      setError(err.response?.data?.msg || 'Save operation failed.');
    } finally {
      setLoading(false);
    }
  };
  
  const handleDelete = async (uid) => {
    if (window.confirm('Are you sure you want to delete this subscriber? This action cannot be undone.')) {
        setLoading(true);
        setError('');
        setMessage('');
        try {
            await API.delete(`/provision/subscriber/${uid}`);
            setMessage('Subscriber deleted successfully!');
            setSubscriber(null); // Clear the view
            setSearchTerm(''); // Clear the search bar
        } catch (err) {
            setError(err.response?.data?.msg || 'Delete operation failed.');
        } finally {
            setLoading(false);
        }
    }
  };

  const openAddForm = () => {
    setEditingSubscriber(null);
    setIsFormOpen(true);
  };
  
  const openEditForm = (sub) => {
    setEditingSubscriber(sub);
    //setIsFormOpen(true); // Disabled until PUT endpoint is fully implemented
  };

  return (
    <Paper sx={{ p: 3, backgroundColor: '#f9f9f9' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h5">Subscriber Provisioning</Typography>
            <Button variant="contained" startIcon={<Add />} onClick={openAddForm}>
                Add New Subscriber
            </Button>
        </Box>
      <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
        Search for a subscriber by UID, IMSI, or MSISDN to view, create, edit, or delete their profile.
      </Typography>

      <Box display="flex" alignItems="center" mb={2}>
        <TextField fullWidth label="Enter Identifier (UID, IMSI, or MSISDN)" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} variant="outlined" />
        <Button variant="contained" startIcon={<Search />} onClick={() => handleSearch()} disabled={loading} sx={{ ml: 2, py: '15px' }}>Search</Button>
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

