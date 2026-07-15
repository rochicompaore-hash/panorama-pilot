import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Target, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

export default function GoalsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["goals-mine"], queryFn: async () => (await api.get("/goals", { params: { mine: true } })).data });
  const [open, setOpen] = useState(false);
  const createMut = useMutation({ mutationFn: async (p) => (await api.post("/goals", p)).data, onSuccess: () => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["goals-mine"] }); setOpen(false); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });

  return (
    <div className="space-y-8" data-testid="goals-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("crm.goals.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("crm.goals.title")}</h1>
        </div>
        {has("crm.goals.manage") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="rounded-sm h-11 gap-2" data-testid="new-goal-button"><Plus size={16} weight="bold" />{t("crm.goals.new")}</Button></DialogTrigger>
            <NewGoalDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(data?.items || []).map((g) => {
          const pct = g.target_value > 0 ? Math.min(100, Math.round((g.achieved_value / g.target_value) * 100)) : 0;
          return (
            <Card key={g.id} className="rounded-sm border-border p-6" data-testid={`goal-card-${g.id}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="overline">{g.metric} · {g.period_type}</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {new Date(g.period_start).toLocaleDateString("it-IT")} → {new Date(g.period_end).toLocaleDateString("it-IT")}
                  </div>
                </div>
                <Target size={20} weight="duotone" className="text-[hsl(var(--brand-red))]" />
              </div>
              <div className="mt-6">
                <div className="flex items-baseline justify-between">
                  <span className="font-display text-2xl font-black tracking-tight">{g.metric === "revenue" ? fmtEUR(g.achieved_value) : g.achieved_value}</span>
                  <span className="text-xs text-muted-foreground">/ {g.metric === "revenue" ? fmtEUR(g.target_value) : g.target_value}</span>
                </div>
                <Progress value={pct} className="mt-2 h-2" />
                <div className="mt-1 text-[10px] font-mono-plex text-muted-foreground uppercase">{pct}% raggiunto</div>
              </div>
            </Card>
          );
        })}
        {(data?.items || []).length === 0 && <Card className="rounded-sm border-border p-10 text-center col-span-full text-sm text-muted-foreground">Nessun obiettivo. Creane uno per iniziare a tracciare i tuoi target.</Card>}
      </div>
    </div>
  );
}

function NewGoalDialog({ onSubmit, loading }) {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  const [f, setF] = useState({ metric: "revenue", period_type: "month", period_start: first, period_end: last, target_value: 20000 });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  const { data: users } = useQuery({ queryKey: ["users-for-goal"], queryFn: async () => (await api.get("/users", { params: { limit: 100 } })).data });
  const [userId, setUserId] = useState("");
  return (
    <DialogContent className="rounded-sm" data-testid="new-goal-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo obiettivo</DialogTitle>
        <DialogDescription>Imposta un target commerciale.</DialogDescription>
      </DialogHeader>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit({ ...f, user_id: userId, period_start: new Date(f.period_start).toISOString(), period_end: new Date(f.period_end).toISOString(), target_value: Number(f.target_value) }); }} className="space-y-3">
        <div><Label className="overline">Utente</Label>
          <Select value={userId} onValueChange={setUserId}>
            <SelectTrigger className="rounded-sm h-10" data-testid="ng-user"><SelectValue placeholder="Seleziona…" /></SelectTrigger>
            <SelectContent>{(users?.items || []).map(u => <SelectItem key={u.id} value={u.id}>{u.first_name || u.email}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Metrica</Label>
            <Select value={f.metric} onValueChange={(v) => upd("metric", v)}>
              <SelectTrigger className="rounded-sm h-10" data-testid="ng-metric"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="revenue">Fatturato</SelectItem>
                <SelectItem value="leads">Lead</SelectItem>
                <SelectItem value="deals_won">Vinti</SelectItem>
                <SelectItem value="appointments">Appuntamenti</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label className="overline">Periodo</Label>
            <Select value={f.period_type} onValueChange={(v) => upd("period_type", v)}>
              <SelectTrigger className="rounded-sm h-10" data-testid="ng-period"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="month">Mensile</SelectItem><SelectItem value="quarter">Trimestrale</SelectItem><SelectItem value="year">Annuale</SelectItem></SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Dal</Label><Input type="date" value={f.period_start} onChange={(e) => upd("period_start", e.target.value)} className="rounded-sm h-10" data-testid="ng-from" /></div>
          <div><Label className="overline">Al</Label><Input type="date" value={f.period_end} onChange={(e) => upd("period_end", e.target.value)} className="rounded-sm h-10" data-testid="ng-to" /></div>
        </div>
        <div><Label className="overline">Target</Label><Input type="number" value={f.target_value} onChange={(e) => upd("target_value", e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="ng-target" /></div>
        <DialogFooter><Button type="submit" disabled={loading || !userId} className="rounded-sm" data-testid="ng-submit">{loading ? "…" : "Crea obiettivo"}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
