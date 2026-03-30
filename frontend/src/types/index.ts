// DecisionOS Types

export interface DecisionInput {
  taskDescription: string;
  deadline: Date | null;
  constraints: Constraint[];
  priority: 'low' | 'medium' | 'high';
}

export interface Constraint {
  id: string;
  type: 'meeting' | 'time-limit' | 'dependency' | 'resource';
  description: string;
  startTime?: Date;
  endTime?: Date;
}

export interface SimulationOption {
  id: string;
  name: string;
  description: string;
  outcomeSummary: string;
  riskLevel: 'low' | 'medium' | 'high';
  successProbability: number;
  estimatedCompletion: Date;
  pros: string[];
  cons: string[];
}

export interface DecisionResult {
  recommendation: string;
  reasoning: string;
  confidence: number;
  selectedOptionId: string;
  alternatives: SimulationOption[];
}

export interface Task {
  id: string;
  title: string;
  description: string;
  deadline: Date;
  priority: 'low' | 'medium' | 'high';
  status: 'pending' | 'in-progress' | 'completed';
  conflicts: string[];
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  role: string;
}

export interface NavItem {
  id: string;
  label: string;
  icon: string;
  path: string;
}
