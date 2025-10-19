import React, { useState, useEffect } from 'react';
import { 
  Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
  TableContainer, TableHead, TableRow, Alert, Box, Chip, CircularProgress,
  Card, CardContent, TextField
} from '@mui/material';
import { CloudUpload, GetApp as GetAppIcon } from '@mui/icons-material';
import API from '../api';

// --- Sub-Component 1: Bulk Migration Uploader and Job Viewer ---
const BulkMigrationUploader = () => {
    const [file, setFile] = useState(null);
    const [jobs, setJobs] = useState([]);
    const [message, setMessage] = useState({ type: '', text: '' });
    const [uploading, setUploading] = useState(false);
    
    // Placeholder for real-time job update polling
    useEffect(() => {
        // NOTE: This interval mocks job progress. In a production system, 
        // this would call the /migration/status/{jobId} endpoint to fetch 
        // real progress data from the backend job storage (e.g., DynamoDB or cache).
        const interval = setInterval(() => {
            setJobs(prevJobs => prevJobs.map(job => {
                // Mock progress update for IN_PROGRESS jobs
                if (job.status === 'IN_PROGRESS' && job.progress < 100) {
                    const newProgress = Math.min(job.progress + 10, 100);
                    // Mocking processed count based on 100 total items
                    const processedCount = Math.floor(newProgress / 100 * (job.total || 100));
                    return { ...job, progress: newProgress, processed: processedCount };
                }
                if (job.status === 'IN_PROGRESS' && job.progress === 100) {
                    return { ...job, status: 'COMPLETED', processed: job.total || 100 };
                }
                return job;
            }));
        }, 5000);
        return () => clearInterval(interval);
    }, []);


    const handleUpload = async () => {
        if (!file) return;
        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const { data } = await API.post('/migration/bulk', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
            // Using a mock total of 100 for visual progress, actual total would come from backend
            const mockTotal = 100; 
            setJobs(prevJobs => [
                ...prevJobs, 
                { jobId: data.jobId, status: 'IN_PROGRESS', progress: 10, processed: 0, total: mockTotal, started_at: new Date().toLocaleTimeString() }
            ]);
            setMessage({ type: 'success', text: `Migration job ${data.jobId.substring(0,8)}... started successfully! Processing has begun.` });
            setFile(null);
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

    return (
        <Paper sx={{ p: 4, borderRadius: 2 }}>
            <Typography variant="h4" gutterBottom>Bulk Subscriber Migration</Typography>
            <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
                Upload a CSV file containing UID/IMSI/MSISDNs to begin asynchronous migration.
            </Typography>

            {message.text && <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })} sx={{ mb: 2 }}>{message.text}</Alert>}

            <Box sx={{ mb: 4, display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: { xs: 'stretch', md: 'center' }, gap: 2, p: 2, border: '1px dashed #ccc', borderRadius: 1 }}>
                <input type="file" accept=".csv" onChange={e => setFile(e.target.files[0])} style={{ display: 'none' }} id="file-upload" />
                <label htmlFor="file-upload" style={{ flexShrink: 0 }}>
                    <Button variant="outlined" component="span" fullWidth={!file}>Choose CSV File</Button>
                </label>
                {file && <Typography variant="body1" sx={{ flexGrow: 1, my: { xs: 1, md: 0 } }}>File selected: **{file.name}**</Typography>}
                {!file && <Typography variant="body1" sx={{ flexGrow: 1, color: 'text.secondary', my: { xs: 1, md: 0 } }}>No file selected.</Typography>}
                <Button variant="contained" 
                        startIcon={uploading ? <CircularProgress size={20} color="inherit" /> : <CloudUpload />} 
                        onClick={handleUpload} 
                        disabled={!file || uploading}
                        sx={{ flexShrink: 0 }}
                >
                    {uploading ? 'Starting Job...' : 'Start Migration'}
                </Button>
            </Box>

            <Typography variant="h5" sx={{ mt: 3, mb: 2 }}>Active & Recent Jobs (Real-time)</Typography>
            <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                    <TableHead sx={{ bgcolor: 'action.hover' }}>
                        <TableRow>
                            <TableCell>Job ID</TableCell>
                            <TableCell>Time Started</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Progress</TableCell>
                            <TableCell align="right">Processed</TableCell>
                            <TableCell align="right">Failed</TableCell>
                            <TableCell align="right">Total</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {jobs.length === 0 && (
                            <TableRow><TableCell colSpan={7} align="center" sx={{ py: 2 }}>No bulk migration jobs found.</TableCell></TableRow>
                        )}
                        {jobs.map(job => (
                            <TableRow key={job.jobId} hover>
                                <TableCell>{job.jobId.substring(0, 8)}...</TableCell>
                                <TableCell>{job.started_at}</TableCell>
                                <TableCell><Chip label={job.status} color={getStatusColor(job.status)} size="small" /></TableCell>
                                <TableCell>
                                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                        <Box sx={{ width: '100%', mr: 1 }}>
                                            <LinearProgress variant="determinate" value={job.progress || 0} />
                                        </Box>
                                        <Box sx={{ minWidth: 35 }}>
                                            <Typography variant="body2" color="text.secondary">{job.progress}%</Typography>
                                        </Box>
                                    </Box>
                                </TableCell>
                                <TableCell align="right">{job.processed || '-'}</TableCell>
                                <TableCell align="right">{job.failed || '0'}</TableCell>
                                <TableCell align="right">{job.total || '-'}</TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Paper>
    );
};

// --- Sub-Component 2: Migration Reports Placeholder ---
const MigrationReports = () => {
    return (
        <Paper sx={{ p: 4, borderRadius: 2 }}>
            <Typography variant="h4" gutterBottom>Migration Reports</Typography>
            <Typography variant="body1" color="textSecondary" sx={{ mb: 3 }}>
                Generate and download comprehensive reports for past migration batches.
            </Typography>
            
            <Card variant="outlined" sx={{ p: 3, maxWidth: 600 }}>
                <Typography variant="h6" sx={{ mb: 2 }}>Download Batch Report</Typography>
                <TextField 
                    label="Enter Batch Job ID" 
                    fullWidth 
                    size="small" 
                    sx={{ mb: 2 }}
                />
                <Button variant="contained" startIcon={<GetAppIcon />}>
                    Generate & Download CSV
                </Button>
            </Card>
            
            <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>Recent Report History</Typography>
            <Alert severity="info">Report history and download functionality is ready for backend integration.</Alert>
            
        </Paper>
    );
};

// --- Main Component Switcher ---
export default function BulkMigration({ view }) {
    switch (view) {
        case 'reports':
            return <MigrationReports />;
        case 'bulk':
        default:
            return <BulkMigrationUploader />; // Default to uploader
    }
}
