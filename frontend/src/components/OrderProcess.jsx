import React from "react";
import { api, formatApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

const date = value => value ? new Date(value).toLocaleString("it-IT") : "Da assegnare";
const errorText = e => formatApiError(e.response?.data?.detail || e.message);
const states = { pending: "Da prendere in carico", in_progress: "In lavorazione", blocked: "Bloccata", completed: "Conclusa", cancelled: "Annullata" };
const events = { started: "Procedura avviata", assigned: "Incarico aggiornato", accept: "Presa in carico", complete: "Attività conclusa e consegnata", block: "Blocco segnalato", resume: "Blocco risolto", return: "Rinviata per nuova verifica", cancel: "Commessa annullata" };
function Select(props) { return <select {...props} className="w-full rounded-md border bg-background p-2 text-sm" />; }
function localDate(value) {
  if (!value) return "";
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function PersonOptions({ schema, step }) {
  return <><option value="">Seleziona un incaricato abilitato</option>{Object.entries(schema.candidates || {}).filter(([, p]) => p.steps.includes(step)).map(([id, p]) => <option key={id} value={id}>{p.name}</option>)}</>;
}

export function ProcessInbox({ onOpen, refreshToken }) {
  const [schema, setSchema] = React.useState(null), [rows, setRows] = React.useState([]), [total, setTotal] = React.useState(0);
  const [area, setArea] = React.useState(""), [mine, setMine] = React.useState(false), [attention, setAttention] = React.useState(false), [page, setPage] = React.useState(0);
  const [error, setError] = React.useState(""), [busy, setBusy] = React.useState(true);
  const load = React.useCallback(async () => {
    setBusy(true); setError("");
    try {
      const [s, r] = await Promise.all([api.get("/operations/process/schema"), api.get("/operations/process/inbox", { params: { area, mine, attention, skip: page * 50 } })]);
      setSchema(s.data); setRows(r.data.items); setTotal(r.data.total);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }, [area, mine, attention, page]);
  React.useEffect(() => { load(); }, [load, refreshToken]);
  return <section className="space-y-4" aria-label="Attività dei reparti">
    <div className="flex justify-between gap-3"><div><h2 className="text-xl font-semibold">Attività da lavorare</h2><p className="text-sm text-muted-foreground mt-1">Concludere un’attività consegna il lavoro al reparto successivo. Ogni passaggio resta nello storico.</p></div><Button variant="outline" onClick={load} disabled={busy}>Aggiorna attività</Button></div>
    <div className="flex flex-wrap items-center gap-4"><div className="w-64"><Select aria-label="Reparto" value={area} onChange={e => { setArea(e.target.value); setPage(0); }}><option value="">Tutti i reparti</option>{Object.entries(schema?.areas || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></div>
      <label className="text-sm flex gap-2"><input type="checkbox" checked={mine} onChange={e => { setMine(e.target.checked); setPage(0); }}/>Solo le mie</label>
      <label className="text-sm flex gap-2"><input type="checkbox" checked={attention} onChange={e => { setAttention(e.target.checked); setPage(0); }}/>Da assegnare, bloccate o scadute</label>
    </div>
    {error && <p role="alert" className="text-red-800">{error}</p>}
    <p className="text-sm text-muted-foreground">{total} attività corrispondenti ai filtri · pagina {page + 1}</p>
    {busy ? <p role="status">Caricamento attività…</p> : rows.map(row => {
      const t = row.task;
      const overdue = t.due_at && new Date(t.due_at) < new Date();
      return <button type="button" key={row.id} onClick={() => onOpen(row.id)} className="block w-full text-left rounded-xl border p-4 bg-card hover:border-slate-500 focus-visible:ring-2">
        <div className="flex justify-between gap-3 flex-wrap"><strong>{row.number || row.id} · {row.customer_name}</strong><span className="text-xs rounded-full px-3 py-1 bg-slate-100">{schema?.areas[t.area]} · {states[t.status]}</span></div>
        <p className="font-medium mt-3">{t.label}</p>
        <p className={`text-sm mt-2 ${overdue ? "text-red-800" : "text-muted-foreground"}`}>{schema?.candidates[t.owner_id]?.name || (t.owner_id ? "Incaricato da verificare" : "Direzione: assegnare incaricato")} · {overdue ? "Scaduta: " : "Scadenza: "}{date(t.due_at)}</p>
        {(!t.owner_id || !t.due_at) && <p className="text-sm text-amber-800 mt-2">Il lavoro è in coda; assegnare persona e termine prima della presa in carico.</p>}
        {t.block && <p className="text-sm text-red-800 mt-2">Blocco: {t.block}</p>}
      </button>;
    })}
    {!busy && !rows.length && <Card className="p-6"><p>Nessuna attività in questa vista.</p><p className="text-sm text-muted-foreground mt-2">Le nuove commesse entrano automaticamente. Per quelle pregresse, apri la scheda in Commesse e avvia la procedura.</p></Card>}
    <div className="flex justify-end gap-3"><Button variant="outline" disabled={!page || busy} onClick={() => setPage(p => p - 1)}>Precedente</Button><Button variant="outline" disabled={(page + 1) * 50 >= total || busy} onClick={() => setPage(p => p + 1)}>Successiva</Button></div>
    {schema?.can_assign && <details className="border-t pt-4"><summary className="cursor-pointer font-semibold">Incaricati e tempi dei passaggi automatici</summary><p className="text-sm text-muted-foreground my-3">Configura chi riceve ogni attività e il suo obiettivo interno in ore continuative. Questi tempi non sostituiscono scadenze contrattuali, appuntamenti o termini in giorni lavorativi. Le modifiche valgono per i prossimi incarichi; quelli già aperti mantengono persona e scadenza.</p>
      <div className="grid gap-3">{schema.steps.map(step => <RouteForm key={`${step.key}-${schema.routes[step.key]?.version || 0}`} step={step} schema={schema} onSaved={load}/>)}</div>
    </details>}
  </section>;
}

function RouteForm({ step, schema, onSaved }) {
  const route = schema.routes[step.key] || {};
  const [error, setError] = React.useState(""), [busy, setBusy] = React.useState(false);
  return <form className="border rounded-lg p-3 space-y-2" onSubmit={async e => {
    e.preventDefault(); const f = new FormData(e.currentTarget); setBusy(true); setError("");
    try { await api.put(`/operations/process/routes/${step.key}`, { version: route.version || 0, owner_id: f.get("owner"), target_hours: Number(f.get("hours")) }); await onSaved(); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }}><p className="text-sm font-medium">{schema.areas[step.area]} · {step.label}</p><fieldset disabled={busy} className="flex flex-wrap gap-2 items-end"><label className="text-sm flex-1 min-w-48">Incaricato<Select name="owner" aria-label={`Incaricato: ${step.label}`} required defaultValue={route.owner_id || ""}><PersonOptions schema={schema} step={step.key}/></Select></label><label className="text-sm w-36">Obiettivo ore<Input name="hours" type="number" min="1" max="2160" required defaultValue={route.target_hours || ""}/></label><Button variant="outline" type="submit">Salva regola</Button></fieldset>{error && <p role="alert" className="text-sm text-red-800">{error}</p>}</form>;
}

export function ProcessTask({ order, busy, mutate }) {
  const [schema, setSchema] = React.useState(null), [error, setError] = React.useState("");
  React.useEffect(() => { let active = true; api.get("/operations/process/schema").then(r => { if (active) setSchema(r.data); }).catch(e => { if (active) setError(errorText(e)); }); return () => { active = false; }; }, [order.version]);
  const task = order.operational_process?.task;
  const base = `/operations/process/orders/${order.id || order._id}`;
  const command = (action, fields = {}) => mutate(`${base}/action`, "post", { version: order.version || 0, action, ...fields });
  const closed = ["closed", "cancelled"].includes(order.order_status);
  if (!schema) return <p role={error ? "alert" : "status"}>{error || "Caricamento procedura…"}</p>;
  if (!task) return <Card className="p-4 space-y-3"><h2 className="font-semibold">Passaggi tra reparti da attivare</h2><p className="text-sm">L’avvio riapre la verifica del fascicolo dal commerciale e revoca le vecchie attestazioni. Lo storico rimane conservato; nessuna attività precedente viene dichiarata conclusa automaticamente.</p><Button disabled={busy || closed || !schema.can_assign} onClick={() => mutate(`${base}/start`, "post", { version: order.version || 0 })}>Avvia procedura dal fascicolo</Button></Card>;
  const canWork = schema.user_id === task.owner_id && schema.allowed_steps.includes(task.step);
  const index = schema.steps.findIndex(s => s.key === task.step);
  const next = schema.steps[index + 1];
  return <section className="rounded-xl border bg-slate-50 p-4 space-y-4" aria-label="Attività corrente">
    <div><p className="text-xs uppercase tracking-wide text-muted-foreground">{schema.areas[task.area]} · passaggio {index + 1} di {schema.steps.length}</p><h2 className="font-semibold text-lg mt-1">{task.label}</h2><p className="text-sm mt-2">{states[task.status]} · {schema.candidates[task.owner_id]?.name || "Incaricato da assegnare/verificare"}</p><p className="text-sm">Scadenza: {date(task.due_at)} · Presa in carico: {task.accepted_at ? date(task.accepted_at) : "Non ancora"}</p></div>
    {task.block && <p role="alert" className="text-sm text-red-800">Blocco: {task.block}</p>}
    {!closed && <>
      {(!task.owner_id || !task.due_at) && <p role="alert" className="text-sm text-amber-800">Assegnare incaricato e termine. Questa attività resta visibile nella coda delle eccezioni.</p>}
      <Button disabled={busy || !canWork || task.status !== "pending" || !task.due_at} onClick={() => command("accept")}>Prendi in carico</Button>
      <form key={`${task.id}-${order.version}`} className="space-y-3" onSubmit={e => {
        e.preventDefault(); const f = new FormData(e.currentTarget); const action = e.nativeEvent.submitter?.value;
        if (!action) return;
        command(action, { evidence: f.get("evidence"), ...(action === "complete" && ["installation", "acceptance"].includes(task.step) ? { residuals: Number(f.get("residuals")) } : {}) });
      }}><label className="grid gap-1 text-sm font-medium">Esito e riferimento al documento, oppure motivo del blocco<textarea name="evidence" required minLength={5} maxLength={2000} rows={3} className="w-full rounded-md border p-2 bg-background" disabled={busy || !canWork || task.status === "pending"}/></label>
        {["installation", "acceptance"].includes(task.step) && <label className="grid gap-1 text-sm">Completamenti ancora aperti<Input name="residuals" type="number" required min="0" max="10000" defaultValue={order.operational_residuals || 0}/></label>}
        <div className="flex flex-wrap gap-2"><Button type="submit" value="complete" disabled={busy || !canWork || task.status !== "in_progress"}>{next ? "Concludi e consegna al reparto successivo" : "Concludi e chiudi la commessa"}</Button><Button type="submit" value="block" variant="outline" disabled={busy || !canWork || task.status !== "in_progress"}>Segnala blocco</Button><Button type="submit" value="resume" variant="outline" disabled={busy || !canWork || task.status !== "blocked"}>Registra soluzione e riprendi</Button></div>
      </form>
      {next && <p className="text-sm text-muted-foreground">Alla conclusione: {schema.areas[next.area]} → {next.label}. L’incaricato è scelto dalla regola configurata; se manca, il lavoro entra nella coda da assegnare.</p>}
      {schema.can_assign && <details><summary className="cursor-pointer font-medium text-sm">Assegna, ripianifica o rinvia</summary>
        <form key={`assign-${order.version}`} className="space-y-3 mt-3" onSubmit={e => {
          e.preventDefault(); const f = new FormData(e.currentTarget); const due = new Date(f.get("due"));
          if (!Number.isFinite(due.getTime())) return;
          mutate(`${base}/assignment`, "put", { version: order.version || 0, owner_id: f.get("owner"), due_at: due.toISOString(), reason: f.get("reason") });
        }}><label className="grid gap-1 text-sm">Incaricato abilitato<Select name="owner" required defaultValue={task.owner_id || ""}><PersonOptions schema={schema} step={task.step}/></Select></label><label className="grid gap-1 text-sm">Scadenza effettiva<Input name="due" type="datetime-local" required defaultValue={localDate(task.due_at)}/></label><label className="grid gap-1 text-sm">Motivo dell’assegnazione o ripianificazione<Input name="reason" required minLength={5} maxLength={2000}/></label><Button type="submit" variant="outline" disabled={busy}>Salva incarico e termine</Button></form>
        <form className="space-y-3 mt-5 border-t pt-3" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); command(e.nativeEvent.submitter?.value || "return", { evidence: f.get("reason"), target_step: f.get("target") }); }}><label className="grid gap-1 text-sm">Rinvia per nuova verifica<Select name="target" defaultValue={task.step}>{schema.steps.slice(0, index + 1).map(s => <option key={s.key} value={s.key}>{s.label}</option>)}</Select></label><label className="grid gap-1 text-sm">Motivo del rinvio o annullamento<Input name="reason" required minLength={5} maxLength={2000}/></label><div className="flex gap-2 flex-wrap"><Button type="submit" value="return" variant="outline" disabled={busy}>Rinvia e riapri i controlli successivi</Button><Button type="submit" value="cancel" variant="outline" disabled={busy}>Annulla commessa</Button></div></form>
      </details>}
    </>}
  </section>;
}

export function ProcessHistory({ history, people }) {
  const name = id => people.find(p => p.id === id)?.name || id || "Da assegnare";
  return <details className="border-t pt-4"><summary className="cursor-pointer text-sm font-semibold">Storico di responsabilità e verifiche ({history?.length || 0})</summary><ol className="mt-3 space-y-3">{[...(history || [])].reverse().map((h, i) => {
    const d = h.details;
    return <li key={i} className="text-sm border-b pb-3"><p className="font-medium">{h.event.startsWith("process.") ? events[h.event.slice(8)] || h.event : ({ "finance.updated": "Situazione finanziaria aggiornata", "order.revised": "Commessa revisionata", "plan.updated": "Piano aggiornato" })[h.event] || h.event}</p><p className="text-xs text-muted-foreground">{date(h.at)} · Autore: {name(h.actor_id)}</p>
      {d?.from_task && <p className="mt-1">Da: {d.from_task.label} · {name(d.from_task.owner_id)} · {states[d.from_task.status]}</p>}
      {d?.to_task && <p>A: {d.to_task.label} · {name(d.to_task.owner_id)} · {states[d.to_task.status]} · termine {date(d.to_task.due_at)}</p>}
      {d?.evidence && <p className="mt-1 whitespace-pre-wrap">{d.evidence}</p>}
      {!d && h.changes && <p className="mt-1 text-xs whitespace-pre-wrap">{Object.entries(h.changes).filter(([k]) => k.startsWith("operational_checks.")).map(([, v]) => v.evidence).filter(Boolean).join(" · ") || h.changes.finance_evidence || h.changes.operational_next_action || h.changes.operational_transition_reason || "Aggiornamento registrato"}</p>}
    </li>;
  })}</ol></details>;
}
