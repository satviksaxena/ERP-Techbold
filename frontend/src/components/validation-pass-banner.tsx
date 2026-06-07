import { CheckCircle2 } from "lucide-react";
import type { AiCommand } from "@/lib/types";
import { incidentResolved, publicTestPassed } from "@/components/audit-trail";

export function ValidationPassBanner({
  commands,
  ticket,
}: {
  commands: AiCommand[];
  ticket?: { status?: string | null; ticket_code?: string | null };
}) {
  const pub = publicTestPassed(commands);
  const resolved = incidentResolved(commands, ticket);
  if (!resolved.passed) return null;

  return (
    <div className="rounded-xl border border-safe/50 bg-safe/10 p-4 ring-1 ring-safe/40 fade-in-up">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="h-5 w-5 text-safe shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-safe">
            {pub.passed ? "public-test.sh PASS" : "Validation complete"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
            {resolved.detail ??
              "Fix verified. Review the activity draft and commit to Phoenix ERP."}
          </p>
        </div>
      </div>
    </div>
  );
}
