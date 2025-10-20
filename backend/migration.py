from flask import Blueprint, request, jsonify
from auth import login_required
from audit import log_audit
import os
import boto3
import uuid
from datetime import datetime

mig_bp = Blueprint('migration', __name__)

MIGRATION_JOBS_TABLE_NAME = os.environ.get('MIGRATION_JOBS_TABLE_NAME')
MIGRATION_UPLOAD_BUCKET_NAME = os.environ.get('MIGRATION_UPLOAD_BUCKET_NAME')

dynamodb = boto3.resource('dynamodb')
jobs_table = dynamodb.Table(MIGRATION_JOBS_TABLE_NAME)
s3_client = boto3.client('s3')

@mig_bp.route('/bulk', methods=['POST', 'OPTIONS'])
@login_required()
def start_bulk_migration():
    user = request.environ['user']
    data = request.json
    is_simulate_mode = data.get('isSimulateMode', False)
    
    try:
        migration_id = str(uuid.uuid4())
        upload_key = f"uploads/{migration_id}.csv" 
        
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME,
                'Key': upload_key,
                'ContentType': 'text/csv',
                'Metadata': {
                    'migrationid': migration_id,
                    'issimulatemode': str(is_simulate_mode).lower(),
                    'userid': user['sub']
                }
            },
            ExpiresIn=3600
        )
        
        jobs_table.put_item(
            Item={
                'migrationId': migration_id,
                'status': 'PENDING_UPLOAD',
                'startedBy': user['sub'],
                'startedAt': datetime.utcnow().isoformat(),
                'isSimulateMode': is_simulate_mode
            }
        )
        
        log_audit(user['sub'], 'START_MIGRATION', {'migrationId': migration_id, 'simulate': is_simulate_mode}, 'SUCCESS')
        return jsonify(migrationId=migration_id, uploadUrl=upload_url), 200
        
    except Exception as e:
        log_audit(user['sub'], 'START_MIGRATION', {}, f'FAILED: {str(e)}')
        return jsonify(msg=f'Error initiating migration: {str(e)}'), 500

@mig_bp.route('/status/<migration_id>', methods=['GET'])
@login_required()
def get_migration_status(migration_id):
    try:
        response = jobs_table.get_item(Key={'migrationId': migration_id})
        status = response.get('Item')
        if not status:
            return jsonify(msg='Job not found'), 404
        return jsonify(status)
    except Exception as e:
        return jsonify(msg=f'Error getting job status: {str(e)}'), 500

@mig_bp.route('/report/<migration_id>', methods=['GET'])
@login_required()
def get_migration_report(migration_id):
    try:
        response = jobs_table.get_item(Key={'migrationId': migration_id})
        job = response.get('Item')
        if not job:
            return jsonify(msg='Job not found'), 404
        
        report_key = job.get('reportS3Key')
        if not report_key:
            if job.get('status') == 'FAILED':
                 return jsonify(msg=f"Job failed: {job.get('failureReason', 'Unknown error')}"), 404
            return jsonify(msg='Report not yet available or job is still processing'), 404
            
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': MIGRATION_UPLOAD_BUCKET_NAME, # Report is in the same bucket
                'Key': report_key,
                'ResponseContentDisposition': f'attachment; filename="report-{migration_id}.csv"'
            },
            ExpiresIn=3600
        )
        
        return jsonify(downloadUrl=download_url), 200
        
    except Exception as e:
        return jsonify(msg=f'Error generating report URL: {str(e)}'), 500
```eof

---

#### 4. Legacy DB Connector (`backend/legacy_db.py`)

This ensures the connector has the `init_connection_details` function needed by the Migration Processor Lambda.

```python:Legacy DB Connector:backend/legacy_db.py
import os
import pymysql
import pymysql.cursors
import json
import warnings
from contextlib import contextmanager

# --- Global connection details, used as defaults or can be overridden ---
DB_HOST = os.environ.get('LEGACY_DB_HOST', 'host.docker.internal')
DB_PORT = int(os.environ.get('LEGACY_DB_PORT', 3307))
DB_USER = os.environ.get('LEGACY_DB_USER', 'root')
DB_PASSWORD = os.environ.get('LEGACY_DB_PASSWORD', 'Admin@123')
DB_NAME = os.environ.get('LEGACY_DB_NAME', 'legacydb')
IS_LEGACY_DB_DISABLED = False # Default

