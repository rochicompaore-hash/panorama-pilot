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
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Check, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

const PRIORITY_COLORS = { low: "#71717A", normal: "#3B82F6", high: "#F59E0B", urgent: "#D9381E" };

export default function TasksPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState("mine");
  const [open, setOpen] = useState(false);
  const params = tab === "mine" ? { mine: true } : {};
  const { data } = useQuery({ queryKey: ["tasks", tab], queryFn: async () => (await api.get("/tasks", { params: { ...params, limit: 200 } })).data });

  const createMut = useMutation({ mutationFn: async (p) => (await api.post("/tasks", p)).data, onSuccess: () => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["tasks"] }); setOpen(false); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const patchMut = useMutation({ mutationFn: async ({ id, patch }) => (await api.patch(`/tasks/${id}`, patch)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }) });
  const delMut = useMutation({ mutationFn: async (id) => (await api.delete(`/tasks/${id}`)).data, onSuccess: () => { toast.success(t("toast.deleted")); qc.invalidateQueries({ queryKey: ["tasks"] }); } });

  return (
    <div className="space-y-8" data-testid="tasks-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("crm.tasks.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("crm.tasks.title")}</h1>
        </div>
        {has("crm.tasks.manage") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button className="rounded-sm h-11 gap-2" data-testid="new-task-button"><Plus size={16} weight="bold" />{t("crm.tasks.new_task")}</Button></DialogTrigger>
            <NewTaskDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="mine" className="rounded-sm" data-testid="tasks-tab-mine">{t("crm.tasks.mine")}</TabsTrigger>
          <TabsTrigger value="all" className="rounded-sm" data-testid="tasks-tab-all">{t("crm.tasks.all")}</TabsTrigger>
        </TabsList>
      </Tabs>

      <Card className="rounded-sm border-border divide-y divide-border">
        {(data?.items || []).map((tk) => {
          const overdue = tk.due_at && tk.task_status !== "done" && new Date(tk.due_at) < new Date();
          return (
            <div key={tk.id} className="p-4 flex items-start gap-4" data-testid={`task-row-${tk.id}`}>
              <input type="checkbox" checked={tk.task_status === "done"} onChange={(e) => patchMut.mutate({ id: tk.id, patch: { task_status: e.target.checked ? "done" : "open" } })}
                className="mt-1 h-4 w-4 accent-[hsl(var(--brand-red))]" data-testid={`task-check-${tk.id}`} />
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-medium ${tk.task_status === "done" ? "line-through text-muted-foreground" : ""}`}>{tk.title}</div>
                {tk.description && <div className="text-xs text-muted-foreground mt-0.5">{tk.description}</div>}
                <div className="mt-2 flex items-center gap-2 text-[10px] font-mono-plex text-muted-foreground">
                  <Badge variant="outline" className="rounded-sm text-[10px]" style={{ borderColor: PRIORITY_COLORS[tk.priority] }}>{tk.priority}</Badge>
                  {tk.due_at && <span className={overdue ? "text-[hsl(var(--brand-red))] font-bold" : ""}>Scad. {new Date(tk.due_at).toLocaleDateString("it-IT")}</span>}
                  {overdue && <span className="text-[hsl(var(--brand-red))] font-bold">RITARDO</span>}
                </div>
              </div>
              {has("crm.tasks.manage") && (
                <Button variant="ghost" size="sm" className="rounded-sm text-destructive hover:text-destructive" onClick={() => delMut.mutate(tk.id)} data-testid={`task-delete-${tk.id}`}><Trash size={14} /></Button>
              )}
            </div>
          );
        })}
        {(data?.items || []).length === 0 && <div className="p-10 text-center text-sm text-muted-foreground">Nessun task</div>}
      </Card>
    </div>
  );
}

function NewTaskDialog({ onSubmit, loading }) {
  const [f, setF] = useState({ title: "", description: "", priority: "normal", due_at: "" });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <DialogContent className="rounded-sm" data-testid="new-task-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo task</DialogTitle>
        <DialogDescription>Aggiungi un promemoria o attività.</DialogDescription>
      </DialogHeader>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit({ ...f, due_at: f.due_at || null }); }} className="space-y-3">
        <div><Label className="overline">Titolo</Label><Input required value={f.title} onChange={(e) => upd("title", e.target.value)} className="rounded-sm h-10" data-testid="nt-title" /></div>
        <div><Label className="overline">Note</Label><Textarea value={f.description} onChange={(e) => upd("description", e.target.value)} rows={3} className="rounded-sm" data-testid="nt-desc" /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Priorità</Label>
            <Select value={f.priority} onValueChange={(v) => upd("priority", v)}>
              <SelectTrigger className="rounded-sm h-10" data-testid="nt-priority"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="low">Bassa</SelectItem><SelectItem value="normal">Normale</SelectItem><SelectItem value="high">Alta</SelectItem><SelectItem value="urgent">Urgente</SelectItem></SelectContent>
            </Select>
          </div>
          <div><Label className="overline">Scadenza</Label><Input type="datetime-local" value={f.due_at} onChange={(e) => upd("due_at", e.target.value)} className="rounded-sm h-10" data-testid="nt-due" /></div>
        </div>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="nt-submit">{loading ? "…" : "Crea task"}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
