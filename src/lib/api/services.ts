import { apiClient } from './client';
import {
  User,
  LoginRequest,
  AuthResponse,
  AWSAccount,
  CostData,
  CostSummary,
  CostFilter,
  WasteItem,
  WasteSummary,
  Recommendation,
  RecommendationSummary,
  ReportTemplate,
  GeneratedReport,
  Budget,
  Alert,
  DashboardMetrics,
  PaginatedResponse,
  APIResponse,
} from '@/types';

// Authentication Service
export const authService = {
  async login(credentials: LoginRequest): Promise<APIResponse<AuthResponse>> {
    return apiClient.post('/auth/login', credentials);
  },

  async logout(): Promise<APIResponse> {
    return apiClient.post('/auth/logout');
  },

  async refreshToken(): Promise<APIResponse<AuthResponse>> {
    return apiClient.post('/auth/refresh');
  },

  async getCurrentUser(): Promise<APIResponse<User>> {
    return apiClient.get('/auth/me');
  },

  async updateProfile(data: Partial<User>): Promise<APIResponse<User>> {
    return apiClient.put('/auth/profile', data);
  },
};

// AWS Accounts Service
export const awsAccountsService = {
  async getAccounts(): Promise<APIResponse<AWSAccount[]>> {
    return apiClient.get('/aws/accounts');
  },

  async createAccount(account: Omit<AWSAccount, 'id' | 'lastSync' | 'status'>): Promise<APIResponse<AWSAccount>> {
    return apiClient.post('/aws/accounts', account);
  },

  async updateAccount(id: string, account: Partial<AWSAccount>): Promise<APIResponse<AWSAccount>> {
    return apiClient.put(`/aws/accounts/${id}`, account);
  },

  async deleteAccount(id: string): Promise<APIResponse> {
    return apiClient.delete(`/aws/accounts/${id}`);
  },

  async testConnection(id: string): Promise<APIResponse<{ status: string; message: string }>> {
    return apiClient.post(`/aws/accounts/${id}/test`);
  },

  async syncAccount(id: string): Promise<APIResponse> {
    return apiClient.post(`/aws/accounts/${id}/sync`);
  },
};

// Cost Analysis Service
export const costsService = {
  async getSummary(accountIds?: string[]): Promise<APIResponse<CostSummary>> {
    const params = accountIds ? { account_ids: accountIds.join(',') } : {};
    return apiClient.get('/costs/summary', { params });
  },

  async getDailyCosts(filter: CostFilter): Promise<APIResponse<CostData[]>> {
    return apiClient.get('/costs/daily', { params: filter });
  },

  async getMonthlyCosts(filter: CostFilter): Promise<APIResponse<CostData[]>> {
    return apiClient.get('/costs/monthly', { params: filter });
  },

  async getServiceCosts(filter: CostFilter): Promise<APIResponse<any[]>> {
    return apiClient.get('/costs/services', { params: filter });
  },

  async getRegionCosts(filter: CostFilter): Promise<APIResponse<any[]>> {
    return apiClient.get('/costs/regions', { params: filter });
  },

  async getAccountCosts(filter: CostFilter): Promise<APIResponse<any[]>> {
    return apiClient.get('/costs/accounts', { params: filter });
  },

  async getCostTrends(filter: CostFilter): Promise<APIResponse<any[]>> {
    return apiClient.get('/costs/trends', { params: filter });
  },

  async exportCosts(filter: CostFilter, format: 'csv' | 'excel'): Promise<void> {
    return apiClient.download(`/costs/export?format=${format}`, `costs-${Date.now()}.${format}`);
  },
};

// Waste Detection Service
export const wasteService = {
  async getWasteItems(
    page: number = 1,
    limit: number = 25,
    filters?: any
  ): Promise<PaginatedResponse<WasteItem>> {
    const params = { page, limit, ...filters };
    return apiClient.get('/waste', { params });
  },

  async getWasteSummary(): Promise<APIResponse<WasteSummary>> {
    return apiClient.get('/waste/summary');
  },

  async remediateWaste(id: string): Promise<APIResponse> {
    return apiClient.post(`/waste/${id}/remediate`);
  },

  async bulkRemediate(ids: string[]): Promise<APIResponse> {
    return apiClient.post('/waste/bulk-remediate', { ids });
  },

  async dismissWaste(id: string): Promise<APIResponse> {
    return apiClient.post(`/waste/${id}/dismiss`);
  },

  async scheduleRemediation(id: string, scheduledFor: string): Promise<APIResponse> {
    return apiClient.post(`/waste/${id}/schedule`, { scheduled_for: scheduledFor });
  },

  async scanForWaste(accountIds?: string[]): Promise<APIResponse> {
    const data = accountIds ? { account_ids: accountIds } : {};
    return apiClient.post('/waste/scan', data);
  },
};

