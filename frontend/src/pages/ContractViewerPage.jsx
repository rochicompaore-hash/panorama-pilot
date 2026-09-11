import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";


// Address può essere stringa o oggetto {street, city, zip_code, province, country}
function formatAddress(a) {
  if (!a) return "";
  if (typeof a === "string") return a;
  if (typeof a === "object") {
    const parts = [a.street, a.zip_code, a.city, a.province, a.country].filter(Boolean);
    return parts.join(", ");
  }
  return "";
}

/**
 * Contract viewer + firma integrata.
 * Mostra il contratto integralmente prima della firma (no solo pulsante download).
 */
import { PresignCheckBanner, PartiesEditor, QuoteSummaryCard } from "@/components/app/ContractDraftSections";

export default function ContractViewerPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [contract, setContract] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [accepted, setAccepted] = useState(false);
  const [signerName, setSignerName] = useState("");
  const [drawing, setDrawing] = useState(false);
  const canvasRef = useRef();

  const [pdfVersions, setPdfVersions] = useState([]);
  const [showPreview, setShowPreview] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState(null);
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (showPreview && !previewBlobUrl) {
      (async () => {
        try {
          const resp = await api.get(`/contracts/${id}/pdf/preview`, { responseType: "blob" });
          setPreviewBlobUrl(URL.createObjectURL(resp.data));
        } catch (e) {
          toast.error("Errore caricamento anteprima PDF");
        }
      })();
    }
    return () => { /* keep URL for reuse */ };
  }, [showPreview]);

  const load = async () => {
    try {
      const [c, t, pl] = await Promise.all([
        api.get(`/contracts/${id}`),
        api.get(`/contracts/${id}/timeline`),
        api.get(`/contracts/${id}/pdf/list`).catch(() => ({ data: { versions: [] } })),
      ]);
      setContract(c.data);
      setTimeline(t.data);
      setPdfVersions(pl.data.versions || []);
    } catch (e) {
      toast.error("Errore caricamento contratto");
    }
  };

  const generatePdf = async () => {
    try {
      const { data } = await api.post(`/contracts/${id}/pdf/generate`);
      toast.success(`PDF v${data.version} archiviato — hash ${data.hash?.slice(0, 12)}…`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore generazione PDF");
    }
  };

  const downloadPdf = async (version) => {
    try {
      const resp = await api.get(`/contracts/${id}/pdf/download/${version}`, { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url; a.download = `contract-${contract?.number}-v${version}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Errore download");
    }
  };

  const previewUrl = null; // superseded by blob URL via api client (auth)

  const transition = async (to_state, reason) => {
    try {
      await api.post(`/contracts/${id}/transition`, { to_state, reason });
      toast.success(`Stato → ${to_state}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore transizione");
    }
  };

  // Canvas signature
  const startDraw = (e) => {
    setDrawing(true);
    const ctx = canvasRef.current.getContext("2d");
    ctx.beginPath();
    const rect = canvasRef.current.getBoundingClientRect();
    ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top);
  };
  const draw = (e) => {
    if (!drawing) return;
    const ctx = canvasRef.current.getContext("2d");
    const rect = canvasRef.current.getBoundingClientRect();
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#000";
    ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top);
    ctx.stroke();
  };
  const stopDraw = () => setDrawing(false);
  const clearSig = () => {
    const ctx = canvasRef.current.getContext("2d");
    ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
  };

  const sign = async () => {
    if (!accepted || !signerName) {
      toast.error("Nome e accettazione condizioni obbligatori");
      return;
    }
    const dataUrl = canvasRef.current.toDataURL("image/png");
    try {
      await api.post(`/contracts/${id}/sign`, {
        signer_name: signerName,
        signature_data_url: dataUrl,
        accept_terms: accepted,
      });
      toast.success("Contratto firmato — immutabile");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore firma");
    }
  };

  if (!contract) return <div className="p-6">Caricamento…</div>;

  const snap = contract.quote_snapshot || {};
  const signed = contract.contract_status === "signed";

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto" data-testid="contract-viewer">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">Contratto {contract.number}</h1>
          <div className="flex gap-2 mt-2">
            <Badge variant={signed ? "default" : "secondary"} data-testid="contract-status">{contract.contract_status}</Badge>
            {contract.snapshot_hash && (
              <Badge variant="outline" className="font-mono text-xs">hash: {contract.snapshot_hash.slice(0, 12)}…</Badge>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {contract.contract_status === "draft" && (
            <Button size="sm" onClick={() => transition("ready_for_review")} data-testid="btn-ready-review">
              Pronto per revisione
            </Button>
          )}
          {contract.contract_status === "ready_for_review" && (
            <Button size="sm" onClick={() => transition("ready_for_signature")} data-testid="btn-ready-sign">
              Pronto per firma
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setShowPreview(v => !v)} data-testid="btn-preview-pdf">
            {showPreview ? "Nascondi PDF" : "Anteprima PDF"}
          </Button>
          <Button size="sm" variant="outline" onClick={generatePdf} data-testid="btn-generate-pdf">
            Archivia PDF
          </Button>
          {["draft", "ready_for_review", "ready_for_signature", "sent", "viewed", "rejected", "expired"].includes(contract.contract_status) && (
            <Button size="sm" variant="destructive" onClick={() => transition("cancelled", "Annullato dall'utente")}>
              Annulla
            </Button>
          )}
        </div>
      </div>

      {/* PDF Preview inline */}
      {showPreview && (
        <Card>
          <CardHeader><CardTitle>Anteprima PDF</CardTitle></CardHeader>
          <CardContent>
            <iframe
              src={previewBlobUrl || "about:blank"}
              width="100%" height="700"
              style={{ border: "1px solid #ddd", borderRadius: "4px" }}
              data-testid="pdf-preview-iframe"
              title="Anteprima contratto PDF"
            />
          </CardContent>
        </Card>
      )}

      {/* PDF Versions */}
      {pdfVersions.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Documenti PDF archiviati ({pdfVersions.length})</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow>
                <TableHead>V.</TableHead><TableHead>Tipo</TableHead>
                <TableHead>Data</TableHead><TableHead>Hash</TableHead>
                <TableHead>Size</TableHead><TableHead></TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {pdfVersions.map(v => (
                  <TableRow key={v.version} data-testid={`pdf-version-${v.version}`}>
                    <TableCell>v{v.version}</TableCell>
                    <TableCell><Badge>{v.kind}</Badge></TableCell>
                    <TableCell className="text-xs">{v.generated_at ? new Date(v.generated_at).toLocaleString("it-IT") : "-"}</TableCell>
                    <TableCell className="font-mono text-xs">{v.hash?.slice(0, 16)}…</TableCell>
                    <TableCell className="text-xs">{Math.round((v.size_bytes || 0) / 1024)} KB</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => downloadPdf(v.version)}
                               data-testid={`btn-download-v${v.version}`}>Scarica</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* msg 803 — Contract Draft: pre-firma check, cliente/cantiere modificabili, oggetto del contratto */}
      {!signed && <PresignCheckBanner contractId={id} refreshKey={contract.updated_at} />}
      {contract.lifecycle_status === "ACTIVE" && <div className="rounded-sm border border-emerald-600/40 bg-emerald-500/10 p-3 text-sm font-bold text-emerald-800" data-testid="contract-active">CONTRATTO ATTIVO — snapshot firmato congelato il {contract.signed_snapshot?.frozen_at ? new Date(contract.signed_snapshot.frozen_at).toLocaleString("it-IT") : ""}. Correzioni solo tramite Addendum / Revisione.</div>}
      <PartiesEditor contract={contract} onSaved={load} />
      <QuoteSummaryCard contract={contract} />

      {/* Intestazione azienda + cliente */}
      <Card>
        <CardHeader><CardTitle>Intestazione</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <div className="text-xs text-muted-foreground uppercase mb-1">Azienda</div>
              <div className="font-semibold">{snap.company?.name}</div>
              <div className="text-sm">P.IVA {snap.company?.vat}</div>
              <div className="text-sm">{formatAddress(snap.company?.address)}</div>
              <div className="text-sm">{snap.company?.email}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground uppercase mb-1">Cliente</div>
              <div className="font-semibold" data-testid="customer-name">{snap.customer?.company_name || [snap.customer?.first_name, snap.customer?.last_name].filter(Boolean).join(" ") || snap.customer?.name || "-"}</div>
              <div className="text-sm">{snap.customer?.email}</div>
              <div className="text-sm">{snap.customer?.phone}</div>
              <div className="text-sm">{formatAddress(snap.customer?.address)}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Prodotti / ambienti / vani */}
      <Card>
        <CardHeader><CardTitle>Prodotti ({(snap.products || []).length})</CardTitle></CardHeader>
        <CardContent>
          {(snap.environments || []).length > 0 && (
            <div className="mb-4">
              <div className="text-xs text-muted-foreground mb-1">Ambienti</div>
              <div className="flex flex-wrap gap-2">
                {snap.environments.map(e => (
                  <Badge key={e.id} variant="secondary">{e.name}</Badge>
                ))}
              </div>
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Vano</TableHead>
                <TableHead>Descrizione</TableHead>
                <TableHead>Dim.</TableHead>
                <TableHead>Qty</TableHead>
                <TableHead>Prezzo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(snap.products || []).map((p, i) => (
                <TableRow key={i} data-testid={`product-row-${i}`}>
                  <TableCell className="text-xs">{p.opening_id?.slice(0, 6) || i + 1}</TableCell>
                  <TableCell className="text-xs">{p.description || p.category}</TableCell>
                  <TableCell className="font-mono text-xs">{p.dimensions?.width_mm || "?"} × {p.dimensions?.height_mm || "?"}</TableCell>
                  <TableCell>{p.quantity}</TableCell>
                  <TableCell className="font-mono text-xs">{(p.total_price || p.unit_price || 0).toFixed(2)} €</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Importi */}
      <Card>
        <CardHeader><CardTitle>Importi</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-1 text-sm max-w-xs ml-auto">
            <div className="flex justify-between"><span>Subtotale:</span><span className="font-mono">{(snap.quote_totals?.subtotal || 0).toFixed(2)} €</span></div>
            <div className="flex justify-between"><span>Sconto:</span><span className="font-mono">-{(snap.quote_totals?.discount || 0).toFixed(2)} €</span></div>
            <div className="flex justify-between"><span>IVA:</span><span className="font-mono">{(snap.quote_totals?.tax || 0).toFixed(2)} €</span></div>
            <div className="flex justify-between text-lg font-bold pt-2 border-t"><span>Totale:</span><span className="font-mono" data-testid="total-amount">{(snap.quote_totals?.total || 0).toFixed(2)} €</span></div>
          </div>
        </CardContent>
      </Card>

      {/* Condizioni Generali — testo canonico congelato */}
      {snap.general_terms?.articles?.length > 0 && (
        <Card data-testid="contract-general-terms-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-2">
              <span>Condizioni Generali di Contratto</span>
              <Badge variant="outline" data-testid="contract-gt-version">{snap.general_terms.version}</Badge>
            </CardTitle>
            <div className="text-xs text-muted-foreground font-mono break-all" data-testid="contract-gt-hash">
              SHA-256 {snap.general_terms.general_terms_hash} · {snap.general_terms.articles.length} articoli · in vigore dal {snap.general_terms.effective_from}
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm max-h-[420px] overflow-y-auto pr-2" data-testid="contract-gt-articles">
              {snap.general_terms.articles.map((a) => (
                <div key={a.code} className="pb-2 border-b" data-testid={`gt-article-${a.code}`}>
                  <div className="font-semibold">Articolo {a.number} – {a.title}</div>
                  <div className="text-xs whitespace-pre-line text-muted-foreground">{a.text}</div>
                </div>
              ))}
              <div className="pt-2" data-testid="gt-clause-approval">
                <div className="font-semibold">{snap.general_terms.clause_approval?.title}</div>
                <div className="text-xs whitespace-pre-line text-muted-foreground">{snap.general_terms.clause_approval?.text}</div>
                <div className="text-xs whitespace-pre-line text-muted-foreground mt-2">{snap.general_terms.clause_approval?.second_approval_text}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Clausole legacy (contratti generati prima della versione canonica) */}
      {!snap.general_terms && (snap.clauses || []).length > 0 && (
        <Card>
          <CardHeader><CardTitle>Condizioni e clausole ({snap.clauses.length})</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3 text-sm">
              {snap.clauses.map((c, i) => (
                <div key={i} className="pb-2 border-b" data-testid={`clause-${i}`}>
                  <div className="font-semibold">{c.title || `Clausola ${i + 1}`}</div>
                  <div className="text-xs whitespace-pre-wrap text-muted-foreground">{c.body || c.text || c.content}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Firma o info firmato */}
      {!signed ? (
        <Card>
          <CardHeader><CardTitle>Firma elettronica</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Nome firmatario</Label>
              <Input value={signerName} onChange={(e) => setSignerName(e.target.value)}
                      placeholder="Nome e cognome" data-testid="input-signer-name"/>
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox id="accept" checked={accepted}
                         onCheckedChange={setAccepted} data-testid="check-accept-terms"/>
              <label htmlFor="accept" className="text-sm">
                Ho letto integralmente il contratto, le Condizioni Generali {snap.general_terms?.version ? `(${snap.general_terms.version})` : ""} e approvo espressamente le clausole onerose ai sensi degli artt. 1341 e 1342 c.c.
              </label>
            </div>
            <div>
              <Label>Firma (disegna nel riquadro)</Label>
              <div className="border-2 rounded bg-white">
                <canvas ref={canvasRef} width={500} height={150}
                         className="cursor-crosshair touch-none"
                         onMouseDown={startDraw} onMouseMove={draw}
                         onMouseUp={stopDraw} onMouseLeave={stopDraw}
                         data-testid="signature-canvas"/>
              </div>
              <Button variant="outline" size="sm" onClick={clearSig} className="mt-2">Cancella firma</Button>
            </div>
            <Button onClick={sign} disabled={!accepted || !signerName || contract.contract_status !== "ready_for_signature"}
                     data-testid="btn-sign-contract">
              Firma contratto
            </Button>
            {contract.contract_status !== "ready_for_signature" && (
              <p className="text-xs text-muted-foreground">
                Il contratto deve essere in stato "ready_for_signature" per la firma.
              </p>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card className="border-green-600">
          <CardHeader><CardTitle className="text-green-600">Contratto firmato</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>Firmato da: <b>{contract.signed_by_name}</b></div>
            <div>Data: {contract.signed_at ? new Date(contract.signed_at).toLocaleString("it-IT") : "-"}</div>
            <div>IP: {contract.signed_ip}</div>
            <div>Tipo firma: <Badge>{contract.signature_type || "electronic_simple"}</Badge></div>
            <div className="font-mono text-xs mt-2">
              Hash firma: {contract.signature_hash}
            </div>
            {contract.signature_data_url && (
              <img src={contract.signature_data_url} alt="firma" className="mt-2 border rounded max-w-xs bg-white"/>
            )}
          </CardContent>
        </Card>
      )}

      {/* Timeline */}
      {timeline?.state_history && (
        <Card>
          <CardHeader><CardTitle>Cronologia stati</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {timeline.state_history.map((s, i) => (
                <div key={i} className="flex items-center gap-3 pb-2 border-b" data-testid={`timeline-${i}`}>
                  <Badge>{s.state}</Badge>
                  <span className="text-muted-foreground">{new Date(s.at).toLocaleString("it-IT")}</span>
                  <span>{s.by_email || s.by_name || "sistema"}</span>
                  {s.reason && <span className="text-muted-foreground italic">— {s.reason}</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
