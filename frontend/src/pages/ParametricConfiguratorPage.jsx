/**
 * ParametricConfiguratorPage
 * ---------------------------
 * Configuratore live: L, H, quantità, colore, tipologia → chiamata /parametric/preview
 * Mostra:
 *  - SVG dinamico (server-side, sanitized)
 *  - Prezzo unitario, subtotale, VAT, totale
 *  - Costo/margine (solo se permesso)
 *  - Breakdown regola per regola
 *  - Distinta base risolta
 *  - Preview lista taglio con efficienza
 */
import React, { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const PRODUCTS = [
  { key: "window_1_leaf", label: "Finestra 1 anta" },
  { key: "window_2_leaves", label: "Finestra 2 ante" },
  { key: "window_fixed", label: "Fisso" },
  { key: "door_1_leaf", label: "Portafinestra 1 anta" },
];

export default function ParametricConfiguratorPage() {
  const [productKey, setProductKey] = useState("window_1_leaf");
  const [width, setWidth] = useState(1200);
  const [height, setHeight] = useState(1400);
  const [quantity, setQuantity] = useState(1);
  const [nrAnte, setNrAnte] = useState(1);
  const [colorCats, setColorCats] = useState([]);
  const [colorCategoryId, setColorCategoryId] = useState("");
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // deduci nr_ante dal product_key
  useEffect(() => {
    if (productKey === "window_2_leaves") setNrAnte(2);
    else setNrAnte(1);
  }, [productKey]);

  useEffect(() => {
    api.get("/parametric/color-categories").then(r => {
      setColorCats(r.data.items || []);
    }).catch(() => {});
  }, []);

  const compute = async () => {
    setLoading(true); setError(null);
    try {
      const { data } = await api.post("/parametric/preview", {
        product_key: productKey,
        width_mm: Number(width) || 0,
        height_mm: Number(height) || 0,
        quantity: Number(quantity) || 1,
        nr_ante: nrAnte,
        color_category_id: colorCategoryId || null,
        include_svg: true,
        include_cutting_preview: true,
      });
      setPreview(data);
      if (data.errors?.length) {
        toast.error(data.errors[0]);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      toast.error("Errore preview");
    } finally {
      setLoading(false);
    }
  };

  // Ricalcolo automatico su change (debounced)
  useEffect(() => {
    const t = setTimeout(() => { compute(); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productKey, width, height, quantity, nrAnte, colorCategoryId]);

  const canSeeCost = (preview?.unit_cost ?? 0) > 0;

  return (
    <div className="space-y-6" data-testid="parametric-configurator-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="overline text-muted-foreground">Preventivatore parametrico</div>
          <h1 className="font-display text-3xl font-black tracking-tight">Configuratore Live</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Modalità A (tabella) · B (BOM) · C (ibrida) — risoluzione automatica per prodotto/tenant.
            Formule DB-driven, parser AST sicuro. Nesting FFD/BFD 1D.
          </p>
        </div>
        <Badge variant="outline" className="rounded-sm font-mono-plex" data-testid="engine-badge">
          Engine v{preview?.engine_version || "1.0.0"}
        </Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* PARAMETRI */}
        <Card className="lg:col-span-4 rounded-sm">
          <CardHeader><CardTitle className="text-base">Parametri</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Tipologia</Label>
              <Select value={productKey} onValueChange={setProductKey}>
                <SelectTrigger data-testid="config-product-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PRODUCTS.map(p => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Larghezza (mm)</Label>
                <Input type="number" value={width} onChange={e => setWidth(e.target.value)}
                       data-testid="config-width-input" min={300} max={4000} step={10}/>
              </div>
              <div>
                <Label>Altezza (mm)</Label>
                <Input type="number" value={height} onChange={e => setHeight(e.target.value)}
                       data-testid="config-height-input" min={300} max={4000} step={10}/>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Quantità</Label>
                <Input type="number" value={quantity} onChange={e => setQuantity(e.target.value)}
                       data-testid="config-quantity-input" min={1}/>
              </div>
              <div>
                <Label>N. ante</Label>
                <Input type="number" value={nrAnte} onChange={e => setNrAnte(Number(e.target.value))}
                       data-testid="config-ante-input" min={1} max={4}/>
              </div>
            </div>
            <div>
              <Label>Colore / Categoria</Label>
              <Select value={colorCategoryId || "__none__"} onValueChange={v => setColorCategoryId(v === "__none__" ? "" : v)}>
                <SelectTrigger data-testid="config-color-select"><SelectValue placeholder="Default (Cat.1)"/></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Default (Cat.1)</SelectItem>
                  {colorCats.map(c => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name} {c.charges_whole_bar ? "· barra intera" : ""} {c.surcharge_pct ? `+${c.surcharge_pct}%` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={compute} disabled={loading} className="w-full rounded-sm" data-testid="config-recompute-btn">
              {loading ? "Calcolo…" : "Ricalcola preview"}
            </Button>
            {error && <div className="text-sm text-red-600" data-testid="config-error">{String(error)}</div>}
          </CardContent>
        </Card>

        {/* DISEGNO SVG */}
        <Card className="lg:col-span-4 rounded-sm">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Disegno tecnico</CardTitle>
            {preview?.mode_used && (
              <Badge variant="secondary" className="rounded-sm font-mono-plex text-[10px]" data-testid="mode-badge">
                {preview.mode_used} · {preview.mode_source}
              </Badge>
            )}
          </CardHeader>
          <CardContent>
            {preview?.svg ? (
              <div
                data-testid="config-svg-preview"
                dangerouslySetInnerHTML={{ __html: preview.svg }}
                className="w-full flex justify-center"
              />
            ) : (
              <div className="text-sm text-muted-foreground text-center py-10">
                {loading ? "…" : "Nessun disegno disponibile"}
              </div>
            )}
          </CardContent>
        </Card>

        {/* PRICING */}
        <Card className="lg:col-span-4 rounded-sm">
          <CardHeader><CardTitle className="text-base">Prezzo</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Row label="Prezzo unitario" value={fmt(preview?.unit_price)} strong testid="price-unit"/>
            <Row label="Subtotale" value={fmt(preview?.subtotal)} testid="price-subtotal"/>
            <Row label="IVA" value={fmt(preview?.vat_amount)} testid="price-vat"/>
            <div className="border-t pt-2 mt-2">
              <Row label="Totale" value={fmt(preview?.total)} strong big testid="price-total"/>
            </div>
            {canSeeCost && (
              <>
                <div className="mt-4 pt-3 border-t border-dashed">
                  <div className="overline text-muted-foreground mb-2">Costo & Margine</div>
                  <Row label="Costo unitario" value={fmt(preview?.unit_cost)} testid="cost-unit"/>
                  <Row label="Costo totale" value={fmt(preview?.total_cost)} testid="cost-total"/>
                  <Row label="Margine" value={fmt(preview?.margin_abs)} testid="cost-margin-abs"/>
                  <Row label="Margine %" value={`${preview?.margin_pct?.toFixed(2)}%`} strong testid="cost-margin-pct"/>
                </div>
              </>
            )}
            {(preview?.warnings || []).length > 0 && (
              <div className="mt-3 text-xs text-amber-700 bg-amber-50 rounded-sm p-2" data-testid="preview-warnings">
                {preview.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Dettagli */}
      <Tabs defaultValue="breakdown">
        <TabsList className="rounded-sm">
          <TabsTrigger value="breakdown" data-testid="tab-breakdown">Breakdown prezzo</TabsTrigger>
          <TabsTrigger value="bom" data-testid="tab-bom">Distinta base ({preview?.bom_resolved?.length || 0})</TabsTrigger>
          <TabsTrigger value="cutting" data-testid="tab-cutting">Lista taglio</TabsTrigger>
        </TabsList>
        <TabsContent value="breakdown">
          <Card className="rounded-sm">
            <CardContent className="p-4">
              {(preview?.price_breakdown || []).length === 0 ? (
                <div className="text-sm text-muted-foreground">Nessun dettaglio</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground border-b">
                    <tr><th className="text-left py-2">Fase</th><th className="text-left">Descrizione</th><th className="text-right">Importo</th></tr>
                  </thead>
                  <tbody>
                    {preview.price_breakdown.map((b, i) => (
                      <tr key={i} className="border-b" data-testid={`breakdown-row-${i}`}>
                        <td className="py-1.5"><Badge variant="outline" className="rounded-sm text-[10px] font-mono-plex">{b.step}</Badge></td>
                        <td className="py-1.5">{b.label}</td>
                        <td className="py-1.5 text-right font-mono-plex">{fmt(b.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="bom">
          <Card className="rounded-sm">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground border-b bg-muted">
                    <tr>
                      <th className="text-left py-2 px-3">Componente</th>
                      <th className="text-left">Tipo</th>
                      <th className="text-right">Qtà</th>
                      <th className="text-right">Lunghezza mm</th>
                      <th className="text-right">m² / m</th>
                      <th className="text-right">Costo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(preview?.bom_resolved || []).map((c, i) => (
                      <tr key={i} className="border-b" data-testid={`bom-row-${i}`}>
                        <td className="py-1.5 px-3">{c.role || c.component_type}</td>
                        <td>{c.component_type}</td>
                        <td className="text-right font-mono-plex">{c.quantity?.toFixed(2)}</td>
                        <td className="text-right font-mono-plex">{c.length_mm?.toFixed(1) ?? "—"}</td>
                        <td className="text-right font-mono-plex">{c.line_measure?.toFixed(2)}</td>
                        <td className="text-right font-mono-plex">{canSeeCost ? fmt(c.line_cost) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="cutting">
          <Card className="rounded-sm">
            <CardContent className="p-4 space-y-3">
              {!preview?.cutting_preview ? (
                <div className="text-sm text-muted-foreground">Nessuna preview taglio disponibile.</div>
              ) : (
                <>
                  <div className="grid grid-cols-4 gap-3 text-sm">
                    <Stat label="Barre" value={preview.cutting_preview.total_bars} testid="cut-bars"/>
                    <Stat label="Efficienza" value={`${preview.cutting_preview.efficiency_pct}%`} testid="cut-eff"/>
                    <Stat label="Sfrido riutil." value={`${preview.cutting_preview.total_reusable_scrap_mm} mm`} testid="cut-reusable"/>
                    <Stat label="Scarto" value={`${preview.cutting_preview.total_waste_mm} mm`} testid="cut-waste"/>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-xs text-muted-foreground border-b bg-muted">
                        <tr>
                          <th className="text-left py-2 px-3">Barra</th>
                          <th className="text-left">Profilo</th>
                          <th className="text-right">Lunghezza</th>
                          <th className="text-left">Tagli</th>
                          <th className="text-right">Eff.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(preview.cutting_preview.bars || []).map((b, i) => (
                          <tr key={i} className="border-b align-top" data-testid={`bar-row-${i}`}>
                            <td className="py-1.5 px-3 font-mono-plex">#{i+1}</td>
                            <td className="text-xs font-mono-plex">{b.profile_id?.slice(0, 8)}…</td>
                            <td className="text-right font-mono-plex">{b.bar_length_mm} mm</td>
                            <td className="text-xs">
                              {(b.cuts || []).map((c, j) => (
                                <div key={j}>{Math.round(c.length_mm)} mm {c.role ? `· ${c.role}` : ""}</div>
                              ))}
                            </td>
                            <td className="text-right font-mono-plex">{b.efficiency_pct}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Row({ label, value, strong, big, testid }) {
  return (
    <div className="flex items-center justify-between" data-testid={testid}>
      <span className={strong ? "text-sm font-medium" : "text-sm text-muted-foreground"}>{label}</span>
      <span className={`font-mono-plex ${strong ? "font-bold" : ""} ${big ? "text-lg" : "text-sm"}`}>
        {value ?? "—"}
      </span>
    </div>
  );
}

function Stat({ label, value, testid }) {
  return (
    <div className="rounded-sm bg-muted p-3" data-testid={testid}>
      <div className="overline text-muted-foreground">{label}</div>
      <div className="font-mono-plex text-lg font-bold">{value}</div>
    </div>
  );
}

function fmt(n) {
  if (n == null) return "—";
  return `€ ${Number(n).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
