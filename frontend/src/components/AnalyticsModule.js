import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tabs,
  Tab,
  CircularProgress,
  Tooltip,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert
} from '@mui/material';
import {
  Assessment,
  TrendingUp,
  TrendingDown,
  Download,
  Refresh,
  DateRange,
  FilterList,
  BarChart,
  Timeline,
  PieChart,
  ShowChart
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  BarChart as RechartsBarChart,
  Bar,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  AreaChart,
  Area,
  ComposedChart
} from 'recharts';
import { api } from '../api/enhanced';

const AnalyticsModule = ({ user, onNotification }) => {
  // State management
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('30d');
  const [analyticsData, setAnalyticsData] = useState({
    overview: {
      totalMigrations: 0,
      successRate: 0,
      avgProcessingTime: 0,
      dataTransferred: 0,
      trends: {
        migrationsChange: 0,
        successRateChange: 0,
        performanceChange: 0
      }
    },
    migrationTrends: [],
    systemPerformance: [],
    errorAnalysis: [],
    regionDistribution: [],
    planDistribution: [],
    timeBasedAnalytics: [],
    topErrors: [],
    recommendations: []
  });

  // Chart colors
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D', '#FFC658', '#FF7C7C'];

  // Time range options
  const timeRanges = [
    { value: '7d', label: 'Last 7 days' },
    { value: '30d', label: 'Last 30 days' },
    { value: '90d', label: 'Last 90 days' },
    { value: '1y', label: 'Last year' }
  ];

  // Load analytics data on component mount and time range change
  useEffect(() => {
    loadAnalyticsData();
  }, [timeRange, activeTab]);

  // Load analytics data
  const loadAnalyticsData = async () => {
    try {
      setLoading(true);
      
      const [overview, trends, performance, errors, regions, plans, timeAnalytics, topErrors, recommendations] = await Promise.all([
        api.getAnalyticsOverview(timeRange),
        api.getMigrationTrends(timeRange),
        api.getSystemPerformanceAnalytics(timeRange),
        api.getErrorAnalysis(timeRange),
        api.getRegionDistribution(timeRange),
        api.getPlanDistribution(timeRange),
        api.getTimeBasedAnalytics(timeRange),
        api.getTopErrors(timeRange),
        api.getAnalyticsRecommendations(timeRange)
      ]);
      
      setAnalyticsData({
        overview: overview || analyticsData.overview,
        migrationTrends: trends || [],
        systemPerformance: performance || [],
        errorAnalysis: errors || [],
        regionDistribution: regions || [],
        planDistribution: plans || [],
        timeBasedAnalytics: timeAnalytics || [],
        topErrors: topErrors || [],
        recommendations: recommendations || []
      });
    } catch (error) {
      console.error('Error loading analytics data:', error);
      onNotification('Error loading analytics data: ' + error.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Export analytics report
  const exportReport = async () => {
    try {
      const response = await api.exportAnalyticsReport({
        timeRange,
        includeCharts: true,
        format: 'pdf'
      });
      
      // Create and trigger download
      const blob = new Blob([response], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `analytics_report_${timeRange}_${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      
      onNotification('Analytics report exported successfully', 'success');
    } catch (error) {
      console.error('Error exporting report:', error);
      onNotification('Error exporting report: ' + error.message, 'error');
    }
  };

  // Format large numbers
  const formatNumber = (num) => {
    if (!num) return '0';
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toLocaleString();
  };

  // Get trend indicator
  const getTrendIndicator = (change) => {
    if (change > 0) {
      return { icon: <TrendingUp color="success" />, color: 'success', text: `+${change.toFixed(1)}%` };
    } else if (change < 0) {
      return { icon: <TrendingDown color="error" />, color: 'error', text: `${change.toFixed(1)}%` };
    }
    return { icon: <Assessment color="info" />, color: 'info', text: 'No change' };
  };

  // Get severity color
  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'info';
      default: return 'default';
    }
  };

  // Tab panel component
  const TabPanel = ({ children, value, index, ...other }) => (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`analytics-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary' }}>
            Analytics & Reports
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Comprehensive analytics and insights for migration portal operations
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Time Range</InputLabel>
            <Select
              value={timeRange}
              label="Time Range"
              onChange={(e) => setTimeRange(e.target.value)}
              startAdornment={<DateRange sx={{ mr: 1, color: 'action.active' }} />}
            >
              {timeRanges.map((range) => (
                <MenuItem key={range.value} value={range.value}>
                  {range.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Tooltip title="Refresh Data">
            <IconButton 
              onClick={loadAnalyticsData}
              disabled={loading}
              color="primary"
            >
              <Refresh />
            </IconButton>
          </Tooltip>
          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={exportReport}
          >
            Export Report
          </Button>
        </Box>
      </Box>

      {/* Overview Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {formatNumber(analyticsData.overview.totalMigrations)}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Total Migrations
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    {getTrendIndicator(analyticsData.overview.trends.migrationsChange).icon}
                    <Typography variant="caption" sx={{ ml: 0.5 }}>
                      {getTrendIndicator(analyticsData.overview.trends.migrationsChange).text}
                    </Typography>
                  </Box>
                </Box>
                <Assessment sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {analyticsData.overview.successRate}%
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Success Rate
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    {getTrendIndicator(analyticsData.overview.trends.successRateChange).icon}
                    <Typography variant="caption" sx={{ ml: 0.5 }}>
                      {getTrendIndicator(analyticsData.overview.trends.successRateChange).text}
                    </Typography>
                  </Box>
                </Box>
                <TrendingUp sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {analyticsData.overview.avgProcessingTime}s
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Avg. Processing Time
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                    {getTrendIndicator(analyticsData.overview.trends.performanceChange).icon}
                    <Typography variant="caption" sx={{ ml: 0.5 }}>
                      {getTrendIndicator(analyticsData.overview.trends.performanceChange).text}
                    </Typography>
                  </Box>
                </Box>
                <Timeline sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {formatNumber(analyticsData.overview.dataTransferred)}GB
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Data Transferred
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.8 }}>
                    {timeRanges.find(r => r.value === timeRange)?.label}
                  </Typography>
                </Box>
                <BarChart sx={{ fontSize: 60, opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Card>
        <Tabs 
          value={activeTab} 
          onChange={(e, newValue) => setActiveTab(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Migration Analytics" />
          <Tab label="Performance Analysis" />
          <Tab label="Error Analysis" />
          <Tab label="Distribution Reports" />
        </Tabs>

        {/* Tab Panel 0: Migration Analytics */}
        <TabPanel value={activeTab} index={0}>
          <Grid container spacing={3}>
            {/* Migration Trends */}
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Migration Trends Over Time
                  </Typography>
                  {analyticsData.migrationTrends.length > 0 ? (
                    <ResponsiveContainer width="100%" height={400}>
                      <ComposedChart data={analyticsData.migrationTrends}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis yAxisId="left" />
                        <YAxis yAxisId="right" orientation="right" />
                        <RechartsTooltip />
                        <Bar yAxisId="left" dataKey="total" fill="#8884d8" name="Total Migrations" />
                        <Line yAxisId="right" type="monotone" dataKey="success_rate" stroke="#82ca9d" strokeWidth={3} name="Success Rate (%)" />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">No trend data available</Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Tab Panel 1: Performance Analysis */}
        <TabPanel value={activeTab} index={1}>
          <Grid container spacing={3}>
            {/* System Performance */}
            <Grid item xs={12} lg={8}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    System Performance Metrics
                  </Typography>
                  {analyticsData.systemPerformance.length > 0 ? (
                    <ResponsiveContainer width="100%" height={400}>
                      <AreaChart data={analyticsData.systemPerformance}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="timestamp" />
                        <YAxis />
                        <RechartsTooltip />
                        <Area type="monotone" dataKey="response_time" stackId="1" stroke="#8884d8" fill="#8884d8" name="Response Time (ms)" />
                        <Area type="monotone" dataKey="throughput" stackId="2" stroke="#82ca9d" fill="#82ca9d" name="Throughput (req/min)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">No performance data available</Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Time-based Analytics */}
            <Grid item xs={12} lg={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Peak Usage Hours
                  </Typography>
                  {analyticsData.timeBasedAnalytics.length > 0 ? (
                    <ResponsiveContainer width="100%" height={400}>
                      <RechartsBarChart data={analyticsData.timeBasedAnalytics}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="hour" />
                        <YAxis />
                        <RechartsTooltip />
                        <Bar dataKey="requests" fill="#8884d8" />
                      </RechartsBarChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">No time-based data available</Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Tab Panel 2: Error Analysis */}
        <TabPanel value={activeTab} index={2}>
          <Grid container spacing={3}>
            {/* Error Trends */}
            <Grid item xs={12} lg={8}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Error Trends
                  </Typography>
                  {analyticsData.errorAnalysis.length > 0 ? (
                    <ResponsiveContainer width="100%" height={400}>
                      <LineChart data={analyticsData.errorAnalysis}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <RechartsTooltip />
                        <Line type="monotone" dataKey="total_errors" stroke="#ff7300" strokeWidth={2} name="Total Errors" />
                        <Line type="monotone" dataKey="critical_errors" stroke="#ff0000" strokeWidth={2} name="Critical Errors" />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">No error data available</Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Top Errors */}
            <Grid item xs={12} lg={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Top Error Types
                  </Typography>
                  <TableContainer sx={{ maxHeight: 400 }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Error Type</TableCell>
                          <TableCell>Count</TableCell>
                          <TableCell>Severity</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {analyticsData.topErrors.length > 0 ? (
                          analyticsData.topErrors.map((error, index) => (
                            <TableRow key={index}>
                              <TableCell>
                                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                  {error.type}
                                </Typography>
                              </TableCell>
                              <TableCell>{error.count}</TableCell>
                              <TableCell>
                                <Chip 
                                  label={error.severity} 
                                  color={getSeverityColor(error.severity)}
                                  size="small"
                                />
                              </TableCell>
                            </TableRow>
                          ))
                        ) : (
                          <TableRow>
                            <TableCell colSpan={3} align="center">
                              {loading ? <CircularProgress size={20} /> : 
                                <Typography variant="body2" color="text.secondary">No error data</Typography>
                              }
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Tab Panel 3: Distribution Reports */}
        <TabPanel value={activeTab} index={3}>
          <Grid container spacing={3}>
            {/* Region Distribution */}
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Regional Distribution
                  </Typography>
                  {analyticsData.regionDistribution.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <RechartsPieChart>
                        <Pie
                          data={analyticsData.regionDistribution}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                        >
                          {analyticsData.regionDistribution.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip />
                      </RechartsPieChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">No region data available</Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Plan Distribution */}
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Plan Distribution
                  </Typography>
                  {analyticsData.planDistribution.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <RechartsBarChart data={analyticsData.planDistribution}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="plan" />
                        <YAxis />
                        <RechartsTooltip />
                        <Bar dataKey="count" fill="#82ca9d" />
                      </RechartsBarChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">No plan data available</Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Recommendations */}
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 500 }}>
                    Analytics Recommendations
                  </Typography>
                  {analyticsData.recommendations.length > 0 ? (
                    <Box sx={{ space: 2 }}>
                      {analyticsData.recommendations.map((recommendation, index) => (
                        <Alert 
                          key={index} 
                          severity={getSeverityColor(recommendation.priority)}
                          sx={{ mb: 2 }}
                        >
                          <Typography variant="body1" sx={{ fontWeight: 500 }}>
                            {recommendation.title}
                          </Typography>
                          <Typography variant="body2">
                            {recommendation.description}
                          </Typography>
                          {recommendation.action && (
                            <Button 
                              size="small" 
                              sx={{ mt: 1 }}
                              color="inherit"
                            >
                              {recommendation.action}
                            </Button>
                          )}
                        </Alert>
                      ))}
                    </Box>
                  ) : (
                    <Box sx={{ textAlign: 'center', py: 4 }}>
                      {loading ? <CircularProgress /> : 
                        <Typography variant="body2" color="text.secondary">
                          No recommendations available
                        </Typography>
                      }
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
      </Card>
    </Box>
  );
};

export default AnalyticsModule;