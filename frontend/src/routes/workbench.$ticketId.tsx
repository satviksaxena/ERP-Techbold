import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppHeader } from "@/components/app-header";
import {
  useActivity,
  useCommands,
  useSystemInfo,
  useTicket,
} from "@/lib/queries";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { AgentStepper } from "@/components/agent-stepper";
import { TerminalEmulator } from "@/components/terminal-emulator";
import { SafetyGate } from "@/components/safety-gate";
import { ActivityDraft } from "@/components/activity-draft";
import { HypothesisTabs } from "@/components/hypothesis-tabs";
import { AuditTrail, incidentResolved, lastFailedCommand } from "@/components/audit-trail";
import { FailedCommandRetry } from "@/components/failed-command-retry";
import { ValidationPassBanner } from "@/components/validation-pass-banner";
import { CollapsiblePanel, truncateSummary } from "@/components/collapsible-panel";
import { ArrowLeft, Plug, ServerCrash, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export const Route = createFileRoute("/workbench/$ticketId")({
  head: ({ params }) => ({
    meta: [
      { title: `Workbench · ${params.ticketId.slice(0, 8)} — Autopilot` },
      { name: "description", content: "Technician workbench for AI-assisted incident resolution." },
    ],
  }),
  component: WorkbenchPage,
  errorComponent: ({ error, reset }) => (
    <div className="min-h-screen grid-bg">
      <AppHeader />
      <div className="mx-auto max-w-3xl px-6 py-16 glass rounded-xl mt-8 glow-danger">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <ServerCrash className="h-5 w-5 text-danger" /> Workbench failed to load
        </h2>
        <p className="text-sm text-muted-foreground mt-2">{error.message}</p>
        <Button onClick={reset} className="mt-4">Retry</Button>
      </div>
    </div>
  ),
  notFoundComponent: () => (
    <div className="min-h-screen grid-bg">
      <AppHeader />
      <div className="mx-auto max-w-3xl px-6 py-16 glass rounded-xl mt-8">
        <h2 className="text-lg font-semibold">Ticket not found</h2>
        <p className="text-sm text-muted-foreground mt-2">
          This workbench link may be from an old database session. Open the ticket again from the matrix.
        </p>
        <Link to="/" className="text-primary text-sm">← back to matrix</Link>
      </div>
    </div>
  ),
});

function WorkbenchPage() {
  const { ticketId: ticketRef } = Route.useParams();
  const { data: ticket, isLoading: tLoad, error: tErr } = useTicket(ticketRef);
  const ticketId = ticket?.id;
  const { data: sys } = useSystemInfo(ticketId);
  const { data: cmds = [], isFetching: cmdsFetching } = useCommands(ticketId);
  const { data: activity } = useActivity(ticketId);
  const qc = useQueryClient();

  const pending = useMemo(
    () => [...cmds].reverse().find((c) => c.human_status === "Pending"),
    [cmds],
  );
  const validationPass = useMemo(
    () => incidentResolved(cmds, ticket),
    [cmds, ticket],
  );
  const lastFailed = useMemo(() => lastFailedCommand(cmds), [cmds]);
  const executedCount = useMemo(
    () => cmds.filter((c) => c.human_status === "Approved" || c.human_status === "Edited").length,
    [cmds],
  );
  const sshLive = useMemo(
    () =>
      cmds.some(
        (c) =>
          (c.human_status === "Approved" || c.human_status === "Edited") &&
          c.output_logs &&
          !c.output_logs.includes("[mock]"),
      ),
    [cmds],
  );
  const [analyzing, setAnalyzing] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [pipelineSettling, setPipelineSettling] = useState(false);
  const reconcileAttempted = useRef(false);

  const RESUME_COOLDOWN_MS = 20_000;

  useEffect(() => {
    reconcileAttempted.current = false;
  }, [ticketId]);

  useEffect(() => {
    if (!ticketId) return;
    const key = `resume:${ticketId}`;
    const last = Number(sessionStorage.getItem(key) || 0);
    if (Date.now() - last < RESUME_COOLDOWN_MS) return;
    sessionStorage.setItem(key, String(Date.now()));

    setPipelineSettling(true);
    api
      .resumePipeline(ticketId)
      .then(async (result) => {
        if (result.resumed) {
          await qc.refetchQueries({ queryKey: ["commands", ticketId] });
          qc.invalidateQueries({ queryKey: ["ticket", ticketRef] });
          qc.invalidateQueries({ queryKey: ["activity", ticketId] });
        }
      })
      .catch(() => {
        sessionStorage.removeItem(key);
      })
      .finally(() => {
        setPipelineSettling(false);
      });
  }, [ticketId, ticketRef, qc]);

  useEffect(() => {
    if (!ticketId) return;
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      // Only recover if the gate looks stuck (no pending after prior commands).
      const hasExecuted = cmds.some(
        (c) => c.human_status === "Approved" || c.human_status === "Edited",
      );
      const hasPending = cmds.some((c) => c.human_status === "Pending");
      if (!hasExecuted || hasPending) return;
      const key = `resume:${ticketId}`;
      const last = Number(sessionStorage.getItem(key) || 0);
      if (Date.now() - last < RESUME_COOLDOWN_MS) return;
      sessionStorage.setItem(key, String(Date.now()));
      void api.resumePipeline(ticketId).then((result) => {
        if (result.resumed) {
          qc.invalidateQueries({ queryKey: ["commands", ticketId] });
          qc.invalidateQueries({ queryKey: ["activity", ticketId] });
        }
      });
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [ticketId, qc, cmds]);

  useEffect(() => {
    if (!ticketId || !validationPass.passed || !pending || reconcileAttempted.current) return;
    if (!(pending.command_text || "").toLowerCase().includes("public-test")) return;
    reconcileAttempted.current = true;
    api
      .reconcileValidation(ticketId)
      .then(() => {
        qc.invalidateQueries({ queryKey: ["commands", ticketId] });
        qc.invalidateQueries({ queryKey: ["ticket", ticketRef] });
        qc.invalidateQueries({ queryKey: ["activity", ticketId] });
        qc.invalidateQueries({ queryKey: ["audit", ticketId] });
      })
      .catch(() => {
        reconcileAttempted.current = false;
      });
  }, [ticketId, ticketRef, validationPass.passed, pending, qc]);

  async function startAnalysis() {
    if (!ticketId) return;
    setAnalyzing(true);
    try {
      const result = await api.startAnalysis(ticketId);
      toast.success("AI analysis started — review the proposed command");
      if (result.command && typeof result.command === "object" && "command_text" in result.command) {
        toast("Command proposed", {
          description: String((result.command as { command_text: string }).command_text),
        });
      }
      qc.invalidateQueries({ queryKey: ["commands", ticketId] });
      qc.invalidateQueries({ queryKey: ["ticket", ticketRef] });
      qc.invalidateQueries({ queryKey: ["system_info", ticketId] });
      qc.invalidateQueries({ queryKey: ["activity", ticketId] });
      qc.invalidateQueries({ queryKey: ["hypotheses", ticketId] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  async function connectSsh() {
    if (!ticketId) return;
    setConnecting(true);
    try {
      const result = await api.connectSsh(ticketId);
      toast.success(`SSH ${result.connection_status.toLowerCase()}`);
      qc.invalidateQueries({ queryKey: ["system_info", ticketId] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "SSH connection failed");
      qc.invalidateQueries({ queryKey: ["system_info", ticketId] });
    } finally {
      setConnecting(false);
    }
  }

  if (tLoad) {
    return (
      <div className="min-h-screen grid-bg">
        <AppHeader />
        <div className="mx-auto max-w-[1600px] px-6 py-8 grid grid-cols-1 lg:grid-cols-[320px_1fr_360px] gap-4">
          <div className="glass rounded-xl h-[600px] animate-pulse" />
          <div className="glass rounded-xl h-[600px] animate-pulse" />
          <div className="glass rounded-xl h-[600px] animate-pulse" />
        </div>
      </div>
    );
  }
  if (tErr) throw tErr;
  if (!ticket) throw notFound();

  return (
    <div className="min-h-screen grid-bg">
      <AppHeader />
      <main className="mx-auto max-w-[1600px] px-6 py-6 fade-in-up">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3 min-w-0">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/">
                <ArrowLeft className="h-4 w-4" /> Matrix
              </Link>
            </Button>
            <span className="font-mono text-xs text-primary tracking-wider">
              {ticket.ticket_code}
            </span>
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            <h1 className="text-base sm:text-lg font-semibold truncate">{ticket.title}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={connectSsh} variant="outline" size="sm" disabled={connecting}>
              <Plug className="h-4 w-4" /> Connect SSH
            </Button>
            <Button onClick={startAnalysis} variant="outline" size="sm" disabled={analyzing}>
              <Sparkles className="h-4 w-4" /> {analyzing ? "Gemini analyzing…" : "Start Analysis (Gemini)"}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_380px] gap-4">
          {/* Zone A */}
          <aside className="space-y-4">
            <CollapsiblePanel
              title="Customer Report"
              summary={truncateSummary(ticket.report_text)}
            >
              <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
                {ticket.report_text || "—"}
              </p>
              <div className="mt-3 text-[11px] font-mono text-muted-foreground">
                <span>opened by </span>
                <span className="text-foreground">{ticket.customer_name}</span>
              </div>
            </CollapsiblePanel>

            <Panel title="Loaded System Info">
              {sys ? (
                <div className="space-y-2 text-sm">
                  <Row k="Host" v={sys.host_ip} />
                  <Row k="User" v={sys.username} />
                  <Row k="Port" v={String(sys.port)} />
                  <Row k="OS" v={sys.os_version} />
                  {sys.system_notes && (
                    <p className="text-[10px] font-mono text-muted-foreground pt-1 border-t border-border/40 mt-2 leading-relaxed">
                      {sys.system_notes}
                    </p>
                  )}
                  <div className="flex items-center gap-2 pt-2 mt-2 border-t border-border/60">
                    <span
                      className={cn(
                        "h-2.5 w-2.5 rounded-full pulse-dot",
                        sshLive
                          ? "bg-safe"
                          : sys.connection_status === "Connected"
                            ? "bg-warn"
                            : sys.connection_status === "Failed"
                              ? "bg-danger"
                              : "bg-warn",
                      )}
                    />
                    <span
                      className={cn(
                        "text-xs font-mono uppercase tracking-[0.2em]",
                        sshLive
                          ? "text-safe"
                          : sys.connection_status === "Connected"
                            ? "text-warn"
                            : sys.connection_status === "Failed"
                              ? "text-danger"
                              : "text-warn",
                      )}
                    >
                      ssh ·{" "}
                      {sshLive
                        ? "live"
                        : sys.connection_status === "Connected"
                          ? "linked"
                          : sys.connection_status}
                    </span>
                    <Plug className="ml-auto h-4 w-4 text-muted-foreground" />
                  </div>
                  {sys.connection_status === "Connected" && !sshLive && (
                    <div className="mt-2 text-[11px] font-mono text-warn rounded border border-warn/40 bg-warn/10 p-2">
                      SSH handshake OK — authorize a command to stream output in the terminal.
                    </div>
                  )}
                  {sys.connection_status !== "Connected" && !sshLive && (
                    <div className="mt-2 text-[11px] font-mono text-warn rounded border border-warn/40 bg-warn/10 p-2">
                      ⚠ SSH not connected — click Connect SSH or authorize a command to establish the link.
                    </div>
                  )}
                  {sshLive && sys.connection_status !== "Connected" && (
                    <div className="mt-2 text-[11px] font-mono text-safe rounded border border-safe/40 bg-safe/10 p-2">
                      ✓ Commands reached the VM — SSH link active via last execution.
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No system info attached.</p>
              )}
            </Panel>

            <Panel title="Agent Pipeline">
              <AgentStepper
                active={validationPass.passed ? "Activity Log Generator" : ticket.active_agent}
                resolved={validationPass.passed || ticket.status === "Fixed"}
              />
            </Panel>
          </aside>

          {/* Zone B */}
          <section className="space-y-4 min-w-0">
            <Panel
              title="Live Agent Terminal"
              subtitle={
                sshLive
                  ? `${cmds.length} commands · ssh live`
                  : `${cmds.length} commands · local feed`
              }
            >
              <TerminalEmulator
                commands={cmds}
                connectionStatus={sys?.connection_status}
              />
            </Panel>

            <HypothesisTabs ticketId={ticketId} commands={cmds} validationPassed={validationPass.passed} />

            {validationPass.passed && <ValidationPassBanner commands={cmds} ticket={ticket} />}

            {lastFailed && !pending && !validationPass.passed && (
              <FailedCommandRetry command={lastFailed} ticketId={ticketId} />
            )}

            <Panel
              title={pending ? "⚡ Agent Command Gate" : validationPass.passed ? "✓ Validation Complete" : "Command Gate"}
              subtitle={
                pending
                  ? "human authorization required"
                  : validationPass.passed
                    ? "public-test.sh passed — commit activity to ERP"
                    : "no pending proposals — gate idle"
              }
              accent={pending ? "warn" : validationPass.passed ? "safe" : undefined}
            >
              {pipelineSettling || cmdsFetching ? (
                <div className="rounded-lg border border-dashed border-border bg-background/30 p-8 text-center">
                  <p className="text-sm text-muted-foreground">Syncing command gate with selected pathway…</p>
                </div>
              ) : pending && !validationPass.passed ? (
                <SafetyGate command={pending} />
              ) : validationPass.passed ? (
                <div className="rounded-lg border border-safe/40 bg-safe/10 p-6 text-center">
                  <p className="text-sm font-medium text-safe">public-test.sh PASS (exit 0)</p>
                  <p className="text-sm text-muted-foreground mt-2">
                    {validationPass.detail ?? "Fix validated successfully."} Edit the activity draft on the right and commit to Phoenix ERP.
                  </p>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-border bg-background/30 p-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    No AI command is awaiting authorization.
                  </p>
                  <p className="text-[11px] font-mono text-muted-foreground/70 mt-1">
                    Click <span className="text-primary">Start Analysis</span> to begin the agent pipeline.
                  </p>
                </div>
              )}
            </Panel>
          </section>

          {/* Zone C */}
          <aside className="space-y-4">
            <AuditTrail ticketId={ticketId} />
            <Panel title="Phoenix ERP — Activity Draft" subtitle="editable preview · Gemini">
              <ActivityDraft ticketId={ticketId} activity={activity ?? null} executedCount={executedCount} />
            </Panel>
          </aside>
        </div>
      </main>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
  accent,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  accent?: "warn" | "danger" | "safe";
}) {
  return (
    <section
      className={cn(
        "glass rounded-xl p-4",
        accent === "warn" && "ring-1 ring-warn/50",
        accent === "danger" && "ring-1 ring-danger/50",
        accent === "safe" && "ring-1 ring-safe/50",
      )}
    >
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-xs font-semibold uppercase tracking-[0.22em] font-mono text-foreground/90">
          {title}
        </h2>
        {subtitle && (
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
            {subtitle}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between font-mono text-[12.5px]">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-foreground">{v}</span>
    </div>
  );
}
