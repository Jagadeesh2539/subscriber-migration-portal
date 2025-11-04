import React, { useState, useEffect, useCallback } from 'react';
import { 
    Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
    TableContainer, TableHead, TableRow, Alert, Box, Chip, IconButton,
    Checkbox, FormControlLabel, Tabs, Tab, Card, CircularProgress, TextField,
    Snackbar, Tooltip
} from '@mui/material';
import { 
    CloudUpload, Download, Assessment, FileDownload, ContentCopy 
} from '@mui/icons-material';
import API from '../api';

// --- Sub-Component for Bulk Upload Tab ---
const BulkUploadTool = ({ jobs, setJobs, userRole, uploading, setUploading, setMessage }) => {
  const [file, setFile] = useState(null);
  const [isSimulateMode, setIsSimulateMode] = useState(false);
  const [copySuccess, setCopySuccess] = useState('');

  const isAuthorized = userRole === 'admin';

  const handleUpload = async () => {
    if (!file) {
       setMessage({ type: 'error', text: 'Please select a CSV file first.' });
       return;
    }
    setUploading(true);
    setMessage({ type: 'info', text: 'Requesting secure upload URL...' });

    try {
      const { data } = await API.post('/migration/bulk', { 
          isSimulateMode: isSimulateMode 
      });
      
      const { migrationId, uploadUrl } = data;
      setMessage({ type: 'info', text: 'Uploading file securely to S3... This might take a moment.' });
      
      const uploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'text/csv'
        },
        body: file,
      });

      if (!uploadResponse.ok) {
        throw new Error(`S3 Upload Failed: Server responded with status ${uploadResponse.status}`);
      }

      // Add job with all expected fields and proper initialization
      const newJob = {
        JobId: migrationId,
        migrationId: migrationId, // Backward compatibility
        status: 'PENDING_UPLOAD',
        isSimulateMode, 
        startedBy: userRole,
        startedAt: new Date().toISOString(),
        fileName: file.name, // Store filename to prevent clearing
        // Initialize all expected fields to prevent undefined errors
        totalRecords: null,
        migrated: null,
        alreadyPresent: null,
        not_found_in_legacy: null,
        failed: null,
        reportS3Key: null,
        failureReason: null
      };

      setJobs(prevJobs => [newJob, ...(prevJobs || [])]);
      
      // FIX LINE 69: Add null check for migrationId
      const displayId = migrationId ? migrationId.substring(0,8) : 'unknown';
      setMessage({ type: 'success', text: `Upload successful! Job ${displayId}... processing will start shortly.` });
      
      // Don't clear file immediately to prevent UI flash
      setTimeout(() => setFile(null), 1000);

    } catch (err) {
      console.error("Migration start failed:", err);
      setMessage({ type: 'error', text: err.response?.data?.msg || err.message || 'Failed to start migration. Check console for details.' });
    } finally {
      setUploading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'COMPLETED': return 'success';
      case 'FAILED': return 'error';
      case 'IN_PROGRESS': return 'info';
      case 'PENDING_UPLOAD': return 'warning';
      default: return 'default';
    }
  };
  
  const calculateProgress = (job) => {
    if (!job || job.status === 'PENDING_UPLOAD') return 0;
    if (job.status === 'COMPLETED' || job.status === 'FAILED') return 100;
    
    if (job.totalRecords && job.totalRecords > 0 && job.status === 'IN_PROGRESS') {
      const processed = (job.migrated || 0) + (job.alreadyPresent || 0) + (job.not_found_in_legacy || 0) + (job.failed || 0);
      return Math.max(0, Math.min(100, Math.round((processed / job.totalRecords) * 100)));
    }
    return 0;
  };

  // Copy to clipboard functionality - FIX LINE 114
  const copyToClipboard = (jobId) => {
    // FIX: Add null check for jobId
    if (!jobId) {
      setMessage({type: 'error', text: 'Invalid Job ID'});
      return;
    }
    
    // FIX LINE 114: Add null check for navigator.clipboard
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      // Fallback for browsers without clipboard API
      try {
        const textArea = document.createElement('textarea');
        textArea.value = jobId;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        setCopySuccess(`Copied Job ID: ${jobId.substring(0, 8)}...`);
      } catch (fallbackError) {
        setMessage({type: 'error', text: 'Clipboard not supported in this browser'});
        console.error('Clipboard fallback failed:', fallbackError);
      }
      return;
    }
    
    navigator.clipboard.writeText(jobId).then(() => {
      setCopySuccess(`Copied Job ID: ${jobId.substring(0, 8)}...`);
    }, (err) => {
      setMessage({type: 'error', text: 'Failed to copy Job ID'});
      console.error('Clipboard copy failed:', err);
    });
  };

  const handleSnackbarClose = (event, reason) => {
    if (reason === 'clickaway') return;
    setCopySuccess('');
  };

  // Download report handler
  const handleDownloadReport = async (jobId) => {
    // FIX: Add null check for jobId
    if (!jobId) {
      setMessage({ type: 'error', text: 'Invalid Job ID for report download' });
      return;
    }
    
    const displayId = jobId.substring(0,8);
    setMessage({ type: 'info', text: `Requesting download URL for report ${displayId}...` });
    try {
      const { data } = await API.get(`/migration/report/${jobId}`);
      window.open(data.downloadUrl, '_blank');
      setTimeout(() => setMessage({ type: '', text: '' }), 2000);
    } catch (err) {
      setMessage({ 
        type: 'error', 
        text: err.response?.data?.msg || `Could not get report for Job ${displayId}.` 
      });
    }
  };

  return (
    <Box>
       <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '1px solid #ddd', pb: 1 }}>
        Bulk Subscriber Upload
      </Typography>

      {!isAuthorized && (
        <Alert severity="warning" sx={{ mb: 3 }}>Only users with the 'admin' role can initiate bulk migrations.</Alert>
      )}

      <Card variant="outlined" sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Upload Migration File</Typography>
        <Box display="flex" flexDirection={{ xs: 'column', md: 'row' }} alignItems="center" gap={2}>
          <input 
            type="file" 
            accept=".csv" 
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
            {file ? file.name : 'Select a CSV file (must contain uid, imsi, or msisdn header)'}
          </Typography>
        </Box>
        <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <FormControlLabel
               control={<Checkbox checked={isSimulateMode} onChange={(e) => setIsSimulateMode(e.target.checked)} disabled={!isAuthorized}/>}
               label="Run in Simulate Mode (Dry Run)"
            />
            <Button 
                variant="contained" 
                startIcon={uploading ? <CircularProgress size={24} color="inherit" /> : <CloudUpload />} 
                onClick={handleUpload} 
                disabled={!file || uploading || !isAuthorized} 
                color="primary"
                sx={{ flexShrink: 0 }}
            >
                {uploading ? 'Initializing...' : 'Start Migration Job'}
            </Button>
        </Box>
      </Card>

      <Typography variant="h6" sx={{ mb: 2 }}>Active & Recent Jobs</Typography>
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { fontWeight: 'bold' } }}>
              <TableCell>Job ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell sx={{ minWidth: 150 }}>Progress</TableCell>
              <TableCell>Simulate</TableCell>
              <TableCell>Total</TableCell>
              <TableCell>Migrated</TableCell>
              <TableCell>Skipped</TableCell>
              <TableCell>Failed</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!jobs || jobs.length === 0 ? (
              <TableRow><TableCell colSpan={9} align="center">No migration jobs found.</TableCell></TableRow>
            ) : (
              jobs.map(job => {
                // FIX LINE 215: Add null checks for jobId
                const jobId = job.JobId || job.migrationId || `job-${Math.random().toString(36).substr(2, 9)}`;
                const displayId = jobId ? jobId.substring(0, 8) : 'unknown';
                
                return (
                  <TableRow key={jobId} hover>
                    <TableCell>
                      <Box display="flex" alignItems="center">
                        <Tooltip title={jobId || 'Unknown Job ID'}>
                          <span>{displayId}...</span>
                        </Tooltip>
                        <Tooltip title="Copy full Job ID">
                          <IconButton 
                            size="small" 
                            onClick={() => copyToClipboard(jobId)} 
                            sx={{ ml: 0.5 }}
                            disabled={!jobId}
                          >
                            <ContentCopy fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip label={job.status || 'Unknown'} color={getStatusColor(job.status)} size="small" />
                    </TableCell>
                    <TableCell>
                      {(job.status === 'IN_PROGRESS' || job.status === 'COMPLETED') && job.totalRecords != null ? (
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Box sx={{ width: '100%', mr: 1 }}>
                              <LinearProgress variant="determinate" value={calculateProgress(job)} color={getStatusColor(job.status)}/>
                          </Box>
                          <Box sx={{ minWidth: 35 }}>
                              <Typography variant="body2" color="text.secondary">{`${calculateProgress(job)}%`}</Typography>
                          </Box>
                          </Box>
                      ) : job.status === 'PENDING_UPLOAD' ? (
                         <Typography variant="caption" color="textSecondary">Waiting for processing...</Typography>
                      ) : job.status === 'FAILED' ? (
                         <Tooltip title={job.failureReason || 'Failed with unknown error'}>
                           <Typography variant="caption" color="error">{job.failureReason || 'Failed'}</Typography>
                         </Tooltip>
                      ): (
                         <Typography variant="caption" color="textSecondary">{job.status || 'Unknown'}</Typography>
                      )}
                    </TableCell>
                    <TableCell>{job.isSimulateMode ? 'Yes' : 'No'}</TableCell>
                    <TableCell>{job.totalRecords ?? '-'}</TableCell>
                    <TableCell>{job.migrated ?? '-'}</TableCell>
                    <TableCell>{(job.alreadyPresent ?? 0) + (job.not_found_in_legacy ?? 0)}</TableCell>
                    <TableCell sx={{ 
                      color: (job.failed ?? 0) > 0 ? 'error.main' : 'inherit', 
                      fontWeight: (job.failed ?? 0) > 0 ? 'bold' : 'normal' 
                    }}>
                      {job.failed ?? '-'}
                    </TableCell>
                    <TableCell>
                      {(job.status === 'COMPLETED' || job.status === 'FAILED') && job.reportS3Key && (
                        <Tooltip title="Download Report">
                          <IconButton 
                            size="small" 
                            onClick={() => handleDownloadReport(jobId)}
                          >
                            <Download fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

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

// --- Sub-Component for Migration Reports Tab ---
const MigrationReports = ({ setMessage, jobs }) => {
  const [loadingReports] = useState(false);
  const [jobIdInput, setJobIdInput] = useState('');

  // Show completed jobs from current session
  const completedJobs = jobs ? jobs.filter(job => job.status === 'COMPLETED').slice(0, 10) : [];

  const handleDownloadReport = async (migrationId) => {
    if (!migrationId || !migrationId.trim()){
        setMessage({ type: 'warning', text: 'Please enter a valid Job ID.' });
        return;
    }
    
    // FIX: Add null check for migrationId before substring
    const displayId = migrationId ? migrationId.substring(0,8) : 'unknown';
    setMessage({ type: 'info', text: `Requesting download URL for report ${displayId}...` });
    
    try {
      const { data } = await API.get(`/migration/report/${migrationId.trim()}`);
      window.open(data.downloadUrl, '_blank');
      setTimeout(() => setMessage({ type: '', text: '' }), 2000);
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.msg || `Could not get report for Job ${displayId}.` });
    }
  };
  
  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '1px solid #ddd', pb: 1 }}>
        <Assessment sx={{ mr: 1 }} /> Migration Reports
      </Typography>
      
      <Card variant="outlined" sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Download Specific Job Report</Typography>
        <Box display="flex" alignItems="center" gap={2}>
            <TextField 
              label="Enter or Paste Completed Job ID" 
              fullWidth 
              size="small" 
              value={jobIdInput}
              onChange={(e) => setJobIdInput(e.target.value)}
            />
            <Button 
                variant="contained" 
                startIcon={<Download />} 
                onClick={() => handleDownloadReport(jobIdInput)}
                disabled={!jobIdInput.trim()}
                sx={{ whiteSpace: 'nowrap' }}
            >
                Get Report
            </Button>
        </Box>
      </Card>
      
      <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>Recent Completed Jobs (from this session)</Typography>
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { fontWeight: 'bold' } }}>
              <TableCell>Job ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Total Records</TableCell>
              <TableCell>Migrated</TableCell>
              <TableCell>Skipped</TableCell>
              <TableCell>Failures</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loadingReports ? (
              <TableRow><TableCell colSpan={7} align="center"><CircularProgress size={24} /></TableCell></TableRow>
            ) : completedJobs.length === 0 ? (
              <TableRow><TableCell colSpan={7} align="center">No completed jobs found in this session.</TableCell></TableRow>
            ) : (
              completedJobs.map((job) => {
                // FIX: Add null checks for jobId
                const jobId = job.JobId || job.migrationId || `job-${Math.random().toString(36).substr(2, 9)}`;
                const displayId = jobId ? jobId.substring(0, 8) : 'unknown';
                
                return (
                  <TableRow key={jobId} hover>
                    <TableCell>
                      <Tooltip title={jobId || 'Unknown Job ID'}>
                        <span>{displayId}...</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell><Chip label={job.status} color="success" size="small" /></TableCell>
                    <TableCell>{job.totalRecords ?? '-'}</TableCell>
                    <TableCell>{job.migrated ?? '-'}</TableCell>
                    <TableCell>{(job.alreadyPresent ?? 0) + (job.not_found_in_legacy ?? 0)}</TableCell>
                    <TableCell sx={{ 
                      color: (job.failed ?? 0) > 0 ? 'error.main' : 'inherit', 
                      fontWeight: (job.failed ?? 0) > 0 ? 'bold' : 'normal' 
                    }}>
                      {job.failed ?? 0}
                    </TableCell>
                    <TableCell>
                      {job.reportS3Key && (
                        <Tooltip title="Download Report">
                          <IconButton onClick={() => handleDownloadReport(jobId)} size="small">
                            <Download fontSize="inherit"/>
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

// --- Main Component for the Migration Page ---
export default function BulkMigration() {
  const [activeTab, setActiveTab] = useState(0);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [uploading, setUploading] = useState(false);
  
  // Initialize jobs from localStorage with error handling
  const [jobs, setJobs] = useState(() => {
    try {
      const storedJobs = localStorage.getItem('migrationJobs');
      const parsed = storedJobs ? JSON.parse(storedJobs) : [];
      console.log('[Init] Loaded jobs from localStorage:', parsed.length, 'jobs');
      return parsed;
    } catch (e) {
      console.error("[Init] Failed to parse stored jobs, initializing empty:", e);
      localStorage.removeItem('migrationJobs');
      return [];
    }
  });
  
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userRole = user.role || 'guest';
  
  // Fetch recent jobs from backend API
  const fetchRecentJobs = useCallback(async () => {
    try {
      console.log('[API] Fetching recent jobs from backend...');
      const { data } = await API.get('/migration/jobs?limit=20');
      if (data && data.jobs) {
        console.log('[API] Received jobs from backend:', data.jobs.length);
        setJobs(prevJobs => {
          const fetchedJobMap = new Map(data.jobs.map(job => [job.JobId, job]));
          const updatedJobs = prevJobs.map(job => {
            const jobId = job.JobId || job.migrationId;
            return fetchedJobMap.get(jobId) || job;
          });
          const newJobs = data.jobs.filter(job => 
            !prevJobs.some(prevJob => (prevJob.JobId || prevJob.migrationId) === job.JobId)
          );
          return [...newJobs, ...updatedJobs].slice(0, 50);
        });
      }
    } catch (err) {
      console.warn("[API] Failed to fetch recent jobs:", err.response?.data?.msg || err.message);
    }
  }, []);

  useEffect(() => {
    fetchRecentJobs();
  }, [fetchRecentJobs]);

  // Persist jobs to localStorage whenever jobs change
  useEffect(() => {
    try {
      console.log('[Storage] Saving jobs to localStorage:', jobs.length, 'jobs');
      localStorage.setItem('migrationJobs', JSON.stringify(jobs));
    } catch (e) {
      console.error("[Storage] Failed to save jobs to localStorage:", e);
    }
  }, [jobs]);

  // ENHANCED POLLING LOGIC - SINGLE VERSION
  useEffect(() => {
    const activeJobs = jobs.filter(job => 
      job.status === 'IN_PROGRESS' || job.status === 'PENDING_UPLOAD'
    );
    
    if (activeJobs.length === 0) {
      console.log('[Polling] No active jobs to poll');
      return;
    }

    console.log(`[Polling] Starting enhanced polling for ${activeJobs.length} active jobs:`, 
      activeJobs.map(j => {
        const jobId = j.JobId || j.migrationId || 'unknown';
        const displayId = jobId ? jobId.substring(0,8) : 'unknown';
        return `${displayId} (${j.status})`;
      }));
    
    let pollCount = 0;
    const maxPollAttempts = 240; // 240 * 5s = 20 minutes
    let consecutiveErrors = 0;
    const maxConsecutiveErrors = 3;

    const pollInterval = setInterval(async () => {
      pollCount++;
      
      if (pollCount > maxPollAttempts) {
        console.warn('[Polling] Maximum polling time reached (20 minutes), stopping');
        setMessage({ 
          type: 'warning', 
          text: '⏰ Stopped automatic polling after 20 minutes. Refresh page to check latest status.' 
        });
        clearInterval(pollInterval);
        return;
      }

      console.log(`[Polling] Poll #${pollCount}/${maxPollAttempts} - checking ${activeJobs.length} jobs`);

      // Poll each active job
      for (const job of activeJobs) {
        try {
          const jobId = job.JobId || job.migrationId;
          if (!jobId) continue; // Skip jobs with no ID
          
          const response = await API.get(`/migration/status/${jobId}`);
          const serverData = response.data;
          
          // Reset error counter on successful request
          consecutiveErrors = 0;
          
          setJobs(currentJobs => {
            return currentJobs.map(j => {
              const currentJobId = j.JobId || j.migrationId;
              if (currentJobId === jobId) {
                const statusChanged = j.status !== serverData.status;
                
                if (statusChanged) {
                  const displayId = jobId ? jobId.substring(0,8) : 'unknown';
                  console.log(`[Polling] Job ${displayId} status changed: ${j.status} → ${serverData.status}`);
                  
                  // Show user notifications for important status changes
                  if (serverData.status === 'COMPLETED') {
                    setMessage({ 
                      type: 'success', 
                      text: `✅ Migration ${displayId} completed successfully!` 
                    });
                  } else if (serverData.status === 'FAILED') {
                    setMessage({ 
                      type: 'error', 
                      text: `❌ Migration ${displayId} failed: ${serverData.failureReason || 'Unknown error'}` 
                    });
                  } else if (serverData.status === 'IN_PROGRESS' && j.status === 'PENDING_UPLOAD') {
                    setMessage({ 
                      type: 'info', 
                      text: `🔄 Migration ${displayId} processing started` 
                    });
                  }
                }
                
                return {
                  ...j,           // Keep existing job data
                  ...serverData,  // Override with server data
                  JobId: jobId,   // Ensure JobId is preserved
                  migrationId: jobId // Backward compatibility
                };
              }
              return j;
            });
          });
          
        } catch (pollError) {
          const jobId = job.JobId || job.migrationId;
          consecutiveErrors++;
          
          if (pollError.response?.status === 401) {
            console.error(`[Polling] Authentication failed - stopping all polling`);
            setMessage({ 
              type: 'error', 
              text: '🔐 Authentication expired. Please refresh the page and login again.' 
            });
            clearInterval(pollInterval);
            return;
            
          } else if (pollError.response?.status === 404) {
            const displayId = jobId ? jobId.substring(0,8) : 'unknown';
            console.warn(`[Polling] Job ${displayId} not found on server`);
            // Mark job as potentially failed
            setJobs(currentJobs => {
              return currentJobs.map(j => {
                const currentJobId = j.JobId || j.migrationId;
                if (currentJobId === jobId && j.status === 'PENDING_UPLOAD') {
                  return { 
                    ...j, 
                    status: 'FAILED', 
                    failureReason: 'Job not found on server - may have been deleted or expired' 
                  };
                }
                return j;
              });
            });
            
          } else {
            const displayId = jobId ? jobId.substring(0,8) : 'unknown';
            console.warn(`[Polling] Error for job ${displayId}:`, pollError.message);
          }
          
          // Stop polling if too many consecutive errors
          if (consecutiveErrors >= maxConsecutiveErrors) {
            console.error('[Polling] Too many consecutive errors, stopping polling');
            setMessage({ 
              type: 'error', 
              text: '❌ Multiple polling errors occurred. Please refresh the page or check your connection.' 
            });
            clearInterval(pollInterval);
            return;
          }
        }
      }
    }, 5000); // Poll every 5 seconds

    return () => {
      console.log(`[Polling] Cleanup - stopped polling for ${activeJobs.length} jobs`);
      clearInterval(pollInterval);
    };
  }, [jobs, setMessage]);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
    setMessage({ type: '', text: '' });
  };
  
  return (
    <Paper sx={{ p: 3, my: 2 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3 }}>
        Migration Management
      </Typography>
      
      {message.text && (
        <Alert 
          severity={message.type} 
          onClose={() => setMessage({ type: '', text: '' })} 
          sx={{ mb: 3 }}
        >
          {message.text}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="migration tabs">
          <Tab label="Bulk Upload Tool" icon={<CloudUpload />} iconPosition="start" />
          <Tab label="Migration Reports" icon={<Assessment />} iconPosition="start" />
        </Tabs>
      </Box>

      {activeTab === 0 && <BulkUploadTool 
          jobs={jobs} 
          setJobs={setJobs} 
          userRole={userRole} 
          uploading={uploading} 
          setUploading={setUploading}
          setMessage={setMessage}
      />}
      {activeTab === 1 && <MigrationReports 
          setMessage={setMessage} 
          jobs={jobs} 
      />}
          
    </Paper>
  );
}