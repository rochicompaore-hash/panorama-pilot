import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { toast } from "sonner";
import { api } from "@/api/client";

/**
 * Configurazione tecnica — UI amministrativa per il motore Unified Pricing v3.
 * Milestone A: gestione da UI di workshop_cost, commercial_rule e prezzi componenti.
 *
 * Preventivi esistenti NON vengono ricalcolati. Solo NUOVI /api/pricing/compute
 * usano i nuovi valori (snapshot congelato preservato).
 */
export default function TechConfigPage() {
  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4" data-testid="tech-config-page">
      <div>
        <h1 className="text-2xl font-semibold" data-testid="tech-config-title">Configurazione tecnica</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Amministrazione del motore Unified Pricing v3 senza toccare MongoDB.
          I preventivi esistenti restano congelati; solo i NUOVI calcoli useranno i nuovi valori.
        </p>
      </div>
      <Tabs defaultValue="workshop">
        <TabsList data-testid="tech-config-tabs" className="flex flex-wrap h-auto">
          <TabsTrigger value="workshop" data-testid="tab-workshop">Costo officina</TabsTrigger>
          <TabsTrigger value="commercial" data-testid="tab-commercial">Regola commerciale</TabsTrigger>
          <TabsTrigger value="components" data-testid="tab-components">Prezzi componenti</TabsTrigger>
          <TabsTrigger value="glass" data-testid="tab-glass">Vetri</TabsTrigger>
          <TabsTrigger value="hardware" data-testid="tab-hardware">Ferramenta</TabsTrigger>
          <TabsTrigger value="prodtime" data-testid="tab-prodtime">Tempi produzione</TabsTrigger>
          <TabsTrigger value="recipes" data-testid="tab-recipes">Ricette tecniche</TabsTrigger>
        </TabsList>
        <TabsContent value="workshop"><WorkshopCostTab /></TabsContent>
        <TabsContent value="commercial"><CommercialRuleTab /></TabsContent>
        <TabsContent value="components"><ComponentPricesTab /></TabsContent>
        <TabsContent value="glass"><GlassPricesTab /></TabsContent>
        <TabsContent value="hardware"><HardwareRulesTab /></TabsContent>
        <TabsContent value="prodtime"><ProductionTimesTab /></TabsContent>
        <TabsContent value="recipes"><TechnicalRecipesTab /></TabsContent>
      </Tabs>
    </div>
  );
}

function WorkshopCostTab() {
  const [value, setValue] = useState("");
  const [version, setVersion] = useState(0);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get("/tech-config/workshop-cost");
    setValue(data.hourly_workshop_cost || "");
    setVersion(data.version || 0);
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/tech-config/workshop-cost", { hourly_workshop_cost: Number(value) });
      toast.success("Costo officina aggiornato");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Errore salvataggio");
    } finally { setSaving(false); }
  };

  return (
    <Card data-testid="workshop-cost-card">
      <CardHeader>
        <CardTitle>Costo orario officina (hourly_workshop_cost)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>€ / ora (versione corrente: v{version})</Label>
          <Input type="number" step="0.01" value={value} onChange={e => setValue(e.target.value)}
                 data-testid="workshop-cost-input" placeholder="180.00" />
          <p className="text-xs text-muted-foreground mt-1">V1_3 BR-06: 180 €/h approvato.</p>
        </div>
        <Button onClick={save} disabled={saving || !value} data-testid="workshop-cost-save">
          {saving ? "Salvataggio…" : "Salva"}
        </Button>
      </CardContent>
    </Card>
  );
}

