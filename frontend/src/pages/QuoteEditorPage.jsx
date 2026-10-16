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
import { MultiCategoryConfiguratorDialog } from "@/components/app/MultiCategoryConfiguratorDialog";
import { ProductVisualThumb } from "@/components/app/ProductVisualSVG";
import { MarginTachometer } from "@/components/app/MarginTachometer";
import { CommissionTachometer } from "@/components/app/CommissionTachometer";
import { AutosaveIndicator } from "@/components/app/AutosaveIndicator";
import { useConflict, getVersion, withVersion, withForce } from "@/hooks/useConflict";
import { useAutosave } from "@/hooks/useAutosave";
import { Textarea } from "@/components/ui/textarea";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { FilePdf, Download, Eye, CaretDown, Link, Copy, XCircle } from "@phosphor-icons/react";
import { CompetitorAnalyzerCard } from "@/components/quotes/CompetitorAnalyzerCard";
import { QuoteEmailDialog, QuoteEmailHistory } from "@/components/quotes/QuoteEmailDialog";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0); } catch { return "€ 0,00"; } }
function fmtPct(n) { return typeof n === "number" ? `${n.toFixed(2).replace(".", ",")} %` : "—"; }

const PAYMENT_TERMS_OPTIONS = [
  ["DEPOSIT_50_BALANCE_50", "50% acconto all'ordine · 50% avviso merce pronta"],
  ["FULL_UPFRONT", "100% all'ordine (sconto automatico 5%)"],
  ["DEPOSIT_30_SURVEY_20_BALANCE_50", "30% ordine · 20% dopo rilievo · 50% merce pronta"],
  ["FINANCING_WITHOUT_DEPOSIT", "Finanziamento senza acconto"],
  ["FINANCING_WITH_DEPOSIT", "Finanziamento con acconto"],
];
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
  // Margin Engine V1 — Tachimetro live: dedicated endpoint applies RBAC redaction backend-side.
  const { data: financial } = useQuery({
    queryKey: ["quote-financial", id, q?.version],
    queryFn: async () => (await api.get(`/quotes/${id}/financial-snapshot`)).data,
    enabled: !!q,
    refetchOnWindowFocus: false,
  });

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

  const [editLine, setEditLine] = React.useState(null);
  const reconfigureLine = useMutation({
    mutationFn: async ({ line_id, ...p }) => (await api.put(`/quotes/${id}/lines/${line_id}/reconfigure`, p)).data,
    onSuccess: () => { toast.success("Riga aggiornata e ricalcolata"); reload(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const [discountPct, setDiscountPct] = React.useState(0);
  const maxCommercialStep = financial?.financial_snapshot?.max_commercial_discount_step_percent ?? null;
  const isAdminMaster = !!financial?.is_admin_master_view;
  const maxAdminStep = financial?.financial_snapshot?.max_admin_discount_step_percent ?? null;
  const adminHardCap = financial?.financial_snapshot?.admin_master_max_discount_percent ?? 40;
  const dropdownMax = isAdminMaster ? adminHardCap : 30;
  const maxAllowedStep = isAdminMaster ? maxAdminStep : maxCommercialStep;
  const [emailOpen, setEmailOpen] = React.useState(false);
  const { data: vatOptions } = useQuery({ queryKey: ["vat-options"], queryFn: async () => (await api.get(`/quotes/vat-options`)).data, staleTime: 600000 });
  const patchFiscal = useMutation({
    mutationFn: async (fields) => (await api.patch(`/quotes/${id}/fiscal-dossier`, fields)).data,
    onSuccess: (d) => { toast.success(`Regime IVA: ${vatOptions?.labels?.[d.vat_regime] || d.vat_regime}`); reload(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const [promoInput, setPromoInput] = React.useState("");
  React.useEffect(() => { if (q) { setDiscountPct(q.global_discount_source === "MANUAL" ? q.global_discount_value || 0 : 0); setPromoInput(q.promo_code || ""); } }, [q?.global_discount_value, q?.promo_code, q?.global_discount_source]); // eslint-disable-line react-hooks/exhaustive-deps
  const patchQuote = useMutation({
    mutationFn: async (fields) => (await api.patch(`/quotes/${id}`, fields)).data,
    onSuccess: () => { toast.success("Preventivo aggiornato e ricalcolato"); reload(); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
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
    if (payload.line_id) await reconfigureLine.mutateAsync(payload);
    else await addLine.mutateAsync(payload);
    setCfgOpen(false);
    setEditLine(null);
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
          {has("quotes.send") && !["accepted", "converted", "superseded", "rejected", "cancelled", "expired", "signed"].includes(q.quote_status) && <Button className="rounded-sm" onClick={async () => { await autosave.flushNow(); setEmailOpen(true); }} data-testid="quote-send-email"><PaperPlaneTilt size={14} className="mr-1" /> Invia via email</Button>}
          {editable && has("quotes.send") && q.quote_status === "draft" && <Button variant="outline" className="rounded-sm" onClick={async () => { await autosave.flushNow(); changeStatus.mutate("sent"); }} data-testid="quote-send"><Check size={14} className="mr-1" /> Segna come inviato (senza email)</Button>}
          {q.quote_status === "sent" && <Button variant="outline" className="rounded-sm" onClick={() => changeStatus.mutate("accepted")} data-testid="quote-accept"><Check size={14} className="mr-1" /> Accettato</Button>}
          {["accepted", "approved"].includes(q.quote_status) && !q.contract_id && has("quotes.convert_contract") && <Button className="rounded-sm bg-emerald-600 hover:bg-emerald-700" onClick={async () => { await autosave.flushNow(); convert.mutate(); }} data-testid="quote-convert"><FileText size={14} className="mr-1" /> Genera contratto</Button>}
          {["accepted", "approved", "converted"].includes(q.quote_status) && q.contract_id && <Button className="rounded-sm" variant="outline" onClick={() => navigate(`/contracts/${q.contract_id}`)} data-testid="quote-open-contract"><FileText size={14} className="mr-1" /> Apri contratto</Button>}
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
          {/* --- Installation Mode V1 (msg 393) --- */}
          <InstallationModeCard q={q} editable={editable} onChange={reload} />

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
                <Select value={q.payment_terms_code || q.payment_terms || "DEPOSIT_50_BALANCE_50"} disabled={!editable} onValueChange={(v) => patchQuote.mutate({ payment_terms: v })}>
                  <SelectTrigger className="rounded-sm h-9" data-testid="quote-payment-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {PAYMENT_TERMS_OPTIONS.map(([v, l]) => <SelectItem key={v} value={v} data-testid={`payment-opt-${v}`}>{l}</SelectItem>)}
                  </SelectContent>
                </Select>
                {(q.payment_schedule || []).length > 0 && (
                  <div className="mt-1 text-[10px] font-mono-plex text-muted-foreground" data-testid="quote-payment-schedule">
                    {q.payment_schedule.map((s, i) => <span key={i} className="mr-2">{s.percent != null ? `${s.percent}% ` : ""}{s.label}</span>)}
                  </div>
                )}
                <div className="mt-2">
                  <Label className="text-[10px] uppercase">Consegna</Label>
                  <Select value={q.delivery_mode || "STANDARD"} disabled={!editable} onValueChange={(v) => patchQuote.mutate({ delivery_mode: v })}>
                    <SelectTrigger className="rounded-sm h-9" data-testid="quote-delivery-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="STANDARD" data-testid="delivery-opt-STANDARD">Standard — in base alla configurazione (60/90 giorni)</SelectItem>
                      <SelectItem value="EXPRESS" disabled data-testid="delivery-opt-EXPRESS">Accelerata (+20%) — non disponibile: tempistica da definire (PO)</SelectItem>
                    </SelectContent>
                  </Select>
                  {(q.delivery_mode || "STANDARD") === "STANDARD" && <div className="mt-1" data-testid="quote-lead-time"><span className="text-[10px] uppercase text-muted-foreground">Tempi di consegna</span> <b className="text-sm" data-testid="quote-lead-time-days">{q.delivery_lead_time_days ? `ENTRO ${q.delivery_lead_time_days} GIORNI` : "da definire (nessun colore configurato)"}</b>{q.delivery_lead_time_mixed && <div className="text-[10px] text-amber-700" data-testid="quote-lead-time-mixed">Tempo commessa determinato dalla configurazione con lead time maggiore.</div>}</div>}
                  {q.delivery_customer_text && <div className="mt-1 text-[10px] text-muted-foreground" data-testid="quote-delivery-text">{q.delivery_customer_text}</div>}
                  {Number(q.delivery_surcharge_amount) > 0 && <div className="mt-1 text-xs font-bold text-amber-700" data-testid="quote-delivery-surcharge">Maggiorazione consegna accelerata +{q.delivery_surcharge_percent}% = {fmtEUR(q.delivery_surcharge_amount)}</div>}
                </div>
                <div className="mt-3 border border-border rounded-sm p-3 space-y-2" data-testid="quote-discount-section">
                  <Label className="text-[10px] uppercase font-bold">Sconto / Codice promo (intero preventivo)</Label>
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <Label className="text-[10px] uppercase">Sconto % (max consentito {maxAllowedStep ?? "—"}%{isAdminMaster ? ` · Admin Master fino a ${adminHardCap}%` : ""})</Label>
                      <Select disabled={!editable} value={String(Math.round(Number(discountPct) || 0))} onValueChange={(v) => setDiscountPct(Number(v))}>
                        <SelectTrigger className="rounded-sm h-9" data-testid="quote-discount-pct-select"><SelectValue /></SelectTrigger>
                        <SelectContent className="max-h-64">
                          {Array.from({ length: dropdownMax + 1 }, (_, i) => i).map((i) => (
                            <SelectItem key={i} value={String(i)} disabled={maxAllowedStep != null && i > maxAllowedStep} data-testid={`discount-opt-${i}`}>
                              {i}%{maxAllowedStep != null && i > maxAllowedStep ? " — non consentito (margine minimo)" : (i > 30 ? " — autorizzazione Admin Master" : "")}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button type="button" size="sm" variant="outline" className="rounded-sm h-9" disabled={!editable} onClick={() => patchQuote.mutate({ global_discount_percent: Number(discountPct || 0) })} data-testid="quote-discount-apply-btn">Applica</Button>
                  </div>
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <Label className="text-[10px] uppercase">Codice sconto</Label>
                      <Input disabled={!editable} value={promoInput} onChange={(e) => setPromoInput(e.target.value.toUpperCase())} placeholder="es. PROMO10" className="rounded-sm h-9 font-mono-plex" data-testid="quote-promo-input" />
                    </div>
                    <Button type="button" size="sm" className="rounded-sm h-9" disabled={!editable || !promoInput} onClick={() => patchQuote.mutate({ promo_code: promoInput })} data-testid="quote-promo-apply-btn">Applica</Button>
                    {(q.promo_code || Number(q.global_discount_value) > 0) && <Button type="button" size="sm" variant="ghost" className="rounded-sm h-9 text-destructive" disabled={!editable} onClick={() => { setPromoInput(""); setDiscountPct(0); patchQuote.mutate({ promo_code: "" }); }} data-testid="quote-discount-remove-btn">Rimuovi</Button>}
                  </div>
                  {Number(q.global_discount_amount) > 0 && (
                    <div className="text-xs font-bold text-emerald-700" data-testid="quote-global-discount">
                      Subtotale {fmtEUR(q.commercial_subtotal)} · Sconto {q.promo_code ? `promo ${q.promo_code}` : `${q.global_discount_value}%`} = − {fmtEUR(q.global_discount_amount)} → Imponibile {fmtEUR(q.subtotal)}
                    </div>
                  )}
                </div>
                {Number(q.automatic_discount_percent) > 0 && (
                  <div className="mt-1 text-xs font-bold text-emerald-700" data-testid="quote-payment-discount">
                    Sconto automatico pagamento {q.automatic_discount_percent}% = − {fmtEUR(q.payment_discount_amount)}
                  </div>
                )}
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
                  <Button size="sm" className="rounded-sm" onClick={() => setCfgOpen(true)} data-testid="cfg-open"><Plus size={12} className="mr-1" /> Aggiungi prodotto</Button>
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
                  <React.Fragment key={l.id}>
                  <TableRow data-testid={`line-row-${l.id}`}>
                    <TableCell>
                      <div className="flex items-start gap-2">
                        {l.visual_spec?.svg_exterior && <ProductVisualThumb visual={l.visual_spec} size={52} testid={`line-visual-${l.id}`} />}
                        <div>
                          <Badge variant="outline" className="rounded-sm text-[10px] mr-2">{CATEGORY_LABELS[l.category] || l.category}</Badge>
                          <span className="text-sm">{l.description || "—"}</span>
                          {(l.width_mm || l.height_mm) ? <div className="text-[10px] font-mono-plex text-muted-foreground">{l.width_mm}×{l.height_mm} mm</div> : null}
                          {l.visual_spec?.spec?.interior_color_code && (
                            <div className="text-[10px] font-mono-plex text-muted-foreground" data-testid={`line-colors-${l.id}`}>
                              Int. {l.visual_spec.spec.interior_color_code} · Est. {l.visual_spec.spec.exterior_color_code}
                              {l.visual_spec.spec.sash_count ? ` · ${l.visual_spec.spec.sash_count} ante` : ""}
                            </div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono-plex text-xs">{l.quantity}</TableCell>
                    <TableCell className="font-mono-plex text-xs">{fmtEUR(l.unit_price_final || l.base_price)}</TableCell>
                    <TableCell>
                      {editable ? (
                        <Input type="number" step="0.5" defaultValue={l.discount_pct} onBlur={(e) => { const v = Number(e.target.value); if (v !== l.discount_pct) updateLine(l.id, { discount_pct: v }); }} className="rounded-sm h-8 w-16 text-xs font-mono-plex" data-testid={`line-discount-${l.id}`} />
                      ) : `${l.discount_pct}%`}
                    </TableCell>
                    <TableCell className="font-mono-plex text-xs font-bold">{fmtEUR(l.subtotal_line)}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {editable && l.product_id && <Button variant="ghost" size="sm" onClick={() => { setEditLine(l); setCfgOpen(true); }} data-testid={`line-edit-${l.id}`}>Modifica</Button>}
                      {editable && <Button variant="ghost" size="sm" onClick={() => delLine.mutate(l.id)} className="text-destructive" data-testid={`line-delete-${l.id}`}><Trash size={12} /></Button>}
                    </TableCell>
                  </TableRow>
                  {(l.automatic_services || []).length > 0 && (
                    <TableRow className="bg-muted/30" data-testid={`line-services-${l.id}`}>
                      <TableCell colSpan={6} className="py-1.5">
                        <div className="text-[10px] font-mono-plex text-muted-foreground pl-4">
                          Servizi standard inclusi:{" "}
                          {l.automatic_services.map((s, i) => (
                            <span key={s.id || i} className="mr-3">
                              <Badge variant="outline" className="rounded-sm text-[9px] mr-1">{s.service_type}</Badge>
                              {s.service_name} · <span className="font-bold">{fmtEUR(s.sale_price_total)}</span>
                            </span>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                  </React.Fragment>
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
              {Number(q.global_discount_value) > 0 && q.commercial_subtotal != null && <div className="flex justify-between text-xs"><span className="text-muted-foreground">Valore commerciale</span><span className="font-mono-plex" data-testid="totals-commercial-subtotal">{fmtEUR(q.commercial_subtotal)}</span></div>}
              {Number(q.global_discount_value) > 0 && <div className="flex justify-between text-xs"><span className="text-muted-foreground">Sconto {q.global_discount_type === "PERCENT" ? `${q.global_discount_value}%` : ""}</span><span className="font-mono-plex text-emerald-700" data-testid="totals-discount">−{fmtEUR(Number(q.commercial_subtotal || 0) - Number(q.subtotal || 0))}</span></div>}
              <div className="flex justify-between"><span className="text-muted-foreground">Imponibile</span><span className="font-mono-plex" data-testid="totals-net">{fmtEUR(q.subtotal)}</span></div>
              {(q.vat_breakdown || []).length > 1 ? (q.vat_breakdown || []).map((vb) => (
                <div key={vb.rate} className="flex justify-between text-xs" data-testid={`totals-vat-${Math.round(Number(vb.rate) * 100)}`}><span className="text-muted-foreground">IVA {Math.round(Number(vb.rate) * 100)}% su {fmtEUR(vb.taxable)}</span><span className="font-mono-plex">{fmtEUR(vb.tax)}</span></div>
              )) : null}
              <div className="flex justify-between"><span className="text-muted-foreground">IVA{(q.vat_breakdown || []).length === 1 ? ` ${Math.round(Number(q.vat_breakdown[0].rate) * 100)}%` : ((q.vat_breakdown || []).length > 1 ? " (mista)" : "")}</span><span className="font-mono-plex" data-testid="totals-vat">{fmtEUR(q.vat_amount)}</span></div>
              <div className="flex justify-between pt-2 border-t"><span className="font-bold">Totale IVA inclusa</span><span className="font-mono-plex text-lg font-black" data-testid="totals-gross">{fmtEUR(q.total)}</span></div>
              <div className="pt-2">
                <Label className="text-[10px] uppercase">IVA</Label>
                <Select value={q.fiscal_dossier?.requested_regime || "VAT_ORDINARY"} disabled={!editable} onValueChange={(v) => patchFiscal.mutate({ requested_regime: v })}>
                  <SelectTrigger className="rounded-sm h-9" data-testid="quote-vat-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(vatOptions?.options || []).map((o) => <SelectItem key={o.value} value={o.value} data-testid={`vat-opt-${o.value}`}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
                {["VAT_DOCUMENTATION_INCOMPLETE", "VAT_REVIEW_REQUIRED"].includes(q.vat_regime) && <div className="mt-1 text-[10px] font-bold text-amber-700" data-testid="quote-vat-warning">IVA AGEVOLATA — DOCUMENTAZIONE DA COMPLETARE: applicata IVA 22% ordinaria finché il dossier fiscale non è validato{q.fiscal_dossier?.documentation_status ? ` (documenti: ${q.fiscal_dossier.documentation_status}${q.fiscal_dossier.customer_declaration ? ", dichiarazione cliente ✓" : ", dichiarazione cliente mancante"})` : ""}.</div>}
              </div>
              <div className="flex items-center justify-between pt-1 text-[10px] text-muted-foreground"><span>Regime IVA applicato: <b data-testid="totals-vat-regime">{vatOptions?.labels?.[q.vat_regime] || q.vat_regime || "IVA 22% ordinaria"}</b></span>{q.fiscal_dossier?.vat_eligibility_status && <Badge variant="outline" className="rounded-sm text-[10px]" data-testid="totals-fiscal-status">Dossier fiscale: {q.fiscal_dossier.vat_eligibility_status}</Badge>}</div>
            </div>
          </Card>

          {/* --- Marginalità (Margin Tachometer V1 — msg 392) --- */}
          <MarginPanel financial={financial} isAdmin={!!financial?.is_admin_master_view} />
          <CompetitorAnalyzerCard quoteId={id} editable={editable} isAdmin={isAdminMaster} />
          <Card className="rounded-sm border-border p-4" data-testid="quote-emails-card">
            <div className="overline mb-3">Email preventivo — stato consegna</div>
            <QuoteEmailHistory quoteId={id} />
          </Card>
          <QuoteEmailDialog quoteId={id} open={emailOpen} onOpenChange={setEmailOpen} latestPdf={latestDef} onSent={reload} />

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

      <MultiCategoryConfiguratorDialog open={cfgOpen} onOpenChange={(o) => { setCfgOpen(o); if (!o) setEditLine(null); }} onConfirm={onConfiguratorConfirm} initialConfig={editLine} canSeeCosts={canSeeCosts} />
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


// ---------------------------------------------------------------------------
// Margin Panel — Tachimetro + breakdown differenziato per ruolo (§10/§12 msg 392)
// ---------------------------------------------------------------------------
function MarginPanel({ financial, isAdmin }) {
  const fs = financial?.financial_snapshot;
  const frozen = !!financial?.frozen;
  if (!fs) {
    return (
      <Card className="rounded-sm border-border p-6" data-testid="margin-panel-empty">
        <div className="overline mb-2">Commissione e sconti</div>
        <div className="text-xs text-muted-foreground">Aggiungi almeno una riga per calcolare la commissione.</div>
      </Card>
    );
  }
  const commRate = fs.actual_commission_rate ?? fs.commission_rate;
  const commGross = fs.commission_gross;
  const blocked = fs.discount_status === "BLOCKED";
  const isIncomplete = fs.financial_snapshot_status === "INCOMPLETE";
  const postPct = fs.post_margin_percent;
  const postClass = postPct == null ? null : postPct <= 15 ? "BLOCKED" : postPct < 20 ? "LOW_MARGIN" : "NORMAL";

  return (
    <Card className="rounded-sm border-border p-6" data-testid="margin-panel">
      <div className="flex items-center justify-between mb-2">
        <div className="overline">{isAdmin ? "Margine aziendale" : "Commissione prevista"}</div>
        {frozen && <Badge className="rounded-sm bg-slate-500/20 text-slate-700 text-[10px]">CONGELATA</Badge>}
      </div>

      {isAdmin ? (
        <MarginTachometer marginPct={fs.tachometer_value} band={fs.margin_band} />
      ) : (
        <CommissionTachometer ratePct={commRate != null ? commRate * 100 : null} />
      )}

      {isIncomplete && (
        <div className="mt-3 rounded-sm border border-amber-500 bg-amber-500/10 p-3" data-testid="margin-enea-incomplete">
          <div className="text-xs font-bold text-amber-800">COMMISSIONE NON DEFINITIVA</div>
          <div className="text-[11px] text-amber-800/90 mt-0.5">Alcuni costi interni non sono ancora configurati.</div>
        </div>
      )}

      {/* Commercial view — sconto effettivo / commissione / sconto massimo (msg 801). NESSUN margine. */}
      <div className="mt-4 pt-3 border-t space-y-1.5 text-sm" data-testid="margin-panel-commercial">
        <div className="flex justify-between" data-testid="margin-panel-effective-discount">
          <span className="text-muted-foreground">Sconto effettivo</span>
          <span className="font-mono-plex font-bold">{fmtPct(fs.effective_discount_percent)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Commissione prevista</span>
          <span className="font-mono-plex" data-testid="margin-panel-commission-rate">{commRate != null ? fmtPct(commRate * 100) : "n/d"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Commissione lorda stimata</span>
          <span className="font-mono-plex font-black" data-testid="margin-panel-commission-gross">{commGross != null ? fmtEUR(commGross) : "—"}</span>
        </div>
        <div className="flex justify-between" data-testid="margin-panel-max-discount">
          <span className="text-muted-foreground">Sconto massimo disponibile</span>
          <span className="font-mono-plex">{fmtPct(fs.max_discount_without_approval_percent)}</span>
        </div>
        <div className={`rounded-sm border p-2 text-[11px] font-bold ${blocked ? "border-destructive bg-destructive/10 text-destructive" : "border-emerald-600/40 bg-emerald-500/10 text-emerald-800"}`}
             data-testid={blocked ? "margin-discount-blocked" : "margin-price-allowed"}>
          {blocked ? "PREZZO NON CONSENTITO — riduci lo sconto o rivedi il prezzo" : "PREZZO CONSENTITO"}
        </div>
        {fs.director_approval_required && (
          <div className="rounded-sm border border-amber-500 bg-amber-500/10 p-2 text-[11px] font-bold text-amber-800" data-testid="margin-director-approval">
            SCONTO &gt; 30% — AUTORIZZAZIONE DIREZIONE RICHIESTA (commissione 0%)
          </div>
        )}
      </div>

      {/* ADMIN MASTER ONLY — dual margin (msg 800 §9) + breakdown */}
      {isAdmin && fs.pre_margin_amount != null && (
        <div className="mt-4 pt-3 border-t space-y-2 text-xs" data-testid="margin-panel-profitability">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-mono-plex text-muted-foreground uppercase">Redditività commessa · Admin Master</div>
            {postClass && (
              <Badge className={`rounded-sm text-[10px] ${postClass === "NORMAL" ? "bg-emerald-500/15 text-emerald-800" : postClass === "LOW_MARGIN" ? "bg-amber-500/15 text-amber-800" : "bg-destructive/15 text-destructive"}`} data-testid="margin-post-class">
                {postClass === "NORMAL" ? "NORMALE" : postClass === "LOW_MARGIN" ? "MARGINALITÀ BASSA" : "CRITICA / BLOCCATA"}
              </Badge>
            )}
          </div>
          <div className="flex justify-between items-baseline" data-testid="margin-pre">
            <span className="text-muted-foreground">Margine pre ritenuta/commissione</span>
            <span className="font-mono-plex font-bold">{fmtEUR(fs.pre_margin_amount)} <span className="text-muted-foreground">| {fmtPct(fs.pre_margin_percent)}</span></span>
          </div>
          <div className="flex justify-between items-baseline" data-testid="margin-post">
            <span className="font-bold">Margine finale impresa</span>
            <span className="font-mono-plex font-black text-[hsl(200_82%_45%)]">{fs.post_margin_amount != null ? fmtEUR(fs.post_margin_amount) : "—"} <span className="text-muted-foreground font-normal">| {postPct != null ? fmtPct(postPct) : "n/d"}</span></span>
          </div>
        </div>
      )}

      {isAdmin && fs.supply_cost != null && (
        <div className="mt-4 pt-3 border-t border-dashed space-y-1 text-xs" data-testid="margin-panel-admin">
          <div className="text-[10px] font-mono-plex text-muted-foreground uppercase mb-1">Riservato Direzione</div>
          <div className="flex justify-between"><span className="text-muted-foreground">Valore contratto IVA incl.</span><span className="font-mono-plex">{fmtEUR(fs.gross_contract_value)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Ricavo netto</span><span className="font-mono-plex">{fmtEUR(fs.net_revenue_ex_vat)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Costo fornitura</span><span className="font-mono-plex">− {fmtEUR(fs.supply_cost)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Costo posa</span><span className="font-mono-plex">− {fmtEUR(fs.installation_cost)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Altri costi diretti</span><span className="font-mono-plex">− {fmtEUR(fs.other_direct_costs)}</span></div>
          {fs.withholding_applicable && (
            <div className="flex justify-between" data-testid="margin-panel-withholding"><span className="text-muted-foreground">Ritenuta d'acconto ({(fs.withholding_rate * 100).toFixed(0)}%)</span><span className="font-mono-plex">− {fmtEUR(fs.withholding_cost)}</span></div>
          )}
          {commGross != null && (
            <div className="flex justify-between"><span className="text-muted-foreground">Commissione commerciale</span><span className="font-mono-plex">− {fmtEUR(commGross)}</span></div>
          )}
        </div>
      )}
    </Card>
  );
}
// ---------------------------------------------------------------------------
// Installation Mode V1 (msg 393 §17) — selector top-preventivo
// ---------------------------------------------------------------------------
function InstallationModeCard({ q, editable, onChange }) {
  const [pending, setPending] = React.useState(false);
  const [err, setErr] = React.useState(null);
  const mode = q.installation_mode || null;
  const dm = q.dismantling_mode || "EXCLUDED";
  const dpm = q.disposal_mode || "EXCLUDED";

  const patch = async (payload) => {
    setErr(null); setPending(true);
    try {
      await api.patch(`/quotes/${q.id}`, payload);
      toast.success("Modalità aggiornata");
      onChange?.();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = formatApiError(detail) || e.message;
      setErr(msg);
      toast.error(msg);
    } finally { setPending(false); }
  };

  return (
    <Card className="rounded-sm border-border p-4" data-testid="installation-mode-card">
      <div className="overline mb-3">Tipo fornitura</div>
      <div className="flex flex-wrap gap-2 mb-3">
        <Button
          variant={mode === "SUPPLY_ONLY" ? "default" : "outline"}
          size="sm"
          disabled={!editable || pending}
          onClick={() => patch({ installation_mode: "SUPPLY_ONLY" })}
          className="rounded-sm"
          data-testid="installation-mode-supply-only"
        >Solo fornitura</Button>
        <Button
          variant={mode === "SUPPLY_AND_INSTALLATION" ? "default" : "outline"}
          size="sm"
          disabled={!editable || pending}
          onClick={() => patch({ installation_mode: "SUPPLY_AND_INSTALLATION" })}
          className="rounded-sm"
          data-testid="installation-mode-supply-and-installation"
        >Fornitura + posa</Button>
        {mode == null && <Badge className="rounded-sm bg-amber-500/20 text-amber-800 text-[10px] self-center">Da selezionare</Badge>}
      </div>
      {mode === "SUPPLY_AND_INSTALLATION" && (
        <div className="grid grid-cols-2 gap-3 pt-3 border-t">
          <PolicySelect label="Smontaggio" value={dm} editable={editable && !pending} testid="dismantling-mode"
                        onChange={(v) => patch({ dismantling_mode: v })} />
          <PolicySelect label="Smaltimento" value={dpm} editable={editable && !pending} testid="disposal-mode"
                        onChange={(v) => patch({ disposal_mode: v })} disableIncluded />
        </div>
      )}
      {/* Detrazione fiscale — single source (msg 397) + Pratica ENEA */}
      <div className="grid grid-cols-2 gap-3 pt-3 border-t mt-3">
        <div>
          <Label className="text-xs">Detrazione fiscale</Label>
          <div className="mt-1 flex gap-2">
            <Button variant={!q.tax_deduction_requested ? "default" : "outline"} size="sm" className="rounded-sm flex-1"
                    disabled={!editable || pending}
                    onClick={() => patch({ tax_deduction_requested: false })}
                    data-testid="tax-deduction-no">No</Button>
            <Button variant={q.tax_deduction_requested ? "default" : "outline"} size="sm" className="rounded-sm flex-1"
                    disabled={!editable || pending}
                    onClick={() => patch({ tax_deduction_requested: true, enea_practice_code: q.enea_practice_code || "ENEA_STANDARD" })}
                    data-testid="tax-deduction-yes">Sì</Button>
          </div>
          {q.tax_deduction_requested && (
            <div className="text-[10px] text-muted-foreground mt-1">Ritenuta d'acconto 11% applicata al pagamento.</div>
          )}
        </div>
        <div>
          <Label className="text-xs">Pratica ENEA {q.tax_deduction_requested && <span className="text-destructive">*</span>}</Label>
          <Select value={q.enea_practice_code || "NONE"}
                  disabled={!editable || pending}
                  onValueChange={(v) => patch({ enea_practice_code: v === "NONE" ? null : v })}>
            <SelectTrigger className="rounded-sm h-9 mt-1" data-testid="enea-practice">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="NONE" disabled={q.tax_deduction_requested} data-testid="enea-none">
                Nessuna{q.tax_deduction_requested ? " (richiesta con detrazione)" : ""}
              </SelectItem>
              <SelectItem value="ENEA_STANDARD" data-testid="enea-standard">Standard — 100,00 €</SelectItem>
              <SelectItem value="ENEA_INSURED" data-testid="enea-insured">Assicurata — 350,00 €</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      {err && <div className="text-xs text-destructive mt-2" data-testid="installation-mode-error">{err}</div>}
      <div className="text-[10px] text-muted-foreground mt-2">
        {mode === "SUPPLY_AND_INSTALLATION"
          ? "I servizi di posa vengono aggiunti automaticamente per ogni prodotto compatibile."
          : mode === "SUPPLY_ONLY"
          ? "Nessun servizio di posa automatico. Solo prodotti."
          : "Seleziona il tipo fornitura per iniziare la configurazione."}
      </div>
    </Card>
  );
}

function PolicySelect({ label, value, onChange, editable, testid, disableIncluded }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange} disabled={!editable}>
        <SelectTrigger className="rounded-sm h-9" data-testid={testid}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="INCLUDED" disabled={disableIncluded} data-testid={`${testid}-included`}>
            Incluso{disableIncluded ? " (prezzo da configurare)" : ""}
          </SelectItem>
          <SelectItem value="EXCLUDED" data-testid={`${testid}-excluded`}>Escluso</SelectItem>
          <SelectItem value="NOT_APPLICABLE" data-testid={`${testid}-not-applicable`}>Non applicabile</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

