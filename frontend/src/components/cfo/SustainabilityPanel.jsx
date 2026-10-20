import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`);
const FIELDS = [["annual_fixed_cost_target", "Costi fissi annui (override registry)"], ["structure_coverage_target_date", "Copertura struttura entro (data)"], ["expected_monthly_jobs", "Vendite attese / mese"], ["expected_monthly_revenue", "Fatturato atteso / mese"], ["target_monthly_contribution", "Target contribution / mese"], ["target_profit", "Target utile annuo"], ["average_contribution_pct", "Contribution media %"], ["current_close_rate", "Close rate attuale %"]];

export function SustainabilityPanel({ legalEntityId }) {
  const qc = useQueryClient();
  const le = !legalEntityId || legalEntityId === "all" ? "GROUP" : legalEntityId;
  const { data: d } = useQuery({ queryKey: ["sustainability-overview", le], queryFn: async () => (await api.get("/sustainability/overview", { params: { legal_entity_id: le } })).data });
  const [f, setF] = React.useState({});
  const [sim, setSim] = React.useState({ expected_monthly_jobs: "", expected_monthly_revenue: "", average_contribution_pct: "", close_rate: "" });
  const [simOut, setSimOut] = React.useState(null);
  React.useEffect(() => { if (d) setF(Object.fromEntries(FIELDS.map(([k]) => [k, d.settings[k] ?? ""]).concat([["planning_mode", d.settings.planning_mode || "HYBRID_MODE"]]))); }, [d]);
  const save = useMutation({ mutationFn: async () => (await api.put("/sustainability/settings", { legal_entity_id: le, ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : (k === "planning_mode" || k === "structure_coverage_target_date" ? v : Number(v))])) })).data,
    onSuccess: () => { toast.success("Piano sostenibilità salvato — ricalcolato"); qc.invalidateQueries({ queryKey: ["sustainability-overview"] }); qc.invalidateQueries({ queryKey: ["cfo-overview"] }); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const run = useMutation({ mutationFn: async () => (await api.post("/sustainability/simulate", { legal_entity_id: le, ...Object.fromEntries(Object.entries(sim).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)])) })).data, onSuccess: setSimOut, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  if (!d) return null;
  const p = d.plan, reg = d.fixed_cost_registry;
  return (
    <Card className="rounded-sm p-4 space-y-3" data-testid="sustainability-panel">
      <div className="flex items-center justify-between"><div className="overline">Pricing &amp; Sustainability · costi fissi nel controllo prezzi</div><Badge className={`rounded-sm text-[10px] ${p.data_quality === "COMPLETE" ? "bg-emerald-600 text-white" : "bg-amber-500 text-white"}`} data-testid="sus-data-quality">PRICING SUSTAINABILITY = {p.data_quality}</Badge></div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
        <div className="border rounded-sm p-2" data-testid="sus-registry"><div className="text-[10px] uppercase text-muted-foreground">Costi fissi annui (registry)</div><div className="font-mono-plex font-black">{eur(reg.annual_total)}</div><div className="text-[10px]">PO ref {eur(reg.po_reference_annual)} · Δ {eur(reg.reconciliation_diff)} · <b>{reg.reconciliation_status}</b></div></div>
        <div className="border rounded-sm p-2" data-testid="sus-secured"><div className="text-[10px] uppercase text-muted-foreground">Contribution SECURED YTD</div><div className="font-mono-plex font-black">{eur(p.secured_contribution_ytd)}</div><div className="text-[10px]">{d.secured.signed_contracts_counted} contratti · pipeline FORECAST {eur(d.secured.forecast_pipeline_contribution)} (non acquisito)</div></div>
        <div className="border rounded-sm p-2" data-testid="sus-coverage-pct"><div className="text-[10px] uppercase text-muted-foreground">Struttura coperta</div><div className="font-mono-plex font-black">{p.structure_coverage_percent == null ? "—" : `${p.structure_coverage_percent}%`}</div><div className="text-[10px]">residuo {eur(p.structure_residual)} · {p.phase} · forecast {p.forecast_coverage_date || "n/d"}</div></div>
        <div className="border rounded-sm p-2" data-testid="sus-monthly"><div className="text-[10px] uppercase text-muted-foreground">Target struttura / mese</div><div className="font-mono-plex font-black">{eur(p.monthly_structure_coverage_target)}</div><div className="text-[10px]">entro {p.coverage_target_date} ({p.months_remaining} mesi) · mese attuale {eur(p.monthly.actual_contribution_month)} (gap {eur(p.monthly.month_gap)})</div></div>
        <div className="border rounded-sm p-2" data-testid="sus-required"><div className="text-[10px] uppercase text-muted-foreground">Richiesto per commessa / % struttura</div><div className="font-mono-plex font-black">{eur(p.required_structure_contribution_per_job)} / {p.required_structure_margin_rate_percent ?? "—"}%</div><div className="text-[10px]">{p.expected_monthly_jobs ?? "—"} vendite · {eur(p.expected_monthly_revenue)} fatturato · {p.planning_mode}{p.profit_target_remaining != null ? ` · utile residuo ${eur(p.profit_target_remaining)}` : ""}</div></div>
      </div>
      <details><summary className="text-xs cursor-pointer font-bold" data-testid="sus-settings-toggle">Pianificazione (Admin) · modalità {f.planning_mode}</summary>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
          {FIELDS.map(([k, l]) => <div key={k}><Label className="text-[10px] uppercase">{l}</Label><Input type={k === "structure_coverage_target_date" ? "date" : "number"} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="rounded-sm h-9" data-testid={`sus-field-${k}`} /></div>)}
          <div><Label className="text-[10px] uppercase">Planning mode</Label><select className="h-9 w-full rounded-sm border px-2 text-sm" value={f.planning_mode || "HYBRID_MODE"} onChange={(e) => setF({ ...f, planning_mode: e.target.value })} data-testid="sus-field-planning_mode">{["HYBRID_MODE", "JOB_COUNT_MODE", "REVENUE_VOLUME_MODE"].map((m) => <option key={m}>{m}</option>)}</select></div>
          <div className="flex items-end"><Button size="sm" className="rounded-sm" onClick={() => save.mutate()} data-testid="sus-settings-save">Salva piano</Button></div>
        </div>
      </details>
      {d.scenarios.by_jobs.length > 0 && (
        <div className="grid md:grid-cols-2 gap-2 text-xs">
          <div data-testid="sus-scenarios-jobs"><div className="text-[10px] uppercase text-muted-foreground mb-1">Vendite attese → quota struttura per commessa (costo fisso invariato)</div><div className="flex flex-wrap gap-1">{d.scenarios.by_jobs.map((s) => <span key={s.expected_jobs} className="border rounded-sm px-2 py-1">{s.expected_jobs} → {eur(s.required_contribution_per_job)}</span>)}</div></div>
          <div data-testid="sus-scenarios-revenue"><div className="text-[10px] uppercase text-muted-foreground mb-1">Fatturato atteso → peso struttura %</div><div className="flex flex-wrap gap-1">{d.scenarios.by_revenue.map((s) => <span key={s.expected_revenue} className="border rounded-sm px-2 py-1">{eur(s.expected_revenue)} → {s.required_structure_percent}%</span>)}</div></div>
        </div>
      )}
      {Object.keys(d.scenarios.presets || {}).length > 0 && (
        <table className="w-full text-xs" data-testid="sus-presets"><thead><tr className="text-left text-[10px] uppercase text-muted-foreground"><th>Scenario</th><th>Struttura/job</th><th>% richiesta</th><th>Break-even fatturato</th><th>Break-even jobs</th><th>Contribution attesa</th><th>Risultato</th><th>Copertura (mesi)</th></tr></thead><tbody>
          {Object.entries(d.scenarios.presets).map(([k, s]) => <tr key={k} className="border-t"><td className="font-bold">{k}</td><td>{eur(s.required_contribution_per_job)}</td><td>{s.required_structure_percent ?? "—"}%</td><td>{eur(s.break_even_revenue_month)}</td><td>{s.break_even_jobs_month ?? "—"}</td><td>{eur(s.expected_contribution_month)}</td><td className={s.expected_operating_result_month < 0 ? "text-red-700" : "text-emerald-700"}>{eur(s.expected_operating_result_month)}</td><td>{s.expected_structure_coverage_months ?? "—"}</td></tr>)}
        </tbody></table>
      )}
      <div className="border-t pt-2">
        <div className="text-[10px] uppercase text-muted-foreground mb-1">Simulatore custom (solo calcolo: nessuna modifica a listini o prezzi)</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
          {[["expected_monthly_jobs", "Vendite/mese"], ["expected_monthly_revenue", "Fatturato/mese"], ["average_contribution_pct", "Contribution %"], ["close_rate", "Close rate %"]].map(([k, l]) => <div key={k}><Label className="text-[10px] uppercase">{l}</Label><Input type="number" value={sim[k]} onChange={(e) => setSim({ ...sim, [k]: e.target.value })} className="rounded-sm h-9" data-testid={`sus-sim-${k}`} /></div>)}
          <Button size="sm" className="rounded-sm" onClick={() => run.mutate()} data-testid="sus-sim-run">Simula</Button>
        </div>
        {simOut && <div className="text-xs mt-2 grid grid-cols-2 md:grid-cols-4 gap-1" data-testid="sus-sim-output">{[["Contribution richiesta/mese", eur(simOut.required_contribution_per_month)], ["Richiesta per commessa", eur(simOut.required_contribution_per_job)], ["% struttura", `${simOut.required_structure_percent ?? "—"}%`], ["Break-even fatturato", eur(simOut.break_even_revenue_month)], ["Break-even jobs", simOut.break_even_jobs_month ?? "—"], ["Pipeline richiesta", simOut.required_pipeline ?? "—"], ["Contribution attesa", eur(simOut.expected_contribution_month)], ["Risultato atteso", eur(simOut.expected_operating_result_month)]].map(([l, v]) => <div key={l} className="border rounded-sm p-1"><div className="text-[10px] text-muted-foreground">{l}</div><b className="font-mono-plex">{v}</b></div>)}</div>}
      </div>
    </Card>
  );
}
