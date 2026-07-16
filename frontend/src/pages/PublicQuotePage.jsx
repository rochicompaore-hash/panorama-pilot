/** Public read-only quote portal — /p/:token
 *
 * SEPARATE from the internal app layout. No sidebar/menu. Minimal footprint.
 * Robots meta noindex/nofollow set at runtime.
 */
import React from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FilePdf, Download, WarningCircle, ArrowClockwise, Phone, Envelope } from "@phosphor-icons/react";
import { toast, Toaster } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

function fmt(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0); } catch { return "€ 0"; } }
function fmtDate(s) { if (!s) return ""; try { return new Date(s).toLocaleDateString("it-IT"); } catch { return s; } }

export default function PublicQuotePage() {
  const { token } = useParams();
  const [state, setState] = React.useState({ loading: true, data: null, error: null });
  const [downloading, setDownloading] = React.useState(false);

  React.useEffect(() => {
    // Set robots meta noindex
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow, noarchive, nosnippet";
    document.head.appendChild(meta);
    return () => { document.head.removeChild(meta); };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/public/quotes/${token}`)
      .then((r) => { if (!cancelled) setState({ loading: false, data: r.data, error: null }); })
      .catch((e) => {
        if (cancelled) return;
        const status = e.response?.status;
        const msg = e.response?.data?.detail || "Errore di caricamento";
        setState({ loading: false, data: null, error: { status, msg } });
      });
    return () => { cancelled = true; };
  }, [token]);

  const downloadPdf = async () => {
    setDownloading(true);
    try {
      const res = await axios.get(`${API}/api/public/quotes/${token}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = "preventivo.pdf"; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Impossibile scaricare il documento");
    } finally { setDownloading(false); }
  };

  if (state.loading) return <PublicShell><div className="text-center py-16 text-muted-foreground">Caricamento…</div></PublicShell>;
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
  const canDownload = (d.allowed_actions || []).includes("download");
  const style = {
    "--brand-p": d.primary_color || "#0F1720",
    "--brand-s": d.secondary_color || "#D42027",
  };

  return (
    <PublicShell style={style}>
      <Toaster richColors />
      {/* Header */}
      <header className="border-b border-border pb-4 mb-6 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {d.company_logo_url ? (
            <img src={d.company_logo_url} alt="" className="max-h-14 max-w-40" />
          ) : (
            <div className="font-display text-xl font-black" style={{ color: "var(--brand-p)" }}>{d.company_name}</div>
          )}
        </div>
        <div className="text-xs text-right">
          {d.company_phone && <div className="flex items-center justify-end gap-1"><Phone size={12} /> {d.company_phone}</div>}
          {d.company_email && <div className="flex items-center justify-end gap-1 text-muted-foreground"><Envelope size={12} /> {d.company_email}</div>}
        </div>
      </header>

      {/* Alerts */}
      {d.is_superseded && (
        <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 p-4 mb-4 text-sm" data-testid="alert-superseded">
          <b>Revisione superata.</b> Questa revisione è stata sostituita da una versione più recente. Contatta il tuo consulente per l'aggiornamento.
        </div>
      )}
      {d.is_expired && !d.is_superseded && (
        <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 p-4 mb-4 text-sm" data-testid="alert-expired">
          <b>Preventivo scaduto.</b> Questo preventivo è scaduto. Contatta il tuo consulente per richiedere un aggiornamento.
        </div>
      )}

      {/* Cover */}
      <div className="mb-8" data-testid="quote-cover">
        <div className="text-xs uppercase tracking-widest text-muted-foreground font-mono-plex">Preventivo</div>
        <h1 className="mt-1 font-display text-4xl sm:text-5xl font-black tracking-tight" style={{ color: "var(--brand-p)" }}>
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

      {/* Intro */}
      {d.intro_text && (
        <div className="mb-6 text-sm leading-relaxed">{d.intro_text}</div>
      )}

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

      {/* PDF actions */}
      <div className="flex flex-wrap gap-3 mb-8">
        {d.has_pdf && canDownload && (
          <Button size="lg" className="rounded-sm" onClick={downloadPdf} disabled={downloading} data-testid="public-download-pdf">
            {downloading ? <ArrowClockwise size={18} className="mr-2 animate-spin" /> : <Download size={18} className="mr-2" />}
            Scarica il preventivo (PDF)
          </Button>
        )}
        {d.has_pdf && (
          <a href={`${API}/api/public/quotes/${token}/pdf`} target="_blank" rel="noopener noreferrer" data-testid="public-open-pdf">
            <Button variant="outline" size="lg" className="rounded-sm">
              <FilePdf size={18} className="mr-2" /> Apri PDF completo
            </Button>
          </a>
        )}
      </div>

      {/* Contact info */}
      <Card className="rounded-sm border-border p-4 text-xs text-muted-foreground">
        Per qualsiasi domanda contatta il tuo consulente {d.sales_rep_name || d.company_name}.
        {d.company_phone && <> Telefono: <b>{d.company_phone}</b>.</>}
        {d.company_email && <> Email: <b>{d.company_email}</b>.</>}
      </Card>

      <footer className="mt-10 text-[10px] text-muted-foreground text-center border-t border-border pt-4">
        Questo documento è riservato al destinatario. Non condividere il link.
        {d.watermark && <span className="ml-2"><Badge variant="outline" className="rounded-sm text-[9px]">{d.watermark}</Badge></span>}
      </footer>
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
