import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Search,
  Calendar,
  ChevronRight,
  Sparkles,
  TrendingUp,
  Clock,
} from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";

interface DecisionHistory {
  id: string;
  title: string;
  description: string;
  date: Date;
  confidence: number;
  recommendation: string;
  category: string;
  status: "completed" | "pending" | "archived";
}

const mockHistory: DecisionHistory[] = [
  {
    id: "1",
    title: "Q4 Product Roadmap Prioritization",
    description:
      "Decided on key features for Q4 release based on resource constraints and market demand.",
    date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
    confidence: 92,
    recommendation: "Focus on core features, defer nice-to-haves",
    category: "Product",
    status: "completed",
  },
  {
    id: "2",
    title: "Team Resource Allocation",
    description:
      "Optimized team assignments across 3 concurrent projects with conflicting deadlines.",
    date: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
    confidence: 87,
    recommendation: "Redistribute 2 developers to critical path",
    category: "Management",
    status: "completed",
  },
  {
    id: "3",
    title: "Marketing Campaign Timing",
    description: "Analyzed optimal launch window for new product announcement.",
    date: new Date(Date.now() - 8 * 24 * 60 * 60 * 1000),
    confidence: 78,
    recommendation: "Delay by 2 weeks for better market conditions",
    category: "Marketing",
    status: "completed",
  },
  {
    id: "4",
    title: "Budget Reallocation Request",
    description:
      "Evaluated budget shifts between engineering and marketing departments.",
    date: new Date(Date.now() - 12 * 24 * 60 * 60 * 1000),
    confidence: 85,
    recommendation: "Approve 15% shift to engineering",
    category: "Finance",
    status: "completed",
  },
  {
    id: "5",
    title: "Hiring Decision - Senior Engineer",
    description:
      "Assessed candidate fit against team needs and project timeline.",
    date: new Date(Date.now() - 15 * 24 * 60 * 60 * 1000),
    confidence: 91,
    recommendation: "Extend offer with modified start date",
    category: "HR",
    status: "completed",
  },
  {
    id: "6",
    title: "Vendor Selection",
    description: "Compared 3 cloud providers for infrastructure migration.",
    date: new Date(Date.now() - 20 * 24 * 60 * 60 * 1000),
    confidence: 88,
    recommendation: "Select Provider B for best cost/performance",
    category: "Technical",
    status: "completed",
  },
];

const categories = [
  "All",
  "Product",
  "Management",
  "Marketing",
  "Finance",
  "HR",
  "Technical",
];

export function History() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");

  const filteredHistory = mockHistory.filter((item) => {
    const matchesSearch =
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory =
      selectedCategory === "All" || item.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Decision History
          </h1>
          <p className="text-muted-foreground mt-1">
            Review and learn from past AI-assisted decisions
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                <Sparkles className="w-6 h-6 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-bold">{mockHistory.length}</p>
                <p className="text-sm text-muted-foreground">Total Decisions</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {Math.round(
                    mockHistory.reduce(
                      (acc, item) => acc + item.confidence,
                      0,
                    ) / mockHistory.length,
                  )}
                  %
                </p>
                <p className="text-sm text-muted-foreground">Avg. Confidence</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                <Clock className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">2.3 days</p>
                <p className="text-sm text-muted-foreground">
                  Avg. Decision Time
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search decisions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {categories.map((category) => (
            <Button
              key={category}
              variant={selectedCategory === category ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedCategory(category)}
              className="whitespace-nowrap"
            >
              {category}
            </Button>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {filteredHistory.map((item) => (
          <Card
            key={item.id}
            className="hover:shadow-md transition-shadow cursor-pointer group"
          >
            <CardContent className="p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors">
                      {item.title}
                    </h3>
                    <Badge variant="secondary" className="text-xs">
                      {item.category}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-xs",
                        item.confidence >= 90 &&
                          "border-green-500 text-green-600",
                        item.confidence >= 80 &&
                          item.confidence < 90 &&
                          "border-blue-500 text-blue-600",
                        item.confidence < 80 &&
                          "border-yellow-500 text-yellow-600",
                      )}
                    >
                      {item.confidence}% confidence
                    </Badge>
                  </div>

                  <p className="text-sm text-muted-foreground mt-2">
                    {item.description}
                  </p>

                  <div className="flex items-center gap-4 mt-3">
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Calendar className="w-4 h-4" />
                      {format(item.date, "MMM d, yyyy")}
                    </div>
                    <div className="flex items-center gap-1.5 text-sm">
                      <span className="text-muted-foreground">
                        Recommendation:
                      </span>
                      <span className="font-medium text-foreground">
                        {item.recommendation}
                      </span>
                    </div>
                  </div>
                </div>

                <Button variant="ghost" size="icon" className="flex-shrink-0">
                  <ChevronRight className="w-5 h-5 text-muted-foreground" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}

        {filteredHistory.length === 0 && (
          <Card>
            <CardContent className="p-12 text-center">
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mx-auto mb-4">
                <Search className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                No decisions found
              </h3>
              <p className="text-muted-foreground mt-1">
                Try adjusting your search or filters
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
