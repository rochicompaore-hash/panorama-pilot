import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, FileText } from "@phosphor-icons/react";
import { toast } from "sonner";
import { NewQuoteDialog } from "@/components/quotes/NewQuoteDialog";
import { customerDisplayName } from "@/components/customers/CustomerTypeBadge";

function fmtEUR(n) {
  try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); }
  catch { return "€ 0"; }
}

/**
 * CustomerQuotesTab — Milestone 1 Part 2
 * - lista preventivi filtrati sul customer_id
 * - CTA "Nuovo preventivo" con selezione Cantiere obbligatoria
 * - se il cliente non ha cantieri, offre creazione inline (link Cantieri tab)
 */
export default function CustomerQuotesTab({ customerId, customer, sites = [] }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data } = useQuery({
    queryKey: ["customer-quotes", customerId],
    queryFn: async () => (await api.get("/quotes", { params: { customer_id: customerId, limit: 200 } })).data,
  });

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/quotes", payload)).data,
    onSuccess: (d) => {
      toast.success("Preventivo creato");
      qc.invalidateQueries({ queryKey: ["customer-quotes", customerId] });
      qc.invalidateQueries({ queryKey: ["customer-timeline", customerId] });
      setOpen(false);
      navigate(`/quotes/${d.id}`);
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const items = data?.items || [];

  return (
    <div className="space-y-4" data-testid="quotes-tab">
      <div className="flex items-center justify-between">
        <div className="overline">{items.length} preventivo/i</div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-sm gap-2 h-10" data-testid="new-quote-button-in-customer">
              <Plus size={14} weight="bold" /> Crea preventivo
            </Button>
          </DialogTrigger>
          <NewQuoteDialog initialCustomer={customer} onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
        </Dialog>
      </div>

      {items.length === 0 && (
        <Card className="rounded-sm border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Nessun preventivo per questo cliente.
        </Card>
      )}

      <div className="space-y-2">
        {items.map((q) => (
          <Card
            key={q.id}
            className="rounded-sm border-border p-4 cursor-pointer hover:border-primary transition-colors"
            onClick={() => navigate(`/quotes/${q.id}`)}
            data-testid={`customer-quote-${q.id}`}
          >
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <FileText size={18} weight="duotone" />
                <div>
                  <div className="font-mono-plex text-xs text-muted-foreground">{q.number}</div>
                  <div className="text-sm font-medium">{q.title || "Preventivo"}</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Badge variant="outline" className="rounded-sm text-[10px] uppercase font-mono-plex">{q.quote_status}</Badge>
                <div className="font-mono-plex text-sm">{fmtEUR(q.total)}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function NewQuoteForCustomerDialog({ customer, sites, onSubmit, loading }) {
  const [siteId, setSiteId] = useState(sites[0]?.id || "");
  const [title, setTitle] = useState("");
  const [intervention, setIntervention] = useState("new");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [notes, setNotes] = useState("");

  const noSites = sites.length === 0;

  const submit = (e) => {
    e.preventDefault();
    if (noSites || !siteId) {
      toast.error("Selezionare un cantiere");
      return;
    }
    onSubmit({
      customer_id: customer.id,
      site_id: siteId,
      title: title || undefined,
      intervention_type: intervention,
      payment_terms: paymentTerms || undefined,
      notes: notes || undefined,
    });
  };

  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="new-quote-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo preventivo</DialogTitle>
        <DialogDescription>
          Cliente: <b>{customerDisplayName(customer)}</b> · Selezionare il cantiere di riferimento.
        </DialogDescription>
      </DialogHeader>
      {noSites && (
        <Card className="rounded-sm bg-amber-50 border-amber-300 p-3 text-sm text-amber-900" data-testid="quote-no-sites-warning">
          Questo cliente non ha ancora cantieri. Aggiungi almeno un cantiere per creare un preventivo.
          <div className="mt-2">
            <a href={`/customers/${customer.id}`} className="underline font-medium" data-testid="quote-goto-sites">
              → Vai al tab Cantieri
            </a>
          </div>
        </Card>
      )}
      <form onSubmit={submit} className="space-y-3">
        <div>
          <Label className="overline">Cantiere *</Label>
          <Select value={siteId} onValueChange={setSiteId} disabled={noSites}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nq-site"><SelectValue placeholder="Seleziona…" /></SelectTrigger>
            <SelectContent>
              {sites.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.site_number} · {s.name} {s.city ? `(${s.city})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="overline">Titolo</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`Preventivo ${customerDisplayName(customer)}`} className="rounded-sm h-10" data-testid="nq-title" />
        </div>
        <div>
          <Label className="overline">Tipo intervento</Label>
          <Select value={intervention} onValueChange={setIntervention}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nq-intervention"><SelectValue /></SelectTrigger>
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
        <div>
          <Label className="overline">Note</Label>
          <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} className="rounded-sm" data-testid="nq-notes" />
        </div>
        <DialogFooter>
          <Button type="submit" disabled={loading || noSites || !siteId} className="rounded-sm" data-testid="nq-submit">
            {loading ? "…" : "Crea preventivo"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
