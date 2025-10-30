import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { apiService, apiUtils } from '../api/apiClient';

// Query Keys - Centralized for better cache management
export const queryKeys = {
  // Authentication
  auth: ['auth'],
  authUser: ['auth', 'user'],
  
  // Dashboard
  dashboard: ['dashboard'],
  dashboardStats: ['dashboard', 'stats'],
  dashboardHealth: ['dashboard', 'health'],
  dashboardActivity: (limit) => ['dashboard', 'activity', limit],
  
  // Subscribers
  subscribers: ['subscribers'],
  subscriberList: (params) => ['subscribers', 'list', params],
  subscriber: (id) => ['subscribers', id],
  subscriberSearch: (query, filters) => ['subscribers', 'search', query, filters],
  
  // Migration
  migration: ['migration'],
  migrationJobs: (params) => ['migration', 'jobs', params],
  migrationJob: (id) => ['migration', 'jobs', id],
  
  // Analytics
  analytics: ['analytics'],
  analyticsMetrics: (timeRange) => ['analytics', 'metrics', timeRange],
  analyticsPerformance: (params) => ['analytics', 'performance', params],
  analyticsUsage: (params) => ['analytics', 'usage', params],
  
  // Monitoring
  monitoring: ['monitoring'],
  monitoringStatus: ['monitoring', 'status'],
  monitoringAlerts: (params) => ['monitoring', 'alerts', params],
  monitoringMetrics: (metric, timeRange) => ['monitoring', 'metrics', metric, timeRange],
  
  // Users
  users: ['users'],
  userList: (params) => ['users', 'list', params],
  user: (id) => ['users', id],
  userProfile: ['users', 'profile'],
  
  // Settings
  settings: ['settings'],
  settingsAll: ['settings', 'all'],
  settingsProvisioningMode: ['settings', 'provisioning-mode'],
  
  // Audit
  audit: ['audit'],
  auditLogs: (params) => ['audit', 'logs', params],
  auditLog: (id) => ['audit', 'logs', id],
};

// === DASHBOARD HOOKS ===
export const useDashboardStats = () => {
  return useQuery({
    queryKey: queryKeys.dashboardStats,
    queryFn: () => apiService.dashboard.getStats(),
    select: (response) => response.data,
    staleTime: 2 * 60 * 1000, // 2 minutes
    refetchInterval: 5 * 60 * 1000, // Auto-refetch every 5 minutes
  });
};

export const useSystemHealth = () => {
  return useQuery({
    queryKey: queryKeys.dashboardHealth,
    queryFn: () => apiService.dashboard.getSystemHealth(),
    select: (response) => response.data,
    staleTime: 30 * 1000, // 30 seconds
    refetchInterval: 60 * 1000, // Auto-refetch every minute
  });
};

export const useRecentActivity = (limit = 10) => {
  return useQuery({
    queryKey: queryKeys.dashboardActivity(limit),
    queryFn: () => apiService.dashboard.getRecentActivity(limit),
    select: (response) => response.data,
    staleTime: 1 * 60 * 1000, // 1 minute
  });
};

// === SUBSCRIBER HOOKS ===
export const useSubscribers = (params = {}) => {
  return useQuery({
    queryKey: queryKeys.subscriberList(params),
    queryFn: () => apiService.subscribers.getAll(params),
    select: (response) => response.data,
    keepPreviousData: true, // Keep previous data while fetching new
  });
};

export const useSubscriber = (id, enabled = true) => {
  return useQuery({
    queryKey: queryKeys.subscriber(id),
    queryFn: () => apiService.subscribers.getById(id),
    select: (response) => response.data,
    enabled: !!id && enabled,
  });
};

export const useSubscriberSearch = (query, filters = {}, enabled = true) => {
  return useQuery({
    queryKey: queryKeys.subscriberSearch(query, filters),
    queryFn: () => apiService.subscribers.search(query, filters),
    select: (response) => response.data,
    enabled: !!query && enabled,
    staleTime: 30 * 1000, // 30 seconds for search results
  });
};

