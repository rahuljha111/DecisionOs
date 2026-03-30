import { useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { format } from "date-fns";
import {
  Calendar as CalendarIcon,
  Plus,
  X,
  Clock,
  AlertCircle,
  Sparkles,
  Briefcase,
  Users,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { DecisionInput, Constraint } from "@/types";
import { v4 as uuidv4 } from "uuid";

interface DecisionInputFormProps {
  onSubmit: (data: DecisionInput) => void;
  isLoading?: boolean;
}

const constraintTypes = [
  { value: "meeting", label: "Meeting", icon: Users },
  { value: "time-limit", label: "Time Limit", icon: Clock },
  { value: "dependency", label: "Dependency", icon: AlertCircle },
  { value: "resource", label: "Resource", icon: Briefcase },
];

const priorityOptions = [
  { value: "low", label: "Low Priority", color: "bg-blue-500" },
  { value: "medium", label: "Medium Priority", color: "bg-yellow-500" },
  { value: "high", label: "High Priority", color: "bg-red-500" },
];

export function DecisionInputForm({
  onSubmit,
  isLoading,
}: DecisionInputFormProps) {
  const [taskDescription, setTaskDescription] = useState("");
  const [deadline, setDeadline] = useState<Date>();
  const [priority, setPriority] = useState<"low" | "medium" | "high">("medium");
  const [constraints, setConstraints] = useState<Constraint[]>([]);
  const [newConstraint, setNewConstraint] = useState("");
  const [constraintType, setConstraintType] =
    useState<Constraint["type"]>("meeting");

  const handleAddConstraint = () => {
    if (newConstraint.trim()) {
      setConstraints([
        ...constraints,
        {
          id: uuidv4(),
          type: constraintType,
          description: newConstraint.trim(),
        },
      ]);
      setNewConstraint("");
    }
  };

  const handleRemoveConstraint = (id: string) => {
    setConstraints(constraints.filter((c) => c.id !== id));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (taskDescription && deadline) {
      onSubmit({
        taskDescription,
        deadline,
        constraints,
        priority,
      });
    }
  };

  const getConstraintIcon = (type: Constraint["type"]) => {
    const item = constraintTypes.find((t) => t.value === type);
    const Icon = item?.icon || AlertCircle;
    return <Icon className="w-3 h-3" />;
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Sparkles className="w-5 h-5 text-primary" />
          New Decision
        </CardTitle>
        <CardDescription>
          Describe your task and constraints. Our AI will analyze and recommend
          the best approach.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Task Description */}
          <div className="space-y-2">
            <Label htmlFor="task" className="text-sm font-medium">
              Task Description
            </Label>
            <Textarea
              id="task"
              placeholder="Describe what you need to accomplish..."
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              className="min-h-[100px] resize-none"
              disabled={isLoading}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-sm font-medium">Deadline</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      "w-full justify-start text-left font-normal",
                      !deadline && "text-muted-foreground",
                    )}
                    disabled={isLoading}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {deadline ? format(deadline, "PPP") : "Select a date"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={deadline}
                    onSelect={setDeadline}
                    disabled={(date) => date < new Date()}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>

            <div className="space-y-2">
              <Label className="text-sm font-medium">Priority Level</Label>
              <Select
                value={priority}
                onValueChange={(v) =>
                  setPriority(v as "low" | "medium" | "high")
                }
                disabled={isLoading}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {priorityOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      <div className="flex items-center gap-2">
                        <span
                          className={cn("w-2 h-2 rounded-full", option.color)}
                        />
                        {option.label}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-sm font-medium">
              Constraints & Blockers
            </Label>

            <div className="flex gap-2">
              <Select
                value={constraintType}
                onValueChange={(v) =>
                  setConstraintType(v as Constraint["type"])
                }
                disabled={isLoading}
              >
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {constraintTypes.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      <div className="flex items-center gap-2">
                        <type.icon className="w-4 h-4" />
                        {type.label}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                placeholder="Add a constraint (e.g., 'Team meeting at 2pm')"
                value={newConstraint}
                onChange={(e) => setNewConstraint(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddConstraint();
                  }
                }}
                disabled={isLoading}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleAddConstraint}
                disabled={isLoading || !newConstraint.trim()}
              >
                <Plus className="w-4 h-4" />
              </Button>
            </div>

            {constraints.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2">
                {constraints.map((constraint) => (
                  <Badge
                    key={constraint.id}
                    variant="secondary"
                    className="flex items-center gap-2 px-3 py-1.5 text-sm"
                  >
                    {getConstraintIcon(constraint.type)}
                    <span className="capitalize">{constraint.type}:</span>
                    {constraint.description}
                    <button
                      type="button"
                      onClick={() => handleRemoveConstraint(constraint.id)}
                      className="ml-1 hover:text-red-500 transition-colors"
                      disabled={isLoading}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <Button
            type="submit"
            className="w-full h-12 text-base font-medium"
            disabled={isLoading || !taskDescription || !deadline}
          >
            {isLoading ? (
              <>
                <Zap className="w-5 h-5 mr-2 animate-pulse" />
                Analyzing...
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5 mr-2" />
                Analyze & Recommend
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
