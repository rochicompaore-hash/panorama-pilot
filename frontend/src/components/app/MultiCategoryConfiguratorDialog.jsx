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
import { ProductVisualSVG } from "@/components/app/ProductVisualSVG";

const WHITE_MASS_CODE = "003";
const WHITE_MASS_NAME = "Bianco massa";

/** COLOR INPUT V2 (msg 631): il commerciale inserisce CODICE + NOME; la classificazione (003 / standard / special) è del backend. */
function ColorCodeNameInput({ label, code, name, onChange, testid }) {
  return (
    <div className="grid grid-cols-3 gap-2" data-testid={testid}>
      <div className="space-y-1">
        <Label className="text-xs">{label} · Codice</Label>
        <Input value={code || ""} onChange={(e) => onChange(e.target.value.toUpperCase(), name)} placeholder="es. 110" className="h-9 font-mono-plex" data-testid={`${testid}-code`} data-invalid={!code ? "true" : undefined} />
      </div>
      <div className="col-span-2 space-y-1">
        <Label className="text-xs">Nome colore</Label>
        <Input value={name || ""} onChange={(e) => onChange(code, e.target.value)} placeholder="es. Rovere / Grigio antracite" className="h-9" data-testid={`${testid}-name`} data-invalid={!name ? "true" : undefined} />
      </div>
      {(!code || !name) && <div className="col-span-3 text-[11px] text-amber-700" data-testid={`${testid}-required`}>{!code ? "COLOR_CODE_REQUIRED: codice colore obbligatorio." : "COLOR_NAME_REQUIRED: nome colore obbligatorio."}</div>}
    </div>
  );
}
const COLOR_MODES = [
  ["WHITE_MASS", "Bianco massa (003)"],
  ["WHITE_IN_FOIL_OUT", "Bianco interno + pellicolato esterno"],
  ["FOIL_BOTH_SAME", "Pellicolato due lati stesso colore"],
  ["BICOLOR", "Bicolore (interno ≠ esterno)"],
];
// Deriva la modalità colore da una configurazione salvata (reload/modify di righe esistenti).
function deriveColorMode(cfg) {
  if (cfg.color_mode) return cfg.color_mode;
  const ci = cfg.color_internal, ce = cfg.color_external;
  if (!ci || !ce) return "WHITE_MASS";
  if (ci === ce) return ["WHITE_MASS", WHITE_MASS_CODE].includes(ci) ? "WHITE_MASS" : "FOIL_BOTH_SAME";
  return ["WHITE_MASS", WHITE_MASS_CODE].includes(ci) ? "WHITE_IN_FOIL_OUT" : "BICOLOR";
}

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

  // Prefill for edit (msg 402 Lotto 1): stesso configuratore, valori già popolati.
  const isEdit = !!(initialConfig?.id && initialConfig?.product_id);
  React.useEffect(() => {
    if (!open || !isEdit) return;
    (async () => {
      try {
        const prod = (await api.get(`/multi-cat/products/${initialConfig.product_id}`)).data;
        setSelectedCat({ id: prod.category_id, code: prod.category_code || initialConfig.category_code });
        setSelectedProduct(prod);
        const cfg = initialConfig.configuration_snapshot || initialConfig.product_config || {};
        const legacy = (c) => (c === "WHITE_MASS" ? WHITE_MASS_CODE : c);
        const colorFix = prod.pricing_model === "FORMULA_TECHNICAL"
          ? { color_mode: deriveColorMode(cfg), color_internal: legacy(cfg.color_internal) || WHITE_MASS_CODE, color_external: legacy(cfg.color_external) || WHITE_MASS_CODE,
              color_internal_name: cfg.color_internal_name || (legacy(cfg.color_internal) === WHITE_MASS_CODE || !cfg.color_internal ? WHITE_MASS_NAME : legacy(cfg.color_internal)),
              color_external_name: cfg.color_external_name || (legacy(cfg.color_external) === WHITE_MASS_CODE || !cfg.color_external ? WHITE_MASS_NAME : legacy(cfg.color_external)) }
          : {};
        setInputs({ ...cfg, ...colorFix, quantity: initialConfig.quantity || cfg.quantity || 1, width_mm: cfg.width_mm ?? initialConfig.width_mm, height_mm: cfg.height_mm ?? initialConfig.height_mm });
        setPreview(null);
        setStep(3);
      } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || e.message); }
    })();
  }, [open, isEdit, initialConfig]);

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
    if (p.pricing_model === "FORMULA_TECHNICAL") {
      defaults.color_mode = "WHITE_MASS"; defaults.color_internal = WHITE_MASS_CODE; defaults.color_external = WHITE_MASS_CODE;
      defaults.color_internal_name = WHITE_MASS_NAME; defaults.color_external_name = WHITE_MASS_NAME;
      defaults.opening_configuration = "ANTA_RIBALTA"; defaults.hinge_side = "DX";
    }
    if (p.pricing_model === "AREA_PURCHASE_MULTIPLIER") {
      defaults.width_mm = 1200; defaults.height_mm = 1500; defaults.orientable = false;
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
  React.useEffect(() => {
    if (preview?.blocking_errors?.length) {
      document.querySelector('[data-testid="multi-cat-preview"]')?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [preview?.blocking_errors?.length]);

  const runPreview = React.useCallback(async () => {
    if (!selectedProduct) return;
    setLoading(true);
    try {
      let body;
      if (selectedProduct.pricing_model === "GRID" && inputs.color_code && !inputs.color_name) {
        setPreview({ pricing_status: "incomplete", blocking_errors: ["COLOR_NAME_REQUIRED: inserisci il nome colore."], visual: null });
        setLoading(false);
        return;
      }
      if (selectedProduct.pricing_model === "FORMULA_TECHNICAL") {
        if (!inputs.color_internal || !inputs.color_external || !inputs.color_internal_name || !inputs.color_external_name) {
          setPreview({ pricing_status: "incomplete", blocking_errors: [(!inputs.color_internal || !inputs.color_external) ? "COLOR_CODE_REQUIRED: inserisci il codice colore." : "COLOR_NAME_REQUIRED: inserisci il nome colore."], visual: null });
          setLoading(false);
          return;
        }
        body = {
          technical_inputs: {
            product_key: selectedProduct.key,
            window_type: inputs.window_type || "WINDOW",
            number_of_sashes: Number(inputs.number_of_sashes || 1),
            width_mm: Number(inputs.width_mm || 0),
            height_mm: Number(inputs.height_mm || 0),
            color_mode: inputs.color_mode || deriveColorMode(inputs),
            color_internal: String(inputs.color_internal).trim(),
            color_internal_name: inputs.color_internal_name,
            color_external: String(inputs.color_external).trim(),
            color_external_name: inputs.color_external_name,
            opening_configuration: inputs.opening_configuration || "ANTA_RIBALTA",
            hinge_side: inputs.hinge_side || "DX",
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
            ...(inputs.color_code ? { color_code: String(inputs.color_code).trim(), color_name: inputs.color_name || undefined } : {}),
            ...(inputs.depth_mm ? { depth_mm: Number(inputs.depth_mm) } : {}),
            ...(inputs.ceiling_liner ? { ceiling_liner: inputs.ceiling_liner } : {}),
            ...(typeof inputs.orientable === "boolean" ? { orientable: inputs.orientable } : {}),
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
      ...(isEdit ? { line_id: initialConfig.id, opening_id: initialConfig.opening_id } : {}),
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
            {/* RIGHT: live visual + price (sticky su desktop mentre i campi a sinistra scorrono) */}
            <div className="lg:col-span-2 space-y-3 lg:sticky lg:top-16 self-start">
              {preview?.visual?.svg_exterior && (
                <Card className="rounded-sm border-border p-3" data-testid="multi-cat-visual">
                  <div className="overline mb-2">Schema prodotto (live)</div>
                  <ProductVisualSVG visual={preview.visual} size={200} testid="cfg-visual" />
                </Card>
              )}
              <Card className="rounded-sm border-border p-4" data-testid="multi-cat-preview">
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
    // PO msg 627: solo configurazioni realmente prezzabili sono selezionabili (fail closed lato API in ogni caso).
    const quotable = product?.quotable_configurations || { WINDOW: [1, 2], DOOR_WINDOW: [1, 2] };
    const wt = inputs.window_type || "WINDOW";
    const sashOptions = quotable[wt] || [];
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-technical">
        <div className="text-xs font-bold flex items-center gap-1"><Info size={12} /> Configurazione tecnica autorevole</div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField
            label="TIPO SERRAMENTO"
            value={wt}
            onChange={(v) => setInputs((s) => ({ ...s, window_type: v, number_of_sashes: (quotable[v] || []).includes(Number(s.number_of_sashes)) ? s.number_of_sashes : (quotable[v] || [1])[0] }))}
            options={[["WINDOW","FINESTRA"],["DOOR_WINDOW","PORTAFINESTRA"]].filter(([k]) => (quotable[k] || []).length)}
            testid="cfg-tech-wtype"
          />
          <SelectField label="N. ante" value={String(inputs.number_of_sashes || 1)} onChange={(v) => set("number_of_sashes", Number(v))} options={sashOptions.map((n) => [String(n), `${n} ant${n === 1 ? "a" : "e"}`])} testid="cfg-tech-sashes" />
          <NumField label="Larghezza (mm)" value={inputs.width_mm} onChange={(v) => set("width_mm", v)} testid="cfg-tech-width" />
          <NumField label="Altezza (mm)" value={inputs.height_mm} onChange={(v) => set("height_mm", v)} testid="cfg-tech-height" />
          <SelectField label="Apertura" value={inputs.opening_configuration || "ANTA_RIBALTA"} onChange={(v) => set("opening_configuration", v)} options={[["ANTA_RIBALTA","Anta-ribalta"],["BATTENTE","Battente"],["FISSA","Fissa"]]} testid="cfg-tech-opening" />
          {Number(inputs.number_of_sashes || 1) === 1 && (inputs.opening_configuration || "ANTA_RIBALTA") !== "FISSA" && (
            <SelectField label="Lato cerniere (vista interna)" value={inputs.hinge_side || "DX"} onChange={(v) => set("hinge_side", v)} options={[["DX","Destra"],["SX","Sinistra"]]} testid="cfg-tech-hinge" />
          )}
          <SelectField label="Vetro" value={inputs.glass_type || "DOUBLE_STANDARD"} onChange={(v) => set("glass_type", v)} options={[["DOUBLE_STANDARD","Doppio vetro (76 €/m²)"],["DOUBLE_SATIN","Doppio vetro satinato (96 €/m²)"],["TRIPLE_STANDARD","Triplo vetro (125 €/m²)"],["TRIPLE_SATIN","Triplo vetro satinato (156,25 €/m²)"]]} testid="cfg-tech-glass" />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
        <WindowColorSection inputs={inputs} setInputs={setInputs} />
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
    const cfg = product?.pricing_config || {};
    const widths = cfg.widths_mm || Array.from({ length: 31 }, (_, i) => 500 + i * 100);
    const heights = cfg.heights_mm || [250, 350, 450, 550, 650, 750];
    const depths = cfg.depths_mm || [163, 326, 489, 652];
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-grid">
        <div className="text-xs font-bold">Cassonetto — griglia ufficiale (L × H × profondità × cielino × colore)</div>
        <div className="text-[11px] text-muted-foreground">Solo misure di listino: L {widths[0]}–{widths[widths.length - 1]} mm (step 100) · H {heights.join("/")} mm. Le misure del cassonetto sono indipendenti dal vano.</div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Larghezza cassonetto (mm)" value={String(inputs.width_mm || widths[0])} onChange={(v) => set("width_mm", Number(v))} options={widths.map((w) => [String(w), `${w} mm`])} testid="cfg-grid-width" />
          <SelectField label="Altezza cassonetto (mm)" value={String(inputs.height_mm || heights[0])} onChange={(v) => set("height_mm", Number(v))} options={heights.map((h) => [String(h), `${h} mm`])} testid="cfg-grid-height" />
          <SelectField label="Profondità (mm)" value={String(inputs.depth_mm || depths[0])} onChange={(v) => set("depth_mm", Number(v))} options={depths.map((d) => [String(d), `${d} mm`])} testid="cfg-grid-depth" />
          <SelectField label="Cielino" value={inputs.ceiling_liner || "SI"} onChange={(v) => set("ceiling_liner", v)} options={[["SI","Con cielino"],["NO","Senza cielino"]]} testid="cfg-grid-ceiling" />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
        <ColorCodeNameInput label="Colore cassonetto" code={inputs.color_code} name={inputs.color_name} onChange={(c, n) => setInputs((s) => ({ ...s, color_code: c, color_name: n }))} testid="cfg-grid-color" />
      </Card>
    );
  }

  if (model === "AREA_PURCHASE_MULTIPLIER") {
    const colorMap = product?.pricing_config?.color_map || { RAL: "RAL", WOOD_EFFECT: "WOOD", SPECIAL_RAFFAELLO: "SPECIAL" };
    const labels = { RAL: "Colorazione RAL", WOOD_EFFECT: "Effetto legno", SPECIAL_RAFFAELLO: "Speciali / Raffaello" };
    return (
      <Card className="rounded-sm border-border p-4 space-y-3" data-testid="cfg-persiana">
        <div className="text-xs font-bold">Persiana — dimensioni, colore e orientabilità (minimo 1,30 m² per pezzo)</div>
        <div className="grid grid-cols-3 gap-3">
          <NumField label="Larghezza (mm)" value={inputs.width_mm} onChange={(v) => set("width_mm", v)} testid="cfg-persiana-width" />
          <NumField label="Altezza (mm)" value={inputs.height_mm} onChange={(v) => set("height_mm", v)} testid="cfg-persiana-height" />
          <NumField label="Quantità" value={inputs.quantity || 1} onChange={(v) => set("quantity", v)} testid="cfg-qty" min={1} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Categoria colore" value={inputs.color_code || ""} onChange={(v) => set("color_code", v)} options={Object.keys(colorMap).map((k) => [k, labels[k] || k])} testid="cfg-persiana-color" />
          <SelectField label="Lamelle" value={inputs.orientable === true ? "YES" : inputs.orientable === false ? "NO" : ""} onChange={(v) => set("orientable", v === "YES")} options={[["NO","Fisse"],["YES","Orientabili (+ sovrapprezzo)"]]} testid="cfg-persiana-orientable" />
        </div>
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

/**
 * WindowColorSection — Color Engine finestre PVC (P0 msg 625 §5-§9).
 * Modalità: BIANCO MASSA | BIANCO INT + PELLICOLATO EST | PELLICOLATO 2 LATI STESSO COLORE | BICOLORE.
 * Salva sempre color_internal / color_external come codici catalogo product_colors.
 */
function WindowColorSection({ inputs, setInputs }) {
  const mode = inputs.color_mode || deriveColorMode(inputs);
  const patch = (p) => setInputs((s) => ({ ...s, ...p }));
  const setMode = (m) => {
    const W = { code: WHITE_MASS_CODE, name: WHITE_MASS_NAME };
    const keepExt = inputs.color_external !== WHITE_MASS_CODE ? { code: inputs.color_external, name: inputs.color_external_name } : { code: undefined, name: undefined };
    const keepInt = inputs.color_internal !== WHITE_MASS_CODE ? { code: inputs.color_internal, name: inputs.color_internal_name } : { code: undefined, name: undefined };
    if (m === "WHITE_MASS") patch({ color_mode: m, color_internal: W.code, color_internal_name: W.name, color_external: W.code, color_external_name: W.name });
    else if (m === "WHITE_IN_FOIL_OUT") patch({ color_mode: m, color_internal: W.code, color_internal_name: W.name, color_external: keepExt.code, color_external_name: keepExt.name });
    else if (m === "FOIL_BOTH_SAME") patch({ color_mode: m, color_internal: keepExt.code, color_internal_name: keepExt.name, color_external: keepExt.code, color_external_name: keepExt.name });
    else patch({ color_mode: m, color_internal: keepInt.code, color_internal_name: keepInt.name, color_external: keepExt.code, color_external_name: keepExt.name });
  };
  return (
    <div className="space-y-3 pt-2 border-t border-border" data-testid="cfg-window-color" data-color-mode={mode}>
      <SelectField label="Colore serramento" value={mode} onChange={setMode} options={COLOR_MODES} testid="cfg-color-mode" />
      {mode === "WHITE_MASS" && (
        <div className="text-[11px] text-muted-foreground" data-testid="cfg-color-white-mass-info">Interno ed esterno <b>003 — BIANCO MASSA</b>. Nessuna maggiorazione pellicolato.</div>
      )}
      {mode === "WHITE_IN_FOIL_OUT" && (
        <>
          <div className="text-[11px] text-muted-foreground" data-testid="cfg-color-int-auto">Interno: <b>003 — BIANCO MASSA</b> (automatico)</div>
          <ColorCodeNameInput label="Colore esterno (pellicolato)" code={inputs.color_external} name={inputs.color_external_name} onChange={(c, n) => patch({ color_external: c, color_external_name: n })} testid="cfg-color-ext" />
        </>
      )}
      {mode === "FOIL_BOTH_SAME" && (
        <ColorCodeNameInput label="Colore pellicolato (interno = esterno)" code={inputs.color_external} name={inputs.color_external_name} onChange={(c, n) => patch({ color_internal: c, color_internal_name: n, color_external: c, color_external_name: n })} testid="cfg-color-both" />
      )}
      {mode === "BICOLOR" && (
        <>
          <ColorCodeNameInput label="Colore interno" code={inputs.color_internal} name={inputs.color_internal_name} onChange={(c, n) => patch({ color_internal: c, color_internal_name: n })} testid="cfg-color-int" />
          <ColorCodeNameInput label="Colore esterno" code={inputs.color_external} name={inputs.color_external_name} onChange={(c, n) => patch({ color_external: c, color_external_name: n })} testid="cfg-color-ext" />
          {inputs.color_internal && inputs.color_internal === inputs.color_external && (
            <div className="text-[11px] text-amber-700" data-testid="cfg-color-bicolor-warn">Bicolore richiede interno ≠ esterno: usa "Pellicolato due lati stesso colore".</div>
          )}
        </>
      )}
      <div className="text-[11px] font-mono-plex text-muted-foreground" data-testid="cfg-color-summary">
        Interno: <b data-testid="cfg-color-summary-int">{inputs.color_internal || "—"}</b> · Esterno: <b data-testid="cfg-color-summary-ext">{inputs.color_external || "—"}</b>
      </div>
    </div>
  );
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
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger className="rounded-sm h-9" data-testid={testid}><SelectValue placeholder="Seleziona…" /></SelectTrigger>
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
function ColorPicker({ productCategory, value, onChange, testid, label = "Colore", excludeCodes = [], showCategory = false }) {
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
  const colors = (data?.items || []).filter((c) => !excludeCodes.includes(c.code));
  return (
    <div className="space-y-1" data-testid={testid}>
      <Label className="text-xs">{label}</Label>
      <div className="grid grid-cols-3 md:grid-cols-4 gap-2">
        {colors.map((c) => {
          const active = value === c.code;
          const cat = productCategory === "CASSONETTI"
            ? (c.cassonetti_price_family || "")
            : (c.pvc_color_category || c.price_category || c.cassonetti_price_family || "");
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
              {showCategory && cat && <div className="text-[9px] text-muted-foreground mt-0.5">{cat}</div>}
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
      {product.pricing_model === "AREA_PURCHASE_MULTIPLIER" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-persiana-detail">
          <Row k="Area reale" v={`${s.real_area_m2} m²`} />
          {s.minimum_billable_area_m2 && <Row k="Minimo fatturabile (pz)" v={`${s.minimum_billable_area_m2} m²`} />}
          <Row k="Area fatturata (pz)" v={`${s.billable_area_m2} m²`} />
          <Row k="Categoria colore" v={s.color_price_category} />
          <Row k="Lamelle" v={s.orientable ? "Orientabili" : "Fisse"} />
          <Row k="Prezzo/m²" v={fmt(s.unit_sale_price_per_m2)} />
          {s.purchase_rate_per_m2 != null && canSeeCosts && <Row k="Costo acquisto/m²" v={fmt(s.purchase_rate_per_m2)} />}
          {s.effective_purchase_rate != null && canSeeCosts && s.orientable && <Row k="Costo acquisto/m² (orientabile)" v={fmt(s.effective_purchase_rate)} />}
          {s.purchase_cost_per_item != null && canSeeCosts && <Row k="Costo acquisto (pz)" v={fmt(s.purchase_cost_per_item)} />}
          {s.commercial_multiplier && canSeeCosts && <Row k="Moltiplicatore" v={`× ${s.commercial_multiplier}`} />}
          <Row k="Quantità" v={s.quantity} />
        </div>
      )}
      {product.pricing_model === "GRID" && s && (
        <div className="mt-3 space-y-1 text-xs font-mono-plex" data-testid="preview-grid-detail">
          <Row k="Dimensioni" v={`${s.width_mm}×${s.height_mm} mm`} />
          <Row k="Profondità" v={`${s.depth_mm} mm`} />
          <Row k="Cielino" v={s.ceiling_liner === "SI" ? "Con cielino" : "Senza cielino"} />
          {canSeeCosts && <Row k="Famiglia listino (interno)" v={s.finish_family} />}
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
