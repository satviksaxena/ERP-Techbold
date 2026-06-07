import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import type { Activity } from "@/lib/types";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Rocket, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api-client";

const fields = [
  { key: "summary", label: "Summary", hint: "Short executive summary of the incident & resolution." },
  { key: "root_cause", label: "Root Cause", hint: "Technical cause, not the symptom." },
  { key: "actions_taken", label: "Actions Taken", hint: "Ordered timeline of steps performed." },
  { key: "commands_summary", label: "Commands Summary", hint: "Command classes, secrets stripped." },
  { key: "validation_result", label: "Validation Result", hint: "Concrete proof the customer benefit is restored." },
] as const;

type Field = (typeof fields)[number]["key"];

export function ActivityDraft({
  ticketId,
  activity,
  executedCount = 0,
}: {
  ticketId: string;
  activity: Activity | null;
  executedCount?: number;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<Field, string>>({
    summary: "",
    root_cause: "",
    actions_taken: "",
    commands_summary: "",
    validation_result: "",
  });
  const [saving, setSaving] = useState(false);
  const [committed, setCommitted] = useState(false);
  const [confetti, setConfetti] = useState(false);

  useEffect(() => {
    if (!activity) {
      setDraft({
        summary: "",
        root_cause: "",
        actions_taken: "",
        commands_summary: "",
        validation_result: "",
      });
      setCommitted(false);
      return;
    }
    setDraft({
      summary: activity.summary,
      root_cause: activity.root_cause,
      actions_taken: activity.actions_taken,
      commands_summary: activity.commands_summary,
      validation_result: activity.validation_result,
    });
    setCommitted(activity.submitted_to_erp);
  }, [activity, executedCount, ticketId]);

  async function save(commit = false) {
    setSaving(true);
    try {
      const payload = { ...draft, ticket_id: ticketId, submitted_to_erp: commit };
      const { error } = await supabase
        .from("activities")
        .upsert(payload, { onConflict: "ticket_id" });
      if (error) throw error;
      if (commit) {
        await api.submitActivity(ticketId, draft);
        setCommitted(true);
        setConfetti(true);
        setTimeout(() => setConfetti(false), 2200);
        toast.success("Committed to Phoenix ERP");
      } else {
        toast.success("Draft saved");
      }
      qc.invalidateQueries({ queryKey: ["activity", ticketId] });
      qc.invalidateQueries({ queryKey: ["ticket", ticketId] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 relative">
      {confetti && <ConfettiBurst />}
      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-[0.18em]">
        Auto-refreshes after each authorized command · {executedCount} executed
      </p>
      <Accordion type="multiple" defaultValue={["summary", "root_cause"]} className="space-y-2">
        {fields.map((f) => (
          <AccordionItem
            key={f.key}
            value={f.key}
            className="border border-border rounded-lg bg-background/30 px-3"
          >
            <AccordionTrigger className="hover:no-underline">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{f.label}</span>
                {draft[f.key]?.trim() && (
                  <CheckCircle2 className="h-3.5 w-3.5 text-safe" />
                )}
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground mb-2">
                {f.hint}
              </p>
              <Textarea
                value={draft[f.key]}
                onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                className="font-mono text-[12.5px] bg-background/60 min-h-[88px]"
                placeholder={`Enter ${f.label.toLowerCase()}…`}
              />
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>

      <div className="flex flex-col gap-2 pt-2">
        <Button variant="outline" onClick={() => save(false)} disabled={saving}>
          <Save className="h-4 w-4" /> Save draft
        </Button>
        <Button
          onClick={() => save(true)}
          disabled={saving || committed}
          className="h-12 text-sm font-semibold bg-safe text-safe-foreground hover:bg-safe/90 glow-safe"
        >
          {committed ? (
            <>
              <CheckCircle2 className="h-5 w-5" /> Committed to Phoenix ERP
            </>
          ) : (
            <>
              <Rocket className="h-5 w-5" /> Validate & Commit to Phoenix ERP
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function ConfettiBurst() {
  const pieces = Array.from({ length: 60 });
  const colors = ["var(--color-safe)", "var(--color-primary)", "var(--color-warn)"];
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden z-10">
      {pieces.map((_, i) => {
        const left = Math.random() * 100;
        const delay = Math.random() * 0.3;
        const dur = 1.4 + Math.random() * 0.8;
        const rot = Math.random() * 360;
        const color = colors[i % colors.length];
        return (
          <span
            key={i}
            className="absolute top-0 h-2 w-1.5 rounded-sm"
            style={{
              left: `${left}%`,
              background: color,
              transform: `rotate(${rot}deg)`,
              animation: `fall-${i} ${dur}s ${delay}s ease-out forwards`,
            }}
          />
        );
      })}
      <style>{`
        ${pieces
          .map(
            (_, i) =>
              `@keyframes fall-${i} { from { transform: translateY(-10px) rotate(0); opacity: 1 } to { transform: translateY(${300 + Math.random() * 200}px) rotate(${Math.random() * 720}deg); opacity: 0 } }`,
          )
          .join("\n")}
      `}</style>
    </div>
  );
}
