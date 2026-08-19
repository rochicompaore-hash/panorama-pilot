import React, { useState } from "react";
import { DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

/**
 * NewCustomerDialog — creazione anagrafica cliente con UI condizionale
 * PRIVATE vs COMPANY (Milestone 1 Part 2 — Enerhia Operating Core).
 */
export default function NewCustomerDialog({ onSubmit, loading, initial }) {
  const [type, setType] = useState(initial?.customer_type || "PRIVATE");
  const [f, setF] = useState({
    first_name: "", last_name: "", company_name: "",
    email: "", phone: "", whatsapp: "",
    pec: "", sdi_code: "", vat_number: "", tax_code: "",
    contact_person: { first_name: "", last_name: "", role: "", phone: "", email: "" },
    address: { street: "", zip_code: "", city: "", province: "", country: "IT" },
    ...(initial || {}),
  });

  const upd = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const updAddr = (k, v) => setF((x) => ({ ...x, address: { ...x.address, [k]: v } }));
  const updCP = (k, v) => setF((x) => ({ ...x, contact_person: { ...x.contact_person, [k]: v } }));

  const submit = (e) => {
    e.preventDefault();
    const payload = { customer_type: type };
    if (type === "PRIVATE") {
      Object.assign(payload, {
        first_name: f.first_name.trim(), last_name: f.last_name.trim(),
        email: f.email || null, phone: f.phone || null, whatsapp: f.whatsapp || null,
        tax_code: f.tax_code || null,
        address: f.address,
      });
    } else {
      Object.assign(payload, {
        company_name: f.company_name.trim(),
        email: f.email || null, phone: f.phone || null,
        vat_number: f.vat_number || null, tax_code: f.tax_code || null,
        pec: f.pec || null, sdi_code: f.sdi_code || null,
        contact_person: f.contact_person,
        address: f.address,
      });
    }
    onSubmit(payload);
  };

  return (
    <DialogContent className="rounded-sm max-w-2xl" data-testid="new-customer-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo cliente</DialogTitle>
        <DialogDescription>
          Anagrafica strutturata. Codice fiscale/P.IVA opzionali — richiesti solo al contratto.
        </DialogDescription>
      </DialogHeader>

      <Tabs value={type} onValueChange={setType} className="w-full">
        <TabsList className="w-full rounded-sm">
          <TabsTrigger value="PRIVATE" className="flex-1" data-testid="nc-type-private">Privato</TabsTrigger>
          <TabsTrigger value="COMPANY" className="flex-1" data-testid="nc-type-company">Azienda</TabsTrigger>
        </TabsList>

        <form onSubmit={submit} className="space-y-3 mt-4">
          <TabsContent value="PRIVATE" className="space-y-3 mt-0">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Nome *"><Input required value={f.first_name} onChange={(e) => upd("first_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-first" /></Field>
              <Field label="Cognome *"><Input required value={f.last_name} onChange={(e) => upd("last_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-last" /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Email"><Input type="email" value={f.email} onChange={(e) => upd("email", e.target.value)} className="rounded-sm h-10" data-testid="nc-email" /></Field>
              <Field label="Telefono"><Input value={f.phone} onChange={(e) => upd("phone", e.target.value)} className="rounded-sm h-10" data-testid="nc-phone" /></Field>
            </div>
            <Field label="Codice Fiscale (opzionale — obbligatorio al contratto)">
              <Input value={f.tax_code} onChange={(e) => upd("tax_code", e.target.value.toUpperCase())} className="rounded-sm h-10 font-mono-plex" data-testid="nc-tax-code" />
            </Field>
            <AddressBlock a={f.address} onChange={updAddr} label="Residenza" />
          </TabsContent>

          <TabsContent value="COMPANY" className="space-y-3 mt-0">
            <Field label="Ragione sociale *">
              <Input required value={f.company_name} onChange={(e) => upd("company_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-company" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="P.IVA (opzionale — obbligatoria al contratto)">
                <Input value={f.vat_number} onChange={(e) => upd("vat_number", e.target.value.toUpperCase())} className="rounded-sm h-10 font-mono-plex" data-testid="nc-vat" />
              </Field>
              <Field label="Codice Fiscale (opzionale)">
                <Input value={f.tax_code} onChange={(e) => upd("tax_code", e.target.value.toUpperCase())} className="rounded-sm h-10 font-mono-plex" data-testid="nc-tax-code" />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="PEC"><Input type="email" value={f.pec} onChange={(e) => upd("pec", e.target.value)} className="rounded-sm h-10" data-testid="nc-pec" /></Field>
              <Field label="Codice SDI"><Input value={f.sdi_code} onChange={(e) => upd("sdi_code", e.target.value.toUpperCase())} className="rounded-sm h-10 font-mono-plex" data-testid="nc-sdi" /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Email azienda"><Input type="email" value={f.email} onChange={(e) => upd("email", e.target.value)} className="rounded-sm h-10" data-testid="nc-email" /></Field>
              <Field label="Telefono azienda"><Input value={f.phone} onChange={(e) => upd("phone", e.target.value)} className="rounded-sm h-10" data-testid="nc-phone" /></Field>
            </div>
            <div className="border-t border-border pt-3">
              <div className="overline mb-2">Referente</div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Nome"><Input value={f.contact_person.first_name} onChange={(e) => updCP("first_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-cp-first" /></Field>
                <Field label="Cognome"><Input value={f.contact_person.last_name} onChange={(e) => updCP("last_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-cp-last" /></Field>
              </div>
              <div className="grid grid-cols-3 gap-3 mt-2">
                <Field label="Ruolo"><Input value={f.contact_person.role} onChange={(e) => updCP("role", e.target.value)} className="rounded-sm h-10" data-testid="nc-cp-role" /></Field>
                <Field label="Telefono"><Input value={f.contact_person.phone} onChange={(e) => updCP("phone", e.target.value)} className="rounded-sm h-10" data-testid="nc-cp-phone" /></Field>
                <Field label="Email"><Input type="email" value={f.contact_person.email} onChange={(e) => updCP("email", e.target.value)} className="rounded-sm h-10" data-testid="nc-cp-email" /></Field>
              </div>
            </div>
            <AddressBlock a={f.address} onChange={updAddr} label="Sede legale" />
          </TabsContent>

          <DialogFooter className="mt-4">
            <Button type="submit" disabled={loading} className="rounded-sm" data-testid="nc-submit">
              {loading ? "…" : "Crea cliente"}
            </Button>
          </DialogFooter>
        </form>
      </Tabs>
    </DialogContent>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <Label className="overline">{label}</Label>
      {children}
    </div>
  );
}

function AddressBlock({ a, onChange, label }) {
  return (
    <div className="border-t border-border pt-3">
      <div className="overline mb-2">{label}</div>
      <div className="grid grid-cols-4 gap-2">
        <div className="col-span-3">
          <Label className="overline">Via</Label>
          <Input value={a.street || ""} onChange={(e) => onChange("street", e.target.value)} className="rounded-sm h-10" data-testid="nc-addr-street" />
        </div>
        <div>
          <Label className="overline">CAP</Label>
          <Input value={a.zip_code || ""} onChange={(e) => onChange("zip_code", e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="nc-addr-zip" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-2">
        <div className="col-span-2">
          <Label className="overline">Città</Label>
          <Input value={a.city || ""} onChange={(e) => onChange("city", e.target.value)} className="rounded-sm h-10" data-testid="nc-addr-city" />
        </div>
        <div>
          <Label className="overline">Provincia</Label>
          <Input value={a.province || ""} onChange={(e) => onChange("province", e.target.value.toUpperCase())} className="rounded-sm h-10 font-mono-plex" maxLength={2} data-testid="nc-addr-province" />
        </div>
      </div>
    </div>
  );
}
