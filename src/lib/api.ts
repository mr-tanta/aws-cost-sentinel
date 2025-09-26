import axios from 'axios';
import { CostData, CostSummary, WasteItem, Recommendation, ServiceCost } from '@/types';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const costApi = {
  async getSummary(): Promise<CostSummary> {
    const response = await api.get('/api/v1/costs/summary');
    return response.data;
  },

  async getDailyCosts(startDate: string, endDate: string): Promise<CostData[]> {
    const response = await api.get('/api/v1/costs/daily', {
      params: { start: startDate, end: endDate },
    });
    return response.data;
  },

  async getServiceCosts(): Promise<ServiceCost[]> {
    const response = await api.get('/api/v1/costs/services');
    return response.data;
  },
};

export const wasteApi = {
  async getWaste(): Promise<WasteItem[]> {
    const response = await api.get('/api/v1/waste');
    return response.data;
  },

  async remediateWaste(id: string): Promise<void> {
    await api.post(`/api/v1/waste/${id}/remediate`);
  },
};

export const recommendationsApi = {
  async getRecommendations(): Promise<Recommendation[]> {
    const response = await api.get('/api/v1/recommendations');
    return response.data;
  },

  async applyRecommendation(id: string): Promise<void> {
    await api.post(`/api/v1/recommendations/${id}/apply`);
  },

  async dismissRecommendation(id: string): Promise<void> {
    await api.post(`/api/v1/recommendations/${id}/dismiss`);
  },
};

export default api;