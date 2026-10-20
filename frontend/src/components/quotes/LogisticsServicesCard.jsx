import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2 })} €`);

function PriceDialog({ item, mode, reasons, onClose, onConfirm, pending }) {
  const [price, setPrice] = React.useState(mode === "zero" ? "0" : String(item?.customer_price ?? ""));
  const [reason, setReason] = React.useState("");
  if (!item) return null;
  const zero = Number(price) === 0;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm max-w-md" data-testid="logistics-price-dialog">
        <DialogHeader><DialogTitle>{mode === "zero" ? "Azzera" : "Sconta"} — {item.label}</DialogTitle><DialogDescription>Prezzo standard {eur(item.standard_price)}. Lo sconto riguarda solo il prezzo cliente: il costo interno resta invariato e il margine viene verificato prima del salvataggio.</DialogDescription></DialogHeader>
        <div className="space-y-3 text-sm">
          <div><div className="text-[10px] uppercase text-muted-foreground font-bold mb-1">Prezzo cliente (0 … {item.standard_price})</div><Input type="number" min={0} max={item.standard_price} step={1} value={price} disabled={mode === "zero"} onChange={(e) => setPrice(e.target.value)} className="rounded-sm" data-testid="logistics-price-input" /></div>
          {zero && (
            <div><div className="text-[10px] uppercase text-muted-foreground font-bold mb-1">Motivo azzeramento (obbligatorio)</div>
              <Select value={reason} onValueChange={setReason}><SelectTrigger className="rounded-sm" data-testid="logistics-reason-select"><SelectValue placeholder="Seleziona motivo" /></SelectTrigger>
                <SelectContent>{reasons.map((r) => <SelectItem key={r} value={r} data-testid={`logistics-reason-${r.replace(/\s+/g, "-")}`}>{r}</SelectItem>)}</SelectContent></Select>
            </div>
          )}
          <div className="flex justify-end gap-2"><Button variant="outline" className="rounded-sm" onClick={onClose}>Annulla</Button><Button className="rounded-sm" disabled={pending || price === "" || (zero && !reason)} onClick={() => onConfirm(Number(price), reason || null)} data-testid="logistics-price-confirm">Conferma</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function LogisticsServicesCard({ quoteId, editable, onChange }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["quote-logistics", quoteId], queryFn: async () => (await api.get(`/quotes/${quoteId}/logistics`)).data });
  const [dlg, setDlg] = React.useState(null);
  const done = (msg) => { toast.success(msg); qc.invalidateQueries({ queryKey: ["quote-logistics", quoteId] }); onChange?.(); };
  const onErr = (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message, { duration: 7000 });
  const setPrice = useMutation({ mutationFn: async ({ code, price, reason }) => (await api.patch(`/quotes/${quoteId}/logistics/${code}/price`, { customer_price: price, reason })).data, onSuccess: () => { setDlg(null); done("Prezzo servizio aggiornato — margine ricalcolato"); }, onError: onErr });
  const add = useMutation({ mutationFn: async (code) => (await api.post(`/quotes/${quoteId}/logistics`, { code })).data, onSuccess: () => done("Servizio aggiunto"), onError: onErr });
  const remove = useMutation({ mutationFn: async (code) => (await api.delete(`/quotes/${quoteId}/logistics/${code}`)).data, onSuccess: () => done("Servizio rimosso"), onError: onErr });
  if (!data) return null;
  const present = new Set(data.items.map((i) => i.code));
  const addable = data.catalog.filter((c) => !present.has(c.code));
  return (
    <Card className="rounded-sm border-border p-4" data-testid="logistics-card">
      <div className="flex items-center justify-between mb-3"><div className="overline">Servizi logistici cantiere{data.site_floor != null ? ` · piano ${data.site_floor}` : ""}</div>{data.is_admin_view && <Badge variant="outline" className="rounded-sm text-[10px]">ADMIN: costi interni visibili</Badge>}</div>
      {data.items.length === 0 && <div className="text-xs text-muted-foreground" data-testid="logistics-empty">Nessun servizio logistico. Il trasporto al piano si attiva automaticamente per cantieri dal 2° al 5° piano.</div>}
      <div className="space-y-2">
        {data.items.map((i) => (
          <div key={i.code} className="border border-border rounded-sm p-3 text-sm" data-testid={`logistics-item-${i.code}`}>
            <div className="flex items-center justify-between gap-2">
              <div><b className="uppercase">{i.label}</b> {i.required && <Badge className="rounded-sm text-[9px] ml-1 bg-zinc-700 text-white">necessario</Badge>}{i.is_free && <Badge className="rounded-sm text-[9px] ml-1 bg-emerald-600 text-white" data-testid={`logistics-free-${i.code}`}>OMAGGIO</Badge>}{i.has_service_discount && !i.is_free && <Badge variant="outline" className="rounded-sm text-[9px] ml-1">scontato</Badge>}</div>
              <div className="text-right"><div className="text-[10px] text-muted-foreground">Prezzo standard {eur(i.standard_price)}</div><div className="font-mono-plex font-black" data-testid={`logistics-price-${i.code}`}>Prezzo cliente {eur(i.customer_price)}</div>{data.is_admin_view && <div className="text-[10px] text-muted-foreground" data-testid={`logistics-cost-${i.code}`}>Costo interno {eur(i.internal_cost)} · contribuzione {eur(Number(i.customer_price || 0) - Number(i.internal_cost || 0))}</div>}</div>
            </div>
            {editable && i.standard_price != null && (
              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="outline" className="rounded-sm" disabled={!i.discountable} onClick={() => setDlg({ item: i, mode: "discount" })} data-testid={`logistics-discount-${i.code}`}>Sconta</Button>
                <Button size="sm" variant="outline" className="rounded-sm" disabled={!i.zeroable || i.is_free} onClick={() => setDlg({ item: i, mode: "zero" })} data-testid={`logistics-zero-${i.code}`}>Azzera</Button>
                {Number(i.customer_price) < Number(i.standard_price) && <Button size="sm" variant="ghost" className="rounded-sm" onClick={() => setPrice.mutate({ code: i.code, price: i.standard_price, reason: null })} data-testid={`logistics-restore-${i.code}`}>Ripristina standard</Button>}
                {!i.required && <Button size="sm" variant="ghost" className="rounded-sm text-destructive ml-auto" onClick={() => remove.mutate(i.code)} data-testid={`logistics-remove-${i.code}`}>Rimuovi</Button>}
              </div>
            )}
            {i.price_history?.length > 0 && <div className="text-[10px] text-muted-foreground mt-1" data-testid={`logistics-history-${i.code}`}>Ultima modifica: {new Date(i.price_history[i.price_history.length - 1].at).toLocaleString("it-IT")} · {i.price_history[i.price_history.length - 1].user_email} · {eur(i.price_history[i.price_history.length - 1].old_price)} → {eur(i.price_history[i.price_history.length - 1].new_price)}{i.price_history[i.price_history.length - 1].reason ? ` · ${i.price_history[i.price_history.length - 1].reason}` : ""}</div>}
          </div>
        ))}
      </div>
      {editable && addable.length > 0 && <div className="flex gap-2 mt-3 flex-wrap">{addable.map((c) => <Button key={c.code} size="sm" variant="outline" className="rounded-sm" disabled={c.standard_price == null} onClick={() => add.mutate(c.code)} data-testid={`logistics-add-${c.code}`}>+ {c.label}{c.standard_price == null ? " (prezzo da configurare)" : ` · ${eur(c.standard_price)}`}</Button>)}</div>}
      {dlg && <PriceDialog item={dlg.item} mode={dlg.mode} reasons={data.zero_reasons} onClose={() => setDlg(null)} pending={setPrice.isPending} onConfirm={(price, reason) => setPrice.mutate({ code: dlg.item.code, price, reason })} />}
    </Card>
  );
}
