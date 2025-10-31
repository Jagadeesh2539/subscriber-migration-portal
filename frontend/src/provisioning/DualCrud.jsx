import React, { useState, useCallback } from 'react';
import {
  Box, Typography, Button, TextField, Select, MenuItem, FormControl, InputLabel,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Chip, Stack,
  Alert, Tooltip, Card, CardContent, Grid, Divider, LinearProgress
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import {
  Add, Edit, Delete, Search, Sync, Refresh, Download, Upload,
  FilterList, Clear, Warning, CheckCircle, Error, CompareArrows
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { format } from 'date-fns';

// API service placeholder - will be implemented
const dualService = {
  getSubscribers: async (params) => {
    // TODO: Implement /dual/subscribers API call
    // Returns data from both Cloud and Legacy with sync status
    return { data: { subscribers: [], pagination: { hasMore: false, count: 0 } } };
  },
  createSubscriber: async (data) => {
    // TODO: Implement POST /dual/subscribers (writes to both)
    return { data: { cloudResult: {}, legacyResult: {}, conflicts: [] } };
  },
  updateSubscriber: async (uid, data) => {
    // TODO: Implement PUT /dual/subscribers/{uid} (updates both)
    return { data: { cloudResult: {}, legacyResult: {}, conflicts: [] } };
  },
  deleteSubscriber: async (uid) => {
    // TODO: Implement DELETE /dual/subscribers/{uid} (deletes from both)
    return { success: true, cloudResult: {}, legacyResult: {} };
  },
  syncSubscriber: async (uid) => {
    // TODO: Implement POST /dual/subscribers/{uid}/sync (resolve conflicts)
    return { success: true };
  },
};

// Status options
const statusOptions = [
  { value: 'ACTIVE', label: 'Active', color: 'success' },
  { value: 'INACTIVE', label: 'Inactive', color: 'default' },
  { value: 'SUSPENDED', label: 'Suspended', color: 'warning' },
  { value: 'DELETED', label: 'Deleted', color: 'error' },
];

// Plan options
const planOptions = [
  { value: 'BASIC', label: 'Basic Plan' },
  { value: 'PREMIUM', label: 'Premium Plan' },
  { value: 'ENTERPRISE', label: 'Enterprise Plan' },
];

// Sync status indicators
const SyncStatusChip = ({ status }) => {
  const statusConfig = {
    'SYNCED': { color: 'success', icon: <CheckCircle />, label: 'Synced' },
    'OUT_OF_SYNC': { color: 'warning', icon: <Warning />, label: 'Out of Sync' },
    'CLOUD_ONLY': { color: 'info', icon: <Error />, label: 'Cloud Only' },
    'LEGACY_ONLY': { color: 'error', icon: <Error />, label: 'Legacy Only' },
    'CONFLICT': { color: 'error', icon: <CompareArrows />, label: 'Conflict' },
  };
  
  const config = statusConfig[status] || statusConfig['CONFLICT'];
  
  return (
    <Chip
      icon={config.icon}
      label={config.label}
      color={config.color}
      size="small"
      variant="outlined"
    />
  );
};

const DualCrud = () => {
  const [filters, setFilters] = useState({
    status: '',
    planId: '',
    search: '',
    syncStatus: '', // SYNCED, OUT_OF_SYNC, CLOUD_ONLY, LEGACY_ONLY, CONFLICT
  });
  const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
  const [selectedRows, setSelectedRows] = useState([]);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedSubscriber, setSelectedSubscriber] = useState(null);
  const [formData, setFormData] = useState({
    uid: '',
    msisdn: '',
    imsi: '',
    status: 'ACTIVE',
    planId: '',
    email: '',
    firstName: '',
    lastName: '',
  });

  const queryClient = useQueryClient();

  // Query subscribers with filters
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dual-subscribers', filters, paginationModel],
    queryFn: () => dualService.getSubscribers({
      ...filters,
      page: paginationModel.page,
      limit: paginationModel.pageSize,
    }),
    staleTime: 1 * 60 * 1000, // 1 minute (dual needs fresh data)
  });

  // Mutations with dual provisioning messaging
  const createMutation = useMutation({
    mutationFn: dualService.createSubscriber,
    onSuccess: (result) => {
      const { cloudResult, legacyResult, conflicts } = result.data;
      if (conflicts?.length > 0) {
        toast.error(`Dual create completed with ${conflicts.length} conflict(s)`);
      } else {
        toast.success('Subscriber created successfully in both Cloud and Legacy');
      }
      queryClient.invalidateQueries(['dual-subscribers']);
      setCreateDialogOpen(false);
      resetForm();
    },
    onError: (error) => {
      toast.error(`Failed to create in dual mode: ${error.message}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ uid, ...data }) => dualService.updateSubscriber(uid, data),
    onSuccess: (result) => {
      const { cloudResult, legacyResult, conflicts } = result.data;
      if (conflicts?.length > 0) {
        toast.warning(`Dual update completed with ${conflicts.length} conflict(s)`);
      } else {
        toast.success('Subscriber updated successfully in both systems');
      }
      queryClient.invalidateQueries(['dual-subscribers']);
      setEditDialogOpen(false);
      resetForm();
    },
    onError: (error) => {
      toast.error(`Failed to update in dual mode: ${error.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: dualService.deleteSubscriber,
    onSuccess: (result) => {
      const { cloudResult, legacyResult } = result;
      toast.success('Subscriber deleted successfully from both systems');
      queryClient.invalidateQueries(['dual-subscribers']);
      setDeleteDialogOpen(false);
      setSelectedSubscriber(null);
    },
    onError: (error) => {
      toast.error(`Failed to delete from dual systems: ${error.message}`);
    },
  });

  const syncMutation = useMutation({
    mutationFn: dualService.syncSubscriber,
    onSuccess: () => {
      toast.success('Subscriber synchronized between Cloud and Legacy');
      queryClient.invalidateQueries(['dual-subscribers']);
    },
    onError: (error) => {
      toast.error(`Failed to sync subscriber: ${error.message}`);
    },
  });

  // DataGrid columns with sync status
  const columns = [
    {
      field: 'uid',
      headerName: 'UID',
      width: 120,
      filterable: true,
    },
    {
      field: 'syncStatus',
      headerName: 'Sync Status',
      width: 140,
      renderCell: (params) => <SyncStatusChip status={params.value} />,
    },
    {
      field: 'msisdn',
      headerName: 'MSISDN',
      width: 140,
      filterable: true,
    },
    {
      field: 'imsi',
      headerName: 'IMSI',
      width: 150,
      filterable: true,
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 120,
      renderCell: (params) => {
        const statusOption = statusOptions.find(opt => opt.value === params.value);
        return (
          <Chip
            label={statusOption?.label || params.value}
            color={statusOption?.color || 'default'}
            size="small"
          />
        );
      },
    },
    {
      field: 'planId',
      headerName: 'Plan',
      width: 120,
      filterable: true,
    },
    {
      field: 'email',
      headerName: 'Email',
      width: 200,
      filterable: true,
    },
    {
      field: 'cloudUpdatedAt',
      headerName: 'Cloud Updated',
      width: 140,
      valueFormatter: (params) => {
        return params.value ? format(new Date(params.value), 'MMM dd, HH:mm') : 'N/A';
      },
    },
    {
      field: 'legacyUpdatedAt',
      headerName: 'Legacy Updated',
      width: 140,
      valueFormatter: (params) => {
        return params.value ? format(new Date(params.value), 'MMM dd, HH:mm') : 'N/A';
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 160,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Tooltip title="Edit Both">
            <IconButton size="small" onClick={() => handleEdit(params.row)}>
              <Edit />
            </IconButton>
          </Tooltip>
          <Tooltip title="Sync">
            <IconButton 
              size="small" 
              color="info" 
              onClick={() => handleSync(params.row)}
              disabled={params.row.syncStatus === 'SYNCED'}
            >
              <Sync />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete Both">
            <IconButton size="small" color="error" onClick={() => handleDelete(params.row)}>
              <Delete />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  // Event handlers
  const resetForm = () => {
    setFormData({
      uid: '',
      msisdn: '',
      imsi: '',
      status: 'ACTIVE',
      planId: '',
      email: '',
      firstName: '',
      lastName: '',
    });
  };

  const handleCreate = () => {
    resetForm();
    setCreateDialogOpen(true);
  };

  const handleEdit = (subscriber) => {
    setFormData({ ...subscriber });
    setSelectedSubscriber(subscriber);
    setEditDialogOpen(true);
  };

  const handleDelete = (subscriber) => {
    setSelectedSubscriber(subscriber);
    setDeleteDialogOpen(true);
  };

  const handleSync = (subscriber) => {
    syncMutation.mutate(subscriber.uid);
  };

  const handleSubmitCreate = () => {
    createMutation.mutate(formData);
  };

  const handleSubmitEdit = () => {
    updateMutation.mutate({ uid: selectedSubscriber.uid, ...formData });
  };

  const handleSubmitDelete = () => {
    deleteMutation.mutate(selectedSubscriber.uid);
  };

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({ ...prev, [field]: value }));
    setPaginationModel(prev => ({ ...prev, page: 0 }));
  };

  const clearFilters = () => {
    setFilters({ status: '', planId: '', search: '', syncStatus: '' });
    setPaginationModel(prev => ({ ...prev, page: 0 }));
  };

  const subscribers = data?.data?.subscribers || [];
  const totalCount = data?.data?.pagination?.count || 0;
  const syncStats = data?.data?.syncStats || { synced: 0, outOfSync: 0, cloudOnly: 0, legacyOnly: 0 };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <Sync color="info" sx={{ fontSize: 32 }} />
          <Typography variant="h4">Dual Provision (Cloud + Legacy)</Typography>
          <Chip label="DUAL_PROV MODE" color="info" variant="outlined" />
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            color="info"
            startIcon={<Add />}
            onClick={handleCreate}
          >
            Add to Both Systems
          </Button>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => refetch()}
          >
            Refresh
          </Button>
        </Stack>
      </Stack>

      {/* Dual Provisioning Info */}
      <Alert severity="info" sx={{ mb: 3 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <CompareArrows />
          <Box>
            <Typography variant="body1" fontWeight="bold">
              Dual Provisioning Mode Active
            </Typography>
            <Typography variant="body2">
              All operations will be performed on both Cloud (DynamoDB) and Legacy (RDS MySQL) systems.
              Sync status indicates consistency between the two systems.
            </Typography>
          </Box>
        </Stack>
      </Alert>

      {/* Sync Statistics */}
      <Card sx={{ mb: 3, bgcolor: 'info.light', color: 'info.contrastText' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            📊 Synchronization Statistics
          </Typography>
          <Grid container spacing={3}>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="success.main">{syncStats.synced}</Typography>
                <Typography variant="body2">Synced</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="warning.main">{syncStats.outOfSync}</Typography>
                <Typography variant="body2">Out of Sync</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="info.main">{syncStats.cloudOnly}</Typography>
                <Typography variant="body2">Cloud Only</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="error.main">{syncStats.legacyOnly}</Typography>
                <Typography variant="body2">Legacy Only</Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card sx={{ mb: 3, border: '1px solid', borderColor: 'info.main' }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={2} mb={2}>
            <FilterList />
            <Typography variant="h6">Dual System Filters</Typography>
          </Stack>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Status</InputLabel>
                <Select
                  value={filters.status}
                  label="Status"
                  onChange={(e) => handleFilterChange('status', e.target.value)}
                >
                  <MenuItem value="">
                    <em>All Statuses</em>
                  </MenuItem>
                  {statusOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Plan</InputLabel>
                <Select
                  value={filters.planId}
                  label="Plan"
                  onChange={(e) => handleFilterChange('planId', e.target.value)}
                >
                  <MenuItem value="">
                    <em>All Plans</em>
                  </MenuItem>
                  {planOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Sync Status</InputLabel>
                <Select
                  value={filters.syncStatus}
                  label="Sync Status"
                  onChange={(e) => handleFilterChange('syncStatus', e.target.value)}
                >
                  <MenuItem value="">
                    <em>All Sync States</em>
                  </MenuItem>
                  <MenuItem value="SYNCED">Synced</MenuItem>
                  <MenuItem value="OUT_OF_SYNC">Out of Sync</MenuItem>
                  <MenuItem value="CLOUD_ONLY">Cloud Only</MenuItem>
                  <MenuItem value="LEGACY_ONLY">Legacy Only</MenuItem>
                  <MenuItem value="CONFLICT">Conflicts</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <TextField
                fullWidth
                size="small"
                label="Search (UID, MSISDN, IMSI, Email)"
                value={filters.search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
                InputProps={{
                  startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />,
                }}
                helperText="Searches both systems"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<Clear />}
                onClick={clearFilters}
                size="small"
              >
                Clear
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load Dual subscribers: {error.message}
          <br />
          <Typography variant="caption">
            Check both Cloud (DynamoDB) and Legacy (RDS) connectivity.
          </Typography>
        </Alert>
      )}

      {/* Data Grid */}
      <Card sx={{ border: '1px solid', borderColor: 'info.main' }}>
        <CardContent sx={{ p: 0 }}>
          <DataGrid
            rows={subscribers}
            columns={columns}
            loading={isLoading}
            getRowId={(row) => row.uid}
            pageSizeOptions={[10, 25, 50, 100]}
            paginationModel={paginationModel}
            onPaginationModelChange={setPaginationModel}
            paginationMode="server"
            rowCount={totalCount}
            checkboxSelection
            onRowSelectionModelChange={setSelectedRows}
            disableRowSelectionOnClick
            autoHeight
            sx={{
              minHeight: 400,
              '& .MuiDataGrid-root': {
                border: 'none',
              },
              '& .MuiDataGrid-columnHeaders': {
                backgroundColor: 'info.light',
                color: 'info.contrastText',
              },
              // Row styling based on sync status
              '& .MuiDataGrid-row': {
                '&[data-sync-status="OUT_OF_SYNC"]': {
                  backgroundColor: 'warning.light',
                  opacity: 0.8,
                },
                '&[data-sync-status="CONFLICT"]': {
                  backgroundColor: 'error.light',
                  opacity: 0.7,
                },
              },
            }}
            getRowClassName={(params) => `sync-status-${params.row.syncStatus?.toLowerCase() || 'unknown'}`}
          />
        </CardContent>
      </Card>

      {/* Bulk Actions for Dual */}
      {selectedRows.length > 0 && (
        <Card sx={{ mt: 2, bgcolor: 'info.light', border: '1px solid', borderColor: 'info.main' }}>
          <CardContent>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Stack direction="row" alignItems="center" spacing={1}>
                <CompareArrows color="info" />
                <Typography variant="body1">
                  {selectedRows.length} subscriber(s) selected for dual operations
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  variant="outlined"
                  color="info"
                  startIcon={<Edit />}
                >
                  Bulk Edit Both
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="info"
                  startIcon={<Sync />}
                >
                  Bulk Sync
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<Delete />}
                >
                  Bulk Delete Both
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<Download />}
                >
                  Export Comparison
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <CompareArrows color="info" />
            <span>Create in Both Systems</span>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Creating subscriber in both Cloud (DynamoDB) and Legacy (RDS MySQL) systems simultaneously.
            Conflicts will be reported if any occur.
          </Alert>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                required
                fullWidth
                label="UID"
                value={formData.uid}
                onChange={(e) => setFormData(prev => ({ ...prev, uid: e.target.value }))}
                helperText="Must be unique in both systems"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                required
                fullWidth
                label="MSISDN"
                value={formData.msisdn}
                onChange={(e) => setFormData(prev => ({ ...prev, msisdn: e.target.value }))}
                helperText="Must be unique in both systems"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                required
                fullWidth
                label="IMSI"
                value={formData.imsi}
                onChange={(e) => setFormData(prev => ({ ...prev, imsi: e.target.value }))}
                helperText="Must be unique in both systems"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={formData.status}
                  label="Status"
                  onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value }))}
                >
                  {statusOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Plan</InputLabel>
                <Select
                  value={formData.planId}
                  label="Plan"
                  onChange={(e) => setFormData(prev => ({ ...prev, planId: e.target.value }))}
                >
                  {planOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="First Name"
                value={formData.firstName}
                onChange={(e) => setFormData(prev => ({ ...prev, firstName: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Last Name"
                value={formData.lastName}
                onChange={(e) => setFormData(prev => ({ ...prev, lastName: e.target.value }))}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleSubmitCreate} 
            variant="contained"
            color="info"
            disabled={createMutation.isLoading || !formData.uid || !formData.msisdn || !formData.imsi}
          >
            {createMutation.isLoading ? (
              <Stack direction="row" alignItems="center" spacing={1}>
                <LinearProgress size={20} />
                <span>Creating in Both...</span>
              </Stack>
            ) : (
              'Create in Both Systems'
            )}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Edit />
            <span>Edit in Both Systems</span>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Warning />
              <Box>
                <Typography variant="body1" fontWeight="bold">
                  Dual System Update
                </Typography>
                <Typography variant="body2">
                  Changes will be applied to both Cloud and Legacy. Any conflicts will be reported.
                  Current sync status: <strong>{selectedSubscriber?.syncStatus || 'Unknown'}</strong>
                </Typography>
              </Box>
            </Stack>
          </Alert>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="UID"
                value={formData.uid}
                disabled
                helperText="UID cannot be changed"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="MSISDN"
                value={formData.msisdn}
                onChange={(e) => setFormData(prev => ({ ...prev, msisdn: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="IMSI"
                value={formData.imsi}
                onChange={(e) => setFormData(prev => ({ ...prev, imsi: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={formData.status}
                  label="Status"
                  onChange={(e) => setFormData(prev => ({ ...prev, status: e.target.value }))}
                >
                  {statusOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Plan</InputLabel>
                <Select
                  value={formData.planId}
                  label="Plan"
                  onChange={(e) => setFormData(prev => ({ ...prev, planId: e.target.value }))}
                >
                  {planOptions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="First Name"
                value={formData.firstName}
                onChange={(e) => setFormData(prev => ({ ...prev, firstName: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Last Name"
                value={formData.lastName}
                onChange={(e) => setFormData(prev => ({ ...prev, lastName: e.target.value }))}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleSubmitEdit} 
            variant="contained"
            color="info"
            disabled={updateMutation.isLoading}
          >
            {updateMutation.isLoading ? 'Updating Both Systems...' : 'Update Both Systems'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle color="error">
          <Stack direction="row" alignItems="center" spacing={1}>
            <Delete color="error" />
            <span>Confirm Dual System Delete</span>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography gutterBottom>
            Are you sure you want to delete subscriber <strong>{selectedSubscriber?.uid}</strong> from both Cloud (DynamoDB) and Legacy (RDS MySQL) systems?
          </Typography>
          <Alert severity="error" sx={{ mt: 2 }}>
            <Typography variant="body1" fontWeight="bold">
              This action cannot be undone.
            </Typography>
            <Typography variant="body2">
              The record will be permanently removed from both systems. Current sync status: <strong>{selectedSubscriber?.syncStatus || 'Unknown'}</strong>
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleSubmitDelete} 
            color="error" 
            variant="contained"
            disabled={deleteMutation.isLoading}
          >
            {deleteMutation.isLoading ? 'Deleting from Both...' : 'Delete from Both Systems'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DualCrud;