function CommercialRuleTab() {
  const [method, setMethod] = useState("MULTIPLIER");
  const [multiplier, setMultiplier] = useState("");
  const [version, setVersion] = useState(0);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get("/tech-config/commercial-rule");
    if (data.configured) {
      setMethod(data.method);
      setMultiplier(data.multiplier || "");
      setVersion(data.version || 0);
    }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/tech-config/commercial-rule", {
        method, multiplier: method === "MULTIPLIER" ? Number(multiplier) : null,
      });
      toast.success("Regola commerciale aggiornata");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Errore");
    } finally { setSaving(false); }
  };

  return (
    <Card data-testid="commercial-rule-card">
      <CardHeader><CardTitle>Regola commerciale (versione v{version})</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>Metodo</Label>
          <select value={method} onChange={e => setMethod(e.target.value)}
                  className="w-full border rounded px-3 py-2" data-testid="commercial-method">
            <option value="MULTIPLIER">MULTIPLIER (prezzo = costo × moltiplicatore)</option>
            <option value="MARKUP_ON_COST">MARKUP_ON_COST (prezzo = costo × (1 + markup%))</option>
            <option value="TARGET_GROSS_MARGIN">TARGET_GROSS_MARGIN</option>
            <option value="FIXED_PRICE">FIXED_PRICE</option>
          </select>
        </div>
        {method === "MULTIPLIER" && (
          <div>
            <Label>Moltiplicatore (es. 3.0)</Label>
            <Input type="number" step="0.01" value={multiplier} onChange={e => setMultiplier(e.target.value)}
                   data-testid="commercial-multiplier-input" placeholder="3.00" />
          </div>
        )}
        <Button onClick={save} disabled={saving} data-testid="commercial-rule-save">
          {saving ? "Salvataggio…" : "Salva"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ComponentPricesTab() {
  const [entries, setEntries] = useState([]);
  const [meta, setMeta] = useState({});
  const [form, setForm] = useState({ code: "", unit_price: "", unit: "ml", color_code: "", description: "" });

  const load = async () => {
    const { data } = await api.get("/tech-config/component-prices");
    setEntries(data.entries || []);
    setMeta({ id: data.pricelist_id, name: data.pricelist_name, version: data.version });
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!form.code || !form.unit_price) { toast.error("Codice e prezzo obbligatori"); return; }
    try {
      await api.put(`/tech-config/component-prices/${encodeURIComponent(form.code)}`, {
        code: form.code, unit_price: Number(form.unit_price), unit: form.unit,
        color_code: form.color_code || null, description: form.description || null,
      });
      toast.success(`${form.code} aggiornato`);
      setForm({ code: "", unit_price: "", unit: "ml", color_code: "", description: "" });
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Errore");
    }
  };

  return (
    <Card data-testid="component-prices-card">
      <CardHeader><CardTitle>Prezzi componenti — {meta.name} v{meta.version}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <Input placeholder="Codice (es. GLAZING_BEAD_PROEVOLUTION)" value={form.code}
                 onChange={e => setForm({...form, code: e.target.value})} data-testid="cp-code" />
          <Input type="number" step="0.01" placeholder="Prezzo unitario" value={form.unit_price}
                 onChange={e => setForm({...form, unit_price: e.target.value})} data-testid="cp-price" />
          <select value={form.unit} onChange={e => setForm({...form, unit: e.target.value})}
                  className="border rounded px-3 py-2" data-testid="cp-unit">
            <option value="ml">€/ml</option><option value="pz">€/pz</option><option value="sqm">€/m²</option>
          </select>
          <Input placeholder="Colore (opz.)" value={form.color_code}
                 onChange={e => setForm({...form, color_code: e.target.value})} data-testid="cp-color" />
          <Button onClick={save} data-testid="cp-save">Aggiungi/Aggiorna</Button>
        </div>
        <div className="border rounded">
          <table className="w-full text-sm" data-testid="cp-table">
            <thead className="bg-slate-50">
              <tr><th className="p-2 text-left">Codice</th><th className="p-2">Colore</th>
                <th className="p-2">Prezzo</th><th className="p-2">Unità</th><th className="p-2">Descrizione</th></tr>
            </thead>
            <tbody>
              {entries.length === 0 && <tr><td colSpan="5" className="p-4 text-center text-muted-foreground">
                Nessun componente configurato. Aggiungi il primo.</td></tr>}
              {entries.map((e, i) => (
                <tr key={i} className="border-t" data-testid={`cp-row-${e.code}`}>
                  <td className="p-2 font-mono text-xs">{e.code}</td>
                  <td className="p-2">{e.color_code || "-"}</td>
                  <td className="p-2">{e.unit_price} €</td>
                  <td className="p-2">{e.unit}</td>
                  <td className="p-2 text-xs text-muted-foreground">{e.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function TechnicalRecipesTab() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/tech-config/technical-recipes").then(({data}) => setItems(data.items)); }, []);
  return (
    <Card data-testid="recipes-card">
      <CardHeader><CardTitle>Ricette tecniche (read-only in Milestone A)</CardTitle></CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead className="bg-slate-50"><tr>
            <th className="p-2 text-left">Prodotto</th><th className="p-2">Ricetta</th>
            <th className="p-2">Sistema profilo</th><th className="p-2">Tempo (h)</th><th className="p-2">Ver.</th>
          </tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan="5" className="p-4 text-center text-muted-foreground">
              Nessuna ricetta. Milestone A carica quelle già seedate (ProEvolution WINDOW_1_SASH).</td></tr>}
            {items.map(r => (
              <tr key={r.id} className="border-t">
                <td className="p-2 font-medium">{r.product_key}</td>
                <td className="p-2 font-mono text-xs">{r.recipe_code}</td>
                <td className="p-2">{r.profile_system_code}</td>
                <td className="p-2">{r.production_time_hours}</td>
                <td className="p-2">v{r.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-muted-foreground mt-4">
          Editing ricette pianificato nelle Milestone successive. Per ora le ricette sono cablate in `pricing_v3/formulas.py` e seedate via script.
        </p>
      </CardContent>
    </Card>
  );
}


// =====================================================================
// GLASS PRICES TAB — Milestone 2 (Enerhia Operating Core)
// =====================================================================
function GlassPricesTab() {
  const [items, setItems] = useState([]);
  const [saving, setSaving] = useState("");

  const load = async () => {
    const r = await api.get("/tech-config/glass-prices");
    setItems(r.data.items || []);
  };
  useEffect(() => { load(); }, []);

  const save = async (row) => {
    setSaving(row.glass_type);
    try {
      await api.put(`/tech-config/glass-prices/${row.glass_type}`, {
        glass_type: row.glass_type,
        unit_price_per_sqm: Number(row.unit_price_per_sqm),
        min_billable_sqm: Number(row.min_billable_sqm),
        description: row.description || "",
      });
      toast.success(`Vetro ${row.glass_type} salvato`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message);
    } finally { setSaving(""); }
  };

  return (
    <Card className="rounded-sm" data-testid="glass-prices-tab">
      <CardHeader>
        <CardTitle className="text-base">Vetri — prezzi €/m² e minimo fatturabile</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground mb-3">
          Valori ufficiali Enerhia (BR-07): <b>DOUBLE_STANDARD 76</b>, <b>DOUBLE_SATIN 96</b>,
          <b> TRIPLE_STANDARD 125</b>, <b>TRIPLE_SATIN 156,25</b>. Minimo fatturabile per pannello: <b>0.50 m²</b>.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="p-2 overline">Tipo vetro</th>
              <th className="p-2 overline">Prezzo €/m²</th>
              <th className="p-2 overline">Min m² per pannello</th>
              <th className="p-2 overline">Descrizione</th>
              <th className="p-2 overline">Ver.</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((r, i) => (
              <tr key={r.id} className="border-b border-border" data-testid={`glass-row-${r.glass_type}`}>
                <td className="p-2 font-mono-plex text-xs">{r.glass_type}</td>
                <td className="p-2"><Input type="number" step="0.01" className="rounded-sm h-9 w-28"
                  value={r.unit_price_per_sqm}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, unit_price_per_sqm: e.target.value } : y))}
                  data-testid={`glass-price-${r.glass_type}`} /></td>
                <td className="p-2"><Input type="number" step="0.01" className="rounded-sm h-9 w-24"
                  value={r.min_billable_sqm}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, min_billable_sqm: e.target.value } : y))}
                  data-testid={`glass-min-${r.glass_type}`} /></td>
                <td className="p-2"><Input className="rounded-sm h-9"
                  value={r.description || ""}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, description: e.target.value } : y))} /></td>
                <td className="p-2 font-mono-plex text-xs text-muted-foreground">{r.version}</td>
                <td className="p-2"><Button size="sm" className="rounded-sm" disabled={saving === r.glass_type} onClick={() => save(r)} data-testid={`glass-save-${r.glass_type}`}>Salva</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

// =====================================================================
// HARDWARE RULES TAB — Milestone 2
// =====================================================================
function HardwareRulesTab() {
  const [items, setItems] = useState([]);
  const [saving, setSaving] = useState("");

  const load = async () => {
    const r = await api.get("/tech-config/hardware-rules");
    setItems(r.data.items || []);
  };
  useEffect(() => { load(); }, []);

  const save = async (row) => {
    setSaving(row.id);
    try {
      await api.put(`/tech-config/hardware-rules/${row.id}`, {
        opening_type: row.opening_type,
        number_of_sashes: row.number_of_sashes === "" ? null : Number(row.number_of_sashes),
        cost_per_unit: Number(row.cost_per_unit),
        per_sash: !!row.per_sash,
        description: row.description || "",
      });
      toast.success(`Ferramenta ${row.opening_type} salvata`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message);
    } finally { setSaving(""); }
  };

  return (
    <Card className="rounded-sm" data-testid="hardware-rules-tab">
      <CardHeader>
        <CardTitle className="text-base">Ferramenta — regole per tipologia serramento</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground mb-3">
          Valori ufficiali Enerhia (BR-08): <b>WINDOW_1_SASH 60</b>, <b>WINDOW_2_SASH 80</b>,
          <b> DOOR_WINDOW_1_SASH 75</b>, <b>DOOR_WINDOW_2_SASH 90</b>,
          <b> SLIDING 380 €/anta</b>, <b>VASISTAS_ONLY 40</b>. Costi tecnici di ferramenta, non prezzo di vendita.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="p-2 overline">Opening</th>
              <th className="p-2 overline">Ante</th>
              <th className="p-2 overline">Costo €</th>
              <th className="p-2 overline">Per anta?</th>
              <th className="p-2 overline">Descrizione</th>
              <th className="p-2 overline">Ver.</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((r, i) => (
              <tr key={r.id} className="border-b border-border" data-testid={`hw-row-${r.opening_type}-${r.number_of_sashes ?? "N"}`}>
                <td className="p-2 font-mono-plex text-xs">{r.opening_type}</td>
                <td className="p-2 font-mono-plex text-xs">{r.number_of_sashes ?? "—"}</td>
                <td className="p-2"><Input type="number" step="0.01" className="rounded-sm h-9 w-24"
                  value={r.cost_per_unit}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, cost_per_unit: e.target.value } : y))}
                  data-testid={`hw-cost-${r.opening_type}`} /></td>
                <td className="p-2"><input type="checkbox" checked={!!r.per_sash}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, per_sash: e.target.checked } : y))} /></td>
                <td className="p-2"><Input className="rounded-sm h-9"
                  value={r.description || ""}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, description: e.target.value } : y))} /></td>
                <td className="p-2 font-mono-plex text-xs text-muted-foreground">{r.version}</td>
                <td className="p-2"><Button size="sm" className="rounded-sm" disabled={saving === r.id} onClick={() => save(r)} data-testid={`hw-save-${r.id}`}>Salva</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

