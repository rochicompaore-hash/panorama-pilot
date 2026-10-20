import React from "react";
import { useMutation } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);

export function DiscountApprovalBar({ quote, isAdmin, onChanged }) {
  const da = quote?.discount_approval, st = quote?.discount_approval_status;
  const decide = useMutation({ mutationFn: async (decision) => (await api.post(`/quotes/${quote.id}/discount-approval/${decision}`, {})).data, onSuccess: (_, d) => { toast.success(d === "approve" ? "Sconto approvato" : "Sconto rifiutato: ripristinato valore precedente"); onChanged?.(); }, onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message) });
  if (!st || !da) return null;
  const tone = st === "DISCOUNT_APPROVAL_REQUIRED" ? "border-amber-300 bg-amber-50" : st === "APPROVED" ? "border-emerald-300 bg-emerald-50" : "border-red-300 bg-red-50";
  return (
    <div className={`border rounded-sm p-2 text-xs space-y-1 ${tone}`} data-testid="discount-approval-bar">
      <div className="flex items-center justify-between"><span className="font-bold">Sconto {da.requested_discount}% — <Badge variant="outline" className="rounded-sm text-[9px]" data-testid="discount-approval-status">{st}</Badge></span><span className="text-[10px] text-muted-foreground">motivo: {da.reason} · richiesto da {da.requested_by_email || da.requested_by} · {String(da.requested_at).slice(0, 16).replace("T", " ")}</span></div>
      {isAdmin && <div className="grid grid-cols-2 md:grid-cols-4 gap-1 text-[10px]">
        {[["Prezzo prima sconto", eur(quote.commercial_subtotal)], ["Sconto €", eur(quote.global_discount_amount)], ["Prezzo finale (imponibile)", eur(quote.subtotal)], ["Margine prima → dopo", `${da.margin_before ?? "—"}% → ${da.margin_after ?? "—"}%`]].map(([l, v]) => <div key={l} className="border rounded-sm p-1 bg-white"><div className="text-muted-foreground">{l}</div><b className="font-mono-plex">{v}</b></div>)}
      </div>}
      {st === "DISCOUNT_APPROVAL_REQUIRED" && isAdmin && <div className="flex gap-1"><Button size="sm" className="rounded-sm h-7 text-[10px]" onClick={() => decide.mutate("approve")} data-testid="discount-approve-btn">APPROVA</Button><Button size="sm" variant="destructive" className="rounded-sm h-7 text-[10px]" onClick={() => decide.mutate("reject")} data-testid="discount-reject-btn">RIFIUTA</Button></div>}
      {st === "DISCOUNT_APPROVAL_REQUIRED" && !isAdmin && <div className="text-[10px] text-amber-800">In attesa di approvazione direzione: il preventivo non può essere inviato come definitivo.</div>}
      {st === "APPROVED" && <div className="text-[10px] text-emerald-800">Approvato da {da.approved_by_email || da.approved_by} il {String(da.approved_at).slice(0, 16).replace("T", " ")}{da.auto_approved_admin_master ? " (Admin Master diretto)" : ""}</div>}
    </div>
  );
}
