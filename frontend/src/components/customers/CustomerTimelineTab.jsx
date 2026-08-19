import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDistanceToNow } from "date-fns";
import { it as itLocale } from "date-fns/locale";
import { toast } from "sonner";

const CATEGORIES = [
  { v: "CALL", l: "Chiamata", color: "#10B981" },
  { v: "FOLLOW_UP", l: "Follow-up", color: "#F59E0B" },
  { v: "COMMERCIAL_NOTE", l: "Nota commerciale", color: "#3B82F6" },
  { v: "TECHNICAL_NOTE", l: "Nota tecnica", color: "#8B5CF6" },
  { v: "ADMIN_NOTE", l: "Nota amministrativa", color: "#71717A" },
  { v: "INSTALLATION_NOTE", l: "Nota posa", color: "#D9381E" },
  { v: "SUPPORT_NOTE", l: "Nota assistenza", color: "#06B6D4" },
];
const CATEGORY_COLOR = Object.fromEntries(CATEGORIES.map((c) => [c.v, c.color]));
CATEGORY_COLOR.SYSTEM_EVENT = "#71717A";
const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.v, c.l]));
CATEGORY_LABEL.SYSTEM_EVENT = "Sistema";

const CHANNELS = [
  { v: "", l: "—" },
  { v: "PHONE", l: "Telefono" },
  { v: "EMAIL", l: "Email" },
  { v: "WHATSAPP", l: "WhatsApp" },
  { v: "IN_PERSON", l: "In persona" },
  { v: "OTHER", l: "Altro" },
];

/**
 * CustomerTimelineTab — cronologia strutturata degli eventi cliente.
 * (Milestone 1 Part 2 — Enerhia Operating Core)
 */
export default function CustomerTimelineTab({ customerId, sites = [] }) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const [showForm, setShowForm] = useState(true);

  const { data } = useQuery({
    queryKey: ["customer-timeline", customerId, filter],
    queryFn: async () => (await api.get(`/customers/${customerId}/timeline`,
      { params: { limit: 200, category: filter || undefined } })).data,
  });

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post(`/customers/${customerId}/timeline`, payload)).data,
    onSuccess: () => {
      toast.success("Evento registrato");
      qc.invalidateQueries({ queryKey: ["customer-timeline", customerId] });
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="timeline-tab">
      <Card className="rounded-sm border-border p-5 lg:col-span-1 h-fit">
        <div className="overline mb-3">Nuovo evento</div>
        <NewEventForm sites={sites} onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
      </Card>

      <Card className="rounded-sm border-border p-5 lg:col-span-2">
        <div className="flex items-center justify-between mb-4 gap-2">
          <div className="overline">Cronologia · {data?.total || 0} eventi</div>
          <Select value={filter || "__all__"} onValueChange={(v) => setFilter(v === "__all__" ? "" : v)}>
            <SelectTrigger className="rounded-sm h-9 w-52" data-testid="timeline-filter"><SelectValue placeholder="Tutte le categorie" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Tutte le categorie</SelectItem>
              {CATEGORIES.map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}
              <SelectItem value="SYSTEM_EVENT">Sistema</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <TimelineList items={data?.items || []} />
      </Card>
    </div>
  );
}

function NewEventForm({ sites, onSubmit, loading }) {
  const [f, setF] = useState({ category: "COMMERCIAL_NOTE", channel: "", title: "", body: "", site_id: "" });
  const upd = (k, v) => setF((x) => ({ ...x, [k]: v }));
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!f.body.trim()) return;
        const payload = { ...f };
        if (!payload.channel) delete payload.channel;
        if (!payload.site_id || payload.site_id === "__none__") delete payload.site_id;
        if (!payload.title) delete payload.title;
        onSubmit(payload);
        setF({ ...f, title: "", body: "" });
      }}
      className="space-y-3"
    >
      <div>
        <Label className="overline">Categoria</Label>
        <Select value={f.category} onValueChange={(v) => upd("category", v)}>
          <SelectTrigger className="rounded-sm h-10" data-testid="ev-category"><SelectValue /></SelectTrigger>
          <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div>
        <Label className="overline">Canale</Label>
        <Select value={f.channel || "__none__"} onValueChange={(v) => upd("channel", v === "__none__" ? "" : v)}>
          <SelectTrigger className="rounded-sm h-10" data-testid="ev-channel"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">—</SelectItem>
            {CHANNELS.filter((c) => c.v).map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {sites.length > 0 && (
        <div>
          <Label className="overline">Cantiere (opzionale)</Label>
          <Select value={f.site_id || "__none__"} onValueChange={(v) => upd("site_id", v === "__none__" ? "" : v)}>
            <SelectTrigger className="rounded-sm h-10" data-testid="ev-site"><SelectValue placeholder="—" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">— Nessuno</SelectItem>
              {sites.map((s) => <SelectItem key={s.id} value={s.id}>{s.site_number} · {s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}
      <div>
        <Label className="overline">Titolo (opzionale)</Label>
        <Input value={f.title} onChange={(e) => upd("title", e.target.value)} className="rounded-sm h-10" data-testid="ev-title" />
      </div>
      <div>
        <Label className="overline">Descrizione *</Label>
        <Textarea required rows={4} value={f.body} onChange={(e) => upd("body", e.target.value)} className="rounded-sm" placeholder="Es. Cliente interessato al colore noce, richiamare venerdì." data-testid="ev-body" />
      </div>
      <Button type="submit" disabled={loading || !f.body.trim()} className="w-full rounded-sm" data-testid="ev-submit">
        {loading ? "…" : "Registra evento"}
      </Button>
    </form>
  );
}

function TimelineList({ items }) {
  if (!items.length) return <div className="text-sm text-muted-foreground p-6 text-center">Nessun evento registrato</div>;
  return (
    <div className="relative pl-6 border-l-2 border-border" data-testid="timeline-list">
      {items.map((e) => {
        const color = CATEGORY_COLOR[e.category] || "#71717A";
        const isSystem = e.event_source === "SYSTEM";
        return (
          <div key={e.id} className="relative mb-6" data-testid={`timeline-event-${e.id}`}>
            <span className="absolute -left-[27px] top-0 h-4 w-4 rounded-full border-2 border-background" style={{ background: color }} />
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="rounded-sm text-[10px] font-mono-plex uppercase">
                  {CATEGORY_LABEL[e.category] || e.category}
                </Badge>
                {e.channel && <Badge variant="outline" className="rounded-sm text-[10px]">{e.channel}</Badge>}
                {isSystem && <Badge className="rounded-sm text-[10px] bg-zinc-100 text-zinc-500">SYSTEM</Badge>}
              </div>
              <div className="text-[10px] font-mono-plex text-muted-foreground whitespace-nowrap">
                {formatDistanceToNow(new Date(e.created_at), { addSuffix: true, locale: itLocale })}
              </div>
            </div>
            {e.title && <div className="mt-1 text-sm font-medium">{e.title}</div>}
            <div className="text-sm mt-0.5 whitespace-pre-wrap">{e.body}</div>
            <div className="mt-1 text-[10px] text-muted-foreground">
              {e.created_by_name || "—"}
              {e.created_by_role && ` · ${e.created_by_role}`}
              {e.site_id && ` · cantiere collegato`}
            </div>
          </div>
        );
      })}
    </div>
  );
}
