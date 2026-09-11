import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const fmtEUR = (n) => (typeof n === "number" ? n.toLocaleString("it-IT", { style: "currency", currency: "EUR", minimumFractionDigits: 2 }) : "—");
const ERR_LABELS = {
  MISSING_CUSTOMER_NAME: "Nome/cognome cliente", MISSING_CUSTOMER_COMPANY_NAME: "Ragione sociale", MISSING_CUSTOMER_TAX_CODE: "Codice fiscale",
  MISSING_CUSTOMER_VAT_NUMBER: "Partita IVA", MISSING_CUSTOMER_ADDRESS: "Indirizzo cliente", MISSING_CUSTOMER_CONTACT: "Email/telefono",
  MISSING_SITE_ADDRESS: "Indirizzo cantiere", MISSING_PRODUCTS: "Prodotti", MISSING_TOTAL: "Totale", MISSING_VAT: "IVA",
  MISSING_PAYMENT_TERMS: "Modalità di pagamento", MISSING_GENERAL_TERMS_VERSION: "Versione Condizioni Generali",
};

export function PresignCheckBanner({ contractId, refreshKey }) {
  const [check, setCheck] = useState(null);
  useEffect(() => { api.get(`/contracts/${contractId}/presign-check`).then((r) => setCheck(r.data)).catch(() => setCheck(null)); }, [contractId, refreshKey]);
  if (!check) return null;
  return check.ok ? (
    <div className="rounded-sm border border-emerald-600/40 bg-emerald-500/10 p-3 text-sm font-bold text-emerald-800" data-testid="presign-ok">
      PRE-FIRMA CHECK OK — Condizioni Generali {check.general_terms_version}
    </div>
  ) : (
    <div className="rounded-sm border border-destructive bg-destructive/10 p-3 text-sm" data-testid="presign-errors">
      <div className="font-bold text-destructive">FIRMA BLOCCATA — dati obbligatori mancanti</div>
      <ul className="mt-1 list-disc pl-5 text-destructive/90">{check.errors.map((e) => <li key={e} data-testid={`presign-err-${e}`}>{ERR_LABELS[e] || e}</li>)}</ul>
    </div>
  );
}

const CUST_FIELDS = [["first_name", "Nome"], ["last_name", "Cognome"], ["company_name", "Ragione sociale"], ["tax_code", "Codice fiscale"],
  ["vat_number", "Partita IVA"], ["email", "Email"], ["phone", "Telefono"], ["pec", "PEC"], ["sdi_code", "Codice SDI"]];
const SITE_FIELDS = [["street", "Via / indirizzo"], ["city", "Comune"], ["zip_code", "CAP"], ["province", "Provincia"], ["floor", "Piano"], ["notes_customer_safe", "Note cantiere"]];

function Field({ label, value, onChange, disabled, testid }) {
  return (
    <label className="block text-xs">
      <span className="text-muted-foreground uppercase tracking-wide">{label}</span>
      <Input value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled} className="mt-1 h-9 rounded-sm" data-testid={testid} />
    </label>
  );
}

