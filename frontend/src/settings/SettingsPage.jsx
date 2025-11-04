import React from 'react';
import { Container, Typography, Box } from '@mui/material';
import ProvisioningSettings from './ProvisioningSettings';

export default function SettingsPage() {
  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Box mt={2}>
        <ProvisioningSettings onModeChanged={(m) => console.log('Mode changed:', m)} />
      </Box>
    </Container>
  );
}
