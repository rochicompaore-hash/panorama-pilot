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
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Plus, UserPlus, TrendUp, Clock, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

export default function LeadsPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState("kanban");
  const [q, setQ] = useState("");
  const [openCreate, setOpenCreate] = useState(false);

  const { data: kanban } = useQuery({ queryKey: ["leads-kanban"], queryFn: async () => (await api.get("/leads/kanban")).data, enabled: tab === "kanban" });
  const { data: list } = useQuery({ queryKey: ["leads-list", q], queryFn: async () => (await api.get("/leads", { params: { q: q || undefined, limit: 200 } })).data, enabled: tab === "list" });

  const updateStage = useMutation({
    mutationFn: async ({ id, stage_id }) => (await api.patch(`/leads/${id}`, { stage_id })).data,
    onSuccess: () => { toast.success("Aggiornato"); qc.invalidateQueries({ queryKey: ["leads-kanban"] }); qc.invalidateQueries({ queryKey: ["leads-list"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const createLead = useMutation({
    mutationFn: async (payload) => (await api.post("/leads", payload)).data,
    onSuccess: (d) => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["leads-kanban"] }); qc.invalidateQueries({ queryKey: ["leads-list"] }); setOpenCreate(false); navigate(`/leads/${d.id}`); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="space-y-8" data-testid="leads-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("crm.leads.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("crm.leads.title")}</h1>
        </div>
        {has("crm.leads.create") && (
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button className="rounded-sm h-11 gap-2" data-testid="new-lead-button"><UserPlus size={16} weight="bold" />{t("crm.leads.new_lead")}</Button>
            </DialogTrigger>
            <NewLeadDialog onSubmit={(p) => createLead.mutate(p)} loading={createLead.isPending} />
          </Dialog>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm">
          <TabsTrigger value="kanban" className="rounded-sm" data-testid="leads-tab-kanban">{t("crm.leads.board")}</TabsTrigger>
          <TabsTrigger value="list" className="rounded-sm" data-testid="leads-tab-list">{t("crm.leads.list")}</TabsTrigger>
        </TabsList>

        <TabsContent value="kanban" className="mt-4">
          <div className="flex gap-3 overflow-x-auto pb-4" data-testid="kanban-board">
            {(kanban?.columns || []).map((col) => (
              <div key={col.stage.id} className="min-w-[280px] w-[280px] bg-secondary/40 rounded-sm border border-border" data-testid={`kanban-col-${col.stage.id}`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  const id = e.dataTransfer.getData("text/plain");
                  if (id) updateStage.mutate({ id, stage_id: col.stage.id });
                }}
              >
                <div className="px-3 py-2 border-b border-border flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: col.stage.color }} />
                    <span className="text-sm font-medium">{col.stage.name}</span>
                  </div>
                  <span className="text-[10px] font-mono-plex text-muted-foreground">{col.leads.length}</span>
                </div>
                <div className="p-2 space-y-2 min-h-[200px] max-h-[70vh] overflow-y-auto">
                  {col.leads.map((l) => (
                    <div
                      key={l.id}
                      draggable
                      onDragStart={(e) => e.dataTransfer.setData("text/plain", l.id)}
                      onClick={() => navigate(`/leads/${l.id}`)}
                      className="cursor-grab active:cursor-grabbing bg-card border border-border p-3 rounded-sm card-lift"
                      data-testid={`kanban-card-${l.id}`}
                    >
                      <div className="text-sm font-medium truncate">{`${l.first_name || ""} ${l.last_name || ""}`.trim() || l.company_name || l.email || "—"}</div>
                      {l.company_name && (l.first_name || l.last_name) && <div className="text-[10px] text-muted-foreground truncate">{l.company_name}</div>}
                      <div className="mt-2 flex items-center justify-between text-[10px] font-mono-plex">
                        <span className="text-muted-foreground">{fmtEUR(l.estimated_value)}</span>
                        <Badge variant="outline" className="rounded-sm">{l.probability}%</Badge>
                      </div>
                      {l.intelligence?.next_action_suggestion && (
                        <div className={`mt-2 text-[10px] flex items-center gap-1 ${l.intelligence.next_action_suggestion.priority === "high" ? "text-[hsl(var(--brand-red))]" : "text-muted-foreground"}`}>
                          <Warning size={10} weight="bold" />
                          {l.intelligence.next_action_suggestion.label}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="list" className="mt-4">
          <Card className="rounded-sm border-border p-4 mb-4">
            <Input placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)}
              className="rounded-sm h-10 max-w-sm" data-testid="leads-search" />
          </Card>
          <Card className="rounded-sm border-border overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead className="overline">Lead</TableHead>
                <TableHead className="overline">{t("crm.leads.value")}</TableHead>
                <TableHead className="overline">{t("crm.leads.probability")}</TableHead>
                <TableHead className="overline">{t("crm.leads.next_action")}</TableHead>
                <TableHead className="overline">Giorni</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {(list?.items || []).map((l) => (
                  <TableRow key={l.id} className="cursor-pointer" onClick={() => navigate(`/leads/${l.id}`)} data-testid={`lead-row-${l.id}`}>
                    <TableCell>
                      <div className="text-sm font-medium">{`${l.first_name || ""} ${l.last_name || ""}`.trim() || l.company_name || l.email || "—"}</div>
                      <div className="text-xs text-muted-foreground">{l.email || l.phone || l.company_name}</div>
                    </TableCell>
                    <TableCell className="font-mono-plex">{fmtEUR(l.estimated_value)}</TableCell>
                    <TableCell><Badge variant="outline" className="rounded-sm">{l.probability}%</Badge></TableCell>
                    <TableCell className="text-xs">{l.intelligence?.next_action_suggestion?.label}</TableCell>
                    <TableCell className="text-xs">{l.intelligence?.days_since_contact != null ? `${l.intelligence.days_since_contact}g` : "—"}</TableCell>
                  </TableRow>
                ))}
                {(list?.items || []).length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-10 text-sm text-muted-foreground">{t("common.no_results")}</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function NewLeadDialog({ onSubmit, loading }) {
  const [f, setF] = useState({ first_name: "", last_name: "", company_name: "", email: "", phone: "", whatsapp: "", estimated_value: 0, source: "website" });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <DialogContent className="rounded-sm max-w-lg" data-testid="new-lead-dialog">
      <DialogHeader>
        <DialogTitle className="font-display tracking-tight">Nuovo lead</DialogTitle>
        <DialogDescription>Registra una nuova opportunità commerciale.</DialogDescription>
      </DialogHeader>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit({ ...f, estimated_value: Number(f.estimated_value || 0) }); }} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Nome</Label><Input value={f.first_name} onChange={(e) => upd("first_name", e.target.value)} className="rounded-sm h-10" data-testid="nl-first" /></div>
          <div><Label className="overline">Cognome</Label><Input value={f.last_name} onChange={(e) => upd("last_name", e.target.value)} className="rounded-sm h-10" data-testid="nl-last" /></div>
        </div>
        <div><Label className="overline">Azienda (opzionale)</Label><Input value={f.company_name} onChange={(e) => upd("company_name", e.target.value)} className="rounded-sm h-10" data-testid="nl-company" /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">Email</Label><Input type="email" value={f.email} onChange={(e) => upd("email", e.target.value)} className="rounded-sm h-10" data-testid="nl-email" /></div>
          <div><Label className="overline">Telefono</Label><Input value={f.phone} onChange={(e) => upd("phone", e.target.value)} className="rounded-sm h-10" data-testid="nl-phone" /></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label className="overline">WhatsApp</Label><Input value={f.whatsapp} onChange={(e) => upd("whatsapp", e.target.value)} className="rounded-sm h-10" data-testid="nl-whatsapp" /></div>
          <div><Label className="overline">Valore stimato €</Label><Input type="number" min={0} value={f.estimated_value} onChange={(e) => upd("estimated_value", e.target.value)} className="rounded-sm h-10" data-testid="nl-value" /></div>
        </div>
        <div><Label className="overline">Fonte</Label><Input value={f.source} onChange={(e) => upd("source", e.target.value)} className="rounded-sm h-10" data-testid="nl-source" /></div>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="nl-submit">{loading ? "…" : "Crea lead"}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
