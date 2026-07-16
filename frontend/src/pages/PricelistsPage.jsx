import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Plus, Pencil, Trash, Check, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const CATEGORY_LABELS = {
  generic: "Generale", base: "Base", color: "Colore", glass: "Vetro", hardware: "Ferramenta",
  roller: "Tapparella", screen: "Zanzariera", shutter: "Persiana", box: "Cassonetto", sill: "Davanzale",
  discount: "Sconto", installation: "Posa",
};

const EFFECT_LABELS = { pct: "Percentuale", fixed: "Fisso €", set: "Sovrascrivi prezzo" };

export default function PricelistsPage() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const canManage = has("pricelists.manage");
  const [tab, setTab] = React.useState("pricelists");

  const { data: plResp } = useQuery({
    queryKey: ["pricelists"],
    queryFn: async () => (await api.get(`/pricelists`)).data,
  });
  const pricelists = plResp?.items || [];
  const [selectedPl, setSelectedPl] = React.useState(null);
  React.useEffect(() => {
    if (!selectedPl && pricelists.length) {
      const def = pricelists.find((p) => p.is_default) || pricelists[0];
      setSelectedPl(def.id);
    }
  }, [pricelists, selectedPl]);

  const { data: rulesResp } = useQuery({
    queryKey: ["price-rules", selectedPl],
    queryFn: async () => (await api.get(`/price-rules`, { params: { pricelist_id: selectedPl } })).data,
    enabled: !!selectedPl,
  });
  const rules = rulesResp?.items || [];

  const [ruleForm, setRuleForm] = React.useState(null);

  const createPl = useMutation({
    mutationFn: async (body) => (await api.post(`/pricelists`, body)).data,
    onSuccess: () => { toast.success("Listino creato"); qc.invalidateQueries({ queryKey: ["pricelists"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });
  const delPl = useMutation({
    mutationFn: async (pid) => (await api.delete(`/pricelists/${pid}`)).data,
    onSuccess: () => { toast.success("Listino eliminato"); qc.invalidateQueries({ queryKey: ["pricelists"] }); },
  });
  const saveRule = useMutation({
    mutationFn: async (body) => {
      if (body.id) {
        return (await api.patch(`/price-rules/${body.id}`, body, { headers: { "If-Match": String(body.version || 1) } })).data;
      }
      return (await api.post(`/price-rules`, body)).data;
    },
    onSuccess: () => { toast.success("Regola salvata"); qc.invalidateQueries({ queryKey: ["price-rules", selectedPl] }); setRuleForm(null); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });
  const delRule = useMutation({
    mutationFn: async (rid) => (await api.delete(`/price-rules/${rid}`)).data,
    onSuccess: () => { toast.success("Regola eliminata"); qc.invalidateQueries({ queryKey: ["price-rules", selectedPl] }); },
  });

  return (
    <div className="space-y-6" data-testid="pricelists-page">
      <div>
        <div className="overline">Amministrazione</div>
        <h1 className="mt-1 font-display text-3xl font-black tracking-tight">Listini &amp; Regole prezzo</h1>
        <p className="text-sm text-muted-foreground mt-1">Motore formule sicuro senza <code>eval</code>. Ogni regola è auditata e versionata.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Pricelists sidebar */}
        <Card className="rounded-sm border-border p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="overline">Listini ({pricelists.length})</div>
            {canManage && (
              <Button size="sm" className="rounded-sm" onClick={() => {
                const name = prompt("Nome nuovo listino");
                if (name) createPl.mutate({ name, is_default: pricelists.length === 0 });
              }} data-testid="pricelist-new"><Plus size={12} /></Button>
            )}
          </div>
          <div className="space-y-1">
            {pricelists.map((p) => (
              <button key={p.id} onClick={() => setSelectedPl(p.id)}
                className={`w-full text-left px-3 py-2 rounded-sm text-xs transition-colors ${selectedPl === p.id ? "bg-primary text-primary-foreground font-bold" : "hover:bg-secondary"}`}
                data-testid={`pricelist-${p.id}`}
              >
                <div className="flex justify-between items-center">
                  <span>{p.name}</span>
                  {p.is_default && <Badge variant="outline" className="rounded-sm text-[9px] bg-white/20">DEFAULT</Badge>}
                </div>
                <div className="text-[10px] opacity-70 font-mono-plex mt-0.5">{p.currency} · v.{p.version}</div>
              </button>
            ))}
          </div>
        </Card>

        {/* Rules table */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between">
            <div className="overline">Regole ({rules.length})</div>
            {canManage && selectedPl && (
              <Button className="rounded-sm" onClick={() => setRuleForm({
                pricelist_id: selectedPl, code: "", name: "",
                category: "generic", conditions: [], formula: "0",
                effect_type: "pct", priority: 100, active: true,
              })} data-testid="rule-new"><Plus size={14} className="mr-1" /> Nuova regola</Button>
            )}
          </div>
          <Card className="rounded-sm border-border p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="overline">Codice</TableHead>
                  <TableHead className="overline">Nome</TableHead>
                  <TableHead className="overline">Categoria</TableHead>
                  <TableHead className="overline">Formula</TableHead>
                  <TableHead className="overline">Effetto</TableHead>
                  <TableHead className="overline">Priorità</TableHead>
                  <TableHead className="overline">Attiva</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rules.map((r) => (
                  <TableRow key={r.id} data-testid={`rule-${r.code}`}>
                    <TableCell className="font-mono-plex text-xs">{r.code}</TableCell>
                    <TableCell className="text-sm">{r.name}</TableCell>
                    <TableCell><Badge variant="outline" className="rounded-sm text-[10px]">{CATEGORY_LABELS[r.category] || r.category}</Badge></TableCell>
                    <TableCell className="font-mono-plex text-[11px] max-w-[200px] truncate" title={r.formula}>{r.formula}</TableCell>
                    <TableCell className="text-xs">{EFFECT_LABELS[r.effect_type]}</TableCell>
                    <TableCell className="font-mono-plex text-xs">{r.priority}</TableCell>
                    <TableCell>{r.active ? <Check size={14} className="text-emerald-600" /> : <AlertTriangle size={14} className="text-muted-foreground" />}</TableCell>
                    <TableCell>
                      {canManage && (
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" onClick={() => setRuleForm(r)} data-testid={`rule-edit-${r.code}`}><Pencil size={12} /></Button>
                          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Eliminare regola ${r.code}?`)) delRule.mutate(r.id); }}><Trash size={12} /></Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {rules.length === 0 && <TableRow><TableCell colSpan={8} className="text-center py-8 text-sm text-muted-foreground">Nessuna regola. Crea la prima per personalizzare i prezzi.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </div>
      </div>

      {ruleForm && <RuleEditor rule={ruleForm} onClose={() => setRuleForm(null)} onSave={(v) => saveRule.mutate(v)} />}
    </div>
  );
}

function RuleEditor({ rule, onClose, onSave }) {
  const [form, setForm] = React.useState(rule);
  const [validating, setValidating] = React.useState(false);
  const [validated, setValidated] = React.useState(null);
  const upd = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const isEdit = !!rule.id;

  const validate = async () => {
    setValidating(true);
    try {
      const res = await api.post(`/price-rules/validate`, { formula: form.formula });
      setValidated(res.data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setValidating(false); }
  };

  const addCond = () => upd("conditions", [...(form.conditions || []), { field: "", op: "eq", value: "" }]);
  const updCond = (i, k, v) => upd("conditions", form.conditions.map((c, j) => j === i ? { ...c, [k]: v } : c));
  const delCond = (i) => upd("conditions", form.conditions.filter((_, j) => j !== i));

  return (
    <Dialog open={true} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Modifica ${rule.code}` : "Nuova regola prezzo"}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <Label>Codice</Label>
            <Input value={form.code} onChange={(e) => upd("code", e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_"))} className="rounded-sm font-mono-plex" disabled={isEdit} data-testid="rule-code" />
          </div>
          <div>
            <Label>Nome</Label>
            <Input value={form.name} onChange={(e) => upd("name", e.target.value)} className="rounded-sm" data-testid="rule-name" />
          </div>
          <div>
            <Label>Categoria</Label>
            <Select value={form.category} onValueChange={(v) => upd("category", v)}>
              <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(CATEGORY_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Effetto</Label>
            <Select value={form.effect_type} onValueChange={(v) => upd("effect_type", v)}>
              <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(EFFECT_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Priorità (bassa = prima)</Label>
            <Input type="number" value={form.priority} onChange={(e) => upd("priority", Number(e.target.value))} className="rounded-sm font-mono-plex" />
          </div>
          <div className="flex items-end gap-2">
            <Switch checked={!!form.active} onCheckedChange={(v) => upd("active", v)} data-testid="rule-active" /> Attiva
          </div>
          <div className="col-span-2">
            <Label>
              Formula
              <span className="text-[10px] text-muted-foreground ml-1 font-mono-plex">
                variabili: width, height, area, base_price, quantity, perimeter · funzioni: min, max, round, ceil, floor
              </span>
            </Label>
            <div className="flex gap-2">
              <Textarea value={form.formula} onChange={(e) => { upd("formula", e.target.value); setValidated(null); }} className="rounded-sm font-mono-plex" rows={2} data-testid="rule-formula" />
              <Button variant="outline" className="rounded-sm h-auto" onClick={validate} disabled={validating}>Valida</Button>
            </div>
            {validated && (validated.ok ? <div className="text-[11px] text-emerald-600 mt-1">✓ Formula valida</div> : <div className="text-[11px] text-destructive mt-1">✗ {validated.error}</div>)}
          </div>

          <div className="col-span-2">
            <div className="flex items-center justify-between mb-1">
              <Label>Condizioni (AND)</Label>
              <Button size="sm" variant="outline" className="rounded-sm" onClick={addCond}><Plus size={12} /> Cond.</Button>
            </div>
            <div className="space-y-1 max-h-40 overflow-auto">
              {(form.conditions || []).map((c, i) => (
                <div key={i} className="grid grid-cols-12 gap-1">
                  <Input placeholder="campo (es. color_kind)" value={c.field} onChange={(e) => updCond(i, "field", e.target.value)} className="col-span-4 rounded-sm h-8 text-xs font-mono-plex" />
                  <Select value={c.op} onValueChange={(v) => updCond(i, "op", v)}>
                    <SelectTrigger className="col-span-2 rounded-sm h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>{["eq", "neq", "in", "nin", "exists", "truthy", "falsy", "gte", "lte"].map((op) => <SelectItem key={op} value={op}>{op}</SelectItem>)}</SelectContent>
                  </Select>
                  <Input placeholder="valore" value={String(c.value ?? "")} onChange={(e) => updCond(i, "value", e.target.value)} className="col-span-5 rounded-sm h-8 text-xs font-mono-plex" />
                  <Button variant="ghost" size="sm" className="col-span-1 text-destructive" onClick={() => delCond(i)}><Trash size={12} /></Button>
                </div>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose}>Annulla</Button>
          <Button className="rounded-sm" onClick={() => onSave(form)} disabled={!form.code || !form.name} data-testid="rule-save">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
