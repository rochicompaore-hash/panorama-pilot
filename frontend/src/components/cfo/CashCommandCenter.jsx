import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine } from "recharts";

const eur = (v) => (v == null ? "n/d" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`);
const COLOR = { GREEN: "bg-emerald-600 text-white", YELLOW: "bg-amber-500 text-white", RED: "bg-red-600 text-white", GREY: "bg-zinc-400 text-white" };
const HEALTH = { SAFE: "bg-emerald-600", TIGHT: "bg-amber-500", AT_RISK: "bg-orange-600", CRITICAL: "bg-red-600", INCOMPLETE: "bg-zinc-500" };
const PRIO = { CRITICAL: "text-red-700", IMPORTANT: "text-amber-700", DEFERRABLE: "text-zinc-600", DISCRETIONARY: "text-zinc-400" };

function Big({ label, value, sub, tone, testId }) {
  const tones = { bad: "border-red-300 bg-red-50", warn: "border-amber-300 bg-amber-50", good: "border-emerald-300 bg-emerald-50", muted: "border-border" };
  return (
    <Card className={`rounded-sm p-4 ${tones[tone] || tones.muted}`} data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">{label}</div>
      <div className="font-mono-plex text-2xl font-black mt-1" data-testid={`${testId}-value`}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground mt-1">{sub}</div>}
    </Card>
  );
}

function Section({ title, testId, children, open }) {
  return (
    <details className="border rounded-sm bg-card" open={open} data-testid={testId}>
      <summary className="cursor-pointer px-4 py-2 text-xs font-bold uppercase tracking-wider select-none">{title}</summary>
      <div className="px-4 pb-4 space-y-2">{children}</div>
    </details>
  );
}

export function CashCommandCenter({ legalEntityId }) {
  const le = !legalEntityId || legalEntityId === "all" ? "GROUP" : legalEntityId;
  const { data: d, isLoading, error } = useQuery({ queryKey: ["cash-command-center", le], queryFn: async () => (await api.get("/cfo/cash-command-center", { params: { legal_entity_id: le } })).data, refetchInterval: 60000 });
  if (isLoading) return <div className="text-sm text-muted-foreground" data-testid="ccc-loading">Caricamento Cash Command Center…</div>;
  if (error || !d) return <div className="text-sm text-destructive" data-testid="ccc-error">Errore: {error?.message}</div>;
  return <CashCommandCenterView data={d} />;
}

export function CashCommandCenterView({ data: d }) {
  const s = d.situation_today, inc = s.cash_status !== "COMPLETE", g30 = s.cash_gap_30d, low = s.lowest_cash_point;
  const exclusions = d.forecast_exclusions;
  const cashBlockMessage = s.forecast_block_message || s.bank_balance_message || "Saldo non certificato: previsione di liquidità non disponibile.";
  const mixedCertificationDates = s.forecast_block_reason === "MIXED_CERTIFICATION_DATES";
  const chart = d.daily_projection.map((p) => ({ d: p.date.slice(5), cash: p.projected_cash }));
  return (
    <div className="space-y-4" data-testid="cash-command-center">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div><div className="overline">Cash Command Center · {d.legal_entity_id} · {d.today}</div><div className="text-[10px] text-muted-foreground">Saldo certificato + movimenti registrati · incassi previsti dalle scadenze da oggi · eventi operativi attesi separati</div></div>
        <div className="flex gap-2 items-center">
          <Badge className={`rounded-sm text-white ${HEALTH[s.cash_health]}`} data-testid="ccc-cash-health">CASH HEALTH: {s.cash_health}</Badge>
          <Badge variant="outline" className="rounded-sm" data-testid="ccc-structure">Struttura coperta {d.structure.structure_coverage_percent ?? "—"}% · {d.structure.kpi_status}</Badge>
        </div>
      </div>
      {inc && <div className="border border-amber-300 bg-amber-50 rounded-sm p-3 text-xs font-bold text-amber-800" data-testid="ccc-bank-not-configured">{cashBlockMessage} — Control Tower → Configurazione.</div>}

      {/* A. SITUAZIONE OGGI — 4 KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Big label="Cassa stimata oggi" value={inc ? (mixedCertificationDates ? "NON DISPONIBILE" : "NON CERTIFICATA") : eur(s.current_cash_estimate ?? s.cash_today)} tone={inc ? "warn" : undefined} sub={inc ? cashBlockMessage : `saldo certificato ${eur(s.certified_cash)} al ${s.cash_as_of}`} testId="ccc-kpi-cash" />
        <Big label="Incassi previsti entro 30 gg" value={eur(s.collections_30d)} sub={`scadenze da oggi · 7 gg ${eur(s.collections_7d)} · scaduti esclusi`} testId="ccc-kpi-in30" />
        <Big label="Uscite prossime 30 gg" value={eur(s.outflows_30d)} sub={`7 gg ${eur(s.outflows_7d)} · obbligatorie ${eur(d.horizons["30d"].mandatory_outflows)}`} testId="ccc-kpi-out30" />
        <Big label="Cassa prevista tra 30 gg" value={inc ? "n/d" : eur(s.projected_cash_30d)} tone={inc ? "warn" : s.projected_cash_30d < 0 ? "bad" : "good"} sub="cassa stimata + incassi previsti − uscite" testId="ccc-kpi-proj30" />
      </div>
      {!inc && <div className="text-[10px] text-muted-foreground" data-testid="ccc-cash-basis">Movimenti registrati dopo il saldo certificato: incassi {eur(s.actual_collections_since_as_of)} · pagamenti {eur(s.actual_payments_since_as_of)}. La cassa stimata non sostituisce un saldo bancario aggiornato.</div>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <Big label={inc ? "Posizione di cassa a 30 gg" : g30.status === "GAP" ? "Cash gap 30 gg" : "Cash surplus 30 gg"} value={inc ? "n/d" : eur(g30.status === "GAP" ? -g30.operating_cash_gap : g30.operating_cash_position)} tone={inc ? "warn" : g30.status === "GAP" ? "bad" : "good"}
          sub={g30.reserve_status === "NOT_CONFIGURED" ? "Riserva minima di sicurezza non configurata · SAFETY GAP = NOT_AVAILABLE" : `riserva ${eur(g30.reserve)} · safety gap ${eur(g30.safety_cash_gap)}`} testId="ccc-kpi-gap" />
        <Big label="Giorno di minima liquidità" value={low ? `${low.date.split("-").reverse().join("/")} · ${eur(low.amount)}` : "n/d"} tone={low ? (low.amount < 0 ? "bad" : "good") : "warn"}
          sub={inc ? cashBlockMessage : `${s.first_negative_date ? `primo giorno sotto zero ${s.first_negative_date}` : "mai sotto zero nell’orizzonte previsto"} · runway ${s.runway.days ?? "n/d"} gg · copertura liquidità ${s.liquidity_coverage.percent ?? "n/d"}% (${s.liquidity_coverage.status})`} testId="ccc-kpi-lowest" />
      </div>
      <div className="border border-sky-200 bg-sky-50 rounded-sm p-3 text-xs flex flex-wrap items-center gap-x-4 gap-y-1" data-testid="ccc-receivables-banner">
        <b>CREDITI NON SIGNIFICA CASSA DISPONIBILE.</b>
        <span>Crediti totali <b className="font-mono-plex">{eur(s.total_receivables)}</b></span>
        <span>· previsti entro 7 gg <b className="font-mono-plex">{eur(s.collectible_7d)}</b></span>
        <span>· previsti entro 30 gg <b className="font-mono-plex">{eur(s.collectible_30d)}</b></span>
        <span>· non ancora monetizzabili <b className="font-mono-plex">{eur(d.receivable_quality.not_yet_monetizable)}</b></span>
        <span>· posizione debitoria 30 gg <b className="font-mono-plex">{eur(s.debt_position_30d)}</b></span>
      </div>
      {exclusions?.total > 0 && <div className="border border-amber-300 bg-amber-50 rounded-sm p-3 text-xs space-y-1" data-testid="ccc-forecast-exclusions">
        <div className="font-bold text-amber-900">Crediti esclusi dalla previsione: {eur(exclusions.total)}</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-amber-900">
          {exclusions.overdue_receivables > 0 && <span data-testid="ccc-overdue-excluded">Scaduti {eur(exclusions.overdue_receivables)}</span>}
          {exclusions.undated_receivables > 0 && <span>Senza data valida {eur(exclusions.undated_receivables)}</span>}
          {exclusions.trigger_expected_receivables > 0 && <span>In attesa di evento operativo {eur(exclusions.trigger_expected_receivables)}</span>}
          {exclusions.disputed_receivables > 0 && <span>Contestati {eur(exclusions.disputed_receivables)}</span>}
          {exclusions.other_receivables > 0 && <span>Altri crediti esclusi {eur(exclusions.other_receivables)}</span>}
        </div>
        <div className="text-amber-800">Gli scaduti restano tra i crediti da sollecitare e non vengono trasformati in incassi di oggi.</div>
      </div>}

      {/* B. PROSSIMI 30/90 GIORNI */}
      <Section title="B · Prossimi giorni — timeline cassa" testId="ccc-timeline" open>
        <div className="grid grid-cols-4 md:grid-cols-8 gap-1 text-xs">
          {Object.entries(d.horizons).map(([k, h]) => <div key={k} className={`border rounded-sm p-2 ${h.projected_cash != null && h.projected_cash < 0 ? "bg-red-50" : ""}`} data-testid={`ccc-h-${k}`}><div className="uppercase text-[10px] text-muted-foreground">{k}</div><div className="text-[10px]">+{eur(h.expected_collections)} / −{eur(h.expected_outflows)}</div><div className="font-mono-plex font-bold">{eur(h.projected_cash)}</div>{h.trigger_expected_collections > 0 && <div className="text-[9px] text-amber-700">+{eur(h.trigger_expected_collections)} potenziali</div>}</div>)}
        </div>
        {!inc && <div className="h-40"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}><XAxis dataKey="d" tick={{ fontSize: 9 }} /><YAxis tick={{ fontSize: 9 }} width={60} /><Tooltip formatter={(v) => eur(v)} /><ReferenceLine y={0} stroke="#dc2626" /><Area type="monotone" dataKey="cash" stroke="#0f766e" fill="#99f6e4" /></AreaChart></ResponsiveContainer></div>}
        <div className="text-[10px] text-muted-foreground" data-testid="ccc-stress">Scenario «cassa vuota» (nessuna vendita, incassi +7 gg, saldi trigger non pagati, fornitori non rinviabili): cassa 7 gg {eur(d.stress_scenario.cash_7d)} · 30 gg {eur(d.stress_scenario.cash_30d)} · minimo {d.stress_scenario.lowest_cash_point ? `${d.stress_scenario.lowest_cash_point.date} ${eur(d.stress_scenario.lowest_cash_point.amount)}` : "n/d"}</div>
      </Section>

      {/* C. DA INCASSARE */}
      <Section title={`C · Crediti e priorità di recupero (${d.collection_priority.length})`} testId="ccc-collect" open>
        <div className="flex flex-wrap gap-1 text-[10px]">{Object.entries(d.receivable_quality.by_status).map(([k, v]) => <Badge key={k} className={`rounded-sm ${COLOR[d.receivable_quality.colors[k]]}`} data-testid={`ccc-rq-${k}`}>{k} {eur(v)}</Badge>)}</div>
        {d.collection_priority.slice(0, 10).map((r, i) => <div key={`${r.payment_plan_id}-${r.installment_ref}-${i}`} className="flex justify-between items-center text-xs border-t py-1" data-testid="ccc-collect-row"><span><b>{r.customer_name}</b> <span className="text-muted-foreground">{r.contract_number || ""} {r.label || r.installment_ref}</span></span><span className="flex items-center gap-2"><span className="text-[10px]">{r.reason}</span><Badge className={`rounded-sm text-[9px] ${COLOR[r.color]}`}>{r.status}</Badge><span className="font-mono-plex font-bold w-24 text-right">{eur(r.amount)}</span></span></div>)}
        {!d.collection_priority.length && <div className="text-xs text-muted-foreground">Nessun credito aperto.</div>}
      </Section>

      {/* D. DA PAGARE */}
      <Section title={`D · Da pagare — debiti 7 gg ${eur(d.debt.ladder["7d"].total)} · 30 gg ${eur(d.debt.ladder["30d"].total)}`} testId="ccc-pay">
        <div className="grid grid-cols-5 gap-1 text-xs">{Object.entries(d.debt.ladder).map(([k, l]) => <div key={k} className="border rounded-sm p-2" data-testid={`ccc-ladder-${k}`}><div className="uppercase text-[10px] text-muted-foreground">entro {k}</div><div className="font-mono-plex font-bold">{eur(l.total)}</div><div className="text-[9px]">critici {eur(l.by_priority.CRITICAL)} · importanti {eur(l.by_priority.IMPORTANT)}</div></div>)}</div>
        {d.debt.due_30d.slice(0, 12).map((o) => <div key={o.id} className="flex justify-between text-xs border-t py-1" data-testid="ccc-pay-row"><span>{o.label} <Badge variant="outline" className="rounded-sm text-[9px] ml-1">{o.category}</Badge> <b className={`text-[9px] ${PRIO[o.priority]}`}>{o.priority}</b></span><span className="font-mono-plex">{eur(o.amount)} · {o.due_date}</span></div>)}
        {d.debt.unscheduled_total > 0 && <div className="text-[10px] text-amber-700">Debiti senza scadenza (fuori calendario): {eur(d.debt.unscheduled_total)}</div>}
        <div className="text-[10px] text-muted-foreground">Le priorità evidenziano, non decidono: nessun pagamento viene rinviato automaticamente.</div>
      </Section>

      {/* E. COMMESSE */}
      <Section title={`E · Commesse e crediti aperti (${d.jobs.soon.length} con scadenza/evento entro 30 gg) · cassa assorbita da commesse aperte ${eur(d.jobs.cash_absorbed_by_open_jobs)}`} testId="ccc-jobs">
        <table className="w-full text-xs"><thead><tr className="text-left text-[10px] uppercase text-muted-foreground"><th>Commessa</th><th className="text-right">Ordine</th><th className="text-right">Incassato</th><th className="text-right">Da incassare</th><th className="text-right">Pagato forn.</th><th className="text-right">Cash position</th><th className="text-right">Peak exposure</th><th>Scadenza / evento operativo</th></tr></thead><tbody>
          {d.jobs.rows.slice(0, 12).map((j) => <tr key={j.contract_id} className="border-t" data-testid="ccc-job-row"><td>{j.contract_number} <span className="text-muted-foreground">{j.order_status || ""}</span></td><td className="text-right font-mono-plex">{eur(j.order_value)}</td><td className="text-right font-mono-plex">{eur(j.collected)}</td><td className="text-right font-mono-plex">{eur(j.to_collect)}</td><td className="text-right font-mono-plex">{eur(j.supplier_paid)}</td><td className={`text-right font-mono-plex font-bold ${j.cash_position < 0 ? "text-red-700" : "text-emerald-700"}`}>{eur(j.cash_position)}</td><td className="text-right font-mono-plex">{eur(j.peak_cash_exposure)} {j.exposure_level && <Badge variant="outline" className="rounded-sm text-[9px]">{j.exposure_level}</Badge>}</td><td>{j.next_cash_event ? <span><Badge className={`rounded-sm text-[9px] ${COLOR[j.next_cash_event.color]}`}>{j.next_cash_event.status}</Badge> {eur(j.next_cash_event.amount)} · {j.next_cash_event.date}</span> : "—"}</td></tr>)}
        </tbody></table>
        <div className="text-[10px] text-muted-foreground">Capitale circolante netto: crediti {eur(d.working_capital.customer_receivables)} + WIP {eur(d.working_capital.work_in_progress_cash)} − debiti fornitori {eur(d.working_capital.supplier_payables)} = <b>{eur(d.working_capital.net_working_capital)}</b></div>
      </Section>

      {/* F. ALERT / NEXT ACTION */}
      <Section title={`F · Cosa devo fare oggi (${d.next_actions.length})`} testId="ccc-actions" open>
        {d.next_actions.map((a, i) => <div key={i} className={`text-xs py-1 border-t ${a.severity === "critical" ? "text-red-700 font-bold" : a.severity === "high" ? "text-amber-800" : ""}`} data-testid="ccc-action">→ {a.message}</div>)}
        {!d.next_actions.length && <div className="text-xs text-emerald-700">Nessuna azione urgente.</div>}
        <div className="text-[10px] text-muted-foreground">STRUTTURA COPERTA {d.structure.structure_coverage_percent ?? "—"}% ({d.structure.kpi_status}) ≠ CASH SAFE · costi fissi reali {eur(d.structure.annual_fixed_costs_real)} · EMAIL = {d.email_module}</div>
      </Section>
    </div>
  );
}
