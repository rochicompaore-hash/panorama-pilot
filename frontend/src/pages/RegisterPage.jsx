import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Seo } from "@/seo/Seo";
import AuthLayout from "@/layouts/AuthLayout";
import { AuthTabs } from "@/components/app/AuthTabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { API_BASE, formatApiError } from "@/api/client";
import { CheckCircle } from "@phosphor-icons/react";

const EMPTY = { first_name: "", last_name: "", email: "", phone: "", password: "", password_confirm: "", requested_role: "", company_name: "" };

const Field = ({ id, label, ...props }) => (
  <div className="space-y-1.5">
    <Label htmlFor={id} className="overline">{label}</Label>
    <Input id={id} className="rounded-sm h-11" data-testid={`register-${id.replace(/_/g, "-")}-input`} {...props} />
  </div>
);

export default function RegisterPage() {
  const navigate = useNavigate();
  const [roles, setRoles] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => { axios.get(`${API_BASE}/auth/register/roles`).then((r) => setRoles(r.data.items || [])).catch(() => setRoles([])); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.password !== form.password_confirm) { setError("Le password non coincidono."); return; }
    if (!form.requested_role) { setError("Seleziona il ruolo richiesto."); return; }
    setLoading(true);
    try {
      const { data } = await axios.post(`${API_BASE}/auth/register`, form);
      localStorage.setItem("registration_request_id", data.request_id);
      setDone(data);
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(formatApiError(d) || err.message);
      if (d?.code === "ACCOUNT_ALREADY_EXISTS") setTimeout(() => {}, 0);
    } finally { setLoading(false); }
  };

  if (done) {
    return (
      <AuthLayout title="Registrazione ricevuta" testId="register-success-page">
        <Seo title="Registrati" path="/register" />
        <div className="space-y-5" data-testid="register-success">
          <div className="flex items-start gap-3 p-4 border border-border rounded-sm bg-secondary/40">
            <CheckCircle size={28} weight="fill" className="text-[#12a16b] shrink-0" />
            <div>
              <div className="font-semibold">✓ Registrazione ricevuta</div>
              <p className="text-sm text-muted-foreground mt-1">
                Ti abbiamo inviato un'email per confermare il tuo indirizzo. Riceverai una comunicazione quando il tuo account sarà stato verificato e approvato.
              </p>
            </div>
          </div>
          <div className="text-xs text-muted-foreground font-mono" data-testid="register-request-id">Riferimento richiesta: {done.request_id}</div>
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" className="rounded-sm" onClick={() => navigate("/registration-status")} data-testid="register-go-status">Stato richiesta</Button>
            <Button variant="ghost" className="rounded-sm" onClick={() => navigate("/login")} data-testid="register-go-login">Torna al login</Button>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Richiedi l'accesso" subtitle="Compila i dati e indica il ruolo richiesto. L'account viene attivato solo dopo verifica email e approvazione dell'amministratore." testId="register-page">
      <Seo title="Registrati" description="Richiedi l'accesso a Panorama Pilot come cliente, commerciale o collaboratore. L'account viene attivato dopo approvazione amministrativa." path="/register" />
      <AuthTabs active="register" />
      <form onSubmit={submit} className="space-y-4 pb-6" data-testid="register-form">
        {error && <Alert variant="destructive" className="rounded-sm" data-testid="register-error"><AlertDescription>{error} {error.includes("già un account") && <Link to="/forgot-password" className="underline">Recupera password</Link>}</AlertDescription></Alert>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field id="first_name" label="Nome" required value={form.first_name} onChange={set("first_name")} autoComplete="given-name" />
          <Field id="last_name" label="Cognome" required value={form.last_name} onChange={set("last_name")} autoComplete="family-name" />
        </div>
        <Field id="email" label="Email" type="email" required value={form.email} onChange={set("email")} autoComplete="email" />
        <Field id="phone" label="Telefono" type="tel" required value={form.phone} onChange={set("phone")} autoComplete="tel" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field id="password" label="Password (min. 8)" type="password" required minLength={8} value={form.password} onChange={set("password")} autoComplete="new-password" />
          <Field id="password_confirm" label="Conferma password" type="password" required minLength={8} value={form.password_confirm} onChange={set("password_confirm")} autoComplete="new-password" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="requested_role" className="overline">Ruolo richiesto</Label>
          <select id="requested_role" required value={form.requested_role} onChange={set("requested_role")} data-testid="register-requested-role-select"
            className="w-full h-11 rounded-sm border border-input bg-background px-3 text-sm">
            <option value="">Seleziona…</option>
            {roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
          </select>
          <p className="text-xs text-muted-foreground">Il ruolo è una richiesta: quello effettivo viene assegnato dall'amministratore.</p>
        </div>
        <Field id="company_name" label="Azienda / Organizzazione (opzionale)" value={form.company_name} onChange={set("company_name")} autoComplete="organization" />
        <Button type="submit" disabled={loading} className="w-full h-11 rounded-sm" data-testid="register-submit-button">
          {loading ? "Invio…" : "REGISTRATI"}
        </Button>
        <p className="text-xs text-center text-muted-foreground">Hai già un account? <Link to="/login" className="underline" data-testid="register-login-link">Accedi</Link></p>
      </form>
    </AuthLayout>
  );
}
