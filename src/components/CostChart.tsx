'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Box, Card, CardContent, Typography } from '@mui/material';
import { CostData } from '@/types';

interface CostChartProps {
  data: CostData[];
  height?: number;
}

export default function CostChart({ data, height = 300 }: CostChartProps) {
  const chartData = data.map((item) => ({
    date: new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    cost: item.total_cost,
  }));

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Daily Cost Trend
        </Typography>
        <Box sx={{ width: '100%', height }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis
                tickFormatter={(value) => `$${value.toLocaleString()}`}
              />
              <Tooltip
                formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Cost']}
                labelStyle={{ color: '#000' }}
              />
              <Line
                type="monotone"
                dataKey="cost"
                stroke="#FF9900"
                strokeWidth={2}
                dot={{ fill: '#FF9900' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </CardContent>
    </Card>
  );
}