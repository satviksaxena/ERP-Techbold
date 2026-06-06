import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export function CollapsiblePanel({
  title,
  subtitle,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  subtitle?: string;
  summary?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="glass rounded-xl overflow-hidden min-w-0">
      <Accordion type="single" collapsible defaultValue={defaultOpen ? "content" : undefined}>
        <AccordionItem value="content" className="border-0">
          <AccordionTrigger className="px-4 py-3 hover:no-underline [&[data-state=open]]:border-b [&[data-state=open]]:border-border/40 [&[data-state=open]_.panel-summary]:hidden">
            <div className="flex flex-1 flex-col items-start gap-1.5 min-w-0 pr-2 text-left">
              <div className="flex items-baseline justify-between w-full gap-2 min-w-0">
                <h2 className="text-xs font-semibold uppercase tracking-[0.22em] font-mono text-foreground/90 shrink-0">
                  {title}
                </h2>
                {subtitle && (
                  <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground shrink-0">
                    {subtitle}
                  </span>
                )}
              </div>
              {summary && (
                <p className="panel-summary text-[12px] leading-snug text-muted-foreground line-clamp-2 font-normal normal-case tracking-normal w-full break-words">
                  {summary}
                </p>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent className="px-4 pb-4">{children}</AccordionContent>
        </AccordionItem>
      </Accordion>
    </section>
  );
}

export function truncateSummary(text: string | null | undefined, max = 140): string {
  const normalized = (text || "—").trim().replace(/\s+/g, " ");
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trimEnd()}…`;
}
