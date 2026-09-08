import React, { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";
import { customerDisplayName } from "@/components/customers/CustomerTypeBadge";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

const STATUS_COLORS = { draft: "bg-secondary", to_complete: "bg-amber-100 text-amber-900", to_approve: "bg-orange-100 text-orange-900", approved: "bg-emerald-100 text-emerald-900", sent: "bg-blue-100 text-blue-900", viewed: "bg-purple-100 text-purple-900", accepted: "bg-emerald-500 text-white", rejected: "bg-red-100 text-red-900", expired: "bg-zinc-200", cancelled: "bg-zinc-200", converted: "bg-emerald-600 text-white", superseded: "bg-zinc-100 text-zinc-500 line-through" };

export default function QuotesPage() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ["quotes", q], queryFn: async () => (await api.get("/quotes", { params: { q: q || undefined, limit: 200 } })).data });
  const createMut = useMutation({
    mutationFn: async (p) => (await api.post("/quotes", p)).data,
    onSuccess: (d) => { toast.success("Preventivo creato"); qc.invalidateQueries({ queryKey: ["quotes"] }); setOpen(false); navigate(`/quotes/${d.id}`); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="space-y-8" data-testid="quotes-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">Modulo commerciale · M3</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">Preventivi</h1>
        </div>
        {has("quotes.create") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="rounded-sm h-11 gap-2" data-testid="new-quote-button"><Plus size={16} weight="bold" />Nuovo preventivo</Button></DialogTrigger>
            <NewQuoteDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <Card className="rounded-sm border-border p-4"><Input placeholder="Cerca numero, titolo…" value={q} onChange={(e) => setQ(e.target.value)} className="rounded-sm h-10 max-w-sm" data-testid="quotes-search" /></Card>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead className="overline">Numero</TableHead>
            <TableHead className="overline">Titolo</TableHead>
            <TableHead className="overline">Stato</TableHead>
            <TableHead className="overline">Totale</TableHead>
            {has("quotes.view_margins") && <TableHead className="overline">Margine</TableHead>}
            <TableHead className="overline">Prob.</TableHead>
            <TableHead className="overline">Aggiornato</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.items || []).map((qq) => (
              <TableRow key={qq.id} onClick={() => navigate(`/quotes/${qq.id}`)} className="cursor-pointer" data-testid={`quote-row-${qq.id}`}>
                <TableCell className="font-mono-plex text-xs">{qq.number}</TableCell>
                <TableCell className="text-sm">{qq.title || "—"}</TableCell>
                <TableCell><span className={`text-[10px] font-mono-plex uppercase px-2 py-1 rounded-sm ${STATUS_COLORS[qq.quote_status] || "bg-secondary"}`}>{qq.quote_status}</span></TableCell>
                <TableCell className="font-mono-plex">{fmtEUR(qq.total)}</TableCell>
                {has("quotes.view_margins") && <TableCell className="font-mono-plex text-xs text-[hsl(var(--brand-red))]">{qq.margin_abs != null ? `${fmtEUR(qq.margin_abs)} (${qq.margin_pct}%)` : "—"}</TableCell>}
                <TableCell><Badge variant="outline" className="rounded-sm">{qq.probability}%</Badge></TableCell>
                <TableCell className="text-xs text-muted-foreground">{qq.updated_at ? new Date(qq.updated_at).toLocaleDateString("it-IT") : ""}</TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && <TableRow><TableCell colSpan={7} className="text-center py-10 text-sm text-muted-foreground">Nessun preventivo</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

/** Nuovo cantiere inline (msg 402 Lotto 2) — dati obbligatori: indirizzo, civico, CAP, comune, provincia, piano, ascensore, telefono. */
function NewSiteInlineForm({ customer, onCreated }) {
  const addr = customer?.address || {};
  const [f, setF] = useState({
    name: "Cantiere", address: addr.street || "", street_number: "", postal_code: addr.zip_code || "", city: addr.city || "",
    province: addr.province || "", floor: "", has_elevator: "", site_contact_phone: customer?.phone || customer?.mobile || "",
  });
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const create = useMutation({
    mutationFn: async () => (await api.post("/sites", {
      customer_id: customer.id, name: f.name || `Cantiere ${f.city}`, address: f.address, street_number: f.street_number,
      postal_code: f.postal_code, city: f.city, province: f.province, floor: f.floor,
      has_elevator: f.has_elevator === "" ? null : f.has_elevator === "SI", site_contact_phone: f.site_contact_phone,
    })).data,
    onSuccess: (site) => { toast.success("Cantiere creato"); onCreated(site); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  return (
    <div className="mt-2 border border-border rounded-sm p-3 space-y-2 bg-muted/20" data-testid="nq-new-site-form">
      <div className="grid grid-cols-2 gap-2">
        <div><Label className="text-[10px] uppercase">Indirizzo *</Label><Input value={f.address} onChange={set("address")} placeholder="Via/Piazza" className="rounded-sm h-9" data-testid="ns-address" /></div>
        <div><Label className="text-[10px] uppercase">Civico *</Label><Input value={f.street_number} onChange={set("street_number")} className="rounded-sm h-9" data-testid="ns-street-number" /></div>
        <div><Label className="text-[10px] uppercase">CAP *</Label><Input value={f.postal_code} onChange={set("postal_code")} className="rounded-sm h-9" data-testid="ns-postal-code" /></div>
        <div><Label className="text-[10px] uppercase">Comune *</Label><Input value={f.city} onChange={set("city")} className="rounded-sm h-9" data-testid="ns-city" /></div>
        <div><Label className="text-[10px] uppercase">Provincia *</Label><Input value={f.province} onChange={set("province")} placeholder="es. MI" className="rounded-sm h-9" data-testid="ns-province" /></div>
        <div><Label className="text-[10px] uppercase">Piano *</Label><Input value={f.floor} onChange={set("floor")} placeholder="es. 2" className="rounded-sm h-9" data-testid="ns-floor" /></div>
        <div>
          <Label className="text-[10px] uppercase">Ascensore *</Label>
          <Select value={f.has_elevator} onValueChange={(v) => setF((s) => ({ ...s, has_elevator: v }))}>
            <SelectTrigger className="rounded-sm h-9" data-testid="ns-elevator"><SelectValue placeholder="SI / NO" /></SelectTrigger>
            <SelectContent><SelectItem value="SI">SI</SelectItem><SelectItem value="NO">NO</SelectItem></SelectContent>
          </Select>
        </div>
        <div><Label className="text-[10px] uppercase">Telefono cantiere *</Label><Input value={f.site_contact_phone} onChange={set("site_contact_phone")} className="rounded-sm h-9" data-testid="ns-phone" /></div>
      </div>
      <Button type="button" size="sm" className="rounded-sm" disabled={create.isPending} onClick={() => create.mutate()} data-testid="ns-save">Crea cantiere</Button>
    </div>
  );
}

/**
 * NewQuoteDialog — Milestone 1 Part 2
 * Cliente obbligatorio → Cantiere obbligatorio filtrato per customer.
 */
function NewQuoteDialog({ onSubmit, loading }) {
  const [customerId, setCustomerId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [title, setTitle] = useState("");
  const [intervention, setIntervention] = useState("new");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [showNewSite, setShowNewSite] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: customers } = useQuery({
    queryKey: ["customers-for-quote-picker"],
    queryFn: async () => (await api.get("/customers", { params: { limit: 500 } })).data,
  });
  const { data: sites, isFetching: sitesLoading } = useQuery({
    enabled: !!customerId,
    queryKey: ["sites-for-quote", customerId],
    queryFn: async () => (await api.get("/sites", { params: { customer_id: customerId } })).data,
  });

  useEffect(() => { setSiteId(""); }, [customerId]);

  const currentCustomer = useMemo(
    () => (customers?.items || []).find((c) => c.id === customerId),
    [customers, customerId],
  );
  const noSites = !!customerId && !sitesLoading && (sites?.items || []).length === 0;

  const submit = (e) => {
    e.preventDefault();
    if (!customerId || !siteId) {
      toast.error("Selezionare cliente e cantiere");
      return;
    }
    onSubmit({
      customer_id: customerId,
      site_id: siteId,
      title: title || undefined,
      intervention_type: intervention,
      payment_terms: paymentTerms || undefined,
    });
  };

  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="new-quote-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo preventivo</DialogTitle>
        <DialogDescription>Cliente → Cantiere → Preventivo. Entrambi i passi sono obbligatori.</DialogDescription>
      </DialogHeader>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <Label className="overline">Cliente *</Label>
          <Select value={customerId} onValueChange={setCustomerId}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nq-customer"><SelectValue placeholder="Seleziona cliente…" /></SelectTrigger>
            <SelectContent>
              {(customers?.items || []).map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.customer_number ? `${c.customer_number} · ` : ""}{customerDisplayName(c)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label className="overline">Cantiere *</Label>
          {/* Radix emette onValueChange("") quando la lista item cambia (refetch): ignorare il reset spontaneo */}
          <Select value={siteId} onValueChange={(v) => { if (v) setSiteId(v); }} disabled={!customerId || noSites}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nq-site">
              <SelectValue placeholder={!customerId ? "Seleziona prima un cliente" : noSites ? "Nessun cantiere per questo cliente" : "Seleziona cantiere…"} />
            </SelectTrigger>
            <SelectContent>
              {(sites?.items || []).map((s) => (
                <SelectItem key={s.id} value={s.id}>{s.site_number} · {s.name} {s.city ? `(${s.city})` : ""}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {noSites && (
            <div className="mt-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-sm p-2" data-testid="nq-no-sites">
              Il cliente non ha cantieri: crea il cantiere qui sotto.
            </div>
          )}
          {customerId && (
            <Button type="button" size="sm" variant="outline" className="rounded-sm h-7 mt-2" onClick={() => setShowNewSite((v) => !v)} data-testid="nq-create-site">
              {showNewSite ? "Annulla nuovo cantiere" : "+ Nuovo cantiere"}
            </Button>
          )}
          {customerId && showNewSite && (
            <NewSiteInlineForm
              customer={currentCustomer}
              onCreated={(site) => {
                qc.setQueryData(["sites-for-quote", customerId], (old) => {
                  if (!old) return { items: [site] };
                  if (Array.isArray(old)) return [...old, site];
                  return { ...old, items: [...(old.items || []), site] };
                });
                setSiteId(site.id);
                setShowNewSite(false);
                qc.invalidateQueries({ queryKey: ["sites-for-quote", customerId] });
              }}
            />
          )}
        </div>

        <div>
          <Label className="overline">Titolo</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Es. Sostituzione infissi" className="rounded-sm h-10" data-testid="nq-title" />
        </div>
        <div>
          <Label className="overline">Tipo intervento</Label>
          <Select value={intervention} onValueChange={setIntervention}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nq-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="new">Nuova costruzione</SelectItem>
              <SelectItem value="renovation">Ristrutturazione</SelectItem>
              <SelectItem value="replacement">Sostituzione</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="overline">Termini pagamento</Label>
          <Select value={paymentTerms || "DEPOSIT_50_BALANCE_50"} onValueChange={setPaymentTerms}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nq-payment"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="DEPOSIT_50_BALANCE_50">50% acconto · 50% merce pronta</SelectItem>
              <SelectItem value="FULL_UPFRONT">100% all'ordine (sconto 5%)</SelectItem>
              <SelectItem value="DEPOSIT_30_SURVEY_20_BALANCE_50">30% · 20% dopo rilievo · 50% merce pronta</SelectItem>
              <SelectItem value="FINANCING_WITHOUT_DEPOSIT">Finanziamento senza acconto</SelectItem>
              <SelectItem value="FINANCING_WITH_DEPOSIT">Finanziamento con acconto</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button type="submit" disabled={loading || !customerId || !siteId} className="rounded-sm" data-testid="nq-submit">
            {loading ? "…" : "Crea preventivo"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
