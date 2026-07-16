import { useEffect, useState } from "react";
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

/**
 * Geometry Builder — Configuratore geometrico libero.
 * Usa esclusivamente il motore BOM + Pricing Hub esistente via /api/geometry/compute.
 */
export default function GeometryBuilderPage() {
  const [templates, setTemplates] = useState([]);
  const [bomTemplates, setBomTemplates] = useState([]);
  const [profileSystems, setProfileSystems] = useState([]);
  const [pricelists, setPricelists] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [outerW, setOuterW] = useState(1200);
  const [outerH, setOuterH] = useState(1400);
  const [bomId, setBomId] = useState("");
  const [psId, setPsId] = useState("");
  const [sellPlId, setSellPlId] = useState("");
  const [tree, setTree] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

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
      } catch (e) {
        toast.error("Errore caricamento configurazioni");
      }
    })();
  }, []);

  const applyTemplate = (tpl) => {
    setSelectedTemplate(tpl);
    setTree({ ...tpl.default_tree });
  };

  const compute = async () => {
    if (!tree || !bomId || !psId) {
      toast.error("Seleziona template, sistema profilo e BOM template");
      return;
    }
    setLoading(true);
    try {
      const geometry = {
        outer_width_mm: outerW,
        outer_height_mm: outerH,
        profile_system_id: psId,
        root: tree,
      };
      const { data } = await api.post("/geometry/compute", {
        geometry, bom_template_id: bomId,
        sell_pricelist_id: sellPlId || undefined,
        include_costs: false,
      });
      setResult(data);
      if (data.errors?.length) {
        toast.warning(`Calcolo con ${data.errors.length} errore/i bloccante/i`);
      } else {
        toast.success(`Calcolato: ${data.materials_price?.toFixed?.(2) || 0} €`);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore calcolo geometria");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="geometry-builder-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Configuratore Geometrico</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Costruisci serramenti fuori standard partendo da un template o combinando splits/moduli.
            Il calcolo passa dal motore BOM + Pricing Hub, mai da valori demo.
          </p>
        </div>
      </div>

      <Tabs defaultValue="templates" className="w-full">
        <TabsList>
          <TabsTrigger value="templates" data-testid="tab-templates">1. Template</TabsTrigger>
          <TabsTrigger value="dimensions" data-testid="tab-dimensions">2. Dimensioni</TabsTrigger>
          <TabsTrigger value="tree" data-testid="tab-tree">3. Struttura</TabsTrigger>
          <TabsTrigger value="result" data-testid="tab-result">4. Risultato</TabsTrigger>
        </TabsList>

        <TabsContent value="templates" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Scegli un template di partenza</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {templates.map((tpl) => (
                  <div key={tpl.code}
                       className={`p-4 border rounded-lg cursor-pointer hover:shadow-md transition ${
                         selectedTemplate?.code === tpl.code ? "border-primary bg-primary/5" : ""
                       }`}
                       onClick={() => applyTemplate(tpl)}
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

        <TabsContent value="dimensions" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Dimensioni esterne e sistema profilo</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <Label>Larghezza esterna (mm)</Label>
                <Input type="number" value={outerW}
                       onChange={(e) => setOuterW(parseInt(e.target.value) || 0)}
                       data-testid="input-outer-width"/>
              </div>
              <div>
                <Label>Altezza esterna (mm)</Label>
                <Input type="number" value={outerH}
                       onChange={(e) => setOuterH(parseInt(e.target.value) || 0)}
                       data-testid="input-outer-height"/>
              </div>
              <div>
                <Label>Sistema profilo</Label>
                <Select value={psId} onValueChange={setPsId}>
                  <SelectTrigger data-testid="select-profile-system"><SelectValue placeholder="Scegli..."/></SelectTrigger>
                  <SelectContent>
                    {profileSystems.map((ps) => (
                      <SelectItem key={ps.id} value={ps.id}>{ps.code} — {ps.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>BOM template</Label>
                <Select value={bomId} onValueChange={setBomId}>
                  <SelectTrigger data-testid="select-bom-template"><SelectValue placeholder="Scegli..."/></SelectTrigger>
                  <SelectContent>
                    {bomTemplates.map((b) => (
                      <SelectItem key={b.id} value={b.id}>{b.code} — {b.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="md:col-span-2">
                <Label>Listino vendita (per valorizzazione)</Label>
                <Select value={sellPlId} onValueChange={setSellPlId}>
                  <SelectTrigger data-testid="select-pricelist"><SelectValue placeholder="Nessuno (solo dimensionale)"/></SelectTrigger>
                  <SelectContent>
                    {pricelists.filter(p => p.kind === "sell").map((p) => (
                      <SelectItem key={p.id} value={p.id}>{p.code} — {p.name} (v{p.version})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="md:col-span-2 flex items-end">
                <Button onClick={compute} disabled={loading} data-testid="btn-compute" className="w-full">
                  {loading ? "Calcolo in corso..." : "Calcola geometria + BOM + prezzo"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tree">
          <Card>
            <CardHeader><CardTitle>Struttura albero</CardTitle></CardHeader>
            <CardContent>
              <pre className="text-xs bg-muted p-4 rounded overflow-auto max-h-[500px]">
                {tree ? JSON.stringify(tree, null, 2) : "Nessun template selezionato"}
              </pre>
              <p className="text-xs text-muted-foreground mt-2">
                v1: modifica visuale dell'albero disponibile via importer BOM template (Blocco C).
                Backend supporta l'intero albero root→split→cell→module con 10 tipi moduli.
              </p>
            </CardContent>
          </Card>
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
                  <CardHeader><CardTitle>Disegno SVG</CardTitle></CardHeader>
                  <CardContent>
                    <div dangerouslySetInnerHTML={{ __html: result.svg || "" }} data-testid="geometry-svg"/>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Prezzo & Sommario</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between"><span>Materiali (prezzo):</span>
                      <span className="font-mono font-bold" data-testid="materials-price">{result.materials_price?.toFixed(2) || 0} €</span></div>
                    {result.materials_cost != null && (
                      <div className="flex justify-between text-muted-foreground">
                        <span>Materiali (costo):</span>
                        <span className="font-mono">{result.materials_cost.toFixed(2)} €</span></div>
                    )}
                    <div className="pt-2 border-t space-y-1">
                      <div className="text-xs text-muted-foreground">Aggregati</div>
                      <div className="text-xs">Ante: <b>{result.geometry_summary?.aggregated?.nr_ante}</b></div>
                      <div className="text-xs">Fissi: <b>{result.geometry_summary?.aggregated?.nr_fissi}</b></div>
                      <div className="text-xs">Vetro totale: <b>{result.geometry_summary?.aggregated?.total_glass_sqm?.toFixed(3)} m²</b></div>
                    </div>
                    <div className="pt-2 border-t">
                      <div className="text-xs text-muted-foreground">Snapshot hash</div>
                      <div className="text-xs font-mono break-all">{result.geometry_snapshot_hash}</div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader><CardTitle>Verifica dimensionale</CardTitle></CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Elemento</TableHead>
                        <TableHead>Input</TableHead>
                        <TableHead>Formula</TableHead>
                        <TableHead>Risultato</TableHead>
                        <TableHead>Note</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(result.geometry_summary?.dimension_verification || []).map((v, i) => (
                        <TableRow key={i} data-testid={`verify-row-${i}`}>
                          <TableCell className="font-mono text-xs">{v.element}</TableCell>
                          <TableCell className="font-mono text-xs">{v.input_mm}</TableCell>
                          <TableCell className="font-mono text-xs">{v.formula}</TableCell>
                          <TableCell className="font-mono text-xs font-bold">{v.result_mm}{v.result_mm_h ? ` × ${v.result_mm_h}` : ""}{v.area_sqm ? ` (${v.area_sqm} m²)` : ""}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{v.notes}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>BOM ({result.components?.length || 0} righe)</CardTitle></CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Tipo</TableHead>
                        <TableHead>Codice</TableHead>
                        <TableHead>Descrizione</TableHead>
                        <TableHead>Qty netta</TableHead>
                        <TableHead>Sfrido</TableHead>
                        <TableHead>Qty fatt.</TableHead>
                        <TableHead>UM</TableHead>
                        <TableHead>€ unit</TableHead>
                        <TableHead>€ tot</TableHead>
                        <TableHead>Listino</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(result.components || []).map((c, i) => (
                        <TableRow key={i} data-testid={`bom-row-${i}`}>
                          <TableCell><Badge variant="outline">{c.component_type}</Badge></TableCell>
                          <TableCell className="font-mono text-xs">{c.code || "-"}</TableCell>
                          <TableCell className="text-xs">{c.description || c.role}</TableCell>
                          <TableCell className="text-xs font-mono">{c.quantity_net}</TableCell>
                          <TableCell className="text-xs font-mono">{c.waste_qty}</TableCell>
                          <TableCell className="text-xs font-mono font-bold">{c.quantity_billable}</TableCell>
                          <TableCell className="text-xs">{c.unit_of_measure}</TableCell>
                          <TableCell className="text-xs font-mono">{c.unit_price?.toFixed(2)}</TableCell>
                          <TableCell className="text-xs font-mono font-bold">{c.line_price?.toFixed(2)}</TableCell>
                          <TableCell className="text-xs">{c.pricelist_origin_sell?.pricelist_name || "-"}</TableCell>
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
