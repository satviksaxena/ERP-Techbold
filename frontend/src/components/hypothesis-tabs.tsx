import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type HypothesisItem } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { CollapsiblePanel } from "@/components/collapsible-panel";
import type { AiCommand } from "@/lib/types";
import { Lightbulb, Loader2, Brain } from "lucide-react";
import { toast } from "sonner";

const confidenceColor: Record<string, string> = {
  high: "text-safe border-safe/40 bg-safe/10",
  medium: "text-warn border-warn/40 bg-warn/10",
  low: "text-muted-foreground border-border/60 bg-background/30",
};

export function HypothesisTabs({
  ticketId,
  commands = [],
  validationPassed = false,
}: {
  ticketId: string | undefined;
  commands?: AiCommand[];
  validationPassed?: boolean;
}) {
  const qc = useQueryClient();
  const [selecting, setSelecting] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const generateAttempted = useRef(false);

  const cmds = commands;

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["hypotheses", ticketId],
    queryFn: () => api.getHypotheses(ticketId!),
    enabled: !!ticketId,
  });

  useEffect(() => {
    generateAttempted.current = false;
    setExpandedIndex(null);
  }, [ticketId]);

  useEffect(() => {
    if (!ticketId) return;
    if (isLoading || isFetching) return;
    if (data?.hypotheses?.length) return;
    if (generateAttempted.current) return;
    generateAttempted.current = true;
    api
      .generateHypotheses(ticketId)
      .then((result) => {
        qc.setQueryData(["hypotheses", ticketId], {
          hypotheses: result.hypotheses ?? [],
          selected_index: result.selected_index ?? 0,
          reasoning_summary: result.reasoning_summary ?? "",
        });
      })
      .catch(() => {
        generateAttempted.current = false;
      });
  }, [ticketId, data, isLoading, isFetching, qc]);

  const hypotheses = data?.hypotheses ?? [];
  const selectedIndex = data?.selected_index ?? 0;
  const reasoningSummary = data?.reasoning_summary ?? "";
  const pipelineState = data?.pipeline_state;
  const verifier = pipelineState?.verifier;

  useEffect(() => {
    if (hypotheses.length > 0 && expandedIndex === null) {
      setExpandedIndex(selectedIndex);
    }
  }, [hypotheses.length, selectedIndex, expandedIndex]);

  const activeIndex = expandedIndex ?? selectedIndex;
  const active = hypotheses[activeIndex];
  const pendingCmd = cmds.find((c) => c.human_status === "Pending");
  const pathFirst = active?.first_command?.trim() ?? "";
  const gateDiffersFromFirst =
    !!pendingCmd &&
    !!pathFirst &&
    pendingCmd.command_text.trim() !== pathFirst &&
    activeIndex === selectedIndex;

  async function selectPath(index: number) {
    if (!ticketId || selecting) return;
    setExpandedIndex(index);
    setSelecting(true);
    try {
      await api.selectHypothesis(ticketId, index);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["hypotheses", ticketId] }),
        qc.invalidateQueries({ queryKey: ["commands", ticketId] }),
        qc.invalidateQueries({ queryKey: ["ticket"] }),
      ]);
      toast.success(
        index === selectedIndex
          ? `Command gate synced to path ${index + 1}`
          : `Path ${index + 1} selected — command gate updated`,
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not select approach");
    } finally {
      setSelecting(false);
    }
  }

  if (!ticketId) {
    return (
      <CollapsiblePanel title="AI Solution Paths" subtitle="this way or that way" summary="Loading ticket…">
        <p className="text-xs text-muted-foreground">Loading ticket…</p>
      </CollapsiblePanel>
    );
  }

  const summary = pathSummary(hypotheses, selectedIndex, isLoading, isFetching, validationPassed);

  if (isLoading || (!hypotheses.length && isFetching)) {
    return (
      <CollapsiblePanel title="AI Solution Paths" subtitle="this way or that way" summary={summary}>
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-4 justify-center">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Generating solution pathways with thinking model…
        </div>
      </CollapsiblePanel>
    );
  }

  if (!hypotheses.length) {
    return (
      <CollapsiblePanel title="AI Solution Paths" subtitle="this way or that way" summary={summary}>
        <div className="rounded-lg border border-dashed border-border/70 bg-background/20 p-6 text-center">
          <p className="text-sm text-muted-foreground">
            No pathways yet — click <span className="text-primary">Start Analysis</span> to generate approaches.
          </p>
        </div>
      </CollapsiblePanel>
    );
  }

  return (
    <CollapsiblePanel title="AI Solution Paths" subtitle="this way or that way" summary={summary}>
      <div className="space-y-3 min-w-0">
      {reasoningSummary && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-2 min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-primary">
            <Brain className="h-3.5 w-3.5 shrink-0" />
            Ticket analysis · thinking model
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap break-words">
            {reasoningSummary}
          </p>
        </div>
      )}
      {verifier?.summary && (
        <div className="rounded-lg border border-border/60 bg-background/25 p-3 text-[11px] text-muted-foreground">
          <span className="font-mono uppercase tracking-wider text-primary">Verifier · {verifier.recommend}</span>
          <p className="mt-1 leading-relaxed">{verifier.summary}</p>
          {pipelineState?.phase && (
            <p className="mt-1 font-mono text-[10px] text-muted-foreground/80">Phase: {pipelineState.phase}</p>
          )}
        </div>
      )}
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
        <Lightbulb className="h-3.5 w-3.5 text-primary shrink-0" />
        Pick a pathway — click a card to view details
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 min-w-0">
        {hypotheses.map((h: HypothesisItem, i: number) => {
          const isActive = i === activeIndex;
          const isSelected = i === selectedIndex;
          const isEliminated = Boolean(h.eliminated);
          return (
            <button
              key={i}
              type="button"
              disabled={selecting || isEliminated}
              onClick={() => selectPath(i)}
              className={cn(
                "text-left rounded-lg border p-3 transition-all min-w-0",
                "bg-background/30 hover:bg-background/50",
                isEliminated && "opacity-50 border-border/40",
                isActive
                  ? "border-primary/60 ring-1 ring-primary/40 shadow-[0_0_20px_-8px] shadow-primary/30"
                  : "border-border/60 hover:border-primary/30",
              )}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-[11px] font-mono text-primary/80">path {i + 1}</span>
                {isSelected && (
                  <span className="text-[9px] font-mono uppercase tracking-wider text-primary shrink-0">
                    active
                  </span>
                )}
              </div>
              <h3 className="text-sm font-medium leading-snug break-words">{h.title}</h3>
              {isEliminated && (
                <p className="mt-1 text-[10px] text-danger font-mono">
                  disproven · {(h as HypothesisItem).elimination_reason || "evidence mismatch"}
                </p>
              )}
              <p className="mt-2 text-[11px] text-muted-foreground line-clamp-2 leading-relaxed break-words">
                {h.summary}
              </p>
              <span
                className={cn(
                  "inline-block mt-3 text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border",
                  confidenceColor[h.confidence] ?? confidenceColor.low,
                )}
              >
                {h.confidence} confidence
              </span>
            </button>
          );
        })}
      </div>

      {active && (
        <div className="rounded-lg border border-border/60 bg-background/25 p-4 space-y-3 min-w-0 overflow-hidden">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 min-w-0">
            <h4 className="text-sm font-semibold break-words">{active.title}</h4>
            <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              pathway detail
            </span>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed break-words">{active.summary}</p>
          <div className="grid gap-3 sm:grid-cols-2 min-w-0">
            <DetailBlock label="root cause" value={active.likely_root_cause} />
            <DetailBlock label="fix strategy" value={active.fix_strategy} />
          </div>
          <div className="min-w-0">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              first command
            </span>
            <pre className="mt-1.5 rounded-md border border-border/50 bg-[oklch(0.12_0.02_250)] p-3 text-[11px] font-mono text-primary whitespace-pre-wrap break-all overflow-x-auto max-w-full">
              {active.first_command}
            </pre>
          </div>
          {gateDiffersFromFirst && pendingCmd && (
            <div className="min-w-0 rounded-md border border-warn/40 bg-warn/10 p-3">
              <span className="text-[10px] font-mono uppercase tracking-wider text-warn">
                {pendingCmd.command_text.toLowerCase().includes("public-test")
                  ? "validation step · command gate"
                  : "next step · command gate"}
              </span>
              <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                {pendingCmd.command_text.toLowerCase().includes("public-test")
                  ? "Diagnostics/fixes may still be in progress on this path — public-test.sh is the hackathon validation check, run after applying the fix (e.g. chmod/chown)."
                  : "The first command for this path may already be done. Authorize the next step below — it continues this pathway."}
              </p>
              <pre className="mt-2 rounded-md border border-border/50 bg-[oklch(0.12_0.02_250)] p-3 text-[11px] font-mono text-warn whitespace-pre-wrap break-all overflow-x-auto max-w-full">
                {pendingCmd.command_text}
              </pre>
            </div>
          )}
        </div>
      )}
      </div>
    </CollapsiblePanel>
  );
}

function pathSummary(
  hypotheses: HypothesisItem[],
  selectedIndex: number,
  isLoading: boolean,
  isFetching: boolean,
  validationPassed: boolean,
): string {
  if (validationPassed) {
    return "Validation passed · public-test.sh exit 0";
  }
  if (isLoading || (!hypotheses.length && isFetching)) {
    return "Generating solution pathways with thinking model…";
  }
  if (!hypotheses.length) {
    return "No pathways yet — start analysis to generate approaches";
  }
  const active = hypotheses[selectedIndex];
  if (!active) {
    return `${hypotheses.length} pathways available`;
  }
  return `Path ${selectedIndex + 1} active · ${active.title}`;
}

function DetailBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/40 bg-background/20 p-3 min-w-0">
      <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{label}</span>
      <p className="mt-1.5 text-[12px] leading-relaxed text-foreground break-words">{value}</p>
    </div>
  );
}
