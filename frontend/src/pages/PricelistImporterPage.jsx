import { useEffect, useState, useRef } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/**
 * Pricelist Importer Wizard — XLS/CSV upload → mapping → validate → preview → publish → rollback.
 */
export default function PricelistImporterPage() {
  const [step, setStep] = useState(1);
  const [entityType, setEntityType] = useState("profile");
  const [pricelists, setPricelists] = useState([]);
  const [targetPl, setTargetPl] = useState("");
  const [file, setFile] = useState(null);
  const [job, setJob] = useState(null);
  const [schema, setSchema] = useState(null);
  const [mappings, setMappings] = useState([]);
  const [jobs, setJobs] = useState([]);
  const fileRef = useRef();

  useEffect(() => {
    (async () => {
      const pl = await api.get("/parametric/item-pricelists");
      setPricelists(pl.data.items || []);
      const j = await api.get("/importer/jobs?limit=20");
      setJobs(j.data.items || []);
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/importer/schema/${entityType}`);
        setSchema(data);
      } catch { setSchema(null); }
    })();
  }, [entityType]);

  const upload = async () => {
    if (!file || !targetPl) {
      toast.error("Seleziona file e listino target");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("entity_type", entityType);
    fd.append("target_pricelist_id", targetPl);
    try {
      const { data } = await api.post("/importer/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        transformRequest: [(d, h) => { delete h["Content-Type"]; return d; }],
      });
      setJob(data);
      // auto-map by header name similarity
      const auto = [];
      if (schema?.fields && data.detected_headers) {
        for (const f of schema.fields) {
          const found = data.detected_headers.find(h =>
            h.toLowerCase().includes(f.code.toLowerCase()) ||
            (f.label || "").toLowerCase().split(" ").some(w => w.length > 3 && h.toLowerCase().includes(w))
          );
          if (found) {
            auto.push({ source_column: found, target_field: f.code, transform: f.transform, required: f.required, default_if_empty: f.default });
          }
        }
      }
      setMappings(auto);
      setStep(2);
      toast.success(`File caricato: ${data.total_rows} righe`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore upload");
    }
  };

  const applyMapping = async () => {
    if (!job) return;
    try {
      const { data } = await api.post(`/importer/jobs/${job.id}/map`, {
        selected_sheet: job.selected_sheet,
        mappings,
      });
      setJob(data);
      setStep(3);
      if (data.validation_errors?.some(e => e.severity === "error")) {
        toast.warning(`${data.validation_errors.length} errori/warning — controlla anteprima`);
      } else {
        toast.success(`Validato: ${data.valid_rows} righe valide`);
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore mapping");
    }
  };

  const publish = async () => {
    try {
      const { data } = await api.post(`/importer/jobs/${job.id}/publish`);
      toast.success(`Pubblicato: +${data.added} nuove, ${data.updated} aggiornate → v${data.new_version}`);
      setStep(4);
      setJob({ ...job, im_status: "published" });
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore publish");
    }
  };

  const rollback = async (jid) => {
    try {
      await api.post(`/importer/jobs/${jid}/rollback`);
      toast.success("Rollback eseguito");
      const j = await api.get("/importer/jobs?limit=20");
      setJobs(j.data.items || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore rollback");
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="pricelist-importer-page">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Importazione Listini</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Wizard XLS/CSV: max 25 MB, 100k righe, 30 fogli — preview 200 righe, rollback disponibile.
        </p>
      </div>

      {step === 1 && (
        <Card>
          <CardHeader><CardTitle>1. Upload file</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label>Tipo entità</Label>
                <Select value={entityType} onValueChange={setEntityType}>
                  <SelectTrigger data-testid="select-entity-type"><SelectValue/></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="profile">Profili</SelectItem>
                    <SelectItem value="reinforcement">Rinforzi</SelectItem>
                    <SelectItem value="glazing_bead">Fermavetri</SelectItem>
                    <SelectItem value="glass_type">Vetri</SelectItem>
                    <SelectItem value="hardware_kit">Ferramenta</SelectItem>
                    <SelectItem value="accessory">Accessori</SelectItem>
                    <SelectItem value="labor">Lavorazioni</SelectItem>
                    <SelectItem value="price_matrix">Matrici prezzi</SelectItem>
                    <SelectItem value="surcharge">Maggiorazioni</SelectItem>
                    <SelectItem value="min_billable">Minimi fatturabili</SelectItem>
                    <SelectItem value="component_association">Associazioni</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Listino target (destinazione)</Label>
                <Select value={targetPl} onValueChange={setTargetPl}>
                  <SelectTrigger data-testid="select-target-pricelist"><SelectValue placeholder="Scegli listino..."/></SelectTrigger>
                  <SelectContent>
                    {pricelists.map((p) => (
                      <SelectItem key={p.id} value={p.id}>{p.code} — {p.name} (v{p.version})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="md:col-span-2">
                <Label>File .csv / .xlsx / .xls</Label>
                <Input type="file" ref={fileRef} accept=".csv,.xls,.xlsx"
                        onChange={(e) => setFile(e.target.files?.[0])}
                        data-testid="input-file"/>
              </div>
            </div>
            <Button onClick={upload} disabled={!file || !targetPl} data-testid="btn-upload">Carica e analizza</Button>
          </CardContent>
        </Card>
      )}

      {step === 2 && job && (
        <Card>
          <CardHeader><CardTitle>2. Mapping colonne — file: {job.filename}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2 flex-wrap">
              <Badge>{job.total_rows} righe</Badge>
              <Badge variant="outline">{job.detected_headers?.length} colonne</Badge>
              <Badge variant="outline">{job.sheet_names?.join(", ")}</Badge>
            </div>
            <div className="grid gap-2">
              {(schema?.fields || []).map((f, i) => {
                const m = mappings.find(mm => mm.target_field === f.code);
                return (
                  <div key={f.code} className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center">
                    <div className="text-sm">
                      {f.label}
                      {f.required && <span className="text-destructive"> *</span>}
                    </div>
                    <Select value={m?.source_column || ""}
                             onValueChange={(v) => {
                               const others = mappings.filter(mm => mm.target_field !== f.code);
                               if (v && v !== "__none__") {
                                 setMappings([...others, {
                                   source_column: v, target_field: f.code,
                                   transform: f.transform, required: f.required,
                                 }]);
                               } else {
                                 setMappings(others);
                               }
                             }}>
                      <SelectTrigger data-testid={`map-${f.code}`}>
                        <SelectValue placeholder="-- non mappato --"/>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">-- non mappato --</SelectItem>
                        {(job.detected_headers || []).map(h => (
                          <SelectItem key={h} value={h}>{h}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <div className="text-xs text-muted-foreground">
                      {f.transform ? `transform: ${f.transform}` : ""}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-2">
              <Button onClick={applyMapping} data-testid="btn-apply-mapping">Applica mapping e valida</Button>
              <Button variant="outline" onClick={() => setStep(1)}>Indietro</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && job && (
        <Card>
          <CardHeader><CardTitle>3. Anteprima e validazione</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2 flex-wrap">
              <Badge>{job.total_rows} totali</Badge>
              <Badge variant="secondary">{job.valid_rows} validi</Badge>
              <Badge variant="destructive">{(job.validation_errors || []).filter(e => e.severity === "error").length} errori</Badge>
              <Badge variant="outline">{job.duplicate_count || 0} duplicati</Badge>
            </div>
            {job.validation_errors?.length > 0 && (
              <div className="max-h-32 overflow-auto text-xs bg-muted p-2 rounded">
                {job.validation_errors.slice(0, 20).map((e, i) => (
                  <div key={i} className={e.severity === "error" ? "text-destructive" : "text-yellow-600"}>
                    riga {e.row_index}: [{e.code}] {e.message}
                  </div>
                ))}
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  {(job.mappings || []).map(m => <TableHead key={m.target_field}>{m.target_field}</TableHead>)}
                </TableRow>
              </TableHeader>
              <TableBody>
                {(job.preview_sample || []).slice(0, 20).map((r, i) => (
                  <TableRow key={i} data-testid={`preview-row-${i}`}>
                    {(job.mappings || []).map(m => <TableCell key={m.target_field}>{String(r[m.target_field] ?? "")}</TableCell>)}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex gap-2">
              <Button onClick={publish} disabled={job.im_status !== "preview_ready"} data-testid="btn-publish">
                Pubblica su listino
              </Button>
              <Button variant="outline" onClick={() => setStep(2)}>Modifica mapping</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 4 && (
        <Card>
          <CardHeader><CardTitle className="text-green-600">Pubblicazione completata</CardTitle></CardHeader>
          <CardContent>
            <p>Le entries del file sono state fuse nel listino <b>{pricelists.find(p => p.id === targetPl)?.code}</b>.</p>
            <p className="text-sm text-muted-foreground mt-2">
              Rollback disponibile nella lista job in fondo alla pagina.
            </p>
            <Button className="mt-4" onClick={() => { setStep(1); setJob(null); setFile(null); }}>Nuova importazione</Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle>Storico importazioni</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data</TableHead>
                <TableHead>File</TableHead>
                <TableHead>Entità</TableHead>
                <TableHead>Righe</TableHead>
                <TableHead>Stato</TableHead>
                <TableHead>Azioni</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map(j => (
                <TableRow key={j.id} data-testid={`job-row-${j.id}`}>
                  <TableCell className="text-xs">{new Date(j.created_at).toLocaleString("it-IT")}</TableCell>
                  <TableCell className="text-xs">{j.filename}</TableCell>
                  <TableCell><Badge variant="outline">{j.entity_type}</Badge></TableCell>
                  <TableCell>{j.total_rows}</TableCell>
                  <TableCell><Badge>{j.im_status}</Badge></TableCell>
                  <TableCell>
                    {j.im_status === "published" && (
                      <Button size="sm" variant="destructive" onClick={() => rollback(j.id)}
                               data-testid={`btn-rollback-${j.id}`}>Rollback</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
