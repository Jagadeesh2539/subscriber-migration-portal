import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  LinearProgress,
  Grid,
  Card,
  CardContent,
  CardActions,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Checkbox,
  Menu,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Search as SearchIcon,
  Upload as UploadIcon,
  Download as DownloadIcon,
  CloudQueue as CloudIcon,
  Storage as LegacyIcon,
  SyncAlt as DualIcon,
  Compare as CompareIcon,
  Refresh as RefreshIcon,
  MoreVert as MoreIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
import { useSnackbar } from 'notistack';

import { subscriberApi } from '../api/subscribers';
import { ConfirmDialog } from './common/ConfirmDialog';
import { LoadingButton } from './common/LoadingButton';
import { StatusChip } from './common/StatusChip';

interface Subscriber {
  uid: string;
  imsi: string;
  msisdn: string;
  status: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED' | 'DELETED';
  source: 'cloud' | 'legacy';
  created_at: string;
  updated_at: string;
  apn?: string;
  service_profile?: string;
  roaming_allowed?: boolean;
  data_limit?: number;
}

interface ProvisioningConfig {
  current_mode: 'legacy' | 'cloud' | 'dual';
  available_modes: string[];
  mode_descriptions: Record<string, string>;
  system_status: {
    dynamodb: boolean;
    mysql: boolean;
  };
}

interface SystemStats {
  cloud: { total: number; active: number; inactive: number; status: string };
  legacy: { total: number; active: number; inactive: number; status: string };
  combined: { total: number; active: number; inactive: number };
  last_updated: string;
}

