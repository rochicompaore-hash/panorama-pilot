import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, PencilSimple, Archive, MapPin } from "@phosphor-icons/react";
import { toast } from "sonner";

const PROPERTY_TYPES = [
  { v: "APPARTAMENTO", l: "Appartamento" },
  { v: "CASA_SINGOLA", l: "Casa singola" },
  { v: "BIFAMILIARE", l: "Bifamiliare" },
  { v: "CONDOMINIO", l: "Condominio" },
  { v: "ATTIVITA_COMMERCIALE", l: "Attività commerciale" },
  { v: "ALTRO", l: "Altro" },
];

/**
 * SitesTab — Milestone 1 Part 2 · gestione N cantieri per Cliente.
 */
export default function SitesTab({ customerId, embedded = false }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const { data } = useQuery({
    queryKey: ["sites", customerId],
    queryFn: async () => (await api.get("/sites", { params: { customer_id: customerId } })).data,
  });

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/sites", { ...payload, customer_id: customerId })).data,
    onSuccess: () => {
      toast.success("Cantiere creato");
      qc.invalidateQueries({ queryKey: ["sites", customerId] });
      qc.invalidateQueries({ queryKey: ["customer-timeline", customerId] });
      setOpen(false);
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const updateMut = useMutation({
    mutationFn: async ({ id, payload }) => (await api.patch(`/sites/${id}`, payload)).data,
    onSuccess: () => {
      toast.success("Cantiere aggiornato");
      qc.invalidateQueries({ queryKey: ["sites", customerId] });
      setEditing(null);
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const archiveMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/sites/${id}`)).data,
    onSuccess: () => {
      toast.success("Cantiere archiviato");
      qc.invalidateQueries({ queryKey: ["sites", customerId] });
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const sites = data?.items || [];

  return (
    <div className="space-y-4" data-testid="sites-tab">
      <div className="flex items-center justify-between">
        <div className="overline">{sites.length} cantiere/i</div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="rounded-sm gap-2 h-10" data-testid="new-site-button">
              <Plus size={14} weight="bold" /> Nuovo cantiere
            </Button>
          </DialogTrigger>
          <SiteFormDialog title="Nuovo cantiere" onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
        </Dialog>
      </div>

      {sites.length === 0 && (
        <Card className="rounded-sm border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Nessun cantiere. Crea il primo cantiere per iniziare a preventivare.
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {sites.map((s) => (
          <Card key={s.id} className="rounded-sm border-border p-4" data-testid={`site-card-${s.id}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-mono-plex text-[10px] text-muted-foreground">{s.site_number}</div>
                <div className="font-medium">{s.name}</div>
              </div>
              <div className="flex items-center gap-1">
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditing(s)} data-testid={`site-edit-${s.id}`}>
                  <PencilSimple size={14} />
                </Button>
                <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive"
                  onClick={() => window.confirm("Archiviare il cantiere?") && archiveMut.mutate(s.id)}
                  data-testid={`site-archive-${s.id}`}>
                  <Archive size={14} />
                </Button>
              </div>
            </div>
            <div className="mt-2 text-xs text-muted-foreground flex items-start gap-1">
              <MapPin size={12} className="mt-0.5 shrink-0" />
              <span>{[s.address, s.street_number].filter(Boolean).join(" ")}<br />{[s.postal_code, s.city, s.province].filter(Boolean).join(" ")}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
              {s.property_type && <Badge variant="outline" className="rounded-sm">{PROPERTY_TYPES.find((p) => p.v === s.property_type)?.l || s.property_type}</Badge>}
              {s.floor && <Badge variant="outline" className="rounded-sm">Piano {s.floor}</Badge>}
              {s.has_elevator === true && <Badge variant="outline" className="rounded-sm">Ascensore</Badge>}
              {s.has_elevator === false && <Badge variant="outline" className="rounded-sm">Senza ascensore</Badge>}
            </div>
          </Card>
        ))}
      </div>

      <Dialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        {editing && (
          <SiteFormDialog
            title={`Modifica cantiere ${editing.site_number}`}
            initial={editing}
            onSubmit={(p) => updateMut.mutate({ id: editing.id, payload: p })}
            loading={updateMut.isPending}
          />
        )}
      </Dialog>
    </div>
  );
}

