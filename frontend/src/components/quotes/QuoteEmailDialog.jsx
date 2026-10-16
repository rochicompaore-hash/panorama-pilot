import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { PaperPlaneTilt } from "@phosphor-icons/react";

export const DELIVERY_LABEL = { queued: "IN CODA", provider_accepted: "INVIATA", delivered: "CONSEGNATA", deferred: "IN RITARDO", bounced: "BOUNCE", failed: "ERRORE", complained: "SPAM" };
const DELIVERY_CLASS = { delivered: "bg-emerald-600 text-white", provider_accepted: "bg-sky-600 text-white", queued: "bg-zinc-400 text-white", deferred: "bg-amber-500 text-white", bounced: "bg-red-600 text-white", failed: "bg-red-600 text-white", complained: "bg-red-700 text-white" };
const fmtTs = (v) => (v ? new Date(v).toLocaleString("it-IT") : "—");

export function DeliveryBadge({ status, testId }) {
  return <Badge className={`rounded-sm text-[10px] ${DELIVERY_CLASS[status] || ""}`} data-testid={testId}>{DELIVERY_LABEL[status] || status || "—"}</Badge>;
}

export function QuoteEmailDialog({ quoteId, open, onOpenChange, latestPdf, onSent }) {
  const qc = useQueryClient();
  const [message, setMessage] = React.useState("");
  const { data: p, isLoading } = useQuery({ queryKey: ["quote-email-preview", quoteId, latestPdf?.id], enabled: open, queryFn: async () => (await api.get(`/quotes/${quoteId}/email/preview`, { params: { pdf_id: latestPdf?.id } })).data });
  const send = useMutation({
    mutationFn: async () => (await api.post(`/quotes/${quoteId}/email/send`, { pdf_id: latestPdf?.id, message: message || null })).data,
    onSuccess: (d) => { toast.success(d.ok ? "Email accettata dal provider — in attesa di consegna" : "Email in coda"); qc.invalidateQueries({ queryKey: ["quote-emails", quoteId] }); onOpenChange(false); onSent?.(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message, { duration: 8000 }),
  });
  const blockers = p?.blockers || [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-2xl" data-testid="quote-email-dialog">
        <DialogHeader><DialogTitle>Invia preventivo via email</DialogTitle><DialogDescription>Anteprima: mittente, destinatario, oggetto, allegati. Il corpo deriva dal template del tenant.</DialogDescription></DialogHeader>
        {isLoading || !p ? <div className="text-sm text-muted-foreground">Caricamento anteprima…</div> : (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-[110px_1fr] gap-y-1 gap-x-3">
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Destinatario</span><span className="font-mono-plex" data-testid="email-preview-to">{p.to || "— (email cliente mancante)"}</span>
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Mittente</span><span data-testid="email-preview-from">{p.sender?.from_name} &lt;{p.sender?.from_email || "non risolvibile"}&gt; <Badge variant="outline" className="rounded-sm ml-1 text-[10px]">{p.sender?.sender_mode === "PANORAMA_MANAGED" ? "Mittente gestito Panorama" : "Dominio verificato"}</Badge></span>
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Reply-To</span><span className="font-mono-plex">{p.sender?.reply_to || "—"}</span>
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Oggetto</span><span data-testid="email-preview-subject">{p.subject}</span>
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Template</span><span>{p.template} {p.template_version ? `v${p.template_version}` : "(sistema)"}</span>
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Allegati</span><span data-testid="email-preview-attachments">{p.attachments?.length ? p.attachments.map((a) => `${a.filename} (${Math.round((a.size_bytes || 0) / 1024)} KB)`).join(", ") : "— PDF definitivo mancante"}</span>
              <span className="text-muted-foreground uppercase text-[10px] font-bold self-center">Provider</span><span>{p.provider}{p.provider_configured ? "" : " — NON CONFIGURATO"}</span>
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Messaggio aggiuntivo (facoltativo)</div>
              <Textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={1500} rows={3} className="rounded-sm" placeholder="Testo personalizzato inserito nel corpo email" data-testid="email-message-input" />
            </div>
            <div className="border border-border rounded-sm p-2 max-h-56 overflow-auto bg-white" data-testid="email-preview-body" dangerouslySetInnerHTML={{ __html: p.html }} />
            {blockers.length > 0 && <div className="text-xs text-destructive font-bold" data-testid="email-preview-blockers">{blockers.join(" · ")}</div>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)}>Annulla</Button>
              <Button className="rounded-sm" disabled={blockers.length > 0 || send.isPending} onClick={() => send.mutate()} data-testid="email-send-confirm-btn"><PaperPlaneTilt size={14} className="mr-1" /> {send.isPending ? "Invio…" : "Invia email"}</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function QuoteEmailHistory({ quoteId }) {
  const { data } = useQuery({ queryKey: ["quote-emails", quoteId], queryFn: async () => (await api.get(`/quotes/${quoteId}/emails`)).data, refetchInterval: 20000 });
  const items = data?.items || [];
  if (!items.length) return <div className="text-xs text-muted-foreground" data-testid="quote-emails-empty">Nessuna email inviata per questo preventivo. Lo stato "sent" non implica un invio email.</div>;
  return (
    <div className="space-y-2" data-testid="quote-emails-list">
      {items.map((e) => (
        <div key={e.id} className="border border-border rounded-sm p-2 text-xs space-y-1" data-testid="quote-email-item">
          <div className="flex items-center justify-between gap-2"><span className="font-mono-plex truncate">{e.original_to}</span><DeliveryBadge status={e.delivery_status} testId="quote-email-delivery-status" /></div>
          <div className="text-muted-foreground">Da {e.from_name} &lt;{e.from_email}&gt; · {e.provider} · {e.attachments?.map((a) => a.filename).join(", ")}</div>
          <div className="text-muted-foreground">Richiesta {fmtTs(e.created_at)}{e.sent_at ? ` · Accettata ${fmtTs(e.sent_at)}` : ""}{e.delivered_at ? ` · Consegnata ${fmtTs(e.delivered_at)}` : ""}</div>
          {(e.delivery_status === "bounced" || e.delivery_status === "failed") && <div className="text-destructive font-bold" data-testid="quote-email-bounce-msg">Email non consegnata. Verificare l'indirizzo del cliente.{e.error ? ` (${e.error})` : ""}</div>}
        </div>
      ))}
    </div>
  );
}
