import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Warning, Buildings, PencilSimple, Users } from "@phosphor-icons/react";
import { toast } from "sonner";

const REQUIRED_FISCAL = [
  { field: "vat_number", label: "P.IVA" },
  { field: "tax_code", label: "Codice Fiscale" },
  { field: "sdi_code", label: "Codice SDI" },
  { field: "pec", label: "PEC" },
  { field: "email", label: "Email" },
  { field: "phone", label: "Telefono" },
  { field: "vat_regime", label: "Regime IVA" },
  { field: "vat_periodicity", label: "Periodicità IVA" },
  { field: "default_iban", label: "IBAN" },
  { field: "rea", label: "REA" },
  { field: "share_capital", label: "Capitale sociale" },
  { field: "activity_start_date", label: "Data inizio attività" },
];

export default function LegalEntitiesPage() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newDialogOpen, setNewDialogOpen] = useState(false);
  const [newForm, setNewForm] = useState({ code: "", name: "", legal_form: "SRL" });

  const load = async () => {
    try {
      const { data } = await api.get("/legal-entities");
      setItems(data.items || []);
    } catch (e) { toast.error("Errore caricamento società"); }
  };
  useEffect(() => { load(); }, []);

  const openEdit = (le) => {
    setSelected(le);
    setForm({ ...le });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!selected) return;
    try {
      const payload = {};
      REQUIRED_FISCAL.forEach(f => { if (form[f.field] !== undefined) payload[f.field] = form[f.field]; });
      ["name", "legal_form", "website", "logo_url"].forEach(k => { if (form[k] !== undefined) payload[k] = form[k]; });
      await api.patch(`/legal-entities/${selected.id}`, payload);
      toast.success("Società aggiornata");
      setDialogOpen(false);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Errore salvataggio"); }
  };

  const createEntity = async () => {
    if (!newForm.code || !newForm.name) { toast.error("Codice e nome richiesti"); return; }
    try {
      await api.post("/legal-entities", newForm);
      toast.success("Società creata (dati fiscali da completare)");
      setNewDialogOpen(false);
      setNewForm({ code: "", name: "", legal_form: "SRL" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Errore creazione"); }
  };

  return (
    <div className="space-y-6" data-testid="legal-entities-page">
      <div className="flex items-center justify-between">
        <div>
          <div className="overline text-muted-foreground">Multi-company</div>
          <h1 className="font-display text-3xl font-black tracking-tight">Società (Legal Entities)</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Ogni operazione economica è legata a una legal entity. I dati fiscali incompleti bloccano le operazioni ufficiali.
          </p>
        </div>
        <Dialog open={newDialogOpen} onOpenChange={setNewDialogOpen}>
          <DialogTrigger asChild>
            <Button data-testid="btn-new-entity"><Buildings size={16} className="mr-2"/>Nuova società</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Nuova Legal Entity</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div><Label>Codice</Label>
                <Input value={newForm.code} onChange={e => setNewForm({...newForm, code: e.target.value.toUpperCase()})} data-testid="new-entity-code"/>
              </div>
              <div><Label>Ragione sociale</Label>
                <Input value={newForm.name} onChange={e => setNewForm({...newForm, name: e.target.value})} data-testid="new-entity-name"/>
              </div>
              <div><Label>Forma giuridica</Label>
                <Select value={newForm.legal_form} onValueChange={v => setNewForm({...newForm, legal_form: v})}>
                  <SelectTrigger data-testid="new-entity-form"><SelectValue/></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="SRL">SRL</SelectItem>
                    <SelectItem value="SPA">SPA</SelectItem>
                    <SelectItem value="SNC">SNC</SelectItem>
                    <SelectItem value="SAS">SAS</SelectItem>
                    <SelectItem value="DITTA_INDIVIDUALE">Ditta individuale</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Alert>
                <Warning size={16}/>
                <AlertDescription>
                  Non verranno inserite P.IVA fittizie. La società sarà creata in stato "to_complete" e bloccata
                  per operazioni fiscali finché i dati non vengono compilati.
                </AlertDescription>
              </Alert>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setNewDialogOpen(false)}>Annulla</Button>
              <Button onClick={createEntity} data-testid="btn-save-new-entity">Crea</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {items.map(le => (
          <Card key={le.id} className="p-6" data-testid={`entity-card-${le.code}`}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="font-mono-plex text-[11px] text-muted-foreground">{le.code}</div>
                <div className="text-xl font-bold">{le.name}</div>
                <div className="text-xs text-muted-foreground">{le.legal_form || "—"}</div>
              </div>
              <Badge variant={le.le_status === "active" ? "default" : "outline"}
                     className={le.fiscal_operations_blocked ? "border-red-500 text-red-600" : ""}
                     data-testid={`entity-status-${le.code}`}>
                {le.le_status === "to_complete" ? "DA COMPLETARE" : le.le_status.toUpperCase()}
              </Badge>
            </div>
            {le.fiscal_operations_blocked && (
              <Alert variant="destructive" className="mb-3">
                <Warning size={16}/>
                <AlertTitle>Dati fiscali incompleti</AlertTitle>
                <AlertDescription className="text-xs">
                  Mancano: {(le.missing_fields || []).join(", ")}. Operazioni fiscali bloccate.
                </AlertDescription>
              </Alert>
            )}
            <div className="text-xs space-y-1 mb-4">
              <div><span className="text-muted-foreground">P.IVA:</span> <span className="font-mono">{le.vat_number || "—"}</span></div>
              <div><span className="text-muted-foreground">C.F.:</span> <span className="font-mono">{le.tax_code || "—"}</span></div>
              <div><span className="text-muted-foreground">PEC:</span> {le.pec || "—"}</div>
              <div><span className="text-muted-foreground">SDI:</span> <span className="font-mono">{le.sdi_code || "—"}</span></div>
              <div><span className="text-muted-foreground">Regime IVA:</span> {le.vat_regime || "—"} ({le.vat_periodicity || "—"})</div>
            </div>
            <Button variant="outline" size="sm" onClick={() => openEdit(le)} data-testid={`btn-edit-entity-${le.code}`}>
              <PencilSimple size={14} className="mr-1"/>Modifica dati fiscali
            </Button>
          </Card>
        ))}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Modifica {selected?.name}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            {REQUIRED_FISCAL.map(f => (
              <div key={f.field}>
                <Label>{f.label}</Label>
                {f.field === "vat_regime" ? (
                  <Select value={form[f.field] || ""} onValueChange={v => setForm({...form, [f.field]: v})}>
                    <SelectTrigger data-testid={`entity-input-${f.field}`}><SelectValue placeholder="Seleziona"/></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ordinario">Ordinario</SelectItem>
                      <SelectItem value="forfettario">Forfettario</SelectItem>
                      <SelectItem value="agricolo">Agricolo</SelectItem>
                      <SelectItem value="marginale">Marginale</SelectItem>
                    </SelectContent>
                  </Select>
                ) : f.field === "vat_periodicity" ? (
                  <Select value={form[f.field] || ""} onValueChange={v => setForm({...form, [f.field]: v})}>
                    <SelectTrigger data-testid={`entity-input-${f.field}`}><SelectValue placeholder="Seleziona"/></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="monthly">Mensile</SelectItem>
                      <SelectItem value="quarterly">Trimestrale</SelectItem>
                      <SelectItem value="annual">Annuale</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Input value={form[f.field] || ""}
                          onChange={e => setForm({...form, [f.field]: e.target.value})}
                          data-testid={`entity-input-${f.field}`}/>
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Annulla</Button>
            <Button onClick={save} data-testid="btn-save-entity">Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
