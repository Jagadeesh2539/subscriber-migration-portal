import React, { useState, useCallback } from 'react';
import {
  Box, Typography, Button, TextField, Select, MenuItem, FormControl, InputLabel,
  Dialog, DialogTitle, DialogContent, DialogActions, IconButton, Chip, Stack,
  Alert, Tooltip, Card, CardContent, Grid, Divider
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import {
  Add, Edit, Delete, Search, Storage, Refresh, Download, Upload,
  FilterList, Clear, Warning, Database
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { format } from 'date-fns';

// API service placeholder - will be implemented
const legacyService = {
  getSubscribers: async (params) => {
    // TODO: Implement /legacy/subscribers API call
    return { data: { subscribers: [], pagination: { hasMore: false, count: 0 } } };
  },
  createSubscriber: async (data) => {
    // TODO: Implement POST /legacy/subscribers
    return { data };
  },
  updateSubscriber: async (uid, data) => {
    // TODO: Implement PUT /legacy/subscribers/{uid}
    return { data };
  },
  deleteSubscriber: async (uid) => {
    // TODO: Implement DELETE /legacy/subscribers/{uid}
    return { success: true };
  },
};

// Status options matching RDS MySQL ENUM
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

const LegacyCrud = () => {
  const [filters, setFilters] = useState({
    status: '',
    planId: '',
    search: '',
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
    queryKey: ['legacy-subscribers', filters, paginationModel],
    queryFn: () => legacyService.getSubscribers({
      ...filters,
      page: paginationModel.page,
      limit: paginationModel.pageSize,
    }),
    staleTime: 5 * 60 * 1000, // 5 minutes (legacy is slower)
  });

  // Mutations with legacy-specific messaging
  const createMutation = useMutation({
    mutationFn: legacyService.createSubscriber,
    onSuccess: () => {
      toast.success('Subscriber created successfully in Legacy RDS');
      queryClient.invalidateQueries(['legacy-subscribers']);
      setCreateDialogOpen(false);
      resetForm();
    },
    onError: (error) => {
      toast.error(`Failed to create in Legacy: ${error.message}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ uid, ...data }) => legacyService.updateSubscriber(uid, data),
    onSuccess: () => {
      toast.success('Subscriber updated successfully in Legacy RDS');
      queryClient.invalidateQueries(['legacy-subscribers']);
      setEditDialogOpen(false);
      resetForm();
    },
    onError: (error) => {
      toast.error(`Failed to update in Legacy: ${error.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: legacyService.deleteSubscriber,
    onSuccess: () => {
      toast.success('Subscriber deleted successfully from Legacy RDS');
      queryClient.invalidateQueries(['legacy-subscribers']);
      setDeleteDialogOpen(false);
      setSelectedSubscriber(null);
    },
    onError: (error) => {
      toast.error(`Failed to delete from Legacy: ${error.message}`);
    },
  });

  // DataGrid columns (same as Cloud but with legacy indicators)
  const columns = [
    {
      field: 'uid',
      headerName: 'UID',
      width: 120,
      filterable: true,
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
            variant="outlined"
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
      field: 'firstName',
      headerName: 'First Name',
      width: 120,
      filterable: true,
    },
    {
      field: 'lastName',
      headerName: 'Last Name',
      width: 120,
      filterable: true,
    },
    {
      field: 'createdAt',
      headerName: 'Created',
      width: 140,
      valueFormatter: (params) => {
        return params.value ? format(new Date(params.value), 'MMM dd, yyyy') : '';
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <Stack direction="row" spacing={1}>
          <Tooltip title="Edit">
            <IconButton size="small" onClick={() => handleEdit(params.row)}>
              <Edit />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete">
            <IconButton size="small" color="error" onClick={() => handleDelete(params.row)}>
              <Delete />
            </IconButton>
          </Tooltip>
        </Stack>
      ),
    },
  ];

  // Event handlers (same as Cloud)
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
    setPaginationModel(prev => ({ ...prev, page: 0 })); // Reset to first page
  };

  const clearFilters = () => {
    setFilters({ status: '', planId: '', search: '' });
    setPaginationModel(prev => ({ ...prev, page: 0 }));
  };

  const subscribers = data?.data?.subscribers || [];
  const totalCount = data?.data?.pagination?.count || 0;

  return (
    <Box sx={{ p: 3 }}>
      {/* Header with Legacy Warning */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <Database color="warning" sx={{ fontSize: 32 }} />
          <Typography variant="h4">Legacy Subscribers (RDS MySQL)</Typography>
          <Chip label="LEGACY MODE" color="warning" variant="outlined" />
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            color="warning"
            startIcon={<Add />}
            onClick={handleCreate}
          >
            Add to Legacy
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

      {/* Legacy System Warning */}
      <Alert severity="warning" sx={{ mb: 3 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Warning />
          <Box>
            <Typography variant="body1" fontWeight="bold">
              Legacy RDS MySQL System
            </Typography>
            <Typography variant="body2">
              Operations on this system may be slower. Large datasets should use bulk operations.
              Changes here affect the legacy MySQL database directly.
            </Typography>
          </Box>
        </Stack>
      </Alert>

      {/* Filters */}
      <Card sx={{ mb: 3, border: '1px solid', borderColor: 'warning.main' }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={2} mb={2}>
            <FilterList />
            <Typography variant="h6">Legacy Filters</Typography>
            <Chip size="small" label="MySQL Query" color="warning" variant="outlined" />
          </Stack>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
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
            <Grid item xs={12} sm={6} md={3}>
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
                helperText="Searches MySQL LIKE queries"
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
          Failed to load Legacy subscribers: {error.message}
          <br />
          <Typography variant="caption">
            Check RDS connectivity and Lambda VPC configuration.
          </Typography>
        </Alert>
      )}

      {/* Data Grid */}
      <Card sx={{ border: '1px solid', borderColor: 'warning.main' }}>
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
                backgroundColor: 'warning.light',
                color: 'warning.contrastText',
              },
            }}
          />
        </CardContent>
      </Card>

      {/* Bulk Actions for Legacy */}
      {selectedRows.length > 0 && (
        <Card sx={{ mt: 2, bgcolor: 'warning.light', border: '1px solid', borderColor: 'warning.main' }}>
          <CardContent>
            <Stack direction="row" alignItems="center" justifyContent="space-between">
              <Stack direction="row" alignItems="center" spacing={1}>
                <Warning color="warning" />
                <Typography variant="body1">
                  {selectedRows.length} legacy subscriber(s) selected
                </Typography>
              </Stack>
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  startIcon={<Edit />}
                >
                  Bulk Edit Legacy
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  startIcon={<Delete />}
                >
                  Bulk Delete Legacy
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<Download />}
                >
                  Export Selected
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Database color="warning" />
            <span>Create Legacy Subscriber</span>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Creating subscriber in Legacy RDS MySQL database.
          </Alert>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                required
                fullWidth
                label="UID"
                value={formData.uid}
                onChange={(e) => setFormData(prev => ({ ...prev, uid: e.target.value }))}
                helperText="Unique identifier (VARCHAR 64)"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                required
                fullWidth
                label="MSISDN"
                value={formData.msisdn}
                onChange={(e) => setFormData(prev => ({ ...prev, msisdn: e.target.value }))}
                helperText="Mobile number (must be unique)"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                required
                fullWidth
                label="IMSI"
                value={formData.imsi}
                onChange={(e) => setFormData(prev => ({ ...prev, imsi: e.target.value }))}
                helperText="SIM identifier (must be unique)"
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
            color="warning"
            disabled={createMutation.isLoading || !formData.uid || !formData.msisdn || !formData.imsi}
          >
            {createMutation.isLoading ? 'Creating in Legacy...' : 'Create in Legacy'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Edit />
            <span>Edit Legacy Subscriber</span>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            Updating subscriber in Legacy RDS MySQL database.
          </Alert>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="UID"
                value={formData.uid}
                disabled
                helperText="UID cannot be changed in Legacy"
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
            color="warning"
            disabled={updateMutation.isLoading}
          >
            {updateMutation.isLoading ? 'Updating Legacy...' : 'Update Legacy'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle color="error">
          <Stack direction="row" alignItems="center" spacing={1}>
            <Delete color="error" />
            <span>Confirm Legacy Delete</span>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete subscriber <strong>{selectedSubscriber?.uid}</strong> from Legacy RDS MySQL?
          </Typography>
          <Alert severity="error" sx={{ mt: 2 }}>
            This action cannot be undone. The record will be permanently removed from the legacy database.
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
            {deleteMutation.isLoading ? 'Deleting from Legacy...' : 'Delete from Legacy'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default LegacyCrud;