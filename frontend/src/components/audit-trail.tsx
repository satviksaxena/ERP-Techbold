import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { CollapsiblePanel } from "@/components/collapsible-panel";
import { cn } from "@/lib/utils";

type AuditEntry = {
  timestamp?: string;
  action?: string;
  ticket_id?: string;
  command?: string;
  error?: string;
  [key: string]: unknown;
};

function formatEntry(entry: AuditEntry): string {
  const parts: string[] = [];
  if (entry.command) parts.push(String(entry.command));
  if (entry.error) parts.push(String(entry.error));
  if (entry.status) parts.push(String(entry.status));
  if (entry.title) parts.push(String(entry.title));
  if (entry.count != null) parts.push(`count=${entry.count}`);
  return parts.join(" · ") || "—";
}

function actionTone(action: string): string {
  if (action.includes("failed") || action.includes("blocked") || action.includes("rejected")) {
    return "text-danger";
  }
  if (action.includes("executed") || action.includes("submitted") || action.includes("passed") || action.includes("auto_approved")) {
    return "text-safe";
  }
  if (action.includes("retry") || action.includes("selected")) {
    return "text-primary";
  }
  return "text-muted-foreground";
}

export function AuditTrail({ ticketId }: { ticketId: string | undefined }) {
  const { data, isLoading } = useQuery({
    queryKey: ["audit", ticketId],
    queryFn: () => api.getAudit(ticketId),
    enabled: !!ticketId,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });

  const entries = (data?.entries ?? []) as AuditEntry[];
  const recent = [...entries].reverse().slice(0, 40);
  const summary =
    recent.length > 0
      ? `${recent.length} events · latest: ${recent[0].action ?? "action"}`
      : "No audit events yet — authorize a command to populate";

  return (
    <CollapsiblePanel title="Audit Trail" subtitle="persisted · Supabase + backend" summary={summary}>
      {isLoading && !entries.length ? (
        <p className="text-xs text-muted-foreground">Loading audit log…</p>
      ) : recent.length === 0 ? (
        <p className="text-xs text-muted-foreground font-mono">
          Every command and key action is recorded here for jury review.
        </p>
      ) : (
        <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
          {recent.map((e, i) => {
            const ts = e.timestamp ? new Date(String(e.timestamp)).toLocaleTimeString() : "—";
            const action = String(e.action ?? "event");
            return (
              <div
                key={`${action}-${ts}-${i}`}
                className="rounded-md border border-border/50 bg-background/25 px-2.5 py-2 font-mono text-[11px]"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className={cn("uppercase tracking-wider", actionTone(action))}>{action}</span>
                  <span className="text-muted-foreground/70 shrink-0">{ts}</span>
                </div>
                <p className="mt-1 text-muted-foreground break-all leading-relaxed">{formatEntry(e)}</p>
              </div>
            );
          })}
        </div>
      )}
    </CollapsiblePanel>
  );
}

export function commandFailed(cmd: { output_logs?: string | null; human_status?: string }): boolean {
  if (cmd.human_status !== "Approved" && cmd.human_status !== "Edited") return false;
  const output = (cmd.output_logs || "").toLowerCase();
  if (output.includes("execution failed")) return true;
  if (output.includes("exit code:") && !output.includes("exit code: 0")) return true;
  if (output.includes("[exit ") && !output.includes("[exit 0]")) return true;
  return false;
}

export function lastFailedCommand(
  commands: { human_status?: string; output_logs?: string | null }[],
): { human_status?: string; output_logs?: string | null; id?: string; command_text?: string } | null {
  for (let i = commands.length - 1; i >= 0; i--) {
    const c = commands[i];
    if (c.human_status === "Pending" || c.human_status === "Rejected") continue;
    if (c.human_status === "Approved" || c.human_status === "Edited") {
      return commandFailed(c) ? c : null;
    }
  }
  return null;
}

export function publicTestPassed(
  commands: { command_text?: string; human_status?: string; output_logs?: string | null }[],
): { passed: boolean; detail?: string } {
  for (let i = commands.length - 1; i >= 0; i--) {
    const c = commands[i];
    if (!(c.command_text || "").toLowerCase().includes("public-test")) continue;
    if (c.human_status !== "Approved" && c.human_status !== "Edited") continue;
    const output = c.output_logs || "";
    const lower = output.toLowerCase();
    if (lower.includes("exit code: 0") || lower.includes("[exit 0]")) {
      const okLine = output.split("\n").find((line) => line.includes("OK:"));
      return { passed: true, detail: okLine?.trim() ?? "All public-test checks passed." };
    }
    return { passed: false };
  }
  return { passed: false };
}

function commandSucceeded(output: string): boolean {
  const lower = output.toLowerCase();
  if (lower.includes("execution failed")) return false;
  if (lower.includes("exit code:") && !lower.includes("exit code: 0")) return false;
  if (lower.includes("[exit ") && !lower.includes("[exit 0]")) return false;
  return true;
}

function isFixCommand(text: string): boolean {
  const t = text.toLowerCase();
  return (
    t.includes("chmod") ||
    t.includes("chown") ||
    t.includes("systemctl restart") ||
    t.includes("systemctl start") ||
    t.includes("systemctl enable") ||
    t.includes("mount -o remount") ||
    t.includes("sed -i")
  );
}

const HACKATHON_GRADING_CODES = new Set(["7001", "7002"]);

export function isHackathonGradingTicket(
  ticket?: { ticket_code?: string | null },
): boolean {
  return HACKATHON_GRADING_CODES.has(String(ticket?.ticket_code ?? ""));
}

function usesPublicTestGrading(
  commands: { command_text?: string }[],
  ticket?: { ticket_code?: string | null },
): boolean {
  return (
    isHackathonGradingTicket(ticket) ||
    commands.some((c) => (c.command_text || "").toLowerCase().includes("public-test"))
  );
}

/** Matches backend _incident_resolved — hackathon tickets require latest public-test pass. */
export function incidentResolved(
  commands: { command_text?: string; human_status?: string; output_logs?: string | null }[],
  ticket?: { status?: string | null; ticket_code?: string | null },
): { passed: boolean; detail?: string } {
  const hackathonGrading = usesPublicTestGrading(commands, ticket);

  if (hackathonGrading) {
    const pub = publicTestPassed(commands);
    if (pub.passed) return pub;
    return { passed: false };
  }

  if (ticket?.status === "Fixed") {
    return { passed: true, detail: "Fix validated — ready to commit activity to Phoenix ERP." };
  }

  let lastFixIdx = -1;
  for (let i = commands.length - 1; i >= 0; i--) {
    const c = commands[i];
    if (c.human_status !== "Approved" && c.human_status !== "Edited") continue;
    const cmd = c.command_text || "";
    if (isFixCommand(cmd) && commandSucceeded(c.output_logs || "")) {
      lastFixIdx = i;
      break;
    }
  }
  if (lastFixIdx < 0) return { passed: false };

  for (let i = commands.length - 1; i > lastFixIdx; i--) {
    const c = commands[i];
    if (c.human_status !== "Approved" && c.human_status !== "Edited") continue;
    if (commandSucceeded(c.output_logs || "")) {
      const cmd = (c.command_text || "").slice(0, 48);
      return { passed: true, detail: `Post-fix verification succeeded (${cmd}).` };
    }
  }

  return { passed: false };
}
