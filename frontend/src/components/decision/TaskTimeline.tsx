import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Task } from "@/types";
import {
  Clock,
  AlertTriangle,
  CheckCircle2,
  Circle,
  PlayCircle,
  Calendar,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  format,
  isPast,
  isToday,
  isTomorrow,
  differenceInDays,
} from "date-fns";

interface TaskTimelineProps {
  tasks: Task[];
}

const priorityConfig = {
  low: {
    color: "bg-blue-500",
    bg: "bg-blue-50",
    text: "text-blue-600",
    label: "Low",
  },
  medium: {
    color: "bg-yellow-500",
    bg: "bg-yellow-50",
    text: "text-yellow-600",
    label: "Medium",
  },
  high: {
    color: "bg-red-500",
    bg: "bg-red-50",
    text: "text-red-600",
    label: "High",
  },
};

const statusConfig = {
  pending: { icon: Circle, color: "text-gray-400", label: "Pending" },
  "in-progress": {
    icon: PlayCircle,
    color: "text-blue-500",
    label: "In Progress",
  },
  completed: {
    icon: CheckCircle2,
    color: "text-green-500",
    label: "Completed",
  },
};

export function TaskTimeline({ tasks }: TaskTimelineProps) {
  const sortedTasks = [...tasks].sort(
    (a, b) => a.deadline.getTime() - b.deadline.getTime(),
  );

  const getDeadlineText = (date: Date) => {
    if (isToday(date)) return "Today";
    if (isTomorrow(date)) return "Tomorrow";
    if (isPast(date)) return "Overdue";
    const days = differenceInDays(date, new Date());
    return `${days} days left`;
  };

  const getDeadlineColor = (date: Date) => {
    if (isPast(date)) return "text-red-600 bg-red-50";
    if (isToday(date)) return "text-orange-600 bg-orange-50";
    if (differenceInDays(date, new Date()) <= 3)
      return "text-yellow-600 bg-yellow-50";
    return "text-green-600 bg-green-50";
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <Calendar className="w-5 h-5 text-primary" />
            Task Timeline
          </CardTitle>
          <Badge variant="outline" className="font-normal">
            {tasks.length} tasks
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="relative">
          <div className="absolute left-4 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-4">
            {sortedTasks.map((task) => {
              const priority = priorityConfig[task.priority];
              const status = statusConfig[task.status];
              const StatusIcon = status.icon;
              const hasConflicts = task.conflicts.length > 0;
              const deadlineText = getDeadlineText(task.deadline);
              const deadlineColor = getDeadlineColor(task.deadline);

              return (
                <div
                  key={task.id}
                  className={cn(
                    "relative pl-10 pr-4 py-3 rounded-lg transition-all duration-200",
                    "hover:bg-muted/50 cursor-pointer",
                    hasConflicts && "bg-red-50/50 hover:bg-red-50",
                  )}
                >
                  <div
                    className={cn(
                      "absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 border-background",
                      task.status === "completed"
                        ? "bg-green-500"
                        : hasConflicts
                          ? "bg-red-500"
                          : "bg-primary",
                    )}
                  />

                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-medium text-foreground truncate">
                            {task.title}
                          </h4>
                          {hasConflicts && (
                            <Badge
                              variant="destructive"
                              className="text-xs flex items-center gap-1"
                            >
                              <AlertTriangle className="w-3 h-3" />
                              Conflict
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground line-clamp-1 mt-0.5">
                          {task.description}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge
                        variant="secondary"
                        className={cn(
                          "text-xs flex items-center gap-1.5",
                          status.color,
                        )}
                      >
                        <StatusIcon className="w-3 h-3" />
                        {status.label}
                      </Badge>

                      <Badge
                        variant="secondary"
                        className={cn(
                          "text-xs flex items-center gap-1.5",
                          priority.bg,
                          priority.text,
                        )}
                      >
                        <span
                          className={cn(
                            "w-1.5 h-1.5 rounded-full",
                            priority.color,
                          )}
                        />
                        {priority.label}
                      </Badge>

                      <Badge
                        variant="secondary"
                        className={cn(
                          "text-xs flex items-center gap-1.5",
                          deadlineColor,
                        )}
                      >
                        <Clock className="w-3 h-3" />
                        {format(task.deadline, "MMM d")} • {deadlineText}
                      </Badge>
                    </div>

                    {hasConflicts && (
                      <div className="flex items-center gap-2 text-xs text-red-600">
                        <AlertTriangle className="w-3 h-3" />
                        <span>Conflicts with: {task.conflicts.join(", ")}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-border">
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-primary" />
              Pending
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              In Progress
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500" />
              Completed
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500" />
              Conflict
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
