export const config = {
  api: {
    baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    version: 'v1',
    timeout: 30000,
  },

  auth: {
    tokenKey: 'cost-sentinel-token',
    refreshTokenKey: 'cost-sentinel-refresh-token',
    userKey: 'cost-sentinel-user',
  },

  app: {
    name: 'AWS Cost Sentinel',
    version: '1.0.0',
    environment: process.env.NEXT_PUBLIC_ENVIRONMENT || 'development',
    isDevelopment: process.env.NODE_ENV === 'development',
    isProduction: process.env.NODE_ENV === 'production',
  },

  theme: {
    primary: '#FF9900', // AWS Orange
    secondary: '#232F3E', // AWS Dark Blue
    success: '#4CAF50',
    warning: '#FFC107',
    error: '#F44336',
    info: '#2196F3',
  },

  charts: {
    colors: ['#FF9900', '#232F3E', '#4CAF50', '#FFC107', '#F44336', '#9C27B0', '#2196F3'],
    defaultHeight: 400,
  },

  pagination: {
    defaultLimit: 25,
    limits: [10, 25, 50, 100],
  },

  cache: {
    defaultTTL: 5 * 60 * 1000, // 5 minutes
    longTTL: 60 * 60 * 1000, // 1 hour
  },

  features: {
    realTimeUpdates: true,
    darkMode: true,
    multiAccount: true,
    reports: true,
    alerts: true,
  },

  aws: {
    defaultRegion: 'us-east-1',
    supportedRegions: [
      { value: 'us-east-1', label: 'US East (N. Virginia)' },
      { value: 'us-east-2', label: 'US East (Ohio)' },
      { value: 'us-west-1', label: 'US West (N. California)' },
      { value: 'us-west-2', label: 'US West (Oregon)' },
      { value: 'eu-west-1', label: 'Europe (Ireland)' },
      { value: 'eu-west-2', label: 'Europe (London)' },
      { value: 'eu-west-3', label: 'Europe (Paris)' },
      { value: 'eu-central-1', label: 'Europe (Frankfurt)' },
      { value: 'ap-south-1', label: 'Asia Pacific (Mumbai)' },
      { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
      { value: 'ap-southeast-2', label: 'Asia Pacific (Sydney)' },
      { value: 'ap-northeast-1', label: 'Asia Pacific (Tokyo)' },
    ],
  },

  dateFormats: {
    display: 'MMM DD, YYYY',
    displayWithTime: 'MMM DD, YYYY HH:mm',
    api: 'YYYY-MM-DD',
    apiWithTime: 'YYYY-MM-DDTHH:mm:ss[Z]',
  },

  notifications: {
    defaultDuration: 5000,
    errorDuration: 10000,
    position: {
      vertical: 'top' as const,
      horizontal: 'right' as const,
    },
  },
} as const;

export type Config = typeof config;