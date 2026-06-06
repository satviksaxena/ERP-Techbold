const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export type HypothesisItem = {
  title: string;
  summary: string;
  likely_root_cause: string;
  confidence: string;
  first_command: string;
  fix_strategy: string;
  safety_status?: string;
};

export type HypothesisState = {
  hypotheses: HypothesisItem[];
  selected_index: number;
};

type RequestOptions = RequestInit & { timeoutMs?: number };

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { timeoutMs = 30_000, ...fetchInit } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchInit,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(fetchInit.headers ?? {}),
      },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ?? body.message ?? detail;
      } catch {
        /* ignore */
      }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(
        "Request timed out — the backend may have restarted. Refresh the page or restart with ./scripts/dev-backend.sh",
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  syncTickets: () =>
    request<{ ok: boolean; count: number }>("/api/sync/tickets", { method: "POST" }),

  startAnalysis: (ticketId: string) =>
    request<{ ok: boolean; command: unknown; hypotheses?: HypothesisState }>(
      `/api/tickets/${ticketId}/analyze`,
      { method: "POST" },
    ),

  getHypotheses: (ticketId: string) =>
    request<HypothesisState>(`/api/tickets/${ticketId}/hypotheses`),

  generateHypotheses: (ticketId: string) =>
    request<HypothesisState & { ok: boolean }>(
      `/api/tickets/${ticketId}/hypotheses/generate`,
      { method: "POST" },
    ),

  selectHypothesis: (ticketId: string, index: number) =>
    request<HypothesisState & { ok: boolean; command?: unknown }>(
      `/api/tickets/${ticketId}/hypotheses/select`,
      { method: "POST", body: JSON.stringify({ index }) },
    ),

  approveCommand: (commandId: string, commandText?: string) =>
    request<{ ok: boolean; command: unknown }>(`/api/commands/${commandId}/approve`, {
      method: "POST",
      timeoutMs: 120_000,
      body: JSON.stringify({ command_text: commandText ?? null }),
    }),

  rejectCommand: (commandId: string) =>
    request<{ ok: boolean }>(`/api/commands/${commandId}/reject`, { method: "POST" }),

  retryCommand: (commandId: string) =>
    request<{ ok: boolean; command: unknown }>(`/api/commands/${commandId}/retry`, { method: "POST" }),

  getAudit: (ticketId?: string) =>
    request<{ entries: unknown[] }>(
      ticketId ? `/api/audit?ticket_id=${encodeURIComponent(ticketId)}` : "/api/audit",
    ),

  submitActivity: (
    ticketId: string,
    fields?: {
      summary: string;
      root_cause: string;
      actions_taken: string;
      commands_summary: string;
      validation_result: string;
    },
  ) =>
    request<{ ok: boolean }>(`/api/tickets/${ticketId}/submit-activity`, {
      method: "POST",
      body: JSON.stringify(fields ?? {}),
    }),

  connectSsh: (ticketId: string) =>
    request<{ ok: boolean; connection_status: string }>(
      `/api/tickets/${ticketId}/connect-ssh`,
      { method: "POST" },
    ),

  reconcileValidation: (ticketId: string) =>
    request<{ reconciled: boolean; rejected_command_ids?: string[] }>(
      `/api/tickets/${ticketId}/reconcile-validation`,
      { method: "POST", timeoutMs: 60_000 },
    ),

  resumePipeline: (ticketId: string) =>
    request<{ resumed: boolean; action?: string; reason?: string }>(
      `/api/tickets/${ticketId}/resume-pipeline`,
      { method: "POST", timeoutMs: 90_000 },
    ),

  resetWorkspace: () =>
    request<{ ok: string; message: string }>("/api/workspace/reset", { method: "POST" }),
};

export { API_BASE };
