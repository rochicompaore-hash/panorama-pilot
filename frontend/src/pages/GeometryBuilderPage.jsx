import { useEffect, useState, useCallback } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  SplitSquareHorizontal, SplitSquareVertical, Copy, Trash2, Plus, Undo2, Redo2, PanelTop, PanelBottom, PanelLeft,
} from "lucide-react";

const MODULE_TYPES = [
  { code: "sash_hinged", label: "Anta battente", icon: "🪟" },
  { code: "sash_tilt", label: "Anta ribalta (vasistas)", icon: "🔽" },
  { code: "sash_tilt_turn", label: "Anta battente-ribalta", icon: "🔃" },
  { code: "sash_sliding", label: "Anta scorrevole", icon: "↔️" },
  { code: "fixed", label: "Fisso (con telaio anta)", icon: "🔲" },
  { code: "glass_fixed", label: "Vetro fisso (senza anta)", icon: "🪞" },
  { code: "panel", label: "Pannello opaco", icon: "🧱" },
  { code: "top_light", label: "Sopraluce", icon: "⬆️" },
  { code: "bottom_light", label: "Sottoluce", icon: "⬇️" },
  { code: "side_light", label: "Fiancoluce", icon: "↔️" },
];

const newId = () => "n_" + Math.random().toString(36).slice(2, 10);

// ---------------------------------------------------------------------------
// Tree operations (immutable, produce nuovo albero)
// ---------------------------------------------------------------------------
function cloneTree(node) { return JSON.parse(JSON.stringify(node)); }

function findAndUpdate(root, targetId, updater) {
  const walk = (n) => {
    if (n.id === targetId) return updater(cloneTree(n));
    if (n.children) return { ...n, children: n.children.map(walk) };
    return n;
  };
  return walk(root);
}

function findAndRemove(root, targetId) {
  const walk = (n) => {
    if (!n.children) return n;
    const kept = n.children.filter(c => c.id !== targetId).map(walk);
    return { ...n, children: kept };
  };
  return walk(root);
}

function findAndDuplicate(root, targetId) {
  const walk = (n) => {
    if (!n.children) return n;
    let out = [];
    for (const c of n.children) {
      out.push(walk(c));
      if (c.id === targetId) {
        const clone = cloneTree(c);
        const renumber = (x) => { x.id = newId(); if (x.children) x.children.forEach(renumber); };
        renumber(clone);
        out.push(clone);
      }
    }
    return { ...n, children: out };
  };
  return walk(root);
}

function collectIds(node, out = []) {
  out.push(node.id);
  (node.children || []).forEach(c => collectIds(c, out));
  return out;
}

