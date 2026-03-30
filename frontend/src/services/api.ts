import axios from "axios";
import type { DecisionInput, DecisionResult, Task } from "@/types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:3000/api",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("auth_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// Decision API
export const decisionApi = {
  // Create a new decision
  createDecision: async (data: DecisionInput): Promise<DecisionResult> => {
    const response = await api.post("/decisions", data);
    return response.data;
  },

  // Get decision history
  getDecisionHistory: async (): Promise<DecisionResult[]> => {
    const response = await api.get("/decisions/history");
    return response.data;
  },

  // Get decision by ID
  getDecisionById: async (id: string): Promise<DecisionResult> => {
    const response = await api.get(`/decisions/${id}`);
    return response.data;
  },

  // Simulate decision outcomes
  simulateDecision: async (data: DecisionInput): Promise<DecisionResult> => {
    const response = await api.post("/decisions/simulate", data);
    return response.data;
  },
};

// Task API
export const taskApi = {
  // Get all tasks
  getTasks: async (): Promise<Task[]> => {
    const response = await api.get("/tasks");
    return response.data;
  },

  // Create task
  createTask: async (data: Partial<Task>): Promise<Task> => {
    const response = await api.post("/tasks", data);
    return response.data;
  },

  // Update task
  updateTask: async (id: string, data: Partial<Task>): Promise<Task> => {
    const response = await api.patch(`/tasks/${id}`, data);
    return response.data;
  },

  // Delete task
  deleteTask: async (id: string): Promise<void> => {
    await api.delete(`/tasks/${id}`);
  },
};

// User API
export const userApi = {
  // Get current user
  getCurrentUser: async () => {
    const response = await api.get("/user/me");
    return response.data;
  },

  // Update user
  updateUser: async (data: Partial<{ name: string; email: string }>) => {
    const response = await api.patch("/user/me", data);
    return response.data;
  },
};

export default api;
