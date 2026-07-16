/**
 * PublicSchedulePage — Portale cliente per abaco tecnico (visualizzazione + firma FES)
 * Route: /p/schedule/:token
 * Nessuna autenticazione — solo il token identifica il documento.
 */
import React, { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

export default function PublicSchedulePage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [consents, setConsents] = useState({
    c1: false, c2: false, c3: false, c4: false, c5: false, c6: false,
  });
  const [signerName, setSignerName] = useState("");
  const [signerEmail, setSignerEmail] = useState("");
  const [signing, setSigning] = useState(false);
  const canvasRef = useRef(null);
  const drawing = useRef(false);

  useEffect(() => {
    axios.get(`${API}/api/public/schedules/${token}`)
      .then(r => setData(r.data))
      .catch(e => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, [token]);

  const canSign = Object.values(consents).every(Boolean) && signerName.length >= 3 && signerEmail.includes("@");

  const sign = async () => {
    if (!canvasRef.current) return;
    setSigning(true);
    try {
      const dataUrl = canvasRef.current.toDataURL("image/png");
      const { data: resp } = await axios.post(`${API}/api/public/schedules/${token}/sign`, {
        signer_name: signerName, signer_email: signerEmail,
        signature_data_url: dataUrl,
        consent_all_openings_verified: consents.c1,
        consent_measurements_verified: consents.c2,
        consent_colors_glass_openings_verified: consents.c3,
        consent_supersedes_preview: consents.c4,
        consent_authorize_production: consents.c5,
        consent_accept_variances_if_any: consents.c6,
      });
      toast.success("Abaco firmato! Ordine esecutivo creato.");
      setData(prev => ({ ...prev, schedule: { ...prev.schedule, ts_status: "signed" } }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Errore firma");
    } finally { setSigning(false); }
  };

  // Canvas signature handlers
  const startDraw = (e) => {
    drawing.current = true;
    const ctx = canvasRef.current.getContext("2d");
    const r = canvasRef.current.getBoundingClientRect();
    const x = (e.touches?.[0]?.clientX ?? e.clientX) - r.left;
    const y = (e.touches?.[0]?.clientY ?? e.clientY) - r.top;
    ctx.beginPath(); ctx.moveTo(x, y);
  };
  const moveDraw = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = canvasRef.current.getContext("2d");
    const r = canvasRef.current.getBoundingClientRect();
    const x = (e.touches?.[0]?.clientX ?? e.clientX) - r.left;
    const y = (e.touches?.[0]?.clientY ?? e.clientY) - r.top;
    ctx.lineTo(x, y); ctx.strokeStyle = "#0F1720"; ctx.lineWidth = 2; ctx.stroke();
  };
  const endDraw = () => { drawing.current = false; };
  const clearCanvas = () => {
    const ctx = canvasRef.current.getContext("2d");
    ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
  };

  if (loading) return <div className="p-8 text-center text-sm text-muted-foreground">Caricamento…</div>;
  if (error) return <div className="p-8 text-center text-red-600" data-testid="public-schedule-error">{error}</div>;
  if (!data) return null;

  const schedule = data.schedule;
  const isSigned = schedule.ts_status === "signed" || schedule.ts_status === "released_to_production";

  return (
    <div className="min-h-screen bg-neutral-50 py-8" data-testid="public-schedule-page">
      <div className="max-w-4xl mx-auto space-y-6 px-4">
        <div className="text-center">
          <div className="overline text-muted-foreground">Abaco tecnico definitivo</div>
          <h1 className="font-display text-2xl sm:text-4xl font-black tracking-tight" data-testid="public-schedule-number">
            {schedule.number} · {schedule.revision_label}
          </h1>
          {isSigned && (
            <Badge className="mt-2 rounded-sm" data-testid="schedule-signed-badge">Firmato — Ordine in produzione</Badge>
          )}
        </div>

        <Card className="rounded-sm">
          <CardHeader><CardTitle className="text-base">Vani rilevati ({(schedule.items || []).length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground border-b bg-muted">
                <tr>
                  <th className="text-left py-2 px-3">Vano</th>
                  <th className="text-left">Stanza</th>
                  <th className="text-left">Prodotto</th>
                  <th className="text-right">L (mm)</th>
                  <th className="text-right">H (mm)</th>
                  <th className="text-center">Ante</th>
                </tr>
              </thead>
              <tbody>
                {(schedule.items || []).map((it, i) => (
                  <tr key={i} className="border-b" data-testid={`public-item-row-${i}`}>
                    <td className="py-1.5 px-3 font-mono-plex">{it.ref}</td>
                    <td>{it.room || "—"}</td>
                    <td>{it.product_key}</td>
                    <td className="text-right font-mono-plex">{it.final_width_mm}</td>
                    <td className="text-right font-mono-plex">{it.final_height_mm}</td>
                    <td className="text-center">{it.nr_ante}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {!isSigned && (
          <Card className="rounded-sm">
            <CardHeader><CardTitle className="text-base">Firma dell'abaco</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="text-xs text-muted-foreground bg-amber-50 rounded-sm p-3">
                <strong>Importante</strong>: verifica ogni vano, misura, colore e apertura prima di firmare.
                Dopo la firma verrà avviata la produzione con queste misure DEFINITIVE.
                Le misure preventive del contratto vengono sostituite da questo documento.
              </div>
              <div className="space-y-2">
                {[
                  ["c1", "Ho verificato tutti i vani indicati"],
                  ["c2", "Ho verificato misure e configurazioni"],
                  ["c3", "Ho verificato colori, vetri e aperture"],
                  ["c4", "Comprendo che questo abaco sostituisce le misure preventive"],
                  ["c5", "Autorizzo l'avvio della produzione"],
                  ["c6", "Accetto eventuali varianti economiche già sottoscritte"],
                ].map(([k, label]) => (
                  <label key={k} className="flex items-start gap-2 text-sm" data-testid={`consent-${k}`}>
                    <Checkbox checked={consents[k]} onCheckedChange={v => setConsents(p => ({...p, [k]: !!v}))} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label>Nome e cognome</Label>
                  <Input value={signerName} onChange={e => setSignerName(e.target.value)} data-testid="signer-name-input"/>
                </div>
                <div>
                  <Label>Email</Label>
                  <Input value={signerEmail} onChange={e => setSignerEmail(e.target.value)} type="email" data-testid="signer-email-input"/>
                </div>
              </div>
              <div>
                <Label>Firma</Label>
                <canvas
                  ref={canvasRef}
                  width={600} height={160}
                  className="border rounded-sm w-full bg-white touch-none"
                  onMouseDown={startDraw} onMouseMove={moveDraw} onMouseUp={endDraw} onMouseLeave={endDraw}
                  onTouchStart={startDraw} onTouchMove={moveDraw} onTouchEnd={endDraw}
                  data-testid="signature-canvas"
                />
                <Button variant="ghost" size="sm" onClick={clearCanvas} className="mt-1 text-xs">Pulisci</Button>
              </div>
              <Button
                onClick={sign} disabled={!canSign || signing}
                className="w-full rounded-sm" data-testid="sign-schedule-btn"
              >
                {signing ? "Firma in corso…" : "Firma abaco e autorizza produzione"}
              </Button>
              {!canSign && (
                <div className="text-xs text-muted-foreground text-center">
                  Compila tutte le conferme, nome/email e disegna la firma per procedere.
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
