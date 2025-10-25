import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  IconButton,
  Chip,
  Alert,
  Tabs,
  Tab,
  CircularProgress,
  Tooltip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControlLabel,
  Checkbox,
  DatePicker,
  LocalizationProvider
} from '@mui/material';
import {
  Search,
  Download,
  CloudDownload,
  Storage,
  FilterList,
  Refresh,
  ExpandMore,
  Clear,
  Analytics,
  Compare,
  Visibility,
  GetApp
} from '@mui/icons-material';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { DatePicker as MUIDatePicker } from '@mui/x-date-pickers/DatePicker';
import { api } from '../api/enhanced';

const DataQueryModule = ({ user, onNotification, onStatsUpdate }) => {
  // State management
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  
  // Query state
  const [queryResults, setQueryResults] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  
  // Filter state
  const [filters, setFilters] = useState({
    system: 'cloud', // cloud, legacy, both
    status: 'all',
    plan: 'all',
    region: 'all',
    dateFrom: null,
    dateTo: null,
    searchTerm: '',
    customFilters: []
  });
  
  // Advanced filters
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(false);
  const [customFilter, setCustomFilter] = useState({
    field: '',
    operator: 'equals',
    value: ''
  });
  
  // Export state
  const [exportConfig, setExportConfig] = useState({
    format: 'csv',
    includeHeaders: true,
    selectedFields: [],
    allFields: false
  });
  
  // System statistics
  const [systemStats, setSystemStats] = useState({
    cloud: { total: 0, active: 0, inactive: 0 },
    legacy: { total: 0, active: 0, inactive: 0 }
  });

  // Available fields for export
  const availableFields = [
    { id: 'subscriber_id', label: 'Subscriber ID', required: true },
    { id: 'name', label: 'Name' },
    { id: 'email', label: 'Email' },
    { id: 'phone', label: 'Phone' },
    { id: 'plan', label: 'Plan' },
    { id: 'status', label: 'Status' },
    { id: 'region', label: 'Region' },
    { id: 'created_date', label: 'Created Date' },
    { id: 'last_updated', label: 'Last Updated' },
    { id: 'billing_address', label: 'Billing Address' },
    { id: 'usage_stats', label: 'Usage Statistics' }
  ];
  
  // Filter options
  const plans = ['basic', 'premium', 'enterprise'];
  const regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'];
  const statuses = ['active', 'inactive', 'suspended', 'pending'];
  const operators = [
    { value: 'equals', label: 'Equals' },
    { value: 'contains', label: 'Contains' },
    { value: 'starts_with', label: 'Starts With' },
    { value: 'ends_with', label: 'Ends With' },
    { value: 'greater_than', label: 'Greater Than' },
    { value: 'less_than', label: 'Less Than' }
  ];

  // Load data on component mount and filter changes
  useEffect(() => {
    loadSystemStats();
  }, []);
  
  useEffect(() => {
    if (activeTab === 0) {
      executeQuery();
    }
  }, [page, rowsPerPage, filters, activeTab]);

  // Load system statistics
  const loadSystemStats = async () => {
    try {
      const stats = await api.getSystemStats();
      setSystemStats(stats);
    } catch (error) {
      console.error('Error loading system stats:', error);
    }
  };

  // Execute query
  const executeQuery = async () => {
    try {
      setLoading(true);
      const params = {
        page: page + 1,
        limit: rowsPerPage,
        ...filters,
        custom_filters: filters.customFilters
      };
      
      const response = await api.querySubscribers(params);
      setQueryResults(response.subscribers || []);
      setTotalCount(response.total || 0);
    } catch (error) {
      console.error('Error executing query:', error);
      onNotification('Error executing query: ' + error.message, 'error');
      setQueryResults([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  };

  // Handle filter changes
  const handleFilterChange = (field, value) => {
    setFilters(prev => ({ ...prev, [field]: value }));
    setPage(0); // Reset to first page
  };

  // Add custom filter
  const addCustomFilter = () => {
    if (customFilter.field && customFilter.value) {
      setFilters(prev => ({
        ...prev,
        customFilters: [...prev.customFilters, { ...customFilter, id: Date.now() }]
      }));
      setCustomFilter({ field: '', operator: 'equals', value: '' });
    }
  };

  // Remove custom filter
  const removeCustomFilter = (filterId) => {
    setFilters(prev => ({
      ...prev,
      customFilters: prev.customFilters.filter(f => f.id !== filterId)
    }));
  };

  // Clear all filters
  const clearAllFilters = () => {
    setFilters({
      system: 'cloud',
      status: 'all',
      plan: 'all',
      region: 'all',
      dateFrom: null,
      dateTo: null,
      searchTerm: '',
      customFilters: []
    });
    setPage(0);
  };

  // Handle export field selection
  const handleFieldSelection = (fieldId, selected) => {
    if (selected) {
      setExportConfig(prev => ({
        ...prev,
        selectedFields: [...prev.selectedFields, fieldId]
      }));
    } else {
      setExportConfig(prev => ({
        ...prev,
        selectedFields: prev.selectedFields.filter(id => id !== fieldId)
      }));
    }
  };

  // Select all fields
  const selectAllFields = (selectAll) => {
    if (selectAll) {
      setExportConfig(prev => ({
        ...prev,
        selectedFields: availableFields.map(f => f.id),
        allFields: true
      }));
    } else {
      setExportConfig(prev => ({
        ...prev,
        selectedFields: availableFields.filter(f => f.required).map(f => f.id),
        allFields: false
      }));
    }
  };

  // Export data
  const exportData = async (system = null) => {
    try {
      setExportLoading(true);
      
      const exportParams = {
        ...filters,
        system: system || filters.system,
        format: exportConfig.format,
        fields: exportConfig.selectedFields,
        include_headers: exportConfig.includeHeaders,
        custom_filters: filters.customFilters
      };
      
      const response = await api.exportSubscriberData(exportParams);
      
      // Create and trigger download
      const blob = new Blob([response], { 
        type: exportConfig.format === 'csv' ? 'text/csv' : 'application/json' 
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `subscribers_${system || filters.system}_${new Date().toISOString().split('T')[0]}.${exportConfig.format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      
      onNotification('Data exported successfully', 'success');
    } catch (error) {
      console.error('Error exporting data:', error);
      onNotification('Error exporting data: ' + error.message, 'error');
    } finally {
      setExportLoading(false);
    }
  };

  // Get status chip color
  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'active': return 'success';
      case 'inactive': return 'default';
      case 'suspended': return 'error';
      case 'pending': return 'warning';
      default: return 'default';
    }
  };

  // Get plan chip color
  const getPlanColor = (plan) => {
    switch (plan?.toLowerCase()) {
      case 'basic': return 'info';
      case 'premium': return 'secondary';
      case 'enterprise': return 'primary';
      default: return 'default';
    }
  };

  // Format date
  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  // Tab panel component
  const TabPanel = ({ children, value, index, ...other }) => (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`data-query-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600, color: 'text.primary' }}>
          Data Query & Export
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Query and export subscriber data from cloud and legacy systems with advanced filtering
        </Typography>
      </Box>

      {/* System Statistics */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h6" sx={{ mb: 1 }}>Cloud System</Typography>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {systemStats.cloud.total.toLocaleString()}
                  </Typography>
                  <Typography variant="body2">Total Subscribers</Typography>
                </Box>
                <CloudDownload sx={{ fontSize: 60 }} />
              </Box>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h6">{systemStats.cloud.active.toLocaleString()}</Typography>
                  <Typography variant="caption">Active</Typography>
                </Box>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h6">{systemStats.cloud.inactive.toLocaleString()}</Typography>
                  <Typography variant="caption">Inactive</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h6" sx={{ mb: 1 }}>Legacy System</Typography>
                  <Typography variant="h3" sx={{ fontWeight: 600 }}>
                    {systemStats.legacy.total.toLocaleString()}
                  </Typography>
                  <Typography variant="body2">Total Subscribers</Typography>
                </Box>
                <Storage sx={{ fontSize: 60 }} />
              </Box>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h6">{systemStats.legacy.active.toLocaleString()}</Typography>
                  <Typography variant="caption">Active</Typography>
                </Box>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h6">{systemStats.legacy.inactive.toLocaleString()}</Typography>
                  <Typography variant="caption">Inactive</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Card sx={{ mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(e, newValue) => setActiveTab(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Query Data" />
          <Tab label="Export Center" />
        </Tabs>

        {/* Tab Panel 0: Query Data */}
        <TabPanel value={activeTab} index={0}>
          {/* Filters */}
          <Card sx={{ mb: 3, p: 3 }}>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              <FilterList sx={{ mr: 1 }} />
              Query Filters
            </Typography>
            
            <Grid container spacing={2} sx={{ mb: 2 }}>
              {/* System Selection */}
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>System</InputLabel>
                  <Select
                    value={filters.system}
                    label="System"
                    onChange={(e) => handleFilterChange('system', e.target.value)}
                  >
                    <MenuItem value="cloud">Cloud Only</MenuItem>
                    <MenuItem value="legacy">Legacy Only</MenuItem>
                    <MenuItem value="both">Both Systems</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              {/* Status Filter */}
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={filters.status}
                    label="Status"
                    onChange={(e) => handleFilterChange('status', e.target.value)}
                  >
                    <MenuItem value="all">All Status</MenuItem>
                    {statuses.map(status => (
                      <MenuItem key={status} value={status}>
                        {status.charAt(0).toUpperCase() + status.slice(1)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              {/* Plan Filter */}
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Plan</InputLabel>
                  <Select
                    value={filters.plan}
                    label="Plan"
                    onChange={(e) => handleFilterChange('plan', e.target.value)}
                  >
                    <MenuItem value="all">All Plans</MenuItem>
                    {plans.map(plan => (
                      <MenuItem key={plan} value={plan}>
                        {plan.charAt(0).toUpperCase() + plan.slice(1)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              {/* Region Filter */}
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Region</InputLabel>
                  <Select
                    value={filters.region}
                    label="Region"
                    onChange={(e) => handleFilterChange('region', e.target.value)}
                  >
                    <MenuItem value="all">All Regions</MenuItem>
                    {regions.map(region => (
                      <MenuItem key={region} value={region}>
                        {region}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              {/* Search */}
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  size="small"
                  placeholder="Search subscribers..."
                  value={filters.searchTerm}
                  onChange={(e) => handleFilterChange('searchTerm', e.target.value)}
                  InputProps={{
                    startAdornment: <Search sx={{ color: 'text.secondary', mr: 1 }} />
                  }}
                />
              </Grid>
            </Grid>
            
            {/* Action Buttons */}
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
              <Button
                variant="contained"
                startIcon={<Search />}
                onClick={executeQuery}
                disabled={loading}
              >
                Execute Query
              </Button>
              <Button
                variant="outlined"
                startIcon={<Clear />}
                onClick={clearAllFilters}
              >
                Clear Filters
              </Button>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={loadSystemStats}
              >
                Refresh Stats
              </Button>
            </Box>
            
            {/* Advanced Filters */}
            <Accordion sx={{ mt: 2 }}>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography>Advanced Filters</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2} alignItems="center">
                  <Grid item xs={12} md={3}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Field"
                      value={customFilter.field}
                      onChange={(e) => setCustomFilter(prev => ({ ...prev, field: e.target.value }))}
                    />
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Operator</InputLabel>
                      <Select
                        value={customFilter.operator}
                        label="Operator"
                        onChange={(e) => setCustomFilter(prev => ({ ...prev, operator: e.target.value }))}
                      >
                        {operators.map(op => (
                          <MenuItem key={op.value} value={op.value}>{op.label}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Value"
                      value={customFilter.value}
                      onChange={(e) => setCustomFilter(prev => ({ ...prev, value: e.target.value }))}
                    />
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Button
                      variant="outlined"
                      onClick={addCustomFilter}
                      disabled={!customFilter.field || !customFilter.value}
                    >
                      Add Filter
                    </Button>
                  </Grid>
                </Grid>
                
                {/* Active Custom Filters */}
                {filters.customFilters.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="body2" gutterBottom>Active Custom Filters:</Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      {filters.customFilters.map((filter) => (
                        <Chip
                          key={filter.id}
                          label={`${filter.field} ${filter.operator} ${filter.value}`}
                          onDelete={() => removeCustomFilter(filter.id)}
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                      ))}
                    </Box>
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          </Card>
          
          {/* Results */}
          <Card>
            <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="h6">
                Query Results ({totalCount.toLocaleString()} records)
              </Typography>
              {queryResults.length > 0 && (
                <Button
                  variant="outlined"
                  startIcon={<Download />}
                  onClick={() => exportData()}
                  disabled={exportLoading}
                >
                  Export Results
                </Button>
              )}
            </Box>
            
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: 'grey.100' }}>
                    <TableCell sx={{ fontWeight: 600 }}>ID</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Email</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Plan</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Region</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>System</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                        <CircularProgress size={40} />
                        <Typography variant="body2" sx={{ mt: 2 }}>Executing query...</Typography>
                      </TableCell>
                    </TableRow>
                  ) : queryResults.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                        <Search sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                        <Typography variant="h6" color="text.secondary" gutterBottom>
                          No Results Found
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Try adjusting your filters or search criteria
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    queryResults.map((subscriber, index) => (
                      <TableRow key={`${subscriber.subscriber_id}-${index}`} hover>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            {subscriber.subscriber_id}
                          </Typography>
                        </TableCell>
                        <TableCell>{subscriber.name}</TableCell>
                        <TableCell>{subscriber.email}</TableCell>
                        <TableCell>
                          <Chip 
                            label={subscriber.plan} 
                            color={getPlanColor(subscriber.plan)}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={subscriber.status} 
                            color={getStatusColor(subscriber.status)}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>{subscriber.region}</TableCell>
                        <TableCell>
                          <Chip 
                            label={subscriber.system || 'Unknown'} 
                            color={subscriber.system === 'cloud' ? 'primary' : 'secondary'}
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            
            <TablePagination
              component="div"
              count={totalCount}
              page={page}
              onPageChange={(event, newPage) => setPage(newPage)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={(event) => {
                setRowsPerPage(parseInt(event.target.value, 10));
                setPage(0);
              }}
              rowsPerPageOptions={[10, 25, 50, 100]}
            />
          </Card>
        </TabPanel>

        {/* Tab Panel 1: Export Center */}
        <TabPanel value={activeTab} index={1}>
          <Grid container spacing={3}>
            {/* Export Configuration */}
            <Grid item xs={12} md={6}>
              <Card sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>
                  Export Configuration
                </Typography>
                
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <FormControl fullWidth>
                      <InputLabel>Export Format</InputLabel>
                      <Select
                        value={exportConfig.format}
                        label="Export Format"
                        onChange={(e) => setExportConfig(prev => ({ ...prev, format: e.target.value }))}
                      >
                        <MenuItem value="csv">CSV</MenuItem>
                        <MenuItem value="json">JSON</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={
                        <Checkbox 
                          checked={exportConfig.includeHeaders}
                          onChange={(e) => setExportConfig(prev => ({ ...prev, includeHeaders: e.target.checked }))}
                        />
                      }
                      label="Include Headers"
                    />
                  </Grid>
                  
                  <Grid item xs={12}>
                    <Typography variant="body2" gutterBottom>Select Fields to Export:</Typography>
                    <FormControlLabel
                      control={
                        <Checkbox 
                          checked={exportConfig.allFields}
                          onChange={(e) => selectAllFields(e.target.checked)}
                        />
                      }
                      label="Select All Fields"
                      sx={{ mb: 1 }}
                    />
                    
                    <Box sx={{ maxHeight: 200, overflow: 'auto', border: 1, borderColor: 'divider', borderRadius: 1, p: 1 }}>
                      {availableFields.map((field) => (
                        <FormControlLabel
                          key={field.id}
                          control={
                            <Checkbox 
                              checked={exportConfig.selectedFields.includes(field.id)}
                              onChange={(e) => handleFieldSelection(field.id, e.target.checked)}
                              disabled={field.required}
                            />
                          }
                          label={field.label + (field.required ? ' (Required)' : '')}
                          sx={{ display: 'block' }}
                        />
                      ))}
                    </Box>
                  </Grid>
                </Grid>
              </Card>
            </Grid>
            
            {/* Export Actions */}
            <Grid item xs={12} md={6}>
              <Card sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>
                  Export Actions
                </Typography>
                
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <Card sx={{ p: 2, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <CloudDownload sx={{ mr: 2 }} />
                        <Typography variant="h6">Cloud System Export</Typography>
                      </Box>
                      <Typography variant="body2" sx={{ mb: 2 }}>
                        Export all subscriber data from the cloud system
                      </Typography>
                      <Button
                        variant="contained"
                        startIcon={exportLoading ? <CircularProgress size={16} /> : <Download />}
                        onClick={() => exportData('cloud')}
                        disabled={exportLoading || exportConfig.selectedFields.length === 0}
                        sx={{ bgcolor: 'white', color: 'primary.main', '&:hover': { bgcolor: 'grey.100' } }}
                      >
                        Export Cloud Data
                      </Button>
                    </Card>
                  </Grid>
                  
                  <Grid item xs={12}>
                    <Card sx={{ p: 2, background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <Storage sx={{ mr: 2 }} />
                        <Typography variant="h6">Legacy System Export</Typography>
                      </Box>
                      <Typography variant="body2" sx={{ mb: 2 }}>
                        Export all subscriber data from the legacy system
                      </Typography>
                      <Button
                        variant="contained"
                        startIcon={exportLoading ? <CircularProgress size={16} /> : <Download />}
                        onClick={() => exportData('legacy')}
                        disabled={exportLoading || exportConfig.selectedFields.length === 0}
                        sx={{ bgcolor: 'white', color: 'secondary.main', '&:hover': { bgcolor: 'grey.100' } }}
                      >
                        Export Legacy Data
                      </Button>
                    </Card>
                  </Grid>
                  
                  <Grid item xs={12}>
                    <Card sx={{ p: 2, background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', color: 'white' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <Compare sx={{ mr: 2 }} />
                        <Typography variant="h6">Combined Export</Typography>
                      </Box>
                      <Typography variant="body2" sx={{ mb: 2 }}>
                        Export combined data from both systems with system identifiers
                      </Typography>
                      <Button
                        variant="contained"
                        startIcon={exportLoading ? <CircularProgress size={16} /> : <Download />}
                        onClick={() => exportData('both')}
                        disabled={exportLoading || exportConfig.selectedFields.length === 0}
                        sx={{ bgcolor: 'white', color: 'info.main', '&:hover': { bgcolor: 'grey.100' } }}
                      >
                        Export Combined Data
                      </Button>
                    </Card>
                  </Grid>
                </Grid>
                
                {exportConfig.selectedFields.length === 0 && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    Please select at least one field to export
                  </Alert>
                )}
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
      </Card>
    </Box>
  );
};

export default DataQueryModule;