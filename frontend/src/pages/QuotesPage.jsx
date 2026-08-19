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
  const navigate = useNavigate();

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
          <Select value={siteId} onValueChange={setSiteId} disabled={!customerId || noSites}>
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
            <div className="mt-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-sm p-2 flex items-center justify-between" data-testid="nq-no-sites">
              <span>Il cliente non ha cantieri.</span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="rounded-sm h-7 gap-1"
                onClick={() => navigate(`/customers/${customerId}`)}
                data-testid="nq-create-site"
              >
                Vai al cliente <ArrowRight size={14} />
              </Button>
            </div>
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
          <Input value={paymentTerms} onChange={(e) => setPaymentTerms(e.target.value)} placeholder="Es. 30% acconto, 70% a saldo" className="rounded-sm h-10" data-testid="nq-payment" />
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
