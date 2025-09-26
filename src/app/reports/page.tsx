'use client';

import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  CloudDownload,
  Schedule,
  PictureAsPdf,
  TableChart,
  Description,
  Visibility,
  Delete,
  GetApp,
} from '@mui/icons-material';

interface Account {
  id: string;
  name: string;
  aws_account_id: string;
}

interface ReportTemplate {
  id: string;
  name: string;
  description: string;
  formats: string[];
  sections: string[];
}

interface GeneratedReport {
  report_id: string;
  format: string;
  size_bytes: number;
  generated_at: string;
  summary: {
    total_cost: number;
    potential_savings: number;
    waste_items_count: number;
    recommendations_count: number;
  };
}

interface ReportPreview {
  account: {
    name: string;
    id: string;
  };
  period: {
    start_date: string;
    end_date: string;
  };
  summary: {
    total_cost: number;
    potential_savings: number;
    waste_items_count: number;
    recommendations_count: number;
  };
  top_services: Array<{
    service_name: string;
    cost: number;
    percentage: number;
  }>;
  top_waste_categories: Array<{
    name: string;
    item_count: number;
    potential_savings: number;
  }>;
  top_recommendations: Array<{
    title: string;
    estimated_savings: number;
    confidence_score: number;
  }>;
}

const ReportsPage: React.FC = () => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [selectedFormat, setSelectedFormat] = useState<string>('pdf');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');
  const [generatedReport, setGeneratedReport] = useState<GeneratedReport | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<ReportPreview | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleType, setScheduleType] = useState<string>('monthly');
  const [scheduleFormats, setScheduleFormats] = useState<string[]>(['pdf']);

  useEffect(() => {
    fetchAccounts();
    fetchTemplates();

    // Set default dates (last 30 days)
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 30);

    setEndDate(end.toISOString().split('T')[0]);
    setStartDate(start.toISOString().split('T')[0]);
  }, []);

  const fetchAccounts = async () => {
    try {
      const response = await fetch('/api/v1/aws/accounts', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setAccounts(data.accounts || []);
        if (data.accounts?.length > 0) {
          setSelectedAccount(data.accounts[0].id);
        }
      }
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
    }
  };

  const fetchTemplates = async () => {
    try {
      const response = await fetch('/api/v1/reports/templates', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setTemplates(data.templates || []);
      }
    } catch (error) {
      console.error('Failed to fetch templates:', error);
    }
  };

  const previewReport = async () => {
    if (!selectedAccount) return;

    setLoading(true);
    setError('');

    try {
      const response = await fetch('/api/v1/reports/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          account_id: selectedAccount,
          start_date: startDate,
          end_date: endDate,
          format_type: selectedFormat,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setPreviewData(data);
        setPreviewOpen(true);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to preview report');
      }
    } catch (error) {
      setError('Failed to preview report');
      console.error('Preview error:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateReport = async () => {
    if (!selectedAccount) return;

    setGenerating(true);
    setError('');
    setSuccess('');

    try {
      const response = await fetch('/api/v1/reports/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          account_id: selectedAccount,
          start_date: startDate,
          end_date: endDate,
          format_type: selectedFormat,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setGeneratedReport(data);
        setSuccess(`Report generated successfully! Format: ${data.format.toUpperCase()}`);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to generate report');
      }
    } catch (error) {
      setError('Failed to generate report');
      console.error('Generation error:', error);
    } finally {
      setGenerating(false);
    }
  };

  const scheduleReports = async () => {
    if (!selectedAccount) return;

    try {
      const response = await fetch('/api/v1/reports/schedule', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: JSON.stringify({
          account_id: selectedAccount,
          schedule_type: scheduleType,
          format_types: scheduleFormats,
          enabled: true,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setSuccess(`Periodic reports scheduled successfully! Next run: ${new Date(data.next_run).toLocaleString()}`);
        setScheduleOpen(false);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Failed to schedule reports');
      }
    } catch (error) {
      setError('Failed to schedule reports');
      console.error('Schedule error:', error);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  const getFormatIcon = (format: string) => {
    switch (format.toLowerCase()) {
      case 'pdf':
        return <PictureAsPdf />;
      case 'excel':
        return <TableChart />;
      case 'html':
        return <Description />;
      default:
        return <Description />;
    }
  };

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        Cost Optimization Reports
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Generate New Report
              </Typography>

              <Box sx={{ mt: 2 }}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <FormControl fullWidth>
                      <InputLabel>AWS Account</InputLabel>
                      <Select
                        value={selectedAccount}
                        onChange={(e) => setSelectedAccount(e.target.value)}
                        label="AWS Account"
                      >
                        {accounts.map((account) => (
                          <MenuItem key={account.id} value={account.id}>
                            {account.name} ({account.aws_account_id})
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <FormControl fullWidth>
                      <InputLabel>Format</InputLabel>
                      <Select
                        value={selectedFormat}
                        onChange={(e) => setSelectedFormat(e.target.value)}
                        label="Format"
                      >
                        <MenuItem value="pdf">PDF</MenuItem>
                        <MenuItem value="excel">Excel</MenuItem>
                        <MenuItem value="html">HTML</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="Start Date"
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      InputLabelProps={{ shrink: true }}
                    />
                  </Grid>

                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="End Date"
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      InputLabelProps={{ shrink: true }}
                    />
                  </Grid>
                </Grid>

                <Box sx={{ mt: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  <Button
                    variant="outlined"
                    startIcon={<Visibility />}
                    onClick={previewReport}
                    disabled={loading || !selectedAccount}
                  >
                    {loading ? <CircularProgress size={20} /> : 'Preview'}
                  </Button>

                  <Button
                    variant="contained"
                    startIcon={<CloudDownload />}
                    onClick={generateReport}
                    disabled={generating || !selectedAccount}
                  >
                    {generating ? <CircularProgress size={20} /> : 'Generate Report'}
                  </Button>

                  <Button
                    variant="outlined"
                    startIcon={<Schedule />}
                    onClick={() => setScheduleOpen(true)}
                    disabled={!selectedAccount}
                  >
                    Schedule Reports
                  </Button>
                </Box>
              </Box>

              {generatedReport && (
                <Box sx={{ mt: 3, p: 2, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
                  <Typography variant="h6" gutterBottom>
                    Generated Report
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" color="text.secondary">
                        Format: {generatedReport.format.toUpperCase()}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Size: {formatFileSize(generatedReport.size_bytes)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Generated: {new Date(generatedReport.generated_at).toLocaleString()}
                      </Typography>
                    </Grid>

                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" color="text.secondary">
                        Total Cost: {formatCurrency(generatedReport.summary.total_cost)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Potential Savings: {formatCurrency(generatedReport.summary.potential_savings)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Waste Items: {generatedReport.summary.waste_items_count}
                      </Typography>
                    </Grid>
                  </Grid>

                  <Button
                    variant="contained"
                    startIcon={<GetApp />}
                    sx={{ mt: 2 }}
                    onClick={() => {
                      // In a real app, this would trigger the download
                      window.open(`/api/v1/reports/download/${generatedReport.report_id}`, '_blank');
                    }}
                  >
                    Download Report
                  </Button>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Available Templates
              </Typography>

              {templates.map((template) => (
                <Box key={template.id} sx={{ mb: 2, p: 2, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
                  <Typography variant="subtitle1" fontWeight="bold">
                    {template.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {template.description}
                  </Typography>

                  <Box sx={{ mb: 1 }}>
                    {template.formats.map((format) => (
                      <Chip
                        key={format}
                        label={format.toUpperCase()}
                        size="small"
                        sx={{ mr: 0.5, mb: 0.5 }}
                        icon={getFormatIcon(format)}
                      />
                    ))}
                  </Box>

                  <Typography variant="caption" color="text.secondary">
                    Sections: {template.sections.join(', ')}
                  </Typography>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Report Preview</DialogTitle>
        <DialogContent>
          {previewData && (
            <Box>
              <Typography variant="h6" gutterBottom>
                {previewData.account.name}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Period: {previewData.period.start_date} to {previewData.period.end_date}
              </Typography>

              <Grid container spacing={2} sx={{ mt: 2 }}>
                <Grid item xs={6} sm={3}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="primary">
                      {formatCurrency(previewData.summary.total_cost)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Total Cost
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="error">
                      {formatCurrency(previewData.summary.potential_savings)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Potential Savings
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Typography variant="h4">
                      {previewData.summary.waste_items_count}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Waste Items
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box sx={{ textAlign: 'center' }}>
                    <Typography variant="h4">
                      {previewData.summary.recommendations_count}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Recommendations
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              <Typography variant="h6" sx={{ mt: 3, mb: 1 }}>
                Top Services by Cost
              </Typography>
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Service</TableCell>
                      <TableCell align="right">Cost</TableCell>
                      <TableCell align="right">Percentage</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {previewData.top_services.map((service) => (
                      <TableRow key={service.service_name}>
                        <TableCell>{service.service_name}</TableCell>
                        <TableCell align="right">{formatCurrency(service.cost)}</TableCell>
                        <TableCell align="right">{service.percentage.toFixed(1)}%</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>Close</Button>
          <Button variant="contained" onClick={() => { setPreviewOpen(false); generateReport(); }}>
            Generate Full Report
          </Button>
        </DialogActions>
      </Dialog>

      {/* Schedule Dialog */}
      <Dialog open={scheduleOpen} onClose={() => setScheduleOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Schedule Periodic Reports</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <FormControl fullWidth sx={{ mb: 2 }}>
              <InputLabel>Schedule Type</InputLabel>
              <Select
                value={scheduleType}
                onChange={(e) => setScheduleType(e.target.value)}
                label="Schedule Type"
              >
                <MenuItem value="daily">Daily</MenuItem>
                <MenuItem value="weekly">Weekly</MenuItem>
                <MenuItem value="monthly">Monthly</MenuItem>
              </Select>
            </FormControl>

            <Typography variant="subtitle2" gutterBottom>
              Report Formats
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {['pdf', 'excel', 'html'].map((format) => (
                <Chip
                  key={format}
                  label={format.toUpperCase()}
                  onClick={() => {
                    if (scheduleFormats.includes(format)) {
                      setScheduleFormats(scheduleFormats.filter(f => f !== format));
                    } else {
                      setScheduleFormats([...scheduleFormats, format]);
                    }
                  }}
                  color={scheduleFormats.includes(format) ? 'primary' : 'default'}
                  variant={scheduleFormats.includes(format) ? 'filled' : 'outlined'}
                />
              ))}
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setScheduleOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={scheduleReports}>
            Schedule Reports
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ReportsPage;