import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogTrigger } from "@/components/ui/dialog";
import { UserPlus } from "@phosphor-icons/react";
import { toast } from "sonner";
import NewCustomerDialog from "@/components/customers/NewCustomerDialog";
import { CustomerTypeBadge, customerDisplayName } from "@/components/customers/CustomerTypeBadge";

export default function CustomersPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["customers", q],
    queryFn: async () => (await api.get("/customers", { params: { q: q || undefined, limit: 200 } })).data,
  });

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/customers", payload)).data,
    onSuccess: (d) => {
      toast.success(t("toast.created"));
      qc.invalidateQueries({ queryKey: ["customers"] });
      setOpen(false);
      navigate(`/customers/${d.id}`);
    },
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
            <DialogTrigger asChild>
              <Button className="rounded-sm h-11 gap-2" data-testid="new-customer-button">
                <UserPlus size={16} weight="bold" />{t("crm.customers.new_customer")}
              </Button>
            </DialogTrigger>
            <NewCustomerDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <Card className="rounded-sm border-border p-4">
        <Input
          placeholder="Cerca per numero, nome, azienda, P.IVA, email…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="rounded-sm h-10 max-w-md"
          data-testid="customers-search"
        />
      </Card>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">N° Cliente</TableHead>
              <TableHead className="overline">Nome / Ragione sociale</TableHead>
              <TableHead className="overline">Tipo</TableHead>
              <TableHead className="overline">Contatti</TableHead>
              <TableHead className="overline">Città</TableHead>
              <TableHead className="overline">P.IVA / CF</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items || []).map((c) => (
              <TableRow
                key={c.id}
                onClick={() => navigate(`/customers/${c.id}`)}
                className="cursor-pointer"
                data-testid={`customer-row-${c.id}`}
              >
                <TableCell className="font-mono-plex text-xs">
                  {c.customer_number || <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell>
                  <div className="text-sm font-medium">{customerDisplayName(c)}</div>
                  {c.customer_type === "COMPANY" && c.contact_person?.first_name && (
                    <div className="text-xs text-muted-foreground">
                      Referente: {c.contact_person.first_name} {c.contact_person.last_name || ""}
                    </div>
                  )}
                </TableCell>
                <TableCell><CustomerTypeBadge type={c.customer_type} /></TableCell>
                <TableCell className="text-xs">{c.email || c.phone || "—"}</TableCell>
                <TableCell className="text-xs">{c.address?.city || "—"}</TableCell>
                <TableCell className="text-xs font-mono-plex">{c.vat_number || c.tax_code || "—"}</TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-10 text-sm text-muted-foreground">
                  {t("common.no_results")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
