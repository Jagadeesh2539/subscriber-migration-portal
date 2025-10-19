import React, { useState, useEffect } from 'react';
import { 
    Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
    TableContainer, TableHead, TableRow, Alert, Box, Chip, IconButton,
    Checkbox, FormControlLabel, Tabs, Tab, Grid, Card, CardContent, CircularProgress
} from '@mui/material';
import { CloudUpload, Download, Assessment, FileDownload } from '@mui/icons-material';
import API from '../api'; // Ensure this path is correct relative to your file structure

// --- Sub-Component for Bulk Upload Tab ---
const BulkUploadTool = ({ jobs, setJobs, userRole, uploading, setUploading, setMessage }) => {
  const [file, setFile] = useState(null);
  const [isSimulateMode, setIsSimulateMode] = useState(false);

  // Migration is restricted to admin role
  const isAuthorized = userRole === 'admin';

  const handleUpload = async () => {
    if (!file) {
       setMessage({ type: 'error', text: 'Please select a CSV file first.' });
       return;
    }
    setUploading(true);
    setMessage({ type: 'info', text: 'Requesting secure upload URL...' });

    try {
      // 1. Get the pre-signed URL from the backend API
      const { data } = await API.post('/migration/bulk', { 
          isSimulateMode: isSimulateMode 
      });
      
      const { migrationId, uploadUrl } = data;
      
      setMessage({ type: 'info', text: 'Uploading file securely to S3... This might take a moment.' });
      
      // 2. Upload the file DIRECTLY to S3 using the received URL
      const uploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'text/csv' // Let S3 know it's a CSV
        },
        body: file,
      });

      // Check if the S3 upload itself was successful
      if (!uploadResponse.ok) {
        throw new Error(`S3 Upload Failed: Server responded with status ${uploadResponse.status}`);
      }

      // 3. Add the new job to the UI list to start status polling
      // We set the initial status based on the response, assuming it starts processing immediately
      setJobs(prevJobs => [{ migrationId, status: 'IN_PROGRESS', isSimulateMode, started_by: userRole }, ...prevJobs]);
      setMessage({ type: 'success', text: `Upload successful! Job ${migrationId.substring(0,8)}... is now processing.` });
      setFile(null); // Clear the file input after successful upload

    } catch (err) {
      console.error("Migration start failed:", err);
      // Provide more specific error feedback if possible
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
      default: return 'primary'; // PENDING_UPLOAD, etc.
    }
  };
  
  const calculateProgress = (job) => {
    if (job.status === 'COMPLETED') return 100;
    if (!job.totalRecords || job.totalRecords === 0 || job.status !== 'IN_PROGRESS') return 0;
    // Calculate progress based on various counts
    const processed = (job.migrated || 0) + (job.alreadyPresent || 0) + (job.notFound || 0) + (job.failed || 0);
    return Math.min(100, Math.round((processed / job.totalRecords) * 100)); // Ensure it doesn't exceed 100
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
          />
          <label htmlFor="file-upload">
            <Button variant="outlined" component="span" startIcon={<FileDownload />}>
              Choose CSV File
            </Button>
          </label>
          
          <Typography variant="body2" sx={{ flexGrow: 1, color: file ? 'text.primary' : 'text.secondary' }}>
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
            <TableRow>
              <TableCell>Job ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell sx={{ minWidth: 150 }}>Progress</TableCell>
              <TableCell>Simulate</TableCell>
              <TableCell>Total</TableCell>
              <TableCell>Migrated</TableCell>
              <TableCell>Skipped</TableCell>
              <TableCell>Failed</TableCell>
              {/* <TableCell>Started By</TableCell> */}
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow><TableCell colSpan={9} align="center">No migration jobs initiated yet.</TableCell></TableRow>
            ) : (
              jobs.map(job => (
                <TableRow key={job.migrationId}>
                  <TableCell title={job.migrationId}>{job.migrationId.substring(0, 8)}...</TableCell>
                  <TableCell><Chip label={job.status} color={getStatusColor(job.status)} size="small" /></TableCell>
                  <TableCell>
                    {(job.status === 'IN_PROGRESS' || job.status === 'COMPLETED') && (
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Box sx={{ width: '100%', mr: 1 }}>
                            <LinearProgress variant="determinate" value={calculateProgress(job)} color={getStatusColor(job.status)}/>
                        </Box>
                        <Box sx={{ minWidth: 35 }}>
                            <Typography variant="body2" color="text.secondary">{`${calculateProgress(job)}%`}</Typography>
                        </Box>
                        </Box>
                    )}
                    {job.status === 'PENDING_UPLOAD' && <Typography variant="caption" color="textSecondary">Waiting for upload...</Typography>}
                    {job.status === 'FAILED' && <Typography variant="caption" color="error">{job.failureReason || 'Unknown Error'}</Typography>}
                  </TableCell>
                  <TableCell>{job.isSimulateMode ? 'Yes' : 'No'}</TableCell>
                  <TableCell>{job.totalRecords ?? '-'}</TableCell>
                  <TableCell>{job.migrated ?? '-'}</TableCell>
                  <TableCell>{(job.alreadyPresent ?? 0) + (job.notFound ?? 0)}</TableCell>
                  <TableCell>{job.failed ?? '-'}</TableCell>
                  {/* <TableCell>{job.startedBy || 'N/A'}</TableCell> */}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

// --- Sub-Component for Migration Reports Tab ---
const MigrationReports = ({ setMessage }) => {
  const [reportList, setReportList] = useState([]); // Start empty
  const [loadingReports, setLoadingReports] = useState(false); // Add loading state
  const [jobIdInput, setJobIdInput] = useState('');

  // Example: Fetch recent jobs on mount (replace with actual API call if needed)
  useEffect(() => {
     // TODO: Implement an API call to fetch recent completed jobs if desired
     // e.g., API.get('/migration/jobs?status=COMPLETED').then(...)
     setLoadingReports(false); // Set to false after fetch
  }, []);

  const handleDownloadReport = async (migrationId) => {
    setMessage({ type: 'info', text: `Requesting download URL for report ${migrationId.substring(0,8)}...` });
    try {
      const { data } = await API.get(`/migration/report/${migrationId}`);
      window.location.href = data.downloadUrl; // Trigger browser download
      setMessage({ type: 'success', text: 'Report download started.' });
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.msg || `Could not get report for Job ${migrationId.substring(0,8)}.` });
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
            label="Enter Completed Job ID" 
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
      
      <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>Recent Report History (Placeholder)</Typography>
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Job ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Total Records</TableCell>
              <TableCell>Failures</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loadingReports ? (
              <TableRow><TableCell colSpan={5} align="center"><CircularProgress size={24} /></TableCell></TableRow>
            ) : reportList.length === 0 ? (
              <TableRow><TableCell colSpan={5} align="center">No recent completed jobs found.</TableCell></TableRow>
            ) : (
              reportList.map((job) => (
                <TableRow key={job.migrationId}>
                  <TableCell>{job.migrationId.substring(0, 8)}...</TableCell>
                  <TableCell>{job.status}</TableCell>
                  <TableCell>{job.totalRecords}</TableCell>
                  <TableCell sx={{ color: (job.failed ?? 0) > 0 ? 'error.main' : 'inherit' }}>{job.failed ?? 0}</TableCell>
                  <TableCell>
                    <IconButton onClick={() => handleDownloadReport(job.migrationId)} title="Download Report">
                      <Download />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))
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
  const [jobs, setJobs] = useState([]); // Start with empty jobs list
  
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userRole = user.role || 'guest';
  
  // Fetch initial job history or active jobs on mount
  useEffect(() => {
      // TODO: Implement API call to fetch recent/active jobs
      // e.g., API.get('/migration/jobs?limit=10').then(({data}) => setJobs(data.jobs));
  }, []);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
    setMessage({ type: '', text: '' }); // Clear messages on tab change
  };
  
  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3 }}>
        Migration Management
      </Typography>
      
      {message.text && <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })} sx={{ mb: 3 }}>{message.text}</Alert>}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="migration tabs">
          <Tab label="Bulk Upload Tool" icon={<CloudUpload />} iconPosition="start" />
          <Tab label="Migration Reports" icon={<Assessment />} iconPosition="start" />
        </Tabs>
      </Box>

      {/* Render the active tab content */}
      {activeTab === 0 && <BulkUploadTool 
          jobs={jobs} 
          setJobs={setJobs} 
          userRole={userRole} 
          uploading={uploading} 
          setUploading={setUploading}
          setMessage={setMessage}
      />}
      {activeTab === 1 && <MigrationReports setMessage={setMessage} />}
          
    </Paper>
  );
}