def init_connection_details(host, port, user, password, database):
    """Allows runtime configuration of DB connection, used by the Lambda."""
    global DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, IS_LEGACY_DB_DISABLED
    DB_HOST = host
    DB_PORT = int(port)
    DB_USER = user
    DB_PASSWORD = password
    DB_NAME = database
    IS_LEGACY_DB_DISABLED = False # Ensure it's enabled when configured

@contextmanager
def get_connection():
    """Provides a database connection that is automatically closed."""
    if IS_LEGACY_DB_DISABLED:
        raise RuntimeError("Legacy DB connection is disabled in this environment.")
        
    connection = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, cursorclass=pymysql.cursors.DictCursor)
    try:
        yield connection
    finally:
        connection.close()

def get_subscriber_by_any_id(identifier):
    """Fetches a full subscriber profile from the legacy DB using UID, IMSI, or MSISDN."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            sql = """
            SELECT s.*, hss.subscription_id, hss.profile_type, hss.private_user_id, hss.public_user_id, hlr.call_forward_unconditional, hlr.call_barring_all_outgoing, hlr.clip_provisioned, hlr.clir_provisioned, hlr.call_hold_provisioned, hlr.call_waiting_provisioned, vas.account_status, vas.language_id, vas.sim_type, (SELECT JSON_ARRAYAGG(JSON_OBJECT('context_id', pdp.context_id, 'apn', pdp.apn, 'qos_profile', pdp.qos_profile)) FROM tbl_pdp_contexts pdp WHERE pdp.subscriber_uid = s.uid) AS pdp_contexts
            FROM subscribers s
            LEFT JOIN tbl_hss_profiles hss ON s.uid = hss.subscriber_uid
            LEFT JOIN tbl_hlr_features hlr ON s.uid = hlr.subscriber_uid
            LEFT JOIN tbl_vas_services vas ON s.uid = vas.subscriber_uid
            WHERE s.uid = %s OR s.imsi = %s OR s.msisdn = %s;
            """
            cursor.execute(sql, (identifier, identifier, identifier))
            result = cursor.fetchone()
            
            if result:
                if result.get('pdp_contexts'):
                    result['pdp_contexts'] = json.loads(result['pdp_contexts'])
                else:
                    result['pdp_contexts'] = []
                for key, value in result.items():
                    if value == 0: result[key] = False
                    elif value == 1: result[key] = True
            return result

def create_subscriber_full_profile(data):
    """Creates a full subscriber profile across all tables within a single transaction."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            try:
                conn.begin()
                sql_sub = """INSERT INTO subscribers (uid, imsi, msisdn, plan, subscription_state, service_class, charging_characteristics) VALUES (%s, %s, %s, %s, %s, %s, %s);"""
                cursor.execute(sql_sub, (data['uid'], data['imsi'], data.get('msisdn'), data.get('plan'), data.get('subscription_state'), data.get('service_class'), data.get('charging_characteristics')))
                sql_hss = """INSERT INTO tbl_hss_profiles (subscriber_uid, profile_type) VALUES (%s, %s);"""
                cursor.execute(sql_hss, (data['uid'], data.get('profile_type')))
                sql_hlr = """INSERT INTO tbl_hlr_features (subscriber_uid, call_forward_unconditional, call_barring_all_outgoing, clip_provisioned, clir_provisioned, call_hold_provisioned, call_waiting_provisioned) VALUES (%s, %s, %s, %s, %s, %s, %s);"""
                cursor.execute(sql_hlr, (data['uid'], data.get('call_forward_unconditional'), data.get('call_barring_all_outgoing', False), data.get('clip_provisioned', True), data.get('clir_provisioned', False), data.get('call_hold_provisioned', True), data.get('call_waiting_provisioned', True)))
                sql_vas = """INSERT INTO tbl_vas_services (subscriber_uid, account_status, language_id, sim_type) VALUES (%s, %s, %s, %s);"""
                cursor.execute(sql_vas, (data['uid'], data.get('account_status', 'ACTIVE'), data.get('language_id', 'en-US'), data.get('sim_type', '4G_USIM')))
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"Transaction failed: {e}")
                raise
            