function SiteFormDialog({ title, initial, onSubmit, loading }) {
  const [f, setF] = useState({
    name: initial?.name || "",
    address: initial?.address || "",
    street_number: initial?.street_number || "",
    postal_code: initial?.postal_code || "",
    city: initial?.city || "",
    province: initial?.province || "",
    country: initial?.country || "IT",
    floor: initial?.floor || "",
    has_elevator: initial?.has_elevator ?? null,
    property_type: initial?.property_type || "",
    accessibility_notes: initial?.accessibility_notes || "",
    unloading_notes: initial?.unloading_notes || "",
    logistics_notes: initial?.logistics_notes || "",
    site_contact_name: initial?.site_contact_name || "",
    site_contact_phone: initial?.site_contact_phone || "",
  });
  const upd = (k, v) => setF((x) => ({ ...x, [k]: v }));

  return (
    <DialogContent className="rounded-sm max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="site-form-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">{title}</DialogTitle>
        <DialogDescription>Dati del cantiere/immobile. Verranno usati in preventivo, rilievo, posa.</DialogDescription>
      </DialogHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const payload = { ...f };
          if (!payload.property_type) delete payload.property_type;
          onSubmit(payload);
        }}
        className="space-y-3"
      >
        <div>
          <Label className="overline">Nome / Riferimento *</Label>
          <Input required value={f.name} onChange={(e) => upd("name", e.target.value)} placeholder="Es. Abitazione principale" className="rounded-sm h-10" data-testid="site-name" />
        </div>
        <div className="grid grid-cols-4 gap-2">
          <div className="col-span-3">
            <Label className="overline">Indirizzo</Label>
            <Input value={f.address} onChange={(e) => upd("address", e.target.value)} className="rounded-sm h-10" data-testid="site-address" />
          </div>
          <div>
            <Label className="overline">Civico</Label>
            <Input value={f.street_number} onChange={(e) => upd("street_number", e.target.value)} className="rounded-sm h-10" data-testid="site-street-number" />
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2">
          <div>
            <Label className="overline">CAP</Label>
            <Input value={f.postal_code} onChange={(e) => upd("postal_code", e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="site-zip" />
          </div>
          <div className="col-span-2">
            <Label className="overline">Città</Label>
            <Input value={f.city} onChange={(e) => upd("city", e.target.value)} className="rounded-sm h-10" data-testid="site-city" />
          </div>
          <div>
            <Label className="overline">Prov.</Label>
            <Input value={f.province} onChange={(e) => upd("province", e.target.value.toUpperCase())} maxLength={2} className="rounded-sm h-10 font-mono-plex" data-testid="site-province" />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <Label className="overline">Piano</Label>
            <Input value={f.floor} onChange={(e) => upd("floor", e.target.value)} className="rounded-sm h-10" data-testid="site-floor" />
          </div>
          <div>
            <Label className="overline">Tipologia</Label>
            <Select value={f.property_type} onValueChange={(v) => upd("property_type", v)}>
              <SelectTrigger className="rounded-sm h-10" data-testid="site-property-type"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{PROPERTY_TYPES.map((p) => <SelectItem key={p.v} value={p.v}>{p.l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="flex items-end pb-2">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={f.has_elevator === true}
                onCheckedChange={(v) => upd("has_elevator", v === true ? true : v === "indeterminate" ? null : false)}
                data-testid="site-has-elevator"
              />
              Ascensore
            </label>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="overline">Referente in cantiere</Label>
            <Input value={f.site_contact_name} onChange={(e) => upd("site_contact_name", e.target.value)} className="rounded-sm h-10" data-testid="site-contact-name" />
          </div>
          <div>
            <Label className="overline">Telefono referente</Label>
            <Input value={f.site_contact_phone} onChange={(e) => upd("site_contact_phone", e.target.value)} className="rounded-sm h-10" data-testid="site-contact-phone" />
          </div>
        </div>
        <div>
          <Label className="overline">Note logistica / scarico / accessibilità</Label>
          <Textarea rows={2} value={f.logistics_notes} onChange={(e) => upd("logistics_notes", e.target.value)} className="rounded-sm" data-testid="site-logistics-notes" />
        </div>
        <DialogFooter>
          <Button type="submit" disabled={loading} className="rounded-sm" data-testid="site-submit">{loading ? "…" : "Salva"}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
