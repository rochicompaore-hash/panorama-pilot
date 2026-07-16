import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Table, TableHead, TableRow, TableHeader, TableBody, TableCell } from "@/components/ui/table";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend, LineChart, Line, AreaChart, Area,
} from "recharts";
import { toast } from "sonner";
import { Warning, TrendUp, Money, Wallet, Buildings, Info } from "@phosphor-icons/react";

const COLORS = ["#D42027", "#0F1720", "#4B5563", "#94A3B8", "#F59E0B", "#10B981", "#3B82F6", "#8B5CF6"];

function KPI({ label, value, sub, testId, danger }) {
  return (
    <Card className="p-5" data-testid={testId}>
      <div className="overline text-muted-foreground">{label}</div>
      <div className={`text-2xl font-bold font-mono-plex mt-1 ${danger ? "text-red-600" : ""}`}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </Card>
  );
}

const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

export default function TreasuryCFOPage() {
  const [tab, setTab] = useState("overview");
  const [entities, setEntities] = useState([]);
  const [legalEntityFilter, setLegalEntityFilter] = useState("all");
  const [treasury, setTreasury] = useState(null);
  const [cfo, setCfo] = useState(null);
  const [consolidation, setConsolidation] = useState(null);
  const [intercompany, setIntercompany] = useState([]);
  const [payables, setPayables] = useState([]);
  const [fixed, setFixed] = useState([]);
  const [personnel, setPersonnel] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [icReport, setIcReport] = useState(null);
  const [insights, setInsights] = useState([]);
  const [f24, setF24] = useState([]);
  const [banks, setBanks] = useState([]);
  const [funds, setFunds] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [presets, setPresets] = useState(null);

  const load = async () => {
    try {
      const [ent, tr, cf, cons, ic, pay, fx, pe, sc, icr, ins, f24res, br, fu, al, pr] = await Promise.all([
        api.get("/legal-entities"),
        api.get("/treasury/dashboard"),
        api.get(`/control/dashboard${legalEntityFilter !== "all" ? "?legal_entity_id=" + legalEntityFilter : ""}`),
        api.get("/control/consolidation"),
        api.get("/intercompany"),
        api.get("/control/payables"),
        api.get("/control/fixed-costs"),
        api.get("/control/personnel-costs"),
        api.get("/control/budget/scenarios"),
        api.get("/intercompany/reconciliation-report"),
        api.get("/treasury/ai-cfo/insights"),
        api.get("/treasury/f24"),
        api.get("/treasury/bank-accounts"),
        api.get("/treasury/funds"),
        api.get("/treasury/alerts"),
        api.get("/control/budget/preset-scenarios"),
      ]);
      setEntities(ent.data.items || []);
      setTreasury(tr.data); setCfo(cf.data); setConsolidation(cons.data);
      setIntercompany(ic.data.items || []); setPayables(pay.data.items || []);
      setFixed(fx.data.items || []); setPersonnel(pe.data.items || []);
      setScenarios(sc.data.items || []); setIcReport(icr.data);
      setInsights(ins.data.items || []); setF24(f24res.data.items || []);
      setBanks(br.data.items || []); setFunds(fu.data.items || []);
      setAlerts(al.data.items || []); setPresets(pr.data);
    } catch (e) { console.error(e); toast.error("Errore caricamento CFO dashboard"); }
  };
  useEffect(() => { load(); }, [legalEntityFilter]);

  const runAiCfo = async () => {
    try {
      await api.post("/treasury/ai-cfo/run", { scope: "all" });
      toast.success("AI CFO analisi rigenerata");
      load();
    } catch { toast.error("Errore AI CFO"); }
  };

  return (
    <div className="space-y-6" data-testid="cfo-dashboard-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="overline text-muted-foreground">Controllo di Gestione + Tesoreria</div>
          <h1 className="font-display text-3xl font-black tracking-tight">Dashboard CFO</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Dati gestionali data-driven. NON sostituisce commercialista/revisore.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Label className="text-xs">Società</Label>
          <Select value={legalEntityFilter} onValueChange={setLegalEntityFilter}>
            <SelectTrigger className="w-56" data-testid="filter-legal-entity"><SelectValue/></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutte / Consolidato</SelectItem>
              {entities.map(e => <SelectItem key={e.id} value={e.id}>{e.code} — {e.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={runAiCfo} data-testid="btn-run-ai-cfo">
            <TrendUp size={16} className="mr-1"/>AI CFO
          </Button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPI label="Saldo banche" testId="kpi-bank-total"
             value={fmt(treasury?.availability?.bank_balance_total)}
             sub={`disponibile ${fmt(treasury?.availability?.available_balance)}`}/>
        <KPI label="Fondi virtuali" testId="kpi-funds-total"
             value={fmt(treasury?.funds?.total)}
             sub={`IVA ${fmt(treasury?.funds?.iva)}`}/>
        <KPI label="Struttura mensile" testId="kpi-structure-month"
             value={fmt(cfo?.totals?.structure_month)}
             sub={`annuo ${fmt(cfo?.totals?.structure_year)}`}/>
        <KPI label="Scadenziario debiti" testId="kpi-payables"
             value={fmt(cfo?.totals?.payables_residual)}
             sub={`${payables.length} scadenze`} danger={payables.some(p => p.payable_status === "overdue")}/>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex flex-wrap h-auto">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="banks" data-testid="tab-banks">Conti</TabsTrigger>
          <TabsTrigger value="funds" data-testid="tab-funds">Fondi</TabsTrigger>
          <TabsTrigger value="vat" data-testid="tab-vat">IVA/F24</TabsTrigger>
          <TabsTrigger value="payables" data-testid="tab-payables">Scadenziario</TabsTrigger>
          <TabsTrigger value="fixed" data-testid="tab-fixed">Costi fissi</TabsTrigger>
          <TabsTrigger value="personnel" data-testid="tab-personnel">Personale</TabsTrigger>
          <TabsTrigger value="budget" data-testid="tab-budget">Budget</TabsTrigger>
          <TabsTrigger value="breakeven" data-testid="tab-breakeven">Break-even</TabsTrigger>
          <TabsTrigger value="simulator" data-testid="tab-simulator">Simulazione</TabsTrigger>
          <TabsTrigger value="intercompany" data-testid="tab-intercompany">Intercompany</TabsTrigger>
          <TabsTrigger value="consolidated" data-testid="tab-consolidated">Consolidato</TabsTrigger>
          <TabsTrigger value="ai_cfo" data-testid="tab-ai-cfo">AI CFO</TabsTrigger>
          <TabsTrigger value="alerts" data-testid="tab-alerts">Alert</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <Card className="p-5">
              <div className="overline mb-3">Costi fissi per categoria</div>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={cfo?.fixed_by_category || []} dataKey="monthly" nameKey="category"
                       cx="50%" cy="50%" outerRadius={80} label={(x) => x.category}>
                    {(cfo?.fixed_by_category || []).map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]}/>
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => fmt(v)}/>
                </PieChart>
              </ResponsiveContainer>
            </Card>
            <Card className="p-5">
              <div className="overline mb-3">Personale per reparto</div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={cfo?.personnel_by_department || []}>
                  <CartesianGrid strokeDasharray="3 3"/>
                  <XAxis dataKey="department"/>
                  <YAxis tickFormatter={(v) => (v/1000)+"k"}/>
                  <Tooltip formatter={(v) => fmt(v)}/>
                  <Bar dataKey="monthly" fill="#0F1720"/>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="banks">
          <Card className="p-5">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Codice</TableHead><TableHead>Banca</TableHead><TableHead>IBAN</TableHead>
                <TableHead>Tipo</TableHead><TableHead className="text-right">Contabile</TableHead>
                <TableHead className="text-right">Disponibile</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {banks.map(b => (
                  <TableRow key={b.id} data-testid={`bank-row-${b.code}`}>
                    <TableCell className="font-mono">{b.code}</TableCell>
                    <TableCell>{b.bank_name}</TableCell>
                    <TableCell className="font-mono text-xs">{b.iban_masked}</TableCell>
                    <TableCell><Badge variant="outline">{b.kind}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{fmt(b.contabile_balance)}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(b.available_balance)}</TableCell>
                  </TableRow>
                ))}
                {banks.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Nessun conto configurato</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="funds">
          <Card className="p-5">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={funds.map(f => ({name: f.code, target: f.target_pct, current: f.current_balance}))}>
                <CartesianGrid strokeDasharray="3 3"/>
                <XAxis dataKey="name"/>
                <YAxis/>
                <Tooltip formatter={(v) => fmt(v)}/>
                <Legend/>
                <Bar dataKey="current" fill="#D42027" name="Saldo attuale"/>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </TabsContent>

        <TabsContent value="vat">
          <div className="grid md:grid-cols-2 gap-4">
            <Card className="p-5">
              <div className="overline mb-3">Ultimo periodo IVA</div>
              {treasury?.vat?.last_closing_period ? (
                <div>
                  <div className="text-3xl font-bold font-mono-plex">{fmt(treasury.vat.last_closing_net_vat)}</div>
                  <div className="text-xs text-muted-foreground">Periodo: {treasury.vat.last_closing_period}</div>
                  <Badge className="mt-2" variant={treasury.vat.last_closing_is_credit ? "default" : "outline"}>
                    {treasury.vat.last_closing_is_credit ? "CREDITO" : "A DEBITO"}
                  </Badge>
                </div>
              ) : <div className="text-muted-foreground text-sm">Nessuna chiusura IVA registrata</div>}
            </Card>
            <Card className="p-5">
              <div className="overline mb-3">F24 in scadenza</div>
              {f24.length === 0 && <div className="text-muted-foreground text-sm">Nessun F24 pianificato</div>}
              {f24.slice(0, 5).map(f => (
                <div key={f.id} className="flex items-center justify-between py-1 border-b">
                  <div>
                    <div className="text-sm font-medium">{f.tribute_code}</div>
                    <div className="text-xs text-muted-foreground">{f.due_date}</div>
                  </div>
                  <div className="font-mono">{fmt(f.net_amount)}</div>
                </div>
              ))}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="payables">
          <Card className="p-5">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Creditore</TableHead><TableHead>Rif</TableHead>
                <TableHead>Scadenza</TableHead><TableHead>Stato</TableHead>
                <TableHead className="text-right">Importo</TableHead>
                <TableHead className="text-right">Residuo</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {payables.map(p => (
                  <TableRow key={p.id} data-testid={`payable-row-${p.id}`}>
                    <TableCell>{p.creditor}</TableCell>
                    <TableCell className="font-mono text-xs">{p.doc_ref || "—"}</TableCell>
                    <TableCell>{p.due_date}</TableCell>
                    <TableCell><Badge>{p.payable_status}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{fmt(p.amount_gross)}</TableCell>
                    <TableCell className="text-right font-mono font-bold">{fmt(p.residual)}</TableCell>
                  </TableRow>
                ))}
                {payables.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Nessuno scadenziario</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="fixed">
          <Card className="p-5">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Voce</TableHead><TableHead>Categoria</TableHead>
                <TableHead>Ricorrenza</TableHead>
                <TableHead className="text-right">Importo (raw)</TableHead>
                <TableHead className="text-right">Mensile</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {fixed.map(f => (
                  <TableRow key={f.id} data-testid={`fixed-row-${f.id}`}>
                    <TableCell>{f.label}</TableCell>
                    <TableCell><Badge variant="outline">{f.category}</Badge></TableCell>
                    <TableCell>{f.recurrence}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(f.amount_raw)}</TableCell>
                    <TableCell className="text-right font-mono font-bold">{fmt(f.amount_monthly)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="personnel">
          <Card className="p-5">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Nome</TableHead><TableHead>Ruolo</TableHead>
                <TableHead>Reparto</TableHead>
                <TableHead className="text-right">RAL</TableHead>
                <TableHead className="text-right">Costo mensile</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {personnel.map(p => (
                  <TableRow key={p.id} data-testid={`personnel-row-${p.id}`}>
                    <TableCell>{p.full_name}</TableCell>
                    <TableCell>{p.role || "—"}</TableCell>
                    <TableCell><Badge variant="outline">{p.department || "—"}</Badge></TableCell>
                    <TableCell className="text-right font-mono">{fmt(p.ral_yearly)}</TableCell>
                    <TableCell className="text-right font-mono font-bold">{fmt(p.monthly_total_cost)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="budget">
          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="overline">Scenari budget salvati</div>
              <div className="text-xs text-muted-foreground">{scenarios.length} scenari</div>
            </div>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Etichetta</TableHead><TableHead>Anno</TableHead>
                <TableHead>Tipo</TableHead><TableHead>Approvato</TableHead>
                <TableHead className="text-right">Ricavo previsto</TableHead>
                <TableHead className="text-right">EBITDA</TableHead>
                <TableHead className="text-right">Break-even</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {scenarios.map(s => (
                  <TableRow key={s.id} data-testid={`scenario-row-${s.id}`}>
                    <TableCell>{s.label}</TableCell>
                    <TableCell>{s.year}</TableCell>
                    <TableCell><Badge>{s.scenario_kind}</Badge></TableCell>
                    <TableCell>{s.approved ? "✅" : "—"}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(s.outputs?.forecast_revenue)}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(s.outputs?.ebitda)}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(s.outputs?.break_even_revenue)}</TableCell>
                  </TableRow>
                ))}
                {scenarios.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-6">
                  Nessuno scenario. Vai su "Simulazione" per crearne uno.
                </TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="breakeven">
          <BreakEvenView presets={presets} scenarios={scenarios} onSaved={load}/>
        </TabsContent>

        <TabsContent value="simulator">
          <SimulatorView presets={presets} onSaved={load}/>
        </TabsContent>

        <TabsContent value="intercompany">
          <IntercompanyView items={intercompany} report={icReport} entities={entities} onReload={load}/>
        </TabsContent>

        <TabsContent value="consolidated">
          <ConsolidationView data={consolidation}/>
        </TabsContent>

        <TabsContent value="ai_cfo" className="space-y-3">
          {insights.length === 0 && <Card className="p-6 text-center text-muted-foreground">
            <Info size={22} className="mx-auto mb-2"/>
            Nessun suggerimento generato. Clicca "AI CFO" in alto per rigenerare.
          </Card>}
          {insights.map(i => (
            <Card key={i.id} className="p-4" data-testid={`insight-${i.id}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-medium">{i.title}</div>
                  <div className="text-sm text-muted-foreground mt-1">{i.body}</div>
                  {i.formula && <div className="text-[11px] font-mono mt-2 text-muted-foreground">↳ {i.formula}</div>}
                  {(i.data_sources || []).length > 0 && (
                    <div className="text-[11px] text-muted-foreground mt-1">
                      Fonti: {i.data_sources.map(s => s.kind).join(", ")}
                    </div>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge>{i.risk_level}</Badge>
                  <div className="text-xs font-mono">conf {Math.round((i.confidence||0)*100)}%</div>
                </div>
              </div>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="alerts" className="space-y-3">
          {alerts.length === 0 && <Card className="p-6 text-center text-muted-foreground">Nessun alert attivo</Card>}
          {alerts.map(a => (
            <Alert key={a.id} variant={a.severity === "high" || a.severity === "critical" ? "destructive" : "default"}>
              <Warning size={16}/>
              <div>
                <div className="font-medium">{a.title}</div>
                <AlertDescription>{a.body}</AlertDescription>
              </div>
            </Alert>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}


function BreakEvenView({ scenarios }) {
  const last = scenarios[0];
  if (!last) return <Card className="p-6 text-center text-muted-foreground">Nessuno scenario salvato — usa il Simulatore per crearne uno.</Card>;
  const wf = last.outputs?.waterfall || [];
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="p-5">
        <div className="overline mb-3">Waterfall break-even — {last.label}</div>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={wf}>
            <CartesianGrid strokeDasharray="3 3"/>
            <XAxis dataKey="label" fontSize={10} angle={-15} textAnchor="end" height={60}/>
            <YAxis tickFormatter={(v) => (v/1000)+"k"}/>
            <Tooltip formatter={(v) => fmt(v)}/>
            <Bar dataKey="value">
              {wf.map((e, i) => (
                <Cell key={i} fill={e.kind === "negative" ? "#D42027" : e.kind === "subtotal" ? "#0F1720" : "#10B981"}/>
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <Card className="p-5">
        <div className="overline mb-3">Confronto tre scenari</div>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={[
            {name: "Pareggio", value: last.outputs?.break_even_revenue || 0},
            {name: "Stabilità", value: last.outputs?.stability_revenue || 0},
            {name: "Crescita", value: last.outputs?.growth_revenue || 0},
          ]}>
            <CartesianGrid strokeDasharray="3 3"/>
            <XAxis dataKey="name"/>
            <YAxis tickFormatter={(v) => (v/1000)+"k"}/>
            <Tooltip formatter={(v) => fmt(v)}/>
            <Bar dataKey="value" fill="#D42027"/>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}


function SimulatorView({ presets, onSaved }) {
  const [inputs, setInputs] = useState({
    yearly_revenue: 800000, average_ticket: 6500, close_rate_pct: 25,
    material_cost_pct: 42, installation_cost_pct: 8,
    personnel_cost_yearly: 180000, fixed_costs_yearly: 90000,
    energy_yearly: 12000, marketing_yearly: 20000, investments_yearly: 15000,
    new_hires_cost_yearly: 0, leasing_yearly: 0,
    target_profit: 60000, tax_rate: 27, vat_rate: 22,
    fund_pct_vat: 20, fund_pct_contingency: 10, fund_pct_investments: 10, fund_pct_urgent: 5,
    production_capacity_pct: 100, price_pct_change: 0,
    collection_days: 60, payment_days: 60,
  });
  const [outputs, setOutputs] = useState(null);
  const [label, setLabel] = useState("Scenario custom");
  const [scenarioKind, setScenarioKind] = useState("custom");

  const applyPreset = (kind) => {
    if (!presets?.[kind]) return;
    setInputs({...inputs, ...presets[kind]});
    setScenarioKind(kind);
    setLabel(`Scenario ${kind}`);
  };

  const simulate = async (save = false) => {
    try {
      const { data } = await api.post("/control/budget/simulate", {
        year: new Date().getFullYear(), inputs, save_as_scenario: save,
        label, scenario_kind: scenarioKind,
      });
      setOutputs(data.outputs);
      if (save) { toast.success("Scenario salvato"); onSaved && onSaved(); }
    } catch (e) { toast.error("Errore simulazione"); }
  };

  useEffect(() => { simulate(false); }, []); // initial

  const FIELDS = [
    { k: "yearly_revenue", l: "Fatturato annuo (€)" },
    { k: "average_ticket", l: "Ticket medio (€)" },
    { k: "close_rate_pct", l: "Tasso chiusura (%)" },
    { k: "material_cost_pct", l: "Costo materiali (%)" },
    { k: "installation_cost_pct", l: "Costo posa (%)" },
    { k: "personnel_cost_yearly", l: "Personale annuo (€)" },
    { k: "fixed_costs_yearly", l: "Costi fissi annui (€)" },
    { k: "energy_yearly", l: "Energia annua (€)" },
    { k: "marketing_yearly", l: "Marketing (€)" },
    { k: "investments_yearly", l: "Investimenti (€)" },
    { k: "new_hires_cost_yearly", l: "Nuove assunzioni (€)" },
    { k: "leasing_yearly", l: "Leasing (€)" },
    { k: "target_profit", l: "Utile obiettivo (€)" },
    { k: "price_pct_change", l: "Variazione prezzi (%)" },
    { k: "collection_days", l: "Giorni incasso" },
    { k: "payment_days", l: "Giorni pagamento" },
    { k: "vat_rate", l: "Aliquota IVA (%)" },
    { k: "tax_rate", l: "Aliquota imposte (%)" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => applyPreset("base")} data-testid="preset-base">Preset Base</Button>
        <Button variant="outline" onClick={() => applyPreset("prudent")} data-testid="preset-prudent">Preset Prudente</Button>
        <Button variant="outline" onClick={() => applyPreset("growth")} data-testid="preset-growth">Preset Crescita</Button>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="overline mb-3">Variabili what-if</div>
          <div className="grid grid-cols-2 gap-3 max-h-[500px] overflow-y-auto pr-2">
            {FIELDS.map(f => (
              <div key={f.k}>
                <Label className="text-xs">{f.l}</Label>
                <Input type="number" value={inputs[f.k]}
                       onChange={e => setInputs({...inputs, [f.k]: Number(e.target.value)})}
                       data-testid={`sim-input-${f.k}`}/>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-4">
            <Button onClick={() => simulate(false)} data-testid="btn-simulate">Simula</Button>
            <Input value={label} onChange={e => setLabel(e.target.value)} placeholder="Nome scenario" className="max-w-xs"/>
            <Button variant="outline" onClick={() => simulate(true)} data-testid="btn-save-scenario">Salva scenario</Button>
          </div>
        </Card>
        <Card className="p-5">
          <div className="overline mb-3">Risultati simulazione</div>
          {outputs && (
            <div className="space-y-2 text-sm">
              <ResultRow label="Fatturato previsto" value={fmt(outputs.forecast_revenue)} highlight/>
              <ResultRow label="Margine di contribuzione" value={`${fmt(outputs.contribution_margin)} (${outputs.contribution_margin_pct}%)`}/>
              <ResultRow label="EBITDA gestionale" value={fmt(outputs.ebitda)} highlight/>
              <ResultRow label="Break-even" value={fmt(outputs.break_even_revenue)}/>
              <ResultRow label="Stabilità" value={fmt(outputs.stability_revenue)}/>
              <ResultRow label="Crescita" value={fmt(outputs.growth_revenue)}/>
              <ResultRow label="Cash flow annuo" value={fmt(outputs.cash_flow_yearly)}/>
              <ResultRow label="Liquidità minima" value={fmt(outputs.liquidity_min)}/>
              <ResultRow label="Runway" value={`${outputs.cash_runway_months} mesi`}/>
              <ResultRow label="Contratti necessari" value={outputs.contracts_needed}/>
              <ResultRow label="Appuntamenti" value={outputs.appointments_needed}/>
              <ResultRow label="Lead necessari" value={outputs.leads_needed}/>
              <ResultRow label="Capacità utilizzata" value={`${outputs.capacity_used_pct}%`}/>
              <ResultRow label="ROI investimenti" value={`${outputs.roi_pct}%`}/>
              <ResultRow label="Payback" value={`${outputs.payback_months} mesi`}/>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function ResultRow({ label, value, highlight }) {
  return (
    <div className={`flex justify-between py-1 border-b ${highlight ? "font-bold text-base" : ""}`}>
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}


function IntercompanyView({ items, report, entities, onReload }) {
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({});

  const create = async () => {
    try {
      await api.post("/intercompany", form);
      toast.success("Operazione intercompany creata (mirroring automatico)");
      setShowNew(false);
      setForm({});
      onReload && onReload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
  };

  const reconcile = async (pair_id, action) => {
    try {
      await api.post("/intercompany/reconcile", { pair_id, action });
      toast.success(`Azione ${action} completata`);
      onReload && onReload();
    } catch (e) { toast.error("Errore riconciliazione"); }
  };

  const grouped = {};
  items.forEach(it => {
    if (!grouped[it.intercompany_pair_id]) grouped[it.intercompany_pair_id] = [];
    grouped[it.intercompany_pair_id].push(it);
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="overline text-muted-foreground">Riconciliazione</div>
          <div className="text-sm">
            {report?.total_pairs || 0} coppie · {report?.reconciled || 0} riconciliate · {report?.issue_count || 0} incoerenze
          </div>
        </div>
        <Dialog open={showNew} onOpenChange={setShowNew}>
          <DialogTrigger asChild>
            <Button data-testid="btn-new-intercompany">Nuova operazione IC</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Nuova operazione intercompany</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div><Label>Società venditrice (source)</Label>
                <Select value={form.source_legal_entity_id || ""} onValueChange={v => setForm({...form, source_legal_entity_id: v})}>
                  <SelectTrigger data-testid="ic-source"><SelectValue/></SelectTrigger>
                  <SelectContent>{entities.map(e => <SelectItem key={e.id} value={e.id}>{e.code}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Società acquirente (target)</Label>
                <Select value={form.target_legal_entity_id || ""} onValueChange={v => setForm({...form, target_legal_entity_id: v})}>
                  <SelectTrigger data-testid="ic-target"><SelectValue/></SelectTrigger>
                  <SelectContent>{entities.map(e => <SelectItem key={e.id} value={e.id}>{e.code}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div><Label>Riferimento documento</Label>
                <Input value={form.doc_ref || ""} onChange={e => setForm({...form, doc_ref: e.target.value})} data-testid="ic-ref"/>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Imponibile</Label>
                  <Input type="number" value={form.amount_taxable || ""} onChange={e => setForm({...form, amount_taxable: Number(e.target.value)})} data-testid="ic-amount"/>
                </div>
                <div><Label>Aliquota IVA %</Label>
                  <Input type="number" value={form.vat_rate || 22} onChange={e => setForm({...form, vat_rate: Number(e.target.value)})}/>
                </div>
              </div>
              <div><Label>Scadenza</Label>
                <Input type="date" value={form.due_date || ""} onChange={e => setForm({...form, due_date: e.target.value})}/>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={create} data-testid="btn-save-intercompany">Crea coppia mirrorata</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
      <Card className="p-5">
        <Table>
          <TableHeader><TableRow>
            <TableHead>Pair ID</TableHead><TableHead>Documento</TableHead>
            <TableHead>Da → A</TableHead><TableHead>Importo</TableHead>
            <TableHead>IVA</TableHead><TableHead>Stato</TableHead><TableHead>Azioni</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {Object.entries(grouped).map(([pid, pair]) => {
              const s = pair.find(x => x.side === "source"); const t = pair.find(x => x.side === "target");
              const src = entities.find(e => e.id === s?.source_legal_entity_id)?.code || "?";
              const tgt = entities.find(e => e.id === s?.target_legal_entity_id)?.code || "?";
              return (
                <TableRow key={pid} data-testid={`ic-pair-${pid}`}>
                  <TableCell className="font-mono text-xs">{pid.substring(0, 8)}</TableCell>
                  <TableCell>{s?.doc_ref || "—"}</TableCell>
                  <TableCell>{src} → {tgt}</TableCell>
                  <TableCell className="font-mono">{fmt(s?.amount_gross)}</TableCell>
                  <TableCell className="font-mono">{fmt(s?.vat_amount)}</TableCell>
                  <TableCell><Badge>{s?.ic_status}</Badge></TableCell>
                  <TableCell className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={() => reconcile(pid, "confirm")} data-testid={`btn-confirm-${pid}`}>Conferma</Button>
                    <Button size="sm" variant="outline" onClick={() => reconcile(pid, "reverse")} data-testid={`btn-reverse-${pid}`}>Storna</Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {items.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-6">Nessuna operazione intercompany</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}


function ConsolidationView({ data }) {
  if (!data) return null;
  const chart = data.entities.map(e => ({name: e.code, revenue: e.revenue}));
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="p-5">
        <div className="overline mb-3">Ricavi per società</div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chart}>
            <CartesianGrid strokeDasharray="3 3"/>
            <XAxis dataKey="name"/>
            <YAxis tickFormatter={(v) => (v/1000)+"k"}/>
            <Tooltip formatter={(v) => fmt(v)}/>
            <Bar dataKey="revenue" fill="#0F1720"/>
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <Card className="p-5">
        <div className="overline mb-3">Consolidamento</div>
        <div className="space-y-2 text-sm">
          <ResultRow label="Totale lordo" value={fmt(data.gross_totals.revenue)}/>
          <ResultRow label="Eliminazioni IC" value={fmt(-(data.eliminations.intercompany_revenue || 0))}/>
          <ResultRow label="Consolidato" value={fmt(data.consolidated.revenue)} highlight/>
          <div className="text-xs text-muted-foreground mt-2">
            Coppie eliminate: {data.eliminations.intercompany_pairs_count}
          </div>
          <Alert className="mt-3"><Info size={14}/><AlertDescription className="text-xs">{data.notes}</AlertDescription></Alert>
        </div>
      </Card>
    </div>
  );
}
