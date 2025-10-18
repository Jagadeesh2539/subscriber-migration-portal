import React, { useState } from 'react';
import { Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Alert, Box, Chip, IconButton } from '@mui/material';
import { CloudUpload, Cancel } from '@mui/icons-material';
import API from '../api';

export default function BulkMigration() {
  const [file, setFile] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [uploading, setUploading] = useState(false);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await API.post('/migration/bulk', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      setJobs([...jobs, { jobId: data.jobId, status: 'IN_PROGRESS', progress: 0 }]);
      setMessage({ type: 'success', text: 'Migration started' });
      setFile(null);
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.msg || 'Upload failed' });
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
    <Paper sx={{ p: 3 }}>
      <Typography variant="h5" gutterBottom>Bulk Migration</Typography>

      {message.text && <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })} sx={{ mb: 2 }}>{message.text}</Alert>}

      <Box sx={{ mb: 3 }}>
        <input type="file" accept=".csv" onChange={e => setFile(e.target.files[0])} style={{ display: 'none' }} id="file-upload" />
        <label htmlFor="file-upload">
          <Button variant="outlined" component="span" sx={{ mr: 2 }}>Choose CSV File</Button>
        </label>
        {file && <Typography variant="body2" display="inline">{file.name}</Typography>}
        <Button variant="contained" startIcon={<CloudUpload />} onClick={handleUpload} disabled={!file || uploading} sx={{ ml: 2 }}>Start Migration</Button>
      </Box>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Job ID</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Progress</TableCell>
              <TableCell>Total</TableCell>
              <TableCell>Processed</TableCell>
              <TableCell>Failed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.map(job => (
              <TableRow key={job.jobId}>
                <TableCell>{job.jobId.substring(0, 8)}...</TableCell>
                <TableCell><Chip label={job.status} color={getStatusColor(job.status)} size="small" /></TableCell>
                <TableCell>
                  {job.status === 'IN_PROGRESS' && <LinearProgress variant="determinate" value={job.progress || 0} />}
                  {job.progress}%
                </TableCell>
                <TableCell>{job.total || '-'}</TableCell>
                <TableCell>{job.processed || '-'}</TableCell>
                <TableCell>{job.failed || '-'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}
