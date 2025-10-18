import React, { useState, useEffect } from 'react';
import {
  Paper, TextField, Button, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, IconButton, Dialog, DialogTitle,
  DialogContent, DialogActions, Alert, Box
} from '@mui/material';
import { Edit, Delete, Add } from '@mui/icons-material';
import API from '../api';

export default function SubscriberProvision() {
  const [subscribers, setSubscribers] = useState([]);
  const [open, setOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [currentSub, setCurrentSub] = useState({ uid: '', imsi: '', msisdn: '', plan: '', status: 'active' });
  const [message, setMessage] = useState({ type: '', text: '' });

  const loadSubscribers = async () => {
    try {
      const { data } = await API.get('/provision/subscribers');
      setSubscribers(data.subscribers || []);
    } catch {
      setMessage({ type: 'error', text: 'Failed to load subscribers' });
    }
  };

  useEffect(() => {
    loadSubscribers();
  }, []);

  const handleSave = async () => {
    try {
      if (editMode) {
        await API.put(`/provision/subscriber/${currentSub.uid}`, currentSub);
        setMessage({ type: 'success', text: 'Subscriber updated' });
      } else {
        await API.post('/provision/subscriber', currentSub);
        setMessage({ type: 'success', text: 'Subscriber added' });
      }
      setOpen(false);
      loadSubscribers();
    } catch {
      setMessage({ type: 'error', text: 'Operation failed' });
    }
  };

  const handleDelete = async (uid) => {
    if (window.confirm('Delete this subscriber?')) {
      try {
        await API.delete(`/provision/subscriber/${uid}`);
        setMessage({ type: 'success', text: 'Subscriber deleted' });
        loadSubscribers();
      } catch {
        setMessage({ type: 'error', text: 'Failed to delete' });
      }
    }
  };

  const openDialog = (sub = null) => {
    if (sub) {
      setCurrentSub(sub);
      setEditMode(true);
    } else {
      setCurrentSub({ uid: '', imsi: '', msisdn: '', plan: '', status: 'active' });
      setEditMode(false);
    }
    setOpen(true);
  };

  return (
    <Paper sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h5">Subscriber Management</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => openDialog()}>Add Subscriber</Button>
      </Box>

      {message.text && <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })} sx={{ mb: 2 }}>{message.text}</Alert>}

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>UID</TableCell>
              <TableCell>IMSI</TableCell>
              <TableCell>MSISDN</TableCell>
              <TableCell>Plan</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {subscribers.map(sub => (
              <TableRow key={sub.uid}>
                <TableCell>{sub.uid}</TableCell>
                <TableCell>{sub.imsi}</TableCell>
                <TableCell>{sub.msisdn}</TableCell>
                <TableCell>{sub.plan}</TableCell>
                <TableCell>{sub.status}</TableCell>
                <TableCell>
                  <IconButton onClick={() => openDialog(sub)}><Edit /></IconButton>
                  <IconButton onClick={() => handleDelete(sub.uid)}><Delete /></IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editMode ? 'Edit Subscriber' : 'Add Subscriber'}</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="UID" value={currentSub.uid} onChange={e => setCurrentSub({ ...currentSub, uid: e.target.value })} margin="normal" disabled={editMode} required />
          <TextField fullWidth label="IMSI" value={currentSub.imsi} onChange={e => setCurrentSub({ ...currentSub, imsi: e.target.value })} margin="normal" required />
          <TextField fullWidth label="MSISDN" value={currentSub.msisdn} onChange={e => setCurrentSub({ ...currentSub, msisdn: e.target.value })} margin="normal" required />
          <TextField fullWidth label="Plan" value={currentSub.plan} onChange={e => setCurrentSub({ ...currentSub, plan: e.target.value })} margin="normal" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} variant="contained">Save</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
