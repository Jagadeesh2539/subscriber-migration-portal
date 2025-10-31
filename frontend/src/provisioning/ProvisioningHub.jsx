import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Tabs, Tab, Card, CardContent, Stack, Chip, Alert,
  Grid, Paper, CircularProgress, Button, Tooltip, Divider
} from '@mui/material';
import {
  CloudQueue, Database, Sync, Refresh, TrendingUp, Speed,
  CheckCircle, Warning, Error
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useLocation, Routes, Route, Navigate } from 'react-router-dom';

// CRUD Components
import CloudCrud from './CloudCrud';
import LegacyCrud from './LegacyCrud';
import DualCrud from './DualCrud';

// Settings service
import { settingsService } from '../api/settingsService';

// Tab configuration
const tabs = [
  {
    value: 'cloud',
    label: 'Cloud (DynamoDB)',
    icon: <CloudQueue />,
    path: '/provision/cloud',
    color: 'success',
    description: 'Serverless, auto-scaling NoSQL database',
  },
  {
    value: 'legacy',
    label: 'Legacy (RDS MySQL)',
    icon: <Database />,
    path: '/provision/legacy',
    color: 'warning',
    description: 'Traditional relational database',
  },
  {
    value: 'dual',
    label: 'Dual Provision',
    icon: <Sync />,
    path: '/provision/dual',
    color: 'info',
    description: 'Synchronized operations across both systems',
  },
];

// System health indicators
const SystemHealthCard = ({ system, isLoading, data, error }) => {
  const getHealthIcon = () => {
    if (isLoading) return <CircularProgress size={20} />;
    if (error) return <Error color="error" />;
    if (data?.healthy) return <CheckCircle color="success" />;
    return <Warning color="warning" />;
  };

  const getHealthColor = () => {
    if (error) return 'error';
    if (data?.healthy) return 'success';
    return 'warning';
  };

  return (
    <Paper sx={{ p: 2, textAlign: 'center', height: '100%' }}>
      <Stack spacing={1} alignItems="center">
        {getHealthIcon()}
        <Typography variant="h6" color={getHealthColor()}>
          {system}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isLoading ? 'Checking...' : error ? 'Unhealthy' : data?.healthy ? 'Healthy' : 'Unknown'}
        </Typography>
        {data?.responseTime && (
          <Chip 
            size="small" 
            label={`${data.responseTime}ms`} 
            color={data.responseTime < 200 ? 'success' : data.responseTime < 500 ? 'warning' : 'error'}
          />
        )}
        {data?.recordCount && (
          <Typography variant="caption">
            {data.recordCount.toLocaleString()} records
          </Typography>
        )}
      </Stack>
    </Paper>
  );
};

