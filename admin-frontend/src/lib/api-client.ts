const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const apiClient = {
  get: async (endpoint: string) => fetch(`${BASE_URL}${endpoint}`).then(res => res.json()),
  post: async (endpoint: string, body: any) => fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(res => res.json()),
};
