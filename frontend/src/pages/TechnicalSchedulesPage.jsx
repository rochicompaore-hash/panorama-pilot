/**
 * TechnicalSchedulesPage — Abaco tecnico (lista + dettaglio semplice)
 */
import React, { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const STATUS_LABEL = {
  draft: "Bozza", in_technical_review: "In revisione tecnica",
  approved_internally: "Approvato interno", sent_to_customer: "Inviato al cliente",
  viewed: "Visualizzato", change_requested: "Modifica richiesta",
  awaiting_signature: "In attesa firma", signed: "Firmato",
  superseded: "Superato", cancelled: "Annullato",
  released_to_production: "Rilasciato in produzione",
};

export default function TechnicalSchedulesPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);
  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/workflow/technical-schedules");
      setItems(data.items || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const sendToCustomer = async (id) => {
    try {
      const { data } = await api.post(`/workflow/technical-schedules/${id}/send`, {
        channel: "link", require_otp: false,
      });
      await navigator.clipboard.writeText(`${window.location.origin}/p/schedule/${data.raw_token}`);
      toast.success("Link abaco copiato negli appunti");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Errore invio");
    }
  };

  return (
    <div className="space-y-6" data-testid="technical-schedules-page">
      <div>
        <div className="overline text-muted-foreground">Abaco tecnico</div>
        <h1 className="font-display text-3xl font-black tracking-tight">Abaci</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Documento tecnico definitivo generato dal rilievo. Contiene misure e configurazione finali
          che sostituiscono le indicazioni del preventivo. Deve essere firmato dal cliente prima
          della produzione.
        </p>
      </div>

      <Card className="rounded-sm">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Elenco abachi ({items.length})</CardTitle>
          <Button size="sm" variant="outline" onClick={load} className="rounded-sm" data-testid="refresh-ts-btn">Aggiorna</Button>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 text-sm text-muted-foreground">Caricamento…</div>
          ) : items.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">
              Nessun abaco. Gli abachi vengono creati dal rilievo validato tramite l'endpoint
              <code className="ml-1 bg-muted px-1 rounded">POST /workflow/technical-schedules/from-survey/{'{'}survey_id{'}'}</code>.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground border-b bg-muted">
                <tr>
                  <th className="text-left py-2 px-3">Numero</th>
                  <th className="text-left">Versione</th>
                  <th className="text-left">Stato</th>
                  <th className="text-left">Vani</th>
                  <th className="text-left">Contratto</th>
                  <th className="text-right px-3">Azioni</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={it.id} className="border-b" data-testid={`ts-row-${i}`}>
                    <td className="py-1.5 px-3 font-mono-plex">{it.number}</td>
                    <td className="font-mono-plex">V{it.version?.toString().padStart(2, "0")}</td>
                    <td>
                      <Badge variant="outline" className="rounded-sm text-[11px]">
                        {STATUS_LABEL[it.ts_status] || it.ts_status}
                      </Badge>
                    </td>
                    <td className="font-mono-plex">{(it.items || []).length}</td>
                    <td className="font-mono-plex text-xs">{(it.contract_id || "").slice(0, 8)}…</td>
                    <td className="text-right px-3">
                      <Button size="sm" variant="ghost" onClick={() => setDetail(it)} className="rounded-sm text-xs" data-testid={`view-ts-btn-${i}`}>
                        Dettaglio
                      </Button>
                      {it.ts_status === "approved_internally" && (
                        <Button size="sm" variant="outline" onClick={() => sendToCustomer(it.id)} className="rounded-sm text-xs ml-2" data-testid={`send-ts-btn-${i}`}>
                          Invia
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {detail && (
        <Card className="rounded-sm">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Abaco {detail.number} · V{detail.version}</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => setDetail(null)} className="rounded-sm">Chiudi</Button>
          </CardHeader>
          <CardContent>
            <div className="text-xs text-muted-foreground mb-2">
              Stato: <Badge variant="outline" className="rounded-sm">{STATUS_LABEL[detail.ts_status]}</Badge>
              {detail.signed_at && <span className="ml-2">Firmato: {detail.signed_at}</span>}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground border-b">
                  <tr>
                    <th className="text-left py-2">Vano</th><th className="text-left">Stanza</th>
                    <th className="text-left">Prodotto</th>
                    <th className="text-right">L (mm)</th><th className="text-right">H (mm)</th>
                    <th className="text-left">Ante</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.items || []).map((it, i) => (
                    <tr key={i} className="border-b">
                      <td className="py-1 font-mono-plex">{it.ref}</td>
                      <td>{it.room || "—"}</td>
                      <td>{it.product_key}</td>
                      <td className="text-right font-mono-plex">{it.final_width_mm}</td>
                      <td className="text-right font-mono-plex">{it.final_height_mm}</td>
                      <td>{it.nr_ante}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
