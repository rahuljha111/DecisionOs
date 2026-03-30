import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { TaskTimeline } from "@/components/decision/TaskTimeline";
import { mockGetTasks, mockUser } from "@/data/mockData";
import type { Task } from "@/types";
import {
  Sparkles,
  TrendingUp,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowRight,
  Brain,
  Zap,
} from "lucide-react";
import { format } from "date-fns";

interface DashboardProps {
  onNewDecision: () => void;
}

export function Dashboard({ onNewDecision }: DashboardProps) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [, setLoading] = useState(true);

  useEffect(() => {
    loadTasks();
  }, []);

  const loadTasks = async () => {
    try {
      const data = await mockGetTasks();
      setTasks(data);
    } finally {
      setLoading(false);
    }
  };

  const stats = {
    total: tasks.length,
    completed: tasks.filter((t) => t.status === "completed").length,
    inProgress: tasks.filter((t) => t.status === "in-progress").length,
    pending: tasks.filter((t) => t.status === "pending").length,
    conflicts: tasks.filter((t) => t.conflicts.length > 0).length,
  };

  const completionRate =
    stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;

  const recentDecisions = [
    {
      id: "1",
      title: "Q4 Feature Prioritization",
      date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
      confidence: 92,
      status: "completed",
    },
    {
      id: "2",
      title: "Team Resource Allocation",
      date: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
      confidence: 87,
      status: "completed",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Welcome back, {mockUser.name.split(" ")[0]}
          </h1>
          <p className="text-muted-foreground mt-1">
            Here's what's happening with your decisions today.
          </p>
        </div>
        <Button onClick={onNewDecision} className="flex items-center gap-2">
          <Sparkles className="w-4 h-4" />
          New Decision
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Completion Rate</p>
                <p className="text-3xl font-bold mt-1">{completionRate}%</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
            </div>
            <Progress value={completionRate} className="mt-4 h-2" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">In Progress</p>
                <p className="text-3xl font-bold mt-1">{stats.inProgress}</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                <Clock className="w-6 h-6 text-blue-600" />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-4">
              {stats.pending} tasks pending
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Completed</p>
                <p className="text-3xl font-bold mt-1">{stats.completed}</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-green-600" />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-4">This month</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Conflicts</p>
                <p className="text-3xl font-bold mt-1">{stats.conflicts}</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-red-600" />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-4">Need attention</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <TaskTimeline tasks={tasks} />
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Zap className="w-5 h-5 text-yellow-500" />
                Quick Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                variant="outline"
                className="w-full justify-between"
                onClick={onNewDecision}
              >
                <span className="flex items-center gap-2">
                  <Brain className="w-4 h-4" />
                  Make a Decision
                </span>
                <ArrowRight className="w-4 h-4" />
              </Button>
              <Button variant="outline" className="w-full justify-between">
                <span className="flex items-center gap-2">
                  <Clock className="w-4 h-4" />
                  View Schedule
                </span>
                <ArrowRight className="w-4 h-4" />
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Recent Decisions
              </CardTitle>
              <CardDescription>
                Your latest AI-assisted decisions
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {recentDecisions.map((decision) => (
                <div
                  key={decision.id}
                  className="p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors cursor-pointer"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-medium text-sm">{decision.title}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {format(decision.date, "MMM d, yyyy")}
                      </p>
                    </div>
                    <Badge variant="secondary" className="text-xs">
                      {decision.confidence}% confidence
                    </Badge>
                  </div>
                </div>
              ))}
              <Button variant="ghost" className="w-full text-sm">
                View All History
              </Button>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                  <Sparkles className="w-4 h-4 text-primary-foreground" />
                </div>
                <div>
                  <p className="font-medium text-sm">AI Tip</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Add more constraints to get more accurate recommendations.
                    The AI works best with 3-5 constraints.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
