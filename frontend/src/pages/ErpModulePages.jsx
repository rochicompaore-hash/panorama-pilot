/** Config-driven wrappers for the new ERP modules. Registered in App.js routes. */
import React from "react";
import ErpOpsPage from "./ErpOpsPage";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowClockwise, Sparkle } from "@phosphor-icons/react";
import { toast, Toaster } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_OPTS = (values) => values.map((v) => ({ value: v, label: v.replace(/_/g, " ") }));

// ------------------- M4: Surveys -------------------
export function SurveysPage() {
  return (<ErpOpsPage config={{
    title: "Rilievi tecnici", description: "Pianifica, esegui e approva rilievi tecnici. Le misure approvate diventano definitive.",
    endpoint: "surveys", testid: "surveys-page",
    columns: [
      { key: "number", label: "Numero" },
      { key: "customer_id", label: "Cliente" },
      { key: "technician_id", label: "Tecnico" },
      { key: "survey_status", label: "Stato", type: "status" },
      { key: "scheduled_at", label: "Pianificato", type: "date" },
    ],
    filters: [{ key: "survey_status", label: "Filtra stato",
      options: STATUS_OPTS(["draft","scheduled","in_progress","completed","approved","rejected","cancelled"]) }],
    createForm: {
      title: "Nuovo rilievo",
      fields: [
        { key: "customer_id", label: "Cliente (id)", required: true },
        { key: "quote_id", label: "Preventivo (id)" },
        { key: "scheduled_at", label: "Pianificato (ISO)", placeholder: "2026-08-01T09:00:00Z" },
      ],
    },
  }} />);
}

// ------------------- M5: Sales Orders -------------------
export function SalesOrdersPage() {
  return (<ErpOpsPage config={{
    title: "Ordini cliente", description: "Ordini esecutivi generati da preventivo firmato + rilievo approvato.",
    endpoint: "sales-orders", testid: "sales-orders-page",
    columns: [
      { key: "number", label: "Numero" },
      { key: "customer_id", label: "Cliente" },
      { key: "order_status", label: "Stato", type: "status" },
      { key: "total", label: "Totale", type: "money" },
      { key: "expected_installation_date", label: "Posa prevista", type: "date" },
    ],
    filters: [{ key: "order_status", label: "Filtra stato",
      options: STATUS_OPTS(["draft","confirmed","technically_validated","waiting_materials","ready_for_production","in_production","completed","ready_for_installation","installed","closed","cancelled"]) }],
    disableCreate: true,
  }} />);
}

// ------------------- M5: Suppliers -------------------
export function SuppliersPage() {
  return (<ErpOpsPage config={{
    title: "Fornitori", endpoint: "suppliers", testid: "suppliers-page",
    columns: [
      { key: "name", label: "Ragione sociale" },
      { key: "vat_number", label: "P.IVA" },
      { key: "email", label: "Email" },
      { key: "quality_rating", label: "Rating" },
      { key: "is_preferred", label: "Preferito", type: "bool" },
    ],
    createForm: {
      title: "Nuovo fornitore",
      fields: [
        { key: "name", label: "Ragione sociale", required: true },
        { key: "vat_number", label: "P.IVA" },
        { key: "email", label: "Email", type: "email" },
        { key: "phone", label: "Telefono" },
      ],
    },
  }} />);
}

// ------------------- M5: Purchase Orders -------------------
export function PurchaseOrdersPage() {
  return (<ErpOpsPage config={{
    title: "Ordini fornitore", endpoint: "purchase-orders", testid: "po-page",
    columns: [
      { key: "number", label: "Numero" },
      { key: "supplier_name", label: "Fornitore" },
      { key: "po_status", label: "Stato", type: "status" },
      { key: "total", label: "Totale", type: "money" },
      { key: "expected_delivery", label: "Consegna prevista", type: "date" },
    ],
    filters: [{ key: "po_status", label: "Filtra stato",
      options: STATUS_OPTS(["draft","requested","approved","sent","partially_received","received","delayed","disputed","cancelled"]) }],
    disableCreate: true,
  }} />);
}

