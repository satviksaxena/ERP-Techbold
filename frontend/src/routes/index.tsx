import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppHeader } from "@/components/app-header";
import { KpiBar } from "@/components/kpi-bar";
import { TicketCard } from "@/components/ticket-card";
import { useTickets } from "@/lib/queries";
import { api } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, ShieldAlert, CloudDownload } from "lucide-react";
import { PRIORITIES } from "@/lib/types";
import { toast } from "sonner";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Ticket Matrix — Service Desk Autopilot" },
      {
        name: "description",
        content: "Live incident matrix with AI-assisted technician workbench.",
      },
    ],
  }),
  component: DashboardPage,
});

type SortKey = "date" | "priority" | "customer";

const priorityRank: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Low: 3 };

function DashboardPage() {
  const { data: tickets, isLoading, error } = useTickets();
  const qc = useQueryClient();
  const autoSynced = useRef(false);
  const [syncing, setSyncing] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("date");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");

  useEffect(() => {
    if (autoSynced.current) return;
    autoSynced.current = true;
    setSyncing(true);
    api
      .syncTickets()
      .then((result) => {
        qc.invalidateQueries({ queryKey: ["tickets"] });
        toast.success(`Synced ${result.count} case(s) from Phoenix ERP`);
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : "Phoenix sync failed — use Sync ERP");
      })
      .finally(() => setSyncing(false));
  }, [qc]);

  const list = useMemo(() => {
    const src = tickets ?? [];
    const filtered = src.filter((t) => {
      const matchesQ =
        !query ||
        t.title.toLowerCase().includes(query.toLowerCase()) ||
        t.customer_name.toLowerCase().includes(query.toLowerCase()) ||
        t.ticket_code.toLowerCase().includes(query.toLowerCase());
      const matchesP = priorityFilter === "all" || t.priority === priorityFilter;
      return matchesQ && matchesP;
    });
    const sorted = [...filtered].sort((a, b) => {
      if (sort === "priority") return (priorityRank[a.priority] ?? 9) - (priorityRank[b.priority] ?? 9);
      if (sort === "customer") return a.customer_name.localeCompare(b.customer_name);
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return sorted;
  }, [tickets, query, sort, priorityFilter]);

  return (
    <div className="min-h-screen grid-bg">
      <AppHeader />
      <main className="mx-auto max-w-[1600px] px-6 py-8 space-y-8">
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Ticket Matrix</h1>
          <p className="text-sm text-muted-foreground">
            Live Phoenix ERP queue — cases 7001–7005 with VM targets from customer-system API.
          </p>
          {syncing && (
            <p className="text-xs font-mono text-primary flex items-center gap-2">
              <CloudDownload className="h-3.5 w-3.5" /> Syncing tickets + VM info from Phoenix…
            </p>
          )}
        </div>

        <KpiBar tickets={tickets ?? []} />

        <div className="glass rounded-xl p-3 flex flex-col sm:flex-row gap-3 sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by title, customer, or ticket code..."
              className="pl-9 bg-background/40 border-border/60 font-mono text-sm"
            />
          </div>
          <Select value={priorityFilter} onValueChange={setPriorityFilter}>
            <SelectTrigger className="w-[160px] bg-background/40">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All priorities</SelectItem>
              {PRIORITIES.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
            <SelectTrigger className="w-[180px] bg-background/40">
              <SelectValue placeholder="Sort" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="date">Sort: Date (newest)</SelectItem>
              <SelectItem value="priority">Sort: Priority</SelectItem>
              <SelectItem value="customer">Sort: Customer</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {error && (
          <div className="glass rounded-xl p-6 flex items-center gap-3 glow-danger">
            <ShieldAlert className="h-5 w-5 text-danger" />
            <div className="text-sm">
              Failed to load tickets: {error instanceof Error ? error.message : "unknown error"}
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="glass rounded-xl p-5 h-44 animate-pulse" />
            ))}
          </div>
        ) : list.length === 0 ? (
          <div className="glass rounded-xl p-12 text-center text-muted-foreground space-y-2">
            <p>No Phoenix cases loaded yet.</p>
            <p className="text-xs font-mono">Click <span className="text-primary">Sync ERP</span> in the header to pull tickets 7001–7005.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {list.map((t) => (
              <TicketCard key={t.id} ticket={t} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
