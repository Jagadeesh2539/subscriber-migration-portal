import React, { useState, useEffect, useCallback } from 'react';
import { 
    Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
    TableContainer, TableHead, TableRow, Alert, Box, Chip, IconButton,
    Checkbox, FormControlLabel, Tabs, Tab, Card, CircularProgress, TextField,
    Snackbar, Tooltip, Select, MenuItem, FormControl, InputLabel, Dialog,
    DialogTitle, DialogContent, DialogActions, Grid, Divider
} from '@mui/material';
import { 
    CloudUpload, Download, Assessment, FileDownload, ContentCopy, Cancel,
    FileCopy, Delete, Audit, GetApp, Dashboard, Warning, CheckCircle
} from '@mui/icons-material';
import API from '../api';

// Enhanced Bulk Operations Tool with multi-operation support
const EnhancedBulkOperations = ({ operationType = 'MIGRATION', jobs, setJobs, userRole, uploading, setUploading, setMessage }) => {
  const [file, setFile] = useState(null);
  const [isSimulateMode, setIsSimulateMode] = useState(false);
  const [copySuccess, setCopySuccess] = useState('');
  const [copyDialogOpen, setCopyDialogOpen] = useState(false);
  const [jobToCopy, setJobToCopy] = useState(null);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [jobToCancel, setJobToCancel] = useState(null);
  const [operationMode, setOperationMode] = useState('CLOUD');
  const [auditScope, setAuditScope] = useState('FULL');
  const [exportScope, setExportScope] = useState('CLOUD');
  const [exportFilters, setExportFilters] = useState({});

  const isAuthorized = userRole === 'admin';

  // Operation configuration
  const operationConfig = {
    'MIGRATION': {
      title: 'Bulk Migration',
      description: 'Migrate subscribers from Legacy to Cloud system',
      endpoint: '/migration/bulk',
      icon: <CloudUpload />,
      requiresFile: true,
      color: 'primary'
    },
    'BULK_DELETE': {
      title: 'Bulk Deletion',
      description: 'Delete multiple subscribers from Cloud system',
      endpoint: '/operations/bulk-delete',
      icon: <Delete />,
      requiresFile: true,
      color: 'error'
    },
    'BULK_AUDIT': {
      title: 'Bulk Audit',
      description: 'Compare Legacy vs Cloud subscriber data',
      endpoint: '/operations/bulk-audit',
      icon: <Audit />,
      requiresFile: true,
      color: 'info'
    },
    'DATA_EXPORT': {
      title: 'Data Export',
      description: 'Export subscriber data with filters',
      endpoint: '/operations/data-export',
      icon: <GetApp />,
      requiresFile: false,
      color: 'success'
    }
  };

  const config = operationConfig[operationType] || operationConfig['MIGRATION'];

  const handleOperation = async () => {
    if (config.requiresFile && !file) {
      setMessage({ type: 'error', text: 'Please select a CSV file first.' });
      return;
    }
    
    setUploading(true);
    setMessage({ type: 'info', text: `Starting ${config.title.toLowerCase()}...` });

    try {
      const requestBody = {
        isSimulateMode,
        mode: operationMode,
        ...(operationType === 'BULK_AUDIT' && { auditScope }),
        ...(operationType === 'DATA_EXPORT' && { 
          scope: exportScope,
          filters: exportFilters
        })
      };

      const { data } = await API.post(config.endpoint, requestBody);
      
      if (operationType === 'DATA_EXPORT') {
        // Data export starts immediately
        const newJob = {
          JobId: data.jobId,
          type: operationType,
          status: 'IN_PROGRESS',
          created: new Date().toISOString(),
          mode: exportScope,
          statusMessage: `Exporting ${exportScope} data...`,
          totalRecords: 0, migrated: 0, failed: 0,
          percentage: 0, isSimulateMode: false
        };
        
        setJobs(prevJobs => [newJob, ...(prevJobs || [])]);
        setMessage({ type: 'success', text: `Data export started! Job ${data.jobId.substring(0,8)}...` });
      } else {
        // File upload required
        const { jobId, uploadUrl } = data;
        setMessage({ type: 'info', text: 'Uploading file to S3...' });
        
        const uploadResponse = await fetch(uploadUrl, {
          method: 'PUT',
          headers: { 'Content-Type': 'text/csv' },
          body: file,
        });

        if (!uploadResponse.ok) {
          throw new Error(`S3 Upload Failed: ${uploadResponse.status}`);
        }

        const newJob = {
          JobId: jobId,
          type: operationType,
          status: 'PENDING_UPLOAD',
          created: new Date().toISOString(),
          fileName: file.name,
          mode: operationMode,
          isSimulateMode,
          statusMessage: `${config.title} job created - processing will start shortly`,
          totalRecords: 0, migrated: 0, failed: 0, deleted: 0, audited: 0,
          percentage: 0, failureReason: ''
        };

        setJobs(prevJobs => [newJob, ...(prevJobs || [])]);
        
        const displayId = jobId ? jobId.substring(0,8) : 'unknown';
        setMessage({ type: 'success', text: `${config.title} started! Job ${displayId}...` });
        
        setTimeout(() => setFile(null), 1000);
      }

    } catch (err) {
      console.error(`${config.title} failed:`, err);
      setMessage({ 
        type: 'error', 
        text: err.response?.data?.error || err.message || `Failed to start ${config.title.toLowerCase()}` 
      });
    } finally {
      setUploading(false);
    }
  };

  // Cancel job functionality
  const handleCancelJob = async (jobId) => {
    if (!jobId) return;
    
    try {
      setMessage({ type: 'info', text: `Canceling job ${jobId.substring(0,8)}...` });
      
      const response = await API.post(`/jobs/${jobId}/cancel`);
      
      if (response.data.success) {
        // Update job status locally
        setJobs(current => current.map(j => {
          const id = j.JobId || j.migrationId;
          if (id === jobId) {
            return { 
              ...j, 
              status: 'CANCELED', 
              statusMessage: 'Canceled by user request',
              failureReason: 'User-requested cancellation',
              lastUpdated: new Date().toISOString()
            };
          }
          return j;
        }));
        
        setMessage({ type: 'success', text: `Job ${jobId.substring(0,8)} canceled successfully` });
      } else {
        throw new Error(response.data.error || 'Cancel failed');
      }
    } catch (error) {
      console.error('Cancel job error:', error);
      setMessage({ 
        type: 'error', 
        text: `Failed to cancel job: ${error.response?.data?.error || error.message}` 
      });
    }
    
    setCancelDialogOpen(false);
    setJobToCancel(null);
  };

  // Copy job functionality
  const handleCopyJob = async (sourceJob) => {
    if (!sourceJob || !sourceJob.JobId) return;
    
    try {
      setMessage({ type: 'info', text: `Copying job ${sourceJob.JobId.substring(0,8)}...` });
      
      const response = await API.post(`/jobs/${sourceJob.JobId}/copy`);
      
      if (response.data.success) {
        const { newJobId, uploadUrl } = response.data;
        
        // Add copied job to list
        const copiedJob = {
          JobId: newJobId,
          type: sourceJob.type,
          status: 'PENDING_UPLOAD',
          created: new Date().toISOString(),
          mode: sourceJob.mode,
          isSimulateMode: sourceJob.isSimulateMode,
          statusMessage: `Copied from ${sourceJob.JobId.substring(0,8)}...`,
          copiedFromJobId: sourceJob.JobId,
          totalRecords: 0, migrated: 0, failed: 0,
          percentage: 0, uploadUrl
        };
        
        setJobs(prevJobs => [copiedJob, ...(prevJobs || [])]);
        setMessage({ type: 'success', text: `Job copied! New Job ID: ${newJobId.substring(0,8)}...` });
      }
    } catch (error) {
      setMessage({ 
        type: 'error', 
        text: `Failed to copy job: ${error.response?.data?.error || error.message}` 
      });
    }
    
    setCopyDialogOpen(false);
    setJobToCopy(null);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'COMPLETED': return 'success';
      case 'FAILED': return 'error';
      case 'CANCELED': return 'warning';
      case 'IN_PROGRESS': return 'info';
      case 'PENDING_UPLOAD': return 'default';
      default: return 'default';
    }
  };
  
  const getStatusIcon = (status) => {
    switch (status) {
      case 'COMPLETED': return <CheckCircle />;
      case 'FAILED': return <Warning />;
      case 'CANCELED': return <Cancel />;
      default: return null;
    }
  };

  const calculateProgress = (job) => {
    if (!job || job.status === 'PENDING_UPLOAD') return 0;
    if (job.status === 'COMPLETED') return 100;
    if (job.status === 'FAILED' || job.status === 'CANCELED') return job.percentage || 0;
    
    if (job.totalRecords && job.totalRecords > 0) {
      const processed = (job.migrated || 0) + (job.deleted || 0) + (job.audited || 0) + 
                       (job.alreadyPresent || 0) + (job.not_found_in_legacy || 0) + (job.failed || 0);
      return Math.max(0, Math.min(100, Math.round((processed / job.totalRecords) * 100)));
    }
    return job.percentage || 0;
  };

  // Enhanced clipboard with fallback
  const copyToClipboard = (jobId) => {
    if (!jobId) {
      setMessage({type: 'error', text: 'Invalid Job ID'});
      return;
    }
    
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      try {
        const textArea = document.createElement('textarea');
        textArea.value = jobId;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopySuccess(`Copied: ${jobId.substring(0, 8)}...`);
      } catch (error) {
        setMessage({type: 'error', text: 'Clipboard not supported'});
      }
      return;
    }
    
    navigator.clipboard.writeText(jobId).then(() => {
      setCopySuccess(`Copied: ${jobId.substring(0, 8)}...`);
    }).catch(() => {
      setMessage({type: 'error', text: 'Failed to copy Job ID'});
    });
  };

  const handleSnackbarClose = () => setCopySuccess('');

  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '2px solid', borderColor: `${config.color}.main`, pb: 1, display: 'flex', alignItems: 'center' }}>
        {config.icon}
        <Box sx={{ ml: 1 }}>{config.title}</Box>
      </Typography>

      <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
        {config.description}
      </Typography>

      {!isAuthorized && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          Only users with 'admin' role can perform {config.title.toLowerCase()} operations.
        </Alert>
      )}

      <Card variant="outlined" sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 3 }}>Configure {config.title}</Typography>
        
        {/* Operation Mode Selection */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          {(operationType !== 'DATA_EXPORT') && (
            <Grid item xs={12} md={6}>
              <FormControl fullWidth size="small">
                <InputLabel>Operation Mode</InputLabel>
                <Select value={operationMode} onChange={(e) => setOperationMode(e.target.value)} label="Operation Mode">
                  <MenuItem value="CLOUD">Cloud Mode</MenuItem>
                  <MenuItem value="LEGACY">Legacy Mode</MenuItem>
                  <MenuItem value="DUAL_PROV">Dual Provision Mode</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          )}
          
          {operationType === 'BULK_AUDIT' && (
            <Grid item xs={12} md={6}>
              <FormControl fullWidth size="small">
                <InputLabel>Audit Scope</InputLabel>
                <Select value={auditScope} onChange={(e) => setAuditScope(e.target.value)} label="Audit Scope">
                  <MenuItem value="FULL">Full Comparison</MenuItem>
                  <MenuItem value="METADATA">Metadata Only</MenuItem>
                  <MenuItem value="CRITICAL">Critical Fields</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          )}
          
          {operationType === 'DATA_EXPORT' && (
            <>
              <Grid item xs={12} md={6}>
                <FormControl fullWidth size="small">
                  <InputLabel>Data Source</InputLabel>
                  <Select value={exportScope} onChange={(e) => setExportScope(e.target.value)} label="Data Source">
                    <MenuItem value="CLOUD">Cloud Database</MenuItem>
                    <MenuItem value="LEGACY">Legacy Database</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth size="small" label="Export Filters (JSON)"
                  placeholder='{"status":"ACTIVE","plan":"4G"}'
                  value={JSON.stringify(exportFilters)}
                  onChange={(e) => {
                    try {
                      setExportFilters(JSON.parse(e.target.value || '{}'));
                    } catch {
                      // Keep previous valid filters
                    }
                  }}
                />
              </Grid>
            </>
          )}
        </Grid>
        
        {config.requiresFile && (
          <Box sx={{ mb: 3 }}>
            <Box display="flex" alignItems="center" gap={2} sx={{ mb: 2 }}>
              <input 
                type="file" accept=".csv" 
                onChange={e => setFile(e.target.files[0])} 
                style={{ display: 'none' }} 
                id="file-upload"
                key={file ? file.name : 'empty'}
              />
              <label htmlFor="file-upload">
                <Button variant="outlined" component="span" startIcon={<FileDownload />}>
                  Choose CSV File
                </Button>
              </label>
              
              <Typography variant="body2" sx={{ 
                flexGrow: 1, 
                color: file ? 'text.primary' : 'text.secondary',
                fontStyle: file ? 'normal' : 'italic'
              }}>
                {file ? file.name : 'Select CSV file with subscriber data'}
              </Typography>
            </Box>
            
            <FormControlLabel
              control={<Checkbox checked={isSimulateMode} onChange={(e) => setIsSimulateMode(e.target.checked)} disabled={!isAuthorized}/>}
              label="Simulate Mode (Dry Run) - No actual changes made"
            />
          </Box>
        )}
        
        <Button 
          variant="contained" color={config.color}
          startIcon={uploading ? <CircularProgress size={20} color="inherit" /> : config.icon} 
          onClick={handleOperation} 
          disabled={!isAuthorized || uploading || (config.requiresFile && !file)} 
          size="large"
        >
          {uploading ? 'Processing...' : `Start ${config.title}`}
        </Button>
      </Card>

      {/* Enhanced Jobs Table */}
      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
        <Dashboard sx={{ mr: 1 }} />
        Active & Recent {config.title} Jobs
      </Typography>
      
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { fontWeight: 'bold', backgroundColor: 'grey.50' } }}>
              <TableCell>Job ID</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Progress</TableCell>
              <TableCell>Mode</TableCell>
              <TableCell>Records</TableCell>
              <TableCell>Success</TableCell>
              <TableCell>Failed</TableCell>
              <TableCell>Created</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!jobs || jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="textSecondary">
                    No {config.title.toLowerCase()} jobs found. Create your first job above!
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              jobs.filter(job => !operationType || job.type === operationType || (operationType === 'MIGRATION' && !job.type)).map(job => {
                const jobId = job.JobId || job.migrationId || `unknown-${Math.random().toString(36).substr(2, 9)}`;
                const displayId = jobId ? jobId.substring(0, 8) : 'unknown';
                const canCancel = ['PENDING_UPLOAD', 'IN_PROGRESS'].includes(job.status);
                const canCopy = ['COMPLETED', 'FAILED', 'CANCELED'].includes(job.status);
                
                return (
                  <TableRow key={jobId} hover>
                    <TableCell>
                      <Box display="flex" alignItems="center">
                        <Tooltip title={jobId}>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            {displayId}...
                          </Typography>
                        </Tooltip>
                        <Tooltip title="Copy Job ID">
                          <IconButton size="small" onClick={() => copyToClipboard(jobId)} sx={{ ml: 0.5 }}>
                            <ContentCopy fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip label={job.type || 'MIGRATION'} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell>
                      <Box display="flex" alignItems="center">
                        {getStatusIcon(job.status)}
                        <Chip 
                          label={job.status || 'Unknown'} 
                          color={getStatusColor(job.status)} 
                          size="small" 
                          sx={{ ml: 0.5 }}
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      {job.status === 'IN_PROGRESS' ? (
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <LinearProgress 
                            variant="determinate" 
                            value={calculateProgress(job)} 
                            color={getStatusColor(job.status)}
                            sx={{ width: '80px', mr: 1 }}
                          />
                          <Typography variant="body2">{calculateProgress(job)}%</Typography>
                        </Box>
                      ) : job.status === 'COMPLETED' ? (
                        <Typography variant="body2" color="success.main">100%</Typography>
                      ) : job.status === 'FAILED' ? (
                        <Tooltip title={job.failureReason || 'Failed'}>
                          <Typography variant="body2" color="error.main">Failed</Typography>
                        </Tooltip>
                      ) : job.status === 'CANCELED' ? (
                        <Typography variant="body2" color="warning.main">Canceled</Typography>
                      ) : (
                        <Typography variant="body2" color="textSecondary">Pending</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip label={job.mode || 'CLOUD'} size="small" color="info" variant="outlined" />
                    </TableCell>
                    <TableCell>{job.totalRecords || '-'}</TableCell>
                    <TableCell>{job.migrated || job.deleted || job.audited || '-'}</TableCell>
                    <TableCell sx={{ color: (job.failed || 0) > 0 ? 'error.main' : 'inherit' }}>
                      {job.failed || '-'}
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="textSecondary">
                        {job.created ? new Date(job.created).toLocaleDateString() : '-'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box display="flex" gap={0.5}>
                        {canCancel && (
                          <Tooltip title="Cancel Job">
                            <IconButton 
                              size="small" color="error"
                              onClick={() => {
                                setJobToCancel(job);
                                setCancelDialogOpen(true);
                              }}
                            >
                              <Cancel fontSize="inherit" />
                            </IconButton>
                          </Tooltip>
                        )}
                        
                        {canCopy && (
                          <Tooltip title="Copy Job">
                            <IconButton 
                              size="small" color="info"
                              onClick={() => {
                                setJobToCopy(job);
                                setCopyDialogOpen(true);
                              }}
                            >
                              <FileCopy fontSize="inherit" />
                            </IconButton>
                          </Tooltip>
                        )}
                        
                        {job.status === 'COMPLETED' && job.reportS3Key && (
                          <Tooltip title="Download Report">
                            <IconButton size="small" color="success">
                              <Download fontSize="inherit" />
                            </IconButton>
                          </Tooltip>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Cancel Confirmation Dialog */}
      <Dialog open={cancelDialogOpen} onClose={() => setCancelDialogOpen(false)}>
        <DialogTitle>Cancel Job</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to cancel job <strong>{jobToCancel?.JobId?.substring(0,8)}...</strong>?
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
            This action cannot be undone. The job will be marked as canceled.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelDialogOpen(false)}>Keep Job</Button>
          <Button onClick={() => handleCancelJob(jobToCancel?.JobId)} color="error" variant="contained">
            Cancel Job
          </Button>
        </DialogActions>
      </Dialog>

      {/* Copy Confirmation Dialog */}
      <Dialog open={copyDialogOpen} onClose={() => setCopyDialogOpen(false)}>
        <DialogTitle>Copy Job</DialogTitle>
        <DialogContent>
          <Typography>
            Create a copy of job <strong>{jobToCopy?.JobId?.substring(0,8)}...</strong>?
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
            A new job will be created with the same configuration. You'll need to upload a new CSV file.
          </Typography>
          {jobToCopy && (
            <Box sx={{ mt: 2, p: 2, backgroundColor: 'grey.50', borderRadius: 1 }}>
              <Typography variant="body2"><strong>Type:</strong> {jobToCopy.type}</Typography>
              <Typography variant="body2"><strong>Mode:</strong> {jobToCopy.mode}</Typography>
              <Typography variant="body2"><strong>Simulate:</strong> {jobToCopy.isSimulateMode ? 'Yes' : 'No'}</Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCopyDialogOpen(false)}>Cancel</Button>
          <Button onClick={() => handleCopyJob(jobToCopy)} color="primary" variant="contained">
            Create Copy
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!copySuccess}
        autoHideDuration={3000}
        onClose={handleSnackbarClose}
        message={copySuccess}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  );
};

export default EnhancedBulkOperations;