import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const fmtEUR = (v) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }).format(Number(v || 0));
const AUTH_LABEL = { COMMERCIAL_AUTHORIZED: "✓ PREZZO SOSTENIBILE — applicabile", ADMIN_AUTHORIZED: "✓ PREZZO SOSTENIBILE — oltre 30%, autorizzazione amministrativa presente",
  ADMIN_APPROVAL_REQUIRED: "⚠ ADMIN APPROVAL REQUIRED — sconto oltre 30%", BLOCKED: "⚠ PREZZO NON ECONOMICAMENTE SOSTENIBILE", NOT_NEEDED: "Il nostro prezzo è già inferiore", UNKNOWN: "Confronto non determinabile (IVA concorrente non nota)" };

export function CompetitorAnalyzerCard({ quoteId, editable, isAdmin }) {
  const qc = useQueryClient();
  const [f, setF] = React.useState({ competitor_price: "", vat_included: "UNKNOWN", competitor_vat_rate: "", competitor_name: "", notes: "" });
  const [sim, setSim] = React.useState(null);
  const [savedId, setSavedId] = React.useState(null);
  const { data: hist } = useQuery({ queryKey: ["competitor", quoteId], queryFn: async () => (await api.get(`/quotes/${quoteId}/competitor`)).data });
  const body = () => ({ competitor_price: Number(f.competitor_price), vat_included: f.vat_included, competitor_vat_rate: f.competitor_vat_rate || null, competitor_name: f.competitor_name || null, notes: f.notes || null });
  const simulate = useMutation({ mutationFn: async () => (await api.post(`/quotes/${quoteId}/competitor/simulate`, body())).data, onSuccess: (d) => { setSim(d); setSavedId(null); }, onError: (e) => toast.error(e.response?.data?.detail?.message || "Simulazione fallita") });
  const save = useMutation({ mutationFn: async () => (await api.post(`/quotes/${quoteId}/competitor`, body())).data, onSuccess: (d) => { setSavedId(d.id); setSim(d.simulation); qc.invalidateQueries({ queryKey: ["competitor", quoteId] }); toast.success("Confronto salvato"); } });
  const apply = useMutation({ mutationFn: async () => (await api.post(`/quotes/${quoteId}/competitor/${savedId}/apply`)).data,
    onSuccess: () => { toast.success("Prezzo target applicato"); qc.invalidateQueries({ queryKey: ["quote", quoteId] }); qc.invalidateQueries({ queryKey: ["competitor", quoteId] }); },
    onError: (e) => toast.error(e.response?.data?.detail?.message || "Applicazione non consentita") });
  const canApply = sim && ["COMMERCIAL_AUTHORIZED", "ADMIN_AUTHORIZED"].includes(sim.authority) && editable;
  const ss = sim?.simulated_snapshot || {};
  return (
    <Card className="rounded-sm border-border p-4" data-testid="competitor-analyzer-card">
      <div className="overline mb-3">Confronta offerta concorrente / prezzo target</div>
      <div className="grid grid-cols-2 gap-2">
        <div><Label className="text-[10px] uppercase">Prezzo concorrente €</Label><Input type="number" step="0.01" value={f.competitor_price} onChange={(e) => setF({ ...f, competitor_price: e.target.value })} className="rounded-sm h-9" data-testid="competitor-price-input" /></div>
        <div><Label className="text-[10px] uppercase">IVA inclusa?</Label>
          <Select value={f.vat_included} onValueChange={(v) => setF({ ...f, vat_included: v })}><SelectTrigger className="rounded-sm h-9" data-testid="competitor-vat-included"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="YES">Sì</SelectItem><SelectItem value="NO">No</SelectItem><SelectItem value="UNKNOWN">Non so</SelectItem></SelectContent></Select></div>
        <div><Label className="text-[10px] uppercase">Aliquota concorrente</Label>
          <Select value={f.competitor_vat_rate || "UNKNOWN"} onValueChange={(v) => setF({ ...f, competitor_vat_rate: v === "UNKNOWN" ? "" : v })}><SelectTrigger className="rounded-sm h-9" data-testid="competitor-vat-rate"><SelectValue /></SelectTrigger>
            <SelectContent>{["4", "10", "22", "MIXED", "UNKNOWN"].map((r) => <SelectItem key={r} value={r}>{r === "UNKNOWN" ? "Non nota" : r === "MIXED" ? "Mista" : `${r}%`}</SelectItem>)}</SelectContent></Select></div>
        <div><Label className="text-[10px] uppercase">Concorrente (facoltativo)</Label><Input value={f.competitor_name} onChange={(e) => setF({ ...f, competitor_name: e.target.value })} className="rounded-sm h-9" data-testid="competitor-name-input" /></div>
      </div>
      <div className="flex gap-2 mt-3">
        <Button size="sm" variant="outline" className="rounded-sm" disabled={!f.competitor_price} onClick={() => simulate.mutate()} data-testid="competitor-simulate-btn">Simula</Button>
        <Button size="sm" variant="outline" className="rounded-sm" disabled={!sim || !editable} onClick={() => save.mutate()} data-testid="competitor-save-btn">Salva confronto</Button>
        {canApply && savedId && <Button size="sm" className="rounded-sm" onClick={() => { if (window.confirm(`Prezzo attuale ${fmtEUR(sim.our_net)} → target ${fmtEUR(sim.target_net)} (sconto ${sim.required_effective_discount_percent}%)${isAdmin ? ` · margine post ${ss.post_margin_percent?.toFixed(2)}%` : ""} · commissione ${(Number(sim.commission_if_matched || 0) * 100).toFixed(2)}%. Confermi?`)) apply.mutate(); }} data-testid="competitor-apply-btn">Applica prezzo target</Button>}
      </div>
      {sim && (
        <div className="mt-3 text-xs space-y-1" data-testid="competitor-result">
          <table className="w-full"><thead><tr className="text-muted-foreground text-[10px] uppercase"><th className="text-left">Parametro</th><th className="text-right">Nostro</th><th className="text-right">Concorrente</th><th className="text-right">Differenza</th></tr></thead><tbody>
            <tr><td>Imponibile</td><td className="text-right font-mono-plex">{fmtEUR(sim.our_net)}</td><td className="text-right font-mono-plex">{sim.competitor_net != null ? fmtEUR(sim.competitor_net) : "NON DISPONIBILE"}</td><td className="text-right font-mono-plex">{sim.price_difference_eur != null ? `${fmtEUR(sim.price_difference_eur)} (${sim.price_difference_percent}%)` : "—"}</td></tr>
            <tr><td>IVA inclusa</td><td className="text-right font-mono-plex">{fmtEUR(sim.our_gross)}</td><td className="text-right font-mono-plex">{sim.competitor_gross != null ? fmtEUR(sim.competitor_gross) : "NON DISPONIBILE"}</td><td className="text-right font-mono-plex">{sim.gross_difference_eur != null ? fmtEUR(sim.gross_difference_eur) : "—"}</td></tr>
            {(sim.scope_comparability?.rows || []).map((r) => <tr key={r.parameter}><td className="capitalize">{r.parameter}</td><td className="text-right">{String(r.ours ?? "—")}</td><td className="text-right">{String(r.competitor)}</td><td className="text-right">{r.match == null ? "—" : r.match ? "=" : "≠"}</td></tr>)}
          </tbody></table>
          {sim.vat_note && <div className="text-amber-700" data-testid="competitor-vat-note">{sim.vat_note}</div>}
          {sim.scope_comparability && <div>Scope comparability: <b>{sim.scope_comparability.status}</b>{sim.scope_comparability.note ? ` — ${sim.scope_comparability.note}` : ""}</div>}
          {sim.required_effective_discount_percent != null && <div>Sconto necessario per pareggiare: <b>{sim.required_effective_discount_percent}%</b> · max sostenibile {sim.max_sustainable_discount_percent}%</div>}
          {sim.minimum_sustainable_net_price != null && <div>Miglior prezzo sostenibile: <b>{fmtEUR(sim.minimum_sustainable_net_price)}</b> (IVA incl. {fmtEUR(sim.minimum_sustainable_gross_price)})</div>}
          {sim.authority === "BLOCKED" && <div className="text-destructive font-bold" data-testid="competitor-gap">Il prezzo concorrente non è raggiungibile mantenendo il margine minimo aziendale. Gap non copribile: {fmtEUR(sim.uncoverable_gap_eur)}</div>}
          {isAdmin && ss.post_margin_percent != null && <div data-testid="competitor-admin-margin">Margine attuale → a target: <b>{ss.post_margin_percent.toFixed(2)}%</b> · commissione {(Number(ss.actual_commission_rate || 0) * 100).toFixed(2)}%</div>}
          <div className={`font-bold ${sim.feasible ? "text-emerald-700" : "text-amber-700"}`} data-testid="competitor-authority">{AUTH_LABEL[sim.authority] || sim.authority}</div>
        </div>
      )}
      {(hist?.items || []).length > 0 && <div className="mt-3 text-[10px] text-muted-foreground" data-testid="competitor-history">{hist.items.length} confronti salvati · ultimo: {fmtEUR(hist.items[0].competitor_price)} ({hist.items[0].decision})</div>}
    </Card>
  );
}
