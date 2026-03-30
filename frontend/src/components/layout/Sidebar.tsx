import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  LayoutDashboard,
  PlusCircle,
  History,
  Settings,
  HelpCircle,
  Sparkles,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";

interface SidebarProps {
  activeView: string;
  onViewChange: (view: string) => void;
}

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
}

const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "new-decision", label: "New Decision", icon: PlusCircle },
  { id: "history", label: "History", icon: History },
];

const bottomItems: NavItem[] = [
  { id: "settings", label: "Settings", icon: Settings },
  { id: "help", label: "Help", icon: HelpCircle },
];

export function Sidebar({ activeView, onViewChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className={cn(
        "flex flex-col h-screen bg-sidebar border-r border-border transition-all duration-300",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className="flex items-center h-16 px-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary">
            <Sparkles className="w-5 h-5 text-primary-foreground" />
          </div>
          {!collapsed && (
            <span className="font-semibold text-lg tracking-tight">
              DecisionOS
            </span>
          )}
        </div>
      </div>

      <ScrollArea className="flex-1 py-4">
        <nav className="px-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeView === item.id;

            return (
              <Button
                key={item.id}
                variant={isActive ? "secondary" : "ghost"}
                className={cn(
                  "w-full justify-start gap-3 h-11 transition-all duration-200",
                  isActive && "bg-secondary/80 shadow-sm",
                  collapsed && "justify-center px-2",
                )}
                onClick={() => onViewChange(item.id)}
              >
                <Icon className={cn("w-5 h-5", isActive && "text-primary")} />
                {!collapsed && (
                  <span className={cn(isActive && "font-medium")}>
                    {item.label}
                  </span>
                )}
              </Button>
            );
          })}
        </nav>
      </ScrollArea>

      <div className="p-2 border-t border-border space-y-1">
        {bottomItems.map((item) => {
          const Icon = item.icon;
          return (
            <Button
              key={item.id}
              variant="ghost"
              className={cn(
                "w-full justify-start gap-3 h-10 text-muted-foreground hover:text-foreground",
                collapsed && "justify-center px-2",
              )}
            >
              <Icon className="w-4 h-4" />
              {!collapsed && <span>{item.label}</span>}
            </Button>
          );
        })}

        <Button
          variant="ghost"
          size="sm"
          className={cn(
            "w-full justify-start gap-3 h-10 text-muted-foreground hover:text-foreground mt-2",
            collapsed && "justify-center px-2",
          )}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
