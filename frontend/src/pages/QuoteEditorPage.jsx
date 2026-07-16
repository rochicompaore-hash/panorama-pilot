import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, Plus, Trash, PaperPlaneTilt, ArrowsClockwise, FileText, Check, Sparkle } from "@phosphor-icons/react";
import { toast } from "sonner";
import { ConflictModal } from "@/components/app/ConflictModal";
import { ConfiguratorDialog } from "@/components/app/ConfiguratorDialog";
import { AutosaveIndicator } from "@/components/app/AutosaveIndicator";
import { useConflict, getVersion, withVersion, withForce } from "@/hooks/useConflict";
import { useAutosave } from "@/hooks/useAutosave";
import { Textarea } from "@/components/ui/textarea";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { FilePdf, Download, Eye, CaretDown, Link, Copy, XCircle } from "@phosphor-icons/react";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

const CATEGORY_LABELS = { window: "Serramento", shutter: "Persiana/Scuro", roller: "Tapparella", persian: "Persiana", screen: "Zanzariera", box: "Cassonetto", sill: "Davanzale", trim: "Coprifilo", accessory: "Accessorio", installation: "Posa", disposal: "Smaltimento", extra: "Extra" };

export default function QuoteEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { has } = useAuth();
  const qc = useQueryClient();
  const conflict = useConflict();
  const [cfgOpen, setCfgOpen] = React.useState(false);

  const { data: q } = useQuery({ queryKey: ["quote", id], queryFn: async () => (await api.get(`/quotes/${id}`)).data });
  const { data: history } = useQuery({ queryKey: ["quote-history", id], queryFn: async () => (await api.get(`/quotes/${id}/history`)).data });

  const reload = () => qc.invalidateQueries({ queryKey: ["quote", id] });
  const canForce = has("records.force_override");
  const canSeeCosts = has("quotes.view_costs") || has("quotes.view_margins");

  const wrapConflict = React.useCallback(
    async (fn, localData, extra = {}) => {
      try { return await fn(); }
      catch (e) {
        if (e.response?.status === 409) {
          const detail = e.response.data?.detail || {};
          conflict.open(detail, localData, {
            canForceOverride: canForce,
            allowForce: extra.allowForce !== false,
            onReload: reload,
            onForce: async (reason) => {
              try {
                await extra.onForce?.(reason);
                toast.success("Modifica forzata registrata");
                reload();
              } catch (err) {
                toast.error(formatApiError(err.response?.data?.detail) || err.message);
              }
            },
            onKeepCopy: extra.onKeepCopy,
          });
          return;
        }
        toast.error(formatApiError(e.response?.data?.detail) || e.message);
        throw e;
      }
    },
    [conflict, canForce, reload]
  );

  const editable = q ? !["accepted", "converted", "superseded", "rejected", "cancelled", "expired", "sent", "signed"].includes(q.quote_status) : false;

  // ---- Autosave for editable header/notes fields (M3.3.1) ----
  const autosave = useAutosave({
    endpoint: `/quotes/${id}/autosave`,
    enabled: editable,
    getVersion: () => (q ? q.version : 1),
    onSuccess: () => {
      // Bump cached version without full refetch to avoid overwriting user edits
      qc.setQueryData(["quote", id], (old) => old ? { ...old, version: (old.version || 1) + 1 } : old);
    },
    onConflict: (detail, fields) => {
      conflict.open(detail, fields, {
        canForceOverride: canForce,
        allowForce: true,
        onReload: reload,
        onForce: async (reason) => {
          // Send fields as force override PATCH
          await api.patch(`/quotes/${id}`, fields, { ...withVersion(getVersion(q)), ...withForce(reason) });
          reload();
        },
      });
    },
  });

  const addOpening = useMutation({
    mutationFn: async (p) => (await api.post(`/quotes/${id}/openings`, p, withVersion(getVersion(q)))).data,
    onSuccess: () => { toast.success("Vano aggiunto"); reload(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const addLine = useMutation({
    mutationFn: async (p) => (await api.post(`/quotes/${id}/lines`, p, withVersion(getVersion(q)))).data,
    onSuccess: () => { toast.success("Riga aggiunta"); reload(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const delLine = useMutation({
    mutationFn: async (lid) => (await api.delete(`/quotes/${id}/lines/${lid}`)).data,
    onSuccess: () => { toast.success("Riga eliminata"); reload(); },
  });
  const changeStatus = useMutation({
    mutationFn: async (new_status) => (await api.post(`/quotes/${id}/status`, { new_status })).data,
    onSuccess: () => { toast.success("Stato aggiornato"); reload(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const revise = useMutation({
    mutationFn: async () => (await api.post(`/quotes/${id}/revise`)).data,
    onSuccess: (d) => { toast.success(`Revisione ${d.revision_label} creata`); navigate(`/quotes/${d.id}`); },
  });
  const convert = useMutation({
    mutationFn: async () => (await api.post(`/quotes/${id}/convert-to-contract`)).data,
    onSuccess: (d) => { toast.success(`Contratto ${d.number} generato`); navigate(`/contracts/${d.id}`); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  // PDF actions (M3.3.2)
  const { data: pdfsResp } = useQuery({
    queryKey: ["quote-pdfs", id],
    queryFn: async () => (await api.get(`/quotes/${id}/pdfs`)).data,
    enabled: !!q,
  });
  const pdfs = pdfsResp?.items || [];
  const latestDef = pdfs.find((p) => p.kind === "definitive" && !p.invalidated_at);
  const previewPdf = useMutation({
    mutationFn: async () => (await api.post(`/quotes/${id}/pdf/preview`, {})).data,
    onSuccess: async (d) => {
      toast.success("Anteprima BOZZA generata");
      window.open(`${api.defaults.baseURL}/quote-pdfs/${d.id}/download`, "_blank");
      qc.invalidateQueries({ queryKey: ["quote-pdfs", id] });
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const generatePdf = useMutation({
    mutationFn: async (opts = {}) => (await api.post(`/quotes/${id}/pdf/generate`, opts)).data,
    onSuccess: (d) => {
      if (d.idempotent_hit) toast.info("Nessuna modifica: rigenerazione idempotente"); else toast.success("PDF definitivo emesso");
      qc.invalidateQueries({ queryKey: ["quote-pdfs", id] });
      qc.invalidateQueries({ queryKey: ["quote", id] });
    },
    onError: (e) => {
      const err = e.response?.data?.detail;
      if (err && typeof err === "object" && err.errors) {
        toast.error(`Validazione fallita:\n${err.errors.map((x) => "• " + x.message).join("\n")}`, { duration: 8000 });
      } else {
        toast.error(formatApiError(err) || e.message);
      }
    },
  });
  const downloadPdf = (pid, filename) => {
    // Download via authenticated axios stream
    api.get(`/quote-pdfs/${pid}/download`, { responseType: "blob" }).then((res) => {
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url; a.download = filename || "preventivo.pdf"; document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    });
  };

  // Public link (M3.3.3)
  const [publicLinkOpen, setPublicLinkOpen] = React.useState(false);
  const { data: linksResp } = useQuery({
    queryKey: ["public-links", id],
    queryFn: async () => (await api.get(`/quotes/${id}/public-links`)).data,
    enabled: !!q && has("quotes.public_link.view"),
  });
  const links = linksResp?.items || [];
  const activeLink = links.find((l) => l.status === "active");
  const [freshRawToken, setFreshRawToken] = React.useState(null);
  const createLink = useMutation({
    mutationFn: async (opts = {}) => (await api.post(`/quotes/${id}/public-links`, { validity_days: 30, ...opts })).data,
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["public-links", id] });
      if (d.raw_token) {
        setFreshRawToken(d.raw_token);
        toast.success("Link pubblico creato — copia ora il token, non sarà più visibile");
      } else if (d.idempotent_hit) {
        toast.info("Link attivo già esistente. Usa 'Rigenera' per un nuovo token.");
      }
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });
  const revokeLink = useMutation({
    mutationFn: async ({ lid, reason }) => (await api.post(`/quotes/${id}/public-links/${lid}/revoke`, { reason })).data,
    onSuccess: () => { toast.success("Link revocato"); qc.invalidateQueries({ queryKey: ["public-links", id] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });
  const regenerateLink = useMutation({
    mutationFn: async () => (await api.post(`/quotes/${id}/public-links/regenerate`, { validity_days: 30 })).data,
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["public-links", id] });
      if (d.raw_token) { setFreshRawToken(d.raw_token); toast.success("Nuovo token generato"); }
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });
  const copyPortalUrl = (raw) => {
    const url = `${window.location.origin}/p/${raw}`;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url)
        .then(() => toast.success("Link copiato negli appunti"))
        .catch(() => toast.error("Copia manuale: la clipboard non è disponibile in questo contesto"));
    } else {
      toast.error("Copia manuale: la clipboard non è disponibile in questo contesto");
    }
  };

  if (!q) return <div className="text-sm text-muted-foreground">Caricamento…</div>;

  const allowForce = editable;

  const updateLine = async (lid, patch) => {
    await wrapConflict(
      async () => {
        const res = await api.patch(`/quotes/${id}/lines/${lid}`, patch, withVersion(getVersion(q)));
        reload();
        return res.data;
      },
      patch,
      {
        allowForce,
        onForce: async (reason) => {
          await api.patch(`/quotes/${id}/lines/${lid}`, patch, { ...withVersion(getVersion(q)), ...withForce(reason) });
        },
      }
    );
  };

  const onConfiguratorConfirm = async (payload) => {
    await addLine.mutateAsync(payload);
    setCfgOpen(false);
  };

  return (
    <div className="space-y-6" data-testid="quote-editor-page">
      <Button variant="ghost" size="sm" className="rounded-sm" onClick={() => navigate("/quotes")}><ArrowLeft size={14} className="mr-1" /> Torna a Preventivi</Button>

      <div className="flex items-end justify-between">
        <div>
          <div className="overline font-mono-plex">{q.number}</div>
          {editable ? (
            <Input
              defaultValue={q.title || ""}
              placeholder="Titolo preventivo"
              onChange={(e) => autosave.schedule({ title: e.target.value })}
              className="mt-1 font-display text-3xl font-black tracking-tight border-0 border-b border-transparent hover:border-border focus:border-primary rounded-none px-0 h-auto bg-transparent"
              data-testid="quote-title-input"
            />
          ) : (
            <h1 className="mt-1 font-display text-3xl font-black tracking-tight">{q.title || "Preventivo"}</h1>
          )}
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="rounded-sm uppercase">{q.quote_status}</Badge>
            <Badge variant="outline" className="rounded-sm">{q.revision_label}</Badge>
            <Badge variant="outline" className="rounded-sm font-mono-plex text-[10px]" data-testid="quote-version">v.{q.version || 1}</Badge>
            {q.approval?.status === "pending" && <Badge className="rounded-sm bg-orange-500">Approvazione pendente</Badge>}
            {editable && <AutosaveIndicator state={autosave.state} lastSavedAt={autosave.lastSavedAt} lastError={autosave.lastError} onRetry={autosave.retry} />}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {editable && has("quotes.send") && q.quote_status === "draft" && <Button variant="outline" className="rounded-sm" onClick={async () => { await autosave.flushNow(); changeStatus.mutate("sent"); }} data-testid="quote-send"><PaperPlaneTilt size={14} className="mr-1" /> Invia</Button>}
          {q.quote_status === "sent" && <Button variant="outline" className="rounded-sm" onClick={() => changeStatus.mutate("accepted")} data-testid="quote-accept"><Check size={14} className="mr-1" /> Accettato</Button>}
          {["accepted", "approved"].includes(q.quote_status) && !q.contract_id && has("quotes.convert_contract") && <Button className="rounded-sm bg-emerald-600 hover:bg-emerald-700" onClick={async () => { await autosave.flushNow(); convert.mutate(); }} data-testid="quote-convert"><FileText size={14} className="mr-1" /> Genera contratto</Button>}
          {editable && q.is_current && <Button variant="outline" className="rounded-sm" onClick={async () => { await autosave.flushNow(); revise.mutate(); }} data-testid="quote-revise"><ArrowsClockwise size={14} className="mr-1" /> Nuova revisione</Button>}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button className="rounded-sm bg-[hsl(var(--brand-red))] hover:bg-[hsl(var(--brand-red))]/90 text-white" data-testid="pdf-menu"><FilePdf size={14} className="mr-1" /> PDF <CaretDown size={12} className="ml-1" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="rounded-sm">
              {has("quotes.preview_pdf") && <DropdownMenuItem onClick={async () => { await autosave.flushNow(); previewPdf.mutate(); }} data-testid="pdf-preview"><Eye size={14} className="mr-2" /> Anteprima BOZZA</DropdownMenuItem>}
              {has("quotes.generate_pdf") && editable && <DropdownMenuItem onClick={async () => { await autosave.flushNow(); generatePdf.mutate({}); }} data-testid="pdf-generate"><FilePdf size={14} className="mr-2" /> Emetti PDF definitivo</DropdownMenuItem>}
              {latestDef && <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => downloadPdf(latestDef.id, latestDef.filename)} data-testid="pdf-download"><Download size={14} className="mr-2" /> Scarica ultimo definitivo</DropdownMenuItem>
                {has("quotes.public_link.view") && <DropdownMenuItem onClick={() => setPublicLinkOpen(true)} data-testid="public-link-open"><Link size={14} className="mr-2" /> Link pubblico</DropdownMenuItem>}
              </>}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <Card className="rounded-sm border-border p-4" data-testid="quote-details-card">
            <div className="flex items-center justify-between mb-3">
              <div className="overline">Dettagli commerciali</div>
              <span className="text-[10px] font-mono-plex text-muted-foreground">Autosalvataggio ogni 800ms</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="col-span-2">
                <Label className="text-xs">Note visibili in preventivo</Label>
                <Textarea
                  defaultValue={q.notes || ""}
                  rows={2}
                  disabled={!editable}
                  onChange={(e) => autosave.schedule({ notes: e.target.value })}
                  className="rounded-sm"
                  data-testid="quote-notes-input"
                />
              </div>
              <div>
                <Label className="text-xs">Termini di pagamento</Label>
                <Input
                  defaultValue={q.payment_terms || ""}
                  disabled={!editable}
                  onChange={(e) => autosave.schedule({ payment_terms: e.target.value })}
                  placeholder="Es. 30% acconto, 70% a saldo"
                  className="rounded-sm h-9"
                  data-testid="quote-payment-input"
                />
              </div>
              <div>
                <Label className="text-xs">Tempi di consegna (giorni)</Label>
                <Input
                  type="number" defaultValue={q.delivery_days ?? ""}
                  disabled={!editable}
                  onChange={(e) => autosave.schedule({ delivery_days: Number(e.target.value) || null })}
                  className="rounded-sm h-9 font-mono-plex"
                  data-testid="quote-delivery-input"
                />
              </div>
              <div>
                <Label className="text-xs">Garanzia (mesi)</Label>
                <Input
                  type="number" defaultValue={q.warranty_months ?? ""}
                  disabled={!editable}
                  onChange={(e) => autosave.schedule({ warranty_months: Number(e.target.value) || null })}
                  className="rounded-sm h-9 font-mono-plex"
                  data-testid="quote-warranty-input"
                />
              </div>
              <div>
                <Label className="text-xs">Valido fino al</Label>
                <Input
                  type="date"
                  defaultValue={q.valid_until ? q.valid_until.slice(0, 10) : ""}
                  disabled={!editable}
                  onChange={(e) => autosave.schedule({ valid_until: e.target.value || null })}
                  className="rounded-sm h-9 font-mono-plex"
                  data-testid="quote-valid-input"
                />
              </div>
              {(has("quotes.view_internal") || has("quotes.view_margins")) && (
                <div className="col-span-2">
                  <Label className="text-xs">Note interne (non visibili al cliente)</Label>
                  <Textarea
                    defaultValue={q.internal_notes || ""}
                    rows={2}
                    disabled={!editable}
                    onChange={(e) => autosave.schedule({ internal_notes: e.target.value })}
                    className="rounded-sm bg-amber-50/40 dark:bg-amber-950/10"
                    data-testid="quote-internal-notes-input"
                  />
                </div>
              )}
            </div>
          </Card>

          {/* Openings */}
          <Card className="rounded-sm border-border p-4" data-testid="openings-card">
            <div className="flex items-center justify-between mb-3">
              <div className="overline">Vani finestra ({(q.openings || []).length})</div>
              {editable && <Button size="sm" variant="outline" className="rounded-sm" onClick={() => addOpening.mutate({ code: `V${(q.openings || []).length + 1}`, description: "" })} data-testid="add-opening"><Plus size={12} className="mr-1" /> Vano</Button>}
            </div>
            <div className="space-y-2">
              {(q.openings || []).map((o) => (
                <OpeningRow key={o.id} quoteId={id} opening={o} editable={editable} parentVersion={getVersion(q)} onConflict={wrapConflict} canForce={canForce} />
              ))}
            </div>
          </Card>

          {/* Lines */}
          <Card className="rounded-sm border-border p-4" data-testid="lines-card">
            <div className="flex items-center justify-between mb-3">
              <div className="overline">Righe ({(q.lines || []).length})</div>
              {editable && (
                <div className="flex gap-2">
                  <Button size="sm" className="rounded-sm" onClick={() => setCfgOpen(true)} data-testid="cfg-open"><Sparkle size={12} className="mr-1" /> Configuratore</Button>
                </div>
              )}
            </div>
            <Table>
              <TableHeader><TableRow>
                <TableHead className="overline">Descrizione</TableHead>
                <TableHead className="overline">Q.tà</TableHead>
                <TableHead className="overline">Prezzo</TableHead>
                <TableHead className="overline">Sconto</TableHead>
                <TableHead className="overline">Subtotale</TableHead>
                <TableHead></TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {(q.lines || []).map((l) => (
                  <TableRow key={l.id} data-testid={`line-row-${l.id}`}>
                    <TableCell>
                      <Badge variant="outline" className="rounded-sm text-[10px] mr-2">{CATEGORY_LABELS[l.category] || l.category}</Badge>
                      <span className="text-sm">{l.description || "—"}</span>
                      {(l.width_mm || l.height_mm) ? <div className="text-[10px] font-mono-plex text-muted-foreground">{l.width_mm}×{l.height_mm} mm</div> : null}
                    </TableCell>
                    <TableCell className="font-mono-plex text-xs">{l.quantity}</TableCell>
                    <TableCell className="font-mono-plex text-xs">{fmtEUR(l.unit_price_final || l.base_price)}</TableCell>
                    <TableCell>
                      {editable ? (
                        <Input type="number" step="0.5" defaultValue={l.discount_pct} onBlur={(e) => { const v = Number(e.target.value); if (v !== l.discount_pct) updateLine(l.id, { discount_pct: v }); }} className="rounded-sm h-8 w-16 text-xs font-mono-plex" data-testid={`line-discount-${l.id}`} />
                      ) : `${l.discount_pct}%`}
                    </TableCell>
                    <TableCell className="font-mono-plex text-xs font-bold">{fmtEUR(l.subtotal_line)}</TableCell>
                    <TableCell>{editable && <Button variant="ghost" size="sm" onClick={() => delLine.mutate(l.id)} className="text-destructive" data-testid={`line-delete-${l.id}`}><Trash size={12} /></Button>}</TableCell>
                  </TableRow>
                ))}
                {(q.lines || []).length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-6 text-sm text-muted-foreground">Nessuna riga. Usa il <b>Configuratore</b> per aggiungere prodotti.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="rounded-sm border-border p-6" data-testid="totals-card">
            <div className="overline mb-4">Totali</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-muted-foreground">Imponibile</span><span className="font-mono-plex">{fmtEUR(q.subtotal)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">IVA</span><span className="font-mono-plex">{fmtEUR(q.vat_amount)}</span></div>
              <div className="flex justify-between pt-2 border-t"><span className="font-bold">Totale</span><span className="font-mono-plex text-lg font-black">{fmtEUR(q.total)}</span></div>
              {canSeeCosts && q.margin_abs != null && (
                <div className="mt-4 pt-3 border-t border-dashed">
                  <div className="text-[10px] font-mono-plex text-muted-foreground uppercase">Riservato</div>
                  <div className="flex justify-between mt-1"><span className="text-muted-foreground text-xs">Costo interno</span><span className="font-mono-plex text-xs">{fmtEUR(q.internal_cost)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground text-xs">Margine</span><span className="font-mono-plex text-xs text-[hsl(var(--brand-red))]">{fmtEUR(q.margin_abs)} ({q.margin_pct}%)</span></div>
                </div>
              )}
            </div>
          </Card>

          <Card className="rounded-sm border-border p-6" data-testid="revisions-card">
            <div className="overline mb-3">Revisioni</div>
            <div className="space-y-1">
              {(history?.items || []).map((h) => (
                <div key={h.id} className={`flex items-center justify-between py-1 text-xs ${h.id === id ? "font-bold" : ""}`}>
                  <span className="font-mono-plex">{h.number}</span>
                  <span className="text-muted-foreground uppercase">{h.quote_status}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card className="rounded-sm border-border p-6" data-testid="pdf-history-card">
            <div className="overline mb-3">PDF emessi ({pdfs.length})</div>
            {pdfs.length === 0 ? (
              <div className="text-xs text-muted-foreground">Nessun PDF ancora generato. Usa il pulsante PDF in alto per anteprima o emissione definitiva.</div>
            ) : (
              <div className="space-y-2">
                {pdfs.slice(0, 5).map((p) => (
                  <div key={p.id} className="flex items-center gap-2 py-1 border-b last:border-b-0 text-[11px]">
                    <Badge variant="outline" className={`rounded-sm text-[9px] ${p.kind === 'definitive' ? 'bg-emerald-500/10 text-emerald-800' : p.kind === 'preview' ? 'bg-amber-500/10 text-amber-800' : 'bg-red-500/10 text-red-800'}`}>{p.kind.toUpperCase()}</Badge>
                    <div className="flex-1 min-w-0 truncate font-mono-plex" title={p.filename}>{p.filename}</div>
                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => downloadPdf(p.id, p.filename)} data-testid={`pdf-hist-dl-${p.id}`}><Download size={12} /></Button>
                  </div>
                ))}
                {pdfs.length > 0 && (
                  <div className="mt-2 pt-2 border-t text-[10px] font-mono-plex text-muted-foreground">
                    Hash snapshot: {(latestDef?.snapshot_hash || pdfs[0].snapshot_hash || "").slice(0, 12)}…
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>

      <ConfiguratorDialog open={cfgOpen} onOpenChange={setCfgOpen} onConfirm={onConfiguratorConfirm} canSeeCosts={canSeeCosts} />
      <ConflictModal {...conflict.modalProps} />

      <PublicLinkDialog
        open={publicLinkOpen}
        onOpenChange={(v) => { setPublicLinkOpen(v); if (!v) setFreshRawToken(null); }}
        links={links}
        activeLink={activeLink}
        freshRawToken={freshRawToken}
        canCreate={has("quotes.public_link.create") && !!latestDef}
        canRevoke={has("quotes.public_link.revoke")}
        canRegenerate={has("quotes.public_link.regenerate")}
        onCreate={() => createLink.mutate({})}
        onRegenerate={() => regenerateLink.mutate()}
        onRevoke={(lid) => {
          const reason = prompt("Motivazione per la revoca");
          if (reason && reason.trim()) revokeLink.mutate({ lid, reason });
        }}
        onCopy={copyPortalUrl}
      />
    </div>
  );
}

function PublicLinkDialog({ open, onOpenChange, links, activeLink, freshRawToken, canCreate, canRevoke, canRegenerate, onCreate, onRegenerate, onRevoke, onCopy }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-sm" data-testid="public-link-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Link size={18} /> Link pubblico preventivo</DialogTitle>
          <DialogDescription>Il cliente può consultare il preventivo e scaricare il PDF senza creare un account. Il link scade dopo 30 giorni ed è revocabile in ogni momento.</DialogDescription>
        </DialogHeader>

        {freshRawToken && (
          <div className="rounded-sm border border-emerald-500/40 bg-emerald-500/5 p-3" data-testid="fresh-token-panel">
            <div className="text-xs overline mb-1 text-emerald-700">Nuovo token — copia ora, non sarà più visibile</div>
            <div className="flex gap-2">
              <Input readOnly value={`${window.location.origin}/p/${freshRawToken}`} className="rounded-sm font-mono-plex text-xs" data-testid="fresh-token-url" />
              <Button size="sm" className="rounded-sm" onClick={() => onCopy(freshRawToken)} data-testid="fresh-token-copy"><Copy size={12} className="mr-1" /> Copia</Button>
            </div>
          </div>
        )}

        {activeLink ? (
          <Card className="rounded-sm border-border p-4">
            <div className="flex items-center justify-between mb-2">
              <Badge className="rounded-sm bg-emerald-500">ATTIVO</Badge>
              <div className="text-xs font-mono-plex text-muted-foreground">Scade: {activeLink.expires_at ? new Date(activeLink.expires_at).toLocaleDateString("it-IT") : "—"}</div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div><div className="overline">Accessi</div><div className="font-mono-plex font-bold">{activeLink.access_count || 0}</div></div>
              <div><div className="overline">Ultimo</div><div className="font-mono-plex text-xs">{activeLink.last_access_at ? new Date(activeLink.last_access_at).toLocaleString("it-IT") : "Mai"}</div></div>
              <div><div className="overline">Azioni</div><div className="text-xs">{(activeLink.allowed_actions || []).join(", ")}</div></div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {canRegenerate && <Button size="sm" variant="outline" className="rounded-sm" onClick={onRegenerate} data-testid="regenerate-link"><ArrowsClockwise size={12} className="mr-1" /> Rigenera token</Button>}
              {canRevoke && <Button size="sm" variant="destructive" className="rounded-sm" onClick={() => onRevoke(activeLink.id)} data-testid="revoke-link"><XCircle size={12} className="mr-1" /> Revoca</Button>}
            </div>
            <div className="mt-3 text-[10px] text-muted-foreground">Nota: per motivi di sicurezza il token non è consultabile dopo la creazione. Rigenera per ottenerne uno nuovo.</div>
          </Card>
        ) : (
          canCreate ? (
            <Button size="lg" className="rounded-sm w-full" onClick={onCreate} data-testid="create-public-link"><Link size={16} className="mr-2" /> Crea link pubblico (30 giorni)</Button>
          ) : (
            <div className="text-sm text-muted-foreground">
              Emetti un PDF definitivo prima di generare il link pubblico.
            </div>
          )
        )}

        {links.filter((l) => l.status !== "active").length > 0 && (
          <div className="mt-4">
            <div className="overline mb-2">Storico ({links.filter((l) => l.status !== "active").length})</div>
            <div className="space-y-1 max-h-40 overflow-auto">
              {links.filter((l) => l.status !== "active").map((l) => (
                <div key={l.id} className="flex items-center justify-between text-xs py-1 border-b">
                  <Badge variant="outline" className="rounded-sm text-[10px] uppercase">{l.status}</Badge>
                  <span className="font-mono-plex text-muted-foreground">{l.revoked_at ? new Date(l.revoked_at).toLocaleDateString("it-IT") : ""}</span>
                  <span className="text-[10px] truncate max-w-[200px]" title={l.revocation_reason}>{l.revocation_reason || ""}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function OpeningRow({ quoteId, opening, editable, parentVersion, onConflict, canForce }) {
  const qc = useQueryClient();
  const [w, setW] = useState(opening.width_mm || "");
  const [h, setH] = useState(opening.height_mm || "");
  const patch = async (payload) => {
    await onConflict(
      async () => (await api.patch(`/quotes/${quoteId}/openings/${opening.id}`, payload, withVersion(parentVersion))).data,
      payload,
      {
        allowForce: editable,
        onForce: async (reason) => {
          await api.patch(`/quotes/${quoteId}/openings/${opening.id}`, payload, { ...withVersion(parentVersion), ...withForce(reason) });
        },
      }
    );
    qc.invalidateQueries({ queryKey: ["quote", quoteId] });
  };
  const del = useMutation({ mutationFn: async () => (await api.delete(`/quotes/${quoteId}/openings/${opening.id}`)).data, onSuccess: () => { toast.success("Vano eliminato"); qc.invalidateQueries({ queryKey: ["quote", quoteId] }); } });
  return (
    <div className="flex items-center gap-3 py-2 border-b last:border-b-0" data-testid={`opening-row-${opening.id}`}>
      <Badge variant="outline" className="rounded-sm font-mono-plex">{opening.code}</Badge>
      <Input placeholder="Stanza / descrizione" defaultValue={opening.description || ""} onBlur={(e) => patch({ description: e.target.value })} className="rounded-sm h-8 text-sm flex-1" disabled={!editable} data-testid={`opening-desc-${opening.id}`} />
      <Input type="number" placeholder="L (mm)" value={w} onChange={(e) => setW(e.target.value)} onBlur={() => patch({ width_mm: Number(w) || null })} className="rounded-sm h-8 w-24 text-xs font-mono-plex" disabled={!editable} data-testid={`opening-w-${opening.id}`} />
      <Input type="number" placeholder="H (mm)" value={h} onChange={(e) => setH(e.target.value)} onBlur={() => patch({ height_mm: Number(h) || null })} className="rounded-sm h-8 w-24 text-xs font-mono-plex" disabled={!editable} data-testid={`opening-h-${opening.id}`} />
      {editable && <Button variant="ghost" size="sm" onClick={() => del.mutate()} className="text-destructive"><Trash size={12} /></Button>}
    </div>
  );
}
