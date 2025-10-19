import React, { useState, useEffect } from 'react';
import { 
  Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
  TableContainer, TableHead, TableRow, Alert, Box, Chip, Grid, Card, CardContent, Tabs, Tab, CircularProgress, IconButton, TextField
} from '@mui/material';
import { CloudUpload, DataArray, FileDownload, Assessment, FileCopy as FileCopyIcon } from '@mui/icons-material';
import API from '../api';

// --- Sub-Component for Bulk Upload Tab ---
const BulkUploadTool = ({ jobs, setJobs, userRole, uploading, setUploading, setMessage }) => {
  const [file, setFile] = useState(null);

  const isAuthorized = userRole === 'admin' || userRole === 'operator';

  const handleUpload = async () => {
    if (!file) {
      setMessage({ type: 'error', text: 'Please select a file to upload.' });
      return;
    }
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await API.post('/migration/bulk', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      
      // Pre-add the job to the list with initial status
      const newJob = { 
        jobId: data.jobId, 
        status: 'IN_PROGRESS', 
        progress: 0,
        started_at: new Date().toLocaleTimeString(),
        started_by: userRole.toUpperCase(), 
        total: 100, // Mock total for visual progress
        processed: 0,
        failed: 0,
      };

      setJobs(prevJobs => [newJob, ...prevJobs]); 
      
      setMessage({ type: 'success', text: `Migration job started successfully! ID: ${data.jobId.substring(0, 8)}...` });
      setFile(null); // Clear file input after submission
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.msg || 'Upload failed. Check file format.' });
    } finally {
      setUploading(false);
    }
  };
  
  const getStatusColor = (status) => {
    switch (status) {
      case 'COMPLETED': return 'success';
      case 'FAILED': return 'error';
      case 'CANCELLED': return 'default';
      default: return 'primary';
    }
  };
  
  const handleCopyJobId = (jobId) => {
    navigator.clipboard.writeText(jobId).then(() => {
        setMessage({ type: 'info', text: `Job ID ${jobId.substring(0, 8)}... copied to clipboard!` });
    }).catch(err => {
        console.error('Could not copy text: ', err);
        setMessage({ type: 'error', text: 'Failed to copy Job ID.' });
    });
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '1px solid #ddd', pb: 1 }}>
        <DataArray sx={{ mr: 1, fontSize: '1.5rem' }} /> Bulk Subscriber Upload
      </Typography>

      {!isAuthorized && (
        <Alert severity="warning" sx={{ mb: 3 }}>You do not have the required permissions (Admin/Operator) to initiate bulk migration.</Alert>
      )}

      <Card variant="outlined" sx={{ p: 3, mb: 4, bgcolor: '#fafafa' }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Upload Migration File</Typography>
        <Box display="flex" flexDirection={{ xs: 'column', md: 'row' }} alignItems={{ xs: 'stretch', md: 'center' }} gap={2}>
          <input 
            type="file" 
            accept=".csv" 
            onChange={e => setFile(e.target.files[0])} 
            style={{ display: 'none' }} 
            id="file-upload" 
          />
          <label htmlFor="file-upload" style={{ flexShrink: 0 }}>
            <Button variant="outlined" component="span" startIcon={<FileDownload />}>
              Choose CSV File
            </Button>
          </label>
          
          <Typography variant="body2" sx={{ flexGrow: 1, color: file ? 'text.primary' : 'text.secondary', fontWeight: file ? 'bold' : 'normal' }}>
            {file ? file.name : 'No file selected. Required format: uid,imsi,msisdn'}
          </Typography>

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
      <Alert severity="warning" sx={{ mb: 2 }}>
        **NOTE:** The Legacy DB connection is disabled in the cloud. Migration is pulling data from a **MOCK dictionary** in the backend for demonstration. Job data is simulated.
      </Alert>
      <TableContainer component={Paper} elevation={2}>
        <Table size="small" aria-label="migration jobs table">
          <TableHead sx={{ bgcolor: 'primary.light' }}>
            <TableRow>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Job ID</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Status</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Progress</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Total Subs</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Processed</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Failed</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Started By</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow><TableCell colSpan={7} align="center">No recent migration jobs found.</TableCell></TableRow>
            ) : (
              jobs.map(job => (
                <TableRow key={job.jobId} hover size="small">
                  <TableCell sx={{ display: 'flex', alignItems: 'center', gap: 1, whiteSpace: 'nowrap' }}>
                    {job.jobId.substring(0, 8)}...
                    <IconButton onClick={() => handleCopyJobId(job.jobId)} size="small" color="info" sx={{ p: 0.5 }}>
                        <FileCopyIcon fontSize="inherit" />
                    </IconButton>
                  </TableCell>
                  <TableCell>
                    <Chip label={job.status} color={getStatusColor(job.status)} size="small" />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', whiteSpace: 'nowrap' }}>
                      <LinearProgress 
                        variant="determinate" 
                        value={job.progress || 0} 
                        sx={{ width: 80, mr: 1 }} 
                        color={getStatusColor(job.status) === 'primary' ? 'primary' : getStatusColor(job.status)}
                      />
                      {job.progress}%
                    </Box>
                  </TableCell>
                  <TableCell>{job.total}</TableCell>
                  <TableCell sx={{ color: 'success.main', fontWeight: 'bold', whiteSpace: 'nowrap' }}>{job.processed}</TableCell>
                  <TableCell sx={{ color: 'error.main', fontWeight: 'bold', whiteSpace: 'nowrap' }}>{job.failed}</TableCell>
                  <TableCell>{job.started_by}</TableCell>
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
const MigrationReports = () => {
  const [reportList] = useState([
    { id: 'job-1', date: '2025-10-15', total: 5000, failed: 12, status: 'Completed' },
    { id: 'job-2', date: '2025-10-01', total: 8500, failed: 25, status: 'Completed' },
    { id: 'job-3', date: '2025-09-20', total: 2000, failed: 0, status: 'Completed' },
  ]);
  const [jobIdInput, setJobIdInput] = useState('');
  const [reportMessage, setReportMessage] = useState({ type: 'info', text: 'Enter a Job ID to generate a final report.' });

  const handleGenerateReport = () => {
    if (!jobIdInput.trim()) {
        setReportMessage({ type: 'error', text: 'Please enter a valid Batch Job ID.' });
        return;
    }
    
    // NOTE: This download is currently mocked. The backend API needs to be implemented.
    setReportMessage({ 
        type: 'error', 
        text: `Error: Report download failed for Job ID ${jobIdInput}. The physical download function is a placeholder and requires backend implementation (e.g., S3 access).` 
    });
  };
  
  // Use a temporary list for display to simulate loading/empty state
  const displayList = reportList.length > 0 ? reportList : null;

  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '1px solid #ddd', pb: 1 }}>
        <Assessment sx={{ mr: 1, fontSize: '1.5rem' }} /> Migration Reports
      </Typography>
      
      <Alert severity="info" sx={{ mb: 3 }}>
        View and download detailed reports for historical migration jobs.
      </Alert>

      <Card variant="outlined" sx={{ p: 3, maxWidth: 600, boxShadow: 1 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Download Batch Report</Typography>
        
        {reportMessage.text && <Alert severity={reportMessage.type} sx={{ mb: 2 }}>{reportMessage.text}</Alert>}

        <TextField 
          label="Enter Batch Job ID" 
          fullWidth 
          size="small" 
          value={jobIdInput}
          onChange={(e) => {setJobIdInput(e.target.value); setReportMessage({type: 'info', text: 'Enter a Job ID to generate a final report.'});}}
          sx={{ mb: 2 }}
        />
        <Button variant="contained" startIcon={<FileDownload />} onClick={handleGenerateReport}>
          Generate & Download CSV
        </Button>
      </Card>
      
      <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>Recent Report History</Typography>
      <TableContainer component={Paper} elevation={2}>
        <Table size="small" aria-label="report history table">
          <TableHead sx={{ bgcolor: 'secondary.light' }}>
            <TableRow>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Job ID</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Report Date</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Total Migrated</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Failures</TableCell>
              <TableCell sx={{ color: '#fff', whiteSpace: 'nowrap' }}>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {displayList === null ? (
              <TableRow><TableCell colSpan={5} align="center"><CircularProgress size={24} /> Loading reports...</TableCell></TableRow>
            ) : displayList.length === 0 ? (
              <TableRow><TableCell colSpan={5} align="center">No historical reports available.</TableCell></TableRow>
            ) : (
              displayList.map((report) => (
                <TableRow key={report.id} hover>
                  <TableCell>{report.id}</TableCell>
                  <TableCell>{report.date}</TableCell>
                  <TableCell>{report.total.toLocaleString()}</TableCell>
                  <TableCell sx={{ color: report.failed > 0 ? 'error.main' : 'inherit' }}>{report.failed}</TableCell>
                  <TableCell>
                    <Button variant="outlined" size="small" startIcon={<FileDownload />} onClick={() => setReportMessage({type: 'warning', text: `Download link generation is currently mocked. Report ID: ${report.id}`})}>
                      Download
                    </Button>
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


// --- Main Component Switcher ---
export default function BulkMigration() {
  const [activeTab, setActiveTab] = useState(0);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [uploading, setUploading] = useState(false);
  
  // Initialize with a mock job for demonstration
  const [jobs, setJobs] = useState([{
    jobId: '7d5cd6cf-a2b1-4c3e-9f01-1b2c3d4e5f6g',
    status: 'COMPLETED',
    progress: 100,
    started_at: '10:30 AM',
    started_by: 'admin',
    total: 100,
    processed: 100,
    failed: 0,
  }]);
  
  // ✅ Enhanced: Safely default userRole to 'guest' if localStorage is empty
  const user = JSON.parse(localStorage.getItem('user') || '{"role": "guest"}');
  const userRole = user.role;
  
  // --- FIX: Background polling moved here to persist across tabs ---
  useEffect(() => {
    // Only start interval if there is at least one job IN_PROGRESS
    const jobsInProgress = jobs.some(job => job.status === 'IN_PROGRESS');
    if (!jobsInProgress) return;
    
    const interval = setInterval(() => {
      setJobs(prevJobs => prevJobs.map(job => {
        if (job.status === 'IN_PROGRESS') {
          // Increase progress, but don't increase it past 90% immediately to give the illusion of completion time
          const newProgress = Math.min(95, (job.progress || 0) + 10);
          
          if (newProgress >= 95 && job.progress < 95) {
            // Wait a moment at 95% before completing
            return {...job, progress: newProgress};
          } else if (newProgress >= 95 && job.progress >= 95) {
             // Final step completion
             return { 
                ...job, 
                status: 'COMPLETED', 
                progress: 100,
                processed: job.total, // Processed equals total upon completion
                failed: 0,
            };
          }

          // Mock data update: simulate steady progress
          const processedCount = Math.floor(newProgress / 100 * job.total);
          return { 
              ...job, 
              progress: newProgress,
              processed: processedCount,
          };
        }
        return job;
      }));
    }, 2000);

    return () => clearInterval(interval);
  }, [jobs, setJobs]);
  // -------------------------------------------------------------

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
    // Clear global messages when switching tabs
    setMessage({ type: '', text: '' }); 
  };
  
  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, borderBottom: '2px solid #1976d2', pb: 1 }}>
        Migration Management Center
      </Typography>
      
      {/* Global message display */}
      {message.text && <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })} sx={{ mb: 3 }}>{message.text}</Alert>}


      <Box sx={{ width: '100%', mb: 4 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="migration tabs">
          <Tab label="Bulk Upload Tool" icon={<CloudUpload />} iconPosition="start" />
          <Tab label="Migration Reports" icon={<Assessment />} iconPosition="start" />
        </Tabs>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Box sx={{ pt: 2 }}>
            {activeTab === 0 && <BulkUploadTool 
                jobs={jobs} 
                setJobs={setJobs} 
                userRole={userRole} 
                uploading={uploading} 
                setUploading={setUploading}
                setMessage={setMessage}
            />}
            {activeTab === 1 && <MigrationReports setMessage={setMessage} />}
          </Box>
        </Grid>
      </Grid>
    </Paper>
  );
}
