/** Public read-only quote portal — /p/:token
 *
 * M3.3.3: read-only view + PDF download.
 * M3.3.4: OTP + electronic signature (canvas), request-changes, reject, signed-PDF download.
 */
import React from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "@/components/ui/input-otp";
import {
  FilePdf, Download, WarningCircle, ArrowClockwise, Phone, Envelope,
  Signature, ChatCircleText, XCircle, CheckCircle, ShieldCheck,
} from "@phosphor-icons/react";
import { toast, Toaster } from "sonner";
import SignatureCanvas from "@/components/app/SignatureCanvas";

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0); } catch { return "€ 0"; } }
function fmtDate(s) { if (!s) return ""; try { return new Date(s).toLocaleDateString("it-IT"); } catch { return s; } }

export default function PublicQuotePage() {
  const { token } = useParams();
  const [state, setState] = React.useState({ loading: true, data: null, error: null });
  const [downloading, setDownloading] = React.useState(false);
  const [signOpen, setSignOpen] = React.useState(false);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [changeOpen, setChangeOpen] = React.useState(false);
  const [signResult, setSignResult] = React.useState(null); // { evidence_id, signed_pdf_id }

  const reload = React.useCallback(() => {
    axios.get(`${API}/api/public/quotes/${token}`)
      .then((r) => setState({ loading: false, data: r.data, error: null }))
      .catch((e) => {
        const status = e.response?.status;
        const msg = e.response?.data?.detail || "Errore di caricamento";
        setState({ loading: false, data: null, error: { status, msg } });
      });
  }, [token]);

  React.useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow, noarchive, nosnippet";
    document.head.appendChild(meta);
    return () => { try { document.head.removeChild(meta); } catch {} };
  }, []);
  React.useEffect(() => { reload(); }, [reload]);

  const downloadPdf = async (kind = "pdf") => {
    setDownloading(true);
    try {
      const url = kind === "signed" ? `${API}/api/public/quotes/${token}/signed-pdf` : `${API}/api/public/quotes/${token}/pdf`;
      const res = await axios.get(url, { responseType: "blob" });
      const blobUrl = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = blobUrl; a.download = kind === "signed" ? "preventivo_firmato.pdf" : "preventivo.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Impossibile scaricare il documento");
    } finally { setDownloading(false); }
  };

  if (state.loading) return <PublicShell><div className="text-center py-16 text-muted-foreground" data-testid="public-loading">Caricamento…</div></PublicShell>;
  if (state.error) {
    const map = {
      404: { title: "Link non disponibile", body: "Il collegamento non è valido o non è più disponibile." },
      410: { title: "Documento non disponibile", body: state.error.msg || "Questa versione non è più disponibile." },
      429: { title: "Accessi eccessivi", body: "Sono stati rilevati troppi tentativi. Riprova tra qualche minuto." },
      500: { title: "Errore temporaneo", body: "Riprova tra qualche istante." },
    };
    const e = map[state.error.status] || map[500];
    return <PublicShell>
      <Card className="rounded-sm border-border p-8 max-w-lg mx-auto text-center" data-testid="public-error">
        <WarningCircle size={48} className="mx-auto text-[hsl(var(--brand-red))] mb-4" />
        <h1 className="font-display text-2xl font-black mb-2">{e.title}</h1>
        <p className="text-sm text-muted-foreground">{e.body}</p>
      </Card>
    </PublicShell>;
  }

  const d = state.data;
  const actions = d.allowed_actions || [];
  const canDownload = actions.includes("download");
  const canDownloadSigned = actions.includes("download_signed");
  const canSign = actions.includes("sign");
  const canRequestChanges = actions.includes("request_changes");
  const canReject = actions.includes("reject");
  const isSigned = d.quote_status === "signed";
  const isRejected = d.quote_status === "rejected";
  const isChangeRequested = d.quote_status === "change_requested";
  const style = {
    "--brand-p": d.primary_color || "#0F1720",
    "--brand-s": d.secondary_color || "#D42027",
  };

  return (
    <PublicShell style={style}>
      <Toaster richColors position="top-center" />
      {/* Header */}
      <header className="border-b border-border pb-4 mb-6 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {d.company_logo_url ? (
            <img src={d.company_logo_url} alt="" className="max-h-14 max-w-40" />
          ) : (
            <div className="font-display text-xl font-black" style={{ color: "var(--brand-p)" }} data-testid="company-name">{d.company_name}</div>
          )}
        </div>
        <div className="text-xs text-right">
          {d.company_phone && <div className="flex items-center justify-end gap-1"><Phone size={12} /> {d.company_phone}</div>}
          {d.company_email && <div className="flex items-center justify-end gap-1 text-muted-foreground"><Envelope size={12} /> {d.company_email}</div>}
        </div>
      </header>

      {/* State alerts */}
      {isSigned && (
        <div className="rounded-sm border border-emerald-500/50 bg-emerald-500/10 p-4 mb-4 text-sm flex items-start gap-3" data-testid="alert-signed">
          <CheckCircle size={22} className="text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold text-emerald-900">Preventivo firmato</div>
            <div className="text-xs text-emerald-800/80">
              Il documento è stato accettato mediante firma elettronica semplice. Puoi scaricare il PDF firmato qui sotto.
            </div>
          </div>
        </div>
      )}
      {isChangeRequested && (
        <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 p-4 mb-4 text-sm" data-testid="alert-change-requested">
          <b>Modifica richiesta.</b> Abbiamo ricevuto la tua richiesta di modifica. Un consulente ti contatterà per gestire una nuova revisione.
        </div>
      )}
      {isRejected && (
        <div className="rounded-sm border border-red-500/50 bg-red-500/10 p-4 mb-4 text-sm" data-testid="alert-rejected">
          <b>Preventivo rifiutato.</b> Hai comunicato di non voler procedere. Puoi ancora consultare e scaricare il documento; contatta il tuo consulente se cambia idea.
        </div>
      )}
      {d.is_superseded && (
        <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 p-4 mb-4 text-sm" data-testid="alert-superseded">
          <b>Revisione superata.</b> Questa revisione è stata sostituita da una versione più recente. Contatta il tuo consulente per l'aggiornamento.
        </div>
      )}
      {d.is_expired && !d.is_superseded && !isSigned && (
        <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 p-4 mb-4 text-sm" data-testid="alert-expired">
          <b>Preventivo scaduto.</b> Questo preventivo è scaduto. Contatta il tuo consulente per richiedere un aggiornamento.
        </div>
      )}

      {/* Cover */}
      <div className="mb-8" data-testid="quote-cover">
        <div className="text-xs uppercase tracking-widest text-muted-foreground font-mono-plex">Preventivo</div>
        <h1 className="mt-1 font-display text-4xl sm:text-5xl font-black tracking-tight" style={{ color: "var(--brand-p)" }} data-testid="quote-number">
          {d.quote_number}
        </h1>
        <div className="mt-1 text-sm text-muted-foreground">
          Revisione <b>{d.quote_revision}</b>
          {d.issue_date && <> · Emesso il <b>{fmtDate(d.issue_date)}</b></>}
          {d.valid_until && <> · Valido fino al <b>{fmtDate(d.valid_until)}</b></>}
        </div>
      </div>

      {/* Meta grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="rounded-sm border-border p-4">
          <div className="overline">Cliente</div>
          <div className="mt-1 font-bold">{d.customer_name || "—"}</div>
        </Card>
        <Card className="rounded-sm border-border p-4">
          <div className="overline">Cantiere</div>
          {d.site_address ? (
            <>
              <div className="mt-1 font-bold">{d.site_address.street}</div>
              <div className="text-xs text-muted-foreground">{d.site_address.zip_code} {d.site_address.city} {d.site_address.province ? `(${d.site_address.province})` : ""}</div>
            </>
          ) : <div className="text-xs text-muted-foreground mt-1">Non specificato</div>}
        </Card>
        <Card className="rounded-sm border-border p-4">
          <div className="overline">Riferimento commerciale</div>
          <div className="mt-1 font-bold">{d.sales_rep_name || "—"}</div>
          {d.sales_rep_email && <div className="text-xs text-muted-foreground">{d.sales_rep_email}</div>}
          {d.sales_rep_phone && <div className="text-xs">{d.sales_rep_phone}</div>}
        </Card>
      </div>

      {d.intro_text && <div className="mb-6 text-sm leading-relaxed">{d.intro_text}</div>}

      {/* Economic summary */}
      <Card className="rounded-sm border-border p-6 mb-6" style={{ borderLeft: `3px solid var(--brand-p)` }}>
        <div className="overline mb-3">Riepilogo economico</div>
        <div className="space-y-1 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Imponibile</span><span className="font-mono-plex">{fmt(d.subtotal)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">IVA</span><span className="font-mono-plex">{fmt(d.vat_amount)}</span></div>
          <div className="flex justify-between pt-3 mt-3 border-t border-border"><span className="font-bold text-lg">Totale</span><span className="font-mono-plex text-2xl font-black" style={{ color: "var(--brand-p)" }} data-testid="public-total">{fmt(d.total)}</span></div>
        </div>
        {d.payment_terms_display && (
          <div className="mt-4 pt-4 border-t border-border">
            <div className="overline mb-1">Condizioni di pagamento</div>
            <div className="text-sm">{d.payment_terms_display}</div>
          </div>
        )}
      </Card>

      {/* PDF & action buttons */}
      <div className="flex flex-wrap gap-3 mb-8">
        {d.has_pdf && canDownload && (
          <Button size="lg" className="rounded-sm" onClick={() => downloadPdf("pdf")} disabled={downloading} data-testid="public-download-pdf">
            {downloading ? <ArrowClockwise size={18} className="mr-2 animate-spin" /> : <Download size={18} className="mr-2" />}
            Scarica preventivo (PDF)
          </Button>
        )}
        {canDownloadSigned && (
          <Button size="lg" className="rounded-sm bg-emerald-600 hover:bg-emerald-700" onClick={() => downloadPdf("signed")} data-testid="public-download-signed">
            <ShieldCheck size={18} className="mr-2" /> Scarica PDF firmato
          </Button>
        )}
        {canSign && (
          <Button size="lg" className="rounded-sm" style={{ backgroundColor: "var(--brand-p)" }}
                  onClick={() => setSignOpen(true)} data-testid="public-open-sign">
            <Signature size={18} className="mr-2" /> Firma il preventivo
          </Button>
        )}
        {canRequestChanges && (
          <Button size="lg" variant="outline" className="rounded-sm" onClick={() => setChangeOpen(true)} data-testid="public-open-request-changes">
            <ChatCircleText size={18} className="mr-2" /> Richiedi modifica
          </Button>
        )}
        {canReject && (
          <Button size="lg" variant="ghost" className="rounded-sm text-red-700 hover:bg-red-50" onClick={() => setRejectOpen(true)} data-testid="public-open-reject">
            <XCircle size={18} className="mr-2" /> Rifiuta
          </Button>
        )}
      </div>

      {/* Contact card */}
      <Card className="rounded-sm border-border p-4 text-xs text-muted-foreground">
        Per qualsiasi domanda contatta il tuo consulente {d.sales_rep_name || d.company_name}.
        {d.company_phone && <> Telefono: <b>{d.company_phone}</b>.</>}
        {d.company_email && <> Email: <b>{d.company_email}</b>.</>}
      </Card>

      <footer className="mt-10 text-[10px] text-muted-foreground text-center border-t border-border pt-4">
        Questo documento è riservato al destinatario. Non condividere il link.
        {d.watermark && <span className="ml-2"><Badge variant="outline" className="rounded-sm text-[9px]">{d.watermark}</Badge></span>}
      </footer>

      {/* SIGNATURE DIALOG */}
      {signOpen && (
        <SignatureDialog
          token={token}
          quoteNumber={d.quote_number}
          companyName={d.company_name}
          onClose={() => setSignOpen(false)}
          onSuccess={(res) => {
            setSignOpen(false);
            setSignResult(res);
            toast.success("Firma acquisita con successo");
            setTimeout(reload, 800);
          }}
        />
      )}
      {/* REQUEST CHANGES */}
      {changeOpen && (
        <RequestChangesDialog token={token}
          onClose={() => setChangeOpen(false)}
          onSuccess={() => { setChangeOpen(false); toast.success("Richiesta inviata"); setTimeout(reload, 800); }} />
      )}
      {/* REJECT */}
      {rejectOpen && (
        <RejectDialog token={token}
          onClose={() => setRejectOpen(false)}
          onSuccess={() => { setRejectOpen(false); toast.success("Rifiuto registrato"); setTimeout(reload, 800); }} />
      )}

      {/* Success post-sign */}
      {signResult && (
        <Dialog open onOpenChange={() => setSignResult(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><CheckCircle size={22} className="text-emerald-600" /> Firma completata</DialogTitle>
              <DialogDescription>
                Il documento è stato accettato mediante firma elettronica semplice.
              </DialogDescription>
            </DialogHeader>
            <div className="text-sm">
              <div className="mb-2"><span className="text-muted-foreground">Evidence ID: </span><b className="font-mono-plex">{signResult.evidence_id}</b></div>
              <div className="text-xs text-muted-foreground">Conserva questo riferimento come prova della firma.</div>
            </div>
            <DialogFooter>
              <Button onClick={() => { setSignResult(null); downloadPdf("signed"); }} data-testid="post-sign-download">
                <Download size={16} className="mr-2" /> Scarica PDF firmato
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </PublicShell>
  );
}


function PublicShell({ children, style }) {
  return (
    <div className="min-h-screen bg-background" style={style} data-testid="public-portal">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </div>
    </div>
  );
}


// ==========================================================================
// Signature dialog — multi-step: 1) request OTP  2) verify OTP  3) canvas + consents  4) submit
// ==========================================================================
function SignatureDialog({ token, quoteNumber, companyName, onClose, onSuccess }) {
  const [step, setStep] = React.useState(1); // 1=email 2=verify 3=sign 4=submitting
  const [email, setEmail] = React.useState("");
  const [otpReq, setOtpReq] = React.useState(null); // {request_id, recipient_masked, expires_in_seconds, max_attempts}
  const [otpCode, setOtpCode] = React.useState("");
  const [otpVerified, setOtpVerified] = React.useState(false);
  const [firstName, setFirstName] = React.useState("");
  const [lastName, setLastName] = React.useState("");
  const [fiscalRole, setFiscalRole] = React.useState("");
  const [companyRepr, setCompanyRepr] = React.useState("");
  const [sigData, setSigData] = React.useState(null);
  const [consents, setConsents] = React.useState({
    accept_terms: false, accept_privacy: false, accept_payment_terms: false, consent_electronic_sign: false,
  });
  const [busy, setBusy] = React.useState(false);
  const [cooldownS, setCooldownS] = React.useState(0);

  React.useEffect(() => {
    if (cooldownS <= 0) return;
    const t = setTimeout(() => setCooldownS(cooldownS - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldownS]);

  const requestOtp = async () => {
    if (!email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) { toast.error("Email non valida"); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/public/quotes/${token}/request-otp`, { email });
      setOtpReq(r.data);
      setStep(2);
      setOtpCode("");
      toast.success(`Codice inviato a ${r.data.recipient_masked}`);
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      if (status === 429 && typeof detail === "object" && detail.error === "cooldown") {
        const retry = parseInt(e.response.headers["retry-after"] || "60", 10);
        setCooldownS(retry);
        toast.error(detail.message || `Attendi ${retry}s prima di richiedere un nuovo codice`);
      } else if (status === 429) {
        toast.error("Troppi tentativi. Riprova più tardi.");
      } else if (status === 503) {
        toast.error("Servizio firma temporaneamente non disponibile. Riprova più tardi.");
      } else {
        toast.error((typeof detail === "string" ? detail : detail?.message) || "Errore invio codice");
      }
    } finally { setBusy(false); }
  };

  const verifyOtp = async () => {
    if ((otpCode || "").length < 4) { toast.error("Inserisci il codice"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/api/public/quotes/${token}/verify-otp`, {
        request_id: otpReq.request_id, code: otpCode,
      });
      setOtpVerified(true);
      setStep(3);
      toast.success("Codice verificato");
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : detail?.message || "Codice non valido";
      toast.error(msg);
    } finally { setBusy(false); }
  };

  const submit = async () => {
    if (!firstName.trim() || !lastName.trim()) { toast.error("Nome e cognome sono obbligatori"); return; }
    if (!sigData?.data_url) { toast.error("Effettua la firma sul riquadro"); return; }
    for (const k of Object.keys(consents)) {
      if (!consents[k]) { toast.error("È necessario accettare tutte le dichiarazioni"); return; }
    }
    setBusy(true);
    setStep(4);
    try {
      const payload = {
        otp_request_id: otpReq.request_id,
        otp_code: otpCode,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        fiscal_role: fiscalRole || null,
        company_represented: companyRepr || null,
        signature: sigData,
        ...consents,
        client_timestamp_ms: Date.now(),
      };
      const r = await axios.post(`${API}/api/public/quotes/${token}/sign`, payload);
      onSuccess(r.data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : detail?.message || "Errore durante la firma";
      toast.error(msg);
      setStep(3);
    } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[95vh] overflow-y-auto" data-testid="signature-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Signature size={22} /> Firma elettronica del preventivo</DialogTitle>
          <DialogDescription>
            {quoteNumber} · {companyName}. La firma qui apposta ha valore di <b>firma elettronica semplice</b>.
          </DialogDescription>
        </DialogHeader>

        <div className="text-xs text-muted-foreground border-l-2 border-border pl-3 mb-2 flex items-center gap-4">
          <StepDot n={1} active={step===1} done={step>1}>Email</StepDot>
          <StepDot n={2} active={step===2} done={otpVerified}>Verifica</StepDot>
          <StepDot n={3} active={step===3} done={false}>Firma</StepDot>
        </div>

        {step === 1 && (
          <div className="space-y-3">
            <Label htmlFor="sig-email">Inserisci la tua email per ricevere il codice di verifica</Label>
            <Input id="sig-email" type="email" placeholder="tua@email.it" value={email} onChange={(e) => setEmail(e.target.value)}
                   className="rounded-sm" data-testid="sig-email-input" autoFocus />
            <div className="text-xs text-muted-foreground">Riceverai un codice a 6 cifre valido 10 minuti.</div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <div className="text-sm">Abbiamo inviato un codice a <b>{otpReq?.recipient_masked}</b>.</div>
            <Label>Inserisci il codice ricevuto</Label>
            <InputOTP maxLength={6} value={otpCode} onChange={setOtpCode} data-testid="sig-otp-input">
              <InputOTPGroup>
                {[0,1,2,3,4,5].map((i) => <InputOTPSlot key={i} index={i} />)}
              </InputOTPGroup>
            </InputOTP>
            <div className="flex items-center justify-between text-xs">
              <Button variant="link" size="sm" onClick={requestOtp} disabled={busy || cooldownS > 0} data-testid="sig-otp-resend" className="p-0 h-auto">
                {cooldownS > 0 ? `Rinvia codice tra ${cooldownS}s` : "Rinvia codice"}
              </Button>
              <span className="text-muted-foreground">Max tentativi: {otpReq?.max_attempts || 5}</span>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Nome*</Label>
                <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="rounded-sm" data-testid="sig-firstname" />
              </div>
              <div>
                <Label>Cognome*</Label>
                <Input value={lastName} onChange={(e) => setLastName(e.target.value)} className="rounded-sm" data-testid="sig-lastname" />
              </div>
              <div>
                <Label>Ruolo (facoltativo)</Label>
                <Input placeholder="Titolare, Legale rappr…" value={fiscalRole} onChange={(e) => setFiscalRole(e.target.value)} className="rounded-sm" data-testid="sig-role" />
              </div>
              <div>
                <Label>Azienda rappresentata</Label>
                <Input placeholder="Se applicabile" value={companyRepr} onChange={(e) => setCompanyRepr(e.target.value)} className="rounded-sm" data-testid="sig-company" />
              </div>
            </div>

            <div>
              <Label className="mb-1 block">Firma qui</Label>
              <SignatureCanvas onChange={setSigData} data-testid="sig-canvas" />
            </div>

            <div className="space-y-2 text-sm">
              <label className="flex items-start gap-2 cursor-pointer" data-testid="chk-accept-terms">
                <Checkbox checked={consents.accept_terms} onCheckedChange={(v) => setConsents(s => ({ ...s, accept_terms: !!v }))} />
                <span>Ho letto e accetto le <b>condizioni contrattuali</b> riportate nel preventivo.</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer" data-testid="chk-accept-payment">
                <Checkbox checked={consents.accept_payment_terms} onCheckedChange={(v) => setConsents(s => ({ ...s, accept_payment_terms: !!v }))} />
                <span>Accetto i <b>termini di pagamento</b> indicati.</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer" data-testid="chk-accept-privacy">
                <Checkbox checked={consents.accept_privacy} onCheckedChange={(v) => setConsents(s => ({ ...s, accept_privacy: !!v }))} />
                <span>Ho preso visione dell'<b>informativa privacy</b>.</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer" data-testid="chk-consent-fes">
                <Checkbox checked={consents.consent_electronic_sign} onCheckedChange={(v) => setConsents(s => ({ ...s, consent_electronic_sign: !!v }))} />
                <span>Acconsento all'accettazione tramite <b>firma elettronica semplice</b>.</span>
              </label>
            </div>

            <div className="text-[11px] text-muted-foreground bg-amber-50 border-l-2 border-amber-500 p-3">
              La firma qui apposta è una <b>Firma Elettronica Semplice</b> e la verifica avviene tramite email.
              L'efficacia probatoria dipende dal processo e dalle evidenze raccolte; questo sistema non attesta il valore di firma qualificata o marca temporale certificata.
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="py-10 text-center">
            <ArrowClockwise size={32} className="mx-auto animate-spin text-muted-foreground" />
            <div className="mt-3 text-sm">Registrazione firma in corso…</div>
          </div>
        )}

        <DialogFooter className="flex gap-2">
          {step === 1 && (<>
            <Button variant="outline" onClick={onClose} className="rounded-sm">Annulla</Button>
            <Button onClick={requestOtp} disabled={busy} className="rounded-sm" data-testid="sig-request-otp">
              {busy ? <ArrowClockwise size={16} className="animate-spin mr-2" /> : <Envelope size={16} className="mr-2" />}
              Invia codice
            </Button>
          </>)}
          {step === 2 && (<>
            <Button variant="outline" onClick={() => setStep(1)} className="rounded-sm">Indietro</Button>
            <Button onClick={verifyOtp} disabled={busy || otpCode.length < 4} className="rounded-sm" data-testid="sig-verify-otp">
              {busy ? <ArrowClockwise size={16} className="animate-spin mr-2" /> : <CheckCircle size={16} className="mr-2" />}
              Verifica
            </Button>
          </>)}
          {step === 3 && (<>
            <Button variant="outline" onClick={onClose} className="rounded-sm">Annulla</Button>
            <Button onClick={submit} disabled={busy || !sigData} className="rounded-sm" style={{ backgroundColor: "var(--brand-p)" }} data-testid="sig-submit">
              <Signature size={16} className="mr-2" /> Firma
            </Button>
          </>)}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function StepDot({ n, active, done, children }) {
  const color = done ? "bg-emerald-500 text-white" : active ? "bg-black text-white" : "bg-muted text-muted-foreground";
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold ${color}`}>{done ? "✓" : n}</span>
      <span className={active ? "font-bold text-foreground" : ""}>{children}</span>
    </span>
  );
}


function RequestChangesDialog({ token, onClose, onSuccess }) {
  const [reason, setReason] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [contact, setContact] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const submit = async () => {
    if (reason.trim().length < 5) { toast.error("Descrivi la modifica richiesta"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/api/public/quotes/${token}/request-changes`, {
        reason: reason.trim(), notes: notes || null, preferred_callback: contact || null,
      });
      onSuccess();
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.message || "Errore");
    } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg" data-testid="request-changes-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ChatCircleText size={20} /> Richiedi una modifica</DialogTitle>
          <DialogDescription>Descrivi cosa vorresti modificare. Il tuo consulente ti ricontatterà.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Descrizione della modifica*</Label>
            <Textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} className="rounded-sm"
                      placeholder="Es. sostituire vetro con basso emissivo, cambiare colore, aggiungere una zanzariera…" data-testid="rc-reason" />
          </div>
          <div>
            <Label>Note aggiuntive</Label>
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} className="rounded-sm" data-testid="rc-notes" />
          </div>
          <div>
            <Label>Preferenza di contatto (facoltativo)</Label>
            <Input placeholder="Orari, giorni…" value={contact} onChange={(e) => setContact(e.target.value)} className="rounded-sm" data-testid="rc-contact" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-sm">Annulla</Button>
          <Button onClick={submit} disabled={busy} className="rounded-sm" data-testid="rc-submit">
            {busy ? <ArrowClockwise size={16} className="animate-spin mr-2" /> : null}
            Invia richiesta
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function RejectDialog({ token, onClose, onSuccess }) {
  const [reasonCode, setReasonCode] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/api/public/quotes/${token}/reject`, {
        reason_code: reasonCode || null, notes: notes || null,
      });
      onSuccess();
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.message || "Errore");
    } finally { setBusy(false); }
  };
  const opts = [
    { v: "price", l: "Prezzo" },
    { v: "delivery", l: "Tempi di consegna" },
    { v: "scope", l: "Ambito / prodotti" },
    { v: "other", l: "Altro" },
  ];
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg" data-testid="reject-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-700"><XCircle size={20} /> Rifiuta preventivo</DialogTitle>
          <DialogDescription>Non procederai con questo preventivo. Puoi indicare il motivo per aiutarci a migliorare.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Motivo (facoltativo)</Label>
            <div className="grid grid-cols-2 gap-2 mt-1" data-testid="reject-reason-group">
              {opts.map((o) => (
                <label key={o.v} className={`cursor-pointer rounded-sm border p-2 text-sm ${reasonCode === o.v ? "border-red-500 bg-red-50" : "border-border"}`}>
                  <input type="radio" name="reason" value={o.v} checked={reasonCode === o.v} onChange={() => setReasonCode(o.v)} className="mr-2" />
                  {o.l}
                </label>
              ))}
            </div>
          </div>
          <div>
            <Label>Note (facoltativo)</Label>
            <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} className="rounded-sm" data-testid="reject-notes" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-sm">Annulla</Button>
          <Button onClick={submit} disabled={busy} className="rounded-sm bg-red-600 hover:bg-red-700 text-white" data-testid="reject-submit">
            {busy ? <ArrowClockwise size={16} className="animate-spin mr-2" /> : null}
            Conferma rifiuto
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
