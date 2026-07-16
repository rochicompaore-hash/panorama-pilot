/** Generic ERP list page with config-driven columns + optional create dialog.
 * Renders a searchable/filterable table for any of the new M4..M17 modules.
 * Delegates detail views to individual dialogs or a JSON drawer for now.
 */
import React from "react";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Plus, MagnifyingGlass, ArrowClockwise } from "@phosphor-icons/react";
import { toast, Toaster } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;
function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0); } catch { return "€ 0"; } }
function fmtDate(v) { if (!v) return ""; try { return new Date(v).toLocaleString("it-IT"); } catch { return v; } }

export default function ErpOpsPage({ config }) {
  const { title, description, endpoint, columns, filters, primaryKey = "_id",
          idKey = "_id", createForm, statusField, testid, disableCreate = false } = config;
  const [items, setItems] = React.useState([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [q, setQ] = React.useState("");
  const [filterVals, setFilterVals] = React.useState({});
  const [detail, setDetail] = React.useState(null);
  const [createOpen, setCreateOpen] = React.useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    Object.entries(filterVals).forEach(([k, v]) => { if (v) params.set(k, v); });
    params.set("limit", "50");
    axios.get(`${API}/api/${endpoint}?${params}`)
      .then((r) => { setItems(r.data.items || r.data.docs || []); setTotal(r.data.total || (r.data.items || []).length); })
      .catch((e) => { toast.error(e.response?.data?.detail || "Errore caricamento"); })
      .finally(() => setLoading(false));
  }, [endpoint, q, JSON.stringify(filterVals)]); // eslint-disable-line

  React.useEffect(load, [load]);

  return (
    <div className="space-y-6" data-testid={testid || "ops-page"}>
      <Toaster richColors position="top-center" />
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-display text-3xl font-black tracking-tight">{title}</h1>
          {description && <p className="text-sm text-muted-foreground mt-1">{description}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="rounded-sm" onClick={load} data-testid="btn-reload">
            <ArrowClockwise size={14} className="mr-1" /> Aggiorna
          </Button>
          {!disableCreate && createForm && (
            <Button size="sm" className="rounded-sm" onClick={() => setCreateOpen(true)} data-testid="btn-new">
              <Plus size={14} className="mr-1" /> Nuovo
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-2 top-2.5 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca…"
                 className="rounded-sm pl-7 w-64" data-testid="search-input" />
        </div>
        {(filters || []).map((f) => (
          <select key={f.key} value={filterVals[f.key] || ""}
                  onChange={(e) => setFilterVals((s) => ({ ...s, [f.key]: e.target.value }))}
                  className="rounded-sm border border-input bg-background px-2 py-1.5 text-sm"
                  data-testid={`filter-${f.key}`}>
            <option value="">{f.label}</option>
            {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ))}
        <div className="ml-auto text-xs text-muted-foreground" data-testid="ops-total">Totale: <b>{total}</b></div>
      </div>

      <Card className="rounded-sm border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-muted/30">
            <tr>
              {columns.map((c) => <th key={c.key} className="text-left px-3 py-2 font-mono-plex text-xs uppercase tracking-wider">{c.label}</th>)}
              <th />
            </tr>
          </thead>
          <tbody>
            {loading && (<tr><td colSpan={columns.length + 1} className="text-center py-6 text-muted-foreground">Caricamento…</td></tr>)}
            {!loading && items.length === 0 && (
              <tr><td colSpan={columns.length + 1} className="text-center py-8 text-muted-foreground" data-testid="empty-state">
                Nessun elemento. {!disableCreate && "Crea il primo con il tasto 'Nuovo'."}
              </td></tr>
            )}
            {items.map((it) => (
              <tr key={it[idKey] || it.id} className="border-t hover:bg-muted/20 cursor-pointer"
                  onClick={() => setDetail(it)} data-testid={`row-${(it[idKey] || it.id || "").slice(-6)}`}>
                {columns.map((c) => (
                  <td key={c.key} className="px-3 py-2 align-middle">{renderCell(it, c)}</td>
                ))}
                <td className="px-3 py-2 text-right text-muted-foreground text-xs">→</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {detail && (
        <Dialog open onOpenChange={() => setDetail(null)}>
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{title} — dettaglio</DialogTitle>
              <DialogDescription>{detail.number || detail.name || detail._id}</DialogDescription>
            </DialogHeader>
            <pre className="text-xs bg-muted/20 rounded-sm p-3 overflow-auto max-h-[60vh] font-mono-plex">
              {JSON.stringify(detail, null, 2)}
            </pre>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDetail(null)}>Chiudi</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {createOpen && createForm && (
        <SimpleCreateDialog config={createForm} endpoint={endpoint}
          onClose={() => setCreateOpen(false)}
          onSuccess={() => { setCreateOpen(false); load(); toast.success("Creato con successo"); }} />
      )}
    </div>
  );
}


function renderCell(item, col) {
  const v = item[col.key];
  if (col.type === "money") return <span className="font-mono-plex">{fmtEUR(v)}</span>;
  if (col.type === "date") return <span className="text-xs text-muted-foreground">{fmtDate(v)}</span>;
  if (col.type === "status") {
    if (!v) return "—";
    return <Badge variant="outline" className="rounded-sm text-xs capitalize">{String(v).replace(/_/g, " ")}</Badge>;
  }
  if (col.type === "bool") return v ? "✓" : "—";
  if (v === null || v === undefined) return <span className="text-muted-foreground">—</span>;
  if (typeof v === "object") return <span className="text-xs text-muted-foreground">…</span>;
  return String(v);
}


function SimpleCreateDialog({ config, endpoint, onClose, onSuccess }) {
  const [values, setValues] = React.useState({});
  const [busy, setBusy] = React.useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const payload = { ...config.defaults, ...values };
      // Coerce numeric fields
      for (const f of config.fields) {
        if (f.type === "number" && payload[f.key] != null && payload[f.key] !== "") payload[f.key] = Number(payload[f.key]);
      }
      await axios.post(`${API}/api/${endpoint}`, payload);
      onSuccess();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore creazione");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{config.title || "Nuovo"}</DialogTitle>
          {config.description && <DialogDescription>{config.description}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-3">
          {config.fields.map((f) => (
            <div key={f.key}>
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{f.label}{f.required && " *"}</label>
              <Input type={f.type || "text"} value={values[f.key] || ""}
                     onChange={(e) => setValues((s) => ({ ...s, [f.key]: e.target.value }))}
                     className="rounded-sm mt-1" placeholder={f.placeholder}
                     data-testid={`field-${f.key}`} />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={submit} disabled={busy} data-testid="create-submit">
            {busy ? "Salvataggio…" : "Crea"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
