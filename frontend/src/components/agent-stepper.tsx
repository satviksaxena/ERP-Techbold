import { AGENTS, type Agent } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Check, Brain, Cpu, FileText, Loader2, Wrench } from "lucide-react";

const icons: Record<Agent, typeof Brain> = {
  "Problem Analyzer": Brain,
  "Customer System Analyzer": Cpu,
  "Problem Solver": Wrench,
  "Activity Log Generator": FileText,
};

export function AgentStepper({ active, resolved = false }: { active: string; resolved?: boolean }) {
  const activeIdx = AGENTS.indexOf(active as Agent);
  return (
    <div className="space-y-3">
      {AGENTS.map((a, i) => {
        const Icon = icons[a];
        const state = resolved || i < activeIdx ? "done" : i === activeIdx ? "active" : "pending";
        return (
          <div key={a} className="flex items-center gap-3">
            <div
              className={cn(
                "h-9 w-9 grid place-items-center rounded-md border font-mono text-xs shrink-0 transition",
                state === "done" && "border-safe/60 text-safe bg-safe/10",
                state === "active" && !resolved && "border-primary text-primary glow-primary bg-primary/10",
                state === "active" && resolved && "border-safe/60 text-safe bg-safe/10",
                state === "pending" && "border-border text-muted-foreground bg-background/30",
              )}
            >
              {state === "done" || resolved ? (
                <Check className="h-4 w-4" />
              ) : state === "active" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Icon className="h-4 w-4" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div
                className={cn(
                  "text-sm font-medium",
                  state === "pending" && "text-muted-foreground",
                )}
              >
                {a}
              </div>
              <div className="text-[10px] uppercase tracking-[0.2em] font-mono text-muted-foreground">
                {state === "done" || resolved ? "complete" : state === "active" ? "running" : "queued"}
              </div>
            </div>
            {i < AGENTS.length - 1 && (
              <div className="absolute" />
            )}
          </div>
        );
      })}
    </div>
  );
}
