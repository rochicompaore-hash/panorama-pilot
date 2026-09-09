import React from "react";
import axios from "axios";
import { Routes, Route, Navigate, useNavigate, useParams, Link, useLocation } from "react-router-dom";
import { Home, FileText, LifeBuoy, User, ChevronRight, LogOut, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ProductVisualSVG } from "@/components/app/ProductVisualSVG";

/**
 * CUSTOMER PORTAL CORE V1 — area cliente mobile-first, token separato (cp_access_token), nessuna sidebar ERP.
 * Riusa QuoteLine.visual_spec -> ProductVisualSVG (nessun nuovo renderer).
 */
const cp = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api/customer-portal` });
cp.interceptors.request.use((c) => { const t = localStorage.getItem("cp_access_token"); if (t) c.headers.Authorization = `Bearer ${t}`; return c; });
const fmtEUR = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n || 0);
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("it-IT") : "—");
const errMsg = (e) => { const d = e?.response?.data?.detail; if (!d) return e.message; if (typeof d === "string") return d; if (Array.isArray(d)) return d.map((x) => x.msg).join(" "); return d.message || JSON.stringify(d); };

export default function CustomerPortal() {
  return (
    <div className="min-h-screen bg-[#F5F7F6] text-[#1F2937]" style={{ fontFamily: "Roboto, system-ui, sans-serif" }} data-testid="customer-portal">
      <Routes>
        <Route path="login" element={<CPLogin />} />
        <Route path="*" element={<CPGuard><Routes>
          <Route index element={<CPHome />} />
          <Route path="jobs/:id" element={<CPJob />} />
          <Route path="documents" element={<CPDocuments />} />
          <Route path="support" element={<CPSupport />} />
          <Route path="profile" element={<CPProfile />} />
          <Route path="*" element={<Navigate to="/customer-portal" replace />} />
        </Routes></CPGuard>} />
      </Routes>
    </div>
  );
}

function CPGuard({ children }) {
  const [state, setState] = React.useState(null);
  React.useEffect(() => { cp.get("/auth/me").then((r) => setState(r.data)).catch(() => setState(false)); }, []);
  if (state === null) return <div className="p-8 text-center text-sm text-gray-500">Caricamento…</div>;
  if (state === false) return <Navigate to="/customer-portal/login" replace />;
  return <CPShell user={state}>{children}</CPShell>;
}

function CPShell({ user, children }) {
  const loc = useLocation();
  const nav = [["/customer-portal", "Home", Home], ["/customer-portal/documents", "Documenti", FileText], ["/customer-portal/support", "Assistenza", LifeBuoy], ["/customer-portal/profile", "Profilo", User]];
  return (
    <div className="max-w-2xl mx-auto min-h-screen flex flex-col">
      <header className="px-5 pt-6 pb-4 flex items-center justify-between">
        <div><div className="text-[10px] tracking-[0.2em] uppercase font-bold text-[#12a16b]">Area cliente</div><div className="text-lg font-bold" data-testid="cp-welcome">Ciao {user.first_name || ""}</div></div>
      </header>
      <main className="flex-1 px-5 pb-24">{children}</main>
      <nav className="fixed bottom-0 inset-x-0 bg-white border-t border-gray-200" data-testid="cp-bottom-nav">
        <div className="max-w-2xl mx-auto grid grid-cols-4">
          {nav.map(([to, label, Icon]) => { const active = loc.pathname === to; return (
            <Link key={to} to={to} className={`flex flex-col items-center gap-1 py-3 text-[11px] font-medium ${active ? "text-[#12a16b]" : "text-gray-500"}`} data-testid={`cp-nav-${label.toLowerCase()}`}><Icon size={20} />{label}</Link>); })}
        </div>
      </nav>
    </div>
  );
}

function CPLogin() {
  const nav = useNavigate();
  const [email, setEmail] = React.useState(""); const [password, setPassword] = React.useState(""); const [err, setErr] = React.useState(""); const [busy, setBusy] = React.useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { const r = await cp.post("/auth/login", { email, password }); localStorage.setItem("cp_access_token", r.data.access_token); nav("/customer-portal"); }
    catch (ex) { setErr(errMsg(ex)); } finally { setBusy(false); }
  };
  return (
    <div className="max-w-sm mx-auto min-h-screen flex flex-col justify-center px-6" data-testid="cp-login">
      <div className="text-[10px] tracking-[0.2em] uppercase font-bold text-[#12a16b]">Area cliente</div>
      <h1 className="text-3xl font-bold mt-1 mb-6">Accedi alla tua commessa</h1>
      <form onSubmit={submit} className="space-y-4 bg-white rounded-2xl p-5 shadow-sm">
        <div><Label className="text-xs">Email</Label><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="cp-login-email" className="h-11 rounded-xl" /></div>
        <div><Label className="text-xs">Password</Label><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="cp-login-password" className="h-11 rounded-xl" /></div>
        {err && <div className="text-sm text-rose-600" data-testid="cp-login-error">{err}</div>}
        <Button type="submit" disabled={busy} className="w-full h-11 rounded-xl bg-[#12a16b] hover:bg-[#0d7a51]" data-testid="cp-login-submit">Entra</Button>
      </form>
      <p className="text-xs text-gray-500 mt-4">L'accesso viene attivato dall'azienda dopo la verifica dei tuoi dati.</p>
    </div>
  );
}

function StatusBadge({ label }) { return <Badge className="rounded-full bg-[#e8f6f0] text-[#0d7a51] border-0 text-[10px]">{label}</Badge>; }

function CPHome() {
  const [jobs, setJobs] = React.useState(null);
  React.useEffect(() => { cp.get("/jobs").then((r) => setJobs(r.data.items)).catch((e) => toast.error(errMsg(e))); }, []);
  if (!jobs) return <div className="text-sm text-gray-500">Caricamento…</div>;
  return (
    <div className="space-y-3" data-testid="cp-jobs">
      <h2 className="text-base font-bold">Le tue commesse</h2>
      {!jobs.length && <div className="bg-white rounded-2xl p-5 text-sm text-gray-500" data-testid="cp-jobs-empty">Nessuna commessa attiva al momento.</div>}
      {jobs.map((j) => (
        <Link key={j.id} to={`/customer-portal/jobs/${j.id}`} className="block bg-white rounded-2xl p-4 shadow-sm" data-testid={`cp-job-${j.id}`}>
          <div className="flex items-center justify-between"><div className="text-xs text-gray-500">{j.contract_number || j.number}</div><StatusBadge label={j.customer_status_label} /></div>
          <div className="font-bold mt-1">{j.title || "Fornitura serramenti"}</div>
          <div className="text-xs text-gray-500 mt-1">{j.site?.street ? `${j.site.street}, ${j.site.city || ""}` : "Cantiere da definire"} · {j.lines_count} prodotti</div>
          <div className="flex items-center justify-between mt-3"><div className="text-lg font-bold text-[#12a16b]">{fmtEUR(j.total)}</div><ChevronRight size={18} className="text-gray-400" /></div>
        </Link>
      ))}
    </div>
  );
}

function CPJob() {
  const { id } = useParams();
  const [job, setJob] = React.useState(null);
  React.useEffect(() => { cp.get(`/jobs/${id}`).then((r) => setJob(r.data)).catch((e) => toast.error(errMsg(e))); }, [id]);
  if (!job) return <div className="text-sm text-gray-500">Caricamento…</div>;
  const opening = (oid) => job.openings?.find((o) => o.id === oid);
  const glass = (g) => (g ? `${g.includes("TRIPLE") ? "triplo" : "doppio"}${g.includes("SATIN") ? " satinato" : ""}` : null);
  return (
    <div className="space-y-4" data-testid="cp-job-detail">
      <Link to="/customer-portal" className="text-xs text-gray-500">← Tutte le commesse</Link>
      <div className="bg-white rounded-2xl p-4 shadow-sm">
        <div className="text-xs text-gray-500">{job.contract_number || job.number}</div>
        <div className="text-lg font-bold">{job.title}</div>
        <div className="mt-2"><StatusBadge label={job.customer_status_label} /></div>
        <div className="text-2xl font-bold text-[#12a16b] mt-3" data-testid="cp-job-total">{fmtEUR(job.total)}</div>
        {job.payment_terms_label && <div className="text-xs text-gray-500 mt-1">Pagamento: {job.payment_terms_label}</div>}
      </div>
      <section className="bg-white rounded-2xl p-4 shadow-sm" data-testid="cp-timeline">
        <h3 className="text-sm font-bold mb-3">Avanzamento</h3>
        <ol className="space-y-2">{job.timeline.map((s) => (
          <li key={s.key} className="flex items-center gap-3 text-sm"><span className={`w-3 h-3 rounded-full ${s.done ? "bg-[#12a16b]" : "bg-gray-300"}`} /><span className={s.done ? "font-medium" : "text-gray-500"}>{s.label}</span>{s.at && <span className="ml-auto text-xs text-gray-400">{fmtDate(s.at)}</span>}</li>))}</ol>
      </section>
      <section className="space-y-3" data-testid="cp-job-lines">
        <h3 className="text-sm font-bold">I tuoi prodotti</h3>
        {job.lines.map((l) => { const sp = l.visual_spec?.spec; const op = opening(l.opening_id); return (
          <div key={l.id} className="bg-white rounded-2xl p-4 shadow-sm" data-testid={`cp-line-${l.id}`}>
            <div className="flex items-center gap-2 mb-2">{op?.code && <span className="text-[10px] font-bold bg-[#12a16b] text-white rounded px-1.5 py-0.5">{op.code}</span>}<div className="font-bold text-sm">{l.description}</div><span className="ml-auto text-xs text-gray-500">× {l.quantity}</span></div>
            {op?.room && <div className="text-xs text-gray-500 mb-2">{op.room}</div>}
            {l.visual_spec && <ProductVisualSVG visual={l.visual_spec} size={220} testid={`cp-visual-${l.id}`} />}
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mt-3">
              <dt className="text-gray-500">Dimensioni</dt><dd className="font-medium">{l.width_mm} × {l.height_mm} mm</dd>
              {sp?.sash_count && <><dt className="text-gray-500">Ante</dt><dd className="font-medium">{sp.sash_count}</dd></>}
              {glass(sp?.glass_type) && <><dt className="text-gray-500">Vetro</dt><dd className="font-medium">{glass(sp.glass_type)}</dd></>}
              {sp?.interior_color_code && <><dt className="text-gray-500">Colore interno</dt><dd className="font-medium">{sp.interior_color_code} {sp.interior_color_name}</dd></>}
              {sp?.exterior_color_code && <><dt className="text-gray-500">Colore esterno</dt><dd className="font-medium">{sp.exterior_color_code} {sp.exterior_color_name}</dd></>}
              {sp?.roller_box_color && <><dt className="text-gray-500">Colore</dt><dd className="font-medium">{sp.roller_box_color.code} {sp.roller_box_color.name}</dd></>}
            </dl>
          </div>); })}
      </section>
    </div>
  );
}

function CPDocuments() {
  const [docs, setDocs] = React.useState(null);
  React.useEffect(() => { cp.get("/documents").then((r) => setDocs(r.data.items)).catch((e) => toast.error(errMsg(e))); }, []);
  const download = async (d) => { const r = await cp.get(`/documents/${d.id}/download`, { responseType: "blob" }); const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = d.filename || "documento.pdf"; a.click(); URL.revokeObjectURL(url); };
  return (
    <div className="space-y-3" data-testid="cp-documents">
      <h2 className="text-base font-bold">Documenti</h2>
      {docs && !docs.length && <div className="bg-white rounded-2xl p-5 text-sm text-gray-500" data-testid="cp-docs-empty">Nessun documento disponibile.</div>}
      {(docs || []).map((d) => (
        <div key={d.id} className="bg-white rounded-2xl p-4 shadow-sm flex items-center gap-3" data-testid={`cp-doc-${d.id}`}>
          <FileText className="text-[#12a16b]" size={20} /><div className="flex-1 min-w-0"><div className="text-sm font-medium truncate">{d.filename}</div><div className="text-xs text-gray-500">{d.category} · {fmtDate(d.generated_at)}</div></div>
          <Button size="sm" variant="outline" className="rounded-xl" onClick={() => download(d)} data-testid={`cp-doc-download-${d.id}`}><Download size={14} /></Button>
        </div>))}
    </div>
  );
}

function CPSupport() {
  const [tickets, setTickets] = React.useState([]); const [subject, setSubject] = React.useState(""); const [desc, setDesc] = React.useState("");
  const load = () => cp.get("/tickets").then((r) => setTickets(r.data.items));
  React.useEffect(() => { load(); }, []);
  const send = async (e) => { e.preventDefault(); try { await cp.post("/tickets", { subject, description: desc }); toast.success("Richiesta inviata"); setSubject(""); setDesc(""); load(); } catch (ex) { toast.error(errMsg(ex)); } };
  return (
    <div className="space-y-4" data-testid="cp-support">
      <h2 className="text-base font-bold">Assistenza</h2>
      <form onSubmit={send} className="bg-white rounded-2xl p-4 shadow-sm space-y-3">
        <Input placeholder="Oggetto" value={subject} onChange={(e) => setSubject(e.target.value)} required minLength={3} className="rounded-xl h-11" data-testid="cp-ticket-subject" />
        <textarea placeholder="Descrivi la richiesta" value={desc} onChange={(e) => setDesc(e.target.value)} required minLength={3} className="w-full rounded-xl border border-gray-200 p-3 text-sm min-h-[90px]" data-testid="cp-ticket-desc" />
        <Button type="submit" className="w-full h-11 rounded-xl bg-[#12a16b] hover:bg-[#0d7a51]" data-testid="cp-ticket-submit">Invia richiesta</Button>
      </form>
      {tickets.map((t) => (<div key={t.id} className="bg-white rounded-2xl p-4 shadow-sm" data-testid={`cp-ticket-${t.id}`}><div className="flex items-center justify-between"><div className="text-sm font-bold">{t.subject}</div><StatusBadge label={t.ticket_status} /></div><div className="text-xs text-gray-500 mt-1">{t.description}</div></div>))}
    </div>
  );
}

function CPProfile() {
  const nav = useNavigate();
  const [me, setMe] = React.useState(null);
  React.useEffect(() => { cp.get("/auth/me").then((r) => setMe(r.data)); }, []);
  const logout = async () => { await cp.post("/auth/logout").catch(() => {}); localStorage.removeItem("cp_access_token"); nav("/customer-portal/login"); };
  return (
    <div className="space-y-4" data-testid="cp-profile">
      <h2 className="text-base font-bold">Profilo</h2>
      {me && <div className="bg-white rounded-2xl p-4 shadow-sm text-sm space-y-1"><div className="font-bold">{me.first_name} {me.last_name}</div><div className="text-gray-500">{me.email}</div></div>}
      <Button variant="outline" onClick={logout} className="w-full h-11 rounded-xl" data-testid="cp-logout"><LogOut size={14} className="mr-2" /> Esci</Button>
    </div>
  );
}