// Infinite query for large subscriber lists
export const useInfiniteSubscribers = (params = {}) => {
  return useInfiniteQuery({
    queryKey: ['subscribers', 'infinite', params],
    queryFn: ({ pageParam = 0 }) => 
      apiService.subscribers.getAll({ ...params, offset: pageParam }),
    select: (data) => ({
      pages: data.pages.map(page => page.data),
      pageParams: data.pageParams,
    }),
    getNextPageParam: (lastPage, pages) => {
      const hasMore = lastPage.data?.hasMore;
      return hasMore ? pages.length * (params.limit || 50) : undefined;
    },
  });
};

// === SUBSCRIBER MUTATIONS ===
export const useCreateSubscriber = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data) => apiService.subscribers.create(data),
    onSuccess: (response) => {
      // Invalidate and refetch subscriber lists
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboardStats });
      
      toast.success('Subscriber created successfully!');
      return response.data;
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to create subscriber: ${message}`);
    },
  });
};

export const useUpdateSubscriber = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, data }) => apiService.subscribers.update(id, data),
    onMutate: async ({ id, data }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.subscriber(id) });
      
      // Snapshot previous value
      const previousSubscriber = queryClient.getQueryData(queryKeys.subscriber(id));
      
      // Optimistically update
      queryClient.setQueryData(queryKeys.subscriber(id), (old) => ({
        ...old,
        ...data,
      }));
      
      return { previousSubscriber, id };
    },
    onSuccess: (response, { id }) => {
      // Update the subscriber data with server response
      queryClient.setQueryData(queryKeys.subscriber(id), response.data);
      
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers });
      
      toast.success('Subscriber updated successfully!');
    },
    onError: (error, { id }, context) => {
      // Revert optimistic update on error
      if (context?.previousSubscriber) {
        queryClient.setQueryData(queryKeys.subscriber(id), context.previousSubscriber);
      }
      
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to update subscriber: ${message}`);
    },
  });
};

export const useDeleteSubscriber = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id) => apiService.subscribers.delete(id),
    onSuccess: () => {
      // Invalidate and refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboardStats });
      
      toast.success('Subscriber deleted successfully!');
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to delete subscriber: ${message}`);
    },
  });
};

export const useBulkUpdateSubscribers = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data) => apiService.subscribers.bulkUpdate(data),
    onSuccess: (response) => {
      // Invalidate all subscriber-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.subscribers });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboardStats });
      
      const { updated, failed } = response.data;
      toast.success(`Bulk update completed: ${updated} updated, ${failed} failed`);
      
      return response.data;
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Bulk update failed: ${message}`);
    },
  });
};

// === MIGRATION HOOKS ===
export const useMigrationJobs = (params = {}) => {
  return useQuery({
    queryKey: queryKeys.migrationJobs(params),
    queryFn: () => apiService.migration.getJobs(params),
    select: (response) => response.data,
    refetchInterval: 5000, // Auto-refresh every 5 seconds for job status
  });
};

export const useMigrationJob = (id, enabled = true) => {
  return useQuery({
    queryKey: queryKeys.migrationJob(id),
    queryFn: () => apiService.migration.getJobById(id),
    select: (response) => response.data,
    enabled: !!id && enabled,
    refetchInterval: (data) => {
      // Auto-refresh if job is still running
      const isRunning = ['PENDING', 'RUNNING', 'UPLOADING'].includes(data?.status);
      return isRunning ? 2000 : false; // 2 seconds if running, no refresh if completed
    },
  });
};

