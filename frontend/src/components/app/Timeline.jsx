import React from "react";
import { formatDistanceToNow, format } from "date-fns";
import { it as itLocale } from "date-fns/locale";
import {
  Phone, EnvelopeSimple, WhatsappLogo, NotePencil, CalendarBlank, CheckCircle,
  UserPlus, ArrowRight, Trophy, XCircle, Sparkle, ListChecks,
} from "@phosphor-icons/react";

const ICON_MAP = {
  lead_created: UserPlus,
  note: NotePencil,
  call: Phone,
  email: EnvelopeSimple,
  whatsapp: WhatsappLogo,
  appointment_scheduled: CalendarBlank,
  appointment_done: CheckCircle,
  task_created: ListChecks,
  task_done: CheckCircle,
  stage_changed: ArrowRight,
  conversion: Trophy,
  quote_created: Sparkle,
  quote_sent: Sparkle,
  order_created: Sparkle,
  survey_scheduled: CalendarBlank,
  survey_done: CheckCircle,
  install_scheduled: CalendarBlank,
  install_done: CheckCircle,
  service_requested: XCircle,
};

const COLOR_MAP = {
  lead_created: "#3B82F6",
  note: "#71717A",
  call: "#10B981",
  email: "#8B5CF6",
  whatsapp: "#22C55E",
  appointment_scheduled: "#F59E0B",
  appointment_done: "#10B981",
  task_created: "#71717A",
  task_done: "#10B981",
  stage_changed: "#D9381E",
  conversion: "#10B981",
};

function eventColor(type) { return COLOR_MAP[type] || "#71717A"; }

export default function Timeline({ activities = [] }) {
  if (!activities.length) {
    return <div className="text-sm text-muted-foreground p-8 text-center">Nessun evento registrato</div>;
  }
  return (
    <div className="relative pl-6 border-l-2 border-border" data-testid="timeline">
      {activities.map((a, i) => {
        const Icon = ICON_MAP[a.type] || NotePencil;
        const c = eventColor(a.type);
        return (
          <div key={a.id || i} className="relative mb-6" data-testid={`timeline-item-${a.id}`}>
            <span
              className="absolute -left-[34px] top-0 flex h-6 w-6 items-center justify-center rounded-full text-white"
              style={{ background: c }}
            >
              <Icon size={12} weight="bold" />
            </span>
            <div className="flex items-baseline justify-between gap-3">
              <div className="text-sm font-medium">{a.subject}</div>
              <div className="text-[10px] font-mono-plex text-muted-foreground whitespace-nowrap">
                {a.occurred_at ? formatDistanceToNow(new Date(a.occurred_at), { addSuffix: true, locale: itLocale }) : ""}
              </div>
            </div>
            {a.body && <div className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{a.body}</div>}
            <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground font-mono-plex">
              <span className="uppercase tracking-widest">{a.type.replace(/_/g, " ")}</span>
              {a._by_email && <>· <span>{a._by_name || a._by_email}</span></>}
              {a.direction && <>· <span>{a.direction === "in" ? "→ IN" : "OUT →"}</span></>}
              {a.outcome && <>· <span>{a.outcome}</span></>}
              {a.duration_seconds ? <>· <span>{Math.round(a.duration_seconds / 60)}m</span></> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
