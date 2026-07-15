import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import { ArrowRight, Check, Buildings, Image as ImageIcon, Hash, UserPlus, User, Sparkle } from "@phosphor-icons/react";

const STEPS = [
  { key: "welcome", label: "Benvenuto", icon: Sparkle },
  { key: "company", label: "Azienda", icon: Buildings },
  { key: "logo", label: "Logo", icon: ImageIcon },
  { key: "sequences", label: "Numerazioni", icon: Hash },
  { key: "invite", label: "Team", icon: UserPlus },
  { key: "lead", label: "Primo lead", icon: User },
  { key: "done", label: "Fatto", icon: Check },
];

export default function OnboardingWizard() {
  const { t } = useTranslation();
  const { loadMe } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [inviteUrl, setInviteUrl] = useState("");
  const [companyForm, setCompanyForm] = useState({ name: "", legal_name: "", vat_number: "", city: "", province: "", phone: "", email: "" });
  const [logoForm, setLogoForm] = useState({ logo_url: "" });
  const [seqForm, setSeqForm] = useState({ quote_prefix: "PRV-", quote_padding: 5, order_prefix: "ORD-", order_padding: 5, year_reset: true });
  const [inviteForm, setInviteForm] = useState({ email: "", first_name: "", last_name: "", role_slug: "commerciale" });
  const [leadForm, setLeadForm] = useState({ first_name: "Mario", last_name: "Rossi", email: "mario.rossi@example.com", phone: "+39 3331234567", estimated_value: 8500, source: "onboarding" });

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/onboarding/state");
        setCompanyForm(f => ({ ...f, name: data.company_name || "" }));
        if (data.state?.completed) navigate("/dashboard");
        else setStep(Math.max(0, data.state?.step || 0) + 0);
      } catch {}
    })();
  }, [navigate]);

  const doStep = async (fn) => {
    setBusy(true);
    try { await fn(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || e.message); }
    finally { setBusy(false); }
  };

  const submitCompany = () => doStep(async () => {
    await api.post("/onboarding/step-company", companyForm);
    setStep(2);
  });
  const submitLogo = () => doStep(async () => {
    await api.post("/onboarding/step-logo", logoForm);
    setStep(3);
  });
  const submitSequences = () => doStep(async () => {
    await api.post("/onboarding/step-sequences", seqForm);
    setStep(4);
  });
  const submitInvite = () => doStep(async () => {
    if (!inviteForm.email) { setStep(5); return; }
    const { data } = await api.post("/onboarding/step-invite", inviteForm);
    if (data.invitation_url) setInviteUrl(data.invitation_url);
    setStep(5);
  });
  const submitLead = () => doStep(async () => {
    await api.post("/onboarding/step-first-lead", { ...leadForm, estimated_value: Number(leadForm.estimated_value) });
    setStep(6);
  });
  const finish = () => doStep(async () => {
    await api.post("/onboarding/complete");
    await loadMe();
    toast.success("Setup completato! Buon lavoro.");
    navigate("/dashboard");
  });
  const skip = () => doStep(async () => {
    await api.post("/onboarding/skip");
    await loadMe();
    navigate("/dashboard");
  });

  const progress = Math.min(100, Math.round((step / (STEPS.length - 1)) * 100));

  return (
    <div className="min-h-screen bg-background flex flex-col" data-testid="onboarding-wizard">
      <header className="border-b border-border p-4 lg:px-10 flex items-center justify-between">
        <div>
          <div className="overline">Setup guidato · 5 minuti</div>
          <div className="font-display text-lg font-black tracking-tight">Infissi Express Cloud</div>
        </div>
        <button onClick={skip} className="text-xs text-muted-foreground hover:text-foreground underline" data-testid="ob-skip">{t("onboarding.skip")}</button>
      </header>

      <div className="border-b border-border">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <Progress value={progress} className="h-1 bg-secondary" />
          <div className="mt-4 hidden md:flex items-center justify-between text-[10px] font-mono-plex uppercase tracking-widest">
            {STEPS.map((s, i) => (
              <div key={s.key} className={`flex items-center gap-1 ${i <= step ? "text-foreground" : "text-muted-foreground"}`}>
                {i < step ? <Check size={12} weight="bold" /> : <span className={`h-4 w-4 flex items-center justify-center ${i === step ? "bg-[hsl(var(--brand-red))] text-white" : "bg-secondary"}`}>{i + 1}</span>}
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 max-w-2xl w-full mx-auto px-4 py-10">
        {step === 0 && (
          <div className="text-center py-10" data-testid="ob-welcome">
            <div className="overline">Milestone 2 · CRM attivato</div>
            <h1 className="mt-4 font-display text-4xl sm:text-5xl font-black tracking-tight">{t("onboarding.welcome_title")}</h1>
            <p className="mt-4 text-muted-foreground max-w-lg mx-auto">{t("onboarding.welcome_sub")}</p>
            <Button size="lg" className="mt-8 rounded-sm h-12 px-8 gap-2" onClick={() => setStep(1)} data-testid="ob-start">
              {t("onboarding.start")} <ArrowRight size={16} />
            </Button>
          </div>
        )}

        {step === 1 && (
          <Card className="rounded-sm border-border p-8" data-testid="ob-company">
            <div className="overline">Step 1 di 5</div>
            <h2 className="mt-1 font-display text-3xl font-black tracking-tight">{t("onboarding.step_company")}</h2>
            <div className="mt-6 space-y-3">
              <div><Label className="overline">Ragione sociale</Label><Input value={companyForm.name} onChange={(e) => setCompanyForm(f => ({ ...f, name: e.target.value }))} className="rounded-sm h-10" data-testid="ob-c-name" /></div>
              <div><Label className="overline">P.IVA</Label><Input value={companyForm.vat_number} onChange={(e) => setCompanyForm(f => ({ ...f, vat_number: e.target.value }))} className="rounded-sm h-10 font-mono-plex" data-testid="ob-c-vat" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="overline">Città</Label><Input value={companyForm.city} onChange={(e) => setCompanyForm(f => ({ ...f, city: e.target.value }))} className="rounded-sm h-10" data-testid="ob-c-city" /></div>
                <div><Label className="overline">Provincia</Label><Input value={companyForm.province} onChange={(e) => setCompanyForm(f => ({ ...f, province: e.target.value }))} className="rounded-sm h-10" data-testid="ob-c-prov" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="overline">Telefono</Label><Input value={companyForm.phone} onChange={(e) => setCompanyForm(f => ({ ...f, phone: e.target.value }))} className="rounded-sm h-10" data-testid="ob-c-phone" /></div>
                <div><Label className="overline">Email</Label><Input value={companyForm.email} onChange={(e) => setCompanyForm(f => ({ ...f, email: e.target.value }))} className="rounded-sm h-10" data-testid="ob-c-email" /></div>
              </div>
            </div>
            <Button className="mt-6 rounded-sm w-full h-11" disabled={busy || !companyForm.name} onClick={submitCompany} data-testid="ob-c-next">{t("onboarding.next")} →</Button>
          </Card>
        )}

        {step === 2 && (
          <Card className="rounded-sm border-border p-8" data-testid="ob-logo">
            <div className="overline">Step 2 di 5</div>
            <h2 className="mt-1 font-display text-3xl font-black tracking-tight">{t("onboarding.step_logo")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">Incolla l'URL del logo aziendale (verrà usato su preventivi, ordini, PDF). Puoi anche saltare.</p>
            <div className="mt-6"><Label className="overline">URL Logo</Label><Input placeholder="https://…" value={logoForm.logo_url} onChange={(e) => setLogoForm(f => ({ ...f, logo_url: e.target.value }))} className="rounded-sm h-10 font-mono-plex" data-testid="ob-logo-url" /></div>
            <div className="flex gap-2 mt-6"><Button variant="outline" className="rounded-sm h-11" onClick={() => setStep(1)}>← {t("onboarding.back")}</Button>
              <Button className="rounded-sm h-11 flex-1" disabled={busy} onClick={submitLogo} data-testid="ob-logo-next">{t("onboarding.next")} →</Button></div>
          </Card>
        )}

        {step === 3 && (
          <Card className="rounded-sm border-border p-8" data-testid="ob-sequences">
            <div className="overline">Step 3 di 5</div>
            <h2 className="mt-1 font-display text-3xl font-black tracking-tight">{t("onboarding.step_sequences")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">Come vuoi numerare preventivi e ordini?</p>
            <div className="mt-6 grid grid-cols-2 gap-4">
              <div><Label className="overline">Prefisso preventivi</Label><Input value={seqForm.quote_prefix} onChange={(e) => setSeqForm(f => ({ ...f, quote_prefix: e.target.value }))} className="rounded-sm h-10 font-mono-plex" data-testid="ob-s-qp" /></div>
              <div><Label className="overline">Prefisso ordini</Label><Input value={seqForm.order_prefix} onChange={(e) => setSeqForm(f => ({ ...f, order_prefix: e.target.value }))} className="rounded-sm h-10 font-mono-plex" data-testid="ob-s-op" /></div>
            </div>
            <div className="mt-3 text-xs text-muted-foreground font-mono-plex">
              Esempio: {seqForm.quote_prefix}{new Date().getFullYear()}/00001
            </div>
            <div className="flex gap-2 mt-6"><Button variant="outline" className="rounded-sm h-11" onClick={() => setStep(2)}>← {t("onboarding.back")}</Button>
              <Button className="rounded-sm h-11 flex-1" disabled={busy} onClick={submitSequences} data-testid="ob-s-next">{t("onboarding.next")} →</Button></div>
          </Card>
        )}

        {step === 4 && (
          <Card className="rounded-sm border-border p-8" data-testid="ob-invite">
            <div className="overline">Step 4 di 5</div>
            <h2 className="mt-1 font-display text-3xl font-black tracking-tight">{t("onboarding.step_invite")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">Invita il primo commerciale del team (opzionale, puoi saltare).</p>
            <div className="mt-6 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="overline">Nome</Label><Input value={inviteForm.first_name} onChange={(e) => setInviteForm(f => ({ ...f, first_name: e.target.value }))} className="rounded-sm h-10" data-testid="ob-i-first" /></div>
                <div><Label className="overline">Cognome</Label><Input value={inviteForm.last_name} onChange={(e) => setInviteForm(f => ({ ...f, last_name: e.target.value }))} className="rounded-sm h-10" data-testid="ob-i-last" /></div>
              </div>
              <div><Label className="overline">Email</Label><Input type="email" value={inviteForm.email} onChange={(e) => setInviteForm(f => ({ ...f, email: e.target.value }))} className="rounded-sm h-10" data-testid="ob-i-email" /></div>
            </div>
            {inviteUrl && <div className="mt-3 text-[10px] font-mono-plex text-muted-foreground break-all p-2 bg-secondary" data-testid="ob-i-url">Link invito: {inviteUrl}</div>}
            <div className="flex gap-2 mt-6"><Button variant="outline" className="rounded-sm h-11" onClick={() => setStep(3)}>← {t("onboarding.back")}</Button>
              <Button className="rounded-sm h-11 flex-1" disabled={busy} onClick={submitInvite} data-testid="ob-i-next">{t("onboarding.next")} →</Button></div>
          </Card>
        )}

        {step === 5 && (
          <Card className="rounded-sm border-border p-8" data-testid="ob-lead">
            <div className="overline">Step 5 di 5</div>
            <h2 className="mt-1 font-display text-3xl font-black tracking-tight">{t("onboarding.step_lead")}</h2>
            <p className="mt-2 text-sm text-muted-foreground">Creiamo un lead di esempio: potrai esplorare tutte le funzionalità.</p>
            <div className="mt-6 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="overline">Nome</Label><Input value={leadForm.first_name} onChange={(e) => setLeadForm(f => ({ ...f, first_name: e.target.value }))} className="rounded-sm h-10" data-testid="ob-l-first" /></div>
                <div><Label className="overline">Cognome</Label><Input value={leadForm.last_name} onChange={(e) => setLeadForm(f => ({ ...f, last_name: e.target.value }))} className="rounded-sm h-10" data-testid="ob-l-last" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="overline">Email</Label><Input value={leadForm.email} onChange={(e) => setLeadForm(f => ({ ...f, email: e.target.value }))} className="rounded-sm h-10" data-testid="ob-l-email" /></div>
                <div><Label className="overline">Telefono</Label><Input value={leadForm.phone} onChange={(e) => setLeadForm(f => ({ ...f, phone: e.target.value }))} className="rounded-sm h-10" data-testid="ob-l-phone" /></div>
              </div>
              <div><Label className="overline">Valore stimato €</Label><Input type="number" value={leadForm.estimated_value} onChange={(e) => setLeadForm(f => ({ ...f, estimated_value: e.target.value }))} className="rounded-sm h-10" data-testid="ob-l-value" /></div>
            </div>
            <div className="flex gap-2 mt-6"><Button variant="outline" className="rounded-sm h-11" onClick={() => setStep(4)}>← {t("onboarding.back")}</Button>
              <Button className="rounded-sm h-11 flex-1" disabled={busy} onClick={submitLead} data-testid="ob-l-next">Crea lead →</Button></div>
          </Card>
        )}

        {step === 6 && (
          <Card className="rounded-sm border-border p-10 text-center" data-testid="ob-done">
            <Check size={48} weight="bold" className="mx-auto text-emerald-500" />
            <div className="overline mt-4">Setup completato</div>
            <h2 className="mt-2 font-display text-4xl font-black tracking-tight">{t("onboarding.completed")}</h2>
            <p className="mt-3 text-sm text-muted-foreground max-w-md mx-auto">{t("onboarding.tour_dashboard")}</p>
            <Button className="mt-8 rounded-sm h-12 px-8" onClick={finish} disabled={busy} data-testid="ob-finish">{t("onboarding.finish")}</Button>
          </Card>
        )}
      </div>
    </div>
  );
}
