import React, { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Plus, CalendarBlank, MapPin, Clock } from "@phosphor-icons/react";
import { toast } from "sonner";

function isoDay(d) { return d.toISOString().slice(0, 10); }

export default function CalendarPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(() => {
    const d = new Date(); const day = d.getDay() || 7; d.setDate(d.getDate() - (day - 1)); d.setHours(0, 0, 0, 0); return d;
  });
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => { const d = new Date(weekStart); d.setDate(d.getDate() + i); return d; }), [weekStart]);
  const from = weekStart.toISOString();
  const to = new Date(weekStart.getTime() + 7 * 86400000).toISOString();

  const { data } = useQuery({
    queryKey: ["appointments", from, to],
    queryFn: async () => (await api.get("/appointments", { params: { from_date: from, to_date: to } })).data,
  });
  const [open, setOpen] = useState(false);
  const createMut = useMutation({ mutationFn: async (p) => (await api.post("/appointments", p)).data, onSuccess: () => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["appointments"] }); setOpen(false); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });

  const byDay = useMemo(() => {
    const map = {};
    for (const a of (data?.items || [])) {
      const k = isoDay(new Date(a.start_at));
      (map[k] = map[k] || []).push(a);
    }
    return map;
  }, [data]);

  return (
    <div className="space-y-8" data-testid="calendar-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("crm.appointments.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("crm.appointments.title")}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" className="rounded-sm" onClick={() => { const d = new Date(weekStart); d.setDate(d.getDate() - 7); setWeekStart(d); }} data-testid="cal-prev">←</Button>
          <div className="text-sm font-mono-plex px-3">{weekStart.toLocaleDateString("it-IT", { day: "2-digit", month: "short" })} — {days[6].toLocaleDateString("it-IT", { day: "2-digit", month: "short" })}</div>
          <Button variant="outline" className="rounded-sm" onClick={() => { const d = new Date(weekStart); d.setDate(d.getDate() + 7); setWeekStart(d); }} data-testid="cal-next">→</Button>
          {has("crm.appointments.manage") && (
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild><Button className="rounded-sm gap-2 ml-2" data-testid="new-appointment-button"><Plus size={14} weight="bold" />{t("crm.appointments.new")}</Button></DialogTrigger>
              <NewAppointmentDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
            </Dialog>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-7 gap-2">
        {days.map((d, i) => {
          const list = byDay[isoDay(d)] || [];
          const isToday = isoDay(d) === isoDay(new Date());
          return (
            <Card key={i} className={`rounded-sm border-border p-3 min-h-[220px] ${isToday ? "border-[hsl(var(--brand-red))]" : ""}`} data-testid={`cal-day-${isoDay(d)}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-mono-plex uppercase text-muted-foreground">{d.toLocaleDateString("it-IT", { weekday: "short" })}</div>
                <div className={`text-lg font-display font-bold ${isToday ? "text-[hsl(var(--brand-red))]" : ""}`}>{d.getDate()}</div>
              </div>
              <div className="space-y-2">
                {list.map((a) => (
                  <div key={a.id} className="p-2 text-xs border-l-2 bg-secondary/50" style={{ borderColor: a.color }} data-testid={`appt-${a.id}`}>
                    <div className="font-medium truncate">{a.title}</div>
                    <div className="text-[10px] text-muted-foreground font-mono-plex mt-0.5 flex items-center gap-1"><Clock size={10} />{new Date(a.start_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</div>
                    {a.location && <div className="text-[10px] text-muted-foreground truncate flex items-center gap-1 mt-0.5"><MapPin size={10} />{a.location}</div>}
                  </div>
                ))}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function NewAppointmentDialog({ onSubmit, loading }) {
  const [f, setF] = useState({ title: "", description: "", start_at: "", end_at: "", location: "", appointment_type: "meeting" });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="new-appointment-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo appuntamento</DialogTitle>
        <DialogDescription>Fissa un evento sul calendario.</DialogDescription>
      </DialogHeader>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit({ ...f, start_at: new Date(f.start_at).toISOString(), end_at: new Date(f.end_at).toISOString() }); }} className="space-y-3">
        <div><Label className="overline">Titolo</Label><Input required value={f.title} onChange={(e) => upd("title", e.target.value)} className="rounded-sm h-10" data-testid="na-title" /></div>
        <div><Label className="overline">Descrizione</Label><Textarea value={f.description} onChange={(e) => upd("description", e.target.value)} rows={2} className="rounded-sm" data-testid="na-desc" /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Inizio</Label><Input required type="datetime-local" value={f.start_at} onChange={(e) => upd("start_at", e.target.value)} className="rounded-sm h-10" data-testid="na-start" /></div>
          <div><Label className="overline">Fine</Label><Input required type="datetime-local" value={f.end_at} onChange={(e) => upd("end_at", e.target.value)} className="rounded-sm h-10" data-testid="na-end" /></div>
        </div>
        <div><Label className="overline">Luogo</Label><Input value={f.location} onChange={(e) => upd("location", e.target.value)} className="rounded-sm h-10" data-testid="na-location" /></div>
        <div><Label className="overline">Tipo</Label>
          <Select value={f.appointment_type} onValueChange={(v) => upd("appointment_type", v)}>
            <SelectTrigger className="rounded-sm h-10" data-testid="na-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="meeting">Riunione</SelectItem>
              <SelectItem value="call">Chiamata</SelectItem>
              <SelectItem value="survey">Rilievo</SelectItem>
              <SelectItem value="install">Posa</SelectItem>
              <SelectItem value="other">Altro</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="na-submit">{loading ? "…" : "Crea appuntamento"}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
