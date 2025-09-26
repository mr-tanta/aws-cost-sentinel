'use client';

import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Toolbar,
  Paper,
  List,
  ListItem,
  ListItemText,
  Chip,
  Button,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Delete,
  Lightbulb,
} from '@mui/icons-material';
import Sidebar from '@/components/Sidebar';
import CostChart from '@/components/CostChart';
import ServiceBreakdown from '@/components/ServiceBreakdown';
import { useState, useEffect } from 'react';
import { CostSummary, ServiceCost, WasteItem, Recommendation, CostData } from '@/types';

// Mock data for development
const mockCostSummary: CostSummary = {
  current_month: 45234.56,
  last_month: 42123.45,
  projected: 48500.00,
  savings_potential: 8234.00,
  trend_percentage: 7.3,
};

const mockServiceCosts: ServiceCost[] = [
  { service: 'EC2', cost: 20355.42, percentage: 45, trend: 5.2 },
  { service: 'RDS', cost: 13570.37, percentage: 30, trend: -2.1 },
  { service: 'S3', cost: 6785.18, percentage: 15, trend: 12.8 },
  { service: 'Lambda', cost: 2261.73, percentage: 5, trend: 18.5 },
  { service: 'CloudFront', cost: 2261.86, percentage: 5, trend: -8.3 },
];

const mockWasteItems: WasteItem[] = [
  {
    id: '1',
    resource_type: 'EC2 Volume',
    resource_id: 'vol-0123456789abcdef0',
    monthly_cost: 89.50,
    detected_at: '2025-01-20T10:00:00Z',
    remediated: false,
    action: 'Delete unused volume',
  },
  {
    id: '2',
    resource_type: 'Elastic IP',
    resource_id: '52.123.45.67',
    monthly_cost: 3.60,
    detected_at: '2025-01-20T09:30:00Z',
    remediated: false,
    action: 'Release unused IP',
  },
];

const mockRecommendations: Recommendation[] = [
  {
    id: '1',
    type: 'reserved_instance',
    resource_id: 'i-0123456789abcdef0',
    title: 'Buy Reserved Instances',
    description: 'Purchase 1-year Reserved Instances for consistent workloads',
    monthly_savings: 2340.00,
    complexity: 2,
    risk_level: 'low',
    status: 'pending',
    created_at: '2025-01-20T08:00:00Z',
  },
  {
    id: '2',
    type: 'right_sizing',
    resource_id: 'i-0987654321fedcba0',
    title: 'Right-size EC2 Instances',
    description: 'Reduce instance sizes based on CPU utilization',
    monthly_savings: 560.00,
    complexity: 3,
    risk_level: 'medium',
    status: 'pending',
    created_at: '2025-01-20T07:30:00Z',
  },
];

const mockCostData: CostData[] = Array.from({ length: 30 }, (_, i) => ({
  date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
  total_cost: 1200 + Math.random() * 800 + Math.sin(i / 7) * 200,
  services: {
    EC2: 600 + Math.random() * 400,
    RDS: 300 + Math.random() * 200,
    S3: 200 + Math.random() * 100,
  },
  tags: {},
}));

export default function Dashboard() {
  const [costSummary] = useState<CostSummary>(mockCostSummary);
  const [serviceCosts] = useState<ServiceCost[]>(mockServiceCosts);
  const [wasteItems] = useState<WasteItem[]>(mockWasteItems);
  const [recommendations] = useState<Recommendation[]>(mockRecommendations);
  const [costData] = useState<CostData[]>(mockCostData);

  return (
    <Box sx={{ display: 'flex' }}>
      <Sidebar />
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        <Grid container spacing={3}>
          {/* Cost Summary Cards */}
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Current Month
                </Typography>
                <Typography variant="h5" component="div">
                  ${costSummary.current_month.toLocaleString()}
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                  {costSummary.trend_percentage > 0 ? (
                    <TrendingUp color="error" sx={{ mr: 0.5 }} />
                  ) : (
                    <TrendingDown color="success" sx={{ mr: 0.5 }} />
                  )}
                  <Typography
                    variant="body2"
                    color={costSummary.trend_percentage > 0 ? 'error' : 'success'}
                  >
                    {Math.abs(costSummary.trend_percentage)}%
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Last Month
                </Typography>
                <Typography variant="h5" component="div">
                  ${costSummary.last_month.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Projected
                </Typography>
                <Typography variant="h5" component="div">
                  ${costSummary.projected.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Savings Potential
                </Typography>
                <Typography variant="h5" component="div" color="success.main">
                  ${costSummary.savings_potential.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          {/* Charts */}
          <Grid item xs={12} lg={8}>
            <CostChart data={costData} height={400} />
          </Grid>

          <Grid item xs={12} lg={4}>
            <ServiceBreakdown data={serviceCosts} height={400} />
          </Grid>

          {/* Top Waste Items */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Delete sx={{ mr: 1 }} />
                  <Typography variant="h6">Top Waste Items</Typography>
                </Box>
                <List>
                  {wasteItems.slice(0, 3).map((item) => (
                    <ListItem key={item.id} sx={{ px: 0 }}>
                      <ListItemText
                        primary={item.action}
                        secondary={`${item.resource_type}: ${item.resource_id}`}
                      />
                      <Chip
                        label={`$${item.monthly_cost}/mo`}
                        color="error"
                        size="small"
                      />
                    </ListItem>
                  ))}
                </List>
                <Button variant="outlined" fullWidth sx={{ mt: 1 }}>
                  View All Waste Items
                </Button>
              </CardContent>
            </Card>
          </Grid>

          {/* Top Recommendations */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Lightbulb sx={{ mr: 1 }} />
                  <Typography variant="h6">Top Recommendations</Typography>
                </Box>
                <List>
                  {recommendations.slice(0, 3).map((rec) => (
                    <ListItem key={rec.id} sx={{ px: 0 }}>
                      <ListItemText
                        primary={rec.title}
                        secondary={rec.description}
                      />
                      <Chip
                        label={`$${rec.monthly_savings}/mo`}
                        color="success"
                        size="small"
                      />
                    </ListItem>
                  ))}
                </List>
                <Button variant="outlined" fullWidth sx={{ mt: 1 }}>
                  View All Recommendations
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
}