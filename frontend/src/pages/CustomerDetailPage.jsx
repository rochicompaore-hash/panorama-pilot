import React from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Timeline from "@/components/app/Timeline";
import ActivityLogger from "@/components/app/ActivityLogger";
import { ArrowLeft, EnvelopeSimple, Phone, WhatsappLogo, MapPin } from "@phosphor-icons/react";

export default function CustomerDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: c } = useQuery({ queryKey: ["customer", id], queryFn: async () => (await api.get(`/customers/${id}`)).data });
  const { data: acts } = useQuery({ queryKey: ["activities-customer", id], queryFn: async () => (await api.get("/activities", { params: { customer_id: id } })).data });

  if (!c) return <div className="text-sm text-muted-foreground">Caricamento…</div>;
  const name = `${c.first_name || ""} ${c.last_name || ""}`.trim() || c.company_name || "Cliente";

  return (
    <div className="space-y-6" data-testid="customer-detail-page">
      <Button variant="ghost" size="sm" className="rounded-sm" onClick={() => navigate("/customers")}>
        <ArrowLeft size={14} className="mr-1" /> Torna a Clienti
      </Button>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="rounded-sm border-border p-6 lg:col-span-1 h-fit" data-testid="customer-summary">
          <div className="overline">{c.customer_type === "business" ? "Azienda" : "Privato"}</div>
          <h1 className="mt-1 font-display text-3xl font-black tracking-tight">{name}</h1>
          {c.company_name && (c.first_name || c.last_name) && <div className="text-sm text-muted-foreground">{c.company_name}</div>}
          <div className="mt-4 space-y-1.5 text-sm">
            {c.email && <div className="flex items-center gap-2"><EnvelopeSimple size={14} weight="duotone" /> {c.email}</div>}
            {c.phone && <div className="flex items-center gap-2"><Phone size={14} weight="duotone" /> {c.phone}</div>}
            {c.whatsapp && <div className="flex items-center gap-2"><WhatsappLogo size={14} weight="duotone" /> {c.whatsapp}</div>}
            {c.address?.city && <div className="flex items-center gap-2"><MapPin size={14} weight="duotone" /> {[c.address.street, c.address.city].filter(Boolean).join(", ")}</div>}
            {c.vat_number && <div className="font-mono-plex text-xs mt-2">P.IVA: {c.vat_number}</div>}
          </div>
        </Card>
        <div className="lg:col-span-2 space-y-4">
          <ActivityLogger customerId={c.id} defaultPhone={c.phone} defaultEmail={c.email} defaultWhatsApp={c.whatsapp || c.phone}
            onLogged={() => qc.invalidateQueries({ queryKey: ["activities-customer", id] })} />
          <Card className="rounded-sm border-border p-6">
            <div className="overline mb-6">Timeline · Cronologia completa</div>
            <Timeline activities={acts?.items || []} />
          </Card>
        </div>
      </div>
    </div>
  );
}
