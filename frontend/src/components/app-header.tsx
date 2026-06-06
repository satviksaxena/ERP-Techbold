import { Link } from "@tanstack/react-router";
import { Activity, CloudDownload, RotateCcw, Terminal } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export function AppHeader() {
  const [resetting, setResetting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const qc = useQueryClient();

  async function syncFromPhoenix() {
    setSyncing(true);
    try {
      const result = await api.syncTickets();
      toast.success(`Synced ${result.count} ticket(s) from Phoenix ERP`);
      qc.invalidateQueries();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function resetWorkspace() {
    setResetting(true);
    try {
      await api.resetWorkspace();
      toast.success("Workspace reset — VMs rebooted, state cleared");
      qc.invalidateQueries();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Reset failed";
      toast.error(msg);
    } finally {
      setResetting(false);
    }
  }

  return (
    <header className="sticky top-0 z-40 glass border-b border-border/60">
      <div className="mx-auto max-w-[1600px] flex items-center justify-between px-6 py-3">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="relative h-9 w-9 rounded-md glass-2 grid place-items-center glow-primary">
            <Terminal className="h-4 w-4 text-primary" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-wide">
              SERVICE DESK <span className="text-primary">AUTOPILOT</span>
            </div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono">
              cyber-ops / human-in-the-loop
            </div>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2 rounded-md glass px-3 py-1.5 text-xs font-mono">
            <span className="h-2 w-2 rounded-full bg-safe pulse-dot" />
            <span className="text-muted-foreground">core link</span>
            <span className="text-safe">online</span>
          </div>
          <Button variant="ghost" size="sm" onClick={syncFromPhoenix} disabled={syncing}>
            <CloudDownload className="h-4 w-4" /> Sync ERP
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/">
              <Activity className="h-4 w-4" /> Tickets
            </Link>
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" disabled={resetting}>
                <RotateCcw className="h-4 w-4" /> Reset Workspace
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reset workspace to baseline?</AlertDialogTitle>
                <AlertDialogDescription>
                  Reverts all tickets to Open, clears command outputs, and marks proposed commands
                  as Pending. Activity drafts are kept but un-submitted.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={resetWorkspace}>Reset</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
    </header>
  );
}
