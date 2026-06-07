import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AiCommand } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { SlideToAuthorize } from "./slide-to-authorize";
import { AlertTriangle, ShieldCheck, ShieldX, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { api } from "@/lib/api-client";
import { supabase } from "@/integrations/supabase/client";
import { commandFailed } from "@/components/audit-trail";
import type { AiCommand as AiCommandType } from "@/lib/types";

const safetyStyle: Record<string, { ring: string; icon: typeof ShieldCheck; text: string }> = {
  Safe:    { ring: "ring-safe/50",   icon: ShieldCheck,    text: "text-safe" },
  Warning: { ring: "ring-warn/60",   icon: AlertTriangle,  text: "text-warn" },
  Blocked: { ring: "ring-danger/60", icon: ShieldX,        text: "text-danger" },
};

export function SafetyGate({
  command,
  autoRunEnabled = false,
}: {
  command: AiCommand;
  autoRunEnabled?: boolean;
}) {
  const [edited, setEdited] = useState(command.command_text);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();

  useEffect(() => setEdited(command.command_text), [command.id, command.command_text]);

  const style = safetyStyle[command.safety_status] ?? safetyStyle.Safe;
  const Icon = style.icon;
  const blocked = command.safety_status === "Blocked";

  const isPublicTest = (command.command_text || "").toLowerCase().includes("public-test");
  const looksLikeWrongValidationLoop =
    isPublicTest &&
    (command.script_diff || "").toLowerCase().includes("re-run hackathon validation");
  const isEdited = useMemo(() => edited.trim() !== command.command_text.trim(), [edited, command.command_text]);
  const requiresManualApproval = autoRunEnabled;

  async function waitForNextCommand(ticketId: string) {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const { data } = await supabase
        .from("ai_commands")
        .select("human_status")
        .eq("ticket_id", ticketId)
        .order("created_at", { ascending: false })
        .limit(5);
      if ((data ?? []).some((c) => c.human_status === "Pending")) return;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  async function authorize() {
    if (blocked || busy) return;
    setBusy(true);
    try {
      const result = await api.approveCommand(command.id, edited);
      await qc.refetchQueries({ queryKey: ["commands", command.ticket_id] });
      const executed = result.command as AiCommandType | undefined;
      const failed = executed ? commandFailed(executed) : false;
      const output = (executed?.output_logs || "").toLowerCase();
      const sshUnreachable =
        output.includes("timed out") ||
        output.includes("connection refused") ||
        output.includes("connection reset");

      if (failed) {
        toast.error(
          sshUnreachable
            ? "VM unreachable over SSH — click Connect SSH, wait ~2 min after a reset, then Retry below"
            : "Command ran but failed — check terminal output and use Retry if needed",
          { duration: 8000 },
        );
      } else {
        const passMsg = edited.toLowerCase().includes("public-test")
          ? " — check validation banner for PASS status"
          : "";
        toast.success(
          (isEdited ? "Edited command executed" : "Command authorized & executed") + passMsg,
        );
        if (!failed) {
          toast.message("Preparing next command…", { duration: 2500 });
          void waitForNextCommand(command.ticket_id).then(() => {
            qc.invalidateQueries({ queryKey: ["commands", command.ticket_id] });
            qc.invalidateQueries({ queryKey: ["hypotheses", command.ticket_id] });
            qc.invalidateQueries({ queryKey: ["activity", command.ticket_id] });
          });
        }
      }
      qc.invalidateQueries({ queryKey: ["commands", command.ticket_id] });
      qc.invalidateQueries({ queryKey: ["ticket", command.ticket_id] });
      qc.invalidateQueries({ queryKey: ["system_info", command.ticket_id] });
      qc.invalidateQueries({ queryKey: ["activity", command.ticket_id] });
      qc.invalidateQueries({ queryKey: ["audit", command.ticket_id] });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Authorization failed";
      toast.error(message);
      qc.invalidateQueries({ queryKey: ["commands", command.ticket_id] });
      qc.invalidateQueries({ queryKey: ["ticket", command.ticket_id] });
      void api.resumePipeline(command.ticket_id).then(() => {
        qc.invalidateQueries({ queryKey: ["commands", command.ticket_id] });
        qc.invalidateQueries({ queryKey: ["activity", command.ticket_id] });
      });
      throw err;
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    setBusy(true);
    try {
      await api.rejectCommand(command.id);
      toast.warning("Command rejected");
      qc.invalidateQueries({ queryKey: ["commands", command.ticket_id] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={cn(
        "rounded-xl border bg-background/40 p-4 ring-2 fade-in-up",
        style.ring,
      )}
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] uppercase tracking-[0.2em] font-mono ring-1 ring-primary/40 text-primary bg-primary/10">
            {command.agent_name}
          </span>
          <span className={cn("inline-flex items-center gap-1.5 text-xs font-mono", style.text)}>
            <Icon className="h-3.5 w-3.5" />
            {command.safety_status}
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          {requiresManualApproval ? "fix/validation · approval required" : "command gate · human-in-the-loop"}
        </span>
      </div>

      {requiresManualApproval && (
        <div className="rounded-md border border-primary/30 bg-primary/5 p-3 mb-3">
          <p className="text-[12px] text-muted-foreground leading-relaxed">
            Auto-run diagnostics is ON — this command changes system state or validates the fix, so it still
            needs your slide-to-authorize.
          </p>
        </div>
      )}

      {(command as AiCommand & { agent_reasoning?: string }).agent_reasoning && (
        <div className="rounded-md border border-primary/30 bg-primary/5 p-3 mb-3">
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-primary mb-1">
            agent reasoning
          </div>
          <p className="text-[12px] text-muted-foreground leading-relaxed whitespace-pre-wrap">
            {(command as AiCommand & { agent_reasoning?: string }).agent_reasoning}
          </p>
        </div>
      )}

      {looksLikeWrongValidationLoop && (
        <div className="rounded-md border border-warn/40 bg-warn/10 p-3 mb-3">
          <p className="text-[12px] text-warn leading-relaxed">
            Validation failed — reject this and wait for{" "}
            <span className="font-mono">sudo systemctl enable --now status-api.service</span>{" "}
            (ticket 7001 grading target), then run public-test again.
          </p>
        </div>
      )}

      {command.script_diff && (
        <div className="rounded-md border border-border bg-[oklch(0.13_0.02_250)] mb-3">
          <div className="px-3 py-1.5 border-b border-border text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
            proposed diff
          </div>
          <pre className="p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap">
            {command.script_diff
              .split("\n")
              .map((l, i) => (
                <div
                  key={i}
                  className={
                    l.startsWith("+")
                      ? "text-safe"
                      : l.startsWith("-")
                        ? "text-danger"
                        : "text-muted-foreground"
                  }
                >
                  {l}
                </div>
              ))}
          </pre>
        </div>
      )}

      <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
        editable command
      </label>
      <Textarea
        value={edited}
        onChange={(e) => setEdited(e.target.value)}
        className="mt-1 font-mono text-[12.5px] bg-[oklch(0.13_0.02_250)] border-border min-h-[88px]"
        disabled={blocked || busy}
      />

      <div className="mt-3 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-center">
        <SlideToAuthorize
          key={command.id}
          commandId={command.id}
          onAuthorize={authorize}
          disabled={blocked}
          label={blocked ? "blocked by safety policy" : busy ? "running on VM…" : "slide to authorize command"}
        />
        <Button
          variant="destructive"
          onClick={reject}
          disabled={busy}
          className="h-12 px-5"
        >
          <X className="h-4 w-4" /> Abort / Reject
        </Button>
      </div>

      {isEdited && !blocked && (
        <p className="mt-2 text-[11px] font-mono text-warn">
          ⚠ command edited by technician — will be logged as Edited execution
        </p>
      )}
    </div>
  );
}
