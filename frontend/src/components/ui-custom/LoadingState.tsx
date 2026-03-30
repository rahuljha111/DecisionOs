import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { Brain, Sparkles, Zap, Activity } from "lucide-react";

interface LoadingStateProps {
  className?: string;
}

const loadingMessages = [
  { text: "Analyzing your situation...", icon: Brain },
  { text: "Simulating outcomes...", icon: Activity },
  { text: "Evaluating constraints...", icon: Zap },
  { text: "Generating recommendations...", icon: Sparkles },
];

export function LoadingState({ className }: LoadingStateProps) {
  return (
    <Card className={cn("w-full", className)}>
      <CardContent className="p-12">
        <div className="flex flex-col items-center justify-center space-y-8">
          <div className="relative">
            <div className="absolute inset-0 w-24 h-24 -m-4 rounded-full border-2 border-primary/20 animate-ping" />

            <div className="absolute inset-0 w-20 h-20 -m-2 rounded-full border-2 border-primary/30 animate-pulse" />

            <div className="relative w-16 h-16 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center animate-pulse">
              <Brain className="w-8 h-8 text-primary-foreground" />
            </div>

            <div
              className="absolute inset-0 w-24 h-24 -m-4 animate-spin"
              style={{ animationDuration: "3s" }}
            >
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-primary" />
            </div>
            <div
              className="absolute inset-0 w-28 h-28 -m-6 animate-spin"
              style={{ animationDuration: "4s", animationDirection: "reverse" }}
            >
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-primary/60" />
            </div>
          </div>

          <div className="space-y-3 text-center">
            <h3 className="text-lg font-semibold text-foreground">
              AI is thinking...
            </h3>
            <div className="space-y-2">
              {loadingMessages.map((message, index) => {
                const Icon = message.icon;
                return (
                  <div
                    key={index}
                    className={cn(
                      "flex items-center justify-center gap-2 text-sm transition-all duration-500",
                      "animate-pulse",
                    )}
                    style={{
                      animationDelay: `${index * 200}ms`,
                      opacity: 0.5 + (index % 2) * 0.5,
                    }}
                  >
                    <Icon className="w-4 h-4 text-primary" />
                    <span className="text-muted-foreground">
                      {message.text}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="w-64 space-y-2">
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary to-primary/60 rounded-full animate-[shimmer_2s_infinite]"
                style={{
                  width: "100%",
                  backgroundSize: "200% 100%",
                  animation: "shimmer 2s linear infinite",
                }}
              />
            </div>
            <p className="text-xs text-center text-muted-foreground">
              This may take a few moments
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
