import React, { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ArrowLeft, EnvelopeSimple, Phone, WhatsappLogo, MapPin, PencilSimple, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import { CustomerTypeBadge, customerDisplayName } from "@/components/customers/CustomerTypeBadge";
import NewCustomerDialog from "@/components/customers/NewCustomerDialog";
import SitesTab from "@/components/customers/SitesTab";
import CustomerTimelineTab from "@/components/customers/CustomerTimelineTab";
import CustomerQuotesTab from "@/components/customers/CustomerQuotesTab";
import { NewQuoteDialog } from "@/components/quotes/NewQuoteDialog";
import { Dialog } from "@/components/ui/dialog";

export default function CustomerDetailPage() {
  const { id } = useParams();
  const [newQuoteOpen, setNewQuoteOpen] = useState(false);
  const quoteMut = useMutation({
    mutationFn: async (p) => (await api.post("/quotes", p)).data,
    onSuccess: (d) => { toast.success(`Preventivo ${d.number} creato`); setNewQuoteOpen(false); navigate(`/quotes/${d.id}`); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState("overview");
  const [editOpen, setEditOpen] = useState(false);

  const { data: c } = useQuery({
    queryKey: ["customer", id],
    queryFn: async () => (await api.get(`/customers/${id}`)).data,
  });

  const { data: sitesData } = useQuery({
    enabled: !!id,
    queryKey: ["sites", id],
    queryFn: async () => (await api.get("/sites", { params: { customer_id: id } })).data,
  });

  const { data: timelineData } = useQuery({
    enabled: !!id,
    queryKey: ["customer-timeline", id],
    queryFn: async () => (await api.get(`/customers/${id}/timeline`, { params: { limit: 5 } })).data,
  });

  const isLegacy = c?.customer_type === "TO_CONFIRM";

  // Auto-open edit dialog when legacy customer is opened
  useEffect(() => {
    if (isLegacy) setEditOpen(true);
  }, [isLegacy]);

  const updateMut = useMutation({
    mutationFn: async (payload) => (await api.patch(`/customers/${id}`, payload)).data,
    onSuccess: () => {
      toast.success("Anagrafica aggiornata");
      qc.invalidateQueries({ queryKey: ["customer", id] });
      qc.invalidateQueries({ queryKey: ["customers"] });
      setEditOpen(false);
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  if (!c) return <div className="text-sm text-muted-foreground p-6">Caricamento…</div>;
  const name = customerDisplayName(c);

  return (
    <div className="space-y-6" data-testid="customer-detail-page">
      <Button variant="ghost" size="sm" className="rounded-sm" onClick={() => navigate("/customers")} data-testid="customer-detail-back">
        <ArrowLeft size={14} className="mr-1" /> Torna a Clienti
      </Button>

      {isLegacy && (
        <Card className="rounded-sm border-amber-300 bg-amber-50 p-4 flex items-start gap-3" data-testid="legacy-banner">
          <Warning size={18} weight="fill" className="text-amber-700 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-900">
            <b>Anagrafica da confermare.</b> Questo cliente è stato importato senza classificazione (Privato/Azienda).
            Aprire "Modifica anagrafica" per completare i dati e continuare.
          </div>
        </Card>
      )}

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <div className="overline font-mono-plex">{c.customer_number || "—"}</div>
            <CustomerTypeBadge type={c.customer_type} />
          </div>
          <h1 className="mt-1 font-display text-3xl sm:text-4xl font-black tracking-tight" data-testid="customer-name">{name}</h1>
          {c.customer_type === "COMPANY" && (c.first_name || c.last_name) && (
            <div className="text-sm text-muted-foreground">Referente: {[c.first_name, c.last_name].filter(Boolean).join(" ")}</div>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" className="rounded-sm gap-2" onClick={() => setEditOpen(true)} data-testid="edit-customer-button">
            <PencilSimple size={14} weight="bold" /> Modifica anagrafica
          </Button>
          <Button className="rounded-sm gap-2 bg-emerald-600 hover:bg-emerald-700" onClick={() => setNewQuoteOpen(true)} data-testid="customer-create-quote">
            + Crea preventivo
          </Button>
        </div>
        <Dialog open={newQuoteOpen} onOpenChange={setNewQuoteOpen}>
          <NewQuoteDialog initialCustomer={c} onSubmit={(p) => quoteMut.mutate(p)} loading={quoteMut.isPending} />
        </Dialog>
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <NewCustomerDialog
          initial={{
            customer_type: c.customer_type === "TO_CONFIRM" ? "PRIVATE" : c.customer_type,
            first_name: c.first_name || "",
            last_name: c.last_name || "",
            company_name: c.company_name || "",
            email: c.email || "",
            phone: c.phone || "",
            whatsapp: c.whatsapp || "",
            vat_number: c.vat_number || "",
            tax_code: c.tax_code || "",
            pec: c.pec || "",
            sdi_code: c.sdi_code || "",
            contact_person: c.contact_person || {},
            address: c.address || {},
          }}
          onSubmit={(p) => updateMut.mutate(p)}
          loading={updateMut.isPending}
        />
      </Dialog>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="overview" data-testid="tab-overview">Panoramica</TabsTrigger>
          <TabsTrigger value="anagrafica" data-testid="tab-anagrafica">Anagrafica</TabsTrigger>
          <TabsTrigger value="cantieri" data-testid="tab-cantieri">
            Cantieri {sitesData?.total ? <Badge className="ml-2 rounded-sm h-5">{sitesData.total}</Badge> : null}
          </TabsTrigger>
          <TabsTrigger value="timeline" data-testid="tab-timeline">Timeline</TabsTrigger>
          <TabsTrigger value="preventivi" data-testid="tab-preventivi">Preventivi</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <OverviewTab c={c} sitesTotal={sitesData?.total || 0} recentEvents={timelineData?.items || []} />
        </TabsContent>

        <TabsContent value="anagrafica" className="mt-4">
          <AnagraficaTab c={c} onEdit={() => setEditOpen(true)} />
        </TabsContent>

        <TabsContent value="cantieri" className="mt-4">
          <SitesTab customerId={id} />
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <CustomerTimelineTab customerId={id} sites={sitesData?.items || []} />
        </TabsContent>

        <TabsContent value="preventivi" className="mt-4">
          <CustomerQuotesTab customerId={id} customer={c} sites={sitesData?.items || []} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function OverviewTab({ c, sitesTotal, recentEvents }) {
  const addr = c.address || {};
  const addrLine = [addr.street, addr.zip_code, addr.city, addr.province].filter(Boolean).join(", ");
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="overview-tab">
      <Card className="rounded-sm border-border p-5 lg:col-span-2">
        <div className="overline mb-3">Sintesi</div>
        <dl className="grid grid-cols-2 gap-y-3 gap-x-4 text-sm">
          <Row k="Codice">{c.customer_number || "—"}</Row>
          <Row k="Tipo"><CustomerTypeBadge type={c.customer_type} /></Row>
          <Row k="Denominazione">{customerDisplayName(c)}</Row>
          {c.customer_type === "COMPANY" && <Row k="P.IVA">{c.vat_number || "—"}</Row>}
          {c.customer_type === "PRIVATE" && <Row k="Codice Fiscale">{c.tax_code || "—"}</Row>}
          <Row k="Email">{c.email ? <span className="inline-flex items-center gap-1"><EnvelopeSimple size={14} /> {c.email}</span> : "—"}</Row>
          <Row k="Telefono">{c.phone ? <span className="inline-flex items-center gap-1"><Phone size={14} /> {c.phone}</span> : "—"}</Row>
          {c.whatsapp && <Row k="WhatsApp"><span className="inline-flex items-center gap-1"><WhatsappLogo size={14} /> {c.whatsapp}</span></Row>}
          <Row k="Indirizzo">{addrLine || "—"}</Row>
          <Row k="Cantieri"><b>{sitesTotal}</b></Row>
          <Row k="Ultimo aggiornamento">{c.updated_at ? new Date(c.updated_at).toLocaleString("it-IT") : "—"}</Row>
        </dl>
      </Card>
      <Card className="rounded-sm border-border p-5">
        <div className="overline mb-3">Ultime attività</div>
        {recentEvents.length === 0 && <div className="text-sm text-muted-foreground">Nessun evento registrato</div>}
        <ul className="space-y-3">
          {recentEvents.slice(0, 5).map((e) => (
            <li key={e.id} className="text-xs" data-testid={`overview-event-${e.id}`}>
              <div className="flex items-center gap-2">
                <span className="font-mono-plex uppercase tracking-widest text-[10px]">{e.category.replace(/_/g, " ")}</span>
                <span className="text-muted-foreground">{new Date(e.created_at).toLocaleDateString("it-IT")}</span>
              </div>
              {e.title && <div className="mt-1 font-medium">{e.title}</div>}
              <div className="text-muted-foreground line-clamp-2">{e.body}</div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function AnagraficaTab({ c, onEdit }) {
  const addr = c.address || {};
  const cp = c.contact_person || {};
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="anagrafica-tab">
      <Card className="rounded-sm border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="overline">Dati anagrafici</div>
          <Button size="sm" variant="ghost" className="rounded-sm" onClick={onEdit} data-testid="anagrafica-edit">
            <PencilSimple size={14} weight="bold" className="mr-1" /> Modifica
          </Button>
        </div>
        <dl className="grid grid-cols-2 gap-y-3 gap-x-4 text-sm">
          <Row k="Tipo"><CustomerTypeBadge type={c.customer_type} /></Row>
          <Row k="Codice">{c.customer_number || "—"}</Row>
          {c.customer_type === "PRIVATE" && (
            <>
              <Row k="Nome">{c.first_name || "—"}</Row>
              <Row k="Cognome">{c.last_name || "—"}</Row>
              <Row k="Codice Fiscale"><span className="font-mono-plex">{c.tax_code || "—"}</span></Row>
            </>
          )}
          {c.customer_type === "COMPANY" && (
            <>
              <Row k="Ragione sociale">{c.company_name || "—"}</Row>
              <Row k="P.IVA"><span className="font-mono-plex">{c.vat_number || "—"}</span></Row>
              <Row k="Codice Fiscale"><span className="font-mono-plex">{c.tax_code || "—"}</span></Row>
              <Row k="PEC">{c.pec || "—"}</Row>
              <Row k="Codice SDI"><span className="font-mono-plex">{c.sdi_code || "—"}</span></Row>
            </>
          )}
          <Row k="Email">{c.email || "—"}</Row>
          <Row k="Telefono">{c.phone || "—"}</Row>
        </dl>
      </Card>

      <Card className="rounded-sm border-border p-5">
        <div className="overline mb-3">{c.customer_type === "COMPANY" ? "Sede legale" : "Residenza"}</div>
        <div className="text-sm space-y-1">
          <div><MapPin size={14} className="inline mr-1" />{addr.street || "—"}</div>
          <div>{[addr.zip_code, addr.city, addr.province].filter(Boolean).join(" · ") || "—"}</div>
          <div className="text-xs text-muted-foreground">{addr.country || "IT"}</div>
        </div>
        {c.customer_type === "COMPANY" && (
          <div className="border-t border-border mt-4 pt-4">
            <div className="overline mb-3">Referente</div>
            <div className="text-sm space-y-1">
              <div>{[cp.first_name, cp.last_name].filter(Boolean).join(" ") || "—"}</div>
              {cp.role && <div className="text-xs text-muted-foreground">{cp.role}</div>}
              {cp.phone && <div className="text-xs">📞 {cp.phone}</div>}
              {cp.email && <div className="text-xs">✉ {cp.email}</div>}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function Row({ k, children }) {
  return (
    <>
      <dt className="text-xs text-muted-foreground uppercase tracking-wider">{k}</dt>
      <dd className="text-sm">{children}</dd>
    </>
  );
}
