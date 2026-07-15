import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Plus, IdentificationCard } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function ContactsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ["contacts", q], queryFn: async () => (await api.get("/contacts", { params: { q: q || undefined, limit: 200 } })).data });
  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/contacts", payload)).data,
    onSuccess: () => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["contacts"] }); setOpen(false); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="space-y-8" data-testid="contacts-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("crm.contacts.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("crm.contacts.title")}</h1>
        </div>
        {has("crm.contacts.manage") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="rounded-sm h-11 gap-2" data-testid="new-contact-button"><Plus size={16} weight="bold" />{t("crm.contacts.new_contact")}</Button></DialogTrigger>
            <NewContactDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>
      <Card className="rounded-sm border-border p-4">
        <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} className="rounded-sm h-10 max-w-sm" data-testid="contacts-search" />
      </Card>
      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead className="overline">Nome</TableHead>
            <TableHead className="overline">Ruolo</TableHead>
            <TableHead className="overline">Email</TableHead>
            <TableHead className="overline">Telefono</TableHead>
            <TableHead className="overline">Principale</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.items || []).map((c) => (
              <TableRow key={c.id} data-testid={`contact-row-${c.id}`}>
                <TableCell className="text-sm font-medium">{`${c.first_name || ""} ${c.last_name || ""}`.trim()}</TableCell>
                <TableCell className="text-xs">{c.role || "—"}</TableCell>
                <TableCell className="text-xs font-mono-plex">{c.email || "—"}</TableCell>
                <TableCell className="text-xs font-mono-plex">{c.phone || "—"}</TableCell>
                <TableCell>{c.is_primary && <Badge variant="outline" className="rounded-sm text-[10px]">PRINCIPALE</Badge>}</TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-10 text-sm text-muted-foreground">{t("common.no_results")}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function NewContactDialog({ onSubmit, loading }) {
  const [f, setF] = useState({ first_name: "", last_name: "", role: "", email: "", phone: "", is_primary: false });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="new-contact-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo contatto</DialogTitle>
        <DialogDescription>Aggiungi un nuovo contatto alla rubrica.</DialogDescription>
      </DialogHeader>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit(f); }} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Nome</Label><Input required value={f.first_name} onChange={(e) => upd("first_name", e.target.value)} className="rounded-sm h-10" data-testid="ncc-first" /></div>
          <div><Label className="overline">Cognome</Label><Input value={f.last_name} onChange={(e) => upd("last_name", e.target.value)} className="rounded-sm h-10" data-testid="ncc-last" /></div>
        </div>
        <div><Label className="overline">Ruolo</Label><Input value={f.role} onChange={(e) => upd("role", e.target.value)} className="rounded-sm h-10" data-testid="ncc-role" /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Email</Label><Input type="email" value={f.email} onChange={(e) => upd("email", e.target.value)} className="rounded-sm h-10" data-testid="ncc-email" /></div>
          <div><Label className="overline">Telefono</Label><Input value={f.phone} onChange={(e) => upd("phone", e.target.value)} className="rounded-sm h-10" data-testid="ncc-phone" /></div>
        </div>
        <label className="flex items-center gap-2"><Checkbox checked={f.is_primary} onCheckedChange={(v) => upd("is_primary", !!v)} data-testid="ncc-primary" /><span className="text-sm">Referente principale</span></label>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="ncc-submit">{loading ? "…" : "Crea"}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