// ---------------------------------------------------------------------------
// Compact tree renderer with visual cells + selection
// ---------------------------------------------------------------------------
function TreeCanvas({ tree, selected, onSelect, outerW, outerH }) {
  const scale = Math.min(500 / outerW, 400 / outerH);
  const canvasW = outerW * scale;
  const canvasH = outerH * scale;

  const renderNode = (node, x, y, w, h) => {
    if (!node) return null;
    const isSelected = selected === node.id;
    const stroke = isSelected ? "#ff6600" : "#333";
    const strokeWidth = isSelected ? 3 : 1;

    if (node.kind === "root") {
      return (
        <g key={node.id}>
          <rect x={x} y={y} width={w} height={h} fill="#e6e6e6"
                 stroke={stroke} strokeWidth={strokeWidth}
                 onClick={(e) => { e.stopPropagation(); onSelect(node.id); }}
                 style={{ cursor: "pointer" }}
                 data-testid={`tree-node-${node.id}`}/>
          {(node.children || []).map(c => renderNode(c, x + 4, y + 4, w - 8, h - 8))}
        </g>
      );
    }
    if (node.kind === "split") {
      const children = node.children || [];
      const sizes = resolveSizes(children, node.direction === "vertical" ? w : h);
      let offset = 0;
      return (
        <g key={node.id}>
          {children.map((c, i) => {
            let cx = x, cy = y, cw = w, ch = h;
            if (node.direction === "vertical") { cx = x + offset; cw = sizes[i]; }
            else { cy = y + offset; ch = sizes[i]; }
            offset += sizes[i];
            return renderNode(c, cx, cy, cw, ch);
          })}
        </g>
      );
    }
    if (node.kind === "cell") {
      const child = (node.children || [])[0];
      return renderNode(child ? { ...child, id: node.id } : { ...node, kind: "module", module_type: "fixed" }, x, y, w, h);
    }
    if (node.kind === "module") {
      const isSash = (node.module_type || "").startsWith("sash");
      const isTopBottom = node.module_type === "top_light" || node.module_type === "bottom_light";
      const isSide = node.module_type === "side_light";
      const fillMap = {
        sash_hinged: "#bfdcff", sash_tilt: "#c8e6a0", sash_tilt_turn: "#c8b0ff",
        sash_sliding: "#ffe0a0", fixed: "#e8e8e8", glass_fixed: "#e0f0ff",
        panel: "#c8a87a", top_light: "#e0f0e0", bottom_light: "#e0f0e0", side_light: "#f5e6ff",
      };
      const fill = fillMap[node.module_type] || "#eee";
      return (
        <g key={node.id}>
          <rect x={x + 1} y={y + 1} width={w - 2} height={h - 2}
                 fill={fill} stroke={stroke} strokeWidth={strokeWidth}
                 onClick={(e) => { e.stopPropagation(); onSelect(node.id); }}
                 style={{ cursor: "pointer" }}
                 data-testid={`tree-node-${node.id}`}/>
          {/* glass inner */}
          {(isSash || node.module_type === "fixed" || node.module_type === "glass_fixed" ||
             isTopBottom || isSide) && (
            <rect x={x + 8} y={y + 8} width={Math.max(w - 16, 1)} height={Math.max(h - 16, 1)}
                   fill="#e0f0ff" fillOpacity="0.6" pointerEvents="none"/>
          )}
          {/* label */}
          {w > 40 && h > 20 && (
            <text x={x + w / 2} y={y + h / 2} textAnchor="middle" dominantBaseline="middle"
                   fontSize="10" fill="#333" pointerEvents="none">
              {MODULE_TYPES.find(m => m.code === node.module_type)?.icon || "?"}
              {node.label ? ` ${node.label.slice(0, 8)}` : ""}
            </text>
          )}
        </g>
      );
    }
    return null;
  };

  return (
    <svg width={canvasW} height={canvasH} style={{ background: "#fafafa", border: "1px solid #ddd" }}
          onClick={() => onSelect(null)}>
      {renderNode(tree, 0, 0, canvasW, canvasH)}
    </svg>
  );
}