// Recommendations Service
export const recommendationsService = {
  async getRecommendations(
    page: number = 1,
    limit: number = 25,
    filters?: any
  ): Promise<PaginatedResponse<Recommendation>> {
    const params = { page, limit, ...filters };
    return apiClient.get('/recommendations', { params });
  },

  async getRecommendationSummary(): Promise<APIResponse<RecommendationSummary>> {
    return apiClient.get('/recommendations/summary');
  },

  async getRecommendation(id: string): Promise<APIResponse<Recommendation>> {
    return apiClient.get(`/recommendations/${id}`);
  },

  async applyRecommendation(id: string): Promise<APIResponse> {
    return apiClient.post(`/recommendations/${id}/apply`);
  },

  async dismissRecommendation(id: string, reason?: string): Promise<APIResponse> {
    return apiClient.post(`/recommendations/${id}/dismiss`, { reason });
  },

  async scheduleRecommendation(id: string, scheduledFor: string): Promise<APIResponse> {
    return apiClient.post(`/recommendations/${id}/schedule`, { scheduled_for: scheduledFor });
  },

  async bulkApply(ids: string[]): Promise<APIResponse> {
    return apiClient.post('/recommendations/bulk-apply', { ids });
  },

  async generateRecommendations(accountIds?: string[]): Promise<APIResponse> {
    const data = accountIds ? { account_ids: accountIds } : {};
    return apiClient.post('/recommendations/generate', data);
  },
};

// Reports Service
export const reportsService = {
  async getTemplates(): Promise<APIResponse<ReportTemplate[]>> {
    return apiClient.get('/reports/templates');
  },

  async createTemplate(template: Omit<ReportTemplate, 'id' | 'createdAt' | 'updatedAt'>): Promise<APIResponse<ReportTemplate>> {
    return apiClient.post('/reports/templates', template);
  },

  async updateTemplate(id: string, template: Partial<ReportTemplate>): Promise<APIResponse<ReportTemplate>> {
    return apiClient.put(`/reports/templates/${id}`, template);
  },

  async deleteTemplate(id: string): Promise<APIResponse> {
    return apiClient.delete(`/reports/templates/${id}`);
  },

  async generateReport(templateId?: string, customConfig?: any): Promise<APIResponse<GeneratedReport>> {
    const data = templateId ? { template_id: templateId } : customConfig;
    return apiClient.post('/reports/generate', data);
  },

  async getReports(page: number = 1, limit: number = 25): Promise<PaginatedResponse<GeneratedReport>> {
    return apiClient.get('/reports', { params: { page, limit } });
  },

  async downloadReport(id: string): Promise<void> {
    return apiClient.download(`/reports/${id}/download`);
  },

  async deleteReport(id: string): Promise<APIResponse> {
    return apiClient.delete(`/reports/${id}`);
  },

  async scheduleReport(templateId: string, frequency: string, recipients: string[]): Promise<APIResponse> {
    return apiClient.post(`/reports/templates/${templateId}/schedule`, {
      frequency,
      recipients,
    });
  },
};

// Budgets Service
export const budgetsService = {
  async getBudgets(): Promise<APIResponse<Budget[]>> {
    return apiClient.get('/budgets');
  },

  async createBudget(budget: Omit<Budget, 'id' | 'createdAt' | 'updatedAt'>): Promise<APIResponse<Budget>> {
    return apiClient.post('/budgets', budget);
  },

  async updateBudget(id: string, budget: Partial<Budget>): Promise<APIResponse<Budget>> {
    return apiClient.put(`/budgets/${id}`, budget);
  },

  async deleteBudget(id: string): Promise<APIResponse> {
    return apiClient.delete(`/budgets/${id}`);
  },

  async getBudgetUsage(id: string): Promise<APIResponse<any>> {
    return apiClient.get(`/budgets/${id}/usage`);
  },
};

// Alerts Service
export const alertsService = {
  async getAlerts(
    page: number = 1,
    limit: number = 25,
    filters?: any
  ): Promise<PaginatedResponse<Alert>> {
    const params = { page, limit, ...filters };
    return apiClient.get('/alerts', { params });
  },

  async markAsRead(id: string): Promise<APIResponse> {
    return apiClient.patch(`/alerts/${id}`, { is_read: true });
  },

  async markAsResolved(id: string): Promise<APIResponse> {
    return apiClient.patch(`/alerts/${id}`, { is_resolved: true });
  },

  async bulkMarkAsRead(ids: string[]): Promise<APIResponse> {
    return apiClient.post('/alerts/bulk-update', { ids, is_read: true });
  },

  async deleteAlert(id: string): Promise<APIResponse> {
    return apiClient.delete(`/alerts/${id}`);
  },

  async getUnreadCount(): Promise<APIResponse<{ count: number }>> {
    return apiClient.get('/alerts/unread-count');
  },
};

// Dashboard Service
export const dashboardService = {
  async getMetrics(): Promise<APIResponse<DashboardMetrics>> {
    return apiClient.get('/dashboard/metrics');
  },

  async getRecentActivity(): Promise<APIResponse<any[]>> {
    return apiClient.get('/dashboard/activity');
  },

  async getCostTrend(days: number = 30): Promise<APIResponse<any[]>> {
    return apiClient.get(`/dashboard/cost-trend?days=${days}`);
  },

  async getTopServices(limit: number = 10): Promise<APIResponse<any[]>> {
    return apiClient.get(`/dashboard/top-services?limit=${limit}`);
  },

  async getAnomalies(): Promise<APIResponse<any[]>> {
    return apiClient.get('/dashboard/anomalies');
  },
};

// System Service
export const systemService = {
  async getHealth(): Promise<APIResponse<any>> {
    return apiClient.get('/system/health');
  },

  async getVersion(): Promise<APIResponse<{ version: string; build: string }>> {
    return apiClient.get('/system/version');
  },

  async getStats(): Promise<APIResponse<any>> {
    return apiClient.get('/system/stats');
  },

  async triggerSync(): Promise<APIResponse> {
    return apiClient.post('/system/sync');
  },

  async getJobs(): Promise<APIResponse<any[]>> {
    return apiClient.get('/system/jobs');
  },
};