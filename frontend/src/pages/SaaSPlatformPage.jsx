import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Table, TableHead, TableRow, TableHeader, TableBody, TableCell } from "@/components/ui/table";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Info } from "@phosphor-icons/react";

const STATES = ["active", "trial", "grace_period", "read_only", "suspended", "expired", "disabled"];
const STATE_COLORS = {
  active: "bg-green-100 text-green-800 border-green-300",
  trial: "bg-blue-100 text-blue-800 border-blue-300",
  grace_period: "bg-amber-100 text-amber-800 border-amber-300",
  read_only: "bg-slate-100 text-slate-800 border-slate-300",
  suspended: "bg-red-100 text-red-800 border-red-300",
  expired: "bg-red-100 text-red-800 border-red-300",
  disabled: "bg-gray-100 text-gray-800 border-gray-300",
};

export default function SaaSPlatformPage() {
  const [tab, setTab] = useState("plans");
  const [modules, setModules] = useState([]);
  const [plans, setPlans] = useState([]);
  const [deps, setDeps] = useState([]);
  const [entitlement, setEntitlement] = useState(null);
  const [usage, setUsage] = useState(null);

  const load = async () => {
    try {
      const [m, p, d, e, u] = await Promise.all([
        api.get("/platform/saas/modules"),
        api.get("/platform/saas/plans"),
        api.get("/platform/saas/dependencies"),
        api.get("/platform/saas/me/entitlement"),
        api.get("/platform/saas/me/usage"),
      ]);
      setModules(m.data.items || []);
      setPlans(p.data.items || []);
      setDeps(d.data.items || []);
      setEntitlement(e.data);
      setUsage(u.data);
    } catch (err) { toast.error("Errore caricamento SaaS"); }
  };
  useEffect(() => { load(); }, []);

  const setModuleState = async (tenantId, code, newState) => {
    try {
      await api.post(`/platform/saas/entitlements/${tenantId}/modules/${code}/state`, {state: newState});
      toast.success(`Modulo ${code}: ${newState}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
  };

  return (
    <div className="space-y-6" data-testid="saas-platform-page">
      <div>
        <div className="overline text-muted-foreground">Platform Owner</div>
        <h1 className="font-display text-3xl font-black tracking-tight">SaaS Modularization</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Gestione piani, moduli, entitlement e dipendenze. Nessuna integrazione Stripe attiva.
        </p>
      </div>

      {entitlement && (
        <Card className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="overline">Il mio tenant</div>
              <div className="text-lg font-bold">Piano: {entitlement.plan_code || "—"}</div>
              <div className="text-xs text-muted-foreground">
                Moduli inclusi: {(entitlement.plan_snapshot_module_codes || []).length}/{modules.length}
              </div>
            </div>
            {usage && (
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <div className="text-2xl font-bold">{usage.users}</div>
                  <div className="text-[10px] overline">Utenti</div>
                </div>
                <div>
                  <div className="text-2xl font-bold">{usage.legal_entities}</div>
                  <div className="text-[10px] overline">Società</div>
                </div>
                <div>
                  <div className="text-2xl font-bold">{usage.quotes_total}</div>
                  <div className="text-[10px] overline">Preventivi</div>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="plans" data-testid="saas-tab-plans">Piani</TabsTrigger>
          <TabsTrigger value="modules" data-testid="saas-tab-modules">Moduli e stato</TabsTrigger>
          <TabsTrigger value="dependencies" data-testid="saas-tab-deps">Dipendenze</TabsTrigger>
        </TabsList>

        <TabsContent value="plans">
          <div className="grid md:grid-cols-3 gap-4">
            {plans.map(p => (
              <Card key={p.id} className="p-5" data-testid={`plan-card-${p.code}`}>
                <div className="overline text-muted-foreground">{p.tier.toUpperCase()}</div>
                <div className="text-xl font-bold">{p.name}</div>
                <div className="text-xs text-muted-foreground mt-1">{p.description || "—"}</div>
                <div className="mt-4 space-y-1 text-sm">
                  <div>👥 Utenti: {p.max_users || "∞"}</div>
                  <div>💾 Storage: {p.max_storage_mb ? p.max_storage_mb+" MB" : "∞"}</div>
                  <div>🏢 Società: {p.max_legal_entities || "∞"}</div>
                  <div>⏱ Trial: {p.trial_days} giorni</div>
                </div>
                <div className="mt-4">
                  <div className="text-[11px] overline mb-1">Moduli inclusi</div>
                  <div className="flex flex-wrap gap-1">
                    {(p.included_module_codes || []).map(c => (
                      <Badge key={c} variant="outline" className="text-[10px]">{c}</Badge>
                    ))}
                  </div>
                </div>
                {p.is_demo && (
                  <Badge className="mt-3" variant="outline">CONFIG DEMO</Badge>
                )}
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="modules">
          <Card className="p-5">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Modulo</TableHead>
                <TableHead>Categoria</TableHead>
                <TableHead>Stato effettivo</TableHead>
                <TableHead>Azione (Platform Owner)</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {modules.map(m => {
                  const effState = entitlement?.effective_states?.[m.code]?.state || "unknown";
                  return (
                    <TableRow key={m.code} data-testid={`module-row-${m.code}`}>
                      <TableCell>
                        <div className="font-medium">{m.label}</div>
                        <div className="text-xs text-muted-foreground">{m.code}</div>
                      </TableCell>
                      <TableCell><Badge variant="outline">{m.category}</Badge></TableCell>
                      <TableCell>
                        <Badge className={STATE_COLORS[effState] || ""} data-testid={`module-state-${m.code}`}>
                          {effState}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Select value={effState} onValueChange={v => setModuleState(entitlement.tenant_id, m.code, v)}>
                          <SelectTrigger className="w-40" data-testid={`module-select-${m.code}`}><SelectValue/></SelectTrigger>
                          <SelectContent>
                            {STATES.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="dependencies">
          <Card className="p-5">
            <Alert className="mb-4">
              <Info size={16}/>
              <AlertDescription>
                Le dipendenze bloccano l'attivazione di un modulo se le sue precondizioni non sono soddisfatte.
              </AlertDescription>
            </Alert>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Modulo</TableHead><TableHead>Richiede</TableHead><TableHead>Tipo</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {deps.map(d => (
                  <TableRow key={d.id}>
                    <TableCell><Badge>{d.module_code}</Badge></TableCell>
                    <TableCell><Badge variant="outline">{d.requires_module}</Badge></TableCell>
                    <TableCell>{d.hard ? "🔒 hard" : "⚠️ soft"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