// ------------------- M6: Items -------------------
export function ItemsPage() {
  return (<ErpOpsPage config={{
    title: "Articoli magazzino", endpoint: "items", testid: "items-page",
    columns: [
      { key: "code", label: "Codice" },
      { key: "name", label: "Nome" },
      { key: "category", label: "Categoria" },
      { key: "unit_of_measure", label: "UM" },
      { key: "min_stock", label: "Min stock" },
      { key: "is_bar", label: "Barra", type: "bool" },
    ],
    filters: [{ key: "category", label: "Filtra categoria",
      options: [{value:"profilo",label:"Profili"},{value:"ferramenta",label:"Ferramenta"},
                {value:"vetro",label:"Vetro"},{value:"accessorio",label:"Accessori"}] }],
    createForm: {
      title: "Nuovo articolo",
      fields: [
        { key: "code", label: "Codice", required: true },
        { key: "name", label: "Nome", required: true },
        { key: "category", label: "Categoria" },
        { key: "unit_of_measure", label: "UM (pz/m/m²)", placeholder: "pz" },
        { key: "min_stock", label: "Min stock", type: "number" },
      ],
    },
  }} />);
}

// ------------------- M7: Production Orders -------------------
export function ProductionOrdersPage() {
  return (<ErpOpsPage config={{
    title: "Ordini di produzione", endpoint: "production-orders", testid: "prod-orders-page",
    columns: [
      { key: "number", label: "Numero" },
      { key: "sales_order_id", label: "Ordine cliente" },
      { key: "prod_status", label: "Stato", type: "status" },
      { key: "priority", label: "Priorità" },
      { key: "scheduled_start", label: "Inizio previsto", type: "date" },
    ],
    filters: [{ key: "prod_status", label: "Filtra stato",
      options: STATUS_OPTS(["waiting_validation","waiting_materials","scheduled","released","in_progress","paused","blocked","quality_control","completed","packed","ready_for_dispatch","cancelled"]) }],
    disableCreate: true,
  }} />);
}

// ------------------- M9: QC -------------------
export function QCPage() {
  return (<ErpOpsPage config={{
    title: "Controllo qualità", description: "Checklist di controllo qualità sui prodotti.",
    endpoint: "qc-checks", testid: "qc-page",
    columns: [
      { key: "production_order_id", label: "OPR" },
      { key: "stage", label: "Fase" },
      { key: "passed", label: "Esito", type: "bool" },
      { key: "checked_at", label: "Controllato il", type: "date" },
    ],
    disableCreate: true,
  }} />);
}

// ------------------- M13: Service tickets -------------------
export function ServiceTicketsPage() {
  return (<ErpOpsPage config={{
    title: "Assistenza", endpoint: "service-tickets", testid: "tickets-page",
    columns: [
      { key: "number", label: "Numero" },
      { key: "subject", label: "Oggetto" },
      { key: "customer_id", label: "Cliente" },
      { key: "priority", label: "Priorità" },
      { key: "ticket_status", label: "Stato", type: "status" },
      { key: "created_at", label: "Aperto il", type: "date" },
    ],
    filters: [{ key: "ticket_status", label: "Stato",
      options: STATUS_OPTS(["opened","triaged","waiting_customer","waiting_material","scheduled","in_progress","resolved","closed","rejected"]) }],
    createForm: {
      title: "Nuovo ticket",
      fields: [
        { key: "customer_id", label: "Cliente (id)", required: true },
        { key: "subject", label: "Oggetto", required: true },
        { key: "description", label: "Descrizione" },
      ],
      defaults: { priority: "normal" },
    },
  }} />);
}

// ------------------- M11: Installation plans -------------------
export function InstallationPlansPage() {
  return (<ErpOpsPage config={{
    title: "Pianificazione posa", endpoint: "installation-plans", testid: "install-plans-page",
    columns: [
      { key: "number", label: "Numero" },
      { key: "sales_order_id", label: "Ordine" },
      { key: "scheduled_date", label: "Data", type: "date" },
      { key: "plan_status", label: "Stato", type: "status" },
    ],
    filters: [{ key: "plan_status", label: "Stato",
      options: STATUS_OPTS(["draft","proposed","customer_confirmed","scheduled","in_progress","completed","postponed","blocked_customer","blocked_materials","cancelled"]) }],
    disableCreate: true,
  }} />);
}

// ------------------- M14: Payment plans -------------------
export function PaymentPlansPage() {
  return (<ErpOpsPage config={{
    title: "Piani pagamenti", endpoint: "payment-plans", testid: "payment-plans-page",
    columns: [
      { key: "customer_id", label: "Cliente" },
      { key: "total_amount", label: "Totale", type: "money" },
      { key: "paid_amount", label: "Incassato", type: "money" },
      { key: "outstanding_amount", label: "Residuo", type: "money" },
      { key: "plan_status", label: "Stato", type: "status" },
    ],
    disableCreate: true,
  }} />);
}


