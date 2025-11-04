import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Alert,
  Chip,
  LinearProgress,
  CircularProgress,
  IconButton,
  Tooltip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Switch,
  FormControlLabel,
  Badge,
  Paper
} from '@mui/material';
import {
  Refresh,
  NotificationsActive,
  Warning,
  Error,
  CheckCircle,
  Info,
  Computer,
  CloudSync,
  Storage,
  NetworkCheck,
  Speed,
  Memory,
  Timeline
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { api } from '../api/enhanced';

const MonitoringDashboard = ({ user, onNotification }) => {
  // State management
  const [loading, setLoading] = useState(true);
  const [realTimeEnabled, setRealTimeEnabled] = useState(true);
  const [monitoringData, setMonitoringData] = useState({
    systemHealth: {
      overall: 98,
      cloud: 99,
      legacy: 97,
      network: 98
    },
    alerts: [],
    performance: [],
    resources: {
      cpu: 45,
      memory: 62,
      storage: 78,
      network: 23
    },
    services: [],
    migrations: {
      active: 0,
      queued: 0,
      completed: 0,
      failed: 0
    }
  });

  // Alert severity colors
  const alertColors = {
    critical: 'error',
    high: 'error',
    medium: 'warning',
    low: 'info',
    info: 'info'
  };

  // Service status colors
  const statusColors = {
    healthy: 'success',
    degraded: 'warning',
    critical: 'error',
    down: 'error'
  };

  // Load monitoring data on component mount
  useEffect(() => {
    loadMonitoringData();
    
    // Set up real-time updates
    let interval;
    if (realTimeEnabled) {
      interval = setInterval(() => {
        loadMonitoringData(true); // silent update
      }, 5000); // Update every 5 seconds
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [realTimeEnabled]);

  // Load monitoring data
  const loadMonitoringData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      
      const [alerts, performance, resources, services, migrations] = await Promise.all([
        api.getSystemAlerts(),
        api.getPerformanceMetrics(),
        api.getResourceUtilization(),
        api.getServiceStatus(),
        api.getMigrationMonitoring()
      ]);
      
      setMonitoringData(prev => ({
        systemHealth: {
          overall: calculateOverallHealth(services),
          cloud: services?.find(s => s.name === 'cloud')?.health || 98,
          legacy: services?.find(s => s.name === 'legacy')?.health || 97,
          network: resources?.network || 98
        },
        alerts: alerts || [],
        performance: performance || prev.performance,
        resources: resources || prev.resources,
        services: services || [],
        migrations: migrations || prev.migrations
      }));
    } catch (error) {
      console.error('Error loading monitoring data:', error);
      if (!silent) {
        onNotification('Error loading monitoring data: ' + error.message, 'error');
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Calculate overall system health
  const calculateOverallHealth = (services) => {
    if (!services || services.length === 0) return 98;
    const total = services.reduce((sum, service) => sum + (service.health || 0), 0);
    return Math.round(total / services.length);
  };

  // Get health color
  const getHealthColor = (health) => {
    if (health >= 95) return 'success';
    if (health >= 80) return 'warning';
    return 'error';
  };

  // Get resource utilization color
  const getResourceColor = (usage) => {
    if (usage >= 90) return 'error';
    if (usage >= 70) return 'warning';
    return 'success';
  };

  // Format timestamp
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    return new Date(timestamp).toLocaleString();
  };

  // Get alert icon
  const getAlertIcon = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical':
      case 'high':
        return <Error />;
      case 'medium':
        return <Warning />;
      case 'low':
      case 'info':
        return <Info />;
      default:
        return <NotificationsActive />;
    }
  };

  if (loading && monitoringData.alerts.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress size={60} />
      </Box>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary' }}>
            System Monitoring
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Real-time monitoring of migration portal systems and performance
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControlLabel
            control={
              <Switch 
                checked={realTimeEnabled}
                onChange={(e) => setRealTimeEnabled(e.target.checked)}
                color="primary"
              />
            }
            label="Real-time Updates"
          />
          <Tooltip title="Refresh Data">
            <IconButton 
              onClick={() => loadMonitoringData()}
              disabled={loading}
              color="primary"
            >
              <Refresh />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Active Alerts */}
      {monitoringData.alerts.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
            <Badge badgeContent={monitoringData.alerts.length} color="error" sx={{ mr: 2 }}>
              <NotificationsActive />
            </Badge>
            Active Alerts
          </Typography>
          {monitoringData.alerts.slice(0, 3).map((alert, index) => (
            <Alert 
              key={index} 
              severity={alertColors[alert.severity] || 'info'}
              sx={{ mb: 1 }}
              icon={getAlertIcon(alert.severity)}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                <Box>
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>
                    {alert.title}
                  </Typography>
                  <Typography variant="body2">
                    {alert.message}
                  </Typography>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  {formatTimestamp(alert.timestamp)}
                </Typography>
              </Box>
            </Alert>
          ))}
        </Box>
      )}

      {/* System Health Overview */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={3}>
          <Card sx={{ 
            background: `linear-gradient(135deg, ${
              monitoringData.systemHealth.overall >= 95 ? '#4CAF50' :
              monitoringData.systemHealth.overall >= 80 ? '#FF9800' : '#F44336'
            } 0%, rgba(255,255,255,0.1) 100%)`,
            color: 'white'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {monitoringData.systemHealth.overall}%
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Overall Health
                  </Typography>
                </Box>
                <Computer sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h4" color="primary.main" sx={{ fontWeight: 600 }}>
                    {monitoringData.systemHealth.cloud}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Cloud System
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.systemHealth.cloud} 
                    color={getHealthColor(monitoringData.systemHealth.cloud)}
                    sx={{ mt: 1, height: 6, borderRadius: 3 }}
                  />
                </Box>
                <CloudSync sx={{ fontSize: 40, color: 'primary.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h4" color="secondary.main" sx={{ fontWeight: 600 }}>
                    {monitoringData.systemHealth.legacy}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Legacy System
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.systemHealth.legacy} 
                    color={getHealthColor(monitoringData.systemHealth.legacy)}
                    sx={{ mt: 1, height: 6, borderRadius: 3 }}
                  />
                </Box>
                <Storage sx={{ fontSize: 40, color: 'secondary.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h4" color="info.main" sx={{ fontWeight: 600 }}>
                    {monitoringData.systemHealth.network}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Network Health
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.systemHealth.network} 
                    color={getHealthColor(monitoringData.systemHealth.network)}
                    sx={{ mt: 1, height: 6, borderRadius: 3 }}
                  />
                </Box>
                <NetworkCheck sx={{ fontSize: 40, color: 'info.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Performance Metrics and Resource Utilization */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* Performance Chart */}
        <Grid item xs={12} lg={8}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500, display: 'flex', alignItems: 'center' }}>
                <Timeline sx={{ mr: 1 }} />
                Performance Metrics (Last 24 Hours)
              </Typography>
              {monitoringData.performance.length > 0 ? (
                <ResponsiveContainer width="100%" height={320}>
                  <AreaChart data={monitoringData.performance}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" tickFormatter={(time) => new Date(time).toLocaleTimeString()} />
                    <YAxis domain={[0, 100]} />
                    <RechartsTooltip 
                      labelFormatter={(time) => new Date(time).toLocaleString()}
                      formatter={(value, name) => [`${value}%`, name.charAt(0).toUpperCase() + name.slice(1)]}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="cpu" 
                      stackId="1"
                      stroke="#8884d8" 
                      fill="#8884d8"
                      fillOpacity={0.6}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="memory" 
                      stackId="1"
                      stroke="#82ca9d" 
                      fill="#82ca9d"
                      fillOpacity={0.6}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="network" 
                      stackId="1"
                      stroke="#ffc658" 
                      fill="#ffc658"
                      fillOpacity={0.6}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 320 }}>
                  <Typography variant="body2" color="text.secondary">
                    Loading performance data...
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Resource Utilization */}
        <Grid item xs={12} lg={4}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500, display: 'flex', alignItems: 'center' }}>
                <Speed sx={{ mr: 1 }} />
                Current Resource Usage
              </Typography>
              <Box sx={{ mt: 3 }}>
                {/* CPU Usage */}
                <Box sx={{ mb: 3 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">CPU Usage</Typography>
                    <Typography variant="body2" color={getResourceColor(monitoringData.resources.cpu)}>
                      {monitoringData.resources.cpu}%
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.resources.cpu} 
                    color={getResourceColor(monitoringData.resources.cpu)}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>

                {/* Memory Usage */}
                <Box sx={{ mb: 3 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Memory Usage</Typography>
                    <Typography variant="body2" color={getResourceColor(monitoringData.resources.memory)}>
                      {monitoringData.resources.memory}%
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.resources.memory} 
                    color={getResourceColor(monitoringData.resources.memory)}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>

                {/* Storage Usage */}
                <Box sx={{ mb: 3 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Storage Usage</Typography>
                    <Typography variant="body2" color={getResourceColor(monitoringData.resources.storage)}>
                      {monitoringData.resources.storage}%
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.resources.storage} 
                    color={getResourceColor(monitoringData.resources.storage)}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>

                {/* Network Usage */}
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Network Usage</Typography>
                    <Typography variant="body2" color={getResourceColor(monitoringData.resources.network)}>
                      {monitoringData.resources.network}%
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={monitoringData.resources.network} 
                    color={getResourceColor(monitoringData.resources.network)}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Service Status and Migration Monitoring */}
      <Grid container spacing={3}>
        {/* Service Status */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                Service Status
              </Typography>
              <TableContainer sx={{ maxHeight: 320 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Service</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Health</TableCell>
                      <TableCell>Last Check</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {monitoringData.services.length > 0 ? (
                      monitoringData.services.map((service, index) => (
                        <TableRow key={index}>
                          <TableCell>
                            <Typography variant="body2" sx={{ fontWeight: 500 }}>
                              {service.name}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={service.status} 
                              color={statusColors[service.status] || 'default'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">
                              {service.health}%
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {formatTimestamp(service.lastCheck)}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={4} align="center">
                          <Typography variant="body2" color="text.secondary">
                            Loading service status...
                          </Typography>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Migration Monitoring */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                Migration Status
              </Typography>
              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'primary.light', color: 'white' }}>
                    <Typography variant="h4" sx={{ fontWeight: 600 }}>
                      {monitoringData.migrations.active}
                    </Typography>
                    <Typography variant="body2">Active</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'warning.light', color: 'white' }}>
                    <Typography variant="h4" sx={{ fontWeight: 600 }}>
                      {monitoringData.migrations.queued}
                    </Typography>
                    <Typography variant="body2">Queued</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'success.light', color: 'white' }}>
                    <Typography variant="h4" sx={{ fontWeight: 600 }}>
                      {monitoringData.migrations.completed}
                    </Typography>
                    <Typography variant="body2">Completed</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={6}>
                  <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'error.light', color: 'white' }}>
                    <Typography variant="h4" sx={{ fontWeight: 600 }}>
                      {monitoringData.migrations.failed}
                    </Typography>
                    <Typography variant="body2">Failed</Typography>
                  </Paper>
                </Grid>
              </Grid>
              
              <Box sx={{ mt: 3 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  System Performance Summary
                </Typography>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="body2">Success Rate</Typography>
                  <Typography variant="body2" color="success.main" sx={{ fontWeight: 500 }}>
                    98.5%
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="body2">Avg. Processing Time</Typography>
                  <Typography variant="body2">2.3s</Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="body2">Throughput</Typography>
                  <Typography variant="body2">450 rec/min</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MonitoringDashboard;