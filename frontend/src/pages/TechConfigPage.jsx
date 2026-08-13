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
        <TabsList data-testid="tech-config-tabs">
          <TabsTrigger value="workshop" data-testid="tab-workshop">Costo officina</TabsTrigger>
          <TabsTrigger value="commercial" data-testid="tab-commercial">Regola commerciale</TabsTrigger>
          <TabsTrigger value="components" data-testid="tab-components">Prezzi componenti</TabsTrigger>
          <TabsTrigger value="recipes" data-testid="tab-recipes">Ricette tecniche</TabsTrigger>
        </TabsList>
        <TabsContent value="workshop"><WorkshopCostTab /></TabsContent>
        <TabsContent value="commercial"><CommercialRuleTab /></TabsContent>
        <TabsContent value="components"><ComponentPricesTab /></TabsContent>
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
