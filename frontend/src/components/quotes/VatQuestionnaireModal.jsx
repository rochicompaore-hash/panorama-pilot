import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

const OUT_LABEL = { STANDARD_22: "IVA 22% ordinaria", ELIGIBLE_10_FULL: "IVA 10%", ELIGIBLE_MIXED_10_22: "IVA MISTA 10% / 22%", ELIGIBLE_4: "IVA 4%", NOT_ELIGIBLE: "NON AGEVOLABILE → 22%", NEEDS_DOCUMENTATION: "DOCUMENTAZIONE DA COMPLETARE", NEEDS_FISCAL_REVIEW: "REVISIONE FISCALE RICHIESTA" };
const OUT_TONE = { ELIGIBLE_10_FULL: "bg-emerald-600", ELIGIBLE_MIXED_10_22: "bg-emerald-600", ELIGIBLE_4: "bg-emerald-600", NOT_ELIGIBLE: "bg-red-600", NEEDS_DOCUMENTATION: "bg-amber-500", NEEDS_FISCAL_REVIEW: "bg-orange-600", STANDARD_22: "bg-zinc-500" };
const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);

export function VatQuestionnaireModal({ quoteId, open, onClose, requestedRegime, canValidate }) {
  const qc = useQueryClient();
  const { data: d } = useQuery({ queryKey: ["fiscal-questionnaire", quoteId], queryFn: async () => (await api.get(`/quotes/${quoteId}/fiscal-questionnaire`)).data, enabled: open });
  const [extra, setExtra] = React.useState({});
  const [signer, setSigner] = React.useState("");
  const [showCalc, setShowCalc] = React.useState(false);
  const inv = () => { qc.invalidateQueries({ queryKey: ["fiscal-questionnaire", quoteId] }); qc.invalidateQueries({ queryKey: ["quote", quoteId] }); qc.invalidateQueries({ queryKey: ["quote-financial"] }); };
  const onErr = (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message);
  const answer = useMutation({ mutationFn: async (answers) => (await api.post(`/quotes/${quoteId}/fiscal-questionnaire/answers`, { answers, requested_regime: requestedRegime })).data, onSuccess: inv, onError: onErr });
  const call = useMutation({ mutationFn: async ({ path, body }) => (await api.post(`/quotes/${quoteId}/${path}`, body || {})).data, onSuccess: () => { toast.success("Dossier aggiornato"); inv(); }, onError: onErr });
  if (!d) return null;
  const pending = d.pending_questions || [];
  const current = d.questions.find((q) => q.key === pending[0]);
  const ev = d.evaluation, decl = d.declaration || {};
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="vat-questionnaire-modal">
        <DialogHeader><DialogTitle className="text-base">VERIFICA IVA AGEVOLATA — {d.requested_regime?.replace("VAT_ELIGIBLE_", "IVA ").replace("VAT_MIXED_10_22", "IVA MISTA")}</DialogTitle></DialogHeader>
        <div className="text-xs text-muted-foreground">Per applicare correttamente l'aliquota agevolata dobbiamo verificare alcune informazioni relative all'immobile e all'intervento. Finché la verifica non è conclusa viene applicata l'IVA 22%.</div>
        <div className="text-[10px] text-muted-foreground">Rispondi {d.questions.length - pending.length}/{d.questions.length} · regole {d.rule_version}</div>
        {current && (
          <div className="border rounded-sm p-3 space-y-2" data-testid={`vat-q-${current.key}`}>
            <div className="text-sm font-bold">{current.text}</div>
            {current.note && <div className="text-[10px] text-amber-700">{current.note}</div>}
            <div className="flex flex-wrap gap-1">{current.options.map((o) => <Button key={o.value} size="sm" variant="outline" className="rounded-sm h-8 text-xs" onClick={() => answer.mutate({ [current.key]: o.value, ...extra })} data-testid={`vat-opt-${current.key}-${o.value}`}>{o.label}</Button>)}</div>
            {current.extra_fields && <div className="grid grid-cols-2 gap-1">{[["property_address", "Indirizzo immobile"], ["cadastral_data", "Dati catastali"], ["property_type", "Tipo immobile"], ["condominium_name", "Condominio"]].map(([k, l]) => <Input key={k} placeholder={l} className="rounded-sm h-8 text-xs" value={extra[k] || ""} onChange={(e) => setExtra({ ...extra, [k]: e.target.value })} data-testid={`vat-extra-${k}`} />)}</div>}
          </div>
        )}
        {!current && d.questions.length > 0 && (
          <div className="space-y-1" data-testid="vat-answers-summary">{d.questions.map((q) => <div key={q.key} className="flex justify-between text-xs border-t py-1"><span className="text-muted-foreground">{q.text}</span><button type="button" className="underline" onClick={() => answer.mutate({ [q.key]: "" })} data-testid={`vat-change-${q.key}`}>{q.options.find((o) => o.value === q.answer)?.label || q.answer}</button></div>)}</div>
        )}
        {ev && (
          <div className="border rounded-sm p-3 space-y-2" data-testid="vat-result">
            <div className="flex items-center justify-between"><span className="text-xs font-bold uppercase">Risultato Fiscal Engine</span><Badge className={`rounded-sm text-white ${OUT_TONE[ev.outcome]}`} data-testid="vat-result-outcome">{OUT_LABEL[ev.outcome] || ev.outcome}</Badge></div>
            {ev.checks.map((c, i) => <div key={i} className={`text-xs ${c.ok ? "text-emerald-700" : "text-red-700"}`} data-testid="vat-check">{c.ok ? "✓" : "✗"} {c.label}{c.info ? <span className="text-muted-foreground"> — {c.info}</span> : null}</div>)}
            {ev.missing_requirements?.length > 0 && <div className="text-xs text-amber-800" data-testid="vat-missing"><b>MANCANO:</b> {ev.missing_requirements.join(" · ")} — IVA applicata temporaneamente 22% · dossier {d.vat_eligibility_status || "PENDING"}</div>}
            {ev.legal_basis && canValidate && <div className="text-[10px] text-muted-foreground">Base normativa: {ev.legal_basis}</div>}
            {ev.mixed_split && <div><button type="button" className="text-xs underline" onClick={() => setShowCalc(!showCalc)} data-testid="vat-see-calc">Vedi calcolo beni significativi</button>{showCalc && <div className="text-xs mt-1 grid grid-cols-2 gap-1" data-testid="vat-calc">{[["Bene significativo (infissi)", eur(ev.mixed_split.value_of_significant_good)], ["Altri beni e servizi", eur(ev.mixed_split.other_service_and_goods_value)], ["Imponibile 10%", eur(ev.mixed_split.taxable_10)], ["Imponibile 22%", eur(ev.mixed_split.taxable_22)]].map(([l, v]) => <div key={l} className="border rounded-sm p-1"><div className="text-[10px] text-muted-foreground">{l}</div><b className="font-mono-plex">{v}</b></div>)}<div className="col-span-2 text-[10px] text-muted-foreground">Metodo {ev.mixed_split.method}: 10% su servizi/altri beni e sul bene significativo fino a concorrenza della differenza; eccedenza al 22%.</div></div>}</div>}
          </div>
        )}
        {ev && !current && ev.outcome !== "STANDARD_22" && ev.outcome !== "NOT_ELIGIBLE" && (
          <div className="border rounded-sm p-3 space-y-2" data-testid="vat-dossier-actions">
            <div className="text-xs font-bold uppercase">Dossier · dichiarazione cliente: <Badge variant="outline" className="rounded-sm">{decl.status || "NOT_GENERATED"}</Badge></div>
            {(!decl.status || decl.status === "NOT_GENERATED") && <Button size="sm" className="rounded-sm" onClick={() => call.mutate({ path: "fiscal-dossier/declaration/generate" })} data-testid="vat-decl-generate">Genera dichiarazione IVA agevolata</Button>}
            {decl.status === "WAITING_CUSTOMER" && <div className="space-y-1"><div className="text-[10px] whitespace-pre-wrap border rounded-sm p-2 max-h-32 overflow-y-auto" data-testid="vat-decl-text">{decl.text}</div><div className="flex gap-1"><Input placeholder="Nome e cognome firmatario" className="rounded-sm h-8 text-xs" value={signer} onChange={(e) => setSigner(e.target.value)} data-testid="vat-decl-signer" /><Button size="sm" className="rounded-sm h-8" disabled={!signer} onClick={() => call.mutate({ path: "fiscal-dossier/declaration/sign", body: { signer_name: signer, channel: "IN_PRESENCE" } })} data-testid="vat-decl-sign">Firma (in presenza)</Button></div></div>}
            <div className="flex flex-wrap gap-1 items-center text-xs">Documenti: {(d.documents || []).map((x) => <Badge key={x.id} variant="outline" className="rounded-sm text-[9px]">{x.doc_type}</Badge>)}
              <select className="h-8 rounded-sm border px-2 text-xs" defaultValue="" onChange={(e) => { if (e.target.value) { call.mutate({ path: "fiscal-dossier/documents", body: { doc_type: e.target.value, file_name: `${e.target.value}.pdf` } }); e.target.value = ""; } }} data-testid="vat-doc-add"><option value="">+ registra documento…</option>{(ev.required_documents || []).filter((x) => x !== "CUSTOMER_DECLARATION").map((x) => <option key={x} value={x}>{x}</option>)}</select>
            </div>
            {canValidate && ["ELIGIBLE_10_FULL", "ELIGIBLE_MIXED_10_22", "ELIGIBLE_4"].includes(ev.outcome) && d.vat_eligibility_status !== "VALIDATED" && <div className="flex gap-1"><Button size="sm" className="rounded-sm" onClick={() => call.mutate({ path: "fiscal-dossier/validate", body: { decision: "VALIDATED" } })} data-testid="vat-validate">Valida dossier (Fiscal)</Button><Button size="sm" variant="destructive" className="rounded-sm" onClick={() => call.mutate({ path: "fiscal-dossier/validate", body: { decision: "REJECTED" } })} data-testid="vat-reject">Rifiuta</Button></div>}
            {d.vat_eligibility_status === "VALIDATED" && <div className="text-xs text-emerald-700 font-bold" data-testid="vat-validated">✓ Dossier VALIDATO — aliquota applicata dal backend.</div>}
          </div>
        )}
        <div className="flex justify-end"><Button size="sm" variant="outline" className="rounded-sm" onClick={onClose} data-testid="vat-modal-close">Chiudi</Button></div>
      </DialogContent>
    </Dialog>
  );
}
