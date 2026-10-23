import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SustainabilityPanel } from "@/components/cfo/SustainabilityPanel";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`);
const pct = (v) => (v == null ? "—" : `${v}%`);

function Kpi({ label, value, sub, tone, testId, kind }) {
  const tones = { bad: "border-red-300 bg-red-50", warn: "border-amber-300 bg-amber-50", good: "border-emerald-300 bg-emerald-50", muted: "border-border" };
  return (
    <Card className={`rounded-sm p-3 ${tones[tone] || tones.muted}`} data-testid={testId}>
      <div className="flex items-center justify-between"><div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">{label}</div>{kind && <Badge variant="outline" className="rounded-sm text-[9px]">{kind}</Badge>}</div>
      <div className="font-mono-plex text-xl font-black mt-1" data-testid={testId ? `${testId}-value` : undefined}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground mt-1">{sub}</div>}
    </Card>
  );
}

function SettingsForm({ le, settings, accounts }) {
  const qc = useQueryClient();
  const [f, setF] = React.useState({});
  const [bank, setBank] = React.useState({ bank_account_id: accounts?.[0]?.id || "", balance: "", as_of_date: new Date().toISOString().slice(0, 10) });
  React.useEffect(() => { setF({ monthly_revenue_target: settings?.monthly_revenue_target ?? "", annual_revenue_target: settings?.annual_revenue_target ?? "", monthly_collection_target: settings?.monthly_collection_target ?? "", minimum_cash_reserve: settings?.minimum_cash_reserve ?? "" }); }, [settings]);
  const inv = () => Promise.all([
    qc.invalidateQueries({ queryKey: ["cfo-overview"] }),
    qc.invalidateQueries({ queryKey: ["cash-command-center"] }),
  ]);
  const save = useMutation({ mutationFn: async () => (await api.put("/cfo/settings", { legal_entity_id: le, ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : Number(v)])) })).data, onSuccess: () => { toast.success("Target CFO salvati"); inv(); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const cert = useMutation({ mutationFn: async () => (await api.post("/cfo/bank-balance", { ...bank, balance: Number(bank.balance), legal_entity_id: le === "GROUP" ? null : le })).data, onSuccess: () => { toast.success("Saldo banca certificato"); inv(); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  return (
    <Card className="rounded-sm p-4 space-y-3" data-testid="cfo-settings-card">
      <div className="overline">Configurazione CFO · {le}</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[["monthly_revenue_target", "Target fatturato mese"], ["annual_revenue_target", "Target fatturato anno"], ["monthly_collection_target", "Target incassi mese"], ["minimum_cash_reserve", "Riserva minima cassa"]].map(([k, l]) => (
          <div key={k}><Label className="text-[10px] uppercase">{l}</Label><Input type="number" value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="rounded-sm h-9" data-testid={`cfo-setting-${k}`} /></div>
        ))}
      </div>
      <Button size="sm" className="rounded-sm" onClick={() => save.mutate()} data-testid="cfo-settings-save">Salva target</Button>
      <div className="border-t pt-3 grid grid-cols-2 md:grid-cols-4 gap-2 items-end">
        <div><Label className="text-[10px] uppercase">Conto</Label><select className="h-9 w-full rounded-sm border px-2 text-sm" value={bank.bank_account_id} onChange={(e) => setBank({ ...bank, bank_account_id: e.target.value })} data-testid="cfo-bank-select">{(accounts || []).map((a) => <option key={a.id} value={a.id}>{a.label} ({a.status === "CERTIFIED" ? `certificato ${a.certified_at}` : "NON CERTIFICATO"})</option>)}</select></div>
        <div><Label className="text-[10px] uppercase">Saldo certificato</Label><Input type="number" value={bank.balance} onChange={(e) => setBank({ ...bank, balance: e.target.value })} className="rounded-sm h-9" data-testid="cfo-bank-balance" /></div>
        <div><Label className="text-[10px] uppercase">Data saldo</Label><Input type="date" value={bank.as_of_date} onChange={(e) => setBank({ ...bank, as_of_date: e.target.value })} className="rounded-sm h-9" data-testid="cfo-bank-date" /></div>
        <Button size="sm" className="rounded-sm" disabled={!bank.bank_account_id || bank.balance === ""} onClick={() => cert.mutate()} data-testid="cfo-bank-certify">Certifica saldo</Button>
      </div>
    </Card>
  );
}

export function CfoControlTower({ legalEntityId }) {
  const le = !legalEntityId || legalEntityId === "all" ? "GROUP" : legalEntityId;
  const { data: d, isLoading, error } = useQuery({ queryKey: ["cfo-overview", le], queryFn: async () => (await api.get("/cfo/overview", { params: { legal_entity_id: le } })).data, refetchInterval: 60000 });
  const [showSettings, setShowSettings] = React.useState(false);
  if (isLoading) return <div className="text-sm text-muted-foreground" data-testid="cfo-loading">Caricamento CFO Control Tower…</div>;
  if (error || !d) return <div className="text-sm text-destructive" data-testid="cfo-error">Errore caricamento CFO: {error?.message}</div>;
  const r1 = d.kpi_row1, r2 = d.kpi_row2, r3 = d.kpi_row3, inc = d.cash_flow_status === "INCOMPLETE";
  const fc = d.forecast_month_end;
  const exclusions = d.forecast_exclusions;
  const cashBlockMessage = r1.forecast_block_message || d.cash_position?.forecast_block_message;
  return (
    <div className="space-y-4" data-testid="cfo-control-tower">
      <div className="flex items-center justify-between">
        <div><div className="overline">Cash &amp; Revenue Control Tower · {d.legal_entity_id} · {d.today}</div><div className="text-[10px] text-muted-foreground">VENDUTO ≠ FATTURATO ≠ INCASSATO · ACTUAL e FORECAST distinti · IVA esclusa dai ricavi</div></div>
        <div className="flex gap-2 items-center">{inc && <Badge className="rounded-sm bg-amber-500 text-white" data-testid="cfo-cash-incomplete">CASH FORECAST = INCOMPLETE</Badge>}<Button size="sm" variant="outline" className="rounded-sm" onClick={() => setShowSettings(!showSettings)} data-testid="cfo-toggle-settings">Configurazione</Button></div>
      </div>
      {showSettings && <SettingsForm le={le} settings={d.settings} accounts={d.cash_position?.accounts} />}
      {inc && cashBlockMessage && <div className="border border-amber-300 bg-amber-50 rounded-sm p-3 text-xs font-bold text-amber-800" data-testid="cfo-cash-block-reason">{cashBlockMessage}</div>}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Kpi label="Venduto mese" value={eur(r1.sold_month)} kind="ACTUAL" sub={`${d.revenue.sold.contracts_complete} contratti validi · ${d.revenue.sold.contracts_legacy_excluded} legacy esclusi`} testId="kpi-sold" />
        <Kpi label="Fatturato mese" value={eur(r1.invoiced_month)} kind="ACTUAL" tone={r1.invoiced_status !== "OK" ? "warn" : undefined} sub={r1.invoiced_status === "OK" ? "imponibile netto IVA" : "DATA STATUS: NO INVOICE DATA AVAILABLE"} testId="kpi-invoiced" />
        <Kpi label="Incassato mese" value={eur(r1.collected_month)} kind="ACTUAL" sub={`YTD ${eur(d.collected_ytd)} · conversione ${pct(d.cash_conversion_percent)} · DSO ${d.dso === "NOT_AVAILABLE" ? "n/d" : d.dso}`} testId="kpi-collected" />
        <Kpi label="Uscite mese" value={eur(r1.paid_month)} kind="ACTUAL" sub={`previste a fine mese ${eur(fc.outflows.scheduled_to_month_end)}`} testId="kpi-paid" />
        <Kpi label="Cassa stimata oggi" value={r1.available_cash == null ? "INCOMPLETE" : eur(r1.current_cash_estimate ?? r1.available_cash)} tone={r1.available_cash == null ? "warn" : undefined} sub={r1.available_cash == null ? (cashBlockMessage || "BANK BALANCE NOT CONFIGURED") : `saldo certificato ${eur(r1.certified_cash)} al ${r1.cash_as_of || d.cash_position.as_of} + movimenti registrati successivi`} testId="kpi-cash" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Kpi label="Target fatturato" value={r2.revenue_target.monthly_revenue_target ? `${eur(r1.invoiced_month)} / ${eur(r2.revenue_target.monthly_revenue_target)}` : "—"} sub={r2.revenue_target.monthly_revenue_target ? `${pct(r2.revenue_target.percent_reached)} · mancano ${eur(r2.revenue_target.missing_to_target)}` : "MANUAL CONFIGURATION REQUIRED"} testId="kpi-target-revenue" />
        <Kpi label="Target incassi" value={r2.collection_target.monthly_collection_target ? `${eur(r2.collection_target.actual)} / ${eur(r2.collection_target.monthly_collection_target)}` : "—"} sub={r2.collection_target.monthly_collection_target ? pct(r2.collection_target.percent_reached) : "MANUAL CONFIGURATION REQUIRED"} testId="kpi-target-collections" />
        <Kpi label="Cash gap 30 gg" value={r2.cash_gap_30d == null ? "INCOMPLETE" : eur(r2.cash_gap_30d)} tone={r2.cash_gap_30d > 0 ? "bad" : (r2.cash_gap_30d === 0 ? "good" : "warn")} sub={`fabbisogno minimo 30gg ${eur(r2.minimum_cash_requirement_30d)} (uscite + riserva − cassa stimata − incassi previsti)`} testId="kpi-cash-gap" />
        <Kpi label="Forecast cassa fine mese" value={r2.forecast_cash_month_end == null ? "INCOMPLETE" : eur(r2.forecast_cash_month_end)} kind="FORECAST" sub={`incassi ${eur(fc.collections.total_forecast)} · uscite ${eur(fc.outflows.total_forecast)} · fatturato ${eur(fc.revenue.total_forecast)}`} testId="kpi-forecast-cash" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Kpi label="Break-even fatturato (mese)" value={eur(r3.break_even_revenue_monthly)} sub={`struttura ${eur(r3.monthly_structure_costs)} / margine ${pct(r3.margin.weighted_margin_percent)} su ${r3.margin.margin_sample_size} commesse complete`} testId="kpi-break-even" />
        <Kpi label="Distanza break-even" value={eur(r3.distance_to_break_even)} sub="fatturato ancora necessario nel mese" testId="kpi-be-distance" />
        <Kpi label="Riserva minima" value={r3.minimum_cash_reserve == null ? "non impostata" : eur(r3.minimum_cash_reserve)} testId="kpi-reserve" />
        <Kpi label="Margin of safety cash 30gg" value={r3.margin_of_safety_cash_30d == null ? "INCOMPLETE" : eur(r3.margin_of_safety_cash_30d)} tone={r3.cash_safety_status === "SAFE" ? "good" : (r3.cash_safety_status ? "bad" : "warn")} sub={r3.cash_safety_status || cashBlockMessage || "cassa non certificata"} testId="kpi-safety" />
      </div>
      <Card className="rounded-sm p-3" data-testid="cfo-13w">
        <div className="flex items-center justify-between"><div className="overline">13-week cash flow</div><div className="text-[10px] text-muted-foreground">non schedulati: incassi {eur(d.unscheduled_inflows)} · uscite {eur(d.unscheduled_outflows)} (fuori calendario){d.first_cash_gap_week ? ` · CASH GAP ALERT ${d.first_cash_gap_week}` : ""}</div></div>
        {exclusions?.total > 0 && <div className="border border-amber-300 bg-amber-50 rounded-sm p-2 mt-2 text-xs text-amber-900 space-y-1" data-testid="cfo-forecast-exclusions">
          <div className="font-bold">Crediti esclusi dalla previsione: {eur(exclusions.total)}</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {exclusions.overdue_receivables > 0 && <span>Scaduti {eur(exclusions.overdue_receivables)}</span>}
            {exclusions.undated_receivables > 0 && <span>Senza data valida {eur(exclusions.undated_receivables)}</span>}
            {exclusions.trigger_expected_receivables > 0 && <span>In attesa di evento operativo {eur(exclusions.trigger_expected_receivables)}</span>}
            {exclusions.disputed_receivables > 0 && <span>Contestati {eur(exclusions.disputed_receivables)}</span>}
            {exclusions.other_receivables > 0 && <span>Altri crediti esclusi {eur(exclusions.other_receivables)}</span>}
          </div>
          <div>Gli scaduti restano tra i crediti da sollecitare; non sono incassi previsti oggi.</div>
        </div>}
        <div className="overflow-x-auto"><table className="w-full text-xs mt-2"><thead><tr className="text-left text-[10px] uppercase text-muted-foreground"><th>Sett.</th><th>Dal</th><th className="text-right">Saldo iniziale</th><th className="text-right">Incassi</th><th className="text-right">Uscite</th><th className="text-right">Saldo finale</th></tr></thead><tbody>
          {d.weeks_13.map((w) => <tr key={w.week} className={`border-t ${w.cash_gap ? "bg-red-50 font-bold" : ""}`} data-testid={`cfo-week-${w.week}`}><td>{w.week}</td><td>{w.start}</td><td className="text-right font-mono-plex">{w.opening == null ? "n/d" : eur(w.opening)}</td><td className="text-right font-mono-plex text-emerald-700">+{eur(w.inflows)}</td><td className="text-right font-mono-plex text-red-700">−{eur(w.outflows)}</td><td className="text-right font-mono-plex">{w.closing == null ? "n/d" : eur(w.closing)}</td></tr>)}
        </tbody></table></div>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mt-3">{Object.entries(d.cash_calendar).map(([k, h]) => <div key={k} className="border rounded-sm p-2 text-xs" data-testid={`cfo-horizon-${k}`}><div className="uppercase text-[10px] text-muted-foreground">{k}</div><div>+{eur(h.inflows)} / −{eur(h.outflows)}</div><div className="font-mono-plex font-bold">{h.forecast_closing_cash == null ? "n/d" : eur(h.forecast_closing_cash)}</div></div>)}</div>
      </Card>
      <SustainabilityPanel legalEntityId={le} />
      <div className="grid md:grid-cols-2 gap-2">
        <Card className="rounded-sm p-3" data-testid="cfo-receivables">
          <div className="overline">Da incassare {eur(d.receivables.total_residual)} · scaduti {eur(d.receivables.aging.total_overdue)}</div>
          <div className="text-[10px] text-muted-foreground mb-2">Aging scaduto: {Object.entries(d.receivables.aging.buckets).map(([k, v]) => `${k}gg ${eur(v)}`).join(" · ")}</div>
          {d.receivables.rows.slice(0, 8).map((r) => <div key={r.customer_id} className="flex justify-between text-xs border-t py-1" data-testid="cfo-ar-row"><span>{r.customer_name} <Badge variant="outline" className="rounded-sm text-[9px] ml-1">{r.status}</Badge></span><span className="font-mono-plex">{eur(r.residual)}{r.overdue > 0 ? ` (scad. ${eur(r.overdue)}, ${r.days_overdue}gg)` : ""}{r.trigger_pending > 0 ? ` · trigger ${eur(r.trigger_pending)}` : ""}</span></div>)}
          {!d.receivables.rows.length && <div className="text-xs text-muted-foreground">Nessun credito aperto.</div>}
        </Card>
        <Card className="rounded-sm p-3" data-testid="cfo-payables">
          <div className="overline">Da pagare · fornitori 7gg {eur(d.payables.supplier_due["7d"])} · 30gg {eur(d.payables.supplier_due["30d"])} · 60gg {eur(d.payables.supplier_due["60d"])}</div>
          <div className="text-[10px] text-muted-foreground mb-2">Scaduti fornitori {eur(d.payables.aging.total_overdue)} · intercompany eliminato (group) {eur(d.payables.intercompany_eliminated)} · impegni acquisto (non in forecast) {d.payables.purchase_committed.length}</div>
          {d.payables.items_30d.slice(0, 8).map((o) => <div key={o.id} className="flex justify-between text-xs border-t py-1" data-testid="cfo-ap-row"><span>{o.label} <Badge variant="outline" className="rounded-sm text-[9px] ml-1">{o.category}</Badge></span><span className="font-mono-plex">{eur(o.amount)} · {o.due_date}</span></div>)}
        </Card>
      </div>
      <div className="grid md:grid-cols-3 gap-2">
        <Card className="rounded-sm p-3 md:col-span-2" data-testid="cfo-next-actions">
          <div className="overline">Next action / alert</div>
          {d.alerts.map((a, i) => <div key={i} className={`text-xs py-1 border-t ${a.severity === "critical" ? "text-red-700 font-bold" : ""}`} data-testid="cfo-alert">⚠ {a.code}: {a.message}</div>)}
          {d.next_actions.map((a, i) => <div key={i} className="text-xs py-1 border-t" data-testid="cfo-action">→ {a.message}</div>)}
        </Card>
        <Card className="rounded-sm p-3" data-testid="cfo-data-quality">
          <div className="overline">Data quality</div>
          {d.data_quality.map((q) => <div key={q.area} className="text-xs py-1 border-t"><span className={q.ok ? "text-emerald-700" : "text-amber-700"}>{q.ok ? "✓" : "⚠"}</span> <b>{q.area}</b> — {q.message}</div>)}
          <div className="text-[10px] text-muted-foreground pt-2">EMAIL_GO_LIVE = {d.email_go_live}</div>
        </Card>
      </div>
    </div>
  );
}
