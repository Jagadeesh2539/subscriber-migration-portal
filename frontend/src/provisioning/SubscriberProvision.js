import React, { useState, useEffect, useCallback } from 'react';
import { 
  Paper, TextField, Button, Typography, Alert, Box, CircularProgress, 
  Grid, Card, CardContent, CardHeader, List, ListItem, ListItemText, 
  Dialog, DialogTitle, DialogContent, DialogActions, Tabs, Tab,
  Tooltip, Checkbox, FormControlLabel
} from '@mui/material';
import { 
  Search, Add, Edit, Delete, Dashboard, CheckCircleOutline, VpnKey, AccountCircle 
} from '@mui/icons-material';
import API from '../api';

// ---Default Data for Forms---

const DEFAULT_SUBSCRIBER = {
  uid: '', imsi: '', msisdn: '', plan: 'Gold',
  subscription_state: 'ACTIVE', service_class: 'DEFAULT_SC',
  profile_type: 'DEFAULT_LTE_PROFILE', call_barring_all_outgoing: false,
  clip_provisioned: true, clir_provisioned: false,
  call_hold_provisioned: true, call_waiting_provisioned: true,
  ts11_provisioned: true, ts21_provisioned: true,
  ts22_provisioned: true, bs30_genr_provisioned: true,
  account_status: 'ACTIVE', language_id: 'en-US', sim_type: '4G_USIM',
  call_forward_unconditional: '',
};
// --- Helper Components ---

// --- 1. Subscriber Form (Create/Modify) ---
const SubscriberForm = ({ formData, setFormData, isEditing }) => {
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({ 
      ...prev, 
      [name]: type === 'checkbox' ? checked : value,
      uid: isEditing ? formData.uid : (name === 'uid' ? value : prev.uid) 
    }));
  };

  const formFields = [
    { name: 'uid', label: 'UID (Primary Key)', required: true, disabled: isEditing, xs: 12, sm: 4, tooltip: 'Unique Identifier for the subscriber. Cannot be changed when editing.' },
    { name: 'imsi', label: 'IMSI (SIM ID)', required: true, disabled: false, xs: 12, sm: 4, tooltip: 'International Mobile Subscriber Identity.' },
    { name: 'msisdn', label: 'MSISDN (Phone Number)', required: false, disabled: false, xs: 12, sm: 4, tooltip: 'Phone Number. Must be unique if provided.' },
    
    { name: 'plan', label: 'Service Plan', required: false, xs: 12, sm: 4, tooltip: 'Service plan assigned to the subscriber.' },
    { name: 'subscription_state', label: 'Subscription State', required: false, xs: 12, sm: 4, tooltip: 'Current state of the subscription (e.g., ACTIVE, SUSPENDED).' },
    { name: 'service_class', label: 'Service Class', required: false, xs: 12, sm: 4, tooltip: 'The service profile or class.' },
    
    { name: 'profile_type', label: 'Profile Type', required: false, xs: 12, sm: 4 },
    { name: 'account_status', label: 'Account Status (VAS)', required: false, xs: 12, sm: 4 },
    { name: 'language_id', label: 'Language ID', required: false, xs: 12, sm: 4 },
    { name: 'sim_type', label: 'SIM Type', required: false, xs: 12, sm: 4 },

    // HLR Features (Booleans/Flags)
    { name: 'call_barring_all_outgoing', label: 'Call Barring (Outgoing)', type: 'checkbox', xs: 12, sm: 4, tooltip: 'Enable/Disable all outgoing calls.' },
    { name: 'clip_provisioned', label: 'CLIP Provisioned', type: 'checkbox', xs: 12, sm: 4, tooltip: 'Calling Line Identification Presentation.' },
    { name: 'clir_provisioned', label: 'CLIR Provisioned', type: 'checkbox', xs: 12, sm: 4, tooltip: 'Calling Line Identification Restriction.' },
    { name: 'call_hold_provisioned', label: 'Call Hold Provisioned', type: 'checkbox', xs: 12, sm: 4, tooltip: 'Enable/Disable Call Hold feature.' },
    { name: 'call_waiting_provisioned', label: 'Call Waiting Provisioned', type: 'checkbox', xs: 12, sm: 4, tooltip: 'Enable/Disable Call Waiting feature.' },
    { name: 'call_forward_unconditional', label: 'Call Forward Unconditional', required: false, xs: 12, sm: 8 },
  ];

  const renderField = (field) => {
    // Checkbox field rendering using FormControlLabel/Checkbox
    if (field.type === 'checkbox') {
      const isChecked = formData[field.name] === true || formData[field.name] === 'true';

      return (
        <Grid item xs={field.xs} sm={field.sm} key={field.name}>
          <Tooltip title={field.tooltip || field.label}>
            <FormControlLabel
              control={
                <Checkbox 
                  checked={isChecked} 
                  onChange={handleChange} 
                  name={field.name} 
                  size="small"
                />
              }
              label={<Typography variant="body2">{field.label}</Typography>}
            />
          </Tooltip>
        </Grid>
      );
    }

    // Standard TextField rendering with Tooltip
    return (
      <Grid item xs={field.xs} sm={field.sm} key={field.name}>
        <Tooltip title={field.tooltip || field.label}>
          <TextField 
            name={field.name} 
            label={field.label} 
            value={formData[field.name] || ''} 
            onChange={handleChange} 
            fullWidth 
            required={field.required} 
            disabled={field.disabled}
            variant="outlined"
            size="small"
          />
        </Tooltip>
      </Grid>
    );
  };

  return (
    <Grid container spacing={2}>
      {formFields.map(renderField)}
    </Grid>
  );
};


