import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Plus, Pencil, Trash, Check, Palette, LayoutDashboard, FileText, Percent, Info } from "lucide-react";
import { toast } from "sonner";

const SECTION_LABELS = {
  cover: "Copertina", summary: "Riepilogo", openings: "Vani/Prodotti",
  economic_summary: "Economico", payment_terms: "Pagamenti", clauses: "Clausole",
  disclaimers: "Avvertenze", signature: "Firma",
};

const TRIGGER_LABELS = {
  signature: "Alla firma", survey: "Al rilievo", goods_ready: "A merce pronta",
  before_installation: "Prima posa", on_completion: "A fine lavori", fixed_date: "Data fissa",
};

export default function TemplatesPage() {
  const { has } = useAuth();
  const canManage = has("quotes.manage_templates");
  const qc = useQueryClient();

  const { data: resp } = useQuery({
    queryKey: ["quote-templates"],
    queryFn: async () => (await api.get(`/quote-templates`)).data,
  });
  const templates = resp?.items || [];
  const [selected, setSelected] = React.useState(null);
  React.useEffect(() => {
    if (!selected && templates.length) {
      const def = templates.find((t) => t.is_default) || templates[0];
      setSelected(def.id);
    }
  }, [templates, selected]);
  const template = templates.find((t) => t.id === selected);

  const { data: clauseResp } = useQuery({
    queryKey: ["clauses"],
    queryFn: async () => (await api.get(`/clauses`)).data,
  });
  const clauses = clauseResp?.items || [];

  const patch = useMutation({
    mutationFn: async (body) => (await api.patch(`/quote-templates/${selected}`, body, { headers: { "If-Match": String(template?.version || 1) } })).data,
    onSuccess: () => { toast.success("Template salvato"); qc.invalidateQueries({ queryKey: ["quote-templates"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  const [pt, setPt] = React.useState(null);
  React.useEffect(() => {
    if (template) setPt(template.default_payment_terms || { kind: "installments", installments: [] });
  }, [template]);

  const savePt = () => patch.mutate({ default_payment_terms: pt });

  const updField = (k, v) => patch.mutate({ [k]: v });

  return (
    <div className="space-y-6" data-testid="templates-page">
      <div>
        <div className="overline">Amministrazione</div>
        <h1 className="mt-1 font-display text-3xl font-black tracking-tight">Template PDF preventivo</h1>
        <p className="text-sm text-muted-foreground mt-1">Ogni template ha versione ed è utilizzato dal generatore PDF. Le modifiche vengono archiviate; i PDF già emessi non cambiano.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar */}
        <Card className="rounded-sm border-border p-4">
          <div className="overline mb-2">Template ({templates.length})</div>
          <div className="space-y-1">
            {templates.map((t) => (
              <button key={t.id} onClick={() => setSelected(t.id)}
                className={`w-full text-left px-3 py-2 rounded-sm text-xs transition-colors ${selected === t.id ? "bg-primary text-primary-foreground font-bold" : "hover:bg-secondary"}`}
                data-testid={`tpl-${t.code}`}
              >
                <div className="flex justify-between items-center">
                  <span>{t.name}</span>
                  {t.is_default && <Badge variant="outline" className="rounded-sm text-[9px] bg-white/20">DEFAULT</Badge>}
                </div>
                <div className="text-[10px] opacity-70 font-mono-plex mt-0.5">v.{t.version} · {t.code}</div>
              </button>
            ))}
          </div>
        </Card>

        {/* Detail */}
        <div className="lg:col-span-3">
          {template ? (
            <Tabs defaultValue="general">
              <TabsList className="rounded-sm">
                <TabsTrigger value="general" className="rounded-sm"><LayoutDashboard size={12} className="mr-1" /> Generale</TabsTrigger>
                <TabsTrigger value="style" className="rounded-sm"><Palette size={12} className="mr-1" /> Stile</TabsTrigger>
                <TabsTrigger value="sections" className="rounded-sm">Sezioni</TabsTrigger>
                <TabsTrigger value="payment" className="rounded-sm"><Percent size={12} className="mr-1" /> Pagamenti</TabsTrigger>
                <TabsTrigger value="clauses" className="rounded-sm"><FileText size={12} className="mr-1" /> Clausole</TabsTrigger>
                <TabsTrigger value="fields" className="rounded-sm">Campi azienda</TabsTrigger>
              </TabsList>

              <TabsContent value="general">
                <Card className="rounded-sm border-border p-4 mt-2 space-y-3 text-sm">
                  <div><Label>Nome</Label><Input defaultValue={template.name} disabled={!canManage} onBlur={(e) => e.target.value !== template.name && updField("name", e.target.value)} className="rounded-sm" data-testid="tpl-name" /></div>
                  <div><Label>Testo introduttivo</Label><Textarea defaultValue={template.intro_text || ""} rows={3} disabled={!canManage} onBlur={(e) => e.target.value !== template.intro_text && updField("intro_text", e.target.value)} className="rounded-sm" data-testid="tpl-intro" /></div>
                  <div className="grid grid-cols-3 gap-3">
                    <div><Label>Validità (giorni)</Label><Input type="number" defaultValue={template.validity_days} disabled={!canManage} onBlur={(e) => Number(e.target.value) !== template.validity_days && updField("validity_days", Number(e.target.value))} className="rounded-sm font-mono-plex" /></div>
                    <div><Label>Garanzia (mesi)</Label><Input type="number" defaultValue={template.warranty_months} disabled={!canManage} onBlur={(e) => Number(e.target.value) !== template.warranty_months && updField("warranty_months", Number(e.target.value))} className="rounded-sm font-mono-plex" /></div>
                    <div><Label>Consegna (gg min/max)</Label><div className="flex gap-1"><Input type="number" defaultValue={template.delivery_days_min} disabled={!canManage} onBlur={(e) => Number(e.target.value) !== template.delivery_days_min && updField("delivery_days_min", Number(e.target.value))} className="rounded-sm font-mono-plex" /><Input type="number" defaultValue={template.delivery_days_max} disabled={!canManage} onBlur={(e) => Number(e.target.value) !== template.delivery_days_max && updField("delivery_days_max", Number(e.target.value))} className="rounded-sm font-mono-plex" /></div></div>
                  </div>
                  <div>
                    <Label>Modalità visualizzazione prezzi</Label>
                    <Select value={template.show_prices_mode || "per_line"} onValueChange={(v) => updField("show_prices_mode", v)} disabled={!canManage}>
                      <SelectTrigger className="rounded-sm w-72" data-testid="tpl-show-prices"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="per_line">Dettaglio per riga</SelectItem>
                        <SelectItem value="per_opening">Totale per vano</SelectItem>
                        <SelectItem value="total_only">Solo totale generale</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div><Label>Dicitura misure indicative</Label><Textarea defaultValue={template.measures_disclaimer || ""} rows={3} disabled={!canManage} onBlur={(e) => e.target.value !== template.measures_disclaimer && updField("measures_disclaimer", e.target.value)} className="rounded-sm" data-testid="tpl-measures" /></div>
                  <div><Label>Dicitura immagini</Label><Textarea defaultValue={template.images_disclaimer || ""} rows={2} disabled={!canManage} onBlur={(e) => e.target.value !== template.images_disclaimer && updField("images_disclaimer", e.target.value)} className="rounded-sm" /></div>
                  <div><Label>Informativa privacy</Label><Textarea defaultValue={template.privacy_notice || ""} rows={2} disabled={!canManage} onBlur={(e) => e.target.value !== template.privacy_notice && updField("privacy_notice", e.target.value)} className="rounded-sm" /></div>
                </Card>
              </TabsContent>

              <TabsContent value="style">
                <Card className="rounded-sm border-border p-4 mt-2 space-y-3 text-sm">
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Colore primario</Label>
                      <div className="flex gap-2 items-center">
                        <Input type="color" defaultValue={template.style?.primary_color || "#0F1720"} disabled={!canManage} onBlur={(e) => updField("style", { ...template.style, primary_color: e.target.value })} className="rounded-sm w-16 h-9" />
                        <Input defaultValue={template.style?.primary_color || "#0F1720"} disabled className="rounded-sm font-mono-plex" />
                      </div>
                    </div>
                    <div>
                      <Label>Colore secondario</Label>
                      <div className="flex gap-2 items-center">
                        <Input type="color" defaultValue={template.style?.secondary_color || "#D42027"} disabled={!canManage} onBlur={(e) => updField("style", { ...template.style, secondary_color: e.target.value })} className="rounded-sm w-16 h-9" />
                        <Input defaultValue={template.style?.secondary_color || "#D42027"} disabled className="rounded-sm font-mono-plex" />
                      </div>
                    </div>
                    <div>
                      <Label>Larghezza logo (mm)</Label>
                      <Input type="number" defaultValue={template.style?.logo_width_mm || 40} disabled={!canManage} onBlur={(e) => updField("style", { ...template.style, logo_width_mm: Number(e.target.value) })} className="rounded-sm font-mono-plex" />
                    </div>
                  </div>
                </Card>
              </TabsContent>

              <TabsContent value="sections">
                <Card className="rounded-sm border-border p-4 mt-2">
                  <Table>
                    <TableHeader><TableRow><TableHead className="overline">Ordine</TableHead><TableHead className="overline">Chiave</TableHead><TableHead className="overline">Titolo</TableHead><TableHead className="overline">Visibile</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {(template.sections || []).sort((a, b) => a.order_index - b.order_index).map((s, i) => (
                        <TableRow key={s.key} data-testid={`sec-${s.key}`}>
                          <TableCell className="font-mono-plex text-xs">{s.order_index}</TableCell>
                          <TableCell className="text-xs">{SECTION_LABELS[s.key] || s.key}</TableCell>
                          <TableCell><Input defaultValue={s.title || SECTION_LABELS[s.key]} className="rounded-sm h-8 text-xs" onBlur={(e) => { const secs = [...template.sections]; secs[i] = { ...secs[i], title: e.target.value }; updField("sections", secs); }} /></TableCell>
                          <TableCell><Switch checked={s.visible} onCheckedChange={(v) => { const secs = [...template.sections]; secs[i] = { ...secs[i], visible: v }; updField("sections", secs); }} data-testid={`sec-visible-${s.key}`} /></TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              </TabsContent>

              <TabsContent value="payment">
                <Card className="rounded-sm border-border p-4 mt-2 space-y-3 text-sm">
                  <div className="text-xs text-muted-foreground">Termini di pagamento predefiniti applicati ai nuovi preventivi (modificabili per singolo preventivo).</div>
                  <div className="space-y-2">
                    {(pt?.installments || []).map((inst, i) => (
                      <div key={i} className="grid grid-cols-12 gap-2" data-testid={`pt-inst-${i}`}>
                        <div className="col-span-4">
                          <Select value={inst.trigger} onValueChange={(v) => setPt({ ...pt, installments: pt.installments.map((x, j) => j === i ? { ...x, trigger: v } : x) })}>
                            <SelectTrigger className="rounded-sm h-9 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>{Object.entries(TRIGGER_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
                          </Select>
                        </div>
                        <div className="col-span-2"><Input type="number" placeholder="%" value={inst.percent || ""} onChange={(e) => setPt({ ...pt, installments: pt.installments.map((x, j) => j === i ? { ...x, percent: Number(e.target.value) } : x) })} className="rounded-sm h-9 font-mono-plex text-xs" /></div>
                        <div className="col-span-2"><Input type="number" placeholder="€" value={inst.amount || ""} onChange={(e) => setPt({ ...pt, installments: pt.installments.map((x, j) => j === i ? { ...x, amount: Number(e.target.value) } : x) })} className="rounded-sm h-9 font-mono-plex text-xs" /></div>
                        <div className="col-span-3"><Input placeholder="Nota" value={inst.note || ""} onChange={(e) => setPt({ ...pt, installments: pt.installments.map((x, j) => j === i ? { ...x, note: e.target.value } : x) })} className="rounded-sm h-9 text-xs" /></div>
                        <div className="col-span-1"><Button variant="ghost" size="sm" className="text-destructive" onClick={() => setPt({ ...pt, installments: pt.installments.filter((_, j) => j !== i) })}><Trash size={12} /></Button></div>
                      </div>
                    ))}
                  </div>
                  <Button size="sm" variant="outline" className="rounded-sm" onClick={() => setPt({ ...pt, installments: [...(pt?.installments || []), { trigger: "signature", percent: 0 }] })} data-testid="pt-add"><Plus size={12} className="mr-1" /> Rata</Button>
                  <div><Label>Nota</Label><Input value={pt?.display_note || ""} onChange={(e) => setPt({ ...pt, display_note: e.target.value })} className="rounded-sm" /></div>
                  <Button className="rounded-sm" onClick={savePt} disabled={!canManage} data-testid="pt-save">Salva pagamenti</Button>
                </Card>
              </TabsContent>

              <TabsContent value="clauses">
                <Card className="rounded-sm border-border p-4 mt-2 space-y-2 text-sm">
                  <div className="text-xs text-muted-foreground">Clausole collegate al template. Le obbligatorie compaiono sempre nel PDF; le opzionali sono selezionabili in fase di emissione.</div>
                  <Table>
                    <TableHeader><TableRow><TableHead className="overline">Codice</TableHead><TableHead className="overline">Titolo</TableHead><TableHead className="overline">Categoria</TableHead><TableHead className="overline">Ruolo</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {clauses.map((c) => {
                        const isMand = (template.mandatory_clause_codes || []).includes(c.code);
                        const isOpt = (template.optional_clause_codes || []).includes(c.code);
                        return (
                          <TableRow key={c.id} data-testid={`clr-${c.code}`}>
                            <TableCell className="font-mono-plex text-[10px]">{c.code}</TableCell>
                            <TableCell className="text-xs">{c.title}</TableCell>
                            <TableCell><Badge variant="outline" className="rounded-sm text-[10px]">{c.category}</Badge></TableCell>
                            <TableCell>
                              <Select value={isMand ? "mandatory" : (isOpt ? "optional" : "none")} onValueChange={(v) => {
                                const m = new Set(template.mandatory_clause_codes || []);
                                const o = new Set(template.optional_clause_codes || []);
                                m.delete(c.code); o.delete(c.code);
                                if (v === "mandatory") m.add(c.code);
                                if (v === "optional") o.add(c.code);
                                patch.mutate({ mandatory_clause_codes: [...m], optional_clause_codes: [...o] });
                              }} disabled={!canManage}>
                                <SelectTrigger className="rounded-sm h-8 w-32 text-xs" data-testid={`clr-role-${c.code}`}><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="none">Non inclusa</SelectItem>
                                  <SelectItem value="optional">Opzionale</SelectItem>
                                  <SelectItem value="mandatory">Obbligatoria</SelectItem>
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

              <TabsContent value="fields">
                <Card className="rounded-sm border-border p-4 mt-2 space-y-2 text-sm">
                  <div className="text-xs text-muted-foreground">Campi azienda visualizzati nel PDF (letti dai dati aziendali).</div>
                  {Object.entries(template.show_fields || {}).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between border-b pb-2">
                      <span className="text-xs font-mono-plex">{k}</span>
                      <Switch checked={!!v} onCheckedChange={(nv) => updField("show_fields", { ...template.show_fields, [k]: nv })} data-testid={`show-${k}`} />
                    </div>
                  ))}
                </Card>
              </TabsContent>
            </Tabs>
          ) : (
            <div className="text-muted-foreground text-sm">Seleziona un template.</div>
          )}
        </div>
      </div>
    </div>
  );
}