// =====================================================================
// PRODUCTION TIMES TAB — Milestone 2
// =====================================================================
function ProductionTimesTab() {
  const [items, setItems] = useState([]);
  const [saving, setSaving] = useState("");

  const load = async () => {
    const r = await api.get("/tech-config/production-times");
    setItems(r.data.items || []);
  };
  useEffect(() => { load(); }, []);

  const save = async (row) => {
    setSaving(row.recipe_code);
    try {
      await api.put(`/tech-config/production-times/${row.recipe_code}`, {
        recipe_code: row.recipe_code,
        hours: Number(row.hours),
        description: row.description || "",
      });
      toast.success(`Tempo ${row.recipe_code} salvato`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message);
    } finally { setSaving(""); }
  };

  return (
    <Card className="rounded-sm" data-testid="production-times-tab">
      <CardHeader>
        <CardTitle className="text-base">Tempi di produzione — ore per configurazione</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground mb-3">
          Valori ufficiali Enerhia (BR-05). Il costo manodopera = tempo × costo officina.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="p-2 overline">Ricetta</th>
              <th className="p-2 overline">Ore</th>
              <th className="p-2 overline">Descrizione</th>
              <th className="p-2 overline">Ver.</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((r, i) => (
              <tr key={r.id} className="border-b border-border" data-testid={`pt-row-${r.recipe_code}`}>
                <td className="p-2 font-mono-plex text-xs">{r.recipe_code}</td>
                <td className="p-2"><Input type="number" step="0.05" className="rounded-sm h-9 w-24"
                  value={r.hours}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, hours: e.target.value } : y))}
                  data-testid={`pt-hours-${r.recipe_code}`} /></td>
                <td className="p-2"><Input className="rounded-sm h-9"
                  value={r.description || ""}
                  onChange={(e) => setItems((x) => x.map((y, j) => j === i ? { ...y, description: e.target.value } : y))} /></td>
                <td className="p-2 font-mono-plex text-xs text-muted-foreground">{r.version}</td>
                <td className="p-2"><Button size="sm" className="rounded-sm" disabled={saving === r.recipe_code} onClick={() => save(r)} data-testid={`pt-save-${r.recipe_code}`}>Salva</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