function resolveSizes(children, total) {
  let mmTotal = 0, pctTotal = 0, autoCount = 0;
  const sizes = children.map((c) => {
    if (c.size_unit === "mm" && c.size_value) { mmTotal += c.size_value; return c.size_value; }
    if (c.size_unit === "pct" && c.size_value) { pctTotal += c.size_value; return null; }
    autoCount += 1; return null;
  });
  const remaining = Math.max(total - mmTotal, 0);
  let pctAlloc = 0;
  children.forEach((c, i) => {
    if (c.size_unit === "pct" && c.size_value) {
      sizes[i] = remaining * (c.size_value / 100);
      pctAlloc += sizes[i];
    }
  });
  const auto = autoCount > 0 ? Math.max(remaining - pctAlloc, 0) / autoCount : 0;
  return sizes.map(s => s === null ? auto : s);
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function GeometryBuilderPage() {
  const [templates, setTemplates] = useState([]);
  const [bomTemplates, setBomTemplates] = useState([]);
  const [profileSystems, setProfileSystems] = useState([]);
  const [pricelists, setPricelists] = useState([]);
  const [outerW, setOuterW] = useState(1200);
  const [outerH, setOuterH] = useState(1400);
  const [bomId, setBomId] = useState("");
  const [psId, setPsId] = useState("");
  const [sellPlId, setSellPlId] = useState("");
  const [tree, setTree] = useState({
    id: "root", kind: "root",
    children: [{ id: newId(), kind: "module", module_type: "sash_hinged", module_handle_side: "right" }],
  });
  const [selected, setSelected] = useState("root");
  const [history, setHistory] = useState([]);
  const [redoStack, setRedoStack] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("editor");

  useEffect(() => {
    (async () => {
      try {
        const [t, b, p, pl] = await Promise.all([
          api.get("/geometry/templates"),
          api.get("/parametric/bom-templates"),
          api.get("/parametric/profile-systems"),
          api.get("/parametric/item-pricelists"),
        ]);
        setTemplates(t.data.items || []);
        setBomTemplates(b.data.items || []);
        setProfileSystems(p.data.items || []);
        setPricelists(pl.data.items || []);
        if (b.data.items?.[0]) setBomId(b.data.items[0].id);
        if (p.data.items?.[0]) setPsId(p.data.items[0].id);
      } catch (e) { toast.error("Errore caricamento configurazioni"); }
    })();
  }, []);

  const pushHistory = useCallback((prev) => {
    setHistory((h) => [...h.slice(-19), prev]);
    setRedoStack([]);
  }, []);

  const updateTree = (newTree) => { pushHistory(tree); setTree(newTree); };
  const undo = () => { if (history.length === 0) return; const prev = history[history.length - 1]; setRedoStack(r => [...r, tree]); setTree(prev); setHistory(h => h.slice(0, -1)); };
  const redo = () => { if (redoStack.length === 0) return; const next = redoStack[redoStack.length - 1]; setHistory(h => [...h, tree]); setTree(next); setRedoStack(r => r.slice(0, -1)); };

  // Node ops
  const selectedNode = () => {
    const walk = (n) => { if (n.id === selected) return n; for (const c of n.children || []) { const r = walk(c); if (r) return r; } };
    return walk(tree);
  };

  const splitNode = (direction) => {
    if (!selected) return toast.error("Seleziona un modulo o una cella");
    const upd = findAndUpdate(tree, selected, (n) => {
      // trasforma il nodo in split con 2 figli identici
      const originalModule = n.kind === "module" ? n : (n.children?.[0] || { kind: "module", module_type: "fixed" });
      const c1 = { ...cloneTree(originalModule), id: newId(), size_unit: "auto" };
      const c2 = { ...cloneTree(originalModule), id: newId(), size_unit: "auto" };
      return { id: n.id, kind: "split", direction, children: [c1, c2] };
    });
    updateTree(upd);
    toast.success(`Divisione ${direction === "vertical" ? "verticale" : "orizzontale"} inserita`);
  };

  const setModuleType = (nodeId, module_type) => {
    updateTree(findAndUpdate(tree, nodeId, (n) => ({
      ...n, kind: "module", module_type,
      children: undefined,
    })));
  };

  const setNodeField = (nodeId, field, value) => {
    updateTree(findAndUpdate(tree, nodeId, (n) => ({ ...n, [field]: value })));
  };

  const duplicateNode = () => {
    if (!selected || selected === "root") return toast.error("Seleziona un elemento (no root)");
    updateTree(findAndDuplicate(tree, selected));
    toast.success("Duplicato");
  };

  const deleteNode = () => {
    if (!selected || selected === "root") return toast.error("Seleziona un elemento (no root)");
    updateTree(findAndRemove(tree, selected));
    setSelected("root");
    toast.success("Eliminato");
  };

  const compute = async () => {
    if (!bomId || !psId) { toast.error("Seleziona sistema profilo e BOM template"); return; }
    setLoading(true);
    try {
      const geometry = { outer_width_mm: outerW, outer_height_mm: outerH, profile_system_id: psId, root: tree };
      const { data } = await api.post("/geometry/compute", {
        geometry, bom_template_id: bomId,
        sell_pricelist_id: sellPlId || undefined, include_costs: false,
      });
      setResult(data);
      setActiveTab("result");
      if (data.errors?.length) toast.warning(`${data.errors.length} errore/i bloccante/i`);
      else toast.success(`Calcolato: ${(data.materials_price || 0).toFixed(2)} €`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore calcolo");
    } finally { setLoading(false); }
  };

  const applyTemplate = (tpl) => {
    // reassign ids
    const clone = cloneTree(tpl.default_tree);
    const renumber = (x) => { x.id = x.id || newId(); (x.children || []).forEach(renumber); };
    renumber(clone);
    if (!clone.id) clone.id = "root";
    updateTree(clone);
    setSelected("root");
    toast.success(`Template applicato: ${tpl.name}`);
  };

  const node = selectedNode();

  return (
    <div className="p-6 space-y-6" data-testid="geometry-builder-page">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Configuratore Geometrico</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Editor visuale: parti da un template o costruisci celle libere con divisioni H/V. Il calcolo passa dal motore BOM + Pricing Hub esistente.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="editor" data-testid="tab-editor">Editor</TabsTrigger>
          <TabsTrigger value="templates" data-testid="tab-templates">Template</TabsTrigger>
          <TabsTrigger value="result" data-testid="tab-result">Risultato</TabsTrigger>
        </TabsList>

        <TabsContent value="templates" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Template predefiniti</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {templates.map((tpl) => (
                  <div key={tpl.code} className="p-4 border rounded-lg cursor-pointer hover:shadow-md transition"
                        onClick={() => { applyTemplate(tpl); setActiveTab("editor"); }}
                        data-testid={`template-${tpl.code}`}>
                    <div className="font-semibold">{tpl.name}</div>
                    <div className="text-xs text-muted-foreground mt-1">{tpl.description}</div>
                    <Badge variant="secondary" className="mt-2">{tpl.category}</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="editor" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Parametri esterni</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div><Label>L. esterna (mm)</Label>
                <Input type="number" value={outerW} onChange={(e) => setOuterW(parseInt(e.target.value) || 0)} data-testid="input-outer-width"/></div>
              <div><Label>H. esterna (mm)</Label>
                <Input type="number" value={outerH} onChange={(e) => setOuterH(parseInt(e.target.value) || 0)} data-testid="input-outer-height"/></div>
              <div><Label>Sistema profilo</Label>
                <Select value={psId} onValueChange={setPsId}>
                  <SelectTrigger data-testid="select-profile-system"><SelectValue/></SelectTrigger>
                  <SelectContent>{profileSystems.map(ps => <SelectItem key={ps.id} value={ps.id}>{ps.code} — {ps.name}</SelectItem>)}</SelectContent>
                </Select></div>
              <div><Label>BOM template</Label>
                <Select value={bomId} onValueChange={setBomId}>
                  <SelectTrigger data-testid="select-bom-template"><SelectValue/></SelectTrigger>
                  <SelectContent>{bomTemplates.map(b => <SelectItem key={b.id} value={b.id}>{b.code}</SelectItem>)}</SelectContent>
                </Select></div>
              <div className="md:col-span-3"><Label>Listino vendita</Label>
                <Select value={sellPlId} onValueChange={setSellPlId}>
                  <SelectTrigger data-testid="select-pricelist"><SelectValue placeholder="Nessuno (solo dimensionale)"/></SelectTrigger>
                  <SelectContent>{pricelists.filter(p => p.kind === "sell").map(p => <SelectItem key={p.id} value={p.id}>{p.code} v{p.version}</SelectItem>)}</SelectContent>
                </Select></div>
              <div className="flex items-end">
                <Button onClick={compute} disabled={loading} className="w-full" data-testid="btn-compute">
                  {loading ? "Calcolo…" : "Calcola"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Anteprima geometria</CardTitle>
                  <div className="flex gap-1">
                    <Button size="sm" variant="outline" onClick={undo} disabled={history.length === 0} data-testid="btn-undo"><Undo2 className="w-4 h-4"/></Button>
                    <Button size="sm" variant="outline" onClick={redo} disabled={redoStack.length === 0} data-testid="btn-redo"><Redo2 className="w-4 h-4"/></Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex justify-center">
                <TreeCanvas tree={tree} selected={selected} onSelect={setSelected}
                              outerW={outerW} outerH={outerH}/>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Strumenti</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="text-xs text-muted-foreground">
                  Selezionato: <b className="font-mono">{node?.id?.slice(0, 8) || "-"}</b>{" "}
                  ({node?.kind || "-"}{node?.module_type ? ` / ${node.module_type}` : ""})
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Button size="sm" variant="outline" onClick={() => splitNode("vertical")}
                           disabled={!selected} data-testid="btn-split-v">
                    <SplitSquareVertical className="w-4 h-4 mr-1"/>Div. V
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => splitNode("horizontal")}
                           disabled={!selected} data-testid="btn-split-h">
                    <SplitSquareHorizontal className="w-4 h-4 mr-1"/>Div. H
                  </Button>
                  <Button size="sm" variant="outline" onClick={duplicateNode}
                           disabled={!selected || selected === "root"} data-testid="btn-duplicate">
                    <Copy className="w-4 h-4 mr-1"/>Duplica
                  </Button>
                  <Button size="sm" variant="destructive" onClick={deleteNode}
                           disabled={!selected || selected === "root"} data-testid="btn-delete">
                    <Trash2 className="w-4 h-4 mr-1"/>Elimina
                  </Button>
                </div>

                {node?.kind === "module" && (
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-xs">Tipo modulo</Label>
                    <Select value={node.module_type || "fixed"}
                             onValueChange={(v) => setModuleType(selected, v)}>
                      <SelectTrigger data-testid="select-module-type"><SelectValue/></SelectTrigger>
                      <SelectContent>
                        {MODULE_TYPES.map(m => <SelectItem key={m.code} value={m.code}>{m.icon} {m.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                    {(node.module_type || "").startsWith("sash") && (
                      <>
                        <Label className="text-xs">Lato cerniere</Label>
                        <Select value={node.module_handle_side || "right"}
                                 onValueChange={(v) => setNodeField(selected, "module_handle_side", v)}>
                          <SelectTrigger data-testid="select-handle-side"><SelectValue/></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="left">Sinistra</SelectItem>
                            <SelectItem value="right">Destra</SelectItem>
                          </SelectContent>
                        </Select>
                      </>
                    )}
                    <Label className="text-xs">Etichetta</Label>
                    <Input value={node.label || ""} placeholder="Es. anta principale"
                            onChange={(e) => setNodeField(selected, "label", e.target.value)}/>

                    <Label className="text-xs">Dimensione</Label>
                    <div className="flex gap-2">
                      <Select value={node.size_unit || "auto"}
                               onValueChange={(v) => setNodeField(selected, "size_unit", v)}>
                        <SelectTrigger data-testid="select-size-unit"><SelectValue/></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Auto</SelectItem>
                          <SelectItem value="mm">mm</SelectItem>
                          <SelectItem value="pct">%</SelectItem>
                        </SelectContent>
                      </Select>
                      {node.size_unit && node.size_unit !== "auto" && (
                        <Input type="number" value={node.size_value || ""}
                                onChange={(e) => setNodeField(selected, "size_value", parseFloat(e.target.value) || 0)}
                                data-testid="input-size-value"/>
                      )}
                    </div>
                  </div>
                )}

                <div className="pt-2 border-t text-xs text-muted-foreground">
                  <b>Suggerimenti:</b> clicca su un modulo per selezionarlo, poi usa i pulsanti per dividerlo o cambiarne il tipo. Undo/redo disponibili.
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="result">
          {result ? (
            <div className="space-y-4">
              {result.errors?.length > 0 && (
                <Card className="border-destructive">
                  <CardHeader><CardTitle className="text-destructive">Errori bloccanti</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="list-disc pl-5 text-sm space-y-1">
                      {result.errors.map((e, i) => <li key={i} className="text-destructive" data-testid={`error-${i}`}>{e}</li>)}
                    </ul>
                  </CardContent>
                </Card>
              )}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card>
                  <CardHeader><CardTitle>Disegno SVG dal motore</CardTitle></CardHeader>
                  <CardContent><div dangerouslySetInnerHTML={{ __html: result.svg || "" }} data-testid="geometry-svg"/></CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Prezzo & Aggregati</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between"><span>Materiali (prezzo):</span>
                      <span className="font-mono font-bold" data-testid="materials-price">{(result.materials_price || 0).toFixed(2)} €</span></div>
                    <div className="pt-2 border-t text-xs">
                      Ante: <b>{result.geometry_summary?.aggregated?.nr_ante}</b> ·
                      Fissi: <b>{result.geometry_summary?.aggregated?.nr_fissi}</b> ·
                      Vetro: <b>{(result.geometry_summary?.aggregated?.total_glass_sqm || 0).toFixed(3)} m²</b>
                    </div>
                    <div className="pt-2 border-t text-xs">
                      <div className="text-muted-foreground">Snapshot hash</div>
                      <div className="font-mono break-all">{result.geometry_snapshot_hash}</div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader><CardTitle>Verifica dimensionale</CardTitle></CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader><TableRow>
                      <TableHead>Elemento</TableHead><TableHead>Input</TableHead>
                      <TableHead>Formula</TableHead><TableHead>Risultato</TableHead>
                    </TableRow></TableHeader>
                    <TableBody>
                      {(result.geometry_summary?.dimension_verification || []).map((v, i) => (
                        <TableRow key={i} data-testid={`verify-row-${i}`}>
                          <TableCell className="font-mono text-xs">{v.element}</TableCell>
                          <TableCell className="font-mono text-xs">{v.input_mm}</TableCell>
                          <TableCell className="font-mono text-xs">{v.formula}</TableCell>
                          <TableCell className="font-mono text-xs font-bold">{v.result_mm}{v.result_mm_h ? ` × ${v.result_mm_h}` : ""}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>BOM ({result.components?.length || 0})</CardTitle></CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader><TableRow>
                      <TableHead>Tipo</TableHead><TableHead>Codice</TableHead>
                      <TableHead>Descr.</TableHead><TableHead>Qty net</TableHead>
                      <TableHead>Sfrido</TableHead><TableHead>Qty fatt.</TableHead>
                      <TableHead>UM</TableHead><TableHead>€ unit</TableHead>
                      <TableHead>€ tot</TableHead>
                    </TableRow></TableHeader>
                    <TableBody>
                      {(result.components || []).map((c, i) => (
                        <TableRow key={i} data-testid={`bom-row-${i}`}>
                          <TableCell><Badge variant="outline">{c.component_type}</Badge></TableCell>
                          <TableCell className="font-mono text-xs">{c.code || "-"}</TableCell>
                          <TableCell className="text-xs">{c.description}</TableCell>
                          <TableCell className="text-xs font-mono">{c.quantity_net}</TableCell>
                          <TableCell className="text-xs font-mono">{c.waste_qty}</TableCell>
                          <TableCell className="text-xs font-mono font-bold">{c.quantity_billable}</TableCell>
                          <TableCell className="text-xs">{c.unit_of_measure}</TableCell>
                          <TableCell className="text-xs font-mono">{c.unit_price?.toFixed(2) || "-"}</TableCell>
                          <TableCell className="text-xs font-mono font-bold">{c.line_price?.toFixed(2) || "-"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card><CardContent className="py-12 text-center text-muted-foreground">Lancia un calcolo per vedere il risultato</CardContent></Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
