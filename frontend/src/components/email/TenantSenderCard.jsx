import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

const DOMAIN_CLASS = { VERIFIED: "bg-emerald-600 text-white", PENDING_VERIFICATION: "bg-amber-500 text-white", FAILED: "bg-red-600 text-white", SUSPENDED: "bg-red-700 text-white", NOT_CONFIGURED: "bg-zinc-400 text-white" };
const FIELDS = [["from_name", "Nome mittente (display name)"], ["managed_local_part", "Local part mittente gestito (slug@dominio Panorama)"], ["custom_from_local_part", "Local part dominio custom (es. preventivi)"], ["reply_to", "Reply-To"], ["support_email", "Email supporto"], ["sales_email", "Email commerciale"]];

export function TenantSenderCard() {
  const qc = useQueryClient();
  const { data: s, isLoading } = useQuery({ queryKey: ["tenant-email-settings"], queryFn: async () => (await api.get("/tenant-email/settings")).data });
  const [f, setF] = React.useState({});
  const [domain, setDomain] = React.useState("");
  React.useEffect(() => { if (s) setF(Object.fromEntries(FIELDS.map(([k]) => [k, s[k] || ""]).concat([["signature", s.signature || ""], ["sender_mode", s.sender_mode]]))); }, [s]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["tenant-email-settings"] });
  const onErr = (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message, { duration: 8000 });
  const save = useMutation({ mutationFn: async (body) => (await api.patch("/tenant-email/settings", body)).data, onSuccess: () => { toast.success("Impostazioni mittente salvate"); refresh(); }, onError: onErr });
  const addDomain = useMutation({ mutationFn: async () => (await api.post("/tenant-email/domain", { domain })).data, onSuccess: () => { toast.success("Dominio registrato: configura i record DNS"); refresh(); }, onError: onErr });
  const verify = useMutation({ mutationFn: async () => (await api.post("/tenant-email/domain/verify")).data, onSuccess: (d) => { toast[d.domain_status === "VERIFIED" ? "success" : "info"](`Stato dominio: ${d.domain_status}`); refresh(); }, onError: onErr });
  const removeDomain = useMutation({ mutationFn: async () => (await api.delete("/tenant-email/domain")).data, onSuccess: () => { toast.success("Dominio rimosso"); refresh(); }, onError: onErr });
  if (isLoading || !s) return <Card className="rounded-sm p-4 text-sm text-muted-foreground">Caricamento…</Card>;
  const eff = s.effective_sender || {};
  return (
    <div className="space-y-4" data-testid="tenant-sender-card">
      <Card className="rounded-sm border-border p-5 space-y-3">
        <div className="overline">Mittente del tenant · provider {s.provider}</div>
        {!s.provider_configured && <div className="text-xs font-bold text-destructive" data-testid="tenant-provider-blocked">RESEND_CONFIGURATION = BLOCKED_BY_SECRET — nessuna email può essere inviata (nessun fallback mock silenzioso).</div>}
        {s.provider_configured && !s.webhook_configured && <div className="text-xs font-bold text-amber-700" data-testid="tenant-webhook-missing">Webhook Resend non configurato: gli stati CONSEGNATA/BOUNCE non verranno aggiornati.</div>}
        <div className="text-sm" data-testid="tenant-effective-sender">Mittente effettivo: <b>{eff.from_name}</b> &lt;{eff.from_email || "non risolvibile"}&gt; · Reply-To {eff.reply_to || "—"} <Badge variant="outline" className="rounded-sm ml-1 text-[10px]">{eff.sender_mode}</Badge>{eff.fallback_applied && <span className="ml-2 text-[10px] text-amber-700">fallback Panorama attivo (dominio custom non verificato)</span>}</div>
        <div className="grid grid-cols-2 gap-3">
          {FIELDS.map(([k, label]) => <div key={k}><Label className="text-[10px] uppercase">{label}</Label><Input value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="rounded-sm h-9" data-testid={`tenant-field-${k}`} /></div>)}
        </div>
        <div><Label className="text-[10px] uppercase">Firma</Label><Textarea rows={2} value={f.signature || ""} onChange={(e) => setF({ ...f, signature: e.target.value })} className="rounded-sm" data-testid="tenant-field-signature" /></div>
        <div className="flex items-center gap-2">
          <Label className="text-[10px] uppercase">Modalità mittente</Label>
          <Button size="sm" variant={f.sender_mode === "PANORAMA_MANAGED" ? "default" : "outline"} className="rounded-sm" onClick={() => setF({ ...f, sender_mode: "PANORAMA_MANAGED" })} data-testid="tenant-mode-managed">Gestito Panorama ({s.managed_domain || "dominio non configurato"})</Button>
          <Button size="sm" variant={f.sender_mode === "CUSTOM_VERIFIED_DOMAIN" ? "default" : "outline"} className="rounded-sm" disabled={s.domain_status !== "VERIFIED"} onClick={() => setF({ ...f, sender_mode: "CUSTOM_VERIFIED_DOMAIN" })} data-testid="tenant-mode-custom">Dominio verificato</Button>
          <Button size="sm" className="rounded-sm ml-auto" onClick={() => save.mutate(Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v])))} data-testid="tenant-sender-save">Salva</Button>
        </div>
      </Card>
      <Card className="rounded-sm border-border p-5 space-y-3" data-testid="tenant-domain-card">
        <div className="flex items-center gap-2"><div className="overline">Dominio personalizzato</div><Badge className={`rounded-sm text-[10px] ${DOMAIN_CLASS[s.domain_status] || ""}`} data-testid="tenant-domain-status">{s.domain_status}</Badge>{s.custom_domain && <span className="font-mono-plex text-sm">{s.custom_domain}</span>}</div>
        {!s.custom_domain ? (
          <div className="flex gap-2 items-end"><div className="flex-1"><Label className="text-[10px] uppercase">Dominio (es. infissiexpress.it)</Label><Input value={domain} onChange={(e) => setDomain(e.target.value)} className="rounded-sm h-9" data-testid="tenant-domain-input" /></div><Button size="sm" className="rounded-sm h-9" disabled={!domain} onClick={() => addDomain.mutate()} data-testid="tenant-domain-add">Registra dominio</Button></div>
        ) : (
          <>
            <div className="text-xs text-muted-foreground">Aggiungi questi record DNS presso il tuo provider. Solo con stato VERIFIED il dominio può essere usato come mittente. DMARC: <b data-testid="tenant-dmarc-status">{s.dmarc_status === "CONFIGURED" ? "CONFIGURED" : "RECOMMENDED / MISSING"}</b></div>
            <table className="w-full text-xs" data-testid="tenant-dns-records"><thead><tr className="text-left text-muted-foreground uppercase text-[10px]"><th>Record</th><th>Tipo</th><th>Nome</th><th>Valore</th><th>Stato</th></tr></thead><tbody>
              {(s.dns_records || []).map((r, i) => <tr key={i} className="border-t"><td>{r.record}</td><td>{r.type}</td><td className="font-mono-plex break-all">{r.name}</td><td className="font-mono-plex break-all max-w-[320px]">{r.value}</td><td>{r.status}</td></tr>)}
            </tbody></table>
            <div className="flex gap-2"><Button size="sm" className="rounded-sm" onClick={() => verify.mutate()} data-testid="tenant-domain-verify">Verifica ora</Button><Button size="sm" variant="outline" className="rounded-sm" onClick={() => { if (window.confirm("Rimuovere il dominio personalizzato?")) removeDomain.mutate(); }} data-testid="tenant-domain-remove">Rimuovi</Button></div>
          </>
        )}
        <div className="text-[10px] text-muted-foreground">CUSTOM SMTP / MAILBOX per tenant: NOT_IN_SCOPE in questa release.</div>
      </Card>
    </div>
  );
}