// ------------------- M16/17: AI CFO + BI Dashboard -------------------
export function AICFOPage() {
  const [items, setItems] = React.useState([]);
  const [kpi, setKpi] = React.useState(null);
  const [qkpi, setQkpi] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const load = React.useCallback(async () => {
    try {
      const [s, dk, qk] = await Promise.all([
        axios.get(`${API}/api/ai-cfo/suggestions`),
        axios.get(`${API}/api/bi/direction/kpi`),
        axios.get(`${API}/api/bi/quotes/kpi?period_days=90`),
      ]);
      setItems(s.data.items || []);
      setKpi(dk.data); setQkpi(qk.data);
    } catch (e) { toast.error("Errore caricamento"); }
  }, []);
  React.useEffect(() => { load(); }, [load]);
  const generate = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/ai-cfo/generate`, {});
      toast.success(`Generati ${r.data.generated} suggerimenti`);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    finally { setBusy(false); }
  };
  const dismiss = async (sid) => {
    try { await axios.post(`${API}/api/ai-cfo/suggestions/${sid}/dismiss`); load(); }
    catch { toast.error("Errore"); }
  };

  return (
    <div className="space-y-6" data-testid="ai-cfo-page">
      <Toaster richColors />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-black tracking-tight">AI CFO & Business Intelligence</h1>
          <p className="text-sm text-muted-foreground">Suggerimenti prudenti basati esclusivamente sui dati reali del sistema. Ogni output cita le fonti e la logica.</p>
        </div>
        <Button onClick={generate} disabled={busy} className="rounded-sm" data-testid="ai-cfo-generate">
          {busy ? <ArrowClockwise size={16} className="animate-spin mr-2" /> : <Sparkle size={16} className="mr-2" />}
          Rigenera suggerimenti
        </Button>
      </div>

      {kpi && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Object.entries(kpi).map(([k, v]) => (
            <Card key={k} className="rounded-sm border-border p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{k.replace(/_/g, " ")}</div>
              <div className="mt-1 font-display text-2xl font-black">{v}</div>
            </Card>
          ))}
        </div>
      )}

      {qkpi && (
        <Card className="rounded-sm border-border p-4">
          <div className="overline mb-2">KPI Preventivi (ultimi {qkpi.period_days} giorni)</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <Stat label="Valore creato" value={new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(qkpi.value_created)} />
            <Stat label="Valore firmato" value={new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(qkpi.value_signed)} />
            <Stat label="Pipeline pesato" value={new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(qkpi.weighted_pipeline_value)} />
            <Stat label="Tasso conversione" value={`${qkpi.conversion_rate_pct}%`} />
            <Stat label="Ore medie a prima apertura" value={qkpi.avg_hours_to_first_open} />
            <Stat label="Ore medie a firma" value={qkpi.avg_hours_to_sign} />
            <Stat label="Mai visualizzati" value={qkpi.quotes_never_viewed} />
            <Stat label="In scadenza 7gg" value={qkpi.quotes_expiring_7d} />
          </div>
        </Card>
      )}

      <div>
        <div className="overline mb-2">Suggerimenti attivi</div>
        {items.length === 0 && (
          <Card className="rounded-sm border-border p-6 text-center text-sm text-muted-foreground" data-testid="no-suggestions">
            Nessun suggerimento attivo. Rigenera per calcolare nuove analisi.
          </Card>
        )}
        <div className="grid gap-3">
          {items.map((s) => (
            <Card key={s._id} className="rounded-sm border-border p-4">
              <div className="flex justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="outline" className="rounded-sm text-xs">{s.category}</Badge>
                    <Badge className={`rounded-sm text-xs ${s.risk_level === 'high' ? 'bg-red-600' : s.risk_level === 'medium' ? 'bg-amber-500' : 'bg-emerald-600'}`}>{s.risk_level}</Badge>
                    <span className="text-xs text-muted-foreground">Confidenza {(s.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="font-bold">{s.title}</div>
                  <p className="text-sm text-muted-foreground mt-1">{s.body}</p>
                  {s.action_suggested && (
                    <div className="mt-2 text-sm border-l-2 border-black pl-3">
                      <b>Azione suggerita:</b> {s.action_suggested}
                    </div>
                  )}
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    Fonti: {(s.data_sources || []).join(", ") || "—"} · Periodo: {s.period_from} → {s.period_to}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => dismiss(s._id)}>Archivia</Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (<div>
    <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
    <div className="font-mono-plex text-xl font-black">{value}</div>
  </div>);
}
