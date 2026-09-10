import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import {
  EnvelopeSimple, PaperPlaneTilt, ShieldCheck, Warning, CheckCircle,
  XCircle, Wrench, ArrowClockwise, Copy,
} from "@phosphor-icons/react";

const TEMPLATE_CODES = [
  "USER_INVITATION", "PASSWORD_RESET", "QUOTE_SENT",
  "CONTRACT_SIGNATURE_REQUEST", "CONTRACT_SIGNED", "NEW_LEAD_NOTIFICATION",
  "PAYMENT_REMINDER", "ORDER_STATUS_UPDATE", "SUPPORT_TICKET_UPDATE",
  "AI_CFO_ALERT", "DAILY_SUMMARY",
];

function StatusBadge({ ok, label, warning }) {
  const variant = ok ? "default" : warning ? "secondary" : "destructive";
  return <Badge variant={variant} data-testid={`status-${label}`}>{label}</Badge>;
}

export default function EmailSettingsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState("config");

  const cfg = useQuery({
    queryKey: ["email-settings"],
    queryFn: async () => (await api.get("/email-settings")).data,
  });

  const templates = useQuery({
    queryKey: ["email-templates"],
    queryFn: async () => (await api.get("/email-settings/templates")).data,
  });

  const dns = useQuery({
    queryKey: ["email-dns"],
    queryFn: async () => (await api.get("/email-settings/dns-check")).data,
    enabled: tab === "dns",
  });

  return (
    <div className="space-y-8" data-testid="email-settings-page">
      <div>
        <div className="overline text-muted-foreground">Sistema email SMTP</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">
          Impostazioni email
        </h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-2xl">
          Configurazione SMTP SiteGround, template personalizzabili, verifica DNS
          (SPF/DKIM/DMARC) e invio di test. La password è caricata solo dai Production Secrets
          e non è mai esposta.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="config" data-testid="tab-config">Configurazione</TabsTrigger>
          <TabsTrigger value="test" data-testid="tab-test">Invio di test</TabsTrigger>
          <TabsTrigger value="dns" data-testid="tab-dns">Verifica DNS</TabsTrigger>
          <TabsTrigger value="templates" data-testid="tab-templates">Template</TabsTrigger>
        </TabsList>

        {/* -------- CONFIG -------- */}
        <TabsContent value="config" className="space-y-4">
          <ConfigCard cfg={cfg.data} isLoading={cfg.isLoading} />
        </TabsContent>

        {/* -------- TEST -------- */}
        <TabsContent value="test">
          <TestSendCard cfg={cfg.data} />
        </TabsContent>

        {/* -------- DNS -------- */}
        <TabsContent value="dns">
          <DnsCheckCard dns={dns.data} loading={dns.isLoading} onRefresh={() => dns.refetch()} />
        </TabsContent>

        {/* -------- TEMPLATES -------- */}
        <TabsContent value="templates">
          <TemplatesCard
            items={templates.data?.items || []}
            onSaved={() => {
              qc.invalidateQueries({ queryKey: ["email-templates"] });
            }}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---------------------------------------------------------------- Config
function ConfigCard({ cfg, isLoading }) {
  if (isLoading || !cfg) return <Card className="p-6">Caricamento…</Card>;
  const ok = cfg.is_configured;
  return (
    <Card className="p-6 rounded-sm border-border space-y-6" data-testid="config-card">
      <div className="flex items-start gap-4">
        <div className={`w-12 h-12 rounded-sm flex items-center justify-center ${
          ok ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"
        }`}>
          {ok ? <CheckCircle size={28} weight="bold" /> : <Warning size={28} weight="bold" />}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold">{ok ? "SMTP configurato" : "SMTP non configurato"}</h2>
            <StatusBadge ok={ok} label={ok ? "operativo" : "SMTP_NOT_CONFIGURED"} warning={!ok} />
          </div>
          <p className="text-sm text-muted-foreground mt-1" data-testid="smtp-status-desc">
            {ok
              ? "Il servizio SMTP è pronto per inviare email."
              : "Manca MAIL_PASSWORD nei Production Secrets. Le email vengono registrate ma non inviate."}
          </p>
        </div>
      </div>

      {!ok && (
        <Alert className="rounded-sm bg-amber-50 border-amber-200" data-testid="smtp-warn">
          <AlertDescription className="text-sm text-amber-900">
            <b>Come completare la configurazione:</b>
            <ol className="list-decimal pl-6 mt-2 space-y-1">
              <li>Apri il pannello di deploy e vai su <b>Secrets</b>.</li>
              <li>Aggiungi la variabile <code className="bg-white/70 px-1 rounded">MAIL_PASSWORD</code> con la password SMTP di SiteGround per <code className="bg-white/70 px-1 rounded">{cfg.smtp_user}</code>.</li>
              <li>Riavvia il backend (o attendi il redeploy automatico).</li>
              <li>Torna qui e usa "Invio di test" per verificare.</li>
            </ol>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <KV label="Host SMTP" value={cfg.smtp_host} testid="cfg-host" />
        <KV label="Porta" value={cfg.smtp_port} testid="cfg-port" />
        <KV label="Sicurezza" value={cfg.smtp_security.toUpperCase()} testid="cfg-sec" />
        <KV label="Provider" value={cfg.provider_name} testid="cfg-provider" />
        <KV label="Username SMTP" value={cfg.smtp_user} testid="cfg-user" />
        <KV label="Password" value={cfg.password_configured ? "•••••••• (dai Secrets)" : "— non impostata —"} testid="cfg-pass" />
        <KV label="Mittente (From)" value={`${cfg.mail_from_name} <${cfg.mail_from}>`} testid="cfg-from" />
        <KV label="Reply-To" value={cfg.reply_to || "—"} testid="cfg-replyto" />
        <KV label="Modalità consegna" value={
          <Badge variant={cfg.delivery_mode === "live" ? "default" : "secondary"} className="rounded-sm">
            {cfg.delivery_mode === "test" ? "TEST (intercetto abilitato)" : "LIVE"}
          </Badge>
        } testid="cfg-mode" />
        <KV label="Redirect di test" value={cfg.test_redirect_to || "—"} testid="cfg-redirect" />
      </div>

      {cfg.delivery_mode === "test" && (
        <Alert className="rounded-sm bg-blue-50 border-blue-200" data-testid="test-mode-notice">
          <AlertDescription className="text-sm text-blue-900">
            <b>Modalità test attiva</b> — Tutte le email inviate dal sistema vengono automaticamente
            reindirizzate a <b>{cfg.test_redirect_to}</b>. L'indirizzo originario è preservato
            nell'oggetto e nel log con etichetta <code className="bg-white px-1 rounded">[TEST - Destinatario originale: ...]</code>.
            Nessun cliente riceverà email accidentali.
          </AlertDescription>
        </Alert>
      )}
    </Card>
  );
}

function KV({ label, value, testid }) {
  return (
    <div className="space-y-1">
      <div className="text-xs uppercase tracking-wide text-muted-foreground font-mono-plex">{label}</div>
      <div className="text-sm font-medium" data-testid={testid}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------- Test send
function TestSendCard({ cfg }) {
  const { user } = useAuth();
  // PO msg 406 §18: destinatario predefinito = email dell'admin loggato (modificabile), nessun indirizzo hardcoded
  const [to, setTo] = useState(user?.email || "");
  const [template, setTemplate] = useState("USER_INVITATION");
  const [lastResult, setLastResult] = useState(null);

  const send = useMutation({
    mutationFn: async () => (await api.post("/email-settings/test", { to, template })).data,
    onSuccess: (data) => {
      setLastResult(data);
      if (data.status === "sent" || data.status === "test_intercepted") {
        toast.success("Email di test accettata dal server SMTP");
      } else if (data.status === "configuration_required") {
        toast.warning("SMTP non configurato — email registrata ma NON inviata");
      } else {
        toast.error(`Invio non riuscito: ${data.error || data.status}`);
      }
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || "Errore"),
  });

  return (
    <Card className="p-6 rounded-sm border-border space-y-6" data-testid="test-send-card">
      <div>
        <h2 className="text-xl font-bold">Invio email di test</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Rate limit: max 5 invii ogni 5 minuti per utente.
          {cfg?.delivery_mode === "test" && (
            <> L'email verrà consegnata a <b>{cfg.test_redirect_to}</b> (intercetto attivo).</>
          )}
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <Label>Destinatario originale</Label>
          <Input
            data-testid="test-to-input"
            placeholder="destinatario@esempio.com"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <div>
          <Label>Template</Label>
          <Select value={template} onValueChange={setTemplate}>
            <SelectTrigger data-testid="test-template-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {TEMPLATE_CODES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>
      <Button
        onClick={() => send.mutate()}
        disabled={!to || send.isPending}
        data-testid="test-send-btn"
      >
        <PaperPlaneTilt size={16} className="mr-2" />
        {send.isPending ? "Invio…" : "Invia email di test"}
      </Button>

      {lastResult && (
        <div className="border-t pt-4 space-y-2 text-sm" data-testid="test-result">
          <div className="font-bold flex items-center gap-2">
            Risultato invio
            <Badge variant={
              lastResult.status === "sent" || lastResult.status === "test_intercepted"
                ? "default" : "destructive"
            } className="rounded-sm">{lastResult.status}</Badge>
          </div>
          <KV label="Log ID" value={<code className="text-xs">{lastResult.id}</code>} />
          <KV label="Destinatario originale" value={lastResult.original_to} />
          <KV label="Destinatario effettivo" value={lastResult.actual_to} />
          <KV label="Delivery mode" value={lastResult.delivery_mode} />
          <KV label="Provider" value={lastResult.provider} />
          <KV label="Data/ora" value={lastResult.sent_at || new Date().toLocaleString("it-IT")} />
          {lastResult.provider_message_id && <KV label="Provider message ID" value={<code className="text-xs">{lastResult.provider_message_id}</code>} />}
          <KV label="Consegna" value={lastResult.delivery_status || "NON VERIFICABILE (accettazione provider ≠ consegna)"} />
          <KV label="Tentativi" value={lastResult.attempt_count} />
          {lastResult.error && (
            <KV label="Errore" value={<code className="text-xs text-red-600">{lastResult.error}</code>} />
          )}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- DNS check
function DnsCheckCard({ dns, loading, onRefresh }) {
  return (
    <Card className="p-6 rounded-sm border-border space-y-6" data-testid="dns-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <ShieldCheck size={22} /> Verifica autenticazione DNS
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Controllo SPF, DKIM e DMARC del dominio mittente.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={onRefresh} data-testid="dns-refresh">
          <ArrowClockwise size={14} className="mr-2" /> Ricontrolla
        </Button>
      </div>

      {loading && <div className="text-sm text-muted-foreground">Interrogazione DNS in corso…</div>}
      {!loading && dns && (
        <div className="space-y-4">
          <KV label="Dominio verificato" value={dns.domain} testid="dns-domain" />
          <DnsRow name="SPF" res={dns.spf} testid="dns-spf" />
          <DnsRow name="DKIM" res={dns.dkim} testid="dns-dkim">
            <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-1 text-xs font-mono-plex">
              {(dns.dkim.results || []).map((r) => (
                <div key={r.selector} className={r.found ? "text-emerald-700" : "text-muted-foreground"}>
                  {r.found ? "✓" : "·"} {r.selector}
                </div>
              ))}
            </div>
          </DnsRow>
          <DnsRow name="DMARC" res={dns.dmarc} testid="dns-dmarc" />
        </div>
      )}
    </Card>
  );
}

function DnsRow({ name, res, testid, children }) {
  return (
    <div className="border-l-4 pl-4 py-2 rounded-sm" style={{ borderColor: res.found ? "#059669" : "#D97706" }} data-testid={testid}>
      <div className="flex items-center gap-3">
        {res.found ? <CheckCircle size={20} className="text-emerald-600" weight="bold" /> : <Warning size={20} className="text-amber-600" weight="bold" />}
        <span className="font-bold">{name}</span>
        <Badge variant={res.found ? "default" : "secondary"} className="rounded-sm">
          {res.found ? "OK" : "MANCANTE"}
        </Badge>
      </div>
      <div className="text-xs text-muted-foreground mt-1">{res.status_message}</div>
      {res.value && (
        <code className="mt-2 block text-xs bg-muted/50 p-2 rounded break-all font-mono-plex">{res.value}</code>
      )}
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- Templates
function TemplatesCard({ items, onSaved }) {
  const [selected, setSelected] = useState(items[0]?.code || "USER_INVITATION");
  const current = items.find((i) => i.code === selected) || items[0];
  const qc = useQueryClient();

  const [subject, setSubject] = useState(current?.subject || "");
  const [htmlBody, setHtmlBody] = useState(current?.html_body || "");
  const [textBody, setTextBody] = useState(current?.text_body || "");
  const [dirty, setDirty] = useState(false);

  React.useEffect(() => {
    if (current) {
      setSubject(current.subject);
      setHtmlBody(current.html_body);
      setTextBody(current.text_body);
      setDirty(false);
    }
  }, [selected, current?.version]);

  const save = useMutation({
    mutationFn: async () => (await api.patch(`/email-settings/templates/${selected}`, {
      subject, html_body: htmlBody, text_body: textBody,
    })).data,
    onSuccess: () => { toast.success("Template salvato"); onSaved(); setDirty(false); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  const reset = useMutation({
    mutationFn: async () => (await api.post(`/email-settings/templates/${selected}/reset`)).data,
    onSuccess: () => { toast.success("Personalizzazione rimossa — usato template di sistema"); onSaved(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  if (!current) return <Card className="p-6">Nessun template disponibile.</Card>;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      <Card className="p-4 rounded-sm border-border" data-testid="template-list">
        <div className="text-xs uppercase text-muted-foreground font-mono-plex mb-2">Template</div>
        <div className="space-y-1">
          {items.map((it) => (
            <button
              key={it.code}
              onClick={() => setSelected(it.code)}
              className={`w-full text-left px-3 py-2 rounded-sm text-sm ${
                selected === it.code ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
              data-testid={`template-item-${it.code}`}
            >
              <div className="font-bold">{it.code}</div>
              <div className="text-xs opacity-80 truncate">{it.description}</div>
              {it.is_custom && <Badge variant="outline" className="mt-1 rounded-sm text-[10px]">Personalizzato v{it.version}</Badge>}
            </button>
          ))}
        </div>
      </Card>

      <Card className="p-6 rounded-sm border-border lg:col-span-3 space-y-4" data-testid="template-editor">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold">{current.code}</h3>
              {current.is_custom
                ? <Badge className="rounded-sm">Personalizzato v{current.version}</Badge>
                : <Badge variant="secondary" className="rounded-sm">Sistema v{current.version}</Badge>}
            </div>
            <p className="text-sm text-muted-foreground">{current.description}</p>
          </div>
          {current.is_custom && (
            <Button size="sm" variant="outline" onClick={() => reset.mutate()} data-testid="template-reset-btn">
              <Wrench size={14} className="mr-2" /> Ripristina sistema
            </Button>
          )}
        </div>

        <div>
          <Label>Oggetto</Label>
          <Input
            data-testid="template-subject-input"
            value={subject}
            onChange={(e) => { setSubject(e.target.value); setDirty(true); }}
          />
        </div>
        <div>
          <Label>Corpo HTML (Jinja2)</Label>
          <Textarea
            rows={10} data-testid="template-html-input"
            value={htmlBody}
            onChange={(e) => { setHtmlBody(e.target.value); setDirty(true); }}
            className="font-mono-plex text-xs"
          />
        </div>
        <div>
          <Label>Corpo testuale</Label>
          <Textarea
            rows={6} data-testid="template-text-input"
            value={textBody}
            onChange={(e) => { setTextBody(e.target.value); setDirty(true); }}
            className="font-mono-plex text-xs"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending} data-testid="template-save-btn">
            {save.isPending ? "Salvataggio…" : "Salva modifiche"}
          </Button>
          {dirty && <span className="text-xs text-amber-700">Modifiche non salvate</span>}
        </div>

        <div className="border-t pt-4">
          <div className="text-xs uppercase text-muted-foreground font-mono-plex mb-2">Anteprima HTML</div>
          <div className="bg-muted/40 p-4 rounded-sm max-h-[400px] overflow-auto" data-testid="template-preview">
            <div dangerouslySetInnerHTML={{ __html: htmlBody }} />
          </div>
        </div>
      </Card>
    </div>
  );
}
