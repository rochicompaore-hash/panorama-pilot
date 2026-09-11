import React, { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { customerDisplayName } from "@/components/customers/CustomerTypeBadge";
import { CustomerSearchSelect } from "@/components/quotes/CustomerSearchSelect";

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
export function NewQuoteDialog({ onSubmit, loading, initialCustomer = null }) {
  const [customerId, setCustomerId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [title, setTitle] = useState("");
  const [intervention, setIntervention] = useState("new");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [showNewSite, setShowNewSite] = useState(false);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [pickedCustomer, setPickedCustomer] = useState(initialCustomer);
  useEffect(() => { if (initialCustomer?.id) { setPickedCustomer(initialCustomer); setCustomerId(initialCustomer.id); } }, [initialCustomer?.id]);
  const { data: sites, isFetching: sitesLoading } = useQuery({
    enabled: !!customerId,
    queryKey: ["sites-for-quote", customerId],
    queryFn: async () => (await api.get("/sites", { params: { customer_id: customerId } })).data,
  });

  useEffect(() => { setSiteId(""); }, [customerId]);
  // Cliente con UN solo cantiere valido → preselezione automatica (msg 804 §2)
  useEffect(() => { const it = sites?.items || []; if (customerId && it.length === 1 && !siteId) setSiteId(it[0].id); }, [sites, customerId]);

  const currentCustomer = pickedCustomer;
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
          {initialCustomer ? (
            <div className="rounded-sm border border-emerald-600/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium" data-testid="nq-customer-preselected">
              {initialCustomer.customer_number ? `${initialCustomer.customer_number} · ` : ""}{customerDisplayName(initialCustomer)} <span className="text-emerald-700">✓ selezionato</span>
            </div>
          ) : (
            <CustomerSearchSelect value={pickedCustomer} onChange={(c) => { setPickedCustomer(c); setCustomerId(c?.id || ""); }} />
          )}
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
