import { useState } from "react";
import { DecisionInputForm } from "@/components/decision/DecisionInputForm";
import { SimulationResults } from "@/components/decision/SimulationResults";
import { DecisionOutput } from "@/components/decision/DecisionOutput";
import { LoadingState } from "@/components/ui-custom/LoadingState";
import type { DecisionInput, DecisionResult } from "@/types";
import { mockCreateDecision } from "@/data/mockData";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

interface NewDecisionProps {
  onBack: () => void;
}

type DecisionState = "input" | "loading" | "results";

export function NewDecision({ onBack }: NewDecisionProps) {
  const [state, setState] = useState<DecisionState>("input");
  const [result, setResult] = useState<DecisionResult | null>(null);

  const handleSubmit = async (_data: DecisionInput) => {
    setState("loading");

    try {
      // Simulate API call
      const decisionResult = await mockCreateDecision();
      setResult(decisionResult);
      setState("results");
    } catch (error) {
      console.error("Failed to create decision:", error);
      setState("input");
    }
  };

  const handleReset = () => {
    setResult(null);
    setState("input");
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <Button
          variant="ghost"
          size="icon"
          onClick={onBack}
          className="rounded-full"
        >
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold text-foreground">New Decision</h1>
          <p className="text-muted-foreground">
            Let AI help you make the optimal choice
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {state === "input" && (
          <DecisionInputForm onSubmit={handleSubmit} isLoading={false} />
        )}

        {state === "loading" && <LoadingState />}

        {state === "results" && result && (
          <div className="space-y-6">
            <DecisionOutput result={result} onReset={handleReset} />
            <SimulationResults
              options={result.alternatives}
              selectedOptionId={result.selectedOptionId}
            />
          </div>
        )}
      </div>
    </div>
  );
}
