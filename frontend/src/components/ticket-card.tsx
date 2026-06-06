import { Link } from "@tanstack/react-router";
import { ArrowUpRight, User2 } from "lucide-react";
import { PriorityBadge, StatusBadge } from "./badges";
import type { Ticket } from "@/lib/types";
import { formatDistanceToNow } from "date-fns";

export function TicketCard({ ticket }: { ticket: Ticket }) {
  return (
    <Link
      to="/workbench/$ticketId"
      params={{ ticketId: ticket.ticket_code }}
      className="group block fade-in-up"
    >
      <article className="glass rounded-xl p-5 relative overflow-hidden transition-all duration-300 hover:-translate-y-0.5 hover:glow-primary">
        <div className="pointer-events-none absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[11px] text-primary tracking-wider">
                {ticket.ticket_code}
              </span>
              <StatusBadge status={ticket.status} />
            </div>
            <h3 className="text-base font-semibold leading-snug truncate">{ticket.title}</h3>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <User2 className="h-3.5 w-3.5" />
              <span>{ticket.customer_name}</span>
            </div>
          </div>
          <PriorityBadge priority={ticket.priority} />
        </div>

        <p className="mt-3 text-sm text-muted-foreground line-clamp-2">
          {ticket.report_text || "No report text."}
        </p>

        <div className="mt-4 flex items-center justify-between text-[11px] font-mono text-muted-foreground">
          <span>
            opened {formatDistanceToNow(new Date(ticket.created_at), { addSuffix: true })}
          </span>
          <span className="inline-flex items-center gap-1 text-primary opacity-70 group-hover:opacity-100">
            open workbench <ArrowUpRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </article>
    </Link>
  );
}
