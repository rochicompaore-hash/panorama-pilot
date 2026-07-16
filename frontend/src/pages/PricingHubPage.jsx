import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Table, TableHead, TableRow, TableHeader, TableBody, TableCell } from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import { Info, Warning } from "@phosphor-icons/react";

const METHODS = [
  ["per_sqm", "A · Prezzo €/m²"],
  ["tabular", "B · Matrice tabellare"],
  ["per_piece", "C · Prezzo a pezzo"],
  ["per_linear", "D · Prezzo €/ml"],
  ["bom", "E · Distinta BOM"],
  ["hybrid", "F · Ibrido (profili+vetro+ferramenta)"],
  ["formula", "G · Formula personalizzata"],
  ["manual_temporarily", "H · Calcolo manuale temporaneo"],
];

const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);

export default function PricingHubPage() {
  const [methods, setMethods] = useState([]);
  const [tab, setTab] = useState("categories");
  const [selected, setSelected] = useState(null);
  const [sim, setSim] = useState({ category_code: "", width_mm: 1000, height_mm: 1200, quantity: 1 });
  const [simResult, setSimResult] = useState(null);

  const load = async () => {
    const { data } = await api.get("/pricing-hub/methods");
    setMethods(data.items || []);
  };
  useEffect(() => { load(); }, []);

  const seedDefaults = async () => {
    try {
      const { data } = await api.post("/pricing-hub/seed-defaults");
      toast.success(`Creati ${data.created} metodi default`);
      load();
    } catch { toast.error("Errore seed"); }
  };

  const save = async (m) => {
    try {
      await api.patch(`/pricing-hub/methods/${m.id}`, m);
      toast.success("Salvato");
      load();
    } catch (e) { toast.error("Errore"); }
  };

  const publish = async (mid) => {
    try {
      await api.post(`/pricing-hub/methods/${mid}/publish`);
      toast.success("Pubblicato");
      load();
    } catch (e) {
      const errs = e?.response?.data?.detail?.errors;
      toast.error("Non pubblicabile: " + (errs || []).join(", "));
    }
  };

  const simulate = async () => {
    try {
      const { data } = await api.post("/pricing-hub/simulate", sim);
      setSimResult(data);
      if (data.errors?.length) toast.error(data.errors.join(", "));
      else toast.success(`Prezzo netto ${fmt(data.total_net)}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Errore simulazione"); }
  };

  return (
    <div className="space-y-6" data-testid="pricing-hub-page">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="overline text-muted-foreground">Configurazione tecnica</div>
          <h1 className="font-display text-3xl font-black tracking-tight">Listini e regole di calcolo</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configura il metodo di calcolo per ogni categoria prodotto. Il preventivatore commerciale
            userà queste regole automaticamente in background.
          </p>
        </div>
        <Button variant="outline" onClick={seedDefaults} data-testid="btn-seed-defaults">Crea metodi default</Button>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="categories" data-testid="tab-categories">Categorie & metodi</TabsTrigger>
          <TabsTrigger value="simulator" data-testid="tab-simulator">Simulatore prezzi</TabsTrigger>
          <TabsTrigger value="reference" data-testid="tab-reference">Riferimenti tecnici</TabsTrigger>
        </TabsList>

        <TabsContent value="categories">
          <Card className="p-5">
            {methods.length === 0 && (
              <Alert className="mb-4"><Info size={14}/><AlertDescription>
                Nessuna configurazione. Clicca "Crea metodi default" per generare Finestra/Portafinestra/Tapparella/Zanzariera/Cassonetto/Vetro/Accessori/Posa con metodi consigliati.
              </AlertDescription></Alert>
            )}
            <Table>
              <TableHeader><TableRow>
                <TableHead>Categoria</TableHead><TableHead>Metodo</TableHead>
                <TableHead>Min. m²</TableHead><TableHead>Prezzo unit.</TableHead>
                <TableHead>Colore %</TableHead><TableHead>Stato</TableHead>
                <TableHead>Azioni</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {methods.map(m => (
                  <TableRow key={m.id} data-testid={`method-${m.category_code}`}>
                    <TableCell>
                      <div className="font-medium">{m.label}</div>
                      <div className="text-xs text-muted-foreground font-mono">{m.category_code}</div>
                    </TableCell>
                    <TableCell>
                      <Select value={m.method} onValueChange={v => save({...m, method: v})}>
                        <SelectTrigger className="w-56" data-testid={`method-select-${m.category_code}`}><SelectValue/></SelectTrigger>
                        <SelectContent>
                          {METHODS.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Input type="number" className="w-20" value={m.minimum_billable_sqm || 0}
                        onChange={e => save({...m, minimum_billable_sqm: Number(e.target.value)})}
                        data-testid={`method-min-${m.category_code}`}/>
                    </TableCell>
                    <TableCell>
                      <Input className="w-24" value={m.formula_expr || ""}
                        placeholder={m.unit || "€"}
                        onBlur={e => save({...m, formula_expr: e.target.value})}
                        onChange={e => setMethods(x => x.map(y => y.id === m.id ? {...y, formula_expr: e.target.value} : y))}/>
                    </TableCell>
                    <TableCell>
                      <Input type="number" className="w-16" value={m.color_surcharge_pct || 0}
                        onChange={e => save({...m, color_surcharge_pct: Number(e.target.value)})}/>
                    </TableCell>
                    <TableCell>
                      <Badge className={m.published ? "bg-green-100 text-green-800" : "bg-slate-100"}>
                        {m.published ? "Pubblicato" : "Bozza"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {!m.published && (
                        <Button size="sm" variant="outline" onClick={() => publish(m.id)} data-testid={`btn-publish-${m.category_code}`}>
                          Pubblica
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        <TabsContent value="simulator">
          <div className="grid md:grid-cols-2 gap-4">
            <Card className="p-5 space-y-3">
              <div className="overline">Parametri simulazione</div>
              <div><Label>Categoria</Label>
                <Select value={sim.category_code} onValueChange={v => setSim({...sim, category_code: v})}>
                  <SelectTrigger data-testid="sim-cat"><SelectValue placeholder="Seleziona"/></SelectTrigger>
                  <SelectContent>{methods.map(m => <SelectItem key={m.category_code} value={m.category_code}>{m.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><Label>Larghezza (mm)</Label><Input type="number" value={sim.width_mm} onChange={e => setSim({...sim, width_mm: Number(e.target.value)})} data-testid="sim-w"/></div>
                <div><Label>Altezza (mm)</Label><Input type="number" value={sim.height_mm} onChange={e => setSim({...sim, height_mm: Number(e.target.value)})} data-testid="sim-h"/></div>
                <div><Label>Q.tà</Label><Input type="number" value={sim.quantity} onChange={e => setSim({...sim, quantity: Number(e.target.value)})}/></div>
                <div><Label>Metri lineari</Label><Input type="number" value={sim.linear_m || 0} onChange={e => setSim({...sim, linear_m: Number(e.target.value)})}/></div>
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sim.color_surcharge || false} onChange={e => setSim({...sim, color_surcharge: e.target.checked})}/>Colore speciale</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sim.urgent || false} onChange={e => setSim({...sim, urgent: e.target.checked})}/>Urgenza</label>
              <Button onClick={simulate} className="bg-red-600 hover:bg-red-700" data-testid="btn-simulate">Calcola</Button>
            </Card>
            <Card className="p-5">
              <div className="overline mb-3">Risultato simulazione</div>
              {simResult ? (
                <div className="space-y-2 text-sm">
                  <Row l="Metodo" v={simResult.method}/>
                  <Row l="Superficie reale" v={`${simResult.surface_real_sqm.toFixed(2)} m²`}/>
                  <Row l="Superficie fatturata" v={`${simResult.surface_billable_sqm.toFixed(2)} m²`}/>
                  <Row l="Metri lineari" v={simResult.linear_m_used || "—"}/>
                  <Row l="Prezzo unitario" v={fmt(simResult.unit_price_base)}/>
                  <Row l="Subtotale" v={fmt(simResult.subtotal_before_surcharges)}/>
                  {simResult.color_surcharge_amount > 0 && <Row l="Maggiorazione colore" v={fmt(simResult.color_surcharge_amount)}/>}
                  {simResult.urgent_surcharge_amount > 0 && <Row l="Urgenza" v={fmt(simResult.urgent_surcharge_amount)}/>}
                  <Row l="Totale netto" v={fmt(simResult.total_net)} bold/>
                  <Row l="Totale IVA inclusa" v={fmt(simResult.total_gross)} bold/>
                  {simResult.warnings?.map((w, i) => (
                    <Alert key={i}><Warning size={14}/><AlertDescription className="text-xs">{w}</AlertDescription></Alert>
                  ))}
                  {simResult.errors?.map((e, i) => (
                    <Alert key={i} variant="destructive"><Warning size={14}/><AlertDescription className="text-xs">{e}</AlertDescription></Alert>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground text-sm">Inserisci parametri e clicca Calcola</div>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="reference">
          <Card className="p-5 space-y-3 text-sm">
            <div>Le funzioni tecniche esistenti sono disponibili in:</div>
            <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
              <li><a href="/pricelists" className="text-red-600 underline">Listini prodotto</a> — item pricelists, componenti, barre, colori</li>
              <li><a href="/parametric/admin" className="text-red-600 underline">Engine parametrico</a> — sistemi profilo, formule, matrici prezzo, BOM templates</li>
              <li><a href="/parametric" className="text-red-600 underline">Configuratore live</a> — anteprima parametrica dei serramenti</li>
              <li><a href="/product-catalog" className="text-red-600 underline">Catalogo prodotti</a> — tipologie, regole compatibilità, listini montaggio</li>
            </ul>
            <Alert><Info size={14}/><AlertDescription>
              Nel Preventivatore commerciale queste funzioni operano automaticamente in background.
              I metodi qui configurati determinano come vengono calcolati i prezzi.
            </AlertDescription></Alert>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ l, v, bold }) {
  return (
    <div className={`flex justify-between py-1 border-b ${bold ? "font-bold" : ""}`}>
      <span className="text-muted-foreground">{l}</span>
      <span className="font-mono">{v}</span>
    </div>
  );
}
