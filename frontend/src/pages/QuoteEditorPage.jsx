import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ArrowLeft, Plus, Trash, PaperPlaneTilt, ArrowsClockwise, FileText, Check } from "@phosphor-icons/react";
import { toast } from "sonner";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

const CATEGORY_LABELS = { window: "Serramento", shutter: "Persiana/Scuro", roller: "Tapparella", persian: "Persiana", screen: "Zanzariera", box: "Cassonetto", sill: "Davanzale", trim: "Coprifilo", accessory: "Accessorio", installation: "Posa", disposal: "Smaltimento", extra: "Extra" };

export default function QuoteEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { has } = useAuth();
  const qc = useQueryClient();
  const { data: q } = useQuery({ queryKey: ["quote", id], queryFn: async () => (await api.get(`/quotes/${id}`)).data });
  const { data: history } = useQuery({ queryKey: ["quote-history", id], queryFn: async () => (await api.get(`/quotes/${id}/history`)).data });

  const addOpening = useMutation({ mutationFn: async (p) => (await api.post(`/quotes/${id}/openings`, p)).data, onSuccess: () => { toast.success("Vano aggiunto"); qc.invalidateQueries({ queryKey: ["quote", id] }); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const addLine = useMutation({ mutationFn: async (p) => (await api.post(`/quotes/${id}/lines`, p)).data, onSuccess: () => { toast.success("Riga aggiunta"); qc.invalidateQueries({ queryKey: ["quote", id] }); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const delLine = useMutation({ mutationFn: async (lid) => (await api.delete(`/quotes/${id}/lines/${lid}`)).data, onSuccess: () => { toast.success("Riga eliminata"); qc.invalidateQueries({ queryKey: ["quote", id] }); } });
  const updLine = useMutation({ mutationFn: async ({ lid, patch }) => (await api.patch(`/quotes/${id}/lines/${lid}`, patch)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ["quote", id] }), onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const changeStatus = useMutation({ mutationFn: async (new_status) => (await api.post(`/quotes/${id}/status`, { new_status })).data, onSuccess: () => { toast.success("Stato aggiornato"); qc.invalidateQueries({ queryKey: ["quote", id] }); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  const revise = useMutation({ mutationFn: async () => (await api.post(`/quotes/${id}/revise`)).data, onSuccess: (d) => { toast.success(`Revisione ${d.revision_label} creata`); navigate(`/quotes/${d.id}`); } });
  const convert = useMutation({ mutationFn: async () => (await api.post(`/quotes/${id}/convert-to-contract`)).data, onSuccess: (d) => { toast.success(`Contratto ${d.number} generato`); navigate(`/contracts/${d.id}`); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });

  if (!q) return <div className="text-sm text-muted-foreground">Caricamento…</div>;

  const editable = !["accepted", "converted", "superseded", "rejected", "cancelled", "expired"].includes(q.quote_status);

  return (
    <div className="space-y-6" data-testid="quote-editor-page">
      <Button variant="ghost" size="sm" className="rounded-sm" onClick={() => navigate("/quotes")}><ArrowLeft size={14} className="mr-1" /> Torna a Preventivi</Button>

      <div className="flex items-end justify-between">
        <div>
          <div className="overline font-mono-plex">{q.number}</div>
          <h1 className="mt-1 font-display text-3xl font-black tracking-tight">{q.title || "Preventivo"}</h1>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="rounded-sm uppercase">{q.quote_status}</Badge>
            <Badge variant="outline" className="rounded-sm">{q.revision_label}</Badge>
            {q.approval?.status === "pending" && <Badge className="rounded-sm bg-orange-500">Approvazione pendente</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {editable && has("quotes.send") && q.quote_status === "draft" && <Button variant="outline" className="rounded-sm" onClick={() => changeStatus.mutate("sent")} data-testid="quote-send"><PaperPlaneTilt size={14} className="mr-1" /> Invia</Button>}
          {q.quote_status === "sent" && <Button variant="outline" className="rounded-sm" onClick={() => changeStatus.mutate("accepted")} data-testid="quote-accept"><Check size={14} className="mr-1" /> Accettato</Button>}
          {["accepted", "approved"].includes(q.quote_status) && !q.contract_id && has("quotes.convert_contract") && <Button className="rounded-sm bg-emerald-600 hover:bg-emerald-700" onClick={() => convert.mutate()} data-testid="quote-convert"><FileText size={14} className="mr-1" /> Genera contratto</Button>}
          {editable && q.is_current && <Button variant="outline" className="rounded-sm" onClick={() => revise.mutate()} data-testid="quote-revise"><ArrowsClockwise size={14} className="mr-1" /> Nuova revisione</Button>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {/* Openings */}
          <Card className="rounded-sm border-border p-4" data-testid="openings-card">
            <div className="flex items-center justify-between mb-3">
              <div className="overline">Vani finestra ({(q.openings || []).length})</div>
              {editable && <Button size="sm" variant="outline" className="rounded-sm" onClick={() => addOpening.mutate({ code: `V${(q.openings || []).length + 1}`, description: "" })} data-testid="add-opening"><Plus size={12} className="mr-1" /> Vano</Button>}
            </div>
            <div className="space-y-2">
              {(q.openings || []).map((o) => (
                <OpeningRow key={o.id} quoteId={id} opening={o} editable={editable} />
              ))}
            </div>
          </Card>

          {/* Lines */}
          <Card className="rounded-sm border-border p-4" data-testid="lines-card">
            <div className="flex items-center justify-between mb-3">
              <div className="overline">Righe ({(q.lines || []).length})</div>
              {editable && <NewLineForm quoteId={id} openings={q.openings || []} onSubmit={(p) => addLine.mutate(p)} />}
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
                        <Input type="number" step="0.5" defaultValue={l.discount_pct} onBlur={(e) => { const v = Number(e.target.value); if (v !== l.discount_pct) updLine.mutate({ lid: l.id, patch: { discount_pct: v } }); }} className="rounded-sm h-8 w-16 text-xs font-mono-plex" data-testid={`line-discount-${l.id}`} />
                      ) : `${l.discount_pct}%`}
                    </TableCell>
                    <TableCell className="font-mono-plex text-xs font-bold">{fmtEUR(l.subtotal_line)}</TableCell>
                    <TableCell>{editable && <Button variant="ghost" size="sm" onClick={() => delLine.mutate(l.id)} className="text-destructive" data-testid={`line-delete-${l.id}`}><Trash size={12} /></Button>}</TableCell>
                  </TableRow>
                ))}
                {(q.lines || []).length === 0 && <TableRow><TableCell colSpan={6} className="text-center py-6 text-sm text-muted-foreground">Nessuna riga. Aggiungi prodotti al preventivo.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </Card>
        </div>

        {/* Right: totals + revisions */}
        <div className="space-y-4">
          <Card className="rounded-sm border-border p-6" data-testid="totals-card">
            <div className="overline mb-4">Totali</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-muted-foreground">Imponibile</span><span className="font-mono-plex">{fmtEUR(q.subtotal)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">IVA</span><span className="font-mono-plex">{fmtEUR(q.vat_amount)}</span></div>
              <div className="flex justify-between pt-2 border-t"><span className="font-bold">Totale</span><span className="font-mono-plex text-lg font-black">{fmtEUR(q.total)}</span></div>
              {has("quotes.view_margins") && q.margin_abs != null && (
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
        </div>
      </div>
    </div>
  );
}

function OpeningRow({ quoteId, opening, editable }) {
  const qc = useQueryClient();
  const [w, setW] = useState(opening.width_mm || "");
  const [h, setH] = useState(opening.height_mm || "");
  const updOpen = useMutation({ mutationFn: async (patch) => (await api.patch(`/quotes/${quoteId}/openings/${opening.id}`, patch)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ["quote", quoteId] }) });
  const delOpen = useMutation({ mutationFn: async () => (await api.delete(`/quotes/${quoteId}/openings/${opening.id}`)).data, onSuccess: () => { toast.success("Vano eliminato"); qc.invalidateQueries({ queryKey: ["quote", quoteId] }); } });
  return (
    <div className="flex items-center gap-3 py-2 border-b last:border-b-0" data-testid={`opening-row-${opening.id}`}>
      <Badge variant="outline" className="rounded-sm font-mono-plex">{opening.code}</Badge>
      <Input placeholder="Stanza / descrizione" defaultValue={opening.description || ""} onBlur={(e) => updOpen.mutate({ description: e.target.value })} className="rounded-sm h-8 text-sm flex-1" disabled={!editable} data-testid={`opening-desc-${opening.id}`} />
      <Input type="number" placeholder="L (mm)" value={w} onChange={(e) => setW(e.target.value)} onBlur={() => updOpen.mutate({ width_mm: Number(w) || null })} className="rounded-sm h-8 w-24 text-xs font-mono-plex" disabled={!editable} data-testid={`opening-w-${opening.id}`} />
      <Input type="number" placeholder="H (mm)" value={h} onChange={(e) => setH(e.target.value)} onBlur={() => updOpen.mutate({ height_mm: Number(h) || null })} className="rounded-sm h-8 w-24 text-xs font-mono-plex" disabled={!editable} data-testid={`opening-h-${opening.id}`} />
      {editable && <Button variant="ghost" size="sm" onClick={() => delOpen.mutate()} className="text-destructive"><Trash size={12} /></Button>}
    </div>
  );
}

function NewLineForm({ quoteId, openings, onSubmit }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ category: "window", description: "", quantity: 1, base_price: 0, width_mm: "", height_mm: "", opening_id: "" });
  const upd = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <>
      <Button size="sm" className="rounded-sm" onClick={() => setOpen(!open)} data-testid="add-line-toggle"><Plus size={12} className="mr-1" /> Riga</Button>
      {open && (
        <form className="w-full mt-3 p-3 bg-secondary rounded-sm grid grid-cols-2 md:grid-cols-6 gap-2 col-span-full" onSubmit={(e) => { e.preventDefault(); onSubmit({ ...f, quantity: Number(f.quantity) || 1, base_price: Number(f.base_price) || 0, width_mm: Number(f.width_mm) || null, height_mm: Number(f.height_mm) || null, opening_id: f.opening_id || null }); setOpen(false); setF({ category: "window", description: "", quantity: 1, base_price: 0, width_mm: "", height_mm: "", opening_id: "" }); }}>
          <Select value={f.category} onValueChange={(v) => upd("category", v)}>
            <SelectTrigger className="rounded-sm h-9 col-span-2" data-testid="line-cat"><SelectValue /></SelectTrigger>
            <SelectContent>{Object.entries(CATEGORY_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
          </Select>
          <Input placeholder="Descrizione" value={f.description} onChange={(e) => upd("description", e.target.value)} className="rounded-sm h-9 col-span-2" data-testid="line-desc" />
          <Select value={f.opening_id} onValueChange={(v) => upd("opening_id", v)}>
            <SelectTrigger className="rounded-sm h-9 col-span-2" data-testid="line-opening"><SelectValue placeholder="Vano…" /></SelectTrigger>
            <SelectContent>{openings.map(o => <SelectItem key={o.id} value={o.id}>{o.code}</SelectItem>)}</SelectContent>
          </Select>
          <Input type="number" placeholder="L mm" value={f.width_mm} onChange={(e) => upd("width_mm", e.target.value)} className="rounded-sm h-9 font-mono-plex" data-testid="line-w" />
          <Input type="number" placeholder="H mm" value={f.height_mm} onChange={(e) => upd("height_mm", e.target.value)} className="rounded-sm h-9 font-mono-plex" data-testid="line-h" />
          <Input type="number" placeholder="Q.tà" value={f.quantity} onChange={(e) => upd("quantity", e.target.value)} className="rounded-sm h-9 font-mono-plex" data-testid="line-qty" />
          <Input type="number" step="0.01" placeholder="Prezzo unit" value={f.base_price} onChange={(e) => upd("base_price", e.target.value)} className="rounded-sm h-9 font-mono-plex col-span-2" data-testid="line-price" />
          <Button type="submit" className="rounded-sm h-9 col-span-2" data-testid="line-submit">Aggiungi</Button>
        </form>
      )}
    </>
  );
}
