import React, { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import { Play, AlertCircle } from "lucide-react";

/**
 * Product Simulator page (Opzione A) — 1-anta window recipe.
 *
 * - Loads seeded products (ProEvolution / ProEvolution Restauro)
 * - Runs POST /api/catalog/products/{id}/simulate
 * - Displays cut-list, ml consumption, blocking errors and prezzo finale
 * - Cost columns are hidden server-side for users without pricing_admin.view_costs
 */
export default function ProductSimulatorPage() {
  const [products, setProducts] = useState([]);
  const [productId, setProductId] = useState("");
  const [L, setL] = useState(900);
  const [H, setH] = useState(1500);
  const [colorCode, setColorCode] = useState("BIANCO");
  const [isPremium, setIsPremium] = useState(false);
  const [hardware, setHardware] = useState("");
  const [otherComponents, setOtherComponents] = useState("");
  const [otherDeclaredZero, setOtherDeclaredZero] = useState(false);
  const [overrideHourly, setOverrideHourly] = useState("");
  const [overrideTime, setOverrideTime] = useState("");
  const [overrideMargin, setOverrideMargin] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [prodCfg, setProdCfg] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [p, cfg] = await Promise.all([
          api.get("/products"),
          api.get("/catalog/production-config").catch(() => ({ data: null })),
        ]);
        const items = (p.data.items || []).filter((x) => (x.components || []).length > 0);
        setProducts(items);
        if (items.length > 0) setProductId(items[0]._id || items[0].id);
        setProdCfg(cfg?.data || null);
      } catch (e) {
        toast.error("Errore caricamento prodotti");
      }
    })();
  }, []);

  const canRun = productId && L > 0 && H > 0 && colorCode;

  const runSimulation = async () => {
    if (!canRun) { toast.error("Compila i campi obbligatori (prodotto, L, H, colore)"); return; }
    setLoading(true);
    setResult(null);
    try {
      const body = {
        width_mm: Number(L), height_mm: Number(H), weld_allowance_mm: 6,
        color_code: colorCode.trim(),
        is_color_premium: isPremium,
        other_components_declared_zero: otherDeclaredZero,
      };
      if (hardware) body.hardware_kit_price = Number(hardware);
      if (otherComponents !== "") body.other_components_cost = Number(otherComponents);
      if (overrideHourly) body.override_hourly_cost = Number(overrideHourly);
      if (overrideTime) body.override_production_time_min = Number(overrideTime);
      if (overrideMargin) body.override_margin_pct = Number(overrideMargin);
      const r = await api.post(`/catalog/products/${productId}/simulate`, body);
      setResult(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Simulazione fallita");
    } finally { setLoading(false); }
  };

  const statusBadge = useMemo(() => {
    if (!result) return null;
    const s = result.pricing_status;
    const color = s === "ok" ? "bg-emerald-600" : (s === "invalid_geometry" ? "bg-red-600" : "bg-amber-600");
    const label = s === "ok" ? "Calcolo completo"
      : (s === "invalid_geometry" ? "Geometria non valida" : "Prezzi/parametri mancanti");
    return <Badge className={`${color} text-white`} data-testid="sim-status">{label}</Badge>;
  }, [result]);

  return (
    <div className="p-6 space-y-6" data-testid="product-simulator-page">
      <header className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Simulatore prodotto</h1>
        <Badge variant="outline">Finestra 1 anta — 5103 + 12130</Badge>
      </header>

      {prodCfg && !prodCfg.hourly_cost && (
        <Alert variant="destructive" data-testid="prod-cfg-missing">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Configurazione produzione incompleta.
            Imposta <strong>costo orario</strong>, <strong>tempo standard</strong> e <strong>margine %</strong>
            in <em>Catalogo → Configurazione produzione</em>, oppure usa gli override qui sotto.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="p-5 space-y-4">
          <h2 className="font-semibold text-lg">Ingresso simulazione</h2>
          <div>
            <Label>Prodotto</Label>
            <Select value={productId} onValueChange={setProductId}>
              <SelectTrigger data-testid="sim-product-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {products.map((p) => (
                  <SelectItem key={p._id || p.id} value={p._id || p.id}>{p.name} ({p.key})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Larghezza L (mm)</Label>
              <Input type="number" value={L} onChange={(e) => setL(e.target.value)} data-testid="sim-input-L" />
            </div>
            <div>
              <Label>Altezza H (mm)</Label>
              <Input type="number" value={H} onChange={(e) => setH(e.target.value)} data-testid="sim-input-H" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Codice colore</Label>
              <Input value={colorCode} onChange={(e) => setColorCode(e.target.value)} data-testid="sim-input-color" placeholder="es. BIANCO / NOCE" />
            </div>
            <div className="flex items-end gap-3">
              <Switch checked={isPremium} onCheckedChange={setIsPremium} data-testid="sim-input-premium" />
              <span className="text-sm">Colore Premium (+6% PVC)</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Prezzo kit ferramenta (€)</Label>
              <Input type="number" value={hardware} onChange={(e) => setHardware(e.target.value)} data-testid="sim-input-hardware" placeholder="obbligatorio se non default sul prodotto" />
            </div>
            <div>
              <Label>Altri componenti (€)</Label>
              <Input type="number" value={otherComponents} onChange={(e) => setOtherComponents(e.target.value)} data-testid="sim-input-other" placeholder="lascia vuoto e spunta 'nessun altro' sotto" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Switch checked={otherDeclaredZero} onCheckedChange={setOtherDeclaredZero} data-testid="sim-input-other-zero" />
            <span className="text-sm">Nessun altro componente (dichiarazione esplicita)</span>
          </div>

          <details className="text-sm border rounded-lg p-3">
            <summary className="cursor-pointer font-medium">Override manodopera / margine (facoltativi)</summary>
            <div className="grid grid-cols-3 gap-3 mt-3">
              <div><Label>Costo orario €/h</Label><Input type="number" value={overrideHourly} onChange={(e) => setOverrideHourly(e.target.value)} /></div>
              <div><Label>Tempo (min)</Label><Input type="number" value={overrideTime} onChange={(e) => setOverrideTime(e.target.value)} /></div>
              <div><Label>Margine %</Label><Input type="number" value={overrideMargin} onChange={(e) => setOverrideMargin(e.target.value)} /></div>
            </div>
          </details>

          <Button onClick={runSimulation} disabled={loading || !canRun} data-testid="sim-run-button" className="w-full">
            <Play className="w-4 h-4 mr-2" /> {loading ? "Calcolo in corso…" : "Simula"}
          </Button>
        </Card>

        <Card className="p-5 space-y-4" data-testid="sim-result-card">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-lg">Risultato</h2>
            {statusBadge}
          </div>

          {result?.blocking_errors?.length > 0 && (
            <Alert variant="destructive" data-testid="sim-blocking-errors">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <div className="font-medium mb-1">Impossibile completare il calcolo:</div>
                <ul className="list-disc pl-5 text-sm">
                  {result.blocking_errors.map((e, i) => (
                    <li key={i}><code>{e.code}</code> — {e.message || e.variable || e.check}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {result?.ml_consumption && (
            <div className="text-sm space-y-1">
              <div className="font-medium">Lista di taglio (ml)</div>
              <table className="w-full text-xs border">
                <tbody>
                  {Object.entries(result.ml_consumption).map(([k, v]) => (
                    <tr key={k} className="border-t">
                      <td className="p-1 pl-2">{k}</td>
                      <td className="p-1 pr-2 text-right font-mono">{Number(v).toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="text-xs text-muted-foreground mt-2">
                Vetro reale: <strong>{result.glass_real_sqm?.toFixed?.(6)}</strong> m² · fatturabile: <strong>{result.glass_billable_sqm?.toFixed?.(6)}</strong> m²
              </div>
            </div>
          )}

          {result?.sale_price != null && (
            <div className="border-t pt-3 space-y-1">
              {!result._costs_hidden && (
                <>
                  <Row label="Costo materiali" value={result.materials_cost} />
                  <Row label="Manodopera" value={result.labor_cost} />
                  <Row label="Costo produzione" value={result.production_cost} strong />
                  <Row label={`Margine ${result.margin_pct ?? "-"}%`} value={result.sale_price_before_discount - (result.production_cost || 0)} />
                </>
              )}
              <Row label="Prezzo prima dello sconto" value={result.sale_price_before_discount} />
              <Row label="Sconto autorizzato" value={result.discount} />
              <Row label="PREZZO FINALE" value={result.sale_price} big />
              {result._costs_hidden && (
                <div className="text-xs text-muted-foreground">
                  I dettagli dei costi interni sono riservati agli utenti autorizzati.
                </div>
              )}
            </div>
          )}

          {result?.snapshot_hash && (
            <div className="text-[11px] text-muted-foreground font-mono truncate" data-testid="sim-snapshot">
              snapshot: {result.snapshot_hash}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, strong, big }) {
  const cls = big ? "text-lg font-bold" : (strong ? "font-semibold" : "");
  return (
    <div className={`flex justify-between ${cls}`}>
      <span>{label}</span>
      <span className="font-mono">{value == null ? "—" : `€ ${Number(value).toFixed(2)}`}</span>
    </div>
  );
}
