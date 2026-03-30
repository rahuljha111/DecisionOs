import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { DecisionResult } from "@/types";
import {
  Sparkles,
  CheckCircle2,
  Brain,
  Lightbulb,
  Copy,
  Share2,
  RotateCcw,
} from "lucide-react";
import { useState } from "react";

interface DecisionOutputProps {
  result: DecisionResult;
  onReset?: () => void;
}

export function DecisionOutput({ result, onReset }: DecisionOutputProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = `DecisionOS Recommendation: ${result.recommendation}\n\nReasoning: ${result.reasoning}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <Card className="border-2 border-primary shadow-lg shadow-primary/10 overflow-hidden">
        <div className="bg-gradient-to-r from-primary/5 to-primary/10 px-6 py-4 border-b border-primary/20">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-primary-foreground" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                AI Recommendation
              </h3>
              <p className="text-sm text-muted-foreground">
                Based on analysis of your constraints and goals
              </p>
            </div>
          </div>
        </div>

        <CardContent className="p-6 space-y-6">
          <div className="space-y-2">
            <span className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              Selected Option
            </span>
            <h2 className="text-2xl font-bold text-foreground">
              {result.recommendation}
            </h2>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
                <Brain className="w-4 h-4" />
                AI Confidence
              </span>
              <Badge variant="secondary" className="font-semibold">
                {result.confidence}%
              </Badge>
            </div>
            <Progress value={result.confidence} className="h-2.5" />
          </div>

          <div className="space-y-3">
            <span className="text-sm font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
              <Lightbulb className="w-4 h-4" />
              Reasoning
            </span>
            <div className="p-4 bg-muted/50 rounded-lg border border-border">
              <p className="text-sm leading-relaxed text-foreground">
                {result.reasoning}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3 pt-2">
            <Button
              variant="outline"
              size="sm"
              className="flex items-center gap-2"
              onClick={handleCopy}
            >
              {copied ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-green-500" />
                  Copied!
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  Copy
                </>
              )}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="flex items-center gap-2"
            >
              <Share2 className="w-4 h-4" />
              Share
            </Button>
            {onReset && (
              <Button
                variant="outline"
                size="sm"
                className="flex items-center gap-2 ml-auto"
                onClick={onReset}
              >
                <RotateCcw className="w-4 h-4" />
                New Decision
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-500" />
            Key Insights
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            <li className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-xs font-medium text-primary">1</span>
              </span>
              <p className="text-sm text-muted-foreground">
                This approach balances risk and reward effectively given your
                timeline constraints.
              </p>
            </li>
            <li className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-xs font-medium text-primary">2</span>
              </span>
              <p className="text-sm text-muted-foreground">
                Success probability is high with manageable risk factors.
              </p>
            </li>
            <li className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                <span className="text-xs font-medium text-primary">3</span>
              </span>
              <p className="text-sm text-muted-foreground">
                Consider monitoring progress weekly to stay on track.
              </p>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
