import type { DecisionResult, SimulationOption, Task, User } from "@/types";

export const mockUser: User = {
  id: "1",
  name: "Alex Chen",
  email: "alex.chen@decisionos.com",
  role: "Product Manager",
  avatar: undefined,
};

export const mockSimulationOptions: SimulationOption[] = [
  {
    id: "opt-1",
    name: "Option A: Aggressive Timeline",
    description: "Complete the project by prioritizing speed over perfection",
    outcomeSummary: "Fast delivery with acceptable quality, higher team stress",
    riskLevel: "high",
    successProbability: 65,
    estimatedCompletion: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
    pros: [
      "Meets tight deadline",
      "Early market entry",
      "Competitive advantage",
    ],
    cons: [
      "Higher burnout risk",
      "Potential quality issues",
      "Limited testing time",
    ],
  },
  {
    id: "opt-2",
    name: "Option B: Balanced Approach",
    description:
      "Optimize for both quality and speed with strategic compromises",
    outcomeSummary: "Balanced delivery with good quality and manageable risk",
    riskLevel: "medium",
    successProbability: 85,
    estimatedCompletion: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000),
    pros: [
      "Good quality output",
      "Sustainable team pace",
      "Adequate testing time",
    ],
    cons: ["Slight deadline extension needed", "Some features may be deferred"],
  },
  {
    id: "opt-3",
    name: "Option C: Quality First",
    description: "Prioritize thorough development and comprehensive testing",
    outcomeSummary: "High-quality deliverable with extended timeline",
    riskLevel: "low",
    successProbability: 95,
    estimatedCompletion: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000),
    pros: [
      "Exceptional quality",
      "Low maintenance needs",
      "High customer satisfaction",
    ],
    cons: [
      "Misses original deadline",
      "Delayed market entry",
      "Higher initial cost",
    ],
  },
];

export const mockDecisionResult: DecisionResult = {
  recommendation: "Option B: Balanced Approach",
  reasoning: `Based on the analysis of your constraints and deadline, the Balanced Approach offers the optimal trade-off. With an 85% success probability and medium risk level, this option provides good quality while keeping the timeline manageable. The 3-day extension is reasonable given the constraints you've outlined, and it allows for adequate testing without compromising team wellbeing.`,
  confidence: 87,
  selectedOptionId: "opt-2",
  alternatives: mockSimulationOptions,
};

export const mockTasks: Task[] = [
  {
    id: "task-1",
    title: "Q4 Product Roadmap",
    description: "Define key features and timeline for Q4 release",
    deadline: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000),
    priority: "high",
    status: "in-progress",
    conflicts: ["task-2"],
  },
  {
    id: "task-2",
    title: "Team Performance Review",
    description: "Complete quarterly performance evaluations",
    deadline: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000),
    priority: "high",
    status: "pending",
    conflicts: ["task-1"],
  },
  {
    id: "task-3",
    title: "Client Presentation",
    description: "Prepare slides for stakeholder meeting",
    deadline: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000),
    priority: "medium",
    status: "in-progress",
    conflicts: [],
  },
  {
    id: "task-4",
    title: "Budget Planning",
    description: "Finalize next quarter budget allocation",
    deadline: new Date(Date.now() + 8 * 24 * 60 * 60 * 1000),
    priority: "medium",
    status: "pending",
    conflicts: [],
  },
  {
    id: "task-5",
    title: "Security Audit",
    description: "Complete annual security compliance review",
    deadline: new Date(Date.now() + 12 * 24 * 60 * 60 * 1000),
    priority: "low",
    status: "pending",
    conflicts: [],
  },
];

export const simulateDelay = (ms: number = 1500) =>
  new Promise((resolve) => setTimeout(resolve, ms));

export const mockCreateDecision = async (): Promise<DecisionResult> => {
  await simulateDelay(2500);
  return mockDecisionResult;
};

export const mockGetTasks = async (): Promise<Task[]> => {
  await simulateDelay(800);
  return mockTasks;
};
