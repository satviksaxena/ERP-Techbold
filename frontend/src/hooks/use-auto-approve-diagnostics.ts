import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { canAutoApprove } from "@/lib/command-intent";
import { commandFailed } from "@/components/audit-trail";
import type { AiCommand } from "@/lib/types";

export function useAutoApproveDiagnostics({
  enabled,
  pending,
  validationPassed,
  pipelineSettling,
}: {
  enabled: boolean;
  pending: AiCommand | undefined;
  validationPassed: boolean;
  pipelineSettling: boolean;
}) {
  const qc = useQueryClient();
  const inFlightRef = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled || !pending || validationPassed || pipelineSettling) return;
    if (!canAutoApprove(pending.command_text, pending.safety_status)) return;
    if (inFlightRef.current === pending.id) return;

    inFlightRef.current = pending.id;
    let cancelled = false;

    const run = async () => {
      try {
        const result = await api.approveCommand(pending.id, undefined, { autoApproved: true });
        if (cancelled) return;
        const executed = result.command as AiCommand | undefined;
        const failed = executed ? commandFailed(executed) : false;
        const preview = (pending.command_text || "").slice(0, 56);
        if (failed) {
          toast.error(`Auto-run failed: ${preview}`, { duration: 6000 });
        } else {
          toast.message(`Auto-ran diagnostic: ${preview}`, { duration: 2500 });
        }
        await qc.refetchQueries({ queryKey: ["commands", pending.ticket_id] });
        qc.invalidateQueries({ queryKey: ["ticket", pending.ticket_id] });
        qc.invalidateQueries({ queryKey: ["system_info", pending.ticket_id] });
        qc.invalidateQueries({ queryKey: ["activity", pending.ticket_id] });
        qc.invalidateQueries({ queryKey: ["audit", pending.ticket_id] });
        qc.invalidateQueries({ queryKey: ["hypotheses", pending.ticket_id] });
      } catch (err) {
        if (cancelled) return;
        inFlightRef.current = null;
        toast.error(err instanceof Error ? err.message : "Auto-run failed");
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [
    enabled,
    pending?.id,
    pending?.command_text,
    pending?.safety_status,
    pending?.ticket_id,
    validationPassed,
    pipelineSettling,
    qc,
  ]);
}
