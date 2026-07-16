import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChevronRight, ChevronLeft, Sparkles, Activity, Info } from "lucide-react";
import { toast } from "sonner";

const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);
const fmtPct = (n) => `${(n || 0).toFixed(1)}%`;

/**
 * ConfiguratorDialog — guided wizard + advanced accordion for product configuration.
 *
 * Props:
 *  - open, onOpenChange
 *  - onConfirm({ product_key, product_config, width_mm, height_mm, quantity, unit_price_final, subtotal_line, breakdown, description })
 *  - initialConfig?: partial line data (for edit)
 *  - canSeeCosts: boolean (also comes from user permissions)
 */
export function ConfiguratorDialog({ open, onOpenChange, onConfirm, initialConfig, canSeeCosts = false }) {
  // ------- product catalog -------
  const { data: prodResp } = useQuery({
    queryKey: ["products-catalog"],
    queryFn: async () => (await api.get(`/products?active=true`)).data,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });
  const products = prodResp?.items || [];

  // ------- state -------
  const [productKey, setProductKey] = React.useState(initialConfig?.product_key || "");
  const [width, setWidth] = React.useState(initialConfig?.width_mm || 1200);
  const [height, setHeight] = React.useState(initialConfig?.height_mm || 1400);
  const [quantity, setQuantity] = React.useState(initialConfig?.quantity || 1);
  const [config, setConfig] = React.useState(initialConfig?.product_config || {});
  const [step, setStep] = React.useState(0); // wizard step index
  const [mode, setMode] = React.useState("wizard"); // wizard | advanced

  // reset on product change
  React.useEffect(() => {
    if (!productKey) return;
    const p = products.find((pp) => pp.key === productKey);
    if (p && !initialConfig?.product_key) {
      setConfig((c) => ({ ...(p.default_config || {}), ...c }));
    }
  }, [productKey, products, initialConfig]);

  const product = React.useMemo(() => products.find((p) => p.key === productKey), [products, productKey]);
  const steps = product?.config_schema?.steps || [];

  // ------- live preview -------
  const [preview, setPreview] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [warnings, setWarnings] = React.useState([]);
  const requestSeq = React.useRef(0);
  const abortRef = React.useRef(null);

  const runPreview = React.useCallback(async () => {
    if (!productKey || !width || !height || quantity < 1) return;
    const rid = ++requestSeq.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const body = {
        product_key: productKey,
        product_config: { ...config, category: product?.category },
        width_mm: Number(width) || 0,
        height_mm: Number(height) || 0,
        quantity: Number(quantity) || 1,
        request_id: String(rid),
      };
      const res = await api.post(`/configurator/preview`, body, { signal: controller.signal });
      // Guard against out-of-order responses
      if (Number(res.data.request_id) === rid) {
        setPreview(res.data);
        setWarnings(res.data.warnings || []);
      }
    } catch (e) {
      if (e.name !== "CanceledError" && e.code !== "ERR_CANCELED") {
        toast.error(formatApiError(e.response?.data?.detail) || e.message || "Errore preview");
      }
    } finally {
      setLoading(false);
    }
  }, [productKey, width, height, quantity, config, product]);

  // Debounce
  React.useEffect(() => {
    if (!open || !productKey) return;
    const t = setTimeout(runPreview, 450);
    return () => clearTimeout(t);
  }, [open, productKey, width, height, quantity, config, runPreview]);

  // ------- render -------
  const setCfg = (k, v) => setConfig((c) => ({ ...c, [k]: v }));
  const goNext = () => setStep((s) => Math.min(s + 1, steps.length - 1));
  const goPrev = () => setStep((s) => Math.max(s - 1, 0));

  const submit = () => {
    if (!preview) return toast.error("Attendi il calcolo del prezzo");
    const p = product;
    const desc = buildDescription(p, config, width, height);
    onConfirm?.({
      product_key: productKey,
      product_config: { ...config, category: p?.category },
      category: p?.category || "window",
      width_mm: Number(width),
      height_mm: Number(height),
      quantity: Number(quantity),
      base_price: preview.base_price,
      unit_price_final: preview.unit_price_final,
      subtotal_line: preview.subtotal_line,
      description: desc,
      breakdown: preview.breakdown,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl rounded-sm" data-testid="configurator-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles size={18} /> Configuratore prodotto
          </DialogTitle>
          <DialogDescription>Scegli il prodotto, misure e opzioni. Il prezzo si aggiorna in tempo reale dal listino attivo.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* LEFT: config */}
          <div className="lg:col-span-3 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Label className="text-xs">Prodotto</Label>
                <Select value={productKey} onValueChange={setProductKey}>
                  <SelectTrigger className="rounded-sm h-10" data-testid="cfg-product">
                    <SelectValue placeholder="Seleziona un prodotto…" />
                  </SelectTrigger>
                  <SelectContent>
                    {products.map((p) => (
                      <SelectItem key={p.key} value={p.key}>
                        {p.name}
                        <span className="text-muted-foreground text-xs ml-2">· {p.base_type === "sqm" ? `${fmt(p.base_price)}/m²` : fmt(p.base_price)}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Larghezza (mm)</Label>
                <Input type="number" min={100} value={width} onChange={(e) => setWidth(e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="cfg-width" />
              </div>
              <div>
                <Label className="text-xs">Altezza (mm)</Label>
                <Input type="number" min={100} value={height} onChange={(e) => setHeight(e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="cfg-height" />
              </div>
              <div>
                <Label className="text-xs">Quantità</Label>
                <Input type="number" min={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="cfg-qty" />
              </div>
              <div className="flex items-end">
                <Tabs value={mode} onValueChange={setMode} className="w-full">
                  <TabsList className="rounded-sm w-full">
                    <TabsTrigger className="rounded-sm flex-1" value="wizard">Semplice</TabsTrigger>
                    <TabsTrigger className="rounded-sm flex-1" value="advanced">Avanzata</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </div>

            {productKey && steps.length > 0 && (
              mode === "wizard" ? (
                <Card className="rounded-sm border-border p-4" data-testid="cfg-wizard">
                  <div className="flex items-center gap-2 mb-3 flex-wrap">
                    {steps.map((s, i) => (
                      <Badge key={s.key} variant={i === step ? "default" : "outline"} className={`rounded-sm text-[10px] cursor-pointer ${config[s.key] ? "bg-emerald-500/20 text-emerald-700" : ""}`} onClick={() => setStep(i)}>
                        {i + 1}. {s.label}
                      </Badge>
                    ))}
                  </div>
                  {steps[step] && (
                    <StepRenderer step={steps[step]} value={config[steps[step].key]} onChange={(v) => setCfg(steps[step].key, v)} />
                  )}
                  <div className="mt-4 flex justify-between">
                    <Button variant="outline" size="sm" className="rounded-sm" disabled={step === 0} onClick={goPrev} data-testid="cfg-prev"><ChevronLeft size={14} className="mr-1" /> Indietro</Button>
                    <Button size="sm" className="rounded-sm" disabled={step === steps.length - 1} onClick={goNext} data-testid="cfg-next">Avanti <ChevronRight size={14} className="ml-1" /></Button>
                  </div>
                </Card>
              ) : (
                <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-advanced">
                  {steps.map((s) => (
                    <div key={s.key} className="border-b pb-3 last:border-b-0 last:pb-0">
                      <div className="text-xs font-bold mb-2">{s.label}</div>
                      <StepRenderer step={s} value={config[s.key]} onChange={(v) => setCfg(s.key, v)} />
                    </div>
                  ))}
                </Card>
              )
            )}

            {warnings.length > 0 && (
              <div className="rounded-sm border border-amber-500/40 bg-amber-500/5 p-2 text-xs" data-testid="cfg-warnings">
                {warnings.map((w, i) => <div key={i}>{w}</div>)}
              </div>
            )}
          </div>

          {/* RIGHT: live pricing */}
          <div className="lg:col-span-2">
            <Card className="rounded-sm border-border p-4 sticky top-2" data-testid="cfg-preview">
              <div className="flex items-center justify-between mb-2">
                <div className="overline">Prezzo live</div>
                {loading && <Badge className="rounded-sm bg-amber-500/20 text-amber-800 gap-1"><Activity size={10} className="animate-pulse" /> Calcolo…</Badge>}
              </div>
              {preview ? (
                <div className="space-y-2">
                  <div className="text-3xl font-black font-display" data-testid="cfg-total">{fmt(preview.subtotal_line)}</div>
                  <div className="text-[11px] text-muted-foreground font-mono-plex">
                    {fmt(preview.unit_price_final)} × {preview.quantity} pz · IVA {fmt(preview.vat_amount)}
                  </div>
                  <div className="text-xs font-mono-plex mt-1">
                    Totale IVA inclusa: <span className="font-bold">{fmt(preview.total_line)}</span>
                  </div>

                  {preview.pricelist_name && (
                    <div className="mt-2 text-[10px] text-muted-foreground uppercase font-mono-plex">
                      Listino: {preview.pricelist_name}
                    </div>
                  )}

                  {canSeeCosts && preview.internal_cost != null && (
                    <div className="mt-3 pt-3 border-t border-dashed space-y-1">
                      <div className="overline text-amber-700">Riservato</div>
                      <div className="flex justify-between text-xs"><span className="text-muted-foreground">Costo interno</span><span className="font-mono-plex">{fmt(preview.internal_cost)}</span></div>
                      <div className="flex justify-between text-xs"><span className="text-muted-foreground">Margine</span><span className="font-mono-plex">{fmt(preview.margin_abs)} ({fmtPct(preview.margin_pct)})</span></div>
                    </div>
                  )}

                  {/* Breakdown */}
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-bold flex items-center gap-1"><Info size={12} /> Dettaglio calcolo ({(preview.breakdown || []).length})</summary>
                    <div className="mt-2 space-y-1 text-[11px] max-h-64 overflow-auto" data-testid="cfg-breakdown">
                      {(preview.breakdown || []).map((b, i) => (
                        <div key={i} className="border-l-2 border-border pl-2 py-1">
                          <div className="flex justify-between">
                            <span className="font-bold">{b.label}</span>
                            <span className="font-mono-plex">{fmt(b.amount ?? b.result)}</span>
                          </div>
                          {b.effect_type === "pct" && (
                            <div className="text-muted-foreground font-mono-plex">
                              {fmtPct(b.percentage)} su {fmt(b.base_of_calc)} = {fmt(b.amount)}
                            </div>
                          )}
                          {b.effect_type === "fixed" && b.code !== "BASE" && (
                            <div className="text-muted-foreground font-mono-plex">supplemento fisso</div>
                          )}
                          {b.code === "BASE" && (
                            <div className="text-muted-foreground font-mono-plex">
                              {fmt(b.base_price)} × {b.quantity_factor} = {fmt(b.result)}
                            </div>
                          )}
                          <div className="text-muted-foreground text-[10px]">Risultato progressivo: <span className="font-mono-plex">{fmt(b.result)}</span></div>
                        </div>
                      ))}
                    </div>
                  </details>

                  <div className="mt-2 pt-2 border-t text-[10px] text-muted-foreground font-mono-plex">
                    m² geometrici: {preview.sqm} · m² fatturabili: {preview.billable_sqm} · perimetro: {preview.perimeter_m} m
                  </div>
                </div>
              ) : (
                <div className="text-xs text-muted-foreground">Seleziona prodotto e misure per vedere il prezzo.</div>
              )}
            </Card>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)} data-testid="cfg-cancel">Annulla</Button>
          <Button className="rounded-sm" disabled={!preview || !productKey} onClick={submit} data-testid="cfg-confirm">Aggiungi al preventivo</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function StepRenderer({ step, value, onChange }) {
  if (step.type === "single") {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {(step.options || []).map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`text-left rounded-sm border p-3 text-xs transition-all hover:border-primary ${value === opt.value ? "border-primary bg-primary/5 font-bold" : "border-border"}`}
            data-testid={`cfg-opt-${step.key}-${opt.value}`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    );
  }
  if (step.type === "number") {
    return (
      <Input
        type="number" min={step.min} max={step.max}
        value={value ?? step.default ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rounded-sm h-9 font-mono-plex w-32"
      />
    );
  }
  if (step.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <Checkbox checked={!!value} onCheckedChange={(v) => onChange(!!v)} />
        <span className="text-xs">Sì</span>
      </div>
    );
  }
  if (step.type === "multi") {
    const arr = Array.isArray(value) ? value : [];
    const toggle = (v) => {
      onChange(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
    };
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {(step.options || []).map((opt) => (
          <label key={opt.value} className={`flex items-center gap-2 rounded-sm border p-2 text-xs cursor-pointer ${arr.includes(opt.value) ? "border-primary bg-primary/5" : "border-border"}`}>
            <Checkbox checked={arr.includes(opt.value)} onCheckedChange={() => toggle(opt.value)} />
            {opt.label}
          </label>
        ))}
      </div>
    );
  }
  return <div className="text-xs text-muted-foreground">Passo non supportato</div>;
}

function buildDescription(product, config, w, h) {
  if (!product) return "";
  const parts = [product.name, `${w}×${h} mm`];
  const steps = product?.config_schema?.steps || [];
  for (const s of steps) {
    const v = config[s.key];
    if (!v) continue;
    if (s.type === "single") {
      const opt = (s.options || []).find((o) => o.value === v);
      if (opt) parts.push(opt.label);
    } else if (s.type === "multi" && Array.isArray(v) && v.length) {
      parts.push(v.join(", "));
    } else if (s.type === "boolean" && v) {
      parts.push(s.label);
    } else if (s.type === "number") {
      parts.push(`${s.label}: ${v}`);
    }
  }
  return parts.join(" · ");
}
