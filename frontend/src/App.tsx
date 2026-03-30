import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Dashboard } from "@/pages/Dashboard";
import { NewDecision } from "@/pages/NewDecision";
import { History } from "@/pages/History";
import { Toaster } from "@/components/ui/sonner";

type ViewType = "dashboard" | "new-decision" | "history";

function App() {
  const [activeView, setActiveView] = useState<ViewType>("dashboard");

  const handleViewChange = (view: string) => {
    setActiveView(view as ViewType);
  };

  const handleNewDecision = () => {
    setActiveView("new-decision");
  };

  const handleBackToDashboard = () => {
    setActiveView("dashboard");
  };

  return (
    <div className="h-screen overflow-hidden bg-background flex">
      <Sidebar activeView={activeView} onViewChange={handleViewChange} />

      <div className="flex-1 flex flex-col">
        <Header />

        <main className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-7xl mx-auto">
            {activeView === "dashboard" && (
              <Dashboard onNewDecision={handleNewDecision} />
            )}
            {activeView === "new-decision" && (
              <NewDecision onBack={handleBackToDashboard} />
            )}
            {activeView === "history" && <History />}
          </div>
        </main>
      </div>

      <Toaster />
    </div>
  );
}

export default App;
