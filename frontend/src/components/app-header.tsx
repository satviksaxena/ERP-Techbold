import { Link, useNavigate } from "@tanstack/react-router";
import { Activity, CloudDownload, RotateCcw, Terminal, Server, ShieldCheck, ShieldAlert, Loader2, RefreshCw, AlertTriangle } from "lucide-react";
import { useState, useEffect, useCallback } from "react";
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
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export function AppHeader() {
  const [resetting, setResetting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [backendStatus, setBackendStatus] = useState<"connecting" | "online" | "offline">("connecting");
  const [awsStatus, setAwsStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [awsArn, setAwsArn] = useState<string | null>(null);
  const [awsAccount, setAwsAccount] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const checkConnection = useCallback(async (silent = false) => {
    if (!silent) setChecking(true);
    try {
      const data = await api.health();
      setBackendStatus("online");
      if (data.aws_status === "connected") {
        setAwsStatus("connected");
        setAwsArn(data.aws_arn || null);
        setAwsAccount(data.aws_account || null);
        if (!silent) toast.success("AWS Connection Verified");
      } else {
        setAwsStatus("disconnected");
        setAwsArn(null);
        setAwsAccount(null);
        if (!silent) toast.warning("Backend online, but AWS client is disconnected");
      }
    } catch (err) {
      setBackendStatus("offline");
      setAwsStatus("disconnected");
      setAwsArn(null);
      setAwsAccount(null);
      if (!silent) toast.error("Could not reach backend API server");
    } finally {
      if (!silent) setChecking(false);
    }
  }, []);

  useEffect(() => {
    checkConnection(true);
    // Poll every 15 seconds to keep connection status active
    const interval = setInterval(() => {
      checkConnection(true);
    }, 15000);
    return () => clearInterval(interval);
  }, [checkConnection]);

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
      const result = await api.resetWorkspace();
      await qc.resetQueries();
      void navigate({ to: "/" });
      toast.success(result.message || "Workspace cleared — VMs rebooting in background");
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
          <Popover>
            <PopoverTrigger asChild>
              <button className="hidden sm:flex items-center gap-2 rounded-md glass px-3 py-1.5 text-xs font-mono hover:bg-white/5 active:bg-white/10 transition-colors cursor-pointer text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">
                <span className={`h-2 w-2 rounded-full pulse-dot ${
                  backendStatus === "online" 
                    ? (awsStatus === "connected" ? "bg-safe font-semibold" : "bg-warn")
                    : "bg-danger"
                }`} />
                <span className="text-muted-foreground">aws connection:</span>
                <span className={
                  backendStatus === "online" 
                    ? (awsStatus === "connected" ? "text-safe" : "text-warn")
                    : "text-danger"
                }>
                  {backendStatus === "online" 
                    ? (awsStatus === "connected" ? "secure" : "missing keys")
                    : "offline"}
                </span>
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-80 p-4 font-sans border border-border/80 bg-background/95 backdrop-blur-md z-[100]">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold tracking-tight text-foreground">System Connections</h4>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    onClick={() => checkConnection(false)}
                    disabled={checking}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${checking ? "animate-spin" : ""}`} />
                  </Button>
                </div>
                
                <div className="space-y-3">
                  {/* Backend Server Status */}
                  <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-muted/30 p-2.5">
                    <Server className={`mt-0.5 h-4 w-4 ${backendStatus === "online" ? "text-safe" : "text-danger"}`} />
                    <div className="space-y-0.5 text-left">
                      <div className="text-xs font-medium leading-none text-foreground">Backend API Server</div>
                      <div className="text-[10px] text-muted-foreground font-mono leading-none mt-1">
                        {backendStatus === "connecting" && "Verifying link..."}
                        {backendStatus === "online" && "Connected to port 8000"}
                        {backendStatus === "offline" && "Connection failed / Unreachable"}
                      </div>
                    </div>
                    <span className={`ml-auto text-[10px] uppercase font-semibold font-mono leading-none ${
                      backendStatus === "online" ? "text-safe" : "text-danger"
                    }`}>
                      {backendStatus}
                    </span>
                  </div>

                  {/* AWS Connection Status */}
                  <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-muted/30 p-2.5">
                    {awsStatus === "connected" ? (
                      <ShieldCheck className="mt-0.5 h-4 w-4 text-safe" />
                    ) : awsStatus === "connecting" ? (
                      <Loader2 className="mt-0.5 h-4 w-4 text-warn animate-spin" />
                    ) : (
                      <ShieldAlert className="mt-0.5 h-4 w-4 text-danger" />
                    )}
                    <div className="space-y-0.5 text-left">
                      <div className="text-xs font-medium leading-none text-foreground">AWS Boto3 Client</div>
                      <div className="text-[10px] text-muted-foreground font-mono leading-none mt-1">
                        {awsStatus === "connecting" && "Initializing AWS client..."}
                        {awsStatus === "connected" && "STS identity verified"}
                        {awsStatus === "disconnected" && "STS credentials missing"}
                      </div>
                    </div>
                    <span className={`ml-auto text-[10px] uppercase font-semibold font-mono leading-none ${
                      awsStatus === "connected" ? "text-safe" : (awsStatus === "connecting" ? "text-warn" : "text-danger")
                    }`}>
                      {awsStatus}
                    </span>
                  </div>
                </div>

                {/* AWS Details */}
                {awsStatus === "connected" && (awsArn || awsAccount) && (
                  <div className="rounded-md bg-muted/50 p-2.5 text-[10px] font-mono space-y-1.5 border border-border/20 text-left">
                    <div className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold">AWS Identity Details</div>
                    {awsAccount && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Account:</span>
                        <span className="text-foreground">{awsAccount}</span>
                      </div>
                    )}
                    {awsArn && (
                      <div className="space-y-1">
                        <span className="text-muted-foreground">Identity ARN:</span>
                        <div className="text-foreground break-all bg-background/50 p-1 rounded border border-border/20 text-[9px] select-all leading-normal">
                          {awsArn}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Troubleshooting instructions if offline */}
                {backendStatus === "offline" && (
                  <div className="rounded-md bg-danger/10 border border-danger/20 p-2.5 text-[10px] space-y-1 text-danger text-left leading-normal">
                    <div className="font-semibold flex items-center gap-1">
                      <AlertTriangle className="h-3.5 w-3.5" /> Backend Unreachable
                    </div>
                    <p>Make sure your AWS EC2 instance is running and the backend container is active on port 8000. Verify the API routing settings in <code>vercel.json</code>.</p>
                  </div>
                )}
              </div>
            </PopoverContent>
          </Popover>
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
                  Reboots hackathon VMs, clears ERP activities, reopens all tickets as Open,
                  and deletes local commands, hypotheses, and activity drafts in Supabase.
                  Wait ~2 minutes after reset before SSH.
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