export const useCreateMigrationJob = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data) => apiService.migration.createJob(data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.migration });
      toast.success('Migration job created successfully!');
      return response.data;
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to create migration job: ${message}`);
    },
  });
};

export const useUploadFile = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ file, onProgress }) => apiService.migration.uploadFile(file, onProgress),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.migration });
      toast.success('File uploaded successfully!');
      return response.data;
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`File upload failed: ${message}`);
    },
  });
};

// === ANALYTICS HOOKS ===
export const useAnalyticsMetrics = (timeRange = '7d') => {
  return useQuery({
    queryKey: queryKeys.analyticsMetrics(timeRange),
    queryFn: () => apiService.analytics.getMetrics(timeRange),
    select: (response) => response.data,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const usePerformanceData = (params = {}) => {
  return useQuery({
    queryKey: queryKeys.analyticsPerformance(params),
    queryFn: () => apiService.analytics.getPerformanceData(params),
    select: (response) => response.data,
  });
};

// === MONITORING HOOKS ===
export const useSystemStatus = () => {
  return useQuery({
    queryKey: queryKeys.monitoringStatus,
    queryFn: () => apiService.monitoring.getSystemStatus(),
    select: (response) => response.data,
    refetchInterval: 30 * 1000, // Refresh every 30 seconds
  });
};

export const useMonitoringAlerts = (params = {}) => {
  return useQuery({
    queryKey: queryKeys.monitoringAlerts(params),
    queryFn: () => apiService.monitoring.getAlerts(params),
    select: (response) => response.data,
    refetchInterval: 60 * 1000, // Refresh every minute
  });
};

export const useAcknowledgeAlert = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id) => apiService.monitoring.acknowledgeAlert(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.monitoring });
      toast.success('Alert acknowledged!');
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to acknowledge alert: ${message}`);
    },
  });
};

// === USER MANAGEMENT HOOKS ===
export const useUsers = (params = {}) => {
  return useQuery({
    queryKey: queryKeys.userList(params),
    queryFn: () => apiService.users.getAll(params),
    select: (response) => response.data,
  });
};

export const useUser = (id, enabled = true) => {
  return useQuery({
    queryKey: queryKeys.user(id),
    queryFn: () => apiService.users.getById(id),
    select: (response) => response.data,
    enabled: !!id && enabled,
  });
};

export const useCreateUser = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data) => apiService.users.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.users });
      toast.success('User created successfully!');
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to create user: ${message}`);
    },
  });
};

// === SETTINGS HOOKS ===
export const useSettings = () => {
  return useQuery({
    queryKey: queryKeys.settingsAll,
    queryFn: () => apiService.settings.getAll(),
    select: (response) => response.data,
  });
};

export const useProvisioningMode = () => {
  return useQuery({
    queryKey: queryKeys.settingsProvisioningMode,
    queryFn: () => apiService.settings.getProvisioningMode(),
    select: (response) => response.data,
  });
};

export const useUpdateSettings = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data) => apiService.settings.update(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings });
      toast.success('Settings updated successfully!');
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Failed to update settings: ${message}`);
    },
  });
};

// === AUDIT HOOKS ===
export const useAuditLogs = (params = {}) => {
  return useQuery({
    queryKey: queryKeys.auditLogs(params),
    queryFn: () => apiService.audit.getLogs(params),
    select: (response) => response.data,
    keepPreviousData: true,
  });
};

// === UTILITY HOOKS ===
export const useExportData = () => {
  return useMutation({
    mutationFn: async ({ type, params, filename }) => {
      let response;
      switch (type) {
        case 'subscribers':
          response = await apiService.subscribers.export('csv', params);
          break;
        case 'audit':
          response = await apiService.audit.export(params);
          break;
        default:
          throw new Error('Unsupported export type');
      }
      
      // Download the file
      apiUtils.downloadFile(response.data, filename);
      return response.data;
    },
    onSuccess: () => {
      toast.success('Export completed successfully!');
    },
    onError: (error) => {
      const message = apiUtils.getErrorMessage(error);
      toast.error(`Export failed: ${message}`);
    },
  });
};

// Hook for prefetching data
export const usePrefetchQueries = () => {
  const queryClient = useQueryClient();
  
  return {
    prefetchDashboard: () => {
      queryClient.prefetchQuery({
        queryKey: queryKeys.dashboardStats,
        queryFn: () => apiService.dashboard.getStats(),
        staleTime: 2 * 60 * 1000,
      });
    },
    prefetchSubscribers: (params = {}) => {
      queryClient.prefetchQuery({
        queryKey: queryKeys.subscriberList(params),
        queryFn: () => apiService.subscribers.getAll(params),
        staleTime: 1 * 60 * 1000,
      });
    },
    prefetchUser: (id) => {
      if (id) {
        queryClient.prefetchQuery({
          queryKey: queryKeys.user(id),
          queryFn: () => apiService.users.getById(id),
          staleTime: 5 * 60 * 1000,
        });
      }
    },
  };
};