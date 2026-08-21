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
import { ChevronLeft, ArrowRight, Activity, Info, Package, Ruler, Boxes, Hammer } from "lucide-react";
import { toast } from "sonner";

const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);

/**
 * MultiCategoryConfiguratorDialog — nuovo preventivatore multi-categoria (V1).
 *
 * Flusso:
 *  STEP 1 -> Scelta CATEGORIA (data-driven da /api/product-categories)
 *  STEP 2 -> Scelta PRODOTTO (data-driven da /api/multi-cat/products?category_code=..)
 *  STEP 3 -> CONFIGURAZIONE condizionale in base al pricing_model del prodotto.
 *
 * Motore prezzo: sempre backend-authoritative via POST /api/multi-cat/products/{id}/configure.
 * FORMULA_TECHNICAL è instradato al motore autorevole /api/pricing/compute.
 */
export function MultiCategoryConfiguratorDialog({ open, onOpenChange, onConfirm, initialConfig, canSeeCosts = false }) {
  const [step, setStep] = React.useState(1);  // 1=category, 2=product, 3=configure
  const [selectedCat, setSelectedCat] = React.useState(null);
  const [selectedProduct, setSelectedProduct] = React.useState(null);
  const [inputs, setInputs] = React.useState({ quantity: 1 });
  const [preview, setPreview] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  // Reset when dialog closes
  React.useEffect(() => {
    if (!open) {
      setStep(1);
      setSelectedCat(null);
      setSelectedProduct(null);
      setInputs({ quantity: 1 });
      setPreview(null);
    }
  }, [open]);

  // Prefill for edit
  React.useEffect(() => {
    if (open && initialConfig?.category_code && initialConfig?.product_id) {
      // Try to skip to step 3 if we have full context (edit mode)
      // We'll set-and-fetch below via category/product queries
      setStep(3);
    }
  }, [open, initialConfig]);

  // Categories
  const { data: catsResp } = useQuery({
    queryKey: ["multi-cat-categories"],
    queryFn: async () => (await api.get(`/product-categories?active=true`)).data,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });
  const categories = catsResp?.items || [];

  // Products for selected category
  const { data: prodsResp } = useQuery({
    queryKey: ["multi-cat-products", selectedCat?.code, canSeeCosts],
    queryFn: async () => (await api.get(`/multi-cat/products?category_code=${selectedCat.code}&include_test_fixtures=${canSeeCosts ? "true" : "false"}`)).data,
    enabled: open && !!selectedCat,
    staleTime: 60 * 1000,
  });
  const products = prodsResp?.items || [];

  const goCategory = (cat) => { setSelectedCat(cat); setStep(2); };
  const goProduct = (p) => {
    setSelectedProduct(p);
    // seed defaults per pricing_model
    const defaults = { quantity: 1 };
    if (p.pricing_model === "AREA" || p.pricing_model === "FORMULA_TECHNICAL") {
      defaults.width_mm = 1200; defaults.height_mm = 1400;
    }
    if (p.pricing_model === "LINEAR_METER") defaults.linear_meters = 1;
    if (p.pricing_model === "GRID") {
      defaults.width_mm = 500; defaults.height_mm = 250;
      defaults.depth_mm = 163; defaults.ceiling_liner = "SI";
    }
    setInputs(defaults);
    setPreview(null);
    setStep(3);
  };
  const goBack = () => {
    if (step === 3) { setStep(2); setPreview(null); }
    else if (step === 2) { setStep(1); setSelectedCat(null); }
  };

  // -------- live pricing preview (debounced) --------
  const runPreview = React.useCallback(async () => {
    if (!selectedProduct) return;
    setLoading(true);
    try {
      let body;
      if (selectedProduct.pricing_model === "FORMULA_TECHNICAL") {
        body = {
          technical_inputs: {
            product_key: selectedProduct.key,
            window_type: inputs.window_type || "WINDOW",
            number_of_sashes: Number(inputs.number_of_sashes || 1),
            width_mm: Number(inputs.width_mm || 0),
            height_mm: Number(inputs.height_mm || 0),
            color_internal: inputs.color_internal || "WHITE_MASS",
            color_external: inputs.color_external || "WHITE_MASS",
            glass_type: inputs.glass_type || "DOUBLE_STANDARD",
            quantity: Number(inputs.quantity || 1),
          },
        };
      } else {
        body = { simple_inputs: {
          width_mm: inputs.width_mm ? Number(inputs.width_mm) : undefined,
          height_mm: inputs.height_mm ? Number(inputs.height_mm) : undefined,
          linear_meters: inputs.linear_meters ? Number(inputs.linear_meters) : undefined,
          quantity: Number(inputs.quantity || 1),
          variant: inputs.variant || undefined,
          options: {
            ...(inputs.color_code ? { color_code: inputs.color_code } : {}),
            ...(inputs.depth_mm ? { depth_mm: Number(inputs.depth_mm) } : {}),
            ...(inputs.ceiling_liner ? { ceiling_liner: inputs.ceiling_liner } : {}),
          },
        } };
      }
      const res = await api.post(`/multi-cat/products/${selectedProduct.id}/configure`, body);
      setPreview(res.data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }, [selectedProduct, inputs]);

  React.useEffect(() => {
    if (step !== 3 || !selectedProduct) return;
    const t = setTimeout(runPreview, 400);
    return () => clearTimeout(t);
  }, [step, selectedProduct, inputs, runPreview]);

  // -------- submit --------
  const submit = () => {
    if (!preview) return toast.error("Attendi il calcolo del prezzo");
    if (preview.pricing_status !== "ok") {
      return toast.error(`Prezzo non calcolabile (${preview.pricing_status}). ${preview.blocking_errors?.join("; ") || ""}`);
    }
    // Read AUTHORITATIVE fields from the compute response:
    //  - Simple engine (all variants): simple_snapshot.unit_price_final / sale_price_total
    //    (alias per AREA-by-color: sale_price_per_item)
    //  - Technical engine (pricing_v3): commercial_snapshot.final_unit_price / unit_sale_price
    // Fail-closed §6/§8: if we cannot extract a positive unit price we NEVER add
    // the line with 0 €. Show explicit error with contract mismatch code.
    const s = preview.simple_snapshot;
    const c = preview.commercial_snapshot;
    const unit = s?.unit_price_final
      ?? s?.sale_price_per_item
      ?? c?.final_unit_price
      ?? c?.unit_sale_price
      ?? null;
    const total = s?.sale_price_total
      ?? (s?.sale_price_per_item != null ? s.sale_price_per_item * Number(inputs.quantity || 1) : null)
      ?? (c?.final_unit_price != null ? c.final_unit_price * Number(inputs.quantity || 1) : null)
      ?? (c?.unit_sale_price != null ? c.unit_sale_price * Number(inputs.quantity || 1) : null)
      ?? null;
    if (unit == null || total == null || unit <= 0 || total <= 0) {
      return toast.error(
        `COMMERCIAL_PRICING_NOT_CONFIGURED — prezzo commerciale non disponibile per ${selectedProduct.pricing_model}. Configura il moltiplicatore o listino.`,
        { duration: 8000 }
      );
    }
    const qty = Number(inputs.quantity || 1);
    const desc = `${selectedProduct.name}${inputs.width_mm && inputs.height_mm ? ` · ${inputs.width_mm}×${inputs.height_mm} mm` : ""}${inputs.linear_meters ? ` · ${inputs.linear_meters} ml` : ""}`;
    onConfirm?.({
      // legacy fields (retro-compat with QuoteLineCreate)
      category: (selectedCat?.code || "").toLowerCase(),
      product_key: selectedProduct.key,
      product_config: { ...inputs, category: selectedCat?.code },
      width_mm: inputs.width_mm ? Number(inputs.width_mm) : null,
      height_mm: inputs.height_mm ? Number(inputs.height_mm) : null,
      quantity: qty,
      base_price: unit,
      unit_price_final: unit,
      subtotal_line: total,
      description: desc,
      // Multi-Category V1 additive
      source: "MULTI_CATEGORY_V1",
      category_id: selectedCat?.id,
      category_code: selectedCat?.code,
      product_id: selectedProduct.id,
      product_code: selectedProduct.key,
      pricing_model: selectedProduct.pricing_model,
      configuration_snapshot: { ...inputs },
      pricing_snapshot: preview,
      technical_snapshot: preview.technical_snapshot || null,
      commercial_snapshot: preview.commercial_snapshot || null,
    });
    onOpenChange(false);
  };

  // ============================================================
  // RENDER
  // ============================================================
  const title = step === 1 ? "Aggiungi al preventivo"
    : step === 2 ? `${selectedCat?.label || ""} · Scegli il prodotto`
    : `${selectedProduct?.name || ""} · Configura`;
  const subtitle = step === 1 ? "Scegli la categoria del prodotto o servizio."
    : step === 2 ? "Seleziona una linea o modello disponibile."
    : `Pricing: ${selectedProduct?.pricing_model || ""}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl rounded-sm" data-testid="multi-cat-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {step > 1 && (
              <Button variant="ghost" size="sm" className="rounded-sm h-7 px-2" onClick={goBack} data-testid="multi-cat-back">
                <ChevronLeft size={14} /> Indietro
              </Button>
            )}
            {title}
          </DialogTitle>
          <DialogDescription>{subtitle}</DialogDescription>
        </DialogHeader>

        {/* STEP INDICATOR */}
        <div className="flex items-center gap-2 pb-2">
          <StepBadge n={1} label="Categoria" active={step === 1} done={step > 1} />
          <ArrowRight size={12} className="text-muted-foreground" />
          <StepBadge n={2} label="Prodotto" active={step === 2} done={step > 2} disabled={step < 2} />
          <ArrowRight size={12} className="text-muted-foreground" />
          <StepBadge n={3} label="Configurazione" active={step === 3} disabled={step < 3} />
        </div>

        {/* STEP 1 — Category */}
        {step === 1 && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3" data-testid="multi-cat-step-1">
            {categories.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => goCategory(c)}
                className="text-left rounded-sm border border-border p-4 hover:border-primary hover:bg-primary/5 transition-all"
                data-testid={`multi-cat-category-${c.code}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <CategoryIcon code={c.code} />
                  <div className="text-sm font-bold">{c.label}</div>
                </div>
                {c.description && <div className="text-xs text-muted-foreground">{c.description}</div>}
              </button>
            ))}
            {!categories.length && (
              <div className="col-span-full text-xs text-muted-foreground">Nessuna categoria attiva. Contatta l'amministratore.</div>
            )}
          </div>
        )}

        {/* STEP 2 — Product */}
        {step === 2 && (
          <div className="space-y-2" data-testid="multi-cat-step-2">
            {products.length ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {products.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => goProduct(p)}
                    className="text-left rounded-sm border border-border p-3 hover:border-primary hover:bg-primary/5 transition-all"
                    data-testid={`multi-cat-product-${p.key}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="text-sm font-bold">{p.name}</div>
                      <Badge variant="outline" className="rounded-sm text-[10px]">{p.pricing_model}</Badge>
                    </div>
                    {p.line && <div className="text-xs text-muted-foreground">Linea: {p.line}</div>}
                    {p.is_test_fixture && <Badge className="rounded-sm bg-amber-500/20 text-amber-800 text-[10px] mt-1">TEST FIXTURE — non produzione</Badge>}
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-sm border border-border p-6 text-center text-xs text-muted-foreground">
                Nessun prodotto attivo nella categoria "{selectedCat?.label}". Chiedi all'amministratore di configurarne uno.
              </div>
            )}
          </div>
        )}

        {/* STEP 3 — Configuration */}
        {step === 3 && selectedProduct && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4" data-testid="multi-cat-step-3">
            <div className="lg:col-span-3 space-y-3">
              <PricingModelRenderer
                model={selectedProduct.pricing_model}
                inputs={inputs}
                setInputs={setInputs}
                product={selectedProduct}
                category={selectedCat}
              />
            </div>
            {/* RIGHT: live price */}
            <div className="lg:col-span-2">
              <Card className="rounded-sm border-border p-4 sticky top-2" data-testid="multi-cat-preview">
                <div className="flex items-center justify-between mb-2">
                  <div className="overline">Prezzo live</div>
                  {loading && <Badge className="rounded-sm bg-amber-500/20 text-amber-800 gap-1"><Activity size={10} className="animate-pulse" /> Calcolo…</Badge>}
                </div>
                {preview ? (
                  <PricingPreviewCard preview={preview} product={selectedProduct} canSeeCosts={canSeeCosts} />
                ) : (
                  <div className="text-xs text-muted-foreground">Inserisci i valori richiesti per vedere il prezzo.</div>
                )}
              </Card>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)} data-testid="multi-cat-cancel">Annulla</Button>
          {step === 3 && (
            <Button
              className="rounded-sm"
              disabled={!preview || preview?.pricing_status !== "ok"}
              onClick={submit}
              data-testid="multi-cat-confirm"
            >
              Aggiungi al preventivo
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function StepBadge({ n, label, active, done, disabled }) {
  const cls = active
    ? "bg-primary text-primary-foreground"
    : done
    ? "bg-emerald-500/20 text-emerald-700"
    : disabled
    ? "bg-muted text-muted-foreground opacity-50"
    : "bg-muted text-muted-foreground";
  return (
    <Badge className={`rounded-sm text-[10px] ${cls}`}>{n}. {label}</Badge>
  );
}

function CategoryIcon({ code }) {
  const map = {
    FINESTRE: Package,
    PORTEFINESTRE: Package,
    SCORREVOLI: Package,
    ZANZARIERE: Boxes,
    TAPPARELLE: Boxes,
    CASSONETTI: Boxes,
    PERSIANE_SCURI: Package,
    PORTE_INTERNE: Package,
    PORTE_BLINDATE: Package,
    ACCESSORI: Ruler,
    SERVIZI: Hammer,
    MONTAGGI_POSA: Hammer,
  };
  const Icon = map[code] || Package;
  return <Icon size={18} className="text-primary" />;
}

function PricingModelRenderer({ model, inputs, setInputs, product, category }) {
  const set = (k, v) => setInputs((s) => ({ ...s, [k]: v }));
  // Inject product category context to ColorPicker via inputs field (no re-render impact)
  React.useEffect(() => {
    if (category?.code && inputs.__product_category !== category.code) {
      setInputs((s) => ({ ...s, __product_category: category.code }));
    }
  }, [category?.code]);

  if (model === "FORMULA_TECHNICAL") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-technical">
        <div className="text-xs font-bold flex items-center gap-1"><Info size={12} /> Configurazione tecnica autorevole</div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField
            label="TIPO SERRAMENTO"
            value={inputs.window_type || "WINDOW"}
            onChange={(v) => set("window_type", v)}
            options={[["WINDOW","FINESTRA"],["DOOR_WINDOW","PORTAFINESTRA"]]}
            testid="cfg-tech-wtype"
          />
          <NumField label="N. ante" value={inputs.number_of_sashes || 1} onChange={(v) => set("number_of_sashes", v)} testid="cfg-tech-sashes" min={1} max={4} />
          <NumField label="Larghezza (mm)" value={inputs.width_mm} onChange={(v) => set("width_mm", v)} testid="cfg-tech-width" />
          <NumField label="Altezza (mm)" value={inputs.height_mm} onChange={(v) => set("height_mm", v)} testid="cfg-tech-height" />
          <SelectField label="Colore interno" value={inputs.color_internal || "WHITE_MASS"} onChange={(v) => set("color_internal", v)} options={[["WHITE_MASS","Bianco"],["ANTHRACITE","Antracite"],["OAK","Rovere"]]} testid="cfg-tech-cint" />
          <SelectField label="Colore esterno" value={inputs.color_external || "WHITE_MASS"} onChange={(v) => set("color_external", v)} options={[["WHITE_MASS","Bianco"],["ANTHRACITE","Antracite"],["OAK","Rovere"]]} testid="cfg-tech-cext" />
          <SelectField label="Vetro" value={inputs.glass_type || "DOUBLE_STANDARD"} onChange={(v) => set("glass_type", v)} options={[["DOUBLE_STANDARD","Doppio standard"],["TRIPLE_ACOUSTIC","Triplo acustico"],["DOUBLE_LOW_E","Basso emissivo"]]} testid="cfg-tech-glass" />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
      </Card>
    );
  }

  if (model === "AREA") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-area">
        <div className="text-xs font-bold">Dimensioni (m² con minimo fatturabile)</div>
        <div className="grid grid-cols-3 gap-3">
          <NumField label="Larghezza (mm)" value={inputs.width_mm} onChange={(v) => set("width_mm", v)} testid="cfg-area-width" />
          <NumField label="Altezza (mm)" value={inputs.height_mm} onChange={(v) => set("height_mm", v)} testid="cfg-area-height" />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
        <ColorPicker productCategory={inputs.__product_category} value={inputs.color_code} onChange={(v) => set("color_code", v)} testid="cfg-area-color" />
      </Card>
    );
  }

  if (model === "GRID") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-grid">
        <div className="text-xs font-bold">Cassonetto — griglia ufficiale (L × H × profondità × cielino × colore)</div>
        <div className="grid grid-cols-2 gap-3">
          <NumField label="Larghezza (mm)" value={inputs.width_mm} onChange={(v) => set("width_mm", v)} testid="cfg-grid-width" min={500} step={100} />
          <NumField label="Altezza (mm)" value={inputs.height_mm} onChange={(v) => set("height_mm", v)} testid="cfg-grid-height" min={250} step={100} />
          <SelectField label="Profondità (mm)" value={String(inputs.depth_mm || 163)} onChange={(v) => set("depth_mm", Number(v))} options={[["163","163"],["326","326"],["489","489"],["652","652"]]} testid="cfg-grid-depth" />
          <SelectField label="Cielino" value={inputs.ceiling_liner || "SI"} onChange={(v) => set("ceiling_liner", v)} options={[["SI","Con cielino"],["NO","Senza cielino"]]} testid="cfg-grid-ceiling" />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
        <ColorPicker productCategory="CASSONETTI" value={inputs.color_code} onChange={(v) => set("color_code", v)} testid="cfg-grid-color" />
      </Card>
    );
  }

  if (model === "LINEAR_METER") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-linear">
        <div className="text-xs font-bold">Metri lineari</div>
        <div className="grid grid-cols-2 gap-3">
          <NumField label="Lunghezza (ml)" value={inputs.linear_meters} onChange={(v) => set("linear_meters", v)} testid="cfg-linear-ml" step={0.01} />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
      </Card>
    );
  }

  if (model === "PER_ITEM") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-per-item">
        <div className="text-xs font-bold">Quantità</div>
        <div className="grid grid-cols-2 gap-3">
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
          <div>
            <Label className="text-xs">Variante (opzionale)</Label>
            <Input className="rounded-sm h-9" value={inputs.variant || ""} onChange={(e) => set("variant", e.target.value)} data-testid="cfg-variant" />
          </div>
        </div>
      </Card>
    );
  }

  if (model === "FIXED_PRICE") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-fixed">
        <div className="text-xs font-bold">Prezzo fisso (forfait)</div>
        <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
      </Card>
    );
  }

  if (model === "FIXED_PLUS_VARIABLE" || model === "TIERED") {
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-mixed">
        <div className="text-xs font-bold">Configurazione mista ({model})</div>
        <div className="grid grid-cols-3 gap-3">
          <NumField label="Larghezza (mm)" value={inputs.width_mm} onChange={(v) => set("width_mm", v)} />
          <NumField label="Altezza (mm)" value={inputs.height_mm} onChange={(v) => set("height_mm", v)} />
          <NumField label="Metri lineari" value={inputs.linear_meters} onChange={(v) => set("linear_meters", v)} step={0.01} />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} min={1} />
        </div>
      </Card>
    );
  }

  if (model === "MANUAL_REVIEW_REQUIRED") {
    return (
      <Card className="rounded-sm border-amber-500 bg-amber-500/5 p-4" data-testid="cfg-manual-review">
        <div className="text-xs font-bold text-amber-800 mb-1">Configurazione da verificare</div>
        <div className="text-xs text-amber-800">Il commerciale non può assegnare un prezzo per questo prodotto. Sarà gestito con workflow autorizzativo.</div>
      </Card>
    );
  }

  return <div className="rounded-sm border border-border p-4 text-xs text-muted-foreground">Pricing model non supportato: {String(model)}</div>;
}

function NumField({ label, value, onChange, testid, min, max, step }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input
        type="number" min={min} max={max} step={step}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        className="rounded-sm h-9 font-mono-plex"
        data-testid={testid}
      />
    </div>
  );
}

function SelectField({ label, value, onChange, options, testid }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="rounded-sm h-9" data-testid={testid}><SelectValue /></SelectTrigger>
        <SelectContent>
          {options.map(([v, l]) => (<SelectItem key={v} value={v}>{l}</SelectItem>))}
        </SelectContent>
      </Select>
    </div>
  );
}

/**
 * ColorPicker — data-driven color selector by product category.
 * - CASSONETTI / FINESTRE / other PVC -> /api/product-colors (13 approved PVC colors)
 * - ZANZARIERE -> /api/zanzariere-colors (separate taxonomy §7)
 * - TAPPARELLE -> INTERNAL_MAP embedded in product.pricing_config.color_map
 */
function ColorPicker({ productCategory, value, onChange, testid, tapparellaMap }) {
  const isZanzariera = productCategory === "ZANZARIERE";
  const isTapparella = productCategory === "TAPPARELLE";
  const { data } = useQuery({
    queryKey: ["colors", isZanzariera ? "zanzariere" : "pvc"],
    queryFn: async () => {
      if (isTapparella) return { items: [
        { code: "RAL_STANDARD", name: "COLORAZIONE RAL", price_category: "RAL",       visual_hex: "#B0B0B0" },
        { code: "WOOD_EFFECT",  name: "EFFETTO LEGNO",   price_category: "LEGNO",     visual_hex: "#8B5A2B" },
        { code: "RAFFAELLO",    name: "COLORI RAFFAELLO",price_category: "RAFFAELLO", visual_hex: "#7A3E2E" },
      ] };
      if (isZanzariera) return (await api.get(`/zanzariere-colors`)).data;
      return (await api.get(`/product-colors?active=true`)).data;
    },
    staleTime: 5 * 60 * 1000,
    enabled: !!productCategory,
  });
  const colors = data?.items || [];
  return (
    <div className="space-y-1" data-testid={testid}>
      <Label className="text-xs">Colore</Label>
      <div className="grid grid-cols-3 md:grid-cols-4 gap-2">
        {colors.map((c) => {
          const active = value === c.code;
          const cat = c.pvc_color_category || c.price_category || c.cassonetti_price_family || "";
          return (
            <button
              key={c.code}
              type="button"
              onClick={() => onChange(c.code)}
              className={`text-left rounded-sm border p-2 transition-all ${active ? "border-primary bg-primary/10" : "border-border hover:border-primary/50"}`}
              data-testid={`${testid}-${c.code}`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="w-6 h-6 rounded-sm border border-border shrink-0" style={{ backgroundColor: c.visual_hex || "#DDD" }} />
                <div className="text-[11px] font-bold truncate">{c.code}</div>
              </div>
              <div className="text-[10px] text-muted-foreground truncate">{c.name}</div>
              {cat && <div className="text-[9px] text-muted-foreground mt-0.5">{cat}</div>}
            </button>
          );
        })}
      </div>
      {!colors.length && productCategory && (
        <div className="text-[11px] text-muted-foreground">Nessun colore configurato per {productCategory}.</div>
      )}
    </div>
  );
}

function PricingPreviewCard({ preview, product, canSeeCosts }) {
  const s = preview.simple_snapshot;
  const c = preview.commercial_snapshot;
  const t = preview.technical_snapshot;
  const qty = Number(preview.inputs_echo?.technical_inputs?.quantity ?? preview.inputs_echo?.simple_inputs?.quantity ?? 1);
  const unit = s?.unit_price_final ?? s?.sale_price_per_item ?? c?.final_unit_price ?? c?.unit_sale_price ?? null;
  const total = s?.sale_price_total ?? (s?.sale_price_per_item != null ? s.sale_price_per_item * qty : null) ?? (c?.final_unit_price != null ? c.final_unit_price * qty : null) ?? (c?.unit_sale_price != null ? c.unit_sale_price * qty : null) ?? null;
  const status = preview.pricing_status;

  if (status !== "ok") {
    return (
      <div className="space-y-2">
        <Badge className="rounded-sm bg-rose-500/20 text-rose-700" data-testid="preview-status">{status.toUpperCase()}</Badge>
        {(preview.blocking_errors || []).map((e, i) => (
          <div key={i} className="text-xs text-rose-700">{e}</div>
        ))}
        {(preview.warnings || []).map((w, i) => (
          <div key={i} className="text-xs text-amber-700">{w}</div>
        ))}
      </div>
    );
  }
  // Fail-closed §8: se il pricing_status è ok ma i field commerciali mancano
  if (unit == null || total == null || unit <= 0 || total <= 0) {
    return (
      <div className="space-y-2" data-testid="preview-missing-commercial">
        <Badge className="rounded-sm bg-amber-500/20 text-amber-800">COMMERCIAL_PRICING_NOT_CONFIGURED</Badge>
        <div className="text-xs text-amber-800">Prezzo commerciale non disponibile per {product.pricing_model}. Configura il moltiplicatore/listino.</div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="text-3xl font-black font-display" data-testid="preview-total">{fmt(total)}</div>
      <div className="text-[11px] text-muted-foreground font-mono-plex">
        {fmt(unit)} unitario · {preview.pricing_model}
      </div>

      {/* Conditional detail per pricing_model */}
      {product.pricing_model === "AREA" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-area-detail">
          <Row k="Area reale" v={`${s.real_area_m2} m²`} />
          {(s.minimum_billable_area_m2) && <Row k="Minimo fatturabile" v={`${s.minimum_billable_area_m2} m²`} />}
          <Row k="Area fatturata (pz)" v={`${s.billable_area_m2 ?? s.billable_area_m2_per_item} m²`} />
          {s.color_price_category && <Row k="Categoria colore" v={s.color_price_category} />}
          <Row k="Prezzo/m²" v={fmt(s.unit_sale_price ?? s.unit_sale_price_per_m2)} />
          {s.purchase_unit_cost_per_m2 != null && canSeeCosts && (
            <Row k="Costo acquisto/m²" v={fmt(s.purchase_unit_cost_per_m2)} />
          )}
          {s.commercial_multiplier && canSeeCosts && <Row k="Moltiplicatore" v={`× ${s.commercial_multiplier}`} />}
          <Row k="Quantità" v={s.quantity} />
        </div>
      )}
      {product.pricing_model === "LINEAR_METER" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-linear-detail">
          <Row k="Metri lineari" v={`${s.linear_meters} ml`} />
          {s.minimum_billable_linear_meters && <Row k="Minimo fatturabile" v={`${s.minimum_billable_linear_meters} ml`} />}
          <Row k="ML fatturati" v={`${s.billable_linear_meters} ml`} />
          <Row k="Prezzo/ml" v={fmt(s.unit_sale_price)} />
        </div>
      )}
      {product.pricing_model === "PER_ITEM" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-item-detail">
          <Row k="Prezzo unitario" v={fmt(s.unit_sale_price)} />
          <Row k="Quantità" v={s.quantity} />
        </div>
      )}
      {product.pricing_model === "FIXED_PRICE" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-fixed-detail">
          <Row k="Prezzo forfait" v={fmt(s.fixed_sale_price)} />
        </div>
      )}
      {product.pricing_model === "GRID" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-grid-detail">
          <Row k="Dimensioni" v={`${s.width_mm}×${s.height_mm} mm`} />
          <Row k="Profondità" v={`${s.depth_mm} mm`} />
          <Row k="Cielino" v={s.ceiling_liner === "SI" ? "Con cielino" : "Senza cielino"} />
          <Row k="Famiglia" v={s.finish_family} />
          {s.color_code && <Row k="Colore" v={s.color_code} />}
          <Row k="Prezzo vendita" v={fmt(s.customer_sale_price_per_item)} />
          {s.internal_production_cost_per_item != null && canSeeCosts && (
            <Row k="Costo produzione" v={fmt(s.internal_production_cost_per_item)} />
          )}
          <Row k="Quantità" v={s.quantity} />
        </div>
      )}
      {product.pricing_model === "FORMULA_TECHNICAL" && t && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-technical-detail">
          <Row k="Motore" v="Technical Authoritative" />
          {c?.multiplier != null && <Row k="Moltiplicatore" v={`× ${c.multiplier}`} />}
          {c?.final_unit_price != null && <Row k="Prezzo unit. commerciale" v={fmt(c.final_unit_price)} />}
          {t.total_internal_cost != null && canSeeCosts && (
            <Row k="Costo produzione" v={fmt(t.total_internal_cost)} />
          )}
          {preview.calculation_hash && <Row k="Hash calcolo" v={preview.calculation_hash.slice(0,12)} />}
        </div>
      )}
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-bold">{v}</span>
    </div>
  );
}
