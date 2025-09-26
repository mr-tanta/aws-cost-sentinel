// Auth Types
export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  isActive: boolean;
  createdAt: string;
  lastLogin?: string;
}

export type UserRole = 'admin' | 'user' | 'viewer';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// AWS Types
export interface AWSAccount {
  id: string;
  name: string;
  accountId: string;
  region: string;
  roleArn?: string;
  externalId?: string;
  isActive: boolean;
  lastSync?: string;
  status: 'connected' | 'error' | 'pending' | 'syncing';
  errorMessage?: string;
}

// Cost Analysis Types
export interface CostData {
  date: string;
  totalCost: number;
  services: Record<string, number>;
  accounts: Record<string, number>;
  regions: Record<string, number>;
  tags?: Record<string, string>;
}

export interface CostSummary {
  currentMonth: number;
  lastMonth: number;
  projected: number;
  savingsPotential: number;
  trendPercentage: number;
  topServices: ServiceCost[];
}

export interface ServiceCost {
  service: string;
  cost: number;
  percentage: number;
  trend: number;
  previousCost?: number;
}

export interface CostFilter {
  startDate: string;
  endDate: string;
  services?: string[];
  accounts?: string[];
  regions?: string[];
  tags?: Record<string, string>;
}

// Waste Detection Types
export type WasteResourceType =
  | 'ebs_volume'
  | 'elastic_ip'
  | 'ec2_instance'
  | 'rds_instance'
  | 'load_balancer'
  | 'ebs_snapshot'
  | 's3_bucket';

export interface WasteItem {
  id: string;
  resourceType: WasteResourceType;
  resourceId: string;
  accountId: string;
  region: string;
  monthlyCost: number;
  detectedAt: string;
  isRemediated: boolean;
  action: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  tags?: Record<string, string>;
}

export interface WasteSummary {
  totalItems: number;
  totalMonthlySavings: number;
  totalAnnualSavings: number;
  byType: Record<WasteResourceType, {
    count: number;
    cost: number;
  }>;
  byAccount: Record<string, {
    count: number;
    cost: number;
  }>;
}

// Recommendations Types
export type RecommendationType =
  | 'reserved_instances'
  | 'savings_plans'
  | 'right_sizing'
  | 'storage_optimization'
  | 'compute_optimization'
  | 'cleanup';

export type RiskLevel = 'low' | 'medium' | 'high';
export type RecommendationStatus = 'pending' | 'applied' | 'dismissed' | 'scheduled';

export interface Recommendation {
  id: string;
  type: RecommendationType;
  title: string;
  description: string;
  resourceId?: string;
  accountId: string;
  region: string;
  monthlySavings: number;
  annualSavings: number;
  implementationCost?: number;
  complexity: number; // 1-5 scale
  riskLevel: RiskLevel;
  status: RecommendationStatus;
  confidence: number; // 0-100
  impact: 'low' | 'medium' | 'high';
  category: string;
  tags: string[];
  metadata: Record<string, any>;
  createdAt: string;
  updatedAt: string;
  scheduledFor?: string;
  appliedAt?: string;
}

export interface RecommendationSummary {
  totalRecommendations: number;
  totalMonthlySavings: number;
  totalAnnualSavings: number;
  byType: Record<RecommendationType, {
    count: number;
    savings: number;
  }>;
  byRisk: Record<RiskLevel, {
    count: number;
    savings: number;
  }>;
  byStatus: Record<RecommendationStatus, {
    count: number;
    savings: number;
  }>;
}

// Reports Types
export type ReportType = 'executive' | 'technical' | 'financial' | 'custom';
export type ReportFormat = 'pdf' | 'excel' | 'csv';
export type ReportFrequency = 'daily' | 'weekly' | 'monthly' | 'quarterly';

export interface ReportTemplate {
  id: string;
  name: string;
  type: ReportType;
  format: ReportFormat;
  frequency: ReportFrequency;
  recipients: string[];
  isActive: boolean;
  sections: string[];
  filters?: CostFilter;
  createdAt: string;
  updatedAt: string;
  lastGenerated?: string;
  nextRun?: string;
}

export interface GeneratedReport {
  id: string;
  templateId?: string;
  name: string;
  type: ReportType;
  format: ReportFormat;
  status: 'pending' | 'generating' | 'completed' | 'failed';
  url?: string;
  size?: number;
  generatedAt: string;
  requestedBy: string;
  error?: string;
}

// Budget & Alerts Types
export interface Budget {
  id: string;
  name: string;
  amount: number;
  period: 'monthly' | 'quarterly' | 'annually';
  accounts?: string[];
  services?: string[];
  tags?: Record<string, string>;
  alertThresholds: number[]; // Percentage thresholds
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Alert {
  id: string;
  type: 'budget' | 'anomaly' | 'threshold' | 'waste';
  severity: 'info' | 'warning' | 'error' | 'critical';
  title: string;
  message: string;
  accountId?: string;
  budgetId?: string;
  threshold?: number;
  actualValue?: number;
  isRead: boolean;
  isResolved: boolean;
  createdAt: string;
  resolvedAt?: string;
}

// API Response Types
export interface APIResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  metadata?: {
    page?: number;
    limit?: number;
    total?: number;
    hasNext?: boolean;
    hasPrev?: boolean;
  };
}

export interface PaginatedResponse<T> extends APIResponse<T[]> {
  metadata: {
    page: number;
    limit: number;
    total: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
}

// Component Props Types
export interface ChartProps {
  data: any[];
  loading?: boolean;
  error?: string;
  height?: number;
  colors?: string[];
}

export interface TableColumn<T = any> {
  key: keyof T;
  title: string;
  width?: number;
  sortable?: boolean;
  filterable?: boolean;
  render?: (value: any, record: T) => React.ReactNode;
}

export interface TableProps<T = any> {
  data: T[];
  columns: TableColumn<T>[];
  loading?: boolean;
  pagination?: {
    page: number;
    limit: number;
    total: number;
    onChange: (page: number, limit: number) => void;
  };
  selection?: {
    selectedRows: string[];
    onChange: (selectedRows: string[]) => void;
  };
}

// Form Types
export interface FormField {
  name: string;
  label: string;
  type: 'text' | 'email' | 'password' | 'number' | 'select' | 'multiselect' | 'textarea' | 'date' | 'switch';
  required?: boolean;
  placeholder?: string;
  options?: { value: string; label: string }[];
  validation?: any; // Zod schema
  helperText?: string;
}

// Notification Types
export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  duration?: number;
  actions?: {
    label: string;
    action: () => void;
  }[];
}

// Dashboard Types
export interface DashboardMetrics {
  totalCost: {
    current: number;
    previous: number;
    trend: number;
  };
  wasteDetected: {
    count: number;
    savings: number;
  };
  recommendationsAvailable: {
    count: number;
    savings: number;
  };
  accountsConnected: number;
  lastSync: string;
}

export interface DashboardWidget {
  id: string;
  type: 'metric' | 'chart' | 'table' | 'alert';
  title: string;
  position: { x: number; y: number; w: number; h: number };
  config: Record<string, any>;
}

// System Configuration Types
export interface SystemConfig {
  syncFrequency: number;
  dataRetention: number;
  defaultRegion: string;
  emailNotifications: boolean;
  slackWebhook?: string;
  maintenanceMode: boolean;
  features: {
    wasteDetection: boolean;
    recommendations: boolean;
    reports: boolean;
    alerts: boolean;
  };
}