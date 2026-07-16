import React, { useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableHead, TableRow, TableHeader, TableBody, TableCell } from "@/components/ui/table";
import { Warning, Info, CheckCircle } from "@phosphor-icons/react";
import { toast } from "sonner";

/**
 * SiteConditionsForm — Componente riutilizzabile per il questionario cantiere.
 *
 * Prop:
 *   - initial: SiteConditions (opzionale)
 *   - onEvaluated(response): callback con l'esito completo
 *   - numPieces: numero pezzi preventivo
 *
 * Alla submit chiama /product-catalog/site-conditions/evaluate e mostra:
 * - complessità
 * - warning
 * - supplementi applicati (costo interno / prezzo cliente / margine)
 * - se preventivabile
 */
export default function SiteConditionsForm({ initial, onEvaluated, numPieces = 1 }) {
  const [c, setC] = useState(initial || {
    floor_level: "ground",
    floor_number_custom: null,
    has_elevator: false,
    elevator_adequate_size: true,
    parking_distance_m: null,
    truck_access: true,
    ztl_zone: false,
    ztl_permit_needed: false,
    public_soil_occupation_needed: false,
    municipal_authorization: "not_needed",
    authorization_managed_by: "tbd",
    platform_status: "not_needed",
    platform_positionable: null,
    working_height_m: null,
    scaffolding_needed: false,
    crane_needed: false,
    movement_difficulty: "easy",
    glass_dismount_for_transport: false,
    has_courtyard: false,
    has_balcony: false,
    obstacles: "",
    notes: "",
  });
  const [result, setResult] = useState(null);

  const set = (k, v) => setC({ ...c, [k]: v });

  const evaluate = async () => {
    try {
      const { data } = await api.post("/product-catalog/site-conditions/evaluate", {
        conditions: c, num_pieces: numPieces,
      });
      setResult(data);
      onEvaluated && onEvaluated(data);
      if (!data.is_quotable) {
        toast.warning("Preventivo non emettibile senza sopralluogo");
      } else {
        toast.success(`Complessità: ${data.conditions.access_complexity}`);
      }
    } catch (e) { toast.error("Errore valutazione"); }
  };

  const fmt = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);

  return (
    <div className="space-y-4" data-testid="site-conditions-form">
      <Card className="p-5 space-y-4">
        <div>
          <div className="overline">Accessibilità e condizioni del cantiere</div>
          <p className="text-xs text-muted-foreground">
            Compila tutti i campi obbligatori per completare il preventivo.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <Label>Piano immobile *</Label>
            <Select value={c.floor_level} onValueChange={v => set("floor_level", v)}>
              <SelectTrigger data-testid="sc-floor"><SelectValue/></SelectTrigger>
              <SelectContent>
                <SelectItem value="basement">Interrato</SelectItem>
                <SelectItem value="ground">Piano terra</SelectItem>
                <SelectItem value="raised">Rialzato</SelectItem>
                <SelectItem value="1st">Primo piano</SelectItem>
                <SelectItem value="2nd">Secondo piano</SelectItem>
                <SelectItem value="3rd">Terzo piano</SelectItem>
                <SelectItem value="higher">Piani superiori</SelectItem>
                <SelectItem value="custom">Piano personalizzato</SelectItem>
                <SelectItem value="independent_house">Casa indipendente</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {c.floor_level === "custom" && (
            <div>
              <Label>Numero piano</Label>
              <Input type="number" value={c.floor_number_custom || ""} onChange={e => set("floor_number_custom", Number(e.target.value))}/>
            </div>
          )}
          <div className="col-span-2 grid grid-cols-3 gap-4">
            <label className="flex items-center gap-2 text-sm"><Switch checked={c.has_elevator} onCheckedChange={v => set("has_elevator", v)} data-testid="sc-elevator"/>Ascensore</label>
            <label className="flex items-center gap-2 text-sm"><Switch disabled={!c.has_elevator} checked={c.elevator_adequate_size} onCheckedChange={v => set("elevator_adequate_size", v)}/>Ascensore adeguato</label>
            <label className="flex items-center gap-2 text-sm"><Switch checked={c.truck_access} onCheckedChange={v => set("truck_access", v)} data-testid="sc-truck"/>Accesso mezzo</label>
          </div>
          <div>
            <Label>Distanza parcheggio-ingresso (m)</Label>
            <Input type="number" value={c.parking_distance_m || ""} onChange={e => set("parking_distance_m", Number(e.target.value))}/>
          </div>
          <div>
            <Label>Difficoltà movimentazione</Label>
            <Select value={c.movement_difficulty} onValueChange={v => set("movement_difficulty", v)}>
              <SelectTrigger><SelectValue/></SelectTrigger>
              <SelectContent>
                <SelectItem value="easy">Facile</SelectItem>
                <SelectItem value="medium">Media</SelectItem>
                <SelectItem value="hard">Difficile</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2 grid grid-cols-2 gap-4">
            <label className="flex items-center gap-2 text-sm"><Switch checked={c.ztl_zone} onCheckedChange={v => set("ztl_zone", v)}/>Zona ZTL</label>
            <label className="flex items-center gap-2 text-sm"><Switch checked={c.ztl_permit_needed} onCheckedChange={v => set("ztl_permit_needed", v)}/>Permesso ZTL necessario</label>
            <label className="flex items-center gap-2 text-sm"><Switch checked={c.public_soil_occupation_needed} onCheckedChange={v => set("public_soil_occupation_needed", v)} data-testid="sc-occupation"/>Occupazione suolo pubblico</label>
            <label className="flex items-center gap-2 text-sm"><Switch checked={c.glass_dismount_for_transport} onCheckedChange={v => set("glass_dismount_for_transport", v)}/>Smontaggio vetri per trasporto</label>
          </div>
          <div>
            <Label>Piattaforma aerea</Label>
            <Select value={c.platform_status} onValueChange={v => set("platform_status", v)}>
              <SelectTrigger data-testid="sc-platform"><SelectValue/></SelectTrigger>
              <SelectContent>
                <SelectItem value="not_needed">Non necessaria</SelectItem>
                <SelectItem value="optional">Facoltativa</SelectItem>
                <SelectItem value="required">Necessaria</SelectItem>
                <SelectItem value="site_inspection_needed">Sopralluogo necessario</SelectItem>
                <SelectItem value="impossible_verify">Impossibilità da verificare</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {c.platform_status === "required" && (
            <div>
              <Label>Piattaforma posizionabile?</Label>
              <Select value={String(c.platform_positionable)} onValueChange={v => set("platform_positionable", v === "true")}>
                <SelectTrigger><SelectValue placeholder="Da verificare"/></SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">Sì</SelectItem>
                  <SelectItem value="false">No</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label>Autorizzazione comunale</Label>
            <Select value={c.municipal_authorization} onValueChange={v => set("municipal_authorization", v)}>
              <SelectTrigger data-testid="sc-authorization"><SelectValue/></SelectTrigger>
              <SelectContent>
                <SelectItem value="not_needed">Non necessaria</SelectItem>
                <SelectItem value="needed_verify">Da verificare</SelectItem>
                <SelectItem value="needed_managed_by_customer">Necessaria - gestita da cliente</SelectItem>
                <SelectItem value="needed_managed_by_company">Necessaria - gestita da azienda</SelectItem>
                <SelectItem value="obtained">Ottenuta</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Gestione autorizzazioni</Label>
            <Select value={c.authorization_managed_by} onValueChange={v => set("authorization_managed_by", v)}>
              <SelectTrigger><SelectValue/></SelectTrigger>
              <SelectContent>
                <SelectItem value="tbd">Da definire</SelectItem>
                <SelectItem value="customer">Cliente</SelectItem>
                <SelectItem value="company">Azienda</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="col-span-2">
            <Label>Note e ostacoli</Label>
            <Textarea value={c.obstacles || ""} onChange={e => set("obstacles", e.target.value)} rows={2}/>
          </div>
        </div>
        <Button onClick={evaluate} data-testid="btn-evaluate-site">Valuta accessibilità</Button>
      </Card>

      {result && (
        <Card className="p-5 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <div className="overline">Esito valutazione</div>
              <div className="text-xl font-bold" data-testid="site-complexity">Complessità: {result.conditions.access_complexity}</div>
            </div>
            <Badge className={
              result.conditions.risk_level === "critical" ? "bg-red-100 text-red-800" :
              result.conditions.risk_level === "high" ? "bg-amber-100 text-amber-800" :
              result.conditions.risk_level === "medium" ? "bg-yellow-100 text-yellow-800" :
              "bg-green-100 text-green-800"
            } data-testid="site-risk">
              Rischio {result.conditions.risk_level}
            </Badge>
          </div>
          {!result.is_quotable && (
            <Alert variant="destructive" data-testid="site-not-quotable">
              <Warning size={16}/>
              <AlertTitle>Preventivo non emettibile</AlertTitle>
              <AlertDescription>È necessario un sopralluogo prima di poter emettere un preventivo definitivo.</AlertDescription>
            </Alert>
          )}
          {(result.conditions.warnings || []).length > 0 && (
            <div className="space-y-1">
              {(result.conditions.warnings || []).map((w, i) => (
                <Alert key={i}><Warning size={14}/><AlertDescription className="text-xs">{w}</AlertDescription></Alert>
              ))}
            </div>
          )}
          {(result.surcharges_applied || []).length > 0 && (
            <div>
              <div className="overline mb-2">Supplementi applicati</div>
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Voce</TableHead><TableHead>Trigger</TableHead>
                  <TableHead className="text-right">Cliente</TableHead>
                  <TableHead className="text-right">Costo interno</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {result.surcharges_applied.map((s, i) => (
                    <TableRow key={i}>
                      <TableCell>{s.label}</TableCell>
                      <TableCell><Badge variant="outline" className="text-[10px]">{s.trigger}</Badge></TableCell>
                      <TableCell className="text-right font-mono">{fmt(s.customer_price)}</TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">{fmt(s.internal_cost)}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="font-bold">
                    <TableCell colSpan={2}>TOTALE</TableCell>
                    <TableCell className="text-right font-mono">{fmt(result.total_customer)}</TableCell>
                    <TableCell className="text-right font-mono">{fmt(result.total_internal_cost)}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              <div className="mt-2 text-sm">
                <span className="text-muted-foreground">Margine: </span>
                <span className="font-mono font-bold">{fmt(result.margin)}</span>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