def delete_subscriber(uid):
    """Deletes a subscriber. CASCADE constraint handles child tables."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            sql = "DELETE FROM subscribers WHERE uid = %s"
            cursor.execute(sql, (uid,))
```eof

---

#### 5. Frontend Migration UI (`frontend/src/migration/BulkMigration.js`)

This file is updated to implement the correct S3 pre-signed URL upload workflow.

```react:Bulk Migration UI:frontend/src/migration/BulkMigration.js
import React, { useState, useEffect } from 'react';
import { 
    Paper, Button, Typography, LinearProgress, Table, TableBody, TableCell, 
    TableContainer, TableHead, TableRow, Alert, Box, Chip, IconButton,
    Checkbox, FormControlLabel, Tabs, Tab, Grid, Card, CardContent, CircularProgress
} from '@mui/material';
import { CloudUpload, Download, Assessment, FileDownload } from '@mui/icons-material';
import API from '../api'; // Ensure this path is correct

// --- Sub-Component for Bulk Upload Tab ---
const BulkUploadTool = ({ jobs, setJobs, userRole, uploading, setUploading, setMessage }) => {
  const [file, setFile] = useState(null);
  const [isSimulateMode, setIsSimulateMode] = useState(false);

  // Migration should only be allowed by admin
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
    const processed = (job.migrated || 0) + (job.alreadyPresent || 0) + (job.not_found_in_legacy || 0) + (job.failed || 0); // Correct key name
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
              <TableRow><TableCell colSpan={8} align="center">No migration jobs initiated yet.</TableCell></TableRow>
            ) : (
              jobs.map(job => (
                <TableRow key={job.migrationId}>
                  <TableCell title={job.migrationId}>{job.migrationId.substring(0, 8)}...</TableCell>
                  <TableCell><Chip label={job.status} color={getStatusColor(job.status)} size="small" /></TableCell>
                  <TableCell>
                    {(job.status === 'IN_PROGRESS' || job.status === 'COMPLETED') ? (
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Box sx={{ width: '100%', mr: 1 }}>
                            <LinearProgress variant="determinate" value={calculateProgress(job)} color={getStatusColor(job.status)}/>
                        </Box>
                        <Box sx={{ minWidth: 35 }}>
                            <Typography variant="body2" color="text.secondary">{`${calculateProgress(job)}%`}</Typography>
                        </Box>
                        </Box>
                    ) : job.status === 'PENDING_UPLOAD' ? (
                       <Typography variant="caption" color="textSecondary">Waiting for upload...</Typography>
                    ): (
                       <Typography variant="caption" color={job.status === 'FAILED' ? 'error' : 'textSecondary'}>{job.failureReason || job.status || 'Unknown'}</Typography>
                    )}
                  </TableCell>
                  <TableCell>{job.isSimulateMode ? 'Yes' : 'No'}</TableCell>
                  <TableCell>{job.totalRecords ?? '-'}</TableCell>
                  <TableCell>{job.migrated ?? '-'}</TableCell>
                  {/* Combine AlreadyPresent and NotFound for Skipped count */}
                  <TableCell>{(job.alreadyPresent ?? 0) + (job.not_found_in_legacy ?? 0)}</TableCell> 
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
    if (!migrationId || !migrationId.trim()){
        setMessage({ type: 'warning', text: 'Please enter a valid Job ID.' });
        return;
    }
    setMessage({ type: 'info', text: `Requesting download URL for report ${migrationId.substring(0,8)}...` });
    try {
      const { data } = await API.get(`/migration/report/${migrationId.trim()}`);
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

   // Background polling for job status updates
  useEffect(() => {
    const jobsInProgress = jobs.some(job => job.status === 'IN_PROGRESS' || job.status === 'PENDING_UPLOAD');
    if (!jobsInProgress) return; // Only poll if there are active jobs

    const intervalId = setInterval(() => {
      jobs.forEach(job => {
        if (job.status === 'IN_PROGRESS' || job.status === 'PENDING_UPLOAD') {
          API.get(`/migration/status/${job.migrationId}`)
            .then(({ data }) => {
              setJobs(currentJobs =>
                currentJobs.map(j => (j.migrationId === data.migrationId ? data : j))
              );
            })
            .catch(err => console.warn("Polling failed for job", job.migrationId, err)); // Use warn for polling errors
        }
      });
    }, 7000); // Poll every 7 seconds

    return () => clearInterval(intervalId); // Cleanup interval on component unmount or when jobs change
  }, [jobs]); // Re-run effect if the jobs list changes


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
