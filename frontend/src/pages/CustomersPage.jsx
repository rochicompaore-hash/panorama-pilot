import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { UserPlus } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function CustomersPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ["customers", q], queryFn: async () => (await api.get("/customers", { params: { q: q || undefined, limit: 200 } })).data });

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/customers", payload)).data,
    onSuccess: (d) => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["customers"] }); setOpen(false); navigate(`/customers/${d.id}`); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="space-y-8" data-testid="customers-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("crm.customers.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("crm.customers.title")}</h1>
        </div>
        {has("crm.customers.create") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="rounded-sm h-11 gap-2" data-testid="new-customer-button"><UserPlus size={16} weight="bold" />{t("crm.customers.new_customer")}</Button></DialogTrigger>
            <NewCustomerDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <Card className="rounded-sm border-border p-4">
        <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} className="rounded-sm h-10 max-w-sm" data-testid="customers-search" />
      </Card>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead className="overline">Nome</TableHead>
            <TableHead className="overline">Tipo</TableHead>
            <TableHead className="overline">Contatti</TableHead>
            <TableHead className="overline">Città</TableHead>
            <TableHead className="overline">P.IVA</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.items || []).map((c) => (
              <TableRow key={c.id} onClick={() => navigate(`/customers/${c.id}`)} className="cursor-pointer" data-testid={`customer-row-${c.id}`}>
                <TableCell><div className="text-sm font-medium">{`${c.first_name || ""} ${c.last_name || ""}`.trim() || c.company_name || "—"}</div>{c.company_name && (c.first_name || c.last_name) && <div className="text-xs text-muted-foreground">{c.company_name}</div>}</TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm text-[10px]">{c.customer_type === "business" ? t("crm.customers.type_business") : t("crm.customers.type_private")}</Badge></TableCell>
                <TableCell className="text-xs">{c.email || c.phone || "—"}</TableCell>
                <TableCell className="text-xs">{c.address?.city || "—"}</TableCell>
                <TableCell className="text-xs font-mono-plex">{c.vat_number || "—"}</TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-10 text-sm text-muted-foreground">{t("common.no_results")}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function NewCustomerDialog({ onSubmit, loading }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ customer_type: "private", first_name: "", last_name: "", company_name: "", email: "", phone: "", vat_number: "" });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="new-customer-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">{t("crm.customers.new_customer")}</DialogTitle>
        <DialogDescription>Anagrafica del nuovo cliente.</DialogDescription>
      </DialogHeader>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit(f); }} className="space-y-3">
        <div><Label className="overline">Tipo</Label>
          <Select value={f.customer_type} onValueChange={(v) => upd("customer_type", v)}>
            <SelectTrigger className="rounded-sm h-10" data-testid="nc-type"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="private">{t("crm.customers.type_private")}</SelectItem><SelectItem value="business">{t("crm.customers.type_business")}</SelectItem></SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Nome</Label><Input value={f.first_name} onChange={(e) => upd("first_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-first" /></div>
          <div><Label className="overline">Cognome</Label><Input value={f.last_name} onChange={(e) => upd("last_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-last" /></div>
        </div>
        <div><Label className="overline">Azienda</Label><Input value={f.company_name} onChange={(e) => upd("company_name", e.target.value)} className="rounded-sm h-10" data-testid="nc-company" /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Email</Label><Input type="email" value={f.email} onChange={(e) => upd("email", e.target.value)} className="rounded-sm h-10" data-testid="nc-email" /></div>
          <div><Label className="overline">Telefono</Label><Input value={f.phone} onChange={(e) => upd("phone", e.target.value)} className="rounded-sm h-10" data-testid="nc-phone" /></div>
        </div>
        <div><Label className="overline">P.IVA / CF</Label><Input value={f.vat_number} onChange={(e) => upd("vat_number", e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="nc-vat" /></div>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="nc-submit">{loading ? "…" : t("common.create")}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
