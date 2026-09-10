import { Seo, homeJsonLd } from "@/seo/Seo";
import { SEO } from "@/seo/config";
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import {
  ArrowRight, CheckCircle, ShieldCheck, ChartBar, Buildings, Factory, Truck,
  Sparkle, PhoneCall, Calendar, LockKey, Lightning, Users, ArrowUpRight,
} from "@phosphor-icons/react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MODULE_LABELS = {
  core_crm: { name: "CRM & Lead", desc: "Lead, clienti, pipeline, calendario", icon: Users },
  quotes_contracts: { name: "Preventivi & Contratti", desc: "Configuratore, listini, PDF, firme", icon: Sparkle },
  technical_abaco: { name: "Rilievo & Abaco", desc: "Misure definitive, disegno tecnico, approvazione", icon: ChartBar },
  production: { name: "Produzione", desc: "BOM, taglio, ottimizzazione barre, tracciabilità", icon: Factory },
  warehouse: { name: "Magazzino", desc: "Articoli, giacenze, scarti, movimenti", icon: Buildings },
  installation_logistics: { name: "Posa & Logistica", desc: "Squadre, calendario, verbali mobile", icon: Truck },
  service: { name: "Assistenza", desc: "Ticket, garanzie, storico interventi", icon: PhoneCall },
  administration: { name: "Amministrazione", desc: "Fatture, pagamenti, commissioni", icon: ChartBar },
  treasury: { name: "Tesoreria", desc: "Banche, fondi, IVA, ritenute, F24", icon: Lightning },
  management_control: { name: "Controllo di gestione", desc: "Costi fissi, personale, budget, break-even", icon: ChartBar },
  ai_cfo: { name: "AI CFO", desc: "Analisi, alert, scenari, suggerimenti data-driven", icon: Sparkle },
  multi_company: { name: "Multi-company", desc: "Più società, intercompany, consolidato", icon: Buildings },
  omnichannel: { name: "Omnicanale", desc: "Email, WhatsApp, moduli, inbox unificata", icon: PhoneCall },
};

const MODULE_CHECKBOXES = [
  ["core_crm", "CRM e gestione lead"],
  ["quotes_contracts", "Preventivatore, listini, PDF"],
  ["technical_abaco", "Rilievo e abaco"],
  ["production", "Produzione + lista di taglio"],
  ["warehouse", "Magazzino"],
  ["installation_logistics", "Posa e logistica"],
  ["service", "Assistenza post-vendita"],
  ["administration", "Amministrazione"],
  ["treasury", "Tesoreria e cash flow"],
  ["management_control", "Costi fissi, break-even"],
  ["ai_cfo", "AI CFO"],
  ["multi_company", "Multi-company"],
  ["omnichannel", "WhatsApp e omnicanale"],
];

const REVENUE_RANGES = [
  "meno_250k", "meno_500k", "meno_1m", "meno_2_5m", "meno_5m", "oltre_5m", "non_indicato"
];
const REVENUE_LABELS = {
  meno_250k: "Meno di €250.000", meno_500k: "€250.000 – €500.000",
  meno_1m: "€500.000 – €1.000.000", meno_2_5m: "€1.000.000 – €2.500.000",
  meno_5m: "€2.500.000 – €5.000.000", oltre_5m: "Oltre €5.000.000",
  non_indicato: "Preferisco non indicarlo",
};

