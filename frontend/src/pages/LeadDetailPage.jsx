import React, { useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import Timeline from "@/components/app/Timeline";
import ActivityLogger from "@/components/app/ActivityLogger";
import { toast } from "sonner";
import { ArrowLeft, Trophy, Phone, EnvelopeSimple, WhatsappLogo, Warning, MapPin } from "@phosphor-icons/react";
import { formatDistanceToNow } from "date-fns";
import { it as itLocale } from "date-fns/locale";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

export default function LeadDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { has } = useAuth();
  const qc = useQueryClient();
  const { data: lead } = useQuery({ queryKey: ["lead", id], queryFn: async () => (await api.get(`/leads/${id}`)).data });
  const { data: pipe } = useQuery({ queryKey: ["pipeline-default-for-lead"], queryFn: async () => (await api.get("/pipelines/default")).data });
  const { data: acts } = useQuery({ queryKey: ["activities-lead", id], queryFn: async () => (await api.get("/activities", { params: { lead_id: id } })).data });

  const updateMut = useMutation({
    mutationFn: async (patch) => (await api.patch(`/leads/${id}`, patch)).data,
    onSuccess: () => { toast.success("Aggiornato"); qc.invalidateQueries({ queryKey: ["lead", id] }); qc.invalidateQueries({ queryKey: ["activities-lead", id] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const convertMut = useMutation({
    mutationFn: async () => (await api.post(`/leads/${id}/convert`, { customer_type: "private" })).data,
    onSuccess: (d) => { toast.success("Convertito in cliente"); navigate(`/customers/${d.id}`); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const stages = pipe?.stages || [];
  const currentStage = useMemo(() => stages.find(s => s.id === lead?.stage_id), [lead, stages]);
  const intel = lead?.intelligence?.next_action_suggestion;

  if (!lead) return <div className="text-sm text-muted-foreground">Caricamento…</div>;

  const name = `${lead.first_name || ""} ${lead.last_name || ""}`.trim() || lead.company_name || lead.email || "Lead";
  const lastContact = lead.last_contact_at ? formatDistanceToNow(new Date(lead.last_contact_at), { addSuffix: true, locale: itLocale }) : "mai";

  return (
    <div className="space-y-6" data-testid="lead-detail-page">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" className="rounded-sm" onClick={() => navigate("/leads")} data-testid="lead-back">
          <ArrowLeft size={14} className="mr-1" /> Torna a Lead
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: identity + intelligence */}
        <div className="lg:col-span-1 space-y-4">
          <Card className="rounded-sm border-border p-6" data-testid="lead-summary-card">
            <div className="overline">{lead.company_name ? "Azienda" : "Privato"}</div>
            <h1 className="mt-1 font-display text-3xl font-black tracking-tight">{name}</h1>
            {lead.company_name && (lead.first_name || lead.last_name) && <div className="text-sm text-muted-foreground">{lead.company_name}</div>}
            <div className="mt-4 space-y-1.5 text-sm">
              {lead.email && <div className="flex items-center gap-2"><EnvelopeSimple size={14} weight="duotone" /> {lead.email}</div>}
              {lead.phone && <div className="flex items-center gap-2"><Phone size={14} weight="duotone" /> {lead.phone}</div>}
              {lead.whatsapp && <div className="flex items-center gap-2"><WhatsappLogo size={14} weight="duotone" /> {lead.whatsapp}</div>}
              {(lead.address?.city || lead.address?.street) && <div className="flex items-center gap-2"><MapPin size={14} weight="duotone" /> {[lead.address.street, lead.address.city].filter(Boolean).join(", ")}</div>}
            </div>
          </Card>

          <Card className="rounded-sm border-border p-6" data-testid="lead-intel-card">
            <div className="overline mb-3">Intelligenza vendita</div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Valore potenziale</span>
                <span className="font-mono-plex text-lg font-bold">{fmtEUR(lead.estimated_value)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Probabilità</span>
                <Badge variant="outline" className="rounded-sm">{lead.probability}%</Badge>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-muted-foreground">Valore ponderato</span>
                  <span className="font-mono-plex text-sm font-bold text-[hsl(var(--brand-red))]">{fmtEUR((lead.estimated_value || 0) * (lead.probability || 0) / 100)}</span>
                </div>
                <div className="h-1 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full bg-[hsl(var(--brand-red))]" style={{ width: `${lead.probability || 0}%` }} />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Ultimo contatto</span>
                <span className="text-xs">{lastContact}</span>
              </div>
              {intel && (
                <div className={`mt-4 p-3 border rounded-sm ${intel.priority === "high" ? "border-[hsl(var(--brand-red))] bg-[hsl(var(--brand-red))]/5" : "border-border bg-secondary"}`}>
                  <div className="flex items-center gap-2 text-xs font-mono-plex uppercase tracking-widest text-muted-foreground">
                    <Warning size={12} weight="bold" /> Prossima azione consigliata
                  </div>
                  <div className="mt-1 text-sm font-medium">{intel.label}</div>
                </div>
              )}
            </div>
          </Card>

          <Card className="rounded-sm border-border p-6" data-testid="lead-stage-card">
            <div className="overline mb-3">Stato pipeline</div>
            <Select value={lead.stage_id || ""} onValueChange={(v) => updateMut.mutate({ stage_id: v })} disabled={!has("crm.leads.edit")}>
              <SelectTrigger className="rounded-sm h-10" data-testid="lead-stage-select"><SelectValue placeholder="Seleziona fase" /></SelectTrigger>
              <SelectContent>{stages.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
            </Select>
            {currentStage?.is_won && <div className="mt-3 text-sm text-emerald-600 flex items-center gap-2"><Trophy size={16} weight="bold" /> Vinto!</div>}
            {has("crm.leads.convert") && !lead.customer_id && currentStage?.is_won && (
              <Button onClick={() => convertMut.mutate()} disabled={convertMut.isPending} className="rounded-sm w-full mt-4 gap-2" data-testid="lead-convert-button">
                <Trophy size={14} weight="bold" /> Converti in cliente
              </Button>
            )}
            {lead.customer_id && (
              <Button variant="outline" onClick={() => navigate(`/customers/${lead.customer_id}`)} className="rounded-sm w-full mt-4" data-testid="lead-goto-customer">
                Vai alla scheda cliente
              </Button>
            )}
          </Card>
        </div>

        {/* Right: timeline + logger */}
        <div className="lg:col-span-2 space-y-4">
          <ActivityLogger
            leadId={lead.id}
            defaultPhone={lead.phone}
            defaultEmail={lead.email}
            defaultWhatsApp={lead.whatsapp || lead.phone}
            onLogged={() => qc.invalidateQueries({ queryKey: ["activities-lead", id] })}
          />
          <Card className="rounded-sm border-border p-6" data-testid="lead-timeline-card">
            <div className="overline mb-6">Timeline · Cronologia completa</div>
            <Timeline activities={acts?.items || []} />
          </Card>
        </div>
      </div>
    </div>
  );
}
