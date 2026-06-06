import { cn } from "@/lib/utils";
import type { Priority } from "@/lib/types";

const styles: Record<Priority, { dot: string; text: string; ring: string }> = {
  Low:      { dot: "bg-muted-foreground",  text: "text-muted-foreground",  ring: "ring-border" },
  Medium:   { dot: "bg-primary",           text: "text-primary",           ring: "ring-primary/40" },
  High:     { dot: "bg-warn",              text: "text-warn",              ring: "ring-warn/40" },
  Critical: { dot: "bg-danger",            text: "text-danger",            ring: "ring-danger/50" },
};

export function PriorityBadge({ priority, className }: { priority: string; className?: string }) {
  const s = styles[(priority as Priority)] ?? styles.Medium;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-mono uppercase tracking-wider ring-1 bg-background/40",
        s.text,
        s.ring,
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full pulse-dot", s.dot)} />
      {priority}
    </span>
  );
}

const statusColor: Record<string, string> = {
  Open: "text-muted-foreground ring-border",
  Analyzing: "text-primary ring-primary/40",
  Troubleshooting: "text-warn ring-warn/40",
  Validating: "text-primary ring-primary/40",
  Fixed: "text-safe ring-safe/50",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.18em] ring-1 bg-background/40",
        statusColor[status] ?? statusColor.Open,
      )}
    >
      {status}
    </span>
  );
}
