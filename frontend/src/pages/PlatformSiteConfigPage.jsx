import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableHead, TableRow, TableHeader, TableBody, TableCell } from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Warning, Info, CheckCircle } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function PlatformSiteConfigPage() {
  const [cfg, setCfg] = useState(null);
  const [leads, setLeads] = useState([]);
  const [recipientDraft, setRecipientDraft] = useState("");

  const load = async () => {
    try {
      const [c, l] = await Promise.all([
        api.get("/platform/site-config"),
        api.get("/platform/site-config/leads"),
      ]);
      setCfg(c.data); setLeads(l.data.items || []);
    } catch (e) { toast.error("Errore caricamento (solo Platform Owner)"); }
  };
  useEffect(() => { load(); }, []);

  const save = async (updates) => {
    try {
      await api.patch("/platform/site-config", updates);
      toast.success("Configurazione salvata");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Errore salvataggio"); }
  };

  const addRecipient = () => {
    if (!recipientDraft) return;
    const next = [...(cfg.lead_notification_recipients || []), recipientDraft];
    save({ lead_notification_recipients: next });
    setRecipientDraft("");
  };
  const removeRecipient = (email) => {
    const next = (cfg.lead_notification_recipients || []).filter(x => x !== email);
    save({ lead_notification_recipients: next });
  };

  if (!cfg) return <div>Caricamento…</div>;

  const emailConfigured = cfg.email_status === "configured";

  return (
    <div className="space-y-6" data-testid="platform-site-config">
      <div>
        <div className="overline text-muted-foreground">Platform Owner</div>
        <h1 className="font-display text-3xl font-black tracking-tight">Configurazione sito pubblico</h1>
        <p className="text-sm text-muted-foreground mt-1">Landing page, form lead, destinatari email, pacchetti pubblici.</p>
      </div>

      {!emailConfigured && (
        <Alert variant="destructive" data-testid="alert-email-not-configured">
          <Warning size={16}/>
          <AlertDescription>
            <strong>Configurazione richiesta:</strong> aggiungi almeno un indirizzo email valido nella sezione
            "Destinatari lead" per attivare le notifiche. I lead vengono comunque salvati nel CRM.
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general" data-testid="tab-cfg-general">Generale</TabsTrigger>
          <TabsTrigger value="content" data-testid="tab-cfg-content">Contenuti</TabsTrigger>
          <TabsTrigger value="emails" data-testid="tab-cfg-emails">Destinatari lead</TabsTrigger>
          <TabsTrigger value="leads" data-testid="tab-cfg-leads">Lead ricevuti ({leads.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card className="p-5 space-y-3">
            <div><Label>Nome prodotto</Label>
              <Input defaultValue={cfg.product_name} onBlur={e => save({product_name: e.target.value})} data-testid="cfg-product-name"/>
            </div>
            <div><Label>Logo URL</Label>
              <Input defaultValue={cfg.logo_url || ""} onBlur={e => save({logo_url: e.target.value})}/>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
              <div><Label>Telefono commerciale</Label>
                <Input defaultValue={cfg.commercial_phone || ""} onBlur={e => save({commercial_phone: e.target.value})}/>
              </div>
              <div><Label>WhatsApp commerciale</Label>
                <Input defaultValue={cfg.commercial_whatsapp || ""} onBlur={e => save({commercial_whatsapp: e.target.value})}/>
              </div>
            </div>
            <div><Label>Indirizzo azienda</Label>
              <Input defaultValue={cfg.company_address || ""} onBlur={e => save({company_address: e.target.value})}/>
            </div>
            <div className="grid md:grid-cols-3 gap-3">
              <div><Label>Privacy Policy URL</Label>
                <Input defaultValue={cfg.privacy_policy_url || ""} onBlur={e => save({privacy_policy_url: e.target.value})}/>
              </div>
              <div><Label>Cookie Policy URL</Label>
                <Input defaultValue={cfg.cookie_policy_url || ""} onBlur={e => save({cookie_policy_url: e.target.value})}/>
              </div>
              <div><Label>Termini URL</Label>
                <Input defaultValue={cfg.terms_url || ""} onBlur={e => save({terms_url: e.target.value})}/>
              </div>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="content">
          <Card className="p-5 space-y-3">
            <div><Label>Hero title</Label>
              <Textarea rows={2} defaultValue={cfg.hero_title} onBlur={e => save({hero_title: e.target.value})} data-testid="cfg-hero-title"/>
            </div>
            <div><Label>Hero subtitle</Label>
              <Textarea rows={2} defaultValue={cfg.hero_subtitle} onBlur={e => save({hero_subtitle: e.target.value})}/>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
              <div><Label>CTA principale</Label>
                <Input defaultValue={cfg.cta_primary_text} onBlur={e => save({cta_primary_text: e.target.value})} data-testid="cfg-cta-primary"/>
              </div>
              <div><Label>CTA secondaria (login)</Label>
                <Input defaultValue={cfg.cta_secondary_text} onBlur={e => save({cta_secondary_text: e.target.value})}/>
              </div>
            </div>
            <div><Label>Sottotesto CTA</Label>
              <Textarea rows={2} defaultValue={cfg.cta_primary_subtitle} onBlur={e => save({cta_primary_subtitle: e.target.value})}/>
            </div>
            <div className="grid md:grid-cols-2 gap-3">
              <div><Label>SEO title</Label>
                <Input defaultValue={cfg.seo_title || ""} onBlur={e => save({seo_title: e.target.value})}/>
              </div>
              <div><Label>SEO description</Label>
                <Input defaultValue={cfg.seo_description || ""} onBlur={e => save({seo_description: e.target.value})}/>
              </div>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="emails">
          <Card className="p-5 space-y-4">
            <div>
              <Label>Destinatari email lead landing (uno per volta)</Label>
              <div className="flex gap-2 mt-2">
                <Input type="email" placeholder="nome@dominio.it" value={recipientDraft} onChange={e => setRecipientDraft(e.target.value)} data-testid="cfg-recipient-input"/>
                <Button onClick={addRecipient} data-testid="btn-add-recipient">Aggiungi</Button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Solo indirizzi email tecnicamente validi verranno accettati. Indirizzi malformati non vengono usati.
              </p>
            </div>
            <div className="space-y-1">
              {(cfg.lead_notification_recipients || []).map(r => (
                <div key={r} className="flex items-center justify-between p-2 border rounded" data-testid={`recipient-${r}`}>
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle size={14} className="text-green-600"/>{r}
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => removeRecipient(r)}>Rimuovi</Button>
                </div>
              ))}
              {(cfg.lead_notification_recipients || []).length === 0 && (
                <div className="text-sm text-muted-foreground">Nessun destinatario configurato. I lead vengono salvati ma non emailati.</div>
              )}
            </div>
            <div>
              <Label>Mittente email</Label>
              <Input defaultValue={cfg.email_sender || ""} onBlur={e => save({email_sender: e.target.value})} placeholder="noreply@infissiexpress.com"/>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Badge className={emailConfigured ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"} data-testid="cfg-email-status">
                {emailConfigured ? "Configurato" : "Configurazione richiesta"}
              </Badge>
              <span className="text-muted-foreground">{cfg.email_status_note}</span>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="leads">
          <Card className="p-5">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Data</TableHead><TableHead>Nome</TableHead><TableHead>Azienda</TableHead>
                <TableHead>Email/Telefono</TableHead><TableHead>Volume</TableHead>
                <TableHead>Moduli</TableHead><TableHead>Pacchetto</TableHead>
                <TableHead>Notifica</TableHead><TableHead>CRM</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {leads.map(l => (
                  <TableRow key={l.id} data-testid={`landing-lead-${l.id}`}>
                    <TableCell className="text-xs">{new Date(l.created_at).toLocaleString("it-IT")}</TableCell>
                    <TableCell>{l.first_name} {l.last_name}</TableCell>
                    <TableCell>{l.company_name}</TableCell>
                    <TableCell className="text-xs">
                      <div>{l.email}</div>
                      <div className="text-muted-foreground">{l.phone || "—"}</div>
                    </TableCell>
                    <TableCell><Badge variant="outline" className="text-[10px]">{l.revenue_range || "—"}</Badge></TableCell>
                    <TableCell className="text-xs">{(l.interested_module_codes || []).length} sel.</TableCell>
                    <TableCell><Badge>{l.suggested_package_code}</Badge></TableCell>
                    <TableCell>
                      <Badge variant="outline" className={
                        l.email_notification_status === "sent" ? "text-green-700" :
                        l.email_notification_status === "pending_configuration" ? "text-amber-700" : ""
                      }>{l.email_notification_status}</Badge>
                    </TableCell>
                    <TableCell>
                      {l.crm_lead_id ? (
                        <Button size="sm" variant="ghost" onClick={() => window.location.href = `/leads/${l.crm_lead_id}`}>
                          Vai al lead
                        </Button>
                      ) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
                {leads.length === 0 && <TableRow><TableCell colSpan={9} className="text-center text-muted-foreground py-6">Nessuna richiesta ricevuta</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
