import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash, PencilSimple } from "@phosphor-icons/react";

export default function RolesPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();

  const { data: rolesData } = useQuery({ queryKey: ["roles"], queryFn: async () => (await api.get("/roles")).data });
  const { data: permsData } = useQuery({ queryKey: ["permissions"], queryFn: async () => (await api.get("/permissions")).data });
  const roles = rolesData?.items || [];
  const modules = permsData?.modules || [];

  const [selected, setSelected] = useState(null);
  const [openCreate, setOpenCreate] = useState(false);

  const current = useMemo(() => roles.find(r => r.id === selected) || roles[0], [roles, selected]);

  const updateMut = useMutation({
    mutationFn: async ({ id, patch }) => (await api.patch(`/roles/${id}`, patch)).data,
    onSuccess: () => { toast.success(t("toast.saved")); qc.invalidateQueries({ queryKey: ["roles"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const deleteMut = useMutation({
    mutationFn: async (id) => (await api.delete(`/roles/${id}`)).data,
    onSuccess: () => { toast.success(t("toast.deleted")); qc.invalidateQueries({ queryKey: ["roles"] }); setSelected(null); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/roles", payload)).data,
    onSuccess: (r) => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["roles"] }); setOpenCreate(false); setSelected(r.id); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const togglePerm = (key) => {
    if (!current || !has("roles.manage")) return;
    const set = new Set(current.permission_keys || []);
    if (set.has(key)) set.delete(key); else set.add(key);
    updateMut.mutate({ id: current.id, patch: { permission_keys: Array.from(set) } });
  };

  return (
    <div className="space-y-8" data-testid="roles-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="overline">{t("roles.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("roles.title")}</h1>
        </div>
        {has("roles.manage") && (
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button className="rounded-sm h-11 gap-2" data-testid="new-role-button">
                <Plus size={16} weight="bold" /> {t("roles.new_role")}
              </Button>
            </DialogTrigger>
            <CreateRoleDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
        <Card className="rounded-sm border-border p-2 h-fit" data-testid="roles-list">
          {roles.map((r) => (
            <button
              key={r.id}
              onClick={() => setSelected(r.id)}
              className={`w-full text-left px-3 py-2 mb-1 border-l-2 ${current?.id === r.id ? "border-[hsl(var(--brand-red))] bg-secondary" : "border-transparent hover:bg-secondary"}`}
              data-testid={`role-item-${r.id}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{r.name}</span>
                {r.is_system && <Badge variant="outline" className="rounded-sm text-[10px]">SYS</Badge>}
              </div>
              <div className="text-xs text-muted-foreground truncate">{r.description || "—"}</div>
              <div className="text-[10px] text-muted-foreground font-mono-plex mt-1">{(r.permission_keys || []).length} permessi</div>
            </button>
          ))}
        </Card>

        <Card className="rounded-sm border-border p-6" data-testid="role-detail">
          {!current ? (
            <div className="text-sm text-muted-foreground">Seleziona un ruolo.</div>
          ) : (
            <>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="overline">{current.is_system ? t("roles.system_role") : t("roles.custom_role")}</div>
                  <h2 className="mt-1 font-display text-2xl font-bold tracking-tight">{current.name}</h2>
                  {current.description && <p className="mt-1 text-sm text-muted-foreground">{current.description}</p>}
                </div>
                {has("roles.manage") && !current.is_system && (
                  <Button variant="outline" className="rounded-sm gap-2 text-destructive hover:text-destructive" data-testid={`delete-role-${current.id}`}
                    onClick={() => { if (window.confirm("Eliminare?")) deleteMut.mutate(current.id); }}>
                    <Trash size={14} /> {t("common.delete")}
                  </Button>
                )}
              </div>

              <div className="mt-8 space-y-6">
                {modules.map((mod) => (
                  <div key={mod.module} data-testid={`role-module-${mod.module}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="overline">{mod.module}</div>
                      <div className="text-[10px] font-mono-plex text-muted-foreground">
                        {mod.permissions.filter(p => (current.permission_keys || []).includes(p.key)).length} / {mod.permissions.length}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 border-t border-border pt-3">
                      {mod.permissions.map((p) => {
                        const checked = (current.permission_keys || []).includes(p.key);
                        return (
                          <label key={p.key} className={`flex items-start gap-3 p-3 border ${checked ? "border-foreground" : "border-border"} cursor-pointer hover:bg-secondary rounded-sm`}>
                            <Checkbox
                              checked={checked}
                              onCheckedChange={() => togglePerm(p.key)}
                              disabled={!has("roles.manage")}
                              data-testid={`perm-toggle-${p.key}`}
                            />
                            <div className="min-w-0">
                              <div className="text-sm font-medium">{p.description}</div>
                              <div className="text-[10px] font-mono-plex text-muted-foreground truncate">{p.key}</div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function CreateRoleDialog({ onSubmit, loading }) {
  const { t } = useTranslation();
  const [name, setName] = useState(""); const [desc, setDesc] = useState("");
  const submit = (e) => { e.preventDefault(); onSubmit({ name: name.trim(), description: desc || null, permission_keys: [] }); };
  return (
    <DialogContent className="rounded-sm" data-testid="create-role-dialog">
      <DialogHeader><DialogTitle className="font-display tracking-tight">{t("roles.new_role")}</DialogTitle><DialogDescription>Crea un nuovo ruolo personalizzato.</DialogDescription></DialogHeader>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <Label className="overline">{t("users.name")}</Label>
          <Input value={name} required onChange={(e) => setName(e.target.value)} className="rounded-sm h-10" data-testid="cr-name" />
        </div>
        <div className="space-y-1.5">
          <Label className="overline">{t("roles.description")}</Label>
          <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} className="rounded-sm" rows={3} data-testid="cr-desc" />
        </div>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="cr-submit">{loading ? t("common.loading") : t("common.create")}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