const SubscriberManagement: React.FC = () => {
  // State management
  const [subscribers, setSubscribers] = useState<Subscriber[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRows, setSelectedRows] = useState<GridRowSelectionModel>([]);
  const [currentTab, setCurrentTab] = useState(0);
  
  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  
  // Forms
  const [newSubscriber, setNewSubscriber] = useState({
    uid: '',
    imsi: '',
    msisdn: '',
    status: 'ACTIVE' as const,
    provisioning_mode: 'dual' as const,
    apn: '',
    service_profile: '',
    roaming_allowed: true,
    data_limit: 0
  });
  
  const [editingSubscriber, setEditingSubscriber] = useState<Subscriber | null>(null);
  
  // Filters and pagination
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [totalCount, setTotalCount] = useState(0);
  
  // Configuration and stats
  const [provisioningConfig, setProvisioningConfig] = useState<ProvisioningConfig | null>(null);
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
  const [bulkMenuAnchor, setBulkMenuAnchor] = useState<null | HTMLElement>(null);
  
  // File upload
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadMode, setUploadMode] = useState('dual');
  const [uploadProgress, setUploadProgress] = useState(0);
  
  const { enqueueSnackbar } = useSnackbar();

  // Load data on component mount
  useEffect(() => {
    loadData();
    loadProvisioningConfig();
    loadSystemStats();
  }, [page, pageSize, searchTerm, statusFilter, sourceFilter]);

  const loadData = async () => {
    setLoading(true);
    try {
      const response = await subscriberApi.getSubscribers({
        search: searchTerm,
        status: statusFilter === 'all' ? undefined : statusFilter,
        source: sourceFilter === 'all' ? undefined : sourceFilter,
        limit: pageSize,
        offset: page * pageSize,
      });
      
      setSubscribers(response.data.subscribers);
      setTotalCount(response.data.pagination.total_count);
    } catch (error) {
      enqueueSnackbar('Failed to load subscribers', { variant: 'error' });
    }
    setLoading(false);
  };

  const loadProvisioningConfig = async () => {
    try {
      const response = await subscriberApi.getProvisioningConfig();
      setProvisioningConfig(response.data);
    } catch (error) {
      console.error('Failed to load provisioning config:', error);
    }
  };

  const loadSystemStats = async () => {
    try {
      const response = await subscriberApi.getSystemStats();
      setSystemStats(response.data);
    } catch (error) {
      console.error('Failed to load system stats:', error);
    }
  };

  const handleCreateSubmit = async () => {
    try {
      await subscriberApi.createSubscriber(newSubscriber);
      enqueueSnackbar('Subscriber created successfully', { variant: 'success' });
      setCreateDialogOpen(false);
      setNewSubscriber({
        uid: '',
        imsi: '',
        msisdn: '',
        status: 'ACTIVE',
        provisioning_mode: 'dual',
        apn: '',
        service_profile: '',
        roaming_allowed: true,
        data_limit: 0
      });
      loadData();
      loadSystemStats();
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to create subscriber', { 
        variant: 'error' 
      });
    }
  };

  const handleEditSubmit = async () => {
    if (!editingSubscriber) return;
    
    try {
      await subscriberApi.updateSubscriber(editingSubscriber.uid, {
        status: editingSubscriber.status,
        msisdn: editingSubscriber.msisdn,
        apn: editingSubscriber.apn,
        service_profile: editingSubscriber.service_profile,
        roaming_allowed: editingSubscriber.roaming_allowed,
        data_limit: editingSubscriber.data_limit,
      });
      enqueueSnackbar('Subscriber updated successfully', { variant: 'success' });
      setEditDialogOpen(false);
      setEditingSubscriber(null);
      loadData();
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to update subscriber', { 
        variant: 'error' 
      });
    }
  };

  const handleDelete = async (subscriberId: string) => {
    try {
      await subscriberApi.deleteSubscriber(subscriberId, {
        soft: true,
        mode: provisioningConfig?.current_mode || 'dual'
      });
      enqueueSnackbar('Subscriber deleted successfully', { variant: 'success' });
      loadData();
      loadSystemStats();
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to delete subscriber', { 
        variant: 'error' 
      });
    }
  };

  const handleBulkOperation = async (operation: string) => {
    if (selectedRows.length === 0) {
      enqueueSnackbar('Please select subscribers first', { variant: 'warning' });
      return;
    }

    try {
      await subscriberApi.bulkOperation({
        operation,
        subscriber_ids: selectedRows as string[],
        provisioning_mode: provisioningConfig?.current_mode || 'dual',
        soft_delete: operation === 'delete'
      });
      
      enqueueSnackbar(`Bulk ${operation} completed successfully`, { variant: 'success' });
      setSelectedRows([]);
      setBulkMenuAnchor(null);
      loadData();
      loadSystemStats();
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || `Failed to perform bulk ${operation}`, { 
        variant: 'error' 
      });
    }
  };

  const handleFileUpload = async () => {
    if (!uploadFile) {
      enqueueSnackbar('Please select a file', { variant: 'warning' });
      return;
    }

    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('provisioning_mode', uploadMode);

    try {
      setUploadProgress(0);
      const response = await subscriberApi.uploadCSV(formData, {
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total!);
          setUploadProgress(progress);
        }
      });
      
      enqueueSnackbar(
        `CSV processed: ${response.data.summary.successful} successful, ${response.data.summary.failed} failed`,
        { variant: 'success' }
      );
      
      setUploadDialogOpen(false);
      setUploadFile(null);
      setUploadProgress(0);
      loadData();
      loadSystemStats();
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to upload CSV', { 
        variant: 'error' 
      });
      setUploadProgress(0);
    }
  };

  const handleCompareSystem = async () => {
    try {
      setLoading(true);
      const response = await subscriberApi.compareSystems({ sample_size: 1000 });
      
      enqueueSnackbar(
        `Comparison completed: ${response.data.summary.accuracy}% accuracy`,
        { variant: 'info' }
      );
      
      setCompareDialogOpen(false);
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to compare systems', { 
        variant: 'error' 
      });
    }
    setLoading(false);
  };

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      const response = await subscriberApi.exportSubscribers({
        system: sourceFilter === 'all' ? 'all' : sourceFilter,
        format,
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 10000
      });
      
      // Create download
      const blob = new Blob([response.data], { 
        type: format === 'csv' ? 'text/csv' : 'application/json' 
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `subscribers_${sourceFilter}_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      enqueueSnackbar(`Data exported successfully`, { variant: 'success' });
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to export data', { 
        variant: 'error' 
      });
    }
  };

  const handleProvisioningModeChange = async (newMode: string) => {
    try {
      await subscriberApi.setProvisioningMode({ mode: newMode });
      enqueueSnackbar(`Provisioning mode updated to ${newMode}`, { variant: 'success' });
      loadProvisioningConfig();
      setConfigDialogOpen(false);
    } catch (error: any) {
      enqueueSnackbar(error.response?.data?.message || 'Failed to update provisioning mode', { 
        variant: 'error' 
      });
    }
  };

  // DataGrid columns
  const columns: GridColDef[] = [
    {
      field: 'uid',
      headerName: 'UID',
      width: 120,
      renderCell: (params) => (
        <Tooltip title={params.value}>
          <Typography variant="body2" noWrap>
            {params.value}
          </Typography>
        </Tooltip>
      )
    },
    {
      field: 'imsi',
      headerName: 'IMSI',
      width: 150,
      renderCell: (params) => (
        <Typography variant="body2" fontFamily="monospace">
          {params.value}
        </Typography>
      )
    },
    {
      field: 'msisdn',
      headerName: 'MSISDN',
      width: 130,
      renderCell: (params) => (
        <Typography variant="body2" fontFamily="monospace">
          {params.value || '-'}
        </Typography>
      )
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 100,
      renderCell: (params) => <StatusChip status={params.value} />
    },
    {
      field: 'source',
      headerName: 'Source',
      width: 100,
      renderCell: (params) => (
        <Chip
          icon={params.value === 'cloud' ? <CloudIcon /> : <LegacyIcon />}
          label={params.value}
          size="small"
          color={params.value === 'cloud' ? 'primary' : 'secondary'}
        />
      )
    },
    {
      field: 'apn',
      headerName: 'APN',
      width: 120,
      renderCell: (params) => (
        <Typography variant="body2">
          {params.value || '-'}
        </Typography>
      )
    },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 140,
      renderCell: (params) => (
        <Typography variant="body2">
          {new Date(params.value).toLocaleDateString()}
        </Typography>
      )
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      sortable: false,
      renderCell: (params) => (
        <Box>
          <IconButton
            size="small"
            onClick={() => {
              setEditingSubscriber(params.row);
              setEditDialogOpen(true);
            }}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            color="error"
            onClick={() => handleDelete(params.row.uid)}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Box>
      )
    }
  ];

  return (
    <Box sx={{ p: 3 }}>
      {/* Header with System Stats */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Subscriber Management
        </Typography>
        
        {systemStats && (
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <CloudIcon color="primary" sx={{ mr: 1 }} />
                    <Typography variant="h6">Cloud (DynamoDB)</Typography>
                  </Box>
                  <Typography variant="h4" color="primary">
                    {systemStats.cloud.total.toLocaleString()}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {systemStats.cloud.active} active • {systemStats.cloud.inactive} inactive
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <LegacyIcon color="secondary" sx={{ mr: 1 }} />
                    <Typography variant="h6">Legacy (MySQL)</Typography>
                  </Box>
                  <Typography variant="h4" color="secondary">
                    {systemStats.legacy.total.toLocaleString()}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {systemStats.legacy.active} active • {systemStats.legacy.inactive} inactive
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <DualIcon sx={{ mr: 1 }} />
                    <Typography variant="h6">Combined Total</Typography>
                  </Box>
                  <Typography variant="h4">
                    {systemStats.combined.total.toLocaleString()}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {systemStats.combined.active} active • {systemStats.combined.inactive} inactive
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
        
        {/* Provisioning Mode Indicator */}
        {provisioningConfig && (
          <Alert 
            severity="info" 
            sx={{ mb: 2 }}
            action={
              <Button 
                color="inherit" 
                size="small" 
                onClick={() => setConfigDialogOpen(true)}
              >
                Configure
              </Button>
            }
          >
            Current provisioning mode: <strong>{provisioningConfig.current_mode}</strong> - {provisioningConfig.mode_descriptions[provisioningConfig.current_mode]}
          </Alert>
        )}
      </Box>

      {/* Action Buttons */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
        >
          Create Subscriber
        </Button>
        
        <Button
          variant="outlined"
          startIcon={<UploadIcon />}
          onClick={() => setUploadDialogOpen(true)}
        >
          Upload CSV
        </Button>
        
        <Button
          variant="outlined"
          startIcon={<DownloadIcon />}
          onClick={() => handleExport('csv')}
        >
          Export CSV
        </Button>
        
        <Button
          variant="outlined"
          startIcon={<CompareIcon />}
          onClick={() => setCompareDialogOpen(true)}
        >
          Compare Systems
        </Button>
        
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={loadData}
          disabled={loading}
        >
          Refresh
        </Button>
        
        {selectedRows.length > 0 && (
          <Button
            variant="outlined"
            startIcon={<MoreIcon />}
            onClick={(e) => setBulkMenuAnchor(e.currentTarget)}
          >
            Bulk Actions ({selectedRows.length})
          </Button>
        )}
      </Box>

      {/* Filters */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <TextField
          label="Search (UID, IMSI, MSISDN)"
          variant="outlined"
          size="small"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: <SearchIcon sx={{ mr: 1, color: 'action.active' }} />
          }}
          sx={{ minWidth: 250 }}
        />
        
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={statusFilter}
            label="Status"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="ACTIVE">Active</MenuItem>
            <MenuItem value="INACTIVE">Inactive</MenuItem>
            <MenuItem value="SUSPENDED">Suspended</MenuItem>
            <MenuItem value="DELETED">Deleted</MenuItem>
          </Select>
        </FormControl>
        
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Source</InputLabel>
          <Select
            value={sourceFilter}
            label="Source"
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="cloud">Cloud</MenuItem>
            <MenuItem value="legacy">Legacy</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* Data Grid */}
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={subscribers}
          columns={columns}
          getRowId={(row) => row.uid}
          loading={loading}
          checkboxSelection
          rowSelectionModel={selectedRows}
          onRowSelectionModelChange={setSelectedRows}
          paginationMode="server"
          rowCount={totalCount}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          pageSizeOptions={[10, 25, 50, 100]}
          disableRowSelectionOnClick
        />
      </Paper>

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Create New Subscriber</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="UID *"
                value={newSubscriber.uid}
                onChange={(e) => setNewSubscriber({...newSubscriber, uid: e.target.value})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="IMSI *"
                value={newSubscriber.imsi}
                onChange={(e) => setNewSubscriber({...newSubscriber, imsi: e.target.value})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="MSISDN"
                value={newSubscriber.msisdn}
                onChange={(e) => setNewSubscriber({...newSubscriber, msisdn: e.target.value})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={newSubscriber.status}
                  label="Status"
                  onChange={(e) => setNewSubscriber({...newSubscriber, status: e.target.value as any})}
                >
                  <MenuItem value="ACTIVE">Active</MenuItem>
                  <MenuItem value="INACTIVE">Inactive</MenuItem>
                  <MenuItem value="SUSPENDED">Suspended</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="APN"
                value={newSubscriber.apn}
                onChange={(e) => setNewSubscriber({...newSubscriber, apn: e.target.value})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Service Profile"
                value={newSubscriber.service_profile}
                onChange={(e) => setNewSubscriber({...newSubscriber, service_profile: e.target.value})}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={newSubscriber.roaming_allowed}
                    onChange={(e) => setNewSubscriber({...newSubscriber, roaming_allowed: e.target.checked})}
                  />
                }
                label="Roaming Allowed"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Provisioning Mode</InputLabel>
                <Select
                  value={newSubscriber.provisioning_mode}
                  label="Provisioning Mode"
                  onChange={(e) => setNewSubscriber({...newSubscriber, provisioning_mode: e.target.value as any})}
                >
                  <MenuItem value="legacy">Legacy Only</MenuItem>
                  <MenuItem value="cloud">Cloud Only</MenuItem>
                  <MenuItem value="dual">Dual (Both Systems)</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <LoadingButton 
            onClick={handleCreateSubmit}
            disabled={!newSubscriber.uid || !newSubscriber.imsi}
          >
            Create Subscriber
          </LoadingButton>
        </DialogActions>
      </Dialog>

      {/* Additional dialogs and menus would go here... */}
      
    </Box>
  );
};

export default SubscriberManagement;