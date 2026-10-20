import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`);
const TONE = { GREEN: "bg-emerald-600 text-white", ORANGE: "bg-amber-500 text-white", RED: "bg-red-600 text-white", INCOMPLETE: "bg-zinc-400 text-white" };

export function SustainabilityBox({ quoteId, isAdmin, discountPct, refreshKey }) {
  const { data: d } = useQuery({ queryKey: ["sustainability-quote", quoteId, discountPct, refreshKey], queryFn: async () => (await api.get(`/sustainability/quote/${quoteId}`, { params: discountPct ? { discount_percent: discountPct } : {} })).data });
  if (!d) return null;
  if (!isAdmin || !d.is_admin_view) {
    return <Card className="rounded-sm border-border p-3 text-xs flex items-center justify-between" data-testid="sustainability-commercial"><span>Controllo economico</span><Badge className={`rounded-sm text-[10px] ${d.direct_margin_ok ? TONE.GREEN : TONE.RED}`} data-testid="sustainability-commercial-status">{d.status_meaning}</Badge></Card>;
  }
  const row = (l, v, tid) => <div className="flex justify-between text-xs"><span className="text-muted-foreground">{l}</span><span className="font-mono-plex" data-testid={tid}>{v}</span></div>;
  return (
    <Card className="rounded-sm border-border p-4 space-y-1" data-testid="sustainability-box">
      <div className="flex items-center justify-between mb-2"><div className="overline">Sostenibilità commessa</div><Badge className={`rounded-sm ${TONE[d.status]}`} data-testid="sustainability-status">{d.status}</Badge></div>
      {row("Ricavo netto", eur(d.net_revenue_ex_vat), "sus-net")}
      {row("Costi diretti", eur(d.direct_costs), "sus-direct")}
      {row("Contribution", `${eur(d.contribution_margin_amount)} / ${d.contribution_margin_percent ?? "—"}%`, "sus-contribution")}
      {row(`Target contribution struttura (${d.planning_mode})`, eur(d.required_structure_contribution), "sus-required")}
      {d.planning_mode === "HYBRID_MODE" && row("  per n° commesse / per volume", `${eur(d.required_by_job_count)} / ${eur(d.required_by_revenue_volume)}`, "sus-hybrid")}
      {row(d.sustainability_gap >= 0 ? "Surplus" : "Gap", eur(d.sustainability_gap), "sus-gap")}
      <div className="text-[10px] text-muted-foreground" data-testid="sus-meaning">{d.status_meaning}</div>
      <div className="border-t pt-1 mt-1">
        {row("Prezzo cliente attuale", eur(d.prices.current_customer_price), "sus-price-current")}
        {row("Prezzo minimo diretto (floor 15%)", eur(d.prices.direct_minimum_sustainable_price), "sus-price-min")}
        {row("Prezzo target strutturale (direzionale)", eur(d.prices.structural_target_price), "sus-price-target")}
      </div>
      <div className="border-t pt-1 mt-1">
        {row("Expected sales / revenue", `${d.expected_monthly_jobs ?? "—"} / ${eur(d.expected_monthly_revenue)}`, "sus-expected")}
        {row("Structure coverage YTD", d.structure_coverage_percent == null ? "—" : `${d.structure_coverage_percent}%`, "sus-coverage")}
        {d.if_accepted?.monthly_contribution_target != null && row("Se accettato: target mese / già acquisito / nuovo / residuo", `${eur(d.if_accepted.monthly_contribution_target)} / ${eur(d.if_accepted.already_secured)} / ${eur(d.if_accepted.new_total)} / ${eur(d.if_accepted.remaining)}`, "sus-if-accepted")}
      </div>
      {d.discount_impact && <div className="text-[10px] text-amber-700 font-bold mt-1" data-testid="sus-discount-impact">{d.discount_impact.message}</div>}
      {d.data_quality !== "COMPLETE" && <div className="text-[10px] text-amber-700" data-testid="sus-incomplete">PRICING SUSTAINABILITY = INCOMPLETE (mancano: {(d.missing || []).join(", ")}) · riconciliazione costi fissi: {d.fixed_cost_reconciliation}</div>}
    </Card>
  );
}