// --- 2. Subscriber Detail View (Used in Search/Modify) ---
const SubscriberDetail = ({ subscriber }) => {
  if (!subscriber) return null;

  const renderBool = (value) => (value ? 'Yes' : 'No');

  const mainFields = [
    { label: 'UID', key: 'uid' },
    { label: 'IMSI', key: 'imsi' },
    { label: 'MSISDN', key: 'msisdn' },
    { label: 'Plan', key: 'plan' },
    { label: 'Subscription State', key: 'subscription_state' },
    { label: 'Service Class', key: 'service_class' },
    { label: 'Profile Type', key: 'profile_type' },
  ];

  const hlrFields = [
    { label: 'Call Forward Unconditional', key: 'call_forward_unconditional' },
    { label: 'Call Barring (Outgoing)', key: 'call_barring_all_outgoing', render: renderBool },
    { label: 'CLIP Provisioned', key: 'clip_provisioned', render: renderBool },
    { label: 'CLIR Provisioned', key: 'clir_provisioned', render: renderBool },
    { label: 'Call Hold', key: 'call_hold_provisioned', render: renderBool },
    { label: 'Call Waiting', key: 'call_waiting_provisioned', render: renderBool },
  ];

  return (
    <Grid container spacing={3} sx={{ mt: 3 }}>
      <Grid item xs={12} md={6}>
        <Card variant="outlined">
          <CardHeader title="Core & Subscription Info" sx={{ bgcolor: '#f5f5f5' }} />
          <CardContent>
            <List dense disablePadding>
              {mainFields.map(f => (
                <ListItem key={f.key} divider>
                  <ListItemText 
                    primary={<strong>{f.label}</strong>} 
                    secondary={subscriber[f.key] || 'N/A'} 
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card variant="outlined">
          <CardHeader title="HLR & HSS Features" sx={{ bgcolor: '#f5f5f5' }} />
          <CardContent>
            <List dense disablePadding>
              {hlrFields.map(f => (
                <ListItem key={f.key} divider>
                  <ListItemText 
                    primary={<strong>{f.label}</strong>} 
                    secondary={f.render ? f.render(subscriber[f.key]) : (subscriber[f.key] || 'N/A')} 
                  />
                </ListItem>
              ))}
              <ListItem divider>
                <ListItemText primary={<strong>Source Database</strong>} secondary={subscriber.source || 'Cloud/DynamoDB'} />
              </ListItem>
            </List>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};


// --- 3. Delete Confirmation Modal ---
const DeleteConfirmModal = ({ open, onClose, subscriber, onConfirm }) => {
  if (!subscriber) return null;
  
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ bgcolor: '#f44336', color: 'white' }}>
        <Box display="flex" alignItems="center"><Delete sx={{ mr: 1 }} /> Confirm Deletion</Box>
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="h6" color="error" sx={{ mb: 2 }}>
          This action cannot be undone.
        </Typography>
        <Typography>
          Are you absolutely sure you want to delete the subscriber profile for:
        </Typography>
        <Box sx={{ mt: 2, p: 2, border: '1px solid #ccc', borderRadius: 1 }}>
          <Typography><strong>UID:</strong> {subscriber.uid}</Typography>
          <Typography><strong>IMSI:</strong> {subscriber.imsi}</Typography>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="outlined">Cancel</Button>
        <Button onClick={() => onConfirm(subscriber.uid)} color="error" variant="contained" startIcon={<Delete />}>
          Permanently Delete
        </Button>
      </DialogActions>
    </Dialog>
  );
};


// ----------------------------------------------------------------------------------
// --- MAIN VIEWS ---
// ----------------------------------------------------------------------------------

// --- View A: Dashboard ---
const ProvisioningDashboard = ({ totalSubs, todayProvisions, fetchCounts }) => {
  useEffect(() => {
    fetchCounts();
  }, [fetchCounts]);
  
  return (
    <Box>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
        <Dashboard sx={{ mr: 1 }} /> Provisioning Dashboard
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card sx={{ bgcolor: '#e3f2fd', borderLeft: '5px solid #2196f3', boxShadow: 3 }}>
            <CardContent>
              <Typography color="textSecondary" gutterBottom variant="h6">
                TOTAL SUBSCRIBERS (CLOUD)
              </Typography>
              <Typography variant="h3" sx={{ fontWeight: 'bold', color: '#1565c0' }}>
                {totalSubs.toLocaleString()}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ bgcolor: '#e8f5e9', borderLeft: '5px solid #4caf50', boxShadow: 3 }}>
            <CardContent>
              <Typography color="textSecondary" gutterBottom variant="h6">
                TODAY'S PROVISIONS
              </Typography>
              <Typography variant="h3" sx={{ fontWeight: 'bold', color: '#2e7d32' }}>
                {todayProvisions}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <Alert severity="info" sx={{ mt: 4 }}>
        Subscriber counts are fetched from the DynamoDB table. "Today's Provisions" is a client-side simulation updated on every successful Create/Delete operation.
      </Alert>
    </Box>
  );
};


