import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);
const CATS = ["rent", "insurance", "software", "utilities", "consulting", "marketing", "leasing", "logistics", "tax", "energy", "telephony", "admin", "other"];
const REC = ["monthly", "bimonthly", "quarterly", "semiannual", "annual"];

export function FixedCostReconciliation({ legalEntityId }) {
  const qc = useQueryClient();
  const le = !legalEntityId || legalEntityId === "all" ? "GROUP" : legalEntityId;
  const { data: d } = useQuery({ queryKey: ["fixed-cost-registry", le], queryFn: async () => (await api.get("/sustainability/fixed-costs", { params: { legal_entity_id: le } })).data });
  const [f, setF] = React.useState({ label: "", category: "other", amount_raw: "", recurrence: "monthly", supplier: "", cash_due_month: "", cash_due_day: "" });
  const [showDemo, setShowDemo] = React.useState(false);
  const inv = () => { qc.invalidateQueries({ queryKey: ["fixed-cost-registry"] }); qc.invalidateQueries({ queryKey: ["sustainability-overview"] }); qc.invalidateQueries({ queryKey: ["cfo-overview"] }); qc.invalidateQueries({ queryKey: ["cash-command-center"] }); };
  const onErr = (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message);
  const toggle = useMutation({ mutationFn: async ({ item, is_demo }) => (await api.patch(item.source === "personnel_costs" ? `/control/personnel-costs/${item.id}` : `/control/fixed-costs/${item.id}`, { is_demo })).data, onSuccess: () => { toast.success("Classificazione aggiornata"); inv(); }, onError: onErr });
  const del = useMutation({ mutationFn: async (item) => (await api.delete(item.source === "personnel_costs" ? `/control/personnel-costs/${item.id}` : `/control/fixed-costs/${item.id}`)).data, onSuccess: () => { toast.success("Voce eliminata"); inv(); }, onError: onErr });
  const add = useMutation({ mutationFn: async () => {
    const cash_schedule = f.recurrence !== "monthly" ? { recurrence: f.recurrence, due_month: Number(f.cash_due_month || 1), due_day: Number(f.cash_due_day || 5) } : (f.cash_due_day ? { recurrence: "monthly", due_day: Number(f.cash_due_day) } : null);
    return (await api.post("/control/fixed-costs", { label: f.label, category: f.category, amount_raw: Number(f.amount_raw), recurrence: f.recurrence, supplier: f.supplier || null, legal_entity_id: le === "GROUP" ? null : le, cash_schedule })).data;
  }, onSuccess: () => { toast.success("Costo reale registrato"); setF({ label: "", category: "other", amount_raw: "", recurrence: "monthly", supplier: "", cash_due_month: "", cash_due_day: "" }); inv(); }, onError: onErr });
  if (!d) return null;
  const real = d.items.filter((i) => !i.demo_data), demo = d.items.filter((i) => i.demo_data);
  const Row = ({ i }) => (
    <div className="flex items-center justify-between text-xs border-t py-1 gap-2" data-testid={`fc-row-${i.id}`}>
      <span className="flex-1 truncate">{i.label} <Badge variant="outline" className="rounded-sm text-[9px]">{i.category}</Badge> <span className="text-muted-foreground">{i.cost_class}</span>{i.cash_schedule?.recurrence && i.cash_schedule.recurrence !== "monthly" && <span className="text-[9px] text-sky-700"> · cash {i.cash_schedule.recurrence} mese {i.cash_schedule.due_month}</span>}</span>
      <span className="font-mono-plex w-28 text-right">{eur(i.monthly_equivalent)}/m</span>
      <span className="font-mono-plex w-32 text-right font-bold">{eur(i.annual_equivalent)}/a</span>
      <Button size="sm" variant="outline" className="rounded-sm h-7 text-[10px]" onClick={() => toggle.mutate({ item: i, is_demo: !i.demo_data })} data-testid={`fc-toggle-${i.id}`}>{i.demo_data ? "→ REALE" : "→ DEMO"}</Button>
      <Button size="sm" variant="destructive" className="rounded-sm h-7 text-[10px]" onClick={() => del.mutate(i)} data-testid={`fc-delete-${i.id}`}>Elimina</Button>
    </div>
  );
  return (
    <Card className="rounded-sm p-4 space-y-3" data-testid="fixed-cost-reconciliation">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="overline">Costi fissi reali · FIXED COST DATA GATE</div>
        <Badge className={`rounded-sm text-white ${d.reconciliation_status === "COMPLETE" ? "bg-emerald-600" : "bg-amber-500"}`} data-testid="fc-reconciliation-status">FIXED_COST_RECONCILIATION = {d.reconciliation_status} · KPI {d.kpi_status}</Badge>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        {[["PO reference (annuo)", eur(d.po_reference_annual), "fc-po-ref"], ["Costi reali registrati", eur(d.real_annual_total), "fc-real"], ["Differenza", eur(d.reconciliation_diff), "fc-diff"], ["Riconciliazione", `${d.reconciliation_percent}%`, "fc-pct"]].map(([l, v, t]) => <div key={t} className="border rounded-sm p-2" data-testid={t}><div className="text-[10px] uppercase text-muted-foreground">{l}</div><div className="font-mono-plex font-black text-lg">{v}</div></div>)}
      </div>
      <div className="text-[10px] text-muted-foreground">{d.demo_note} Demo esclusi: <b>{eur(d.demo_annual_total)}</b> ({d.demo_items} voci, {d.real_items} reali).</div>
      <div className="border rounded-sm p-3 grid grid-cols-2 md:grid-cols-7 gap-2 items-end" data-testid="fc-add-form">
        <div className="md:col-span-2"><Label className="text-[10px] uppercase">Voce</Label><Input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} className="rounded-sm h-9" data-testid="fc-add-label" /></div>
        <div><Label className="text-[10px] uppercase">Categoria</Label><select className="h-9 w-full rounded-sm border px-2 text-sm" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="fc-add-category">{CATS.map((c) => <option key={c}>{c}</option>)}</select></div>
        <div><Label className="text-[10px] uppercase">Importo</Label><Input type="number" value={f.amount_raw} onChange={(e) => setF({ ...f, amount_raw: e.target.value })} className="rounded-sm h-9" data-testid="fc-add-amount" /></div>
        <div><Label className="text-[10px] uppercase">Ricorrenza</Label><select className="h-9 w-full rounded-sm border px-2 text-sm" value={f.recurrence} onChange={(e) => setF({ ...f, recurrence: e.target.value })} data-testid="fc-add-recurrence">{REC.map((c) => <option key={c}>{c}</option>)}</select></div>
        <div><Label className="text-[10px] uppercase">Cash: mese/giorno</Label><div className="flex gap-1"><Input type="number" placeholder="mese" value={f.cash_due_month} onChange={(e) => setF({ ...f, cash_due_month: e.target.value })} className="rounded-sm h-9" data-testid="fc-add-cash-month" /><Input type="number" placeholder="gg" value={f.cash_due_day} onChange={(e) => setF({ ...f, cash_due_day: e.target.value })} className="rounded-sm h-9" data-testid="fc-add-cash-day" /></div></div>
        <Button size="sm" className="rounded-sm" disabled={!f.label || !f.amount_raw} onClick={() => add.mutate()} data-testid="fc-add-save">Aggiungi reale</Button>
      </div>
      <div data-testid="fc-real-list"><div className="text-[10px] uppercase text-muted-foreground font-bold">Costi reali ({real.length})</div>{real.map((i) => <Row key={i.id} i={i} />)}{!real.length && <div className="text-xs text-muted-foreground">Nessun costo reale registrato: ricostruire i {eur(d.po_reference_annual)} voce per voce.</div>}</div>
      <details open={showDemo} onToggle={(e) => setShowDemo(e.target.open)} data-testid="fc-demo-list"><summary className="text-xs cursor-pointer font-bold">Dati demo esclusi ({demo.length}) · {eur(d.demo_annual_total)}/anno</summary>{demo.map((i) => <Row key={i.id} i={i} />)}</details>
    </Card>
  );
}
