import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const STATUS_BADGE = { PENDING_APPROVAL: "default", PENDING_EMAIL_VERIFICATION: "secondary", APPROVED: "outline", REJECTED: "destructive", SUSPENDED: "destructive" };
const STATUSES = ["PENDING_APPROVAL", "PENDING_EMAIL_VERIFICATION", "APPROVED", "REJECTED", "SUSPENDED"];

function ApproveDialog({ req, options, onClose, onDone }) {
  const [tenantId, setTenantId] = useState(options.tenants[0]?.id || "");
  const [role, setRole] = useState(options.roles.some((r) => r.code === req.requested_role) ? req.requested_role : "");
  const [customerId, setCustomerId] = useState("");
  const [matches, setMatches] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (role !== "cliente" || !tenantId) { setMatches(null); return; }
    api.get(`/registration-requests/${req.id}/customer-matches`, { params: { tenant_id: tenantId } })
      .then((r) => { setMatches(r.data); if (r.data.proposed_customer_id) setCustomerId(r.data.proposed_customer_id); })
      .catch(() => setMatches({ decision: "NO_MATCH", matches: [] }));
  }, [role, tenantId, req.id]);

  const approve = async () => {
    setBusy(true);
    try {
      await api.post(`/registration-requests/${req.id}/approve`, { tenant_id: tenantId, effective_role: role, customer_id: role === "cliente" ? customerId || null : null });
      toast.success("Richiesta approvata"); onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="approve-dialog">
        <DialogHeader><DialogTitle>Approva {req.first_name} {req.last_name}</DialogTitle></DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="text-muted-foreground">Ruolo richiesto: <b>{req.requested_role}</b>{req.company_name ? ` · Azienda indicata: ${req.company_name}` : ""}</div>
          <div className="space-y-1.5">
            <Label className="overline">Tenant</Label>
            <select value={tenantId} onChange={(e) => setTenantId(e.target.value)} className="w-full h-10 rounded-sm border border-input bg-background px-3" data-testid="approve-tenant-select">
              {options.tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="overline">Ruolo effettivo</Label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full h-10 rounded-sm border border-input bg-background px-3" data-testid="approve-role-select">
              <option value="">Seleziona…</option>
              {options.roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
            </select>
          </div>
          {role === "cliente" && (
            <div className="space-y-2 p-3 border rounded-sm bg-secondary/40" data-testid="approve-customer-link">
              <div className="font-semibold">Collegamento scheda cliente (obbligatorio)</div>
              {matches && <div className="text-xs text-muted-foreground" data-testid="customer-match-decision">Esito match: <b>{matches.decision}</b></div>}
              {(matches?.matches || []).map((m) => (
                <label key={m.customer_id} className="flex items-start gap-2 text-xs cursor-pointer" data-testid={`customer-match-${m.customer_id}`}>
                  <input type="radio" name="cust" checked={customerId === m.customer_id} onChange={() => setCustomerId(m.customer_id)} />
                  <span><b>{m.name}</b> {m.company_name && `· ${m.company_name}`} · {m.email} · {m.phone} <span className="text-muted-foreground">({m.match_fields.join(", ")})</span></span>
                </label>
              ))}
              <div className="space-y-1">
                <Label className="text-xs">customer_id (manuale)</Label>
                <Input value={customerId} onChange={(e) => setCustomerId(e.target.value)} className="h-9 rounded-sm font-mono text-xs" data-testid="approve-customer-id-input" />
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-sm">Annulla</Button>
          <Button onClick={approve} disabled={busy || !tenantId || !role || (role === "cliente" && !customerId)} className="rounded-sm" data-testid="approve-confirm-button">Approva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function RegistrationRequestsPage() {
  const [items, setItems] = useState([]);
  const [options, setOptions] = useState({ tenants: [], roles: [] });
  const [filters, setFilters] = useState({ status: "PENDING_APPROVAL", requested_role: "", tenant_id: "", date_from: "" });
  const [approving, setApproving] = useState(null);
  const [rejecting, setRejecting] = useState(null);
  const [reason, setReason] = useState("");

  const load = async () => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    const r = await api.get("/registration-requests", { params });
    setItems(r.data.items || []);
  };
  useEffect(() => { api.get("/registration-requests/options").then((r) => setOptions(r.data)); }, []);
  useEffect(() => { load().catch((e) => toast.error(formatApiError(e.response?.data?.detail))); }, [filters]); // eslint-disable-line

  const pendingCount = useMemo(() => items.filter((i) => i.status === "PENDING_APPROVAL").length, [items]);

  const act = async (id, action, body = {}) => {
    try { await api.post(`/registration-requests/${id}/${action}`, body); toast.success("Operazione eseguita"); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-6" data-testid="registration-requests-page">
      <div>
        <div className="overline">Superadmin</div>
        <h1 className="font-display text-3xl font-black tracking-tight">Richieste di registrazione</h1>
        <p className="text-sm text-muted-foreground mt-1">Il ruolo richiesto non conferisce permessi: tenant e ruolo effettivo vengono assegnati qui.</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Filtri</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className="h-10 rounded-sm border border-input bg-background px-3 text-sm" data-testid="filter-status">
            <option value="">Tutti gli stati</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filters.requested_role} onChange={(e) => setFilters({ ...filters, requested_role: e.target.value })} className="h-10 rounded-sm border border-input bg-background px-3 text-sm" data-testid="filter-role">
            <option value="">Tutti i ruoli richiesti</option>
            {options.roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
          </select>
          <select value={filters.tenant_id} onChange={(e) => setFilters({ ...filters, tenant_id: e.target.value })} className="h-10 rounded-sm border border-input bg-background px-3 text-sm" data-testid="filter-tenant">
            <option value="">Tutti i tenant (approvato)</option>
            {options.tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <Input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} className="h-10 rounded-sm" data-testid="filter-date-from" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2">Richieste <Badge data-testid="pending-count-badge">{pendingCount} PENDING</Badge></CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="registration-requests-table">
            <thead><tr className="text-left text-xs uppercase text-muted-foreground border-b">
              <th className="py-2 pr-3">Nome</th><th className="pr-3">Email / Telefono</th><th className="pr-3">Data</th><th className="pr-3">Ruolo richiesto</th><th className="pr-3">Azienda</th><th className="pr-3">Email verificata</th><th className="pr-3">Stato</th><th>Azioni</th>
            </tr></thead>
            <tbody>
              {items.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-muted-foreground" data-testid="no-requests">Nessuna richiesta</td></tr>}
              {items.map((r) => (
                <tr key={r.id} className={`border-b ${r.status === "PENDING_APPROVAL" ? "bg-amber-50/60" : ""}`} data-testid={`request-row-${r.id}`}>
                  <td className="py-2 pr-3 font-medium">{r.first_name} {r.last_name}</td>
                  <td className="pr-3 text-xs">{r.email}<br />{r.phone}</td>
                  <td className="pr-3 text-xs">{new Date(r.registered_at).toLocaleString("it-IT")}</td>
                  <td className="pr-3"><Badge variant="secondary">{r.requested_role}</Badge>{r.approved_role && r.approved_role !== r.requested_role && <div className="text-[10px] text-muted-foreground">→ {r.approved_role}</div>}</td>
                  <td className="pr-3 text-xs">{r.company_name || "—"}{r.approved_tenant_id && <div className="text-[10px] text-muted-foreground">{options.tenants.find((t) => t.id === r.approved_tenant_id)?.name}</div>}</td>
                  <td className="pr-3">{r.email_verified ? "sì" : "no"}</td>
                  <td className="pr-3"><Badge variant={STATUS_BADGE[r.status]} data-testid={`request-status-${r.id}`}>{r.status}</Badge></td>
                  <td className="whitespace-nowrap space-x-1">
                    {r.status === "PENDING_APPROVAL" && <Button size="sm" className="rounded-sm" onClick={() => setApproving(r)} data-testid={`approve-btn-${r.id}`}>Approva</Button>}
                    {["PENDING_APPROVAL", "PENDING_EMAIL_VERIFICATION"].includes(r.status) && <Button size="sm" variant="outline" className="rounded-sm" onClick={() => { setRejecting(r); setReason(""); }} data-testid={`reject-btn-${r.id}`}>Rifiuta</Button>}
                    {r.status === "APPROVED" && <Button size="sm" variant="destructive" className="rounded-sm" onClick={() => act(r.id, "suspend")} data-testid={`suspend-btn-${r.id}`}>Sospendi</Button>}
                    {r.status === "SUSPENDED" && <Button size="sm" variant="outline" className="rounded-sm" onClick={() => act(r.id, "reactivate")} data-testid={`reactivate-btn-${r.id}`}>Riattiva</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {approving && <ApproveDialog req={approving} options={options} onClose={() => setApproving(null)} onDone={() => { setApproving(null); load(); }} />}
      {rejecting && (
        <Dialog open onOpenChange={(o) => !o && setRejecting(null)}>
          <DialogContent data-testid="reject-dialog">
            <DialogHeader><DialogTitle>Rifiuta richiesta</DialogTitle></DialogHeader>
            <Label className="overline">Motivo interno (opzionale, non mostrato all'utente)</Label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-sm" data-testid="reject-reason-input" />
            <DialogFooter>
              <Button variant="outline" className="rounded-sm" onClick={() => setRejecting(null)}>Annulla</Button>
              <Button variant="destructive" className="rounded-sm" onClick={async () => { await act(rejecting.id, "reject", { rejection_reason_internal: reason || null }); setRejecting(null); }} data-testid="reject-confirm-button">Rifiuta</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