// --- View B: Create Subscriber (Inline Form) ---
const SubscriberCreate = ({ totalSubs, setTotalSubs, fetchCounts }) => {
  const [formData, setFormData] = useState(DEFAULT_SUBSCRIBER);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage({ type: '', text: '' });
    setLoading(true);

    if (!formData.uid || !formData.imsi) {
      setMessage({ type: 'error', text: 'UID and IMSI are mandatory fields.' });
      setLoading(false);
      return;
    }

    try {
      const response = await API.post('/provision/subscriber', formData);
      
      setMessage({ type: 'success', text: response.data?.msg || 'Subscriber created successfully!' });
      
      setTotalSubs(prev => prev + 1);
      fetchCounts();

      setFormData(DEFAULT_SUBSCRIBER); 
      
    } catch (err) {
      const errorMsg = err.response?.data?.msg || 'An unknown error occurred during creation.';
      setMessage({ type: 'error', text: errorMsg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
        <Add sx={{ mr: 1 }} /> Create New Subscriber
      </Typography>
      
      <Card variant="outlined" sx={{ p: 3, boxShadow: 3 }}>
        <Typography variant="h6" sx={{ mb: 3, display: 'flex', alignItems: 'center', borderBottom: '1px solid #eee', pb: 1 }}>
          <AccountCircle sx={{ mr: 1 }} /> Subscriber Profile Data
        </Typography>
        
        {message.text && <Alert severity={message.type} sx={{ mb: 3 }} onClose={() => setMessage({ type: '', text: '' })}>{message.text}</Alert>}

        <form onSubmit={handleSubmit}>
          <SubscriberForm formData={formData} setFormData={setFormData} isEditing={false} />
          <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between' }}>
            <Button 
              type="button"
              variant="outlined"
              onClick={() => setFormData(DEFAULT_SUBSCRIBER)}
            >
              Reset Form
            </Button>
            <Button 
              type="submit" 
              variant="contained" 
              color="primary" 
              startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <CheckCircleOutline />}
              disabled={loading || !formData.uid || !formData.imsi}
            >
              {loading ? 'Creating...' : 'Create Subscriber'}
            </Button>
          </Box>
        </form>
      </Card>
    </Box>
  );
};


// --- Search Tabs Component ---
const SearchTabs = ({ searchTerm, setSearchTerm, handleSearch, loading, type, setSearchType }) => {
    const searchTabs = [
        { label: 'Search by UID', key: 'uid', placeholder: 'Enter UID' },
        { label: 'Search by IMSI', key: 'imsi', placeholder: 'Enter IMSI' },
        { label: 'Search by MSISDN', key: 'msisdn', placeholder: 'Enter MSISDN' },
    ];
    
    // Find the currently active tab index based on the search type prop
    const activeTab = searchTabs.findIndex(t => t.key === type);

    const handleTabChange = (event, newValue) => {
        // Update the searchType in the parent component based on the tab clicked
        setSearchType(searchTabs[newValue].key);
        setSearchTerm('');
    };
    
    const currentTab = searchTabs[activeTab];

    return (
        <Card variant="outlined" sx={{ p: 3, mb: 3, bgcolor: '#f0f4f8' }}>
            <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
                <VpnKey sx={{ mr: 1, color: 'primary.main' }} /> Search By Identifier
            </Typography>

            <Tabs 
                value={activeTab} 
                onChange={handleTabChange} 
                variant="scrollable" 
                scrollButtons="auto" 
                sx={{ mb: 2 }}
            >
                {searchTabs.map((tab, index) => (
                    <Tab key={tab.key} label={tab.label} />
                ))}
            </Tabs>
            
            <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                Enter the subscriber's **{currentTab.key.toUpperCase()}** to retrieve the profile.
            </Typography>
            <Box display="flex" alignItems="center" gap={2}>
              <TextField 
                fullWidth 
                label={currentTab.placeholder}
                value={searchTerm} 
                onChange={e => setSearchTerm(e.target.value)} 
                variant="outlined" 
                size="small"
                onKeyPress={(e) => e.key === 'Enter' && handleSearch(searchTerm, currentTab.key)}
                disabled={loading}
              />
              <Button 
                variant="contained" 
                startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Search />} 
                onClick={() => handleSearch(searchTerm, currentTab.key)} 
                disabled={loading || !searchTerm.trim()} 
                sx={{ py: '8px', whiteSpace: 'nowrap' }}
              >
                Search
              </Button>
            </Box>
        </Card>
    );
};


