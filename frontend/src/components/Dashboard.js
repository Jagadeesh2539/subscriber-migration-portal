import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Chip,
  LinearProgress,
  CircularProgress,
  IconButton,
  Tooltip,
  Alert
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  People,
  CloudSync,
  Analytics,
  Warning,
  CheckCircle,
  Schedule,
  Refresh,
  Visibility
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { api } from '../api/enhanced';

const Dashboard = ({ user, onNotification, globalStats, onStatsUpdate }) => {
  // State management
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState({
    overview: {
      totalSubscribers: 0,
      activeMigrations: 0,
      completedMigrations: 0,
      systemHealth: 100
    },
    recentActivity: [],
    migrationTrends: [],
    systemStats: [],
    alerts: []
  });
  const [realTimeUpdates, setRealTimeUpdates] = useState(true);

  // Chart colors
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];

  // Load dashboard data on component mount
  useEffect(() => {
    loadDashboardData();
    
    // Set up real-time updates
    let interval;
    if (realTimeUpdates) {
      interval = setInterval(() => {
        loadDashboardData(true); // silent update
      }, 30000); // Update every 30 seconds
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [realTimeUpdates]);

  // Load dashboard data
  const loadDashboardData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      
      const [overview, activity, trends, systemStats, alerts] = await Promise.all([
        api.getDashboardOverview(),
        api.getRecentActivity(),
        api.getMigrationTrends(),
        api.getSystemStatistics(),
        api.getSystemAlerts()
      ]);
      
      setDashboardData({
        overview: overview || dashboardData.overview,
        recentActivity: activity || [],
        migrationTrends: trends || [],
        systemStats: systemStats || [],
        alerts: alerts || []
      });
      
      // Update global stats if callback provided
      if (onStatsUpdate && overview) {
        onStatsUpdate();
      }
    } catch (error) {
      console.error('Error loading dashboard data:', error);
      if (!silent) {
        onNotification('Error loading dashboard data: ' + error.message, 'error');
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Format large numbers
  const formatNumber = (num) => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num?.toLocaleString() || '0';
  };

  // Get trend icon and color
  const getTrendIndicator = (current, previous) => {
    if (!previous || current === previous) {
      return { icon: <Analytics />, color: 'info', text: 'No change' };
    }
    
    const change = ((current - previous) / previous) * 100;
    if (change > 0) {
      return { 
        icon: <TrendingUp />, 
        color: 'success', 
        text: `+${change.toFixed(1)}%` 
      };
    } else {
      return { 
        icon: <TrendingDown />, 
        color: 'error', 
        text: `${change.toFixed(1)}%` 
      };
    }
  };

  // Get activity icon
  const getActivityIcon = (type) => {
    switch (type) {
      case 'migration': return <CloudSync />;
      case 'provisioning': return <People />;
      case 'audit': return <Analytics />;
      default: return <CheckCircle />;
    }
  };

  // Get alert severity color
  const getAlertColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return 'error';
      case 'warning': return 'warning';
      case 'info': return 'info';
      default: return 'default';
    }
  };

  // Format timestamp
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    return new Date(timestamp).toLocaleString();
  };

  if (loading && !dashboardData.overview.totalSubscribers) {
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
            Welcome back, {user?.username || 'User'}!
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Here's an overview of your subscriber migration portal activity
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Refresh Dashboard">
            <IconButton 
              onClick={() => loadDashboardData()}
              disabled={loading}
              color="primary"
            >
              <Refresh />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* System Alerts */}
      {dashboardData.alerts.length > 0 && (
        <Box sx={{ mb: 3 }}>
          {dashboardData.alerts.slice(0, 3).map((alert, index) => (
            <Alert 
              key={index} 
              severity={getAlertColor(alert.severity)}
              sx={{ mb: 1 }}
            >
              <strong>{alert.title}:</strong> {alert.message}
            </Alert>
          ))}
        </Box>
      )}

      {/* Overview Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
            color: 'white',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {formatNumber(dashboardData.overview.totalSubscribers)}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Total Subscribers
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    {getTrendIndicator(dashboardData.overview.totalSubscribers, globalStats.totalSubscribers).icon}
                    <Typography variant="caption" sx={{ ml: 0.5 }}>
                      {getTrendIndicator(dashboardData.overview.totalSubscribers, globalStats.totalSubscribers).text}
                    </Typography>
                  </Box>
                </Box>
                <People sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', 
            color: 'white',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {dashboardData.overview.activeMigrations || 0}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Active Migrations
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    <Schedule sx={{ fontSize: 16 }} />
                    <Typography variant="caption" sx={{ ml: 0.5 }}>
                      Running Now
                    </Typography>
                  </Box>
                </Box>
                <CloudSync sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', 
            color: 'white',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {dashboardData.overview.completedMigrations || 0}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Completed Today
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    <CheckCircle sx={{ fontSize: 16 }} />
                    <Typography variant="caption" sx={{ ml: 0.5 }}>
                      Success Rate: 98%
                    </Typography>
                  </Box>
                </Box>
                <Analytics sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)', 
            color: 'white',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {dashboardData.overview.systemHealth}%
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    System Health
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={dashboardData.overview.systemHealth} 
                    sx={{ 
                      mt: 1, 
                      height: 6, 
                      borderRadius: 3,
                      backgroundColor: 'rgba(255,255,255,0.3)',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: 'white'
                      }
                    }}
                  />
                </Box>
                <CheckCircle sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Charts and Activity */}
      <Grid container spacing={3}>
        {/* Migration Trends Chart */}
        <Grid item xs={12} lg={8}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                Migration Trends (Last 30 Days)
              </Typography>
              {dashboardData.migrationTrends.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={dashboardData.migrationTrends}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <RechartsTooltip />
                    <Line 
                      type="monotone" 
                      dataKey="migrations" 
                      stroke="#8884d8" 
                      strokeWidth={2}
                      dot={{ fill: '#8884d8', strokeWidth: 2, r: 4 }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="successful" 
                      stroke="#82ca9d" 
                      strokeWidth={2}
                      dot={{ fill: '#82ca9d', strokeWidth: 2, r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                  <Typography variant="body2" color="text.secondary">
                    No migration trend data available
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* System Statistics */}
        <Grid item xs={12} lg={4}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                System Distribution
              </Typography>
              {dashboardData.systemStats.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={dashboardData.systemStats}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {dashboardData.systemStats.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                  <Typography variant="body2" color="text.secondary">
                    No system distribution data available
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Recent Activity */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                Recent Activity
              </Typography>
              {dashboardData.recentActivity.length > 0 ? (
                <Box sx={{ height: 320, overflow: 'auto' }}>
                  <List>
                    {dashboardData.recentActivity.map((activity, index) => (
                      <ListItem 
                        key={index}
                        divider={index < dashboardData.recentActivity.length - 1}
                        sx={{ px: 0 }}
                      >
                        <ListItemIcon>
                          {getActivityIcon(activity.type)}
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                {activity.title}
                              </Typography>
                              <Chip 
                                label={activity.status || 'completed'} 
                                size="small" 
                                color={activity.status === 'failed' ? 'error' : 'success'}
                              />
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Typography variant="body2" color="text.secondary">
                                {activity.description}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {formatTimestamp(activity.timestamp)}
                              </Typography>
                            </Box>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </Box>
              ) : (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                  <Typography variant="body2" color="text.secondary">
                    No recent activity
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Quick Actions */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                Quick Actions
              </Typography>
              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={12}>
                  <Paper 
                    sx={{ 
                      p: 2, 
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      '&:hover': {
                        backgroundColor: 'action.hover',
                        transform: 'translateY(-2px)'
                      }
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <CloudSync sx={{ mr: 2, color: 'primary.main' }} />
                      <Box>
                        <Typography variant="body1" sx={{ fontWeight: 500 }}>
                          New Migration Job
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Start a new bulk migration operation
                        </Typography>
                      </Box>
                    </Box>
                  </Paper>
                </Grid>
                
                <Grid item xs={12}>
                  <Paper 
                    sx={{ 
                      p: 2, 
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      '&:hover': {
                        backgroundColor: 'action.hover',
                        transform: 'translateY(-2px)'
                      }
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <People sx={{ mr: 2, color: 'secondary.main' }} />
                      <Box>
                        <Typography variant="body1" sx={{ fontWeight: 500 }}>
                          Add Subscriber
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Provision a new subscriber account
                        </Typography>
                      </Box>
                    </Box>
                  </Paper>
                </Grid>
                
                <Grid item xs={12}>
                  <Paper 
                    sx={{ 
                      p: 2, 
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      '&:hover': {
                        backgroundColor: 'action.hover',
                        transform: 'translateY(-2px)'
                      }
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Analytics sx={{ mr: 2, color: 'info.main' }} />
                      <Box>
                        <Typography variant="body1" sx={{ fontWeight: 500 }}>
                          System Audit
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Compare legacy and cloud data
                        </Typography>
                      </Box>
                    </Box>
                  </Paper>
                </Grid>
                
                <Grid item xs={12}>
                  <Paper 
                    sx={{ 
                      p: 2, 
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      '&:hover': {
                        backgroundColor: 'action.hover',
                        transform: 'translateY(-2px)'
                      }
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Visibility sx={{ mr: 2, color: 'success.main' }} />
                      <Box>
                        <Typography variant="body1" sx={{ fontWeight: 500 }}>
                          View Reports
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Access detailed analytics and reports
                        </Typography>
                      </Box>
                    </Box>
                  </Paper>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;