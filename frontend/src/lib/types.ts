import type { Tables } from "@/integrations/supabase/types";

export type Ticket = Tables<"tickets">;
export type SystemInfo = Tables<"system_info">;
export type AiCommand = Tables<"ai_commands">;
export type Activity = Tables<"activities">;

export const PRIORITIES = ["Low", "Medium", "High", "Critical"] as const;
export const STATUSES = ["Open", "Analyzing", "Troubleshooting", "Validating", "Fixed"] as const;
export const AGENTS = [
  "Problem Analyzer",
  "Customer System Analyzer",
  "Problem Solver",
  "Activity Log Generator",
] as const;

export type Priority = (typeof PRIORITIES)[number];
export type Status = (typeof STATUSES)[number];
export type Agent = (typeof AGENTS)[number];