// --- View C: Search, Modify, & Delete Subscriber ---
const SubscriberSearch = ({ totalSubs, setTotalSubs, fetchCounts, isDeleteMode }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [searchType, setSearchType] = useState('uid');
  const [subscriber, setSubscriber] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({});
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  // Set the title based on the mode
  const title = isDeleteMode ? 'Delete Subscriber Profile' : 'Search & Modify Subscriber';

  const handleSearch = useCallback(async (term, type) => {
    const searchIdentifier = term.trim();
    if (!searchIdentifier) {
      setMessage({ type: 'warning', text: 'Please enter an identifier to search.' });
      return;
    }
    setLoading(true);
    setMessage({ type: '', text: '' });
    setSubscriber(null);
    setIsEditing(false);

    try {
      // Send the identifier and its type to the backend for accurate search
      const { data } = await API.get(`/provision/search?identifier=${searchIdentifier}&type=${type}`);
      setSubscriber(data);
      setFormData(data); 
      setMessage({ type: 'success', text: `Subscriber ${data.uid} found by ${type.toUpperCase()}. Source: ${data.source || 'Cloud/DynamoDB'}` });
      if (isDeleteMode) setIsDeleteModalOpen(true); // Open modal immediately if in delete mode
    } catch (err) {
      if (err.response?.status === 404) {
        setMessage({ type: 'error', text: `Subscriber identifier '${searchIdentifier}' not found.` });
      } else {
        setMessage({ type: 'error', text: err.response?.data?.msg || `Error during search: ${err.message}` });
      }
    } finally {
      setLoading(false);
    }
  }, [isDeleteMode]);

  const handleModify = async (e) => {
    e.preventDefault();
    setMessage({ type: '', text: '' });
    setLoading(true);

    if (!formData.uid || !formData.imsi) {
      setMessage({ type: 'error', text: 'UID and IMSI are mandatory fields.' });
      setLoading(false);
      return;
    }

    try {
      const response = await API.put(`/provision/subscriber/${formData.uid}`, formData);
      
      setMessage({ type: 'success', text: response.data?.msg || 'Subscriber updated successfully!' });
      setIsEditing(false);
      
      // Re-fetch data to update the detail view with fresh data
      await handleSearch(formData.uid, 'uid'); 
      
    } catch (err) {
      const errorMsg = err.response?.data?.msg || 'An unknown error occurred during update.';
      setMessage({ type: 'error', text: errorMsg });
    } finally {
      setLoading(false);
    }
  };
  
  const handleDeleteConfirm = async (uid) => {
    setMessage({ type: '', text: '' });
    setLoading(true);
    setIsDeleteModalOpen(false);

    try {
        await API.delete(`/provision/subscriber/${uid}`);
        
        setMessage({ type: 'success', text: 'Subscriber deleted successfully!' });
        setSubscriber(null); 
        setSearchTerm(''); 
        
        // Simulate real-time dashboard update (decrement count)
        setTotalSubs(prev => Math.max(0, prev - 1));
        fetchCounts();

    } catch (err) {
        setMessage({ type: 'error', text: err.response?.data?.msg || 'Delete operation failed.' });
    } finally {
        setLoading(false);
    }
  };
  
  // Render the form if in edit mode, otherwise render the detail view
  const renderContent = () => {
    if (isEditing) {
      return (
        <Box component="form" onSubmit={handleModify} sx={{ mt: 3 }}>
          <Alert severity="info" sx={{ my: 2 }}>
            You are editing Subscriber **{formData.uid}**. Changes will be saved to both Cloud and Legacy DBs (if enabled).
          </Alert>
          <SubscriberForm formData={formData} setFormData={setFormData} isEditing={true} />
          <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between' }}>
            <Button variant="outlined" onClick={() => { setIsEditing(false); setFormData(subscriber); }}>
              Cancel Edit
            </Button>
            <Button 
              type="submit" 
              variant="contained" 
              color="secondary" 
              startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Edit />}
              disabled={loading}
            >
              {loading ? 'Saving Changes...' : 'Save Modifications'}
            </Button>
          </Box>
        </Box>
      );
    }
    
    // Default view: Details + Action Buttons
    return (
      <Box>
        {subscriber && (
            <Box display="flex" justifyContent="flex-end" gap={1} sx={{ mt: 3 }}>
                <Button 
                    variant="contained" 
                    startIcon={<Edit />} 
                    onClick={() => setIsEditing(true)} 
                    color="primary"
                    disabled={isDeleteMode} // Can't modify if in Delete tab
                >
                    Modify Profile
                </Button>
                <Button 
                    variant="contained" 
                    color="error" 
                    startIcon={<Delete />} 
                    onClick={() => setIsDeleteModalOpen(true)}
                >
                    Delete Subscriber
                </Button>
            </Box>
        )}
        {subscriber && <SubscriberDetail subscriber={subscriber} />}
      </Box>
    );
  };
  
  return (
    <Box>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
        {isDeleteMode ? <Delete sx={{ mr: 1, color: 'error.main' }} /> : <Search sx={{ mr: 1 }} />} {title}
      </Typography>
      
      {/* Search Input Block - Now Tabbed */}
      <SearchTabs 
        searchTerm={searchTerm} 
        setSearchTerm={setSearchTerm} 
        handleSearch={handleSearch} 
        loading={loading}
        type={searchType}
        setSearchType={setSearchType} // Pass setter to SearchTabs
      />
      
      {/* Status Messages */}
      {message.text && <Alert severity={message.type.includes('Validation') || message.type.includes('error') ? 'error' : message.type} sx={{ my: 2 }} onClose={() => setMessage({ type: '', text: '' })}>{message.text}</Alert>}
      
      {/* Content Rendering (Detail or Edit Form) */}
      {renderContent()}

      {/* Delete Modal */}
      {subscriber && (
        <DeleteConfirmModal 
          open={isDeleteModalOpen}
          onClose={() => setIsDeleteModalOpen(false)}
          subscriber={subscriber}
          onConfirm={handleDeleteConfirm}
        />
      )}
    </Box>
  );
};


