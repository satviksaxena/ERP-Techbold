import { Switch } from "@/components/ui/switch";
import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";

export function AutoRunDiagnosticsToggle({
  enabled,
  onChange,
  className,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex items-center gap-2.5 rounded-lg border border-border/60 bg-background/40 px-3 py-2 cursor-pointer select-none",
        enabled && "border-primary/40 bg-primary/5",
        className,
      )}
    >
      <Zap className={cn("h-4 w-4 shrink-0", enabled ? "text-primary" : "text-muted-foreground")} />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium leading-tight">Auto-run diagnostics</p>
        <p className="text-[10px] text-muted-foreground leading-snug mt-0.5">
          {enabled
            ? "Read-only checks run automatically · fixes still need approval"
            : "Every command needs slide-to-authorize"}
        </p>
      </div>
      <Switch checked={enabled} onCheckedChange={onChange} aria-label="Auto-run read-only diagnostics" />
    </label>
  );
}