export default function LandingPage() {
  const [cfg, setCfg] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    axios.get(`${API}/public-site/config`).then(r => setCfg(r.data)).catch(() => {});
  }, []);

  if (!cfg) return <div className="min-h-screen flex items-center justify-center">Caricamento…</div>;

  return (
    <div className="min-h-screen bg-white text-slate-900" data-testid="landing-page">
      <Seo title="Software Gestionale per Serramentisti" description={SEO.homeDescription} path="/landing" index jsonLd={homeJsonLd()} />
      {/* NAV */}
      <nav className="border-b border-slate-200 sticky top-0 z-40 bg-white/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2" data-testid="landing-logo">
            <div className="w-8 h-8 bg-slate-900 rounded flex items-center justify-center">
              <Sparkle size={18} weight="fill" className="text-white"/>
            </div>
            <div className="font-black tracking-tight">{cfg.product_name}</div>
          </div>
          <div className="hidden lg:flex items-center gap-8 text-sm">
            <a href="#modules" className="hover:text-red-600">Moduli</a>
            <a href="#how" className="hover:text-red-600">Come funziona</a>
            <a href="#packages" className="hover:text-red-600">Pacchetti</a>
            <a href="#security" className="hover:text-red-600">Sicurezza</a>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate("/login")} data-testid="btn-nav-login">
              {cfg.cta_secondary_text}
            </Button>
            <Button onClick={() => setFormOpen(true)} className="bg-red-600 hover:bg-red-700" data-testid="btn-nav-cta">
              {cfg.cta_primary_text}
            </Button>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 pt-20 pb-24 grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <Badge variant="outline" className="mb-4 text-xs">ERP verticale · SaaS modulare</Badge>
            <h1 className="text-5xl lg:text-6xl font-black tracking-tight leading-[1.05]" data-testid="hero-title">
              {cfg.hero_title}
            </h1>
            <p className="mt-6 text-lg text-slate-600 leading-relaxed" data-testid="hero-subtitle">
              {cfg.hero_subtitle}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" onClick={() => setFormOpen(true)} className="bg-red-600 hover:bg-red-700 text-base" data-testid="btn-hero-cta">
                {cfg.cta_primary_text}<ArrowRight size={18} className="ml-2"/>
              </Button>
              <Button size="lg" variant="outline" onClick={() => navigate("/login")} data-testid="btn-hero-login">
                {cfg.cta_secondary_text}
              </Button>
            </div>
            <p className="mt-4 text-xs text-slate-500">{cfg.cta_primary_subtitle}</p>
          </div>
          <div className="relative">
            <div className="grid grid-cols-2 gap-3">
              {[
                {label: "Lead → Preventivo", val: "1 click"},
                {label: "Break-even & Cash", val: "Real-time"},
                {label: "Multi-company", val: "Enerhia + Auxer"},
                {label: "AI CFO insights", val: "Data-driven"},
              ].map((k, i) => (
                <Card key={i} className="p-6 border-slate-200">
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">{k.label}</div>
                  <div className="text-2xl font-bold mt-2">{k.val}</div>
                </Card>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* PROBLEM */}
      <section className="bg-slate-50 py-20">
        <div className="max-w-5xl mx-auto px-6">
          <div className="overline text-slate-500 mb-2">Le sfide di ogni giorno</div>
          <h2 className="text-3xl lg:text-4xl font-black">Perché servono cinque software diversi per fare un preventivo?</h2>
          <div className="mt-10 grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              "Informazioni disperse tra Excel, email e WhatsApp",
              "Preventivi non uniformi tra commerciali",
              "Costi reali fuori controllo",
              "Passaggi tra reparti senza tracciatura",
              "Produzione scollegata dal commerciale",
              "Clienti che chiedono continuamente aggiornamenti",
              "Difficoltà nel controllo finanziario",
              "Errori nelle misure",
              "Margini non conosciuti",
              "Liste di taglio manuali",
              "Assistenza non organizzata",
              "Nessuna vista consolidata multi-società",
            ].map((p, i) => (
              <div key={i} className="flex gap-3 items-start p-4 bg-white rounded border border-slate-200">
                <div className="w-6 h-6 rounded-full bg-red-100 text-red-600 flex items-center justify-center text-xs font-bold flex-shrink-0">✕</div>
                <div className="text-sm">{p}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* MODULES */}
      <section id="modules" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="overline text-slate-500 mb-2">Un solo sistema, tutti i moduli</div>
          <h2 className="text-3xl lg:text-4xl font-black mb-3">Modulare, come la tua azienda</h2>
          <p className="text-slate-600 mb-10 max-w-2xl">Attivi solo quello che ti serve. Puoi aggiungere moduli in qualsiasi momento.</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(cfg.public_module_codes || []).map(code => {
              const m = MODULE_LABELS[code];
              if (!m) return null;
              const Icon = m.icon;
              return (
                <Card key={code} className="p-6 hover:border-red-600 transition" data-testid={`landing-module-${code}`}>
                  <Icon size={24} className="text-red-600 mb-3"/>
                  <div className="font-bold">{m.name}</div>
                  <div className="text-sm text-slate-600 mt-1">{m.desc}</div>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="bg-slate-900 text-white py-20">
        <div className="max-w-6xl mx-auto px-6">
          <div className="overline text-slate-400 mb-2">Il flusso completo</div>
          <h2 className="text-3xl lg:text-4xl font-black mb-10">Lead → Preventivo → Contratto → Produzione → Posa → Assistenza → Cash</h2>
          <div className="flex flex-wrap gap-3 items-center text-sm">
            {["Lead", "Preventivo", "Contratto", "Rilievo", "Abaco", "Produzione", "Posa", "Assistenza", "Tesoreria", "AI CFO"].map((s, i) => (
              <React.Fragment key={s}>
                <div className="px-4 py-2 border border-white/20 rounded-full">{s}</div>
                {i < 9 && <ArrowRight size={16} className="text-slate-400"/>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* PACKAGES */}
      <section id="packages" className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <div className="overline text-slate-500 mb-2">Pacchetti configurabili</div>
          <h2 className="text-3xl lg:text-4xl font-black mb-3">Scegli come iniziare</h2>
          <p className="text-slate-600 mb-10 max-w-2xl">
            Ogni pacchetto è personalizzabile. Aggiungi moduli in qualsiasi momento. Prezzi da concordare in base alla tua struttura.
          </p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {(cfg.packages || []).map(p => (
              <Card key={p.code} className={`p-6 ${p.badge === "Popolare" ? "border-red-600 border-2" : ""}`} data-testid={`landing-package-${p.code}`}>
                {p.badge && <Badge className="mb-3 bg-red-600 text-white">{p.badge}</Badge>}
                <div className="text-2xl font-bold">{p.name}</div>
                <div className="text-sm text-slate-600 mt-2 min-h-[3rem]">{p.description}</div>
                <div className="mt-4 space-y-1 text-xs text-slate-500">
                  <div>👥 Fino a {p.max_users || "∞"} utenti</div>
                  <div>💾 {p.max_storage_mb ? `${(p.max_storage_mb/1000).toFixed(1)} GB storage` : "Storage flessibile"}</div>
                  <div>🏢 {p.max_legal_entities || 1} società</div>
                  <div>⏱ Trial {p.trial_days} giorni</div>
                </div>
                <div className="mt-4 flex flex-wrap gap-1">
                  {(p.included_module_codes || []).slice(0, 4).map(c => (
                    <Badge key={c} variant="outline" className="text-[10px]">{MODULE_LABELS[c]?.name || c}</Badge>
                  ))}
                  {p.included_module_codes.length > 4 && (
                    <Badge variant="outline" className="text-[10px]">+{p.included_module_codes.length - 4}</Badge>
                  )}
                </div>
                <Button className="w-full mt-5 bg-slate-900" onClick={() => setFormOpen(true)} data-testid={`btn-pkg-${p.code}`}>
                  Parlane con noi<ArrowRight size={14} className="ml-1"/>
                </Button>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* SECURITY */}
      <section id="security" className="bg-slate-50 py-20">
        <div className="max-w-5xl mx-auto px-6">
          <div className="overline text-slate-500 mb-2">Sicurezza e fiducia</div>
          <h2 className="text-3xl lg:text-4xl font-black">Dati protetti, accessi controllati, tutto tracciato</h2>
          <div className="mt-10 grid md:grid-cols-2 gap-4">
            {[
              { i: LockKey, t: "Accessi per ruolo", d: "20+ ruoli configurabili, permessi granulari per modulo/pagina/azione." },
              { i: ShieldCheck, t: "Isolamento dei dati", d: "Tenant-scoping su ogni entità. Multi-company con separazione per legal entity." },
              { i: ChartBar, t: "Audit completo", d: "Ogni azione critica registrata con utente, timestamp, before/after." },
              { i: Users, t: "Documenti protetti", d: "Snapshot immutabili per preventivi PDF, contratti firmati, abaco definitivo." },
            ].map((f, i) => {
              const Icon = f.i;
              return (
                <div key={i} className="flex gap-4">
                  <div className="w-10 h-10 rounded bg-slate-900 text-white flex-shrink-0 flex items-center justify-center">
                    <Icon size={20}/>
                  </div>
                  <div>
                    <div className="font-bold">{f.t}</div>
                    <div className="text-sm text-slate-600 mt-1">{f.d}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="py-20 bg-red-600 text-white">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-4xl lg:text-5xl font-black">Pronto a metterci ordine?</h2>
          <p className="mt-4 text-lg opacity-90">{cfg.cta_primary_subtitle}</p>
          <div className="mt-8 flex justify-center gap-3 flex-wrap">
            <Button size="lg" className="bg-white text-red-600 hover:bg-slate-100" onClick={() => setFormOpen(true)} data-testid="btn-final-cta">
              {cfg.cta_primary_text}<ArrowRight size={18} className="ml-2"/>
            </Button>
            <Button size="lg" variant="outline" className="border-white text-white hover:bg-white hover:text-red-600" onClick={() => navigate("/login")}>
              {cfg.cta_secondary_text}
            </Button>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 py-10">
        <div className="max-w-7xl mx-auto px-6 flex flex-wrap items-center justify-between text-sm text-slate-500 gap-4">
          <div>© {new Date().getFullYear()} {cfg.product_name}</div>
          <div className="flex gap-4">
            {cfg.privacy_policy_url && <a href={cfg.privacy_policy_url}>Privacy</a>}
            {cfg.cookie_policy_url && <a href={cfg.cookie_policy_url}>Cookie</a>}
            {cfg.terms_url && <a href={cfg.terms_url}>Termini</a>}
          </div>
        </div>
      </footer>

      <LeadForm open={formOpen} onOpenChange={setFormOpen} cfg={cfg}/>
    </div>
  );
}


function LeadForm({ open, onOpenChange, cfg }) {
  const [form, setForm] = useState({
    first_name: "", last_name: "", role: "",
    email: "", phone: "", whatsapp: "",
    company_name: "", legal_name: "", vat_number: "",
    website: "", city: "", province: "", region: "", country: "IT",
    operational_area: "",
    num_employees: "", num_sales: "", num_installers: "",
    has_internal_production: false, revenue_range: "",
    quotes_per_month: "", orders_per_month: "",
    current_software: "", main_problems: "", goals: "", notes: "",
    interested_module_codes: [],
    privacy_consent: false, marketing_consent: false,
    contact_availability: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const toggleModule = (code) => {
    setForm(f => ({
      ...f,
      interested_module_codes: f.interested_module_codes.includes(code)
        ? f.interested_module_codes.filter(x => x !== code)
        : [...f.interested_module_codes, code],
    }));
  };

  const submit = async () => {
    if (!form.privacy_consent) { toast.error("Devi accettare la privacy"); return; }
    if (!form.first_name || !form.last_name || !form.email || !form.company_name) {
      toast.error("Compila nome, cognome, email e azienda"); return;
    }
    setSubmitting(true);
    try {
      const payload = { ...form };
      ["num_employees", "num_sales", "num_installers", "quotes_per_month", "orders_per_month"].forEach(k => {
        payload[k] = payload[k] ? Number(payload[k]) : null;
      });
      const utm = new URLSearchParams(window.location.search);
      payload.utm_source = utm.get("utm_source") || undefined;
      payload.utm_medium = utm.get("utm_medium") || undefined;
      payload.utm_campaign = utm.get("utm_campaign") || undefined;
      payload.referrer = document.referrer || undefined;
      const { data } = await axios.post(`${API}/public-site/leads`, payload);
      setResult(data);
      toast.success(data.duplicate ? "Richiesta già registrata" : "Richiesta inviata");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Errore invio");
    } finally { setSubmitting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setResult(null); }}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="lead-form-dialog">
        {result ? (
          <div className="py-6 text-center">
            <CheckCircle size={48} weight="fill" className="text-green-600 mx-auto mb-4"/>
            <div className="text-2xl font-bold mb-2">Grazie!</div>
            <p className="text-slate-600 mb-4">{result.message}</p>
            {result.suggested_package && (
              <Card className="p-4 text-left max-w-md mx-auto">
                <div className="overline text-slate-500">Pacchetto suggerito</div>
                <div className="font-bold text-lg">{result.suggested_package}</div>
                <div className="text-sm text-slate-600 mt-1">{result.reason}</div>
              </Card>
            )}
            <Button className="mt-6" onClick={() => onOpenChange(false)} data-testid="btn-close-success">Chiudi</Button>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{cfg.cta_primary_text}</DialogTitle>
              <p className="text-sm text-slate-500">{cfg.cta_primary_subtitle}</p>
            </DialogHeader>
            <div className="space-y-6">
              <div>
                <div className="overline mb-2">Chi sei</div>
                <div className="grid md:grid-cols-2 gap-3">
                  <div><Label>Nome *</Label><Input value={form.first_name} onChange={e => setForm({...form, first_name: e.target.value})} data-testid="lead-first-name"/></div>
                  <div><Label>Cognome *</Label><Input value={form.last_name} onChange={e => setForm({...form, last_name: e.target.value})} data-testid="lead-last-name"/></div>
                  <div><Label>Ruolo</Label><Input value={form.role} onChange={e => setForm({...form, role: e.target.value})}/></div>
                  <div><Label>Email *</Label><Input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} data-testid="lead-email"/></div>
                  <div><Label>Telefono</Label><Input value={form.phone} onChange={e => setForm({...form, phone: e.target.value})}/></div>
                  <div><Label>WhatsApp</Label><Input value={form.whatsapp} onChange={e => setForm({...form, whatsapp: e.target.value})}/></div>
                </div>
              </div>
              <div>
                <div className="overline mb-2">L'azienda</div>
                <div className="grid md:grid-cols-2 gap-3">
                  <div><Label>Nome azienda *</Label><Input value={form.company_name} onChange={e => setForm({...form, company_name: e.target.value})} data-testid="lead-company"/></div>
                  <div><Label>Ragione sociale</Label><Input value={form.legal_name} onChange={e => setForm({...form, legal_name: e.target.value})}/></div>
                  <div><Label>P.IVA</Label><Input value={form.vat_number} onChange={e => setForm({...form, vat_number: e.target.value})}/></div>
                  <div><Label>Sito web</Label><Input value={form.website} onChange={e => setForm({...form, website: e.target.value})}/></div>
                  <div><Label>Città (sede)</Label><Input value={form.city} onChange={e => setForm({...form, city: e.target.value})}/></div>
                  <div><Label>Provincia</Label><Input value={form.province} onChange={e => setForm({...form, province: e.target.value})}/></div>
                  <div><Label>Regione</Label><Input value={form.region} onChange={e => setForm({...form, region: e.target.value})}/></div>
                  <div><Label>Area geografica operativa</Label><Input value={form.operational_area} onChange={e => setForm({...form, operational_area: e.target.value})}/></div>
                </div>
              </div>
              <div>
                <div className="overline mb-2">La struttura</div>
                <div className="grid md:grid-cols-3 gap-3">
                  <div><Label>Dipendenti</Label><Input type="number" value={form.num_employees} onChange={e => setForm({...form, num_employees: e.target.value})}/></div>
                  <div><Label>Commerciali</Label><Input type="number" value={form.num_sales} onChange={e => setForm({...form, num_sales: e.target.value})}/></div>
                  <div><Label>Posatori</Label><Input type="number" value={form.num_installers} onChange={e => setForm({...form, num_installers: e.target.value})}/></div>
                  <div><Label>Preventivi/mese</Label><Input type="number" value={form.quotes_per_month} onChange={e => setForm({...form, quotes_per_month: e.target.value})}/></div>
                  <div><Label>Commesse/mese</Label><Input type="number" value={form.orders_per_month} onChange={e => setForm({...form, orders_per_month: e.target.value})}/></div>
                  <div>
                    <Label>Volume d'affari</Label>
                    <Select value={form.revenue_range} onValueChange={v => setForm({...form, revenue_range: v})}>
                      <SelectTrigger data-testid="lead-revenue"><SelectValue placeholder="—"/></SelectTrigger>
                      <SelectContent>
                        {REVENUE_RANGES.map(r => <SelectItem key={r} value={r}>{REVENUE_LABELS[r]}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <label className="flex items-center gap-2 mt-3 text-sm">
                  <Checkbox checked={form.has_internal_production} onCheckedChange={v => setForm({...form, has_internal_production: !!v})} data-testid="lead-has-production"/>
                  Produzione interna
                </label>
              </div>
              <div>
                <div className="overline mb-2">Cosa ti interessa</div>
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {MODULE_CHECKBOXES.map(([code, label]) => (
                    <label key={code} className="flex items-center gap-2 text-sm p-2 rounded hover:bg-slate-50 cursor-pointer">
                      <Checkbox checked={form.interested_module_codes.includes(code)} onCheckedChange={() => toggleModule(code)} data-testid={`lead-mod-${code}`}/>
                      {label}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <div className="overline mb-2">Situazione attuale</div>
                <div className="space-y-2">
                  <div><Label>Software attualmente usati</Label><Input value={form.current_software} onChange={e => setForm({...form, current_software: e.target.value})}/></div>
                  <div><Label>Problemi principali</Label><Textarea rows={2} value={form.main_problems} onChange={e => setForm({...form, main_problems: e.target.value})}/></div>
                  <div><Label>Obiettivi</Label><Textarea rows={2} value={form.goals} onChange={e => setForm({...form, goals: e.target.value})}/></div>
                  <div><Label>Note aggiuntive</Label><Textarea rows={2} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})}/></div>
                  <div><Label>Disponibilità contatto</Label><Input placeholder="Es. Lun-Ven 9-18" value={form.contact_availability} onChange={e => setForm({...form, contact_availability: e.target.value})}/></div>
                </div>
              </div>
              <div className="space-y-2 border-t pt-4">
                <label className="flex items-start gap-2 text-sm">
                  <Checkbox checked={form.privacy_consent} onCheckedChange={v => setForm({...form, privacy_consent: !!v})} data-testid="lead-privacy"/>
                  <span>Ho letto e accetto la <a href="#" className="underline">Privacy Policy</a> *</span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <Checkbox checked={form.marketing_consent} onCheckedChange={v => setForm({...form, marketing_consent: !!v})} data-testid="lead-marketing"/>
                  <span>Acconsento a ricevere aggiornamenti commerciali (opzionale)</span>
                </label>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
              <Button onClick={submit} disabled={submitting} className="bg-red-600 hover:bg-red-700" data-testid="btn-submit-lead">
                {submitting ? "Invio…" : "Invia richiesta"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
