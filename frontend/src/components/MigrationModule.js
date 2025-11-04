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
  LinearProgress,
  Tabs,
  Tab,
  Divider,
  CircularProgress,
  Tooltip,
  Badge,
  Stepper,
  Step,
  StepLabel,
  StepContent
} from '@mui/material';
import {
  CloudUpload,
  PlayArrow,
  Pause,
  Stop,
  Refresh,
  Download,
  Upload,
  FileCopy,
  CheckCircle,
  Error,
  Warning,
  Schedule,
  Visibility,
  Delete,
  CloudSync,
  DataUsage,
  Analytics
} from '@mui/icons-material';
import { api } from '../api/enhanced';

const MigrationModule = ({ user, onNotification, onStatsUpdate }) => {
  // State management
  const [activeTab, setActiveTab] = useState(0);
  const [migrationJobs, setMigrationJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [jobConfig, setJobConfig] = useState({
    name: '',
    description: '',
    priority: 'medium',
    schedule: 'immediate',
    source: 'legacy',
    destination: 'cloud',
    batchSize: 100,
    retryAttempts: 3
  });
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState({
    status: 'all',
    priority: 'all',
    source: 'all'
  });
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobDetailsOpen, setJobDetailsOpen] = useState(false);
  const [realTimeStats, setRealTimeStats] = useState({
    activeMigrations: 0,
    completedToday: 0,
    totalRecords: 0,
    successRate: 0
  });

  // Job status options
  const jobStatuses = ['pending', 'running', 'completed', 'failed', 'paused', 'cancelled'];
  const priorities = ['low', 'medium', 'high', 'critical'];
  const sources = ['legacy', 'cloud', 'external'];

  // Load migration jobs on component mount
  useEffect(() => {
    loadMigrationJobs();
    loadRealTimeStats();
    
    // Set up real-time updates
    const interval = setInterval(() => {
      loadRealTimeStats();
      loadMigrationJobs();
    }, 30000); // Update every 30 seconds
    
    return () => clearInterval(interval);
  }, [page, rowsPerPage, filters]);

  // Load migration jobs
  const loadMigrationJobs = async () => {
    try {
      setLoading(true);
      const params = {
        page: page + 1,
        limit: rowsPerPage,
        ...filters
      };
      
      const response = await api.getMigrationJobs(params);
      setMigrationJobs(response.jobs || []);
      setTotalCount(response.total || 0);
    } catch (error) {
      console.error('Error loading migration jobs:', error);
      onNotification('Error loading migration jobs: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Load real-time statistics
  const loadRealTimeStats = async () => {
    try {
      const stats = await api.getMigrationStats();
      setRealTimeStats(stats);
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  // Handle file upload
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (file && file.type === 'text/csv') {
      setSelectedFile(file);
    } else {
      onNotification('Please select a valid CSV file', 'error');
    }
  };

  // Submit migration job
  const submitMigrationJob = async () => {
    if (!selectedFile) {
      onNotification('Please select a CSV file', 'error');
      return;
    }

    try {
      setLoading(true);
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('config', JSON.stringify({
        ...jobConfig,
        created_by: user.username,
        created_timestamp: new Date().toISOString()
      }));
      
      const response = await api.submitMigrationJob(formData);
      onNotification(`Migration job created successfully. Job ID: ${response.job_id}`, 'success');
      
      setUploadDialogOpen(false);
      setSelectedFile(null);
      setJobConfig({
        name: '',
        description: '',
        priority: 'medium',
        schedule: 'immediate',
        source: 'legacy',
        destination: 'cloud',
        batchSize: 100,
        retryAttempts: 3
      });
      
      loadMigrationJobs();
      onStatsUpdate && onStatsUpdate();
    } catch (error) {
      console.error('Error submitting migration job:', error);
      onNotification('Error creating migration job: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Job control actions
  const controlJob = async (jobId, action) => {
    try {
      setLoading(true);
      await api.controlMigrationJob(jobId, action);
      onNotification(`Job ${action} successfully`, 'success');
      loadMigrationJobs();
    } catch (error) {
      console.error(`Error ${action} job:`, error);
      onNotification(`Error ${action} job: ` + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Copy job ID to clipboard
  const copyJobId = async (jobId) => {
    try {
      await navigator.clipboard.writeText(jobId);
      onNotification('Job ID copied to clipboard', 'success');
    } catch (error) {
      onNotification('Failed to copy job ID', 'error');
    }
  };

  // View job details
  const viewJobDetails = async (job) => {
    try {
      const details = await api.getMigrationJobDetails(job.job_id);
      setSelectedJob({ ...job, ...details });
      setJobDetailsOpen(true);
    } catch (error) {
      console.error('Error loading job details:', error);
      onNotification('Error loading job details: ' + error.message, 'error');
    }
  };

  // Get status color
  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'completed': return 'success';
      case 'running': return 'primary';
      case 'pending': return 'warning';
      case 'failed': return 'error';
      case 'paused': return 'default';
      case 'cancelled': return 'default';
      default: return 'default';
    }
  };

  // Get priority color
  const getPriorityColor = (priority) => {
    switch (priority?.toLowerCase()) {
      case 'critical': return 'error';
      case 'high': return 'warning';
      case 'medium': return 'primary';
      case 'low': return 'default';
      default: return 'default';
    }
  };

  // Format timestamp
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString();
  };

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary' }}>
          Migration Management
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Manage bulk migration operations between legacy and cloud systems
        </Typography>
      </Box>

      {/* Real-time Statistics */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <CloudSync sx={{ fontSize: 40, mr: 2 }} />
                <Box>
                  <Typography variant="h4" sx={{ fontWeight: 600 }}>
                    {realTimeStats.activeMigrations}
                  </Typography>
                  <Typography variant="body2">Active Migrations</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <CheckCircle sx={{ fontSize: 40, mr: 2 }} />
                <Box>
                  <Typography variant="h4" sx={{ fontWeight: 600 }}>
                    {realTimeStats.completedToday}
                  </Typography>
                  <Typography variant="body2">Completed Today</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <DataUsage sx={{ fontSize: 40, mr: 2 }} />
                <Box>
                  <Typography variant="h4" sx={{ fontWeight: 600 }}>
                    {realTimeStats.totalRecords?.toLocaleString() || '0'}
                  </Typography>
                  <Typography variant="body2">Total Records</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Analytics sx={{ fontSize: 40, mr: 2 }} />
                <Box>
                  <Typography variant="h4" sx={{ fontWeight: 600 }}>
                    {realTimeStats.successRate}%
                  </Typography>
                  <Typography variant="body2">Success Rate</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Action Bar */}
      <Card sx={{ mb: 3, p: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={4}>
            <Typography variant="h6" sx={{ fontWeight: 500 }}>
              Migration Jobs
            </Typography>
          </Grid>
          <Grid item xs={12} md={8}>
            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Status</InputLabel>
                <Select
                  value={filters.status}
                  label="Status"
                  onChange={(e) => setFilters(prev => ({ ...prev, status: e.target.value }))}
                >
                  <MenuItem value="all">All Status</MenuItem>
                  {jobStatuses.map(status => (
                    <MenuItem key={status} value={status}>
                      {status.charAt(0).toUpperCase() + status.slice(1)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Priority</InputLabel>
                <Select
                  value={filters.priority}
                  label="Priority"
                  onChange={(e) => setFilters(prev => ({ ...prev, priority: e.target.value }))}
                >
                  <MenuItem value="all">All Priority</MenuItem>
                  {priorities.map(priority => (
                    <MenuItem key={priority} value={priority}>
                      {priority.charAt(0).toUpperCase() + priority.slice(1)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={loadMigrationJobs}
                disabled={loading}
                size="small"
              >
                Refresh
              </Button>
              <Button
                variant="contained"
                startIcon={<CloudUpload />}
                onClick={() => setUploadDialogOpen(true)}
                disabled={loading}
                size="small"
              >
                New Migration
              </Button>
            </Box>
          </Grid>
        </Grid>
      </Card>

      {/* Migration Jobs Table */}
      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: 'grey.100' }}>
                <TableCell sx={{ fontWeight: 600 }}>Job ID</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Priority</TableCell>
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
                    <Typography variant="body2" sx={{ mt: 2 }}>Loading migration jobs...</Typography>
                  </TableCell>
                </TableRow>
              ) : migrationJobs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <CloudUpload sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="h6" color="text.secondary" gutterBottom>
                      No Migration Jobs
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Start your first migration by uploading a CSV file
                    </Typography>
                    <Button
                      variant="contained"
                      startIcon={<CloudUpload />}
                      onClick={() => setUploadDialogOpen(true)}
                      sx={{ mt: 2 }}
                    >
                      Create Migration Job
                    </Button>
                  </TableCell>
                </TableRow>
              ) : (
                migrationJobs.map((job) => (
                  <TableRow key={job.job_id} hover>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                          {job.job_id?.slice(-8) || 'N/A'}
                        </Typography>
                        <Tooltip title="Copy full Job ID">
                          <IconButton
                            size="small"
                            onClick={() => copyJobId(job.job_id)}
                          >
                            <FileCopy fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {job.name || 'Unnamed Job'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {job.description || 'No description'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={job.status || 'Unknown'} 
                        color={getStatusColor(job.status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={job.priority || 'Medium'} 
                        color={getPriorityColor(job.priority)}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress 
                          variant="determinate" 
                          value={job.progress || 0} 
                          sx={{ width: 60, height: 6, borderRadius: 3 }}
                        />
                        <Typography variant="body2" sx={{ minWidth: 40 }}>
                          {job.progress || 0}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatTimestamp(job.created_timestamp)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 0.5 }}>
                        <Tooltip title="View Details">
                          <IconButton 
                            size="small" 
                            color="primary"
                            onClick={() => viewJobDetails(job)}
                          >
                            <Visibility fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        {job.status === 'running' ? (
                          <Tooltip title="Pause Job">
                            <IconButton 
                              size="small" 
                              color="warning"
                              onClick={() => controlJob(job.job_id, 'pause')}
                            >
                              <Pause fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        ) : job.status === 'paused' ? (
                          <Tooltip title="Resume Job">
                            <IconButton 
                              size="small" 
                              color="success"
                              onClick={() => controlJob(job.job_id, 'resume')}
                            >
                              <PlayArrow fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        ) : null}
                        {['pending', 'running', 'paused'].includes(job.status) && (
                          <Tooltip title="Stop Job">
                            <IconButton 
                              size="small" 
                              color="error"
                              onClick={() => controlJob(job.job_id, 'stop')}
                            >
                              <Stop fontSize="small" />
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

      {/* Upload Dialog */}
      <Dialog open={uploadDialogOpen} onClose={() => setUploadDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          Create New Migration Job
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Upload a CSV file to start a new migration job. The file should contain subscriber data to be migrated.
              </Typography>
            </Grid>
            
            {/* File Upload */}
            <Grid item xs={12}>
              <Card sx={{ p: 3, border: '2px dashed', borderColor: 'primary.light', textAlign: 'center' }}>
                <CloudUpload sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  {selectedFile ? selectedFile.name : 'Select CSV File'}
                </Typography>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {selectedFile ? 
                    `File size: ${(selectedFile.size / 1024 / 1024).toFixed(2)} MB` :
                    'Drag and drop a CSV file here, or click to browse'
                  }
                </Typography>
                <input
                  accept=".csv"
                  style={{ display: 'none' }}
                  id="csv-upload"
                  type="file"
                  onChange={handleFileUpload}
                />
                <label htmlFor="csv-upload">
                  <Button component="span" variant="outlined" sx={{ mt: 1 }}>
                    {selectedFile ? 'Change File' : 'Browse Files'}
                  </Button>
                </label>
              </Card>
            </Grid>
            
            {/* Job Configuration */}
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Job Name"
                value={jobConfig.name}
                onChange={(e) => setJobConfig(prev => ({ ...prev, name: e.target.value }))}
                required
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Priority</InputLabel>
                <Select
                  value={jobConfig.priority}
                  label="Priority"
                  onChange={(e) => setJobConfig(prev => ({ ...prev, priority: e.target.value }))}
                >
                  {priorities.map(priority => (
                    <MenuItem key={priority} value={priority}>
                      {priority.charAt(0).toUpperCase() + priority.slice(1)}
                    </MenuItem>
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
                value={jobConfig.description}
                onChange={(e) => setJobConfig(prev => ({ ...prev, description: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Source System</InputLabel>
                <Select
                  value={jobConfig.source}
                  label="Source System"
                  onChange={(e) => setJobConfig(prev => ({ ...prev, source: e.target.value }))}
                >
                  <MenuItem value="legacy">Legacy System</MenuItem>
                  <MenuItem value="cloud">Cloud System</MenuItem>
                  <MenuItem value="external">External Source</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Destination System</InputLabel>
                <Select
                  value={jobConfig.destination}
                  label="Destination System"
                  onChange={(e) => setJobConfig(prev => ({ ...prev, destination: e.target.value }))}
                >
                  <MenuItem value="cloud">Cloud System</MenuItem>
                  <MenuItem value="legacy">Legacy System</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Batch Size"
                type="number"
                value={jobConfig.batchSize}
                onChange={(e) => setJobConfig(prev => ({ ...prev, batchSize: parseInt(e.target.value) }))}
                inputProps={{ min: 1, max: 1000 }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Retry Attempts"
                type="number"
                value={jobConfig.retryAttempts}
                onChange={(e) => setJobConfig(prev => ({ ...prev, retryAttempts: parseInt(e.target.value) }))}
                inputProps={{ min: 0, max: 10 }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={submitMigrationJob} 
            variant="contained" 
            disabled={loading || !selectedFile || !jobConfig.name}
            startIcon={loading ? <CircularProgress size={16} /> : <CloudUpload />}
          >
            {loading ? 'Creating...' : 'Create Migration Job'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Job Details Dialog */}
      <Dialog 
        open={jobDetailsOpen} 
        onClose={() => setJobDetailsOpen(false)} 
        maxWidth="lg" 
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="h6">
              Job Details: {selectedJob?.name || 'Unknown'}
            </Typography>
            <Chip 
              label={selectedJob?.status || 'Unknown'} 
              color={getStatusColor(selectedJob?.status)}
              size="small"
            />
          </Box>
        </DialogTitle>
        <DialogContent>
          {selectedJob && (
            <Grid container spacing={3}>
              {/* Job Information */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Job Information</Typography>
                <Table size="small">
                  <TableBody>
                    <TableRow>
                      <TableCell><strong>Job ID:</strong></TableCell>
                      <TableCell sx={{ fontFamily: 'monospace' }}>{selectedJob.job_id}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Priority:</strong></TableCell>
                      <TableCell>
                        <Chip 
                          label={selectedJob.priority} 
                          color={getPriorityColor(selectedJob.priority)}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Created:</strong></TableCell>
                      <TableCell>{formatTimestamp(selectedJob.created_timestamp)}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Created By:</strong></TableCell>
                      <TableCell>{selectedJob.created_by || 'Unknown'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Source:</strong></TableCell>
                      <TableCell>{selectedJob.source || 'Legacy'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Destination:</strong></TableCell>
                      <TableCell>{selectedJob.destination || 'Cloud'}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Grid>
              
              {/* Progress Information */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Progress Details</Typography>
                <Box sx={{ mb: 2 }}>
                  <LinearProgress 
                    variant="determinate" 
                    value={selectedJob.progress || 0} 
                    sx={{ height: 10, borderRadius: 5 }}
                  />
                  <Typography variant="body2" sx={{ mt: 1, textAlign: 'center' }}>
                    {selectedJob.progress || 0}% Complete
                  </Typography>
                </Box>
                <Table size="small">
                  <TableBody>
                    <TableRow>
                      <TableCell><strong>Total Records:</strong></TableCell>
                      <TableCell>{selectedJob.total_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Processed:</strong></TableCell>
                      <TableCell>{selectedJob.processed_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Successful:</strong></TableCell>
                      <TableCell style={{ color: 'green' }}>{selectedJob.successful_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell><strong>Failed:</strong></TableCell>
                      <TableCell style={{ color: 'red' }}>{selectedJob.failed_records?.toLocaleString() || '0'}</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </Grid>
              
              {/* Description */}
              {selectedJob.description && (
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>Description</Typography>
                  <Typography variant="body2">{selectedJob.description}</Typography>
                </Grid>
              )}
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setJobDetailsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MigrationModule;