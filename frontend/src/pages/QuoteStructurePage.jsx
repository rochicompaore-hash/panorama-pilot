import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Plus, House, Buildings, Copy, Trash, Warning, ArrowRight, PencilSimple, Info } from "@phosphor-icons/react";

const ENV_KINDS = [
  ["kitchen", "Cucina"], ["living_room", "Soggiorno"],
  ["bedroom_master", "Camera matrimoniale"], ["bedroom_kid", "Cameretta"],
  ["bathroom", "Bagno"], ["laundry", "Lavanderia"],
  ["study", "Studio"], ["corridor", "Corridoio"],
  ["attic", "Mansarda"], ["garage", "Garage"],
  ["cellar", "Cantina"], ["tavern", "Taverna"],
  ["office", "Ufficio"], ["other", "Altro"],
];

const ROLES = [
  { code: "primary_frame", label: "Serramento", family: ["window", "french_door", "sliding", "fixed", "lift_slide", "entrance_door"] },
  { code: "shading", label: "Oscurante", family: ["roller_shutter", "shutter", "obscurant", "screen"] },
  { code: "insect_screen", label: "Zanzariera", family: ["screen"] },
  { code: "box", label: "Cassonetto", family: ["roller_box"] },
  { code: "counter_frame", label: "Controtelaio", family: [] },
  { code: "installation", label: "Montaggio", family: [] },
  { code: "dismount", label: "Smontaggio", family: [] },
  { code: "disposal", label: "Smaltimento", family: [] },
  { code: "accessory", label: "Accessorio", family: [] },
];

const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);

