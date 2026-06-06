import { useCallback, useEffect, useRef, useState } from "react";
import type { AiCommand } from "@/lib/types";
import { cn } from "@/lib/utils";
import { GripHorizontal } from "lucide-react";

type ConnectionStatus = "Connected" | "Failed" | "Idle" | string;

function parseExitCode(output: string): number | null {
  const match = output.match(/exit code:\s*(\d+)/i);
  return match ? Number(match[1]) : null;
}

function hasRealOutput(commands: AiCommand[]): boolean {
  return commands.some(
    (c) =>
      (c.human_status === "Approved" || c.human_status === "Edited") &&
      c.output_logs &&
      !c.output_logs.includes("[mock]"),
  );
}

function terminalStatusLabel(
  connectionStatus: ConnectionStatus | undefined,
  commands: AiCommand[],
): { label: string; className: string } {
  const executed = hasRealOutput(commands);

  if (executed) {
    return { label: "● ssh live", className: "text-safe" };
  }
  if (connectionStatus === "Connected") {
    return { label: "● ssh linked", className: "text-warn" };
  }
  if (connectionStatus === "Failed") {
    return { label: "● ssh failed", className: "text-danger" };
  }
  if (commands.some((c) => c.human_status === "Pending")) {
    return { label: "● awaiting auth", className: "text-warn" };
  }
  return { label: "● idle", className: "text-muted-foreground" };
}

export function TerminalEmulator({
  commands,
  connectionStatus,
}: {
  commands: AiCommand[];
  connectionStatus?: ConnectionStatus;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(340);
  const dragState = useRef<{ startY: number; startH: number } | null>(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [commands, height]);

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragState.current = { startY: e.clientY, startH: height };

      function onMove(ev: MouseEvent) {
        if (!dragState.current) return;
        const next = dragState.current.startH + (ev.clientY - dragState.current.startY);
        setHeight(Math.max(180, Math.min(window.innerHeight * 0.75, next)));
      }

      function onUp() {
        dragState.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [height],
  );

  const status = terminalStatusLabel(connectionStatus, commands);
  const executed = hasRealOutput(commands);

  const lines: { ts: string; agent: string; line: string; kind: "cmd" | "out" | "warn" | "ok" | "err" }[] = [];
  for (const c of commands) {
    const ts = new Date(c.created_at).toLocaleTimeString();
    lines.push({ ts, agent: c.agent_name, line: `$ ${c.command_text}`, kind: "cmd" });
    const ran = c.human_status === "Approved" || c.human_status === "Edited";
    if (ran && c.output_logs) {
      c.output_logs.split("\n").forEach((l) => {
        const kind =
          l.includes("execution failed") || l.startsWith("stderr:")
            ? "err"
            : l.includes("[mock]")
              ? "warn"
              : "out";
        lines.push({ ts, agent: c.agent_name, line: l, kind });
      });
      const code = parseExitCode(c.output_logs);
      if (code !== null) {
        lines.push({
          ts,
          agent: c.agent_name,
          line: `[exit ${code}]`,
          kind: code === 0 ? "ok" : "err",
        });
      } else if (!c.output_logs.includes("[mock]")) {
        lines.push({ ts, agent: c.agent_name, line: "[completed]", kind: "ok" });
      }
    } else if (c.human_status === "Rejected") {
      lines.push({ ts, agent: c.agent_name, line: "[command rejected by technician]", kind: "err" });
    } else if (c.human_status === "Pending") {
      lines.push({ ts, agent: c.agent_name, line: "[awaiting human authorization]", kind: "warn" });
    }
  }

  return (
    <div className="rounded-lg border border-border bg-[oklch(0.12_0.02_250)] scanline flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/70 bg-background/40 shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-danger/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-warn/80" />
          <span className="h-2.5 w-2.5 rounded-full bg-safe/80" />
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          agent terminal · {executed ? "/dev/ssh0" : "supabase feed"}
        </span>
        <span className={cn("font-mono text-[10px]", status.className)}>{status.label}</span>
      </div>

      <div ref={bodyRef} className="overflow-y-auto p-4 font-mono text-[12.5px] leading-relaxed space-y-0.5" style={{ height }}>
        {lines.length === 0 && (
          <div className="text-muted-foreground space-y-1">
            <div>
              <span className="caret-blink">▌</span> waiting for agent activity…
            </div>
            {connectionStatus === "Connected" && (
              <div className="text-[11px] text-warn/90">
                SSH handshake OK — click <span className="text-primary">Start Analysis</span>, then authorize a command to see output here.
              </div>
            )}
          </div>
        )}
        {lines.map((l, i) => (
          <div key={i} className="flex gap-3">
            <span className="text-muted-foreground/60 shrink-0">{l.ts}</span>
            <span className="text-primary/70 shrink-0 w-44 truncate">[{l.agent}]</span>
            <span
              className={
                l.kind === "cmd"
                  ? "text-foreground"
                  : l.kind === "out"
                    ? "text-muted-foreground"
                    : l.kind === "warn"
                      ? "text-warn"
                      : l.kind === "ok"
                        ? "text-safe"
                        : "text-danger"
              }
            >
              {l.line || " "}
            </span>
          </div>
        ))}
        {lines.length > 0 && (
          <div className="flex gap-3">
            <span className="text-muted-foreground/60 shrink-0">         </span>
            <span className="text-primary">
              <span className="caret-blink">▌</span>
            </span>
          </div>
        )}
      </div>

      <button
        type="button"
        aria-label="Resize terminal"
        onMouseDown={onResizeStart}
        className="flex items-center justify-center py-1 border-t border-border/60 bg-background/30 cursor-row-resize hover:bg-background/50 shrink-0"
      >
        <GripHorizontal className="h-4 w-4 text-muted-foreground/70" />
      </button>
    </div>
  );
};
