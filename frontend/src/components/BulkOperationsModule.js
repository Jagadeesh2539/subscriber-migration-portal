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
  Tabs,
  Tab,
  LinearProgress,
  CircularProgress,
  Tooltip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Badge
} from '@mui/material';
import {
  Delete,
  Compare,
  CloudUpload,
  Download,
  Refresh,
  PlayArrow,
  Warning,
  CheckCircle,
  Error,
  Schedule,
  Visibility,
  FileCopy,
  Assessment,
  FindDifferences,
  CloudSync,
  Storage,
  DeleteSweep
} from '@mui/icons-material';
import { api } from '../api/enhanced';

const BulkOperationsModule = ({ user, onNotification, onStatsUpdate }) => {
  // State management
  const [activeTab, setActiveTab] = useState(0);
  const [operations, setOperations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState({
    operation_type: 'all',
    status: 'all',
    system: 'all'
  });
  
  // Dialog states
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = useState(false);
  const [bulkAuditDialogOpen, setBulkAuditDialogOpen] = useState(false);
  const [operationDetailsOpen, setOperationDetailsOpen] = useState(false);
  const [selectedOperation, setSelectedOperation] = useState(null);
  
  // Form states
  const [deleteFile, setDeleteFile] = useState(null);
  const [deleteConfig, setDeleteConfig] = useState({
    name: '',
    description: '',
    system: 'cloud',
    confirmDelete: false,
    batchSize: 50
  });
  
  const [auditConfig, setAuditConfig] = useState({
    name: '',
    description: '',
    auditType: 'full_comparison',
    includeData: true,
    includeMetadata: true
  });
  
  const [auditResults, setAuditResults] = useState(null);
  const [auditProgress, setAuditProgress] = useState(0);

  // Operation types and statuses
  const operationTypes = {
    'bulk_delete': { label: 'Bulk Delete', icon: <Delete />, color: 'error' },
    'bulk_audit': { label: 'Bulk Audit', icon: <Compare />, color: 'info' },
    'data_sync': { label: 'Data Sync', icon: <CloudSync />, color: 'primary' }
  };
  
  const systems = ['cloud', 'legacy', 'both'];
  const statuses = ['pending', 'running', 'completed', 'failed', 'cancelled'];
  const auditTypes = {
    'full_comparison': 'Full Data Comparison',
    'count_check': 'Record Count Check',
    'sample_audit': 'Sample Data Audit',
    'metadata_check': 'Metadata Validation'
  };

  // Load operations on component mount
  useEffect(() => {
    loadOperations();
  }, [page, rowsPerPage, filters, activeTab]);

  // Load bulk operations
  const loadOperations = async () => {
    try {
      setLoading(true);
      const params = {
        page: page + 1,
        limit: rowsPerPage,
        tab: activeTab, // 0: All, 1: Delete, 2: Audit
        ...filters
      };
      
      const response = await api.getBulkOperations(params);
      setOperations(response.operations || []);
      setTotalCount(response.total || 0);
    } catch (error) {
      console.error('Error loading operations:', error);
      onNotification('Error loading operations: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Handle bulk delete file upload
  const handleDeleteFileUpload = (event) => {
    const file = event.target.files[0];
    if (file && file.type === 'text/csv') {
      setDeleteFile(file);
    } else {
      onNotification('Please select a valid CSV file', 'error');
    }
  };

  // Submit bulk delete operation
  const submitBulkDelete = async () => {
    if (!deleteFile) {
      onNotification('Please select a CSV file with subscriber IDs', 'error');
      return;
    }

    if (!deleteConfig.confirmDelete) {
      onNotification('Please confirm the delete operation', 'error');
      return;
    }

    try {
      setLoading(true);
      const formData = new FormData();
      formData.append('file', deleteFile);
      formData.append('config', JSON.stringify({
        ...deleteConfig,
        operation_type: 'bulk_delete',
        created_by: user.username,
        created_timestamp: new Date().toISOString()
      }));
      
      const response = await api.submitBulkOperation(formData);
      onNotification(`Bulk delete operation created. Operation ID: ${response.operation_id}`, 'success');
      
      setBulkDeleteDialogOpen(false);
      resetDeleteForm();
      loadOperations();
      onStatsUpdate && onStatsUpdate();
    } catch (error) {
      console.error('Error submitting bulk delete:', error);
      onNotification('Error creating bulk delete operation: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Submit bulk audit operation
  const submitBulkAudit = async () => {
    try {
      setLoading(true);
      const config = {
        ...auditConfig,
        operation_type: 'bulk_audit',
        created_by: user.username,
        created_timestamp: new Date().toISOString()
      };
      
      const response = await api.submitBulkAudit(config);
      onNotification(`Bulk audit operation created. Operation ID: ${response.operation_id}`, 'success');
      
      setBulkAuditDialogOpen(false);
      resetAuditForm();
      loadOperations();
      
      // Start monitoring audit progress
      monitorAuditProgress(response.operation_id);
    } catch (error) {
      console.error('Error submitting bulk audit:', error);
      onNotification('Error creating bulk audit operation: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Monitor audit progress
  const monitorAuditProgress = async (operationId) => {
    const checkProgress = async () => {
      try {
        const progress = await api.getOperationProgress(operationId);
        setAuditProgress(progress.percentage || 0);
        
        if (progress.status === 'completed') {
          const results = await api.getAuditResults(operationId);
          setAuditResults(results);
          onNotification('Audit completed successfully', 'success');
        } else if (progress.status === 'failed') {
          onNotification('Audit operation failed', 'error');
        } else {
          setTimeout(checkProgress, 2000); // Check every 2 seconds
        }
      } catch (error) {
        console.error('Error checking progress:', error);
      }
    };
    
    checkProgress();
  };

  // Reset forms
  const resetDeleteForm = () => {
    setDeleteFile(null);
    setDeleteConfig({
      name: '',
      description: '',
      system: 'cloud',
      confirmDelete: false,
      batchSize: 50
    });
  };

  const resetAuditForm = () => {
    setAuditConfig({
      name: '',
      description: '',
      auditType: 'full_comparison',
      includeData: true,
      includeMetadata: true
    });
    setAuditResults(null);
    setAuditProgress(0);
  };

  // View operation details
  const viewOperationDetails = async (operation) => {
    try {
      const details = await api.getBulkOperationDetails(operation.operation_id);
      setSelectedOperation({ ...operation, ...details });
      setOperationDetailsOpen(true);
    } catch (error) {
      console.error('Error loading operation details:', error);
      onNotification('Error loading operation details: ' + error.message, 'error');
    }
  };

  // Download operation results
  const downloadResults = async (operationId, operationType) => {
    try {
      setLoading(true);
      const response = await api.downloadOperationResults(operationId);
      
      const blob = new Blob([response], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `${operationType}_results_${operationId}_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      
      onNotification('Results downloaded successfully', 'success');
    } catch (error) {
      console.error('Error downloading results:', error);
      onNotification('Error downloading results: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Copy operation ID
  const copyOperationId = async (operationId) => {
    try {
      await navigator.clipboard.writeText(operationId);
      onNotification('Operation ID copied to clipboard', 'success');
    } catch (error) {
      onNotification('Failed to copy operation ID', 'error');
    }
  };

  // Get status color
  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'completed': return 'success';
      case 'running': return 'primary';
      case 'pending': return 'warning';
      case 'failed': return 'error';
      case 'cancelled': return 'default';
      default: return 'default';
    }
  };

  // Format timestamp
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString();
  };

  // Tab panel component
  const TabPanel = ({ children, value, index, ...other }) => (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`bulk-ops-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary' }}>
          Bulk Operations
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Manage bulk deletion, audit operations, and data synchronization between systems
        </Typography>
      </Box>

      {/* Tabs */}
      <Card sx={{ mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(e, newValue) => setActiveTab(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="All Operations" />
          <Tab label="Bulk Delete" />
          <Tab label="Bulk Audit" />
        </Tabs>

        {/* Tab Panel 0: All Operations */}
        <TabPanel value={activeTab} index={0}>
          {/* Action Bar */}
          <Box sx={{ mb: 3, px: 3 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={6}>
                <Typography variant="h6" sx={{ fontWeight: 500 }}>
                  All Bulk Operations
                </Typography>
              </Grid>
              <Grid item xs={12} md={6}>
                <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Type</InputLabel>
                    <Select
                      value={filters.operation_type}
                      label="Type"
                      onChange={(e) => setFilters(prev => ({ ...prev, operation_type: e.target.value }))}
                    >
                      <MenuItem value="all">All Types</MenuItem>
                      <MenuItem value="bulk_delete">Bulk Delete</MenuItem>
                      <MenuItem value="bulk_audit">Bulk Audit</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Status</InputLabel>
                    <Select
                      value={filters.status}
                      label="Status"
                      onChange={(e) => setFilters(prev => ({ ...prev, status: e.target.value }))}
                    >
                      <MenuItem value="all">All Status</MenuItem>
                      {statuses.map(status => (
                        <MenuItem key={status} value={status}>
                          {status.charAt(0).toUpperCase() + status.slice(1)}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <Button
                    variant="outlined"
                    startIcon={<Refresh />}
                    onClick={loadOperations}
                    disabled={loading}
                    size="small"
                  >
                    Refresh
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </Box>
        </TabPanel>

        {/* Tab Panel 1: Bulk Delete */}
        <TabPanel value={activeTab} index={1}>
          <Box sx={{ px: 3 }}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card sx={{ p: 3, height: '100%', background: 'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Delete sx={{ fontSize: 40, color: 'white', mr: 2 }} />
                    <Typography variant="h5" sx={{ fontWeight: 600, color: 'white' }}>
                      Bulk Delete
                    </Typography>
                  </Box>
                  <Typography variant="body1" sx={{ mb: 3, color: 'white' }}>
                    Delete multiple subscribers from cloud systems using CSV file with subscriber IDs.
                  </Typography>
                  <Button
                    variant="contained"
                    size="large"
                    startIcon={<CloudUpload />}
                    onClick={() => setBulkDeleteDialogOpen(true)}
                    sx={{ 
                      bgcolor: 'white', 
                      color: 'error.main',
                      '&:hover': { bgcolor: 'grey.100' }
                    }}
                  >
                    Start Bulk Delete
                  </Button>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card sx={{ p: 2 }}>
                  <Typography variant="h6" gutterBottom>Recent Delete Operations</Typography>
                  <List>
                    {operations
                      .filter(op => op.operation_type === 'bulk_delete')
                      .slice(0, 3)
                      .map((op) => (
                        <ListItem key={op.operation_id} divider>
                          <ListItemIcon>
                            <Delete color="error" />
                          </ListItemIcon>
                          <ListItemText
                            primary={op.name || 'Unnamed Operation'}
                            secondary={`${formatTimestamp(op.created_timestamp)} - ${op.status}`}
                          />
                          <Chip 
                            label={op.status} 
                            color={getStatusColor(op.status)} 
                            size="small"
                          />
                        </ListItem>
                      ))
                    }
                    {operations.filter(op => op.operation_type === 'bulk_delete').length === 0 && (
                      <ListItem>
                        <ListItemText 
                          primary="No delete operations found" 
                          secondary="Start your first bulk delete operation"
                        />
                      </ListItem>
                    )}
                  </List>
                </Card>
              </Grid>
            </Grid>
          </Box>
        </TabPanel>

        {/* Tab Panel 2: Bulk Audit */}
        <TabPanel value={activeTab} index={2}>
          <Box sx={{ px: 3 }}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card sx={{ p: 3, height: '100%', background: 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Compare sx={{ fontSize: 40, color: 'white', mr: 2 }} />
                    <Typography variant="h5" sx={{ fontWeight: 600, color: 'white' }}>
                      Bulk Audit
                    </Typography>
                  </Box>
                  <Typography variant="body1" sx={{ mb: 3, color: 'white' }}>
                    Compare data between legacy and cloud systems to identify discrepancies and inconsistencies.
                  </Typography>
                  <Button
                    variant="contained"
                    size="large"
                    startIcon={<Assessment />}
                    onClick={() => setBulkAuditDialogOpen(true)}
                    sx={{ 
                      bgcolor: 'white', 
                      color: 'info.main',
                      '&:hover': { bgcolor: 'grey.100' }
                    }}
                  >
                    Start Bulk Audit
                  </Button>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card sx={{ p: 2 }}>
                  <Typography variant="h6" gutterBottom>Recent Audit Operations</Typography>
                  <List>
                    {operations
                      .filter(op => op.operation_type === 'bulk_audit')
                      .slice(0, 3)
                      .map((op) => (
                        <ListItem key={op.operation_id} divider>
                          <ListItemIcon>
                            <Compare color="info" />
                          </ListItemIcon>
                          <ListItemText
                            primary={op.name || 'Unnamed Operation'}
                            secondary={`${formatTimestamp(op.created_timestamp)} - ${op.status}`}
                          />
                          <Chip 
                            label={op.status} 
                            color={getStatusColor(op.status)} 
                            size="small"
                          />
                        </ListItem>
                      ))
                    }
                    {operations.filter(op => op.operation_type === 'bulk_audit').length === 0 && (
                      <ListItem>
                        <ListItemText 
                          primary="No audit operations found" 
                          secondary="Start your first bulk audit operation"
                        />
                      </ListItem>
                    )}
                  </List>
                </Card>
              </Grid>
            </Grid>
            
            {/* Audit Progress */}
            {auditProgress > 0 && auditProgress < 100 && (
              <Card sx={{ mt: 3, p: 2 }}>
                <Typography variant="h6" gutterBottom>Audit in Progress</Typography>
                <LinearProgress 
                  variant="determinate" 
                  value={auditProgress} 
                  sx={{ height: 10, borderRadius: 5, mb: 1 }}
                />
                <Typography variant="body2" color="text.secondary">
                  {auditProgress}% Complete
                </Typography>
              </Card>
            )}
            
            {/* Audit Results */}
            {auditResults && (
              <Card sx={{ mt: 3, p: 3 }}>
                <Typography variant="h6" gutterBottom>Latest Audit Results</Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={3}>
                    <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'success.light', color: 'white' }}>
                      <Typography variant="h4">{auditResults.totalRecords?.toLocaleString()}</Typography>
                      <Typography variant="body2">Total Records</Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'info.light', color: 'white' }}>
                      <Typography variant="h4">{auditResults.matchingRecords?.toLocaleString()}</Typography>
                      <Typography variant="body2">Matching</Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'warning.light', color: 'white' }}>
                      <Typography variant="h4">{auditResults.discrepancies?.toLocaleString()}</Typography>
                      <Typography variant="body2">Discrepancies</Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'error.light', color: 'white' }}>
                      <Typography variant="h4">{auditResults.errors?.toLocaleString()}</Typography>
                      <Typography variant="body2">Errors</Typography>
                    </Paper>
                  </Grid>
                </Grid>
              </Card>
            )}
          </Box>
        </TabPanel>
      </Card>

      {/* Operations Table */}
      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: 'grey.100' }}>
                <TableCell sx={{ fontWeight: 600 }}>Operation ID</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Type</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Progress</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Created</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <CircularProgress size={40} />
                    <Typography variant="body2" sx={{ mt: 2 }}>Loading operations...</Typography>
                  </TableCell>
                </TableRow>
              ) : operations.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <Assessment sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="h6" color="text.secondary" gutterBottom>
                      No Operations Found
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Start your first bulk operation using the tabs above
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                operations.map((operation) => (
                  <TableRow key={operation.operation_id} hover>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                          {operation.operation_id?.slice(-8) || 'N/A'}
                        </Typography>
                        <Tooltip title="Copy full Operation ID">
                          <IconButton
                            size="small"
                            onClick={() => copyOperationId(operation.operation_id)}
                          >
                            <FileCopy fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {operation.name || 'Unnamed Operation'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {operation.description || 'No description'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        icon={operationTypes[operation.operation_type]?.icon}
                        label={operationTypes[operation.operation_type]?.label || operation.operation_type} 
                        color={operationTypes[operation.operation_type]?.color || 'default'}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={operation.status || 'Unknown'} 
                        color={getStatusColor(operation.status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress 
                          variant="determinate" 
                          value={operation.progress || 0} 
                          sx={{ width: 60, height: 6, borderRadius: 3 }}
                        />
                        <Typography variant="body2" sx={{ minWidth: 40 }}>
                          {operation.progress || 0}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatTimestamp(operation.created_timestamp)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 0.5 }}>
                        <Tooltip title="View Details">
                          <IconButton 
                            size="small" 
                            color="primary"
                            onClick={() => viewOperationDetails(operation)}
                          >
                            <Visibility fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        {operation.status === 'completed' && (
                          <Tooltip title="Download Results">
                            <IconButton 
                              size="small" 
                              color="success"
                              onClick={() => downloadResults(operation.operation_id, operation.operation_type)}
                            >
                              <Download fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )}
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

      {/* Bulk Delete Dialog */}
      <Dialog open={bulkDeleteDialogOpen} onClose={() => setBulkDeleteDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ bgcolor: 'error.light', color: 'white' }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Delete sx={{ mr: 2 }} />
            Bulk Delete Operation
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mt: 2, mb: 3 }}>
            <strong>Warning:</strong> This operation will permanently delete subscribers from the selected system. 
            This action cannot be undone.
          </Alert>
          
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <Card sx={{ p: 3, border: '2px dashed', borderColor: 'error.light', textAlign: 'center' }}>
                <DeleteSweep sx={{ fontSize: 48, color: 'error.main', mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  {deleteFile ? deleteFile.name : 'Select CSV File'}
                </Typography>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {deleteFile ? 
                    `File size: ${(deleteFile.size / 1024 / 1024).toFixed(2)} MB` :
                    'Upload a CSV file with subscriber IDs to delete'
                  }
                </Typography>
                <input
                  accept=".csv"
                  style={{ display: 'none' }}
                  id="delete-csv-upload"
                  type="file"
                  onChange={handleDeleteFileUpload}
                />
                <label htmlFor="delete-csv-upload">
                  <Button component="span" variant="outlined" sx={{ mt: 1 }}>
                    {deleteFile ? 'Change File' : 'Browse Files'}
                  </Button>
                </label>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Operation Name"
                value={deleteConfig.name}
                onChange={(e) => setDeleteConfig(prev => ({ ...prev, name: e.target.value }))}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Target System</InputLabel>
                <Select
                  value={deleteConfig.system}
                  label="Target System"
                  onChange={(e) => setDeleteConfig(prev => ({ ...prev, system: e.target.value }))}
                >
                  <MenuItem value="cloud">Cloud System</MenuItem>
                  <MenuItem value="legacy">Legacy System</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                multiline
                rows={2}
                value={deleteConfig.description}
                onChange={(e) => setDeleteConfig(prev => ({ ...prev, description: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Batch Size"
                type="number"
                value={deleteConfig.batchSize}
                onChange={(e) => setDeleteConfig(prev => ({ ...prev, batchSize: parseInt(e.target.value) }))}
                inputProps={{ min: 1, max: 100 }}
              />
            </Grid>
            <Grid item xs={12}>
              <Alert severity="warning" sx={{ mt: 2 }}>
                <Typography variant="body2">
                  Please confirm that you understand this action will permanently delete the subscribers 
                  listed in the CSV file from the {deleteConfig.system} system.
                </Typography>
              </Alert>
              <Box sx={{ mt: 2 }}>
                <label>
                  <input
                    type="checkbox"
                    checked={deleteConfig.confirmDelete}
                    onChange={(e) => setDeleteConfig(prev => ({ ...prev, confirmDelete: e.target.checked }))}
                    style={{ marginRight: 8 }}
                  />
                  I understand and confirm this delete operation
                </label>
              </Box>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkDeleteDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={submitBulkDelete} 
            variant="contained" 
            color="error"
            disabled={loading || !deleteFile || !deleteConfig.name || !deleteConfig.confirmDelete}
            startIcon={loading ? <CircularProgress size={16} /> : <Delete />}
          >
            {loading ? 'Creating...' : 'Execute Bulk Delete'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Bulk Audit Dialog */}
      <Dialog open={bulkAuditDialogOpen} onClose={() => setBulkAuditDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ bgcolor: 'info.light', color: 'white' }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Compare sx={{ mr: 2 }} />
            Bulk Audit Operation
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mt: 2, mb: 3 }}>
            This operation will compare data between legacy and cloud systems to identify discrepancies.
          </Alert>
          
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Audit Name"
                value={auditConfig.name}
                onChange={(e) => setAuditConfig(prev => ({ ...prev, name: e.target.value }))}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Audit Type</InputLabel>
                <Select
                  value={auditConfig.auditType}
                  label="Audit Type"
                  onChange={(e) => setAuditConfig(prev => ({ ...prev, auditType: e.target.value }))}
                >
                  {Object.entries(auditTypes).map(([value, label]) => (
                    <MenuItem key={value} value={value}>{label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                multiline
                rows={2}
                value={auditConfig.description}
                onChange={(e) => setAuditConfig(prev => ({ ...prev, description: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <label>
                <input
                  type="checkbox"
                  checked={auditConfig.includeData}
                  onChange={(e) => setAuditConfig(prev => ({ ...prev, includeData: e.target.checked }))}
                  style={{ marginRight: 8 }}
                />
                Include data comparison
              </label>
            </Grid>
            <Grid item xs={12} md={6}>
              <label>
                <input
                  type="checkbox"
                  checked={auditConfig.includeMetadata}
                  onChange={(e) => setAuditConfig(prev => ({ ...prev, includeMetadata: e.target.checked }))}
                  style={{ marginRight: 8 }}
                />
                Include metadata validation
              </label>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBulkAuditDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={submitBulkAudit} 
            variant="contained" 
            color="info"
            disabled={loading || !auditConfig.name}
            startIcon={loading ? <CircularProgress size={16} /> : <Assessment />}
          >
            {loading ? 'Creating...' : 'Start Audit'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Operation Details Dialog */}
      <Dialog 
        open={operationDetailsOpen} 
        onClose={() => setOperationDetailsOpen(false)} 
        maxWidth="lg" 
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="h6">
              Operation Details: {selectedOperation?.name || 'Unknown'}
            </Typography>
            <Chip 
              label={selectedOperation?.status || 'Unknown'} 
              color={getStatusColor(selectedOperation?.status)}
              size="small"
            />
          </Box>
        </DialogTitle>
        <DialogContent>
          {selectedOperation && (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Operation Information</Typography>
                <Table size="small">
                  <TableBody>
                    <TableRow>
                      <TableCell><strong>Operation ID:</strong></TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{selectedOperation.operation_id}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Type:</strong></TableCell>
                      <TableCell>
                        <Chip 
                          icon={operationTypes[selectedOperation.operation_type]?.icon}
                          label={operationTypes[selectedOperation.operation_type]?.label || selectedOperation.operation_type} 
                          color={operationTypes[selectedOperation.operation_type]?.color || 'default'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Created:</strong></TableCell>
                      <TableCell>{formatTimestamp(selectedOperation.created_timestamp)}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Created By:</strong></TableCell>
                      <TableCell>{selectedOperation.created_by || 'Unknown'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>System:</strong></TableCell>
                      <TableCell>{selectedOperation.system || 'N/A'}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Progress Details</Typography>
                <Box sx={{ mb: 2 }}>
                  <LinearProgress 
                    variant="determinate" 
                    value={selectedOperation.progress || 0} 
                    sx={{ height: 10, borderRadius: 5 }}
                  />
                  <Typography variant="body2" sx={{ mt: 1, textAlign: 'center' }}>
                    {selectedOperation.progress || 0}% Complete
                  </Typography>
                </Box>
                <Table size="small">
                  <TableBody>
                    <TableRow>
                      <TableCell><strong>Total Records:</strong></TableCell>
                      <TableCell>{selectedOperation.total_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Processed:</strong></TableCell>
                      <TableCell>{selectedOperation.processed_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Successful:</strong></TableCell>
                      <TableCell style={{ color: 'green' }}>{selectedOperation.successful_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Failed:</strong></TableCell>
                      <TableCell style={{ color: 'red' }}>{selectedOperation.failed_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Grid>
              
              {selectedOperation.description && (
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>Description</Typography>
                  <Typography variant="body2">{selectedOperation.description}</Typography>
                </Grid>
              )}
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          {selectedOperation?.status === 'completed' && (
            <Button 
              startIcon={<Download />}
              onClick={() => downloadResults(selectedOperation.operation_id, selectedOperation.operation_type)}
            >
              Download Results
            </Button>
          )}
          <Button onClick={() => setOperationDetailsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default BulkOperationsModule;