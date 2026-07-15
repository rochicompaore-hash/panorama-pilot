import React, { useState } from "react";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Phone, EnvelopeSimple, WhatsappLogo, NotePencil } from "@phosphor-icons/react";

/**
 * ActivityLogger — quick-actions logger for calls, notes, emails, WhatsApp.
 * Records to the timeline of the given lead/customer/contact.
 */
export default function ActivityLogger({ leadId, customerId, contactId, defaultPhone, defaultEmail, defaultWhatsApp, onLogged }) {
  const [tab, setTab] = useState("note");
  const [busy, setBusy] = useState(false);

  const submit = async (fn) => {
    setBusy(true);
    try {
      const data = await fn();
      toast.success("Registrato");
      onLogged && onLogged(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="border border-border rounded-sm bg-card" data-testid="activity-logger">
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="w-full rounded-none border-b border-border bg-transparent p-0">
          <TabsTrigger value="note" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[hsl(var(--brand-red))]" data-testid="logger-tab-note">
            <NotePencil size={14} className="mr-1" /> Nota
          </TabsTrigger>
          <TabsTrigger value="call" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[hsl(var(--brand-red))]" data-testid="logger-tab-call">
            <Phone size={14} className="mr-1" /> Chiamata
          </TabsTrigger>
          <TabsTrigger value="email" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[hsl(var(--brand-red))]" data-testid="logger-tab-email">
            <EnvelopeSimple size={14} className="mr-1" /> Email
          </TabsTrigger>
          <TabsTrigger value="whatsapp" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[hsl(var(--brand-red))]" data-testid="logger-tab-whatsapp">
            <WhatsappLogo size={14} className="mr-1" /> WhatsApp
          </TabsTrigger>
        </TabsList>

        <div className="p-4">
          <TabsContent value="note">
            <NoteForm busy={busy} onSubmit={(v) => submit(async () => (await api.post("/activities", { type: "note", subject: v.subject || "Nota", body: v.body, lead_id: leadId, customer_id: customerId, contact_id: contactId })).data)} />
          </TabsContent>
          <TabsContent value="call">
            <CallForm busy={busy} defaultPhone={defaultPhone} onSubmit={(v) => submit(async () => (await api.post("/activities/log-call", { ...v, lead_id: leadId, customer_id: customerId, contact_id: contactId })).data)} />
          </TabsContent>
          <TabsContent value="email">
            <EmailForm busy={busy} defaultEmail={defaultEmail} onSubmit={(v) => submit(async () => (await api.post("/activities/send-email", { ...v, lead_id: leadId, customer_id: customerId, contact_id: contactId })).data)} />
          </TabsContent>
          <TabsContent value="whatsapp">
            <WhatsAppForm busy={busy} defaultPhone={defaultWhatsApp || defaultPhone} onSubmit={(v) => submit(async () => (await api.post("/activities/send-whatsapp", { ...v, lead_id: leadId, customer_id: customerId, contact_id: contactId })).data)} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function NoteForm({ busy, onSubmit }) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onSubmit({ subject, body }); setSubject(""); setBody(""); }}>
      <Input placeholder="Titolo (opzionale)" value={subject} onChange={(e) => setSubject(e.target.value)} className="rounded-sm h-10" data-testid="note-subject" />
      <Textarea required placeholder="Testo nota…" value={body} onChange={(e) => setBody(e.target.value)} rows={3} className="rounded-sm" data-testid="note-body" />
      <Button type="submit" disabled={busy} className="rounded-sm w-full sm:w-auto" data-testid="note-submit">Salva nota</Button>
    </form>
  );
}

function CallForm({ busy, defaultPhone, onSubmit }) {
  const [to, setTo] = useState(defaultPhone || "");
  const [direction, setDirection] = useState("out");
  const [outcome, setOutcome] = useState("answered");
  const [minutes, setMinutes] = useState(0);
  const [notes, setNotes] = useState("");
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onSubmit({ to, direction, outcome, duration_seconds: Number(minutes || 0) * 60, subject: `Chiamata ${direction === "out" ? "in uscita" : "in ingresso"}`, notes }); setNotes(""); }}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><Label className="overline">Numero</Label><Input value={to} onChange={(e) => setTo(e.target.value)} className="rounded-sm h-10" data-testid="call-to" /></div>
        <div><Label className="overline">Durata (min)</Label><Input type="number" min={0} value={minutes} onChange={(e) => setMinutes(e.target.value)} className="rounded-sm h-10" data-testid="call-duration" /></div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><Label className="overline">Direzione</Label>
          <Select value={direction} onValueChange={setDirection}><SelectTrigger className="rounded-sm h-10" data-testid="call-direction"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="out">In uscita</SelectItem><SelectItem value="in">In ingresso</SelectItem></SelectContent></Select>
        </div>
        <div><Label className="overline">Esito</Label>
          <Select value={outcome} onValueChange={setOutcome}><SelectTrigger className="rounded-sm h-10" data-testid="call-outcome"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="answered">Risposta</SelectItem>
              <SelectItem value="no_answer">Nessuna risposta</SelectItem>
              <SelectItem value="callback">Richiamare</SelectItem>
              <SelectItem value="busy">Occupato</SelectItem>
            </SelectContent></Select>
        </div>
      </div>
      <Textarea placeholder="Note della chiamata…" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="rounded-sm" data-testid="call-notes" />
      <Button type="submit" disabled={busy} className="rounded-sm" data-testid="call-submit">Registra chiamata</Button>
    </form>
  );
}

function EmailForm({ busy, defaultEmail, onSubmit }) {
  const [to, setTo] = useState(defaultEmail || "");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onSubmit({ to, subject, body }); setSubject(""); setBody(""); }}>
      <div><Label className="overline">A</Label><Input required value={to} onChange={(e) => setTo(e.target.value)} className="rounded-sm h-10" data-testid="email-to" /></div>
      <div><Label className="overline">Oggetto</Label><Input required value={subject} onChange={(e) => setSubject(e.target.value)} className="rounded-sm h-10" data-testid="email-subject" /></div>
      <Textarea required placeholder="Testo email…" value={body} onChange={(e) => setBody(e.target.value)} rows={5} className="rounded-sm" data-testid="email-body" />
      <Button type="submit" disabled={busy} className="rounded-sm" data-testid="email-submit">Invia (mock)</Button>
    </form>
  );
}

function WhatsAppForm({ busy, defaultPhone, onSubmit }) {
  const [to, setTo] = useState(defaultPhone || "");
  const [body, setBody] = useState("");
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onSubmit({ to, body, subject: "Messaggio WhatsApp" }); setBody(""); }}>
      <div><Label className="overline">Numero (E.164)</Label><Input required value={to} onChange={(e) => setTo(e.target.value)} className="rounded-sm h-10" data-testid="wa-to" /></div>
      <Textarea required placeholder="Messaggio…" value={body} onChange={(e) => setBody(e.target.value)} rows={4} className="rounded-sm" data-testid="wa-body" />
      <Button type="submit" disabled={busy} className="rounded-sm" data-testid="wa-submit">Invia WhatsApp (mock)</Button>
    </form>
  );
}
