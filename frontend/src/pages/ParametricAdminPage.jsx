/**
 * ParametricAdminPage
 * -------------------
 * Amministrazione dell'Engine Parametrico:
 *  - Sistemi profilo, profili, categorie colore, colori
 *  - Vetri, ferramenta, accessori
 *  - Item pricelists (vendita/costo)
 *  - Price matrices
 *  - BOM templates
 *  - Pricing mode configs (tenant/prodotto/sistema)
 *
 * MVP: elenco read-only + creazione base. Le modifiche fine-grained sui
 * componenti BOM/celle matrice sono possibili tramite endpoint dedicati.
 */
import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const SECTIONS = [
  { id: "profile-systems", label: "Sistemi profilo", fields: ["code", "name", "material", "series"] },
  { id: "profiles", label: "Profili", fields: ["code", "name", "role", "indicative_price_per_m"] },
  { id: "color-categories", label: "Categorie colore", fields: ["code", "name", "scrap_mode", "surcharge_pct", "charges_whole_bar"] },
  { id: "colors", label: "Colori", fields: ["code", "name", "ral_code"] },
  { id: "glass-types", label: "Vetri", fields: ["code", "name", "thickness_mm", "indicative_sqm_price"] },
  { id: "hardware-kits", label: "Ferramenta", fields: ["code", "name", "kit_type", "indicative_price"] },
  { id: "accessories", label: "Accessori", fields: ["code", "name", "kind", "unit_type", "indicative_price"] },
  { id: "item-pricelists", label: "Listini articoli", fields: ["code", "name", "kind", "currency"] },
  { id: "price-matrices", label: "Matrici prezzi", fields: ["code", "name", "product_key", "interpolation"] },
  { id: "bom-templates", label: "BOM parametriche", fields: ["code", "name", "product_key", "level", "bom_status"] },
  { id: "pricing-modes", label: "Modalità pricing", fields: ["scope", "product_key", "mode", "b_markup_pct"] },
];

function Section({ id, label, fields }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/parametric/${id}`);
      setItems(data.items || data || []);
    } catch (e) {
      toast.error(`Errore caricamento ${label}`);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [id]);
  return (
    <Card className="rounded-sm">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">{label} <Badge variant="outline" className="ml-2 rounded-sm">{items.length}</Badge></CardTitle>
        <Button size="sm" variant="outline" onClick={load} className="rounded-sm" data-testid={`refresh-${id}`}>
          Aggiorna
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-6 text-sm text-muted-foreground">Caricamento…</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground">Nessun dato.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground border-b bg-muted">
                <tr>
                  {fields.map(f => <th key={f} className="text-left py-2 px-3">{f}</th>)}
                  <th className="text-left py-2 px-3">demo</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={it.id || i} className="border-b" data-testid={`${id}-row-${i}`}>
                    {fields.map(f => (
                      <td key={f} className="py-1.5 px-3 font-mono-plex text-[13px]">
                        {formatCell(it[f])}
                      </td>
                    ))}
                    <td className="py-1.5 px-3">
                      {it.is_demo ? <Badge variant="secondary" className="rounded-sm text-[10px]">DEMO</Badge> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatCell(v) {
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "✓" : "—";
  if (typeof v === "number") return v.toLocaleString("it-IT");
  return String(v).slice(0, 60);
}

export default function ParametricAdminPage() {
  const [demoStatus, setDemoStatus] = useState(null);
  useEffect(() => {
    api.get("/parametric/demo/status").then(r => setDemoStatus(r.data)).catch(() => {});
  }, []);
  return (
    <div className="space-y-6" data-testid="parametric-admin-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="overline text-muted-foreground">Configurazione Preventivatore</div>
          <h1 className="font-display text-3xl font-black tracking-tight">Engine Parametrico</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Gestione centralizzata: sistemi profilo, BOM parametriche versionate, matrici prezzi,
            categorie colore con policy scarto, listini vendita/costo, modalità pricing A/B/C.
          </p>
        </div>
        {demoStatus?.is_demo_present && (
          <Badge variant="secondary" className="rounded-sm" data-testid="demo-badge">
            Dati DEMO presenti
          </Badge>
        )}
      </div>

      <Tabs defaultValue="profile-systems">
        <TabsList className="rounded-sm flex-wrap h-auto">
          {SECTIONS.map(s => (
            <TabsTrigger key={s.id} value={s.id} data-testid={`tab-${s.id}`} className="text-xs">
              {s.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {SECTIONS.map(s => (
          <TabsContent key={s.id} value={s.id}>
            <Section {...s} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