const ProvisioningHub = () => {
  const [globalMode, setGlobalMode] = useState('CLOUD');
  const navigate = useNavigate();
  const location = useLocation();

  // Determine current tab from URL
  const getCurrentTab = () => {
    const path = location.pathname;
    if (path.includes('/cloud')) return 'cloud';
    if (path.includes('/legacy')) return 'legacy';
    if (path.includes('/dual')) return 'dual';
    return 'cloud'; // default
  };

  const [currentTab, setCurrentTab] = useState(getCurrentTab());

  // Load global provisioning mode
  const { data: modeData } = useQuery({
    queryKey: ['global-provisioning-mode'],
    queryFn: () => settingsService.getProvisioningMode(),
    staleTime: 5 * 60 * 1000,
    onSuccess: (result) => {
      const mode = result?.data?.data?.mode || result?.data?.mode || 'CLOUD';
      setGlobalMode(mode);
    },
  });

  // System health queries (placeholder - will be implemented)
  const { data: cloudHealth, isLoading: cloudLoading, error: cloudError } = useQuery({
    queryKey: ['cloud-health'],
    queryFn: async () => {
      // TODO: Implement /cloud/health endpoint
      return { healthy: true, responseTime: 150, recordCount: 1250 };
    },
    refetchInterval: 30000, // Refresh every 30s
  });

  const { data: legacyHealth, isLoading: legacyLoading, error: legacyError } = useQuery({
    queryKey: ['legacy-health'],
    queryFn: async () => {
      // TODO: Implement /legacy/health endpoint
      return { healthy: true, responseTime: 450, recordCount: 890 };
    },
    refetchInterval: 30000,
  });

  const { data: syncHealth, isLoading: syncLoading, error: syncError } = useQuery({
    queryKey: ['sync-health'],
    queryFn: async () => {
      // TODO: Implement /dual/sync-status endpoint
      return { healthy: true, syncedRecords: 850, conflicts: 5, lastSyncTime: new Date() };
    },
    refetchInterval: 30000,
  });

  // Update URL when tab changes
  const handleTabChange = (event, newValue) => {
    const selectedTab = tabs.find(t => t.value === newValue);
    if (selectedTab) {
      navigate(selectedTab.path);
      setCurrentTab(newValue);
    }
  };

  // Update tab when URL changes
  useEffect(() => {
    setCurrentTab(getCurrentTab());
  }, [location.pathname]);

  const currentTabConfig = tabs.find(t => t.value === currentTab) || tabs[0];

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={3}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <Typography variant="h4">🔧 Provisioning Hub</Typography>
          <Chip 
            label={`Global Mode: ${globalMode}`}
            color={globalMode === 'CLOUD' ? 'success' : globalMode === 'LEGACY' ? 'warning' : 'info'}
            variant="filled"
          />
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => window.location.reload()}
          >
            Refresh All
          </Button>
          <Button
            variant="contained"
            startIcon={<TrendingUp />}
            onClick={() => navigate('/analytics')}
          >
            View Analytics
          </Button>
        </Stack>
      </Stack>

      {/* Global Mode Override Notice */}
      {currentTab.toLowerCase() !== globalMode.toLowerCase().replace('_prov', '')} {
        <Alert severity="info" sx={{ mb: 3 }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Tooltip title="Mode Override Active">
              <Warning color="info" />
            </Tooltip>
            <Box>
              <Typography variant="body1" fontWeight="bold">
                Explicit Mode Override
              </Typography>
              <Typography variant="body2">
                You're using <strong>{currentTabConfig.label}</strong> mode, 
                but the global setting is <strong>{globalMode}</strong>. 
                Explicit tabs override the global mode.
              </Typography>
            </Box>
          </Stack>
        </Alert>
      }

      {/* System Health Overview */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            📊 System Health Overview
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <SystemHealthCard 
                system="Cloud (DynamoDB)"
                isLoading={cloudLoading}
                data={cloudHealth}
                error={cloudError}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <SystemHealthCard 
                system="Legacy (RDS MySQL)"
                isLoading={legacyLoading}
                data={legacyHealth}
                error={legacyError}
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 2, textAlign: 'center', height: '100%' }}>
                <Stack spacing={1} alignItems="center">
                  {syncLoading ? <CircularProgress size={20} /> : <Sync color="info" />}
                  <Typography variant="h6" color="info">
                    Sync Status
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {syncLoading ? 'Checking...' : 'Active'}
                  </Typography>
                  {syncHealth && (
                    <>
                      <Chip 
                        size="small" 
                        label={`${syncHealth.syncedRecords || 0} synced`} 
                        color="success"
                      />
                      {syncHealth.conflicts > 0 && (
                        <Chip 
                          size="small" 
                          label={`${syncHealth.conflicts} conflicts`} 
                          color="error"
                        />
                      )}
                      {syncHealth.lastSyncTime && (
                        <Typography variant="caption">
                          Last: {format(new Date(syncHealth.lastSyncTime), 'HH:mm:ss')}
                        </Typography>
                      )}
                    </>
                  )}
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Tab Navigation */}
      <Card sx={{ mb: 3 }}>
        <Tabs
          value={currentTab}
          onChange={handleTabChange}
          variant="fullWidth"
          indicatorColor="primary"
          textColor="primary"
        >
          {tabs.map((tab) => (
            <Tab
              key={tab.value}
              value={tab.value}
              icon={tab.icon}
              label={tab.label}
              sx={{
                '&.Mui-selected': {
                  color: `${tab.color}.main`,
                },
              }}
            />
          ))}
        </Tabs>
      </Card>

      {/* Tab Description */}
      <Alert severity={currentTabConfig.color} sx={{ mb: 3 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          {currentTabConfig.icon}
          <Box>
            <Typography variant="body1" fontWeight="bold">
              {currentTabConfig.label} Mode
            </Typography>
            <Typography variant="body2">
              {currentTabConfig.description}
            </Typography>
          </Box>
        </Stack>
      </Alert>

      {/* Tab Content */}
      <Routes>
        <Route path="cloud" element={<CloudCrud />} />
        <Route path="legacy" element={<LegacyCrud />} />
        <Route path="dual" element={<DualCrud />} />
        <Route path="" element={<Navigate to="cloud" replace />} />
        <Route path="*" element={<Navigate to="cloud" replace />} />
      </Routes>
    </Box>
  );
};

export default ProvisioningHub;