import { Activity, CheckCircle2, Clock, Cpu } from "lucide-react";
import { useMemo } from "react";
import type { Ticket } from "@/lib/types";

function Kpi({
  label,
  value,
  sub,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: typeof Activity;
  accent: "primary" | "safe" | "warn" | "danger";
}) {
  const accentClass = {
    primary: "text-primary",
    safe: "text-safe",
    warn: "text-warn",
    danger: "text-danger",
  }[accent];
  return (
    <div className="glass rounded-xl p-5 relative overflow-hidden">
      <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-primary/10 blur-2xl" />
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground font-mono">
          {label}
        </span>
        <Icon className={`h-4 w-4 ${accentClass}`} />
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className={`text-3xl font-semibold font-mono ${accentClass}`}>{value}</span>
        {sub && <span className="text-xs text-muted-foreground font-mono">{sub}</span>}
      </div>
    </div>
  );
}

export function KpiBar({ tickets }: { tickets: Ticket[] }) {
  const { active, fixed, connected, cases } = useMemo(() => {
    const fixed = tickets.filter((t) => t.status === "Fixed").length;
    const active = tickets.filter((t) => t.status !== "Fixed").length;
    const cases = tickets.length;
    const inProgress = tickets.filter((t) =>
      ["Analyzing", "Troubleshooting", "Validating"].includes(t.status),
    ).length;
    const connected = cases > 0 ? Math.round(((fixed + inProgress * 0.5) / cases) * 100) : 0;
    return { active, fixed, connected, cases };
  }, [tickets]);

  return (
    <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <Kpi label="Active Incidents" value={String(active)} sub="Phoenix queue" icon={Activity} accent="warn" />
      <Kpi label="Total Fixed" value={String(fixed)} sub="submitted to ERP" icon={CheckCircle2} accent="safe" />
      <Kpi label="Hackathon Cases" value={String(cases)} sub="team tickets" icon={Cpu} accent="primary" />
      <Kpi label="In Progress" value={`${connected}%`} sub="workflow active" icon={Clock} accent="primary" />
    </section>
  );
}
