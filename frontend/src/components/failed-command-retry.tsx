import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AiCommand } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";

export function FailedCommandRetry({
  command,
  ticketId,
}: {
  command: AiCommand | null;
  ticketId: string | undefined;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  if (!command || !ticketId) return null;

  async function retry() {
    setBusy(true);
    try {
      await api.retryCommand(command!.id);
      toast.success("Failed command re-queued — slide to authorize in the gate");
      qc.invalidateQueries({ queryKey: ["commands", ticketId] });
      qc.invalidateQueries({ queryKey: ["audit", ticketId] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-danger/40 bg-danger/5 p-3 flex flex-col sm:flex-row sm:items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-mono uppercase tracking-wider text-danger">Last command failed</p>
        <p className="mt-1 text-[11px] font-mono text-muted-foreground break-all">{command.command_text}</p>
      </div>
      <Button variant="outline" size="sm" onClick={retry} disabled={busy} className="shrink-0 border-warn/50">
        <RotateCcw className="h-4 w-4" /> Retry command
      </Button>
    </div>
  );
}
