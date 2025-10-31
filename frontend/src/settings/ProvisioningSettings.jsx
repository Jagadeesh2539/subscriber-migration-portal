import React, { useEffect, useState } from 'react';
import { Box, Card, CardContent, Typography, RadioGroup, FormControlLabel, Radio, Button, Alert, Stack, Chip } from '@mui/material';
import { settingsService } from '../api/settingsService';
import { toast } from 'react-hot-toast';

const modes = [
  { value: 'CLOUD', label: 'Cloud (DynamoDB)' },
  { value: 'LEGACY', label: 'Legacy (RDS MySQL)' },
  { value: 'DUAL_PROV', label: 'Dual Provision (Cloud + Legacy)' },
];

export default function ProvisioningSettings({ onModeChanged }) {
  const [current, setCurrent] = useState('CLOUD');
  const [selected, setSelected] = useState('CLOUD');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await settingsService.getProvisioningMode();
        const mode = data?.data?.mode || data?.mode || 'CLOUD';
        setCurrent(mode);
        setSelected(mode);
      } catch (e) {
        // default CLOUD
      }
    })();
  }, []);

  const save = async () => {
    setLoading(true);
    try {
      await settingsService.setProvisioningMode(selected);
      setCurrent(selected);
      toast.success(`Provisioning mode updated to ${selected}`);
      onModeChanged && onModeChanged(selected);
    } catch (e) {
      toast.error('Failed to update provisioning mode');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={2} mb={2}>
          <Typography variant="h6">Provisioning Mode</Typography>
          <Chip label={`Current: ${current}`} color="primary" />
        </Stack>
        <Alert severity="info" sx={{ mb: 2 }}>
          Choose where CRUD operations should be performed by default. You can still use explicit tabs for Cloud/Legacy/Dual on CRUD pages.
        </Alert>
        <RadioGroup value={selected} onChange={(e) => setSelected(e.target.value)}>
          {modes.map((m) => (
            <FormControlLabel key={m.value} value={m.value} control={<Radio />} label={m.label} />
          ))}
        </RadioGroup>
        <Box mt={2}>
          <Button variant="contained" onClick={save} disabled={loading}>
            Save Changes
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}