// ----------------------------------------------------------------------------------
// --- ROOT COMPONENT ---
// ----------------------------------------------------------------------------------

// SubscriberProvision is the main container that manages view state
export default function SubscriberProvision() {
  const [activeTab, setActiveTab] = useState(0); // 0=Dashboard, 1=Create, 2=Search/Modify, 3=Delete
  const [totalSubs, setTotalSubs] = useState(0);
  const [todayProvisions, setTodayProvisions] = useState(0);

  // Use useCallback to ensure this function doesn't change unnecessarily
  const fetchCounts = useCallback(async () => {
      try {
          const { data } = await API.get('/provision/count');
          setTotalSubs(data.total_subscribers);
          setTodayProvisions(data.today_provisions);
      } catch (err) {
          console.error("Failed to fetch subscriber counts:", err);
          setTotalSubs('N/A');
          setTodayProvisions('N/A');
      }
  }, []); // Empty dependency array ensures fetchCounts is stable

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };
  
  const renderContent = () => {
    switch (activeTab) {
      case 0:
        return <ProvisioningDashboard totalSubs={totalSubs} todayProvisions={todayProvisions} fetchCounts={fetchCounts} />;
      case 1:
        return <SubscriberCreate totalSubs={totalSubs} setTotalSubs={setTotalSubs} fetchCounts={fetchCounts} />;
      case 2:
        return <SubscriberSearch totalSubs={totalSubs} setTotalSubs={setTotalSubs} fetchCounts={fetchCounts} isDeleteMode={false} />;
      case 3:
        return <SubscriberSearch totalSubs={totalSubs} setTotalSubs={setTotalSubs} fetchCounts={fetchCounts} isDeleteMode={true} />;
      default:
        return <Typography>Select a Provisioning Option</Typography>;
    }
  };

  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, borderBottom: '2px solid #1976d2', pb: 1 }}>
        Subscriber Provisioning Operations
      </Typography>

      <Box sx={{ width: '100%', mb: 4 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="provisioning tabs" variant="fullWidth">
          <Tab label="Dashboard" icon={<Dashboard />} iconPosition="start" />
          <Tab label="Create Subscriber" icon={<Add />} iconPosition="start" />
          <Tab label="Search & Modify" icon={<Edit />} iconPosition="start" />
          <Tab label="Delete Subscriber" icon={<Delete />} iconPosition="start" />
        </Tabs>
      </Box>

      {renderContent()}
    </Paper>
  );
}
