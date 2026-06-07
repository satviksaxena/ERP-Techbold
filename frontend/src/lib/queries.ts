import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { api } from "./api-client";
import type { Activity, AiCommand, SystemInfo, Ticket } from "./types";

type RealtimeChannel = ReturnType<typeof supabase.channel>;

const realtimeRefCounts = new Map<string, number>();
const realtimeChannels = new Map<string, RealtimeChannel>();

function subscribePostgresChanges(
  channelName: string,
  table: string,
  onChange: () => void,
  filter?: string,
): () => void {
  const nextCount = (realtimeRefCounts.get(channelName) ?? 0) + 1;
  realtimeRefCounts.set(channelName, nextCount);

  if (nextCount === 1) {
    const ch = supabase
      .channel(channelName)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table,
          ...(filter ? { filter } : {}),
        },
        onChange,
      )
      .subscribe();
    realtimeChannels.set(channelName, ch);
  }

  return () => {
    const remaining = (realtimeRefCounts.get(channelName) ?? 1) - 1;
    if (remaining <= 0) {
      realtimeRefCounts.delete(channelName);
      const ch = realtimeChannels.get(channelName);
      if (ch) {
        supabase.removeChannel(ch);
        realtimeChannels.delete(channelName);
      }
    } else {
      realtimeRefCounts.set(channelName, remaining);
    }
  };
}

export function isPhoenixTicket(ticket: Ticket): boolean {
  return /^\d+$/.test(ticket.ticket_code);
}

export function useTickets() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["tickets"],
    queryFn: async (): Promise<Ticket[]> => {
      const { data, error } = await supabase
        .from("tickets")
        .select("*")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return (data ?? []).filter(isPhoenixTicket);
    },
  });

  useEffect(() => {
    return subscribePostgresChanges("tickets-rt", "tickets", () => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
    });
  }, [qc]);

  return q;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isTicketUuid(ref: string): boolean {
  return UUID_RE.test(ref);
}

export function useTicket(ref: string | undefined) {
  return useQuery({
    enabled: !!ref,
    queryKey: ["ticket", ref],
    queryFn: async (): Promise<Ticket | null> => {
      if (!ref) return null;
      // Phoenix codes like "7001" are not UUIDs — query by ticket_code first.
      if (/^\d+$/.test(ref)) {
        const byCode = await supabase.from("tickets").select("*").eq("ticket_code", ref).maybeSingle();
        if (byCode.error) throw byCode.error;
        return byCode.data;
      }
      if (isTicketUuid(ref)) {
        const byId = await supabase.from("tickets").select("*").eq("id", ref).maybeSingle();
        if (byId.error) throw byId.error;
        return byId.data;
      }
      return null;
    },
  });
}

export function useSystemInfo(ticketId: string | undefined) {
  const qc = useQueryClient();
  const q = useQuery({
    enabled: !!ticketId,
    queryKey: ["system_info", ticketId],
    queryFn: async (): Promise<SystemInfo | null> => {
      if (!ticketId) return null;
      const { data, error } = await supabase
        .from("system_info")
        .select("*")
        .eq("ticket_id", ticketId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });

  useEffect(() => {
    if (!ticketId) return;
    return subscribePostgresChanges(
      `sysinfo-${ticketId}`,
      "system_info",
      () => qc.invalidateQueries({ queryKey: ["system_info", ticketId] }),
      `ticket_id=eq.${ticketId}`,
    );
  }, [qc, ticketId]);

  return q;
}

export function useCommands(ticketId: string | undefined) {
  const qc = useQueryClient();
  const q = useQuery({
    enabled: !!ticketId,
    queryKey: ["commands", ticketId],
    queryFn: async (): Promise<AiCommand[]> => {
      if (!ticketId) return [];
      const { data, error } = await supabase
        .from("ai_commands")
        .select("*")
        .eq("ticket_id", ticketId)
        .order("created_at", { ascending: true });
      if (error) throw error;
      return data ?? [];
    },
  });

  useEffect(() => {
    if (!ticketId) return;
    return subscribePostgresChanges(
      `cmds-${ticketId}`,
      "ai_commands",
      () => qc.invalidateQueries({ queryKey: ["commands", ticketId] }),
      `ticket_id=eq.${ticketId}`,
    );
  }, [qc, ticketId]);

  return q;
}

export function useActivity(ticketId: string | undefined) {
  const qc = useQueryClient();
  const q = useQuery({
    enabled: !!ticketId,
    queryKey: ["activity", ticketId],
    queryFn: async (): Promise<Activity | null> => {
      if (!ticketId) return null;
      const { data, error } = await supabase
        .from("activities")
        .select("*")
        .eq("ticket_id", ticketId)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });

  useEffect(() => {
    if (!ticketId) return;
    return subscribePostgresChanges(
      `activity-${ticketId}`,
      "activities",
      () => qc.invalidateQueries({ queryKey: ["activity", ticketId] }),
      `ticket_id=eq.${ticketId}`,
    );
  }, [qc, ticketId]);

  return q;
}

export function useSshPing(ticketId: string | undefined, enabled: boolean = true) {
  return useQuery({
    enabled: !!ticketId && enabled,
    queryKey: ["ssh_ping", ticketId],
    queryFn: async () => {
      if (!ticketId) return null;
      return api.pingSsh(ticketId);
    },
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
  });
}

