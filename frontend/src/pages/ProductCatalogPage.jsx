import React, { useEffect, useState, useCallback } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Table, TableHead, TableRow, TableHeader, TableBody, TableCell } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import { Info, Warning } from "@phosphor-icons/react";

const KINDS = ["battente", "ribalta", "battente_ribalta", "fisso", "scorrevole", "alzante", "traslante", "vasistas"];
const HINGES = ["left", "right", "top", "bottom", "none"];

export default function ProductCatalogPage() {
  const [tab, setTab] = useState("configurator");
  const [types, setTypes] = useState([]);
  const [installRules, setInstallRules] = useState([]);
  const [accessRules, setAccessRules] = useState([]);

  const load = async () => {
    try {
      const [t, ir, ar] = await Promise.all([
        api.get("/product-catalog/types"),
        api.get("/product-catalog/installation-rules"),
        api.get("/product-catalog/access-rules"),
      ]);
      setTypes(t.data.items || []);
      setInstallRules(ir.data.items || []);
      setAccessRules(ar.data.items || []);
    } catch (e) { toast.error("Errore caricamento catalogo"); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6" data-testid="product-catalog-page">
      <div>
        <div className="overline text-muted-foreground">Catalogo prodotti</div>
        <h1 className="font-display text-3xl font-black tracking-tight">Tipologie · Configuratore · Listini</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configura tipologie serramento, composizione ante, disegno tecnico e listini montaggio.
        </p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="configurator" data-testid="tab-configurator">Configuratore visuale</TabsTrigger>
          <TabsTrigger value="types" data-testid="tab-types">Tipologie</TabsTrigger>
          <TabsTrigger value="install" data-testid="tab-install">Listini montaggio</TabsTrigger>
          <TabsTrigger value="access" data-testid="tab-access">Supplementi accesso</TabsTrigger>
        </TabsList>

        <TabsContent value="configurator">
          <VisualConfigurator types={types}/>
        </TabsContent>

        <TabsContent value="types">
          <TypesTab types={types} onReload={load}/>
        </TabsContent>

        <TabsContent value="install">
          <InstallTab rules={installRules} onReload={load}/>
        </TabsContent>

        <TabsContent value="access">
          <AccessTab rules={accessRules} onReload={load}/>
        </TabsContent>
      </Tabs>
    </div>
  );
}


function VisualConfigurator({ types }) {
  const [productType, setProductType] = useState("window_3");
  const [width, setWidth] = useState(2400);
  const [height, setHeight] = useState(1500);
  const [numModules, setNumModules] = useState(3);
  const [modules, setModules] = useState([
    { index: 0, kind: "battente", hinges_side: "left", is_fixed: false, width_ratio: 1 },
    { index: 1, kind: "fixed", is_fixed: true, hinges_side: "none", width_ratio: 1 },
    { index: 2, kind: "battente_ribalta", hinges_side: "right", is_fixed: false, width_ratio: 1 },
  ]);
  const [hasSopra, setHasSopra] = useState(true);
  const [sopraH, setSopraH] = useState(400);
  const [sopraOpen, setSopraOpen] = useState(false);
  const [hasSotto, setHasSotto] = useState(false);
  const [sottoH, setSottoH] = useState(200);
  const [hasFianL, setHasFianL] = useState(false);
  const [fianLW, setFianLW] = useState(300);
  const [hasFianR, setHasFianR] = useState(false);
  const [fianRW, setFianRW] = useState(300);
  const [traversi, setTraversi] = useState(0);
  const [svg, setSvg] = useState("");
  const [hash, setHash] = useState("");

  const updateModules = (n) => {
    const arr = [];
    for (let i = 0; i < n; i++) {
      arr.push(modules[i] || { index: i, kind: "battente", hinges_side: i % 2 ? "right" : "left", is_fixed: false, width_ratio: 1 });
    }
    setModules(arr);
    setNumModules(n);
  };

  const generate = useCallback(async () => {
    try {
      const composition = {
        product_type_code: productType,
        total_width_mm: width, total_height_mm: height,
        num_modules: numModules, modules,
        has_sopraluce: hasSopra, sopraluce_height_mm: sopraH, sopraluce_openable: sopraOpen,
        has_sottoluce: hasSotto, sottoluce_height_mm: sottoH,
        has_fiancoluce_left: hasFianL, fiancoluce_left_width_mm: fianLW,
        has_fiancoluce_right: hasFianR, fiancoluce_right_width_mm: fianRW,
        num_traversi_horizontal: traversi,
      };
      const { data } = await api.post("/product-catalog/drawing", {
        composition, show_dimensions: true, show_opening_symbols: true,
        show_legend: true, include_watermark: true,
      });
      setSvg(data.svg); setHash(data.hash);
    } catch (e) { toast.error("Errore generazione disegno"); }
  }, [productType, width, height, numModules, modules, hasSopra, sopraH, sopraOpen,
      hasSotto, sottoH, hasFianL, fianLW, hasFianR, fianRW, traversi]);

  useEffect(() => { generate(); }, [generate]);

  const setModule = (idx, patch) => {
    const next = [...modules];
    next[idx] = { ...next[idx], ...patch };
    if (patch.kind === "fixed" || patch.kind === "fisso_laterale" || patch.kind === "fisso_centrale") {
      next[idx].is_fixed = true;
    } else {
      next[idx].is_fixed = false;
    }
    setModules(next);
  };

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Card className="p-5 space-y-4">
        <div className="overline">Configurazione</div>
        <div><Label>Tipologia</Label>
          <Select value={productType} onValueChange={setProductType}>
            <SelectTrigger data-testid="conf-type"><SelectValue/></SelectTrigger>
            <SelectContent>{types.map(t => <SelectItem key={t.code} value={t.code}>{t.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label>Larghezza (mm)</Label><Input type="number" value={width} onChange={e => setWidth(Number(e.target.value))} data-testid="conf-width"/></div>
          <div><Label>Altezza (mm)</Label><Input type="number" value={height} onChange={e => setHeight(Number(e.target.value))} data-testid="conf-height"/></div>
          <div><Label>N. moduli/ante</Label>
            <Select value={String(numModules)} onValueChange={v => updateModules(Number(v))}>
              <SelectTrigger data-testid="conf-modules"><SelectValue/></SelectTrigger>
              <SelectContent>
                {[1,2,3,4,5].map(n => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label>Traversi orizzontali</Label>
            <Input type="number" min="0" max="4" value={traversi} onChange={e => setTraversi(Number(e.target.value))}/>
          </div>
        </div>
        <div>
          <div className="overline mb-2">Moduli</div>
          <div className="space-y-2">
            {modules.map((m, i) => (
              <div key={i} className="grid grid-cols-3 gap-2 items-center" data-testid={`conf-module-${i}`}>
                <div className="text-sm">Modulo {i + 1}</div>
                <Select value={m.kind} onValueChange={v => setModule(i, {kind: v})}>
                  <SelectTrigger data-testid={`conf-module-kind-${i}`}><SelectValue/></SelectTrigger>
                  <SelectContent>{KINDS.map(k => <SelectItem key={k} value={k}>{k}</SelectItem>)}</SelectContent>
                </Select>
                <Select value={m.hinges_side} onValueChange={v => setModule(i, {hinges_side: v})}>
                  <SelectTrigger data-testid={`conf-module-hinges-${i}`}><SelectValue/></SelectTrigger>
                  <SelectContent>{HINGES.map(h => <SelectItem key={h} value={h}>{h}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="flex items-center gap-2 text-sm"><Switch checked={hasSopra} onCheckedChange={setHasSopra} data-testid="conf-sopraluce"/>Sopraluce</label>
          </div>
          {hasSopra && <>
            <div><Label>H sopraluce</Label><Input type="number" value={sopraH} onChange={e => setSopraH(Number(e.target.value))}/></div>
            <div className="flex items-center gap-2"><Switch checked={sopraOpen} onCheckedChange={setSopraOpen}/>Apribile</div>
          </>}
          <div className="col-span-2">
            <label className="flex items-center gap-2 text-sm"><Switch checked={hasSotto} onCheckedChange={setHasSotto}/>Sottoluce</label>
          </div>
          {hasSotto && <div><Label>H sottoluce</Label><Input type="number" value={sottoH} onChange={e => setSottoH(Number(e.target.value))}/></div>}
          <div className="col-span-2">
            <label className="flex items-center gap-2 text-sm"><Switch checked={hasFianL} onCheckedChange={setHasFianL}/>Fiancoluce SX</label>
          </div>
          {hasFianL && <div><Label>W fiancoluce SX</Label><Input type="number" value={fianLW} onChange={e => setFianLW(Number(e.target.value))}/></div>}
          <div className="col-span-2">
            <label className="flex items-center gap-2 text-sm"><Switch checked={hasFianR} onCheckedChange={setHasFianR}/>Fiancoluce DX</label>
          </div>
          {hasFianR && <div><Label>W fiancoluce DX</Label><Input type="number" value={fianRW} onChange={e => setFianRW(Number(e.target.value))}/></div>}
        </div>
      </Card>
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="overline">Anteprima tecnica</div>
          <div className="text-[10px] font-mono text-muted-foreground">hash {hash.substring(0, 12)}</div>
        </div>
        <div className="bg-slate-50 border rounded p-4 min-h-[400px]" data-testid="drawing-preview"
             dangerouslySetInnerHTML={{__html: svg}}/>
        <Alert className="mt-3">
          <Info size={14}/>
          <AlertDescription className="text-xs">
            Rappresentazione illustrativa. La configurazione e le misure definitive saranno confermate con il rilievo tecnico e l'abaco.
          </AlertDescription>
        </Alert>
      </Card>
    </div>
  );
}


function TypesTab({ types, onReload }) {
  const [showNew, setShowNew] = useState(false);
  return (
    <Card className="p-5">
      <Table>
        <TableHeader><TableRow>
          <TableHead>Codice</TableHead><TableHead>Etichetta</TableHead>
          <TableHead>Famiglia</TableHead><TableHead>Sopra</TableHead><TableHead>Sotto</TableHead>
          <TableHead>Fianco</TableHead><TableHead>Fix laterale</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {types.map(t => (
            <TableRow key={t.code} data-testid={`type-row-${t.code}`}>
              <TableCell className="font-mono">{t.code}</TableCell>
              <TableCell>{t.label}</TableCell>
              <TableCell><Badge variant="outline">{t.family}</Badge></TableCell>
              <TableCell>{t.supports_sopraluce ? "✅" : "—"}</TableCell>
              <TableCell>{t.supports_sottoluce ? "✅" : "—"}</TableCell>
              <TableCell>{t.supports_fiancoluce ? "✅" : "—"}</TableCell>
              <TableCell>{t.supports_fixed_at_side ? "✅" : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}


function InstallTab({ rules }) {
  const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);
  return (
    <Card className="p-5">
      <Table>
        <TableHeader><TableRow>
          <TableHead>Codice</TableHead><TableHead>Etichetta</TableHead>
          <TableHead>Tipologia</TableHead><TableHead>Unità</TableHead>
          <TableHead className="text-right">Costo interno</TableHead>
          <TableHead className="text-right">Prezzo cliente</TableHead>
          <TableHead className="text-right">Margine</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rules.map(r => (
            <TableRow key={r.id} data-testid={`install-row-${r.code}`}>
              <TableCell className="font-mono text-xs">{r.code}</TableCell>
              <TableCell>{r.label}</TableCell>
              <TableCell><Badge variant="outline">{r.product_type_code || r.product_family}</Badge></TableCell>
              <TableCell>{r.install_unit}</TableCell>
              <TableCell className="text-right font-mono">{fmt(r.install_internal_cost)}</TableCell>
              <TableCell className="text-right font-mono">{fmt(r.install_customer_price)}</TableCell>
              <TableCell className="text-right font-mono font-bold">{fmt(r.install_customer_price - r.install_internal_cost)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}


function AccessTab({ rules }) {
  return (
    <Card className="p-5">
      <Alert className="mb-4">
        <Info size={16}/>
        <AlertDescription>
          Regole applicate al questionario cantiere del preventivo (piano, ascensore, piattaforma, autorizzazioni).
        </AlertDescription>
      </Alert>
      <Table>
        <TableHeader><TableRow>
          <TableHead>Codice</TableHead><TableHead>Etichetta</TableHead>
          <TableHead>Trigger</TableHead><TableHead>Tipo</TableHead>
          <TableHead className="text-right">Importo</TableHead>
          <TableHead className="text-right">Costo interno</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rules.map(r => (
            <TableRow key={r.id} data-testid={`access-rule-${r.code}`}>
              <TableCell className="font-mono text-xs">{r.code}</TableCell>
              <TableCell>{r.label}</TableCell>
              <TableCell><Badge>{r.trigger}</Badge></TableCell>
              <TableCell>{r.surcharge_kind}</TableCell>
              <TableCell className="text-right font-mono">€ {r.amount}</TableCell>
              <TableCell className="text-right font-mono">€ {r.cost_internal}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
