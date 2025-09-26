'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { Box, Card, CardContent, Typography } from '@mui/material';
import { ServiceCost } from '@/types';

interface ServiceBreakdownProps {
  data: ServiceCost[];
  height?: number;
}

const COLORS = ['#FF9900', '#232F3E', '#4CAF50', '#FFC107', '#F44336', '#9C27B0', '#2196F3'];

export default function ServiceBreakdown({ data, height = 300 }: ServiceBreakdownProps) {
  const chartData = data.map((item, index) => ({
    name: item.service,
    value: item.cost,
    percentage: item.percentage,
    color: COLORS[index % COLORS.length],
  }));

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Service Cost Breakdown
        </Typography>
        <Box sx={{ width: '100%', height }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percentage }) => `${name} (${percentage.toFixed(1)}%)`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Cost']}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </Box>
      </CardContent>
    </Card>
  );
}