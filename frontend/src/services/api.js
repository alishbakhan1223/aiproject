import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token') || 'mock-token';
  config.headers.Authorization = \Bearer \\;
  return config;
});

export const loginUser = async (username, password) => {
  localStorage.setItem('token', 'mock-token');
  return { data: { access_token: 'mock-token' } };
};

export default api;
