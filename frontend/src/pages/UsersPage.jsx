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
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { DotsThreeVertical, Plus, UserPlus, LockKeyOpen, Trash, EnvelopeSimple } from "@phosphor-icons/react";

export default function UsersPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [openCreate, setOpenCreate] = useState(false);

  const { data } = useQuery({
    queryKey: ["users", q],
    queryFn: async () => (await api.get("/users", { params: { q: q || undefined, limit: 100 } })).data,
  });
  const { data: rolesData } = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await api.get("/roles")).data,
  });
  const roles = rolesData?.items || [];

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/users", payload)).data,
    onSuccess: (data) => {
      toast.success(t("users.invitation_sent"));
      if (data.invitation_url) {
        toast(`${t("users.invitation_link")}: ${data.invitation_url}`, { duration: 12000 });
      }
      qc.invalidateQueries({ queryKey: ["users"] });
      setOpenCreate(false);
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const deactivateMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/users/${id}`)).data,
    onSuccess: () => { toast.success(t("toast.deleted")); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const unlockMut = useMutation({
    mutationFn: async (id) => (await api.post(`/users/${id}/unlock`)).data,
    onSuccess: () => toast.success("Sbloccato"),
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const resendMut = useMutation({
    mutationFn: async (id) => (await api.post(`/users/${id}/resend-invitation`)).data,
    onSuccess: (data) => {
      toast.success(t("users.invitation_sent"));
      if (data.invitation_url) toast(`${t("users.invitation_link")}: ${data.invitation_url}`, { duration: 12000 });
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="space-y-8" data-testid="users-page">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="overline">{t("users.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("users.title")}</h1>
        </div>
        {has("users.create") && (
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button className="rounded-sm h-11 gap-2" data-testid="open-create-user-dialog">
                <UserPlus size={16} weight="bold" /> {t("users.add_user")}
              </Button>
            </DialogTrigger>
            <CreateUserDialog roles={roles} onSubmit={(payload) => createMut.mutate(payload)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <Card className="rounded-sm border-border p-4">
        <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)}
          className="rounded-sm h-10 max-w-sm" data-testid="users-search-input" />
      </Card>

      <Card className="rounded-sm border-border overflow-x-auto" data-testid="users-table-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">{t("users.name")}</TableHead>
              <TableHead className="overline">{t("common.email")}</TableHead>
              <TableHead className="overline">{t("users.roles")}</TableHead>
              <TableHead className="overline">{t("common.status")}</TableHead>
              <TableHead className="overline">{t("users.last_login")}</TableHead>
              <TableHead className="overline text-right">{t("common.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items || []).map((u) => {
              const rolesMap = new Map((roles || []).map(r => [r.id, r.name]));
              const roleNames = (u.role_ids || []).map(id => rolesMap.get(id)).filter(Boolean);
              return (
                <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                  <TableCell className="font-medium">{`${u.first_name || ""} ${u.last_name || ""}`.trim() || "—"}</TableCell>
                  <TableCell className="font-mono-plex text-xs">{u.email}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {roleNames.length === 0 && <span className="text-muted-foreground text-xs">—</span>}
                      {roleNames.map((n) => <Badge key={n} variant="outline" className="rounded-sm text-[10px]">{n}</Badge>)}
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className={`text-[10px] font-mono-plex px-2 py-1 ${u.is_active ? "bg-secondary" : "bg-destructive/10 text-destructive"}`}>
                      {u.is_active ? "ATTIVO" : "DISATTIVO"}
                    </span>
                    {u.must_change_password && (
                      <span className="ml-2 text-[10px] font-mono-plex px-2 py-1 bg-amber-100 text-amber-900">DA IMPOSTARE</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString("it-IT") : t("users.never")}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="p-2 hover:bg-secondary rounded-sm" data-testid={`user-actions-${u.id}`}>
                          <DotsThreeVertical size={18} weight="bold" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="rounded-sm">
                        {has("users.manage") && (
                          <DropdownMenuItem onClick={() => resendMut.mutate(u.id)}>
                            <EnvelopeSimple size={14} className="mr-2" /> {t("common.resend")} invito
                          </DropdownMenuItem>
                        )}
                        {has("users.manage") && (
                          <DropdownMenuItem onClick={() => unlockMut.mutate(u.id)}>
                            <LockKeyOpen size={14} className="mr-2" /> {t("common.unlock")}
                          </DropdownMenuItem>
                        )}
                        {has("users.delete") && (
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => { if (window.confirm(t("users.deactivate_confirm", { email: u.email }))) deactivateMut.mutate(u.id); }}
                            data-testid={`deactivate-user-${u.id}`}
                          >
                            <Trash size={14} className="mr-2" /> {t("users.deactivate")}
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function CreateUserDialog({ roles, onSubmit, loading }) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [phone, setPhone] = useState("");
  const [selected, setSelected] = useState([]);

  const toggle = (id) => setSelected(sel => sel.includes(id) ? sel.filter(x => x !== id) : [...sel, id]);
  const submit = (e) => {
    e.preventDefault();
    onSubmit({ email: email.trim(), first_name: first || null, last_name: last || null, phone: phone || null, role_ids: selected, send_invitation: true });
  };

  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="create-user-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">{t("users.add_user")}</DialogTitle>
      </DialogHeader>
      <form onSubmit={submit} className="space-y-4" data-testid="create-user-form">
        <div className="space-y-1.5">
          <Label className="overline">{t("common.email")}</Label>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-sm h-10" data-testid="cu-email" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="overline">{t("auth.first_name")}</Label>
            <Input value={first} onChange={(e) => setFirst(e.target.value)} className="rounded-sm h-10" data-testid="cu-first" />
          </div>
          <div className="space-y-1.5">
            <Label className="overline">{t("auth.last_name")}</Label>
            <Input value={last} onChange={(e) => setLast(e.target.value)} className="rounded-sm h-10" data-testid="cu-last" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="overline">{t("users.phone")}</Label>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} className="rounded-sm h-10" />
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("users.roles")}</Label>
          <div className="max-h-56 overflow-y-auto border border-border rounded-sm p-2 space-y-1">
            {roles.map((r) => (
              <label key={r.id} className="flex items-center gap-2 px-2 py-1 hover:bg-secondary cursor-pointer">
                <Checkbox checked={selected.includes(r.id)} onCheckedChange={() => toggle(r.id)} data-testid={`cu-role-${r.id}`} />
                <span className="text-sm">{r.name}</span>
                {r.is_system && <Badge variant="outline" className="rounded-sm ml-auto text-[10px]">{t("roles.system_role")}</Badge>}
              </label>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button type="submit" disabled={loading} className="rounded-sm" data-testid="cu-submit">
            {loading ? t("common.loading") : t("users.invite")}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
