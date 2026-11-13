import React from "react";
import { Link } from "react-router-dom";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ArrowClockwise, DownloadSimple, ListChecks, WarningCircle, UserCircle, Clock } from "@phosphor-icons/react";

const id = (record) => record?.id || record?._id;
const date = (v) => v ? new Date(v).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "Da definire";
function localInput(value) {
  if (!value) return "";
  const d = new Date(value);
  if (!Number.isFinite(d.getTime())) return "";
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function errorText(error) {
  const detail = error.response?.data?.detail;
  return [formatApiError(detail || error.message), ...(detail?.missing || [])].join(" · ");
}
function Field({ label, children }) { return <label className="grid gap-1.5 text-sm font-medium">{label}{children}</label>; }
function Select(props) { return <select {...props} className="w-full rounded-md border bg-background p-2 text-sm disabled:opacity-50" />; }
function Alert({ children }) { return <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{children}</div>; }
function Pill({ danger, children }) { return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${danger ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-700"}`}>{children}</span>; }

export default function OperationsCenterPage() {
  const { has } = useAuth();
  const [schema, setSchema] = React.useState(null);
  const [people, setPeople] = React.useState([]);
  const [rows, setRows] = React.useState([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [attention, setAttention] = React.useState(false);
  const [busy, setBusy] = React.useState(true);
  const [error, setError] = React.useState("");
  const [selected, setSelected] = React.useState(null);
  const [creating, setCreating] = React.useState(false);
  const [tab, setTab] = React.useState("orders");
  const [exporting, setExporting] = React.useState(false);
  const load = React.useCallback(async () => {
    setBusy(true); setError("");
    try {
      const [data, rules, users] = await Promise.all([
        api.get("/operations/orders", { params: { q: query, status, skip: page * 50, limit: 50 } }),
        api.get("/operations/schema"), api.get("/operations/assignees"),
      ]);
      setRows(data.data.items); setTotal(data.data.total); setSchema(rules.data); setPeople(users.data);
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }, [query, status, page]);
  React.useEffect(() => { if (has("sales_orders.view")) load(); else setBusy(false); }, [load, has]);
  const exportFile = async (format) => {
    setExporting(true); setError("");
    try {
      const r = await api.get("/operations/export", { params: { format, q: query, status }, responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a");
      a.href = url; a.download = `commesse-${new Date().toISOString().slice(0, 10)}.${format}`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError("Esportazione non riuscita. Riprova o verifica l’accesso."); }
    finally { setExporting(false); }
  };
  if (!has("sales_orders.view")) return <Alert>Serve il permesso di visualizzazione ordini per aprire il centro operativo.</Alert>;
  const visible = attention ? rows.filter(r => r.control?.overdue || r.control?.unassigned || r.control?.blocked || r.control?.invalidated?.length) : rows;
  return <main className="space-y-6" data-testid="operations-center">
    <header className="flex flex-wrap justify-between items-start gap-4">
      <div><p className="text-xs uppercase tracking-widest text-muted-foreground">Dal contratto al completamento</p><h1 className="font-display text-3xl font-bold mt-1">Centro operativo</h1><p className="text-sm text-muted-foreground mt-2">Responsabili, prossime azioni e controlli sulle commesse esistenti.</p></div>
      <div className="flex gap-2 flex-wrap"><Button variant="outline" onClick={load} disabled={busy}><ArrowClockwise className="mr-2" />Aggiorna</Button>
        {has("sales_orders.create") && has("crm.customers.view") && <Button onClick={() => setCreating(true)}>Nuova commessa</Button>}</div>
    </header>
    <nav aria-label="Sezioni operative" className="flex gap-2 border-b pb-3"><Button variant={tab === "orders" ? "default" : "outline"} onClick={() => setTab("orders")}>Commesse</Button>{has("service.view") && <Button variant={tab === "service" ? "default" : "outline"} onClick={() => setTab("service")}>Assistenze</Button>}<Button variant="ghost" asChild><Link to="/calendar">Calendario</Link></Button></nav>
    {tab === "service" ? <ServiceBoard people={people} /> : <>
      <section className="grid grid-cols-2 xl:grid-cols-4 gap-3" aria-label="Indicatori della pagina">
        {[[ListChecks, "Commesse trovate", total], [Clock, "Scadute in pagina", rows.filter(r => r.control?.overdue).length], [UserCircle, "Senza incaricato in pagina", rows.filter(r => r.control?.unassigned).length], [WarningCircle, "Bloccate in pagina", rows.filter(r => r.control?.blocked).length]].map(([Icon, label, value]) => <Card key={label} className="p-4"><Icon className="text-muted-foreground" size={20}/><div className="text-2xl font-bold mt-3">{value}</div><p className="text-xs text-muted-foreground">{label}</p></Card>)}
      </section>
      <form className="flex flex-wrap items-center gap-2" onSubmit={e => { e.preventDefault(); setPage(0); setQuery(search); }}><Input aria-label="Cerca commesse" placeholder="Numero, prossima azione o blocco" value={search} onChange={e => setSearch(e.target.value)} className="max-w-sm"/><Button variant="outline" type="submit">Cerca</Button><div className="w-60"><Select aria-label="Fase" value={status} onChange={e => { setStatus(e.target.value); setPage(0); }}><option value="">Tutte le fasi</option>{Object.entries(schema?.states || {}).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></div></form>
      <div className="flex flex-wrap gap-3 items-center justify-between"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={attention} onChange={e => setAttention(e.target.checked)} />Solo criticità nella pagina</label><div className="flex gap-2"><Button size="sm" variant="outline" disabled={exporting} onClick={() => exportFile("csv")}><DownloadSimple className="mr-1" />CSV</Button><Button size="sm" variant="outline" disabled={exporting} onClick={() => exportFile("json")}>JSON completo</Button></div></div>
      <p className="text-xs text-muted-foreground">L’esportazione include tutte le commesse corrispondenti a ricerca e fase, oltre la pagina corrente. Il filtro criticità agisce solo sulla pagina.</p>
      {error && <Alert>{error}</Alert>}
      {busy ? <p role="status">Caricamento commesse…</p> : <div className="grid gap-3">{visible.map(row => <button type="button" key={id(row)} onClick={() => setSelected(id(row))} className="w-full rounded-xl border bg-card p-4 text-left hover:border-slate-500 focus-visible:ring-2 focus-visible:ring-ring" data-testid="order-card"><div className="flex flex-wrap justify-between gap-2"><strong>{row.number || id(row)}{row.customer_name ? ` · ${row.customer_name}` : ""}</strong><Pill>{row.control?.stage_label}</Pill></div><p className="mt-3 font-medium">{row.operational_next_action || "Assegna la prossima azione"}</p><div className="mt-3 flex flex-wrap gap-3 text-sm text-muted-foreground"><span>{people.find(p => p.id === row.operational_owner_id)?.name || "Senza incaricato"}</span><span>{date(row.operational_due_at)}</span></div><div className="flex flex-wrap gap-2 mt-3">{!row.control?.managed && <Pill>Da attivare</Pill>}{row.control?.overdue && <Pill danger>Scaduta</Pill>}{row.control?.blocked && <Pill danger>{row.operational_block}</Pill>}{!!row.control?.invalidated?.length && <Pill danger>Controlli da completare</Pill>}</div></button>)}{!visible.length && <Card className="p-8 text-center"><h2 className="font-semibold">Nessuna commessa in questa vista</h2><p className="mt-2 text-sm text-muted-foreground">Modifica i filtri oppure crea una commessa collegata a un cliente esistente.</p></Card>}</div>}
      <div className="flex items-center gap-3 justify-end"><Button variant="outline" disabled={!page || busy} onClick={() => setPage(p => p - 1)}>Precedente</Button><span className="text-sm">Pagina {page + 1} / {Math.max(1, Math.ceil(total / 50))}</span><Button variant="outline" disabled={(page + 1) * 50 >= total || busy} onClick={() => setPage(p => p + 1)}>Successiva</Button></div>
    </>}
    {selected && schema && <OrderDialog oid={selected} schema={schema} people={people} onClose={() => setSelected(null)} onSaved={load}/>}
    {creating && <NewOrder onClose={() => setCreating(false)} onSaved={oid => { setCreating(false); setSelected(oid); load(); }}/>} 
  </main>;
}

function OrderDialog({ oid, schema, people, onClose, onSaved }) {
  const { has } = useAuth();
  const [order, setOrder] = React.useState(null), [error, setError] = React.useState(""), [busy, setBusy] = React.useState(false);
  const [plan, setPlan] = React.useState({}), [finance, setFinance] = React.useState({}), [evidence, setEvidence] = React.useState({}), [reason, setReason] = React.useState("");
  const reload = React.useCallback(async () => {
    const r = await api.get(`/operations/orders/${oid}`); const o = r.data;
    setOrder(o); setPlan({ owner_id: o.operational_owner_id || "", next_action: o.operational_next_action || "", due_at: localInput(o.operational_due_at), block: o.operational_block || "", residuals: o.operational_residuals || 0 });
    setFinance({ payment_mode: o.payment_mode || "standard", financing_status: o.financing_status || "none", evidence: o.finance_evidence || "" });
  }, [oid]);
  React.useEffect(() => { reload().catch(e => setError(errorText(e))); }, [reload]);
  const mutate = async (path, method, data) => {
    setBusy(true); setError("");
    try { await api[method](path, data); await reload(); onSaved(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const closed = ["closed", "cancelled"].includes(order?.order_status);
  return <Dialog open onOpenChange={() => { if (!busy) onClose(); }}><DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto"><DialogHeader><DialogTitle>{order?.number || "Commessa"}</DialogTitle><DialogDescription>Ogni controllo conserva autore, data e riferimento dell’evidenza.</DialogDescription></DialogHeader>{error && <Alert>{error} <button className="underline ml-2" onClick={() => reload().catch(e => setError(errorText(e)))}>Ricarica</button></Alert>}{!order ? <p>Caricamento…</p> : <div className="space-y-7">
    <Pill>{schema.states[order.order_status] || order.order_status}</Pill>
    <form onSubmit={e => { e.preventDefault(); const due = new Date(new FormData(e.currentTarget).get("due_at")); if (!Number.isFinite(due.getTime())) { setError("Inserisci una scadenza valida."); return; } mutate(`/operations/orders/${oid}/plan`, "put", { ...plan, residuals: Number(plan.residuals), due_at: due.toISOString(), version: order.version || 0 }); }} className="space-y-3"><h2 className="font-semibold">Responsabilità e prossima azione</h2><fieldset disabled={busy || closed || !schema.can_plan} className="grid sm:grid-cols-2 gap-3"><Field label="Responsabile"><Select required value={plan.owner_id} onChange={e => setPlan({ ...plan, owner_id: e.target.value })}><option value="">Seleziona un incaricato</option>{people.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field><Field label="Scadenza"><Input required name="due_at" type="datetime-local" value={plan.due_at} onChange={e => setPlan({ ...plan, due_at: e.target.value })}/></Field><Field label="Prossima azione"><Input required maxLength={500} value={plan.next_action} onChange={e => setPlan({ ...plan, next_action: e.target.value })}/></Field><Field label="Blocco da risolvere"><Input maxLength={1000} value={plan.block} onChange={e => setPlan({ ...plan, block: e.target.value })} placeholder="Vuoto se non ci sono blocchi"/></Field><Field label="Completamenti ancora aperti"><Input type="number" min="0" max="10000" disabled={!has("installation.edit")} value={plan.residuals} onChange={e => setPlan({ ...plan, residuals: e.target.value })}/></Field><div className="flex items-end"><Button type="submit">{order.operational_enabled ? "Salva piano" : "Attiva procedura e salva"}</Button></div></fieldset></form>
    <form onSubmit={e => { e.preventDefault(); mutate(`/operations/orders/${oid}/finance`, "put", { ...finance, version: order.version || 0 }); }} className="space-y-3 border-t pt-5"><h2 className="font-semibold">Posizione finanziaria</h2><p className="text-xs text-muted-foreground">La firma non equivale all’accredito. Una variazione richiede una nuova verifica dei nulla osta amministrativi.</p><fieldset disabled={busy || closed || !schema.can_finance} className="grid sm:grid-cols-2 gap-3"><Field label="Pagamento"><Select value={finance.payment_mode} onChange={e => setFinance({ ...finance, payment_mode: e.target.value, financing_status: "none" })}><option value="standard">Ordinario</option><option value="financed">Finanziamento</option></Select></Field><Field label="Stato reale"><Select value={finance.financing_status} onChange={e => setFinance({ ...finance, financing_status: e.target.value })}>{Object.entries(schema.finance_states).map(([key, label]) => <option key={key} value={key} disabled={finance.payment_mode === "standard" && key !== "none"}>{label}</option>)}</Select></Field><Field label="Riscontro / documento"><Input minLength={5} maxLength={2000} required value={finance.evidence} onChange={e => setFinance({ ...finance, evidence: e.target.value })}/></Field><div className="flex items-end"><Button variant="outline" type="submit">Registra stato verificato</Button></div></fieldset></form>
    <section className="space-y-3 border-t pt-5"><h2 className="font-semibold">Controlli prima di proseguire</h2>{schema.checks.map(c => { const existing = order.operational_checks?.[c.key]; return <div key={c.key} className="rounded-lg border p-3"><div className="flex justify-between gap-3"><label htmlFor={`evidence-${c.key}`} className="text-sm font-medium">{c.label}</label><Pill danger={!existing?.satisfied}>{existing?.satisfied ? "Verificato" : "Da verificare"}</Pill></div>{existing && <p className="mt-2 text-xs text-muted-foreground">{existing.evidence} · {date(existing.at)}</p>}<div className="flex gap-2 mt-2"><Input id={`evidence-${c.key}`} aria-label={`Evidenza: ${c.label}`} placeholder="Documento, revisione o riscontro verificato" value={evidence[c.key] || ""} disabled={busy || closed || !c.can_edit || !order.operational_enabled} onChange={e => setEvidence({ ...evidence, [c.key]: e.target.value })}/><Button size="sm" variant="outline" disabled={busy || closed || !c.can_edit || !order.operational_enabled || (evidence[c.key] || "").trim().length < 5} onClick={() => mutate(`/operations/orders/${oid}/checks`, "post", { version: order.version || 0, key: c.key, satisfied: !existing?.satisfied, evidence: evidence[c.key] })}>{existing?.satisfied ? "Revoca" : "Conferma"}</Button></div></div>; })}</section>
    <section className="border-t pt-5 space-y-3"><h2 className="font-semibold">Passaggio successivo</h2>{!order.operational_enabled && <p className="text-sm">Attiva la procedura salvando responsabile, azione e scadenza.</p>}<Input aria-label="Nota sul passaggio" placeholder="Nota sul passaggio; motivo obbligatorio per annullare" value={reason} onChange={e => setReason(e.target.value)}/>{(order.transitions || []).map(t => <div key={t.status} className="flex flex-wrap justify-between items-center gap-3 rounded-lg bg-muted/30 p-3"><div><strong className="text-sm">{schema.states[t.status]}</strong>{!!t.missing.length && <ul className="text-xs text-red-800 list-disc ml-4 mt-1">{t.missing.map(m => <li key={m}>{m}</li>)}</ul>}</div><Button size="sm" disabled={busy || closed || !schema.can_plan || !order.operational_enabled || !!t.missing.length || (t.status === "cancelled" && reason.trim().length < 5)} onClick={() => mutate(`/sales-orders/${oid}/status`, "post", { order_status: t.status, expected_version: order.version || 0, reason })}>Passa a questa fase</Button></div>)}</section>
    <details className="border-t pt-4"><summary className="cursor-pointer text-sm font-semibold">Storico delle verifiche ({order.operational_history?.length || 0})</summary><ol className="mt-3 space-y-2">{[...(order.operational_history || [])].reverse().map((h, i) => <li key={i} className="text-xs border-b pb-2">{date(h.at)} · {people.find(p => p.id === h.actor_id)?.name || "Operatore"} · {h.event}</li>)}</ol></details>
  </div>}</DialogContent></Dialog>;
}

function NewOrder({ onClose, onSaved }) {
  const [customers, setCustomers] = React.useState([]), [q, setQ] = React.useState(""), [customer, setCustomer] = React.useState(""), [notes, setNotes] = React.useState(""), [busy, setBusy] = React.useState(false), [error, setError] = React.useState("");
  React.useEffect(() => { let active = true; const timer = setTimeout(() => api.get("/customers", { params: { q, limit: 50 } }).then(r => { if (active) setCustomers(r.data.items || []); }).catch(e => { if (active) setError(errorText(e)); }), 250); return () => { active = false; clearTimeout(timer); }; }, [q]);
  return <Dialog open onOpenChange={onClose}><DialogContent><DialogHeader><DialogTitle>Nuova commessa</DialogTitle><DialogDescription>Collega il lavoro a un cliente già presente. Le verifiche partiranno tutte da completare.</DialogDescription></DialogHeader>{error && <Alert>{error}</Alert>}<form className="space-y-4" onSubmit={async e => { e.preventDefault(); setBusy(true); try { const r = await api.post("/sales-orders", { customer_id: customer, notes }); onSaved(id(r.data)); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } }}><Field label="Cerca cliente"><Input value={q} onChange={e => setQ(e.target.value)}/></Field><Field label="Cliente"><Select required value={customer} onChange={e => setCustomer(e.target.value)}><option value="">Seleziona</option>{customers.map(c => <option key={id(c)} value={id(c)}>{c.display_name || c.company_name || c.name || [c.first_name, c.last_name].filter(Boolean).join(" ") || id(c)}</option>)}</Select></Field><Field label="Descrizione del lavoro"><Input value={notes} onChange={e => setNotes(e.target.value)}/></Field><Button disabled={busy || !customer} type="submit">Crea e assegna</Button></form></DialogContent></Dialog>;
}

function ServiceBoard({ people }) {
  const { has } = useAuth();
  const [rows, setRows] = React.useState([]), [page, setPage] = React.useState(0), [total, setTotal] = React.useState(0);
  const [error, setError] = React.useState(""), [busy, setBusy] = React.useState(false), [edit, setEdit] = React.useState(null);
  const [options, setOptions] = React.useState({ labels: {}, transitions: {} }), [resolution, setResolution] = React.useState(""), [creating, setCreating] = React.useState(false);
  const load = React.useCallback(async () => {
    setBusy(true); setError("");
    try {
      const [r, o] = await Promise.all([api.get("/service-tickets", { params: { skip: page * 50, limit: 50 } }), api.get("/service-tickets/options")]);
      setRows(r.data.items); setTotal(r.data.total); setOptions(o.data);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }, [page]);
  React.useEffect(() => { load(); }, [load]);
  const changeStatus = async (status) => {
    setBusy(true); setError("");
    try {
      await api.post(`/service-tickets/${id(edit)}/status`, { ticket_status: status, expected_version: edit.version || 0, resolution });
      setEdit(null); await load();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const terminal = ["closed", "resolved", "rejected"].includes(edit?.ticket_status);
  return <section className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Assistenze e tempi di intervento</h2>{has("service.create") && has("crm.customers.view") && <Button onClick={() => setCreating(true)}>Nuova assistenza</Button>}</div>
    <p className="text-sm text-muted-foreground">Rosso: 48 ore continuative · Arancione: 15 giorni · Verde: 30 giorni. Le attese non azzerano i termini. Se emerge un’urgenza rossa, valgono 48 ore dall’escalation o il termine precedente, se più vicino.</p>
    {error && !edit && <Alert>{error}</Alert>}{busy && <p role="status">Caricamento…</p>}
    {rows.map(t => <Card className="p-4 space-y-3" key={id(t)}>
      <div className="flex flex-wrap justify-between gap-3"><strong>{t.number} · {t.subject}</strong><Pill danger={t.service_clock?.color === "red" || t.service_clock?.overdue}>{({ red: "Rosso", orange: "Arancione", green: "Verde" })[t.service_clock?.color]}{t.service_clock?.overdue ? " · Scaduta" : ""}</Pill></div>
      <p className="text-sm">{options.labels[t.ticket_status]} · {t.next_action || "Prossima azione da assegnare"}</p>
      <p className="text-xs text-muted-foreground">Prima segnalazione: {date(t.service_clock?.first_reported_at)} · Termine: {date(t.service_clock?.due_at)} · {people.find(p => p.id === t.assigned_to)?.name || "Senza incaricato"}</p>
      {t.resolution && <p className="text-sm">Esito: {t.resolution}</p>}
      <Button size="sm" variant="outline" disabled={!has("service.edit") || ["closed", "rejected"].includes(t.ticket_status)} onClick={() => { setError(""); setResolution(""); setEdit({ ...t, priority: t.service_clock?.color || "orange" }); }}>Gestisci richiesta</Button>
    </Card>)}
    {!rows.length && !busy && <Card className="p-8 text-center">Nessuna assistenza presente.</Card>}
    <div className="flex gap-3 justify-end"><Button variant="outline" disabled={!page || busy} onClick={() => setPage(p => p - 1)}>Precedente</Button><span>{page + 1} / {Math.max(1, Math.ceil(total / 50))}</span><Button variant="outline" disabled={(page + 1) * 50 >= total || busy} onClick={() => setPage(p => p + 1)}>Successiva</Button></div>
    {creating && <NewTicket onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }}/>}
    {edit && <Dialog open onOpenChange={() => { if (!busy) setEdit(null); }}><DialogContent className="max-h-[92vh] overflow-y-auto"><DialogHeader><DialogTitle>{edit.subject}</DialogTitle><DialogDescription>La data della prima segnalazione resta invariata. Salva l’incarico prima di cambiare fase.</DialogDescription></DialogHeader>
      {error && <Alert>{error} <button className="underline" onClick={async () => { try { const r = await api.get(`/service-tickets/${id(edit)}`); setEdit({ ...r.data, priority: r.data.service_clock.color }); setError(""); } catch (e) { setError(errorText(e)); } }}>Ricarica richiesta</button></Alert>}
      <form className="space-y-4" onSubmit={async e => {
        e.preventDefault(); setBusy(true); setError("");
        try { const r = await api.patch(`/service-tickets/${id(edit)}`, { version: edit.version || 0, assigned_to: edit.assigned_to, priority: edit.priority, next_action: edit.next_action || "" }); setEdit({ ...r.data, priority: r.data.service_clock.color }); await load(); }
        catch (err) { setError(errorText(err)); } finally { setBusy(false); }
      }}><fieldset disabled={busy || terminal} className="space-y-4">
        <Field label="Incaricato"><Select required value={edit.assigned_to || ""} onChange={e => setEdit({ ...edit, assigned_to: e.target.value })}><option value="">Seleziona</option>{people.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
        <Field label="Priorità"><Select value={edit.priority} onChange={e => setEdit({ ...edit, priority: e.target.value })}><option value="red">Rosso · urgente</option><option value="orange">Arancione</option><option value="green">Verde</option></Select></Field>
        <Field label="Prossima azione"><Input required maxLength={500} value={edit.next_action || ""} onChange={e => setEdit({ ...edit, next_action: e.target.value })}/></Field><Button type="submit">Salva incarico</Button>
      </fieldset></form>
      <div className="space-y-3 border-t pt-4"><Field label="Esito dell’intervento / motivo"><Input value={resolution} onChange={e => setResolution(e.target.value)} placeholder="Obbligatorio per risolvere, chiudere o non accogliere"/></Field>
        <div className="flex flex-wrap gap-2">{(options.transitions[edit.ticket_status] || []).map(st => <Button key={st} variant="outline" size="sm" disabled={busy || (["resolved", "closed", "rejected"].includes(st) && resolution.trim().length < 5)} onClick={() => changeStatus(st)}>{options.labels[st]}</Button>)}</div>
      </div>
    </DialogContent></Dialog>}
  </section>;
}

function NewTicket({ onClose, onSaved }) {
  const [customers, setCustomers] = React.useState([]), [q, setQ] = React.useState(""), [busy, setBusy] = React.useState(false), [error, setError] = React.useState("");
  const [form, setForm] = React.useState({ customer_id: "", subject: "", description: "", priority: "orange", first_reported_at: localInput(new Date().toISOString()) });
  React.useEffect(() => { let active = true; const timer = setTimeout(() => api.get("/customers", { params: { q, limit: 50 } }).then(r => { if (active) setCustomers(r.data.items || []); }).catch(e => { if (active) setError(errorText(e)); }), 250); return () => { active = false; clearTimeout(timer); }; }, [q]);
  const update = (key, value) => setForm(f => ({ ...f, [key]: value }));
  return <Dialog open onOpenChange={() => { if (!busy) onClose(); }}><DialogContent><DialogHeader><DialogTitle>Nuova assistenza</DialogTitle><DialogDescription>I lavori rimasti da completare vanno registrati sulla commessa. Inserisci qui una nuova richiesta di assistenza.</DialogDescription></DialogHeader>
    {error && <Alert>{error}</Alert>}<form className="space-y-3" onSubmit={async e => { e.preventDefault(); const first = new Date(new FormData(e.currentTarget).get("first_reported_at")); if (!Number.isFinite(first.getTime())) { setError("Inserisci una data valida."); return; } setBusy(true); setError(""); try { await api.post("/service-tickets", { ...form, first_reported_at: first.toISOString() }); onSaved(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } }}>
      <Field label="Cerca cliente"><Input value={q} onChange={e => setQ(e.target.value)}/></Field>
      <Field label="Cliente"><Select required value={form.customer_id} onChange={e => update("customer_id", e.target.value)}><option value="">Seleziona</option>{customers.map(c => <option key={id(c)} value={id(c)}>{c.display_name || c.company_name || c.name || [c.first_name, c.last_name].filter(Boolean).join(" ") || id(c)}</option>)}</Select></Field>
      <Field label="Oggetto"><Input required value={form.subject} onChange={e => update("subject", e.target.value)}/></Field>
      <Field label="Problema segnalato"><Input required value={form.description} onChange={e => update("description", e.target.value)}/></Field>
      <Field label="Prima segnalazione effettiva"><Input required name="first_reported_at" type="datetime-local" value={form.first_reported_at} onChange={e => update("first_reported_at", e.target.value)}/></Field>
      <Field label="Priorità"><Select value={form.priority} onChange={e => update("priority", e.target.value)}><option value="red">Rosso · 48 ore</option><option value="orange">Arancione · 15 giorni</option><option value="green">Verde · 30 giorni</option></Select></Field>
      <Button type="submit" disabled={busy || !form.customer_id}>Apri richiesta</Button>
    </form>
  </DialogContent></Dialog>;
}
