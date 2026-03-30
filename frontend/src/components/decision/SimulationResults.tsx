import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { SimulationOption } from "@/types";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Target,
  Clock,
  TrendingUp,
  Shield,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

interface SimulationResultsProps {
  options: SimulationOption[];
  selectedOptionId?: string;
}

const riskConfig = {
  low: {
    color: "bg-green-500",
    text: "text-green-600",
    bg: "bg-green-50",
    icon: Shield,
  },
  medium: {
    color: "bg-yellow-500",
    text: "text-yellow-600",
    bg: "bg-yellow-50",
    icon: AlertTriangle,
  },
  high: {
    color: "bg-red-500",
    text: "text-red-600",
    bg: "bg-red-50",
    icon: Target,
  },
};

export function SimulationResults({
  options,
  selectedOptionId,
}: SimulationResultsProps) {
  const [expandedOption, setExpandedOption] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedOption(expandedOption === id ? null : id);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Simulation Results</h3>
        <Badge variant="outline" className="font-normal">
          {options.length} options analyzed
        </Badge>
      </div>

      {options.map((option, index) => {
        const risk = riskConfig[option.riskLevel];
        const RiskIcon = risk.icon;
        const isExpanded = expandedOption === option.id;
        const isSelected = selectedOptionId === option.id;

        return (
          <Card
            key={option.id}
            className={cn(
              "transition-all duration-300 border-2",
              isSelected
                ? "border-primary shadow-lg shadow-primary/10"
                : "border-transparent hover:border-border",
            )}
          >
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm text-muted-foreground font-medium">
                      Option {String.fromCharCode(65 + index)}
                    </span>
                    {isSelected && (
                      <Badge className="bg-primary text-primary-foreground">
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        Recommended
                      </Badge>
                    )}
                  </div>
                  <CardTitle className="text-base font-semibold">
                    {option.name}
                  </CardTitle>
                </div>
                <Badge
                  variant="secondary"
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1",
                    risk.bg,
                    risk.text,
                  )}
                >
                  <RiskIcon className="w-3.5 h-3.5" />
                  <span className="capitalize">{option.riskLevel} Risk</span>
                </Badge>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {option.description}
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      <TrendingUp className="w-4 h-4" />
                      Success Rate
                    </span>
                    <span className="font-medium">
                      {option.successProbability}%
                    </span>
                  </div>
                  <Progress value={option.successProbability} className="h-2" />
                </div>

                <div className="flex items-center gap-1.5 text-sm">
                  <Clock className="w-4 h-4 text-muted-foreground" />
                  <span className="text-muted-foreground">
                    Est. completion:
                  </span>
                  <span className="font-medium">
                    {format(option.estimatedCompletion, "MMM d, yyyy")}
                  </span>
                </div>
              </div>

              <Collapsible
                open={isExpanded}
                onOpenChange={() => toggleExpand(option.id)}
              >
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
                  >
                    {isExpanded ? (
                      <>
                        <ChevronUp className="w-4 h-4" />
                        Show Less
                      </>
                    ) : (
                      <>
                        <ChevronDown className="w-4 h-4" />
                        View Details
                      </>
                    )}
                  </Button>
                </CollapsibleTrigger>

                <CollapsibleContent className="pt-4 space-y-4">
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <span className="text-sm font-medium">Outcome:</span>
                    <p className="text-sm text-muted-foreground mt-1">
                      {option.outcomeSummary}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <span className="text-sm font-medium text-green-600 flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4" />
                        Pros
                      </span>
                      <ul className="space-y-1">
                        {option.pros.map((pro, i) => (
                          <li
                            key={i}
                            className="text-sm text-muted-foreground flex items-start gap-1.5"
                          >
                            <span className="text-green-500 mt-1">•</span>
                            {pro}
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="space-y-2">
                      <span className="text-sm font-medium text-red-600 flex items-center gap-1.5">
                        <XCircle className="w-4 h-4" />
                        Cons
                      </span>
                      <ul className="space-y-1">
                        {option.cons.map((con, i) => (
                          <li
                            key={i}
                            className="text-sm text-muted-foreground flex items-start gap-1.5"
                          >
                            <span className="text-red-500 mt-1">•</span>
                            {con}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