export default function QuoteStructurePage() {
  const params = useParams();
  const [quoteId, setQuoteId] = useState(params.quoteId || null);
  const [tree, setTree] = useState(null);
  const [quotes, setQuotes] = useState([]);
  const [productTypes, setProductTypes] = useState([]);
  const [newEnvOpen, setNewEnvOpen] = useState(false);
  const [newEnv, setNewEnv] = useState({ name: "", kind: "other" });
  const [newOpeningEnv, setNewOpeningEnv] = useState(null);
  const [newOpening, setNewOpening] = useState({ width_mm: 1200, height_mm: 1400 });
  const [addProdCtx, setAddProdCtx] = useState(null);   // {opening_id, opening}
  const [prodForm, setProdForm] = useState({ role: "primary_frame", product_type_code: "", description: "", unit_price: 0 });
  const [openingDrawings, setOpeningDrawings] = useState({});

  const load = async (qid = quoteId) => {
    if (!qid) return;
    try {
      const [t, pt] = await Promise.all([
        api.get(`/quote-structure/${qid}/tree`),
        api.get("/product-catalog/types"),
      ]);
      setTree(t.data);
      setProductTypes(pt.data.items || []);
    } catch (e) { toast.error("Errore caricamento struttura"); }
  };

  const loadQuotes = async () => {
    try {
      const { data } = await api.get("/quotes?limit=50");
      setQuotes(data.items || []);
      if (!quoteId && data.items && data.items.length) {
        setQuoteId(data.items[0].id);
      }
    } catch { }
  };

  useEffect(() => { loadQuotes(); }, []);
  useEffect(() => { if (quoteId) load(quoteId); }, [quoteId]);
  // Auto-load drawings when tree changes
  useEffect(() => {
    if (!tree) return;
    tree.environments.forEach(e => e.openings.forEach(op => {
      if (op.products.length > 0 && !openingDrawings[op.opening.id]) loadDrawing(op.opening.id);
    }));
  }, [tree]);

  const createEnv = async () => {
    if (!newEnv.name) return toast.error("Nome ambiente richiesto");
    try {
      await api.post(`/quote-structure/${quoteId}/environments`, newEnv);
      toast.success("Ambiente creato"); setNewEnvOpen(false); setNewEnv({ name: "", kind: "other" });
      load();
    } catch (e) { toast.error("Errore"); }
  };

  const createOpening = async () => {
    if (!newOpeningEnv) return;
    try {
      await api.post("/quote-structure/openings", {
        quote_id: quoteId, environment_id: newOpeningEnv.id,
        dimensions: { width_mm: Number(newOpening.width_mm), height_mm: Number(newOpening.height_mm) },
      });
      toast.success("Vano creato"); setNewOpeningEnv(null);
      load();
    } catch (e) { toast.error("Errore creazione vano"); }
  };

  const addProduct = async () => {
    try {
      await api.post(`/quote-structure/openings/${addProdCtx.opening_id}/products`, {
        opening_id: addProdCtx.opening_id,
        role: prodForm.role,
        product_type_code: prodForm.product_type_code || null,
        description: prodForm.description,
        category: prodForm.role,
        configuration: prodForm.role === "primary_frame" && prodForm.product_type_code
          ? { num_modules: 2, modules: [
              { index: 0, kind: "battente_ribalta", hinges_side: "left", is_fixed: false, width_ratio: 1 },
              { index: 1, kind: "battente_ribalta", hinges_side: "right", is_fixed: false, width_ratio: 1 },
            ]} : {},
        dimension_source: "inherited",
        unit_price: Number(prodForm.unit_price || 0),
      });
      toast.success("Prodotto aggiunto al vano");
      setAddProdCtx(null);
      setProdForm({ role: "primary_frame", product_type_code: "", description: "", unit_price: 0 });
      load();
      loadDrawing(addProdCtx.opening_id);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (typeof d === "object" && d?.blockers) {
        toast.error("Incompatibile: " + d.blockers.join(", "));
      } else toast.error(d || "Errore");
    }
  };

  const loadDrawing = async (op_id) => {
    try {
      const { data } = await api.post(`/quote-structure/openings/${op_id}/composite-drawing`);
      setOpeningDrawings(x => ({ ...x, [op_id]: data.svg }));
    } catch {}
  };

  const duplicateOpening = async (op_id) => {
    try { await api.post(`/quote-structure/openings/${op_id}/duplicate`); toast.success("Vano duplicato"); load(); }
    catch { toast.error("Errore"); }
  };

  const migrateStructure = async () => {
    try {
      const { data } = await api.post(`/quote-structure/${quoteId}/migrate-structure`);
      toast.success(`Migrati ${data.openings_migrated} vani in ${data.environments_created} ambienti`);
      load();
    } catch { toast.error("Errore migrazione"); }
  };

  if (!quoteId) return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Seleziona un preventivo</h1>
      <Select value={quoteId || ""} onValueChange={setQuoteId}>
        <SelectTrigger className="w-96"><SelectValue placeholder="Preventivi"/></SelectTrigger>
        <SelectContent>
          {quotes.map(q => <SelectItem key={q.id} value={q.id}>{q.number || q.id.substring(0,8)} — {q.title || "-"}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );

  if (!tree) return <div className="p-6">Caricamento…</div>;

  const stats = tree.environments.reduce((acc, e) => {
    acc.envs++;
    acc.openings += e.openings.length;
    e.openings.forEach(o => { acc.products += o.products.length; acc.total += o.subtotal; });
    return acc;
  }, { envs: 0, openings: 0, products: 0, total: 0 });

  const currentStep = (
    stats.envs === 0 ? 1 :
    stats.openings === 0 ? 2 :
    stats.products === 0 ? 3 :
    stats.total > 0 ? 4 : 3
  );
  const STEPS = [
    { n: 1, label: "Cliente e immobile" },
    { n: 2, label: "Ambienti" },
    { n: 3, label: "Vani e prodotti" },
    { n: 4, label: "Prezzi e anteprima" },
    { n: 5, label: "Genera PDF" },
  ];

  const openPdf = () => {
    window.open(`/quotes/${quoteId}`, "_blank");
  };

  return (
    <div className="space-y-6" data-testid="quote-structure-page">
      {/* Stepper */}
      <Card className="p-4">
        <div className="flex items-center gap-2 flex-wrap">
          {STEPS.map((s, i) => {
            const done = s.n < currentStep;
            const active = s.n === currentStep;
            return (
              <React.Fragment key={s.n}>
                <div className={`flex items-center gap-2 px-3 py-2 rounded ${
                  active ? "bg-red-600 text-white" : done ? "bg-green-100 text-green-800" : "bg-slate-100 text-slate-500"
                }`} data-testid={`step-${s.n}`}>
                  <div className={`w-6 h-6 rounded-full text-xs flex items-center justify-center font-bold ${
                    active ? "bg-white text-red-600" : done ? "bg-green-600 text-white" : "bg-white"
                  }`}>{done ? "✓" : s.n}</div>
                  <div className="text-sm font-medium">{s.label}</div>
                </div>
                {i < STEPS.length - 1 && <ArrowRight size={14} className="text-slate-400"/>}
              </React.Fragment>
            );
          })}
        </div>
      </Card>

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="overline text-muted-foreground">Preventivatore</div>
          <h1 className="font-display text-3xl font-black tracking-tight">Ambienti → Vani → Prodotti</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Un vano è la nicchia muraria che può contenere più prodotti coordinati (serramento + oscurante + cassonetto + zanzariera). I calcoli avvengono automaticamente in background.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="text-right">
            <div className="overline text-[10px]">Totale preventivo</div>
            <div className="text-2xl font-bold font-mono">{fmt(stats.total)}</div>
            <div className="text-xs text-muted-foreground">{stats.envs} amb · {stats.openings} vani · {stats.products} prod</div>
          </div>
          <Select value={quoteId} onValueChange={setQuoteId}>
            <SelectTrigger className="w-56" data-testid="quote-selector"><SelectValue/></SelectTrigger>
            <SelectContent>
              {quotes.map(q => <SelectItem key={q.id} value={q.id}>{q.number || q.id.substring(0,8)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Dialog open={newEnvOpen} onOpenChange={setNewEnvOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" data-testid="btn-new-env"><House size={16} className="mr-1"/>Nuovo ambiente</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Nuovo ambiente</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>Tipo ambiente</Label>
                  <Select value={newEnv.kind} onValueChange={v => {
                    const label = ENV_KINDS.find(k => k[0] === v)?.[1] || "";
                    setNewEnv({ kind: v, name: newEnv.name || label });
                  }}>
                    <SelectTrigger data-testid="env-kind"><SelectValue/></SelectTrigger>
                    <SelectContent>{ENV_KINDS.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div><Label>Nome</Label><Input value={newEnv.name} onChange={e => setNewEnv({...newEnv, name: e.target.value})} data-testid="env-name"/></div>
                <div><Label>Piano</Label><Input value={newEnv.floor || ""} onChange={e => setNewEnv({...newEnv, floor: e.target.value})}/></div>
              </div>
              <DialogFooter><Button onClick={createEnv} data-testid="btn-save-env">Crea</Button></DialogFooter>
            </DialogContent>
          </Dialog>
          <Button onClick={openPdf} disabled={stats.total === 0} className="bg-red-600 hover:bg-red-700" data-testid="btn-generate-pdf">
            Anteprima / PDF<ArrowRight size={14} className="ml-1"/>
          </Button>
        </div>
      </div>

      {tree.migration_required && (
        <Alert>
          <Warning size={16}/>
          <AlertDescription>
            <div className="flex items-center justify-between">
              <span>Rilevati {tree.orphan_openings.length} vani senza ambiente. Vuoi eseguire la migrazione?</span>
              <Button size="sm" onClick={migrateStructure} data-testid="btn-migrate">Migra struttura</Button>
            </div>
          </AlertDescription>
        </Alert>
      )}

      {tree.environments.length === 0 && (
        <Card className="p-8 text-center border-dashed">
          <House size={40} className="mx-auto mb-3 text-muted-foreground"/>
          <div className="text-lg font-medium">Nessun ambiente definito</div>
          <div className="text-sm text-muted-foreground mt-1 mb-4">
            Crea il primo ambiente (Camera, Cucina, Soggiorno...) per iniziare a inserire i vani.
          </div>
          <Button onClick={() => setNewEnvOpen(true)}>Crea primo ambiente</Button>
        </Card>
      )}

      {tree.environments.map(envNode => (
        <Card key={envNode.environment.id} className="p-5" data-testid={`env-block-${envNode.environment.id}`}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-2">
                <House size={18} className="text-red-600"/>
                <div className="text-xl font-bold">{envNode.environment.name}</div>
                <Badge variant="outline">{envNode.openings.length} vani</Badge>
              </div>
              {envNode.environment.floor && <div className="text-xs text-muted-foreground">Piano: {envNode.environment.floor}</div>}
            </div>
            <div className="flex items-center gap-2">
              <div className="text-right">
                <div className="text-[10px] overline">Totale ambiente</div>
                <div className="text-xl font-bold font-mono">{fmt(envNode.subtotal)}</div>
              </div>
              <Button size="sm" onClick={() => { setNewOpeningEnv(envNode.environment); setNewOpening({ width_mm: 1200, height_mm: 1400 }); }} data-testid={`btn-add-opening-${envNode.environment.id}`}>
                <Plus size={14} className="mr-1"/>Nuovo vano
              </Button>
            </div>
          </div>

          {envNode.openings.length === 0 && (
            <div className="text-sm text-muted-foreground text-center py-6 border rounded border-dashed">
              Nessun vano in questo ambiente. Clicca "Nuovo vano" per iniziare.
            </div>
          )}

          <div className="space-y-4">
            {envNode.openings.map(opNode => {
              const op = opNode.opening;
              return (
                <div key={op.id} className="border rounded-lg p-4 bg-slate-50" data-testid={`opening-block-${op.id}`}>
                  <div className="flex items-start justify-between mb-3 flex-wrap gap-2">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded bg-slate-900 text-white flex items-center justify-center font-bold text-sm">{op.code || "V?"}</div>
                      <div>
                        <div className="font-bold">{op.display_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {op.width_mm}×{op.height_mm} mm — {opNode.products.length} prodotti
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="text-right">
                        <div className="text-[10px] overline">Totale vano</div>
                        <div className="text-lg font-bold font-mono">{fmt(opNode.subtotal)}</div>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => setAddProdCtx({opening_id: op.id, opening: op})} data-testid={`btn-add-product-${op.id}`}>
                        <Plus size={12} className="mr-1"/>Aggiungi prodotto al vano
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => duplicateOpening(op.id)} data-testid={`btn-dup-${op.id}`}>
                        <Copy size={12}/>
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => loadDrawing(op.id)}>
                        Preview
                      </Button>
                    </div>
                  </div>

                  <div className="grid md:grid-cols-3 gap-3">
                    <div className="md:col-span-2 space-y-2">
                      {opNode.products.length === 0 ? (
                        <div className="text-sm text-muted-foreground text-center py-4 border rounded border-dashed bg-white">
                          Vano vuoto — aggiungi serramento, oscurante, cassonetto, zanzariera...
                        </div>
                      ) : opNode.products.map(p => (
                        <div key={p.id} className="flex items-center justify-between bg-white p-3 rounded border" data-testid={`product-${p.id}`}>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <Badge className="text-[10px]">{ROLES.find(r => r.code === p.role)?.label || p.role}</Badge>
                              <div className="font-medium text-sm">{p.description || p.product_key}</div>
                            </div>
                            <div className="text-xs text-muted-foreground mt-1">
                              {p.width_mm}×{p.height_mm} mm — {p.dimension_source === "formula" || p.dimension_source === "inherited" ? "↳ ereditato dal vano" : p.dimension_source}
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono font-bold">{fmt(p.subtotal_line)}</div>
                            {p.quantity !== 1 && <div className="text-xs text-muted-foreground">×{p.quantity}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="border rounded bg-white p-2">
                      {openingDrawings[op.id] ? (
                        <div dangerouslySetInnerHTML={{__html: openingDrawings[op.id]}}/>
                      ) : (
                        <div className="text-xs text-muted-foreground text-center py-8">
                          Clicca "Preview" per il disegno composito
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      ))}

      {/* Dialog: nuovo vano */}
      <Dialog open={!!newOpeningEnv} onOpenChange={(v) => !v && setNewOpeningEnv(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Nuovo vano in {newOpeningEnv?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Alert><Info size={14}/><AlertDescription className="text-xs">
              Il vano è la nicchia muraria. Dopo aver inserito le misure potrai aggiungere serramento, oscurante e accessori tutti coordinati.
            </AlertDescription></Alert>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Larghezza (mm)</Label>
                <Input type="number" value={newOpening.width_mm} onChange={e => setNewOpening({...newOpening, width_mm: e.target.value})} data-testid="new-op-width"/>
              </div>
              <div><Label>Altezza (mm)</Label>
                <Input type="number" value={newOpening.height_mm} onChange={e => setNewOpening({...newOpening, height_mm: e.target.value})} data-testid="new-op-height"/>
              </div>
              <div><Label>Profondità (mm)</Label><Input type="number" value={newOpening.depth_mm || ""} onChange={e => setNewOpening({...newOpening, depth_mm: e.target.value})}/></div>
              <div><Label>Quota davanzale (mm)</Label><Input type="number" value={newOpening.sill_height_mm || ""} onChange={e => setNewOpening({...newOpening, sill_height_mm: e.target.value})}/></div>
            </div>
          </div>
          <DialogFooter><Button onClick={createOpening} data-testid="btn-save-opening">Crea vano</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog: aggiungi prodotto */}
      <Dialog open={!!addProdCtx} onOpenChange={(v) => !v && setAddProdCtx(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Aggiungi prodotto al vano {addProdCtx?.opening?.code}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Ruolo</Label>
              <Select value={prodForm.role} onValueChange={v => setProdForm({...prodForm, role: v, product_type_code: ""})}>
                <SelectTrigger data-testid="prod-role"><SelectValue/></SelectTrigger>
                <SelectContent>{ROLES.map(r => <SelectItem key={r.code} value={r.code}>{r.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><Label>Tipologia (opzionale)</Label>
              <Select value={prodForm.product_type_code} onValueChange={v => setProdForm({...prodForm, product_type_code: v})}>
                <SelectTrigger data-testid="prod-type"><SelectValue placeholder="Seleziona tipologia"/></SelectTrigger>
                <SelectContent>
                  {productTypes.filter(t => {
                    const role = ROLES.find(r => r.code === prodForm.role);
                    if (!role || !role.family.length) return true;
                    return role.family.includes(t.family);
                  }).map(t => <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div><Label>Descrizione</Label>
              <Input value={prodForm.description} onChange={e => setProdForm({...prodForm, description: e.target.value})} data-testid="prod-desc"/>
            </div>
            <div><Label>Prezzo unitario (€)</Label>
              <Input type="number" value={prodForm.unit_price} onChange={e => setProdForm({...prodForm, unit_price: e.target.value})} data-testid="prod-price"/>
            </div>
            <Alert>
              <Info size={14}/>
              <AlertDescription className="text-xs">
                Le misure vengono ereditate automaticamente dal vano ({addProdCtx?.opening?.width_mm}×{addProdCtx?.opening?.height_mm}) con eventuali maggiorazioni per il ruolo (tapparella +60/+40 guide/avvolgimento, cassonetto width+40, zanzariera -10/-5, ecc.).
              </AlertDescription>
            </Alert>
          </div>
          <DialogFooter><Button onClick={addProduct} data-testid="btn-save-product">Aggiungi</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
