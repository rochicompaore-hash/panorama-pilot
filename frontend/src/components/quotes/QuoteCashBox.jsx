import React from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SustainabilityBox } from "@/components/quotes/SustainabilityBox";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`);
const TONE = { GREEN: "bg-emerald-600 text-white", ORANGE: "bg-amber-500 text-white", RED: "bg-red-600 text-white", INCOMPLETE: "bg-zinc-400 text-white", LOW: "bg-emerald-600 text-white", MEDIUM: "bg-amber-500 text-white", HIGH: "bg-red-600 text-white" };
const STEP_IT = { ORDER: "firma", TECHNICAL_SURVEY: "rilievo", GOODS_READY: "merce pronta", INSTALLATION: "posa", FINANCING: "finanziamento", APM: "APM" };

export function QuoteCashBox({ quoteId, isAdmin, financial, refreshKey }) {
  const { data: sus } = useQuery({ queryKey: ["sustainability-quote", quoteId, undefined, refreshKey], queryFn: async () => (await api.get(`/sustainability/quote/${quoteId}`)).data });
  const { data: cash } = useQuery({ queryKey: ["quote-cash-exposure", quoteId, refreshKey], queryFn: async () => (await api.get(`/cfo/quote/${quoteId}/cash-exposure`)).data, enabled: !!isAdmin });
  const [open, setOpen] = React.useState(false);
  const [preset, setPreset] = React.useState("50/50");
  const [custom, setCustom] = React.useState("30,70");
  const [out, setOut] = React.useState(null);
  const sim = useMutation({ mutationFn: async () => {
    const body = preset === "CUSTOM" ? { preset: "CUSTOM", splits: custom.split(",").map((p, i, a) => ({ step: i === 0 ? "ORDER" : i === a.length - 1 && a.length > 2 ? "INSTALLATION" : "GOODS_READY", percent: Number(p.trim()) })) } : { preset };
    return (await api.post(`/cfo/quote/${quoteId}/cash-terms-simulate`, body)).data;
  }, onSuccess: setOut, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  if (!isAdmin) return <SustainabilityBox quoteId={quoteId} isAdmin={false} refreshKey={refreshKey} />;
  const marginPct = financial?.post_margin_percent;
  const marginTone = marginPct == null ? "INCOMPLETE" : marginPct > 15 ? "GREEN" : "RED";
  const r = out || cash;
  return (
    <Card className="rounded-sm border-border p-4 space-y-2" data-testid="quote-cash-box">
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="border rounded-sm p-2" data-testid="qcb-margin"><div className="text-[10px] uppercase text-muted-foreground">Margine diretto</div><Badge className={`rounded-sm text-sm ${TONE[marginTone]}`} data-testid="qcb-margin-value">{marginPct == null ? "n/d" : `${Number(marginPct).toFixed(1)}%`}</Badge></div>
        <div className="border rounded-sm p-2" data-testid="qcb-sustainability"><div className="text-[10px] uppercase text-muted-foreground">Sostenibilità struttura</div><Badge className={`rounded-sm text-sm ${TONE[sus?.status] || TONE.INCOMPLETE}`} data-testid="qcb-sustainability-value">{sus?.status || "…"}</Badge>{sus?.provisional && <div className="text-[9px] text-amber-700">PROVISIONAL</div>}</div>
        <div className="border rounded-sm p-2" data-testid="qcb-exposure"><div className="text-[10px] uppercase text-muted-foreground">Esposizione cash prevista</div><Badge className={`rounded-sm text-sm ${TONE[cash?.exposure_level] || TONE.INCOMPLETE}`} data-testid="qcb-exposure-value">{cash ? `${eur(cash.peak_cash_exposure)} · ${cash.exposure_level || "n/d"}` : "…"}</Badge></div>
      </div>
      <button type="button" className="text-xs underline text-muted-foreground" onClick={() => setOpen(!open)} data-testid="qcb-toggle-details">{open ? "Nascondi dettagli" : "Mostra dettagli"}</button>
      {open && (
        <div className="space-y-2" data-testid="qcb-details">
          {cash && <div className="text-xs grid grid-cols-2 md:grid-cols-4 gap-1">
            {[["Condizioni", cash.payment_terms || "—"], ["Acconto incassato alla firma", eur(cash.deposit_received)], ["Costi diretti da pagare", eur(cash.direct_costs)], ["Cash positiva", cash.cash_positive_step ? `${STEP_IT[cash.cash_positive_step] || cash.cash_positive_step} (~${cash.cash_positive_day} gg)` : "mai prima della posa"]].map(([l, v]) => <div key={l} className="border rounded-sm p-1"><div className="text-[10px] text-muted-foreground">{l}</div><b className="font-mono-plex">{v}</b></div>)}
          </div>}
          <div className="border-t pt-2">
            <div className="text-[10px] uppercase text-muted-foreground mb-1">Simulatore condizioni di pagamento (solo calcolo)</div>
            <div className="flex flex-wrap gap-1 items-center">
              {["50/50", "40/60", "30/70", "50/40/10", "CUSTOM"].map((p) => <Button key={p} size="sm" variant={preset === p ? "default" : "outline"} className="rounded-sm h-7 text-[10px]" onClick={() => setPreset(p)} data-testid={`qcb-preset-${p.replace(/\//g, "-")}`}>{p}</Button>)}
              {preset === "CUSTOM" && <input className="h-7 w-28 rounded-sm border px-2 text-xs" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="30,70" data-testid="qcb-custom-input" />}
              <Button size="sm" className="rounded-sm h-7 text-[10px]" onClick={() => sim.mutate()} data-testid="qcb-simulate">Simula</Button>
            </div>
            {r && <div className="grid grid-cols-3 gap-1 text-xs mt-2" data-testid="qcb-sim-output">
              <div className="border rounded-sm p-1"><div className="text-[10px] text-muted-foreground">Acconto</div><b className="font-mono-plex" data-testid="qcb-sim-deposit">{eur(r.deposit_received)}</b></div>
              <div className="border rounded-sm p-1"><div className="text-[10px] text-muted-foreground">Cassa massima da finanziare</div><b className="font-mono-plex" data-testid="qcb-sim-peak">{eur(r.peak_cash_exposure)} <Badge className={`rounded-sm text-[9px] ${TONE[r.exposure_level] || TONE.INCOMPLETE}`}>{r.exposure_level || "n/d"}</Badge></b></div>
              <div className="border rounded-sm p-1"><div className="text-[10px] text-muted-foreground">Data prevista cash positiva</div><b className="font-mono-plex" data-testid="qcb-sim-positive">{r.cash_positive_date ? `${r.cash_positive_date} (${STEP_IT[r.cash_positive_step] || r.cash_positive_step})` : "n/d"}</b></div>
            </div>}
          </div>
          <SustainabilityBox quoteId={quoteId} isAdmin refreshKey={refreshKey} />
        </div>
      )}
    </Card>
  );
}