export function PartiesEditor({ contract, onSaved }) {
  const snap = contract.quote_snapshot || {};
  const locked = contract.contract_status === "signed" || contract.lifecycle_status === "ACTIVE";
  const [cust, setCust] = useState(snap.customer || {});
  const [site, setSite] = useState(snap.site || {});
  const [askSync, setAskSync] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setCust(snap.customer || {}); setSite(snap.site || {}); }, [contract.id, contract.updated_at]);

  const custDiff = Object.fromEntries(CUST_FIELDS.map(([k]) => k).filter((k) => (cust[k] ?? "") !== ((snap.customer || {})[k] ?? "")).map((k) => [k, cust[k]]));
  const siteDiff = Object.fromEntries(SITE_FIELDS.map(([k]) => k).filter((k) => (site[k] ?? "") !== ((snap.site || {})[k] ?? "")).map((k) => [k, site[k]]));
  const dirty = Object.keys(custDiff).length + Object.keys(siteDiff).length > 0;
  const addr = typeof cust.address === "string" ? cust.address : "";

  const save = async (sync) => {
    setSaving(true);
    try {
      const { data } = await api.patch(`/contracts/${contract.id}/parties`, { customer: custDiff, site: siteDiff, sync_customer: sync });
      toast.success(sync && data.customer_synced ? "Contratto e anagrafica cliente aggiornati" : "Dati aggiornati solo su questo contratto");
      setAskSync(false);
      onSaved?.();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast.error(typeof d === "string" ? d : d?.message || "Errore salvataggio");
    } finally { setSaving(false); }
  };

  return (
    <Card data-testid="contract-parties">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Cliente e cantiere {locked && <Badge className="ml-2 rounded-sm" variant="secondary">FIRMATO — non modificabile</Badge>}</CardTitle>
        {!locked && <Button size="sm" disabled={!dirty || saving} onClick={() => (Object.keys(custDiff).length ? setAskSync(true) : save(false))} data-testid="parties-save">Salva correzioni</Button>}
      </CardHeader>
      <CardContent className="grid md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <div className="text-[10px] font-mono uppercase text-muted-foreground">Dati cliente · {cust.customer_number || cust.code || cust.id?.slice(0, 8)}</div>
          {CUST_FIELDS.map(([k, l]) => <Field key={k} label={l} value={cust[k]} disabled={locked} onChange={(v) => setCust({ ...cust, [k]: v })} testid={`party-customer-${k}`} />)}
          <Field label="Indirizzo" value={addr || (cust.address ? [cust.address.street, cust.address.zip_code, cust.address.city].filter(Boolean).join(", ") : "")} disabled={locked} onChange={(v) => setCust({ ...cust, address: v })} testid="party-customer-address" />
        </div>
        <div className="space-y-2">
          <div className="text-[10px] font-mono uppercase text-muted-foreground">Cantiere · {site.site_number || site.name || "—"}</div>
          {SITE_FIELDS.map(([k, l]) => <Field key={k} label={l} value={site[k]} disabled={locked} onChange={(v) => setSite({ ...site, [k]: v })} testid={`party-site-${k}`} />)}
        </div>
        {(contract.party_changes || []).length > 0 && (
          <div className="md:col-span-2 text-[11px] text-muted-foreground" data-testid="party-changes-audit">
            <div className="font-bold uppercase mb-1">Audit correzioni</div>
            {(contract.party_changes || []).map((c, i) => (
              <div key={i}>{new Date(c.changed_at).toLocaleString("it-IT")} · {c.changed_by_email} · <b>{c.scope}.{c.field}</b>: “{String(c.old_value ?? "—")}” → “{String(c.new_value ?? "—")}” {c.synced_to_customer ? "(anagrafica aggiornata)" : "(solo contratto)"}</div>
            ))}
          </div>
        )}
      </CardContent>
      <Dialog open={askSync} onOpenChange={setAskSync}>
        <DialogContent data-testid="sync-customer-dialog">
          <DialogHeader><DialogTitle>Vuoi aggiornare anche l'anagrafica cliente?</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground pt-3">Campi modificati: {Object.keys(custDiff).join(", ")}. Nessun duplicato verrà creato; la modifica viene registrata nell'audit.</p>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => save(false)} disabled={saving} data-testid="sync-only-contract">Solo questo contratto</Button>
            <Button onClick={() => save(true)} disabled={saving} data-testid="sync-update-customer">Aggiorna anagrafica</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export function QuoteSummaryCard({ contract }) {
  const snap = contract.quote_snapshot || {};
  const eco = snap.economics || {};
  const items = snap.quote_summary?.items || [];
  const pt = eco.payment_terms || snap.payment_terms || {};
  return (
    <Card data-testid="contract-quote-summary">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Oggetto del contratto — preventivo {snap.quote_number}</CardTitle>
        <Badge variant="outline" className="rounded-sm" data-testid="revision-guard-badge">Importi congelati · modifiche = REVISIONE</Badge>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="divide-y">
          {items.map((it, i) => (
            <div key={i} className="py-2" data-testid={`summary-item-${i}`}>
              <div className="flex justify-between font-medium">
                <span>{it.quantity} × {it.description}{it.width_mm && it.height_mm ? ` · ${it.width_mm}×${it.height_mm} mm` : ""}</span>
                <span className="font-mono">{fmtEUR(it.subtotal_line)}</span>
              </div>
              {Object.keys(it.configuration || {}).length > 0 && (
                <div className="text-xs text-muted-foreground">{Object.entries(it.configuration).filter(([, v]) => v != null && typeof v !== "object").map(([k, v]) => `${k}: ${v}`).join(" · ")}</div>
              )}
              {it.services?.length > 0 && <div className="text-xs text-muted-foreground">Servizi: {it.services.map((s) => `${s.label || s.service_code}${s.sale_price_total != null ? ` (${fmtEUR(s.sale_price_total)})` : ""}`).join(" · ")}</div>}
            </div>
          ))}
          {items.length === 0 && <div className="text-muted-foreground py-2">Nessuna riga nel preventivo.</div>}
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-1" data-testid="contract-economics">
            <div className="text-[10px] font-mono uppercase text-muted-foreground">Corrispettivo</div>
            <Row l="Valore commerciale" v={fmtEUR(eco.commercial_subtotal)} />
            {eco.global_discount_amount > 0 && <Row l="Sconto" v={`− ${fmtEUR(eco.global_discount_amount)}`} />}
            {eco.payment_discount_amount > 0 && <Row l="Sconto pagamento anticipato" v={`− ${fmtEUR(eco.payment_discount_amount)}`} />}
            <Row l="Imponibile" v={fmtEUR(eco.subtotal)} bold />
            <Row l={`IVA (${eco.vat_regime?.code || "22"}%)`} v={fmtEUR(eco.vat_amount)} />
            <Row l="Totale" v={fmtEUR(eco.total)} bold />
          </div>
          <div className="space-y-1" data-testid="contract-payment-terms">
            <div className="text-[10px] font-mono uppercase text-muted-foreground">Pagamenti e consegna</div>
            <Row l="Modalità" v={pt.label || pt.code || "—"} />
            {(pt.schedule || []).map((s, i) => <Row key={i} l={s.label || s.description || s.trigger} v={s.percent != null ? `${s.percent}%${s.amount != null ? ` · ${fmtEUR(s.amount)}` : ""}` : fmtEUR(s.amount)} />)}
            {pt.financing_mode && <Row l="Finanziamento" v={pt.financing_mode} />}
            <Row l="Consegna" v={eco.delivery_customer_text || eco.delivery_mode || "—"} />
            <Row l="Condizioni Generali" v={snap.general_terms_version || contract.general_terms_version || "—"} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Row({ l, v, bold }) {
  return <div className={`flex justify-between ${bold ? "font-bold" : ""}`}><span className="text-muted-foreground">{l}</span><span className="font-mono">{v}</span></div>;
}
