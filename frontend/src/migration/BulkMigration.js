import React, { useState, useEffect } from 'react';
import { 
  Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
  TableContainer, TableHead, TableRow, Alert, Box, Chip, Grid, Card, CardContent, Tabs, Tab
} from '@mui/material';
import { CloudUpload, DataArray, FileDownload, Assessment, Send, Restore } from '@mui/icons-material';
import API from '../api';

// --- Sub-Component for Bulk Upload Tab ---
const BulkUploadTool = ({ jobs, setJobs, userRole }) => {
  const [file, setFile] = useState(null);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [uploading, setUploading] = useState(false);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await API.post('/migration/bulk', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      // Pre-add the job to the list with initial status
      setJobs([{ 
        jobId: data.jobId, 
        status: 'IN_PROGRESS', 
        progress: 0,
        started_at: new Date().toISOString(),
        started_by: 'You', // In a real app, this comes from the response
        total: 'Processing...'
      }, ...jobs]); 
      
      setMessage({ type: 'success', text: `Migration started successfully! Job ID: ${data.jobId.substring(0, 8)}...` });
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

  // Mock function to simulate status polling
  useEffect(() => {
    const interval = setInterval(() => {
      setJobs(prevJobs => prevJobs.map(job => {
        if (job.status === 'IN_PROGRESS') {
          const newProgress = Math.min(100, (job.progress || 0) + 10);
          if (newProgress === 100) {
            // Simulate completion
            return { 
                ...job, 
                status: 'COMPLETED', 
                progress: 100,
                processed: job.total || 100,
                failed: 0,
                completed_at: new Date().toISOString()
            };
          }
          // Mock data update
          return { 
              ...job, 
              progress: newProgress,
              total: 100,
              processed: Math.floor(newProgress * 0.9),
              failed: Math.floor(newProgress * 0.1) 
          };
        }
        return job;
      }));
    }, 2000);

    // In a real application, you would replace this mock with API polling:
    // const realPolling = setInterval(async () => { 
    //   // ... API.get('/migration/status/' + jobId) ...
    // }, 5000);

    return () => clearInterval(interval);
  }, [setJobs]);
  
  // Restrict to admin/operator roles
  const isAuthorized = userRole === 'admin' || userRole === 'operator';

  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '1px solid #ddd', pb: 1 }}>
        <DataArray sx={{ mr: 1, fontSize: '1.5rem' }} /> Bulk Subscriber Upload
      </Typography>

      {message.text && <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })} sx={{ mb: 3 }}>{message.text}</Alert>}

      {!isAuthorized && (
        <Alert severity="warning" sx={{ mb: 3 }}>You do not have the required permissions (Admin/Operator) to initiate bulk migration.</Alert>
      )}

      <Card variant="outlined" sx={{ p: 3, mb: 4, bgcolor: '#fafafa' }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Upload Migration File</Typography>
        <Box display="flex" alignItems="center" mb={2}>
          <input 
            type="file" 
            accept=".csv" 
            onChange={e => setFile(e.target.files[0])} 
            style={{ display: 'none' }} 
            id="file-upload" 
          />
          <label htmlFor="file-upload">
            <Button variant="outlined" component="span" sx={{ mr: 2 }} startIcon={<FileDownload />}>
              Choose CSV File
            </Button>
          </label>
          {file && <Typography variant="body2" display="inline" sx={{ mr: 4 }}>{file.name}</Typography>}
          <Button 
            variant="contained" 
            startIcon={<CloudUpload />} 
            onClick={handleUpload} 
            disabled={!file || uploading || !isAuthorized} 
            sx={{ ml: 'auto' }}
          >
            {uploading ? 'Uploading...' : 'Start Migration Job'}
          </Button>
        </Box>
        <Typography variant="caption" color="textSecondary">
          Accepted format: CSV with columns: `uid`, `imsi`, `msisdn`. Only subscribers found in the Legacy DB will be migrated.
        </Typography>
      </Card>

      <Typography variant="h6" sx={{ mb: 2 }}>Active & Recent Jobs</Typography>
      <TableContainer component={Paper} elevation={2}>
        <Table size="small">
          <TableHead sx={{ bgcolor: 'primary.light' }}>
            <TableRow>
              <TableCell sx={{ color: '#fff' }}>Job ID</TableCell>
              <TableCell sx={{ color: '#fff' }}>Status</TableCell>
              <TableCell sx={{ color: '#fff' }}>Progress</TableCell>
              <TableCell sx={{ color: '#fff' }}>Total Subs</TableCell>
              <TableCell sx={{ color: '#fff' }}>Processed</TableCell>
              <TableCell sx={{ color: '#fff' }}>Failed</TableCell>
              <TableCell sx={{ color: '#fff' }}>Started By</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow><TableCell colSpan={7} align="center">No recent migration jobs found.</TableCell></TableRow>
            ) : (
              jobs.map(job => (
                <TableRow key={job.jobId} hover>
                  <TableCell>{job.jobId.substring(0, 8)}...</TableCell>
                  <TableCell>
                    <Chip label={job.status} color={getStatusColor(job.status)} size="small" />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <LinearProgress 
                        variant="determinate" 
                        value={job.progress || 0} 
                        sx={{ width: 80, mr: 1 }} 
                        color={getStatusColor(job.status) === 'primary' ? 'primary' : getStatusColor(job.status)}
                      />
                      {job.progress}%
                    </Box>
                  </TableCell>
                  <TableCell>{job.total || '-'}</TableCell>
                  <TableCell sx={{ color: 'success.main', fontWeight: 'bold' }}>{job.processed || 0}</TableCell>
                  <TableCell sx={{ color: 'error.main', fontWeight: 'bold' }}>{job.failed || 0}</TableCell>
                  <TableCell>{job.started_by || 'System'}</TableCell>
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
  const [reportList, setReportList] = useState([
    { id: 1, date: '2025-10-15', total: 5000, failed: 12, status: 'Completed', file: 'report_20251015.csv' },
    { id: 2, date: '2025-10-01', total: 8500, failed: 25, status: 'Completed', file: 'report_20251001.csv' },
    { id: 3, date: '2025-09-20', total: 2000, failed: 0, status: 'Completed', file: 'report_20250920.csv' },
  ]);

  return (
    <Box>
      <Typography variant="h5" gutterBottom sx={{ mb: 2, borderBottom: '1px solid #ddd', pb: 1 }}>
        <Assessment sx={{ mr: 1, fontSize: '1.5rem' }} /> Migration Reports
      </Typography>
      
      <Alert severity="info" sx={{ mb: 3 }}>
        Download detailed CSV reports for historical bulk migration jobs.
      </Alert>

      <TableContainer component={Paper} elevation={2}>
        <Table size="small">
          <TableHead sx={{ bgcolor: 'secondary.light' }}>
            <TableRow>
              <TableCell sx={{ color: '#fff' }}>Report Date</TableCell>
              <TableCell sx={{ color: '#fff' }}>Total Migrated</TableCell>
              <TableCell sx={{ color: '#fff' }}>Failures</TableCell>
              <TableCell sx={{ color: '#fff' }}>Status</TableCell>
              <TableCell sx={{ color: '#fff' }}>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {reportList.map((report) => (
              <TableRow key={report.id} hover>
                <TableCell>{report.date}</TableCell>
                <TableCell>{report.total.toLocaleString()}</TableCell>
                <TableCell sx={{ color: report.failed > 0 ? 'error.main' : 'inherit' }}>{report.failed}</TableCell>
                <TableCell>
                  <Chip label={report.status} color="success" size="small" />
                </TableCell>
                <TableCell>
                  <Button variant="outlined" size="small" startIcon={<FileDownload />} onClick={() => alert(`Simulating download for ${report.file}`)}>
                    Download
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};


// --- Main Migration Component ---
export default function BulkMigration() {
  const [activeTab, setActiveTab] = useState(0);
  const [jobs, setJobs] = useState([]);
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userRole = user.role;

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };
  
  return (
    <Paper sx={{ p: 4, my: 3, boxShadow: 6 }}>
      <Typography variant="h4" gutterBottom sx={{ mb: 3, borderBottom: '2px solid #1976d2', pb: 1 }}>
        Migration Management Center
      </Typography>

      <Box sx={{ width: '100%', mb: 4 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="migration tabs">
          <Tab label="Bulk Upload Tool" icon={<CloudUpload />} iconPosition="start" />
          <Tab label="Migration Reports" icon={<Assessment />} iconPosition="start" />
        </Tabs>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Box sx={{ pt: 2 }}>
            {activeTab === 0 && <BulkUploadTool jobs={jobs} setJobs={setJobs} userRole={userRole} />}
            {activeTab === 1 && <MigrationReports />}
          </Box>
        </Grid>
      </Grid>
    </Paper>
  );
}
