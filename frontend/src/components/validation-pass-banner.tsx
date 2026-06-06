import { CheckCircle2 } from "lucide-react";
import type { AiCommand } from "@/lib/types";
import { publicTestPassed } from "@/components/audit-trail";

export function ValidationPassBanner({ commands }: { commands: AiCommand[] }) {
  const result = publicTestPassed(commands);
  if (!result.passed) return null;

  return (
    <div className="rounded-xl border border-safe/50 bg-safe/10 p-4 ring-1 ring-safe/40 fade-in-up">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="h-5 w-5 text-safe shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-safe">public-test.sh PASS</p>
          <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
            {result.detail ?? "Hackathon validation succeeded (exit 0). Review the activity draft and commit to Phoenix ERP."}
          </p>
        </div>
      </div>
    </div>
  );
}